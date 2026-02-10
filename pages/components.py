from dash import html, dcc
from dash_extensions.javascript import Namespace
from datetime import date
from functions.convex_hull import generate_convex_hulls
from functions.sql_helpers import get_latest_date_processed
from html import unescape
from typing import Optional, Sequence, List
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_mantine_components as dmc
import geopandas as gpd
import json
import logging
import numpy as np
import pandas as pd
import re
import sqlite3

DB_PATH = "assets/datasets/larentals.db"
DEFAULT_SPEED_MAX = 1.0
logger = logging.getLogger(__name__)

def _require_safe_identifier(name: str, *, field_name: str) -> str:
    """
    Validate a SQL identifier (table/column/index name).

    Args:
        name: The identifier to validate.
        field_name: Label for error messages.

    Returns:
        The original name if valid.

    Raises:
        ValueError: If the identifier is unsafe.
    """
    _IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    if not _IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"Unsafe SQL identifier for {field_name}: {name!r}")
    return name

# Create a class to hold all common components for both Lease and Buy pages
class BaseClass:
    def __init__(
        self,
        table_name: str,
        page_type: str,
        *,
        select_columns: Optional[Sequence[str]] = None,
    ) -> None:
        """
        Load a table/view from SQLite and prepare the DataFrame.

        Args:
            table_name: SQLite table/view name (e.g. "lease" or "buy").
            page_type: Page context ("lease" or "buy").
            select_columns: Optional list/tuple of columns to select instead of SELECT *.
                Use this to shrink payload for faster startup and smaller GeoJSON.
        """
        safe_table = _require_safe_identifier(table_name, field_name="table_name")

        if select_columns is None:
            sql = f"SELECT * FROM {safe_table}"
        else:
            if not select_columns:
                raise ValueError("select_columns cannot be empty when provided")

            safe_cols = [
                _require_safe_identifier(col, field_name="select_columns") for col in select_columns
            ]
            sql = f"SELECT {', '.join(safe_cols)} FROM {safe_table}"

        conn = sqlite3.connect(DB_PATH)
        try:
            self.df = pd.read_sql_query(sql, conn)
            self._attach_isp_speeds(conn, table_name=safe_table)
            if select_columns is not None:
                keep_cols = [col for col in select_columns if col in self.df.columns]
                for col in ("best_dn", "best_up"):
                    if col in self.df.columns and col not in keep_cols:
                        keep_cols.append(col)
                self.df = self.df[keep_cols]
        finally:
            conn.close()

        self.page_type = page_type

        # 1.5) Coerce numeric columns that may come back as object (SQLite)
        numeric_cols = [
            # coordinates
            "latitude", "longitude",

            # shared-ish numeric fields
            "bedrooms", "sqft", "year_built", "ppsqft", "list_price", "olp",
            "parking_spaces", "garage_spaces", "lot_size",

            # buy bathrooms / HOA
            "total_bathrooms", "full_bathrooms", "half_bathrooms",
            "three_quarter_bathrooms", "quarter_bathrooms",
            "hoa_fee", "space_rent",

            # lease deposits (won’t exist on buy)
            "key_deposit", "other_deposit", "pet_deposit", "security_deposit",
            "best_dn", "best_up",
        ]
        for col in numeric_cols:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors="coerce")

        # 2) Coerce date columns to datetime
        if "listed_date" in self.df.columns:
            self.df["listed_date"] = pd.to_datetime(self.df["listed_date"], errors="coerce")

        # 3) Build GeoDataFrame if coords exist
        if {"latitude", "longitude"}.issubset(self.df.columns):
            geom = gpd.points_from_xy(self.df["longitude"], self.df["latitude"])
            self.df = gpd.GeoDataFrame(self.df, geometry=geom)

        # 4) Compute earliest listed_date
        if "listed_date" in self.df and not self.df["listed_date"].isna().all():
            self.earliest_date = self.df["listed_date"].min().to_pydatetime()
        else:
            self.earliest_date = date.today()

        # 5) Compute last_updated
        self.last_updated = get_latest_date_processed(DB_PATH, table_name=safe_table)

        # 6) store page_type for return_geojson
        self.page_type = page_type

        # Turn None/NaN subtypes into "Unknown" so they show up in the checklist
        if 'subtype' in self.df.columns:
            self.df['subtype'] = (
                self.df['subtype']
                  .fillna('Unknown')                              # NaN → "Unknown"
                  .replace({None: 'Unknown', 'None': 'Unknown'})  # None or "None" → "Unknown"
                  .astype(str)                                    # Ensure all entries are strings
                  .apply(unescape)                                # "&amp;" → "&"
            )

        # Do the same for Furnished
        if 'furnished' in self.df.columns:
            self.df['furnished'] = (
                self.df['furnished']
                  .fillna('Unknown')
                  .replace({None: 'Unknown', 'None': 'Unknown'})
            )

        # Turn None/NaN laundry_category into "Unknown"
        if 'laundry_category' in self.df.columns:
            self.df['laundry_category'] = self.df['laundry_category'].fillna('Unknown').replace({None: 'Unknown', 'None': 'Unknown'})

    def return_geojson(self) -> dict:
        """
        Return a GeoJSON FeatureCollection for the current GeoDataFrame.
        Convert datetime-like columns to ISO strings.
        """
        gdf = self.df.copy()

        if "listed_date" in gdf.columns and pd.api.types.is_datetime64_any_dtype(gdf["listed_date"]):
            gdf["listed_date"] = (
                gdf["listed_date"]
                .dt.strftime("%Y-%m-%dT%H:%M:%S")
                .fillna("")
            )

        # Round coordinates to 6 decimals (~10cm precision, plenty for map markers)
        if "latitude" in gdf.columns:
            gdf["latitude"] = gdf["latitude"].round(6)
        if "longitude" in gdf.columns:
            gdf["longitude"] = gdf["longitude"].round(6)

        # Round currency/price fields to 2 decimals
        for col in ["list_price", "ppsqft", "security_deposit", "pet_deposit", 
                    "key_deposit", "other_deposit", "hoa_fee", "space_rent"]:
            if col in gdf.columns:
                gdf[col] = gdf[col].round(2)
        
        if {"best_dn", "best_up"}.issubset(gdf.columns):
            gdf[["best_dn", "best_up"]] = gdf[["best_dn", "best_up"]].replace({np.nan: None})

        geojson_str = gdf.to_json(drop_id=True)
        return json.loads(geojson_str)

    def _attach_isp_speeds(self, conn: sqlite3.Connection, table_name: str) -> None:
        if table_name not in {"lease", "buy"}:
            return

        safe_table = _require_safe_identifier(table_name, field_name="table_name")
        provider_table = {
            "lease": "lease_provider_options",
            "buy": "buy_provider_options",
        }.get(safe_table)
        if not provider_table:
            return
        provider_table = _require_safe_identifier(
            provider_table,
            field_name="provider_table",
        )
        try:
            speed_df = pd.read_sql_query(
                f"""
                SELECT
                    listing_id AS mls_number,
                    MAX(MaxAdDn) AS best_dn,
                    MAX(MaxAdUp) AS best_up
                FROM {provider_table}
                GROUP BY listing_id
                """,
                conn,
            )
        except sqlite3.Error as exc:
            logger.warning("Failed to load ISP speeds from %s: %s", provider_table, exc)
            self.df["best_dn"] = np.nan
            self.df["best_up"] = np.nan
            return

        if speed_df.empty:
            self.df["best_dn"] = np.nan
            self.df["best_up"] = np.nan
            return

        self.df = self.df.merge(speed_df, on="mls_number", how="left")

    def _safe_speed_max(self, column: str) -> float:
        if column not in self.df.columns:
            return DEFAULT_SPEED_MAX

        max_value = pd.to_numeric(self.df[column], errors="coerce").max()
        if not np.isfinite(max_value) or max_value <= 0:
            return DEFAULT_SPEED_MAX
        return float(max_value)

    def create_isp_speed_components(self):
        max_download = self._safe_speed_max("best_dn")
        max_upload = self._safe_speed_max("best_up")
        return html.Div(
            [
                html.Div(
                    [
                        html.H6("Download Speed (Mbps)", style={"marginBottom": "5px"}),
                        dcc.RangeSlider(
                            min=0,
                            max=max_download,
                            value=[0, max_download],
                            id="isp_download_speed_slider",
                            updatemode="mouseup",
                            tooltip={
                                "placement": "bottom",
                                "always_visible": True,
                                "transform": "formatIspSpeed",
                            },
                        ),
                    ],
                    style={"marginBottom": "15px"},
                ),
                html.Div(
                    [
                        html.H6("Upload Speed (Mbps)", style={"marginBottom": "5px"}),
                        dcc.RangeSlider(
                            min=0,
                            max=max_upload,
                            value=[0, max_upload],
                            id="isp_upload_speed_slider",
                            updatemode="mouseup",
                            tooltip={
                                "placement": "bottom",
                                "always_visible": True,
                                "transform": "formatIspSpeed",
                            },
                        ),
                    ],
                ),
                dmc.Switch(
                    id="isp_speed_missing_switch",
                    label="Include properties with an unknown ISP speed",
                    checked=True,
                    size="md",
                    color="teal",
                    style={"marginTop": "15px"},
                ),
            ],
            id="isp_speed_div",
        )

    def create_location_filter_components(self) -> html.Div:
        return html.Div(
            [
                dcc.Input(
                    id=f"{self.page_type}-location-input",
                    type="text",
                    debounce=True,
                    placeholder="Neighborhood or ZIP code (e.g., Highland Park or 90042)",
                    className="form-control",
                    style={
                        "color": "white",
                        "backgroundColor": "#1b1f24",
                        "borderColor": "#495057",
                    },
                ),
                html.Div(
                    id=f"{self.page_type}-location-status",
                    style={
                        "marginTop": "6px",
                        "fontSize": "0.85rem",
                        "color": "#9aa0a6",
                    },
                ),
                dmc.Switch(
                    id=f"{self.page_type}-nearby-zip-switch",
                    label="Include nearby ZIP codes",
                    checked=False,
                    size="sm",
                    color="teal",
                    style={"marginTop": "8px"},
                ),
            ],
            style={"marginBottom": "10px"},
        )

    def create_title_card(self, title, subtitle):
        title_card_children = [
            dbc.Row(
                [
                    dbc.Col(html.H3(title, className="card-title"), width="auto"),
                    dbc.Col(
                        dbc.ButtonGroup(
                            [
                                dbc.Button(
                                    [html.I(className="fa fa-building", style={"marginRight": "5px"}), "For Rent"],
                                    href="/",
                                    color="primary"
                                ),
                                html.Div(style={"width": "1px", "backgroundColor": "#ccc", "margin": "0 1px", "height": "100%"}),  # Vertical Divider
                                dbc.Button(
                                    [html.I(className="fa fa-home", style={"marginRight": "5px"}), "For Sale"],
                                    href="/buy",
                                    color="primary"
                                ),
                            ],
                            className="ml-auto",
                        ),
                        width="auto",
                        className="ml-auto",
                    ),
                ],
                align="center",
            ),
            html.P(subtitle),
            html.P(f"Last updated: {self.last_updated}", style={'marginBottom': '5px'}),
            html.I(
                className="bi bi-github",
                style={"marginRight": "5px"},
            ),
            html.A("GitHub", href='https://github.com/perfectly-preserved-pie/larentals', target='_blank'),
            html.I(
                className="fa-solid fa-blog",
                style={"marginRight": "5px", "marginLeft": "15px"},
            ),
            html.A("About This Project", href='https://automateordie.io/blog/2023/08/26/wheretolivela/', target='_blank'),
            html.I(
                className="fa fa-envelope",
                style={"marginRight": "5px", "marginLeft": "15px"},
            ),
            html.A("hey@wheretolive.la", href='mailto:hey@wheretolive.la', target='_blank'),
        ]

        title_card = dbc.Card(title_card_children, body=True)
        return title_card

# Create a class to hold all of the Dash components for the Lease page
class LeaseComponents(BaseClass):
    # Class Variables
    subtype_meaning = {
        'Apartment (Attached)': 'Apartment (Attached)',
        'Apartment (Detached)': 'Apartment (Detached)',
        'Apartment': 'Apartment',
        'Cabin (Detached)': 'Cabin (Detached)',
        'Commercial Residential (Attached)': 'Commercial Residential (Attached)',
        'Condominium (Attached)': 'Condominium (Attached)',
        'Condominium (Detached)': 'Condominium (Detached)',
        'Condominium': 'Condominium',
        'Duplex (Attached)': 'Duplex (Attached)',
        'Duplex (Detached)': 'Duplex (Detached)',
        'Loft (Attached)': 'Loft (Attached)',
        'Loft': 'Loft',
        'Own Your Own': 'Own Your Own',
        'Quadplex (Attached)': 'Quadplex (Attached)',
        'Quadplex (Detached)': 'Quadplex (Detached)',
        'Residential & Commercial': 'Residential & Commercial',
        'Room For Rent (Attached)': 'Room For Rent (Attached)',
        'Single Family (Attached)': 'Single Family (Attached)',
        'Single Family (Detached)': 'Single Family (Detached)',
        'Single Family': 'Single Family',
        'Stock Cooperative': 'Stock Cooperative',
        'Studio (Attached)': 'Studio (Attached)',
        'Studio (Detached)': 'Studio (Detached)',
        'Townhouse (Attached)': 'Townhouse (Attached)',
        'Townhouse (Detached)': 'Townhouse (Detached)',
        'Townhouse': 'Townhouse',
        'Triplex (Attached)': 'Triplex (Attached)',
        'Triplex (Detached)': 'Triplex (Detached)',
        'Unknown': 'Unknown'
    }

    # List of columns to select from the lease table
    LEASE_COLUMNS: tuple[str, ...] = (
        "mls_number",
        "latitude",
        "longitude",
        "zip_code",
        "subtype",
        "list_price",
        "bedrooms",
        "total_bathrooms",
        "sqft",
        "ppsqft",
        "year_built",
        "parking_spaces",
        "laundry",
        "laundry_category",
        "pet_policy",
        "terms",
        "furnished",
        "phone_number",
        "security_deposit",
        "pet_deposit",
        "key_deposit",
        "other_deposit",
        "full_street_address",
        "listed_date",
        "listing_url",
        "mls_photo",
        "lot_size",
        "senior_community",
        "affected_by_palisades_fire",
        "affected_by_eaton_fire",
    )

    def __init__(self) -> None:
        # Call the parent constructor to load the lease table
        super().__init__(
            table_name="lease",
            page_type="lease",
            select_columns=self.LEASE_COLUMNS,
        )

        # Apply lease-specific transformations to the DataFrame
        if 'laundry' in self.df.columns:
            self.df['laundry'] = self.df['laundry'].apply(self.categorize_laundry_features)

        # 7) Build the UI components
        self.bathrooms_slider            = self.create_bathrooms_slider()
        self.bedrooms_slider             = self.create_bedrooms_slider()
        self.furnished_checklist         = self.create_furnished_checklist()
        self.garage_spaces_components    = self.create_garage_spaces_components()
        self.key_deposit_components      = self.create_key_deposit_components()
        self.laundry_checklist           = self.create_laundry_checklist()
        self.listed_date_components      = self.create_listed_date_components()
        self.location_filter_components  = self.create_location_filter_components()
        self.map                         = self.create_map()
        self.map_card                    = self.create_map_card()
        self.other_deposit_components    = self.create_other_deposit_components()
        self.pet_deposit_components      = self.create_pet_deposit_components()
        self.pets_radio                  = self.create_pets_radio_button()
        self.ppsqft_components           = self.create_ppsqft_components()
        self.rental_price_slider         = self.create_rental_price_slider()
        self.rental_terms_checklist      = self.create_rental_terms_checklist()
        self.security_deposit_components = self.create_security_deposit_components()
        self.square_footage_components   = self.create_sqft_components()
        self.subtype_checklist           = self.create_subtype_checklist()
        self.title_card                  = self.create_title_card()
        self.year_built_components       = self.create_year_built_components()
        self.isp_speed_components        = self.create_isp_speed_components()

        # Dependent components last
        self.user_options_card = self.create_user_options_card()
    
    def categorize_laundry_features(self, feature):
        if pd.isna(feature) or feature in ['Unknown', '']:
            return 'Unknown'
        if any(keyword in feature for keyword in ['In Closet', 'In Kitchen', 'In Garage', 'Inside', 'Individual Room']):
            return 'In Unit'
        elif any(keyword in feature for keyword in ['Community Laundry', 'Common Area', 'Shared']):
            return 'Shared'
        elif any(keyword in feature for keyword in ['Hookup', 'Electric Dryer Hookup', 'Gas Dryer Hookup', 'Washer Hookup']):
            return 'Hookups'
        elif any(keyword in feature for keyword in ['Dryer Included', 'Washer Included']):
            return 'Included Appliances'
        elif any(keyword in feature for keyword in ['Outside', 'Upper Level', 'In Carport']):
            return 'Location Specific'
        else:
            return 'Other'
    
    def create_subtype_checklist(self):
        """
        Creates a Dash MultiSelect of subtypes present in the dataset.
        """
        subtype_series = (
            self.df["subtype"]
            .fillna("Unknown")
            .replace({None: "Unknown", "None": "Unknown"})
            .astype(str)
        )

        unique_subtypes = sorted(set(subtype_series.unique()))
        if "Unknown" not in unique_subtypes:
            unique_subtypes.append("Unknown")
            unique_subtypes = sorted(unique_subtypes)

        data = [{"label": st, "value": st} for st in unique_subtypes]
        initial_values = [item["value"] for item in data]

        return html.Div([
            html.Div([
                dcc.Dropdown(
                    id="subtype_checklist",
                    options=data,
                    value=initial_values,
                    searchable=True,
                    multi=True,
                    placeholder="No options found.",
                    maxHeight=200,
                    clearable=True,
                    style={"marginBottom": "10px"},
                    className="dbc",
                ),
            ],
            id={"type": "dynamic_output_div_lease", "index": "subtype"},
            style={"overflowY": "scroll", "overflowX": "hidden", "maxHeight": "120px"})
        ])
        
    def create_bedrooms_slider(self):
        bedrooms_slider = html.Div([
            html.Div([
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=0,
                    max=self.df['bedrooms'].max(),
                    step=1,
                    value=[0, self.df['bedrooms'].max()],
                    id='bedrooms_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'bedrooms'},
            ),
        ],
        id='bedrooms_div'
        )

        return bedrooms_slider

    def create_bathrooms_slider(self):
        bathrooms_slider = html.Div([
            html.Div([
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=0,
                    max=self.df['total_bathrooms'].max(),
                    step=1,
                    value=[0, self.df['total_bathrooms'].max()],
                    id='bathrooms_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'bathrooms'},
            ),
        ],
        id='bathrooms_div'
        )

        return bathrooms_slider

    def create_sqft_components(self):
        square_footage_components = html.Div([
            html.Div([
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['sqft'].min(),
                    max=self.df['sqft'].max(),
                    value=[self.df['sqft'].min(), self.df['sqft'].max()],
                    id='sqft_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatSqFt"
                    },
                ),
                dmc.Switch(
                    id='sqft_missing_switch',
                    label="Include properties with an unknown square footage",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '15px'},
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'sqft'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='square_footage_div'
        )

        return square_footage_components

    def create_ppsqft_components(self):
        ppsqft_components = html.Div([
            html.Div([
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['ppsqft'].min(),
                    max=self.df['ppsqft'].max(),
                    value=[self.df['ppsqft'].min(), self.df['ppsqft'].max()],
                    id='ppsqft_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatCurrency"
                    },
                ),
                dmc.Switch(
                    id='ppsqft_missing_switch',
                    label="Include properties with an unknown price per square foot",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'ppsqft'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='ppsqft_div'
        )

        return ppsqft_components

    
    def create_pets_radio_button(self):
        pets_radio = html.Div([
            html.Div([
                dcc.RadioItems(
                    id='pets_radio',
                    options=[
                        {'label': 'Pets Allowed', 'value': True},
                        {'label': 'Pets NOT Allowed', 'value': False},
                        {'label': 'Both', 'value': 'Both'}
                    ],
                    value='Both',
                    inputStyle={
                        "marginRight": "4px",
                        "marginLeft": "0px"
                    },
                    className="d-flex flex-wrap align-items-center gap-3 mb-1",
                    inline=True
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'pets'}
            ),
        ],
        id='pet_policy_div'
        )

        return pets_radio

    def create_rental_terms_checklist(self):
        # Add 'Unknown' to categories if necessary
        if pd.api.types.is_categorical_dtype(self.df['terms']):
            if 'Unknown' not in self.df['terms'].cat.categories:
                self.df['terms'] = self.df['terms'].cat.add_categories('Unknown')

        # Fill NaN values with 'Unknown'
        terms_series = self.df['terms'].fillna('Unknown')

        # Split terms and flatten the list
        unique_terms = pd.Series([
            term.strip()
            for sublist in terms_series.str.split(',')
            if sublist
            for term in sublist
            if term and term.strip()
        ]).unique()

        unique_terms = sorted(unique_terms)

        # Define term abbreviations and labels
        term_abbreviations = {
            '12M': '12 Months',
            '24M': '24 Months',
            '6M': '6 Months',
            'DL': 'Day-to-Day',
            'DR': 'Deposit Required',
            'MO': 'Month-to-Month',
            'NG': 'Negotiable',
            'Other': 'Other',
            'RO': 'Renewal Options',
            'SN': 'Seasonal',
            'STL': 'Short Term Lease',
            'Unknown': 'Unknown',
            'VR': 'Vacation Rental',
            'WK': 'Week-to-Week',
        }

        terms = {k: term_abbreviations.get(k, k) for k in unique_terms}

        # Create the Dash component as a chip-based multi-select
        rental_terms_checklist = html.Div(
            dmc.ChipGroup(
                id='terms_checklist',
                multiple=True,
                value=list(unique_terms),
                children=[
                    dmc.Chip(
                        children=f"{terms[term]} ({term})",
                        value=term,
                        radius="sm",
                    )
                    for term in unique_terms
                ],
            ),
            id={'type': 'dynamic_output_div_lease', 'index': 'rental_terms'},
            className="d-flex flex-wrap gap-2",
        )

        return html.Div(
            [
                rental_terms_checklist,
                dmc.Switch(
                    id="terms_missing_switch",
                    label="Include properties with an unknown rental term",
                    checked=True,
                    size="md",
                    color="teal",
                    style={"marginTop": "10px"},
                ),
            ],
            id="rental_terms_wrapper",
            style={"marginBottom": "10px"},
        )

    def create_garage_spaces_components(self):
        garage_spaces_components = html.Div([
            html.Div([
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=0, 
                    max=self.df['parking_spaces'].max(),
                    value=[0, self.df['parking_spaces'].max()], 
                    id='garage_spaces_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
                dmc.Switch(
                    id='garage_missing_switch',
                    label="Include properties with an unknown number of garage spaces",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'garage_spaces'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='garage_spaces_div'
        )

        return garage_spaces_components

    def create_rental_price_slider(self):
        rental_price_components = html.Div([
            html.Div([
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['list_price'].min(),
                    max=self.df['list_price'].max(),
                    value=[0, self.df['list_price'].max()],
                    id='rental_price_slider',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatCurrency"
                    },
                    updatemode='mouseup'
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'rental_price'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='rental_price_div'
        )

        return rental_price_components

    def create_year_built_components(self):
        min_year = int(self.df['year_built'].min())
        max_year = int(self.df['year_built'].max())
        marks_range = np.linspace(min_year, max_year, 5, dtype=int)  # 5 equally spaced marks

        year_built_components = html.Div([
            html.Div([
                dcc.RangeSlider(
                    min=min_year,
                    max=max_year,
                    value=[0, max_year],
                    id='yrbuilt_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                    #marks={str(year): str(year) for year in marks_range}
                    marks={int(year): str(int(year)) for year in marks_range},
                ),
                dmc.Switch(
                    id='yrbuilt_missing_switch',
                    label="Include properties with an unknown year built",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'year_built'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='year_built_div'
        )

        return year_built_components

    def create_furnished_checklist(self) -> html.Div:
        """
        Create a checklist-style ChipGroup for furnished status filtering.

        Returns:
            html.Div: A Dash component containing a multi-select ChipGroup.
        """
        furnished_options: List[str] = [
            "Furnished Or Unfurnished",
            "Furnished",
            "Negotiable",
            "Partially",
            "Unfurnished",
            "Unknown",
        ]

        return html.Div(
            dmc.ChipGroup(
                id="furnished_checklist",
                multiple=True,               
                value=furnished_options,  # all selected by default
                children=[
                    dmc.Chip(
                        children=label,
                        value=label,
                        radius="sm",
                    )
                    for label in furnished_options
                ],
            ),
            id="furnished_div",
            className="d-flex flex-wrap gap-2",
        )

    def create_security_deposit_components(self):
        security_deposit_components = html.Div([
            html.Div([
                html.H5("Security Deposit", style={'display': 'inline-block', 'marginRight': '10px'}),
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['security_deposit'].min(),
                    max=self.df['security_deposit'].max(),
                    value=[self.df['security_deposit'].min(), self.df['security_deposit'].max()],
                    id='security_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatCurrency"
                    },
                ),
                dmc.Switch(
                    id='security_deposit_missing_switch',
                    label="Include properties with an unknown security deposit",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'security_deposit'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='security_deposit_div'
        )

        return security_deposit_components

    def create_other_deposit_components(self):
        other_deposit_components = html.Div([
            html.Div([
                html.H5("Other Deposit", style={'display': 'inline-block', 'marginRight': '10px'}),
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['other_deposit'].min(),
                    max=self.df['other_deposit'].max(),
                    value=[self.df['other_deposit'].min(), self.df['other_deposit'].max()],
                    id='other_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatCurrency"
                    },
                ),
                dmc.Switch(
                    id='other_deposit_missing_switch',
                    label="Include properties with an unknown misc/other deposit",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'other_deposit'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='other_deposit_div'
        )

        return other_deposit_components

    def create_pet_deposit_components(self):
        pet_deposit_components = html.Div([
            html.Div([
                html.H5("Pet Deposit", style={'display': 'inline-block', 'marginRight': '10px'}),
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['pet_deposit'].min(),
                    max=self.df['pet_deposit'].max(),
                    value=[self.df['pet_deposit'].min(), self.df['pet_deposit'].max()],
                    id='pet_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatCurrency"
                    },
                ),
                dmc.Switch(
                    id='pet_deposit_missing_switch',
                    label="Include properties with an unknown pet deposit",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'pet_deposit'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='pet_deposit_div'
        )

        return pet_deposit_components

    def create_key_deposit_components(self):
        key_deposit_components = html.Div([
            html.Div([
                html.H5("Key Deposit", style={'display': 'inline-block', 'marginRight': '10px'}),
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['key_deposit'].min(),
                    max=self.df['key_deposit'].max(),
                    value=[self.df['key_deposit'].min(), self.df['key_deposit'].max()],
                    id='key_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatCurrency"
                    },
                ),
                dmc.Switch(
                    id='key_deposit_missing_switch',
                    label="Include properties with an unknown key deposit",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'key_deposit'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='key_deposit_div'
        )

        return key_deposit_components

    def create_key_deposit_components(self):
        key_deposit_components = html.Div([
            html.Div([
                html.H5("Key Deposit", style={'display': 'inline-block', 'marginRight': '10px'}),
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['key_deposit'].min(),
                    max=self.df['key_deposit'].max(),
                    value=[self.df['key_deposit'].min(), self.df['key_deposit'].max()],
                    id='key_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatCurrency"
                    },
                ),
                dmc.Switch(
                    id='key_deposit_missing_switch',
                    label="Include properties with an unknown key deposit",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'key_deposit'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='key_deposit_div'
        )

        return key_deposit_components

    def create_laundry_checklist(self):
        # Replace NaN values with 'Unknown' before sorting
        laundry_series = self.df['laundry'].fillna('Unknown')
        # Get unique laundry categories sorted alphabetically
        unique_categories = sorted(laundry_series.unique())

        # Use chip group for multi-select laundry categories
        laundry_options = list(unique_categories)

        laundry_checklist = html.Div(
            dmc.ChipGroup(
                id='laundry_checklist',
                multiple=True,
                value=laundry_options,
                children=[
                    dmc.Chip(
                        children=category,
                        value=category,
                        radius="sm",
                    )
                    for category in laundry_options
                ],
            ),
            id={'type': 'dynamic_output_div_lease', 'index': 'laundry'},
            className="d-flex flex-wrap gap-2",
        )

        return laundry_checklist
    
    def create_listed_date_components(self):
        # Get today's date and set it as the end date for the date picker
        today = date.today()
        
        listed_date_components = html.Div([
            # Top header: Listed Date Range with toggle button
            html.Div([
            ]),
            # Main content for listed date: radio buttons then DatePicker and alert
            html.Div([
                # Radio buttons placed before the date picker
                html.Div([
                    html.H6(html.Em("I want to see listings posted in the last..."), 
                            style={'marginBottom': '5px'}),
                    dcc.RadioItems(
                        id='listed_time_range_radio',
                        options=[
                            {'label': '2 Weeks', 'value': 14},
                            {'label': '1 Month', 'value': 30},
                            {'label': '3 Months', 'value': 90},
                            {'label': 'All Time', 'value': 0}
                        ],
                        value=0,
                        inline=True,
                        labelStyle={'fontSize': '0.8rem', 'marginRight': '10px'}
                    )
                ], style={'marginBottom': '5px'}),
                # DatePicker component
                dcc.DatePickerRange(
                    id='listed_date_datepicker_lease',
                    max_date_allowed=today,
                    start_date=self.earliest_date,
                    end_date=today,
                    initial_visible_month=today,
                    className="dbc"
                ),
                # Alert about missing listed dates
                dmc.Switch(
                    id='listed_date_missing_switch',
                    label="Include properties with an unknown listed date",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ], id={'type': 'dynamic_output_div_lease', 'index': 'listed_date'})
        ], style={'marginBottom': '10px'}, id='listed_date_div_lease')
        
        return listed_date_components
    
    def create_map(self):
        """
        Creates a Dash Leaflet map with multiple layers.

        Returns:
            dl.Map: A Dash Leaflet Map component.
        """
        # Create additional layers
        #oil_well_layer = self.create_oil_well_geojson_layer()
        #crime_layer = self.create_crime_layer()
        #farmers_market_layer = LayersClass.create_farmers_markets_layer()

        ns = Namespace("dash_props", "module")

        # Create the main map with the lease layer
        map = dl.Map(
            [
                dl.TileLayer(
                    detectRetina=False,
                ),
                dl.GeoJSON(
                    id='lease_geojson',
                    data=None,
                    cluster=True,
                    clusterToLayer=generate_convex_hulls,
                    onEachFeature=ns("on_each_feature"),
                    zoomToBoundsOnClick=True,
                    superClusterOptions={ # https://github.com/mapbox/supercluster#options
                        'radius': 160,
                        'minZoom': 3,
                    },
                ),
                dl.FullScreenControl()
            ],
            id='map',
            zoom=9,
            minZoom=9,
            center={
                "lat": float(self.df.geometry.y.mean()),
                "lng": float(self.df.geometry.x.mean())
            },      
            preferCanvas=True,
            closePopupOnClick=True,
            style={'width': '100%', 'height': '100vh', 'margin': "0", "display": "block"}
        )

        # Add a layer control for the additional layers
        layers_control = dl.LayersControl(
            [ # Create a list of layers to add to the control
                #dl.Overlay(oil_well_layer, name="Oil & Gas Wells", checked=False),
                #dl.Overlay(crime_layer, name="Crime", checked=False),
                #dl.Overlay(farmers_market_layer, name="Farmers Markets", checked=False),
            ],
            collapsed=True,
            position='topleft'
        )
        map.children.append(layers_control)

        return map
        
    def create_user_options_card(self):
        accordion = dbc.Accordion(
            [
                dbc.AccordionItem(self.listed_date_components, title="Listed Date", item_id="listed_date"),
                dbc.AccordionItem(self.location_filter_components, title="Location", item_id="location"),
                dbc.AccordionItem(self.subtype_checklist, title="Subtypes", item_id="subtypes"),
                dbc.AccordionItem(self.rental_price_slider, title="Monthly Rent", item_id="monthly_rent"),
                dbc.AccordionItem(self.bedrooms_slider, title="Bedrooms", item_id="bedrooms"),
                dbc.AccordionItem(self.bathrooms_slider, title="Bathrooms", item_id="bathrooms"),
                dbc.AccordionItem(self.pets_radio, title="Pet Policy", item_id="pet_policy"),
                dbc.AccordionItem(
                    [
                        self.key_deposit_components,
                        self.other_deposit_components,
                        self.pet_deposit_components,
                        self.security_deposit_components,
                    ],
                    title="Deposits",
                    item_id="deposits",
                ),
                dbc.AccordionItem(self.furnished_checklist, title="Furnished", item_id="furnished"),
                dbc.AccordionItem(self.garage_spaces_components, title="Parking Spaces", item_id="parking_spaces"),
                dbc.AccordionItem(self.isp_speed_components, title="Internet Service Provider (ISP) Speed", item_id="isp_speed"),
                dbc.AccordionItem(self.laundry_checklist, title="Laundry", item_id="laundry"),
                dbc.AccordionItem(self.ppsqft_components, title="Price Per Sqft", item_id="ppsqft"),
                dbc.AccordionItem(self.rental_terms_checklist, title="Rental Terms", item_id="rental_terms"),
                dbc.AccordionItem(self.square_footage_components, title="Square Footage", item_id="square_footage"),
                dbc.AccordionItem(self.year_built_components, title="Year Built", item_id="year_built"),
            ],
            flush=True,
            always_open=True,
            active_item=[
                "listed_date",
                "location",
                "subtypes",
                "monthly_rent",
                "bedrooms",
                "bathrooms",
                "pet_policy",
            ],
            className="options-accordion",
        )

        user_options_card = dbc.Card(
            [
                html.P(
                    "Use the options below to filter the map "
                    "according to your needs.",
                    className="card-text",
                ),
                accordion,
            ],
            body=True
        )
        return user_options_card
    
    def create_map_card(self):
        return dbc.Card(
            dbc.CardBody(
                html.Div(
                    [
                        # Spinner overlay (toggled via callback)
                        html.Div(
                            id=f"{self.page_type}-map-spinner",
                            children=[
                                dbc.Spinner(size="lg"),
                                html.P("Loading properties...", style={"marginTop": "10px", "marginLeft": "5px" ,"color": "white"})
                            ],
                            style={
                                "position": "relative",
                                "inset": "0",
                                "display": "flex",
                                "alignItems": "center",
                                "justifyContent": "center",
                                "backgroundColor": "rgba(0, 0, 0, 0.25)",
                                "zIndex": "10000",
                            },
                        ),
                        # Map itself
                        html.Div(self.map, style={"position": "relative", "zIndex": "0"}),
                    ],
                    style={"position": "relative"},
                ),
                className="p-2 g-0",
            ),
            className="d-block d-md-block sticky-top",
        )
    
    def create_title_card(self):
        return super().create_title_card(
            title="WhereToLive.LA",
            subtitle="An interactive map of available rentals in Los Angeles County. Updated weekly."
        )

# Create a class to hold all the components for the buy page
class BuyComponents(BaseClass):
    BUY_COLUMNS: tuple[str, ...] = (
        # identity + geometry
        "mls_number",
        "latitude",
        "longitude",
        "zip_code",

        # core property details (filters + popup)
        "subtype",
        "list_price",
        "bedrooms",
        "total_bathrooms",
        "sqft",
        "ppsqft",
        "year_built",
        "lot_size",
        "garage_spaces",

        # HOA / park / restrictions
        "hoa_fee",
        "hoa_fee_frequency",

        # address + listing metadata
        "full_street_address",
        "listed_date",
        "listing_url",
        "mls_photo",

        # environmental flags
        "affected_by_palisades_fire",
        "affected_by_eaton_fire",
    )

    def __init__(self):
        # Call the parent constructor to load the buy table
        super().__init__(
            table_name="buy",
            page_type="buy",
            select_columns=self.BUY_COLUMNS,
        )
        # Now build the UI components
        self.bathrooms_slider         = self.create_bathrooms_slider()
        self.bedrooms_slider          = self.create_bedrooms_slider()
        self.hoa_fee_components       = self.create_hoa_fee_components()
        self.hoa_fee_frequency_checklist = self.create_hoa_fee_frequency_checklist()
        self.list_price_slider        = self.create_list_price_slider()
        self.listed_date_components   = self.create_listed_date_components()
        self.location_filter_components  = self.create_location_filter_components()
        self.map                      = self.create_map()
        self.map_card                 = self.create_map_card()
        self.ppsqft_components        = self.create_ppsqft_components()
        self.lot_size_components      = self.create_lot_size_components()
        self.sqft_components          = self.create_sqft_components()
        self.subtype_checklist        = self.create_subtype_checklist()
        self.title_card               = self.create_title_card()
        self.year_built_components    = self.create_year_built_components()
        self.isp_speed_components     = self.create_isp_speed_components()

        # 7) Dependent components
        self.user_options_card = self.create_user_options_card()
    
    # Create a checklist for the user to select the subtypes they want to see
    def create_subtype_checklist(self):
        # Get unique subtypes from the dataframe
        unique_subtypes = self.df['subtype'].unique()
        # Replace NAs with 'Unknown'
        cleaned_subtypes = [st if pd.notna(st) else 'Unknown' for st in unique_subtypes]
        # Create data list for MultiSelect
        data = [{'label': st, 'value': st} for st in sorted(cleaned_subtypes)]

        subtype_checklist = html.Div([ 
            # Title and toggle button
            html.Div([
            ]),

            # The actual checklist
            html.Div([
                dmc.MultiSelect(
                id='subtype_checklist',
                data=data,
                value=[item['value'] for item in data],
                searchable=True,
                nothingFoundMessage="No options found",
                clearable=True,
                style={"marginBottom": "10px"},
            ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'subtype'},
            ),
        ],
        id='subtypes_div_buy'
        )

        return subtype_checklist

    def create_bedrooms_slider(self):
        bedrooms_slider = html.Div([
            
            # Title and toggle button
            html.Div([
            ]),
            
            # The actual range slider
            html.Div([
                dcc.RangeSlider(
                    min=0, 
                    max=self.df['bedrooms'].max(), # Dynamically calculate the maximum number of bedrooms
                    step=1, 
                    value=[0, self.df['bedrooms'].max()], 
                    id='bedrooms_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'bedrooms'},
            ),
        ],
        id='bedrooms_div_buy'
        )
        
        return bedrooms_slider

    def create_bathrooms_slider(self):
        bathrooms_slider = html.Div([
            
            # Title and toggle button
            html.Div([
            ]),
            
            # The actual range slider
            html.Div([
                dcc.RangeSlider(
                    min=0, 
                    max=self.df['total_bathrooms'].max(), 
                    step=1, 
                    value=[0, self.df['total_bathrooms'].max()], 
                    id='bathrooms_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'bathrooms'},
            ),
        ],
        id='bathrooms_div_buy'
        )
        
        return bathrooms_slider
    
    def create_sqft_components(self):
        square_footage_components = html.Div([
            html.Div([
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['sqft'].min(),
                    max=self.df['sqft'].max(),
                    value=[self.df['sqft'].min(), self.df['sqft'].max()],
                    id='sqft_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatSqFt"
                    },
                ),
                dmc.Switch(
                    id='sqft_missing_switch',
                    label="Include properties with an unknown square footage",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'}
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'sqft'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='square_footage_div'
        )

        return square_footage_components

    def create_ppsqft_components(self):
        ppsqft_components = html.Div([
            html.Div([
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['ppsqft'].min(),
                    max=self.df['ppsqft'].max(),
                    value=[self.df['ppsqft'].min(), self.df['ppsqft'].max()],
                    id='ppsqft_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatCurrency"
                    },
                ),
                dmc.Switch(
                    id='ppsqft_missing_switch',
                    label="Include properties with an unknown price per square foot",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'ppsqft'}
            ),
        ],
        style={
            'marginBottom': '10px',
        },
        id='ppsqft_div'
        )

        return ppsqft_components

    def create_lot_size_components(self):
        lot_sizes = self.df["lot_size"]
        has_values = lot_sizes.notna().any()

        lot_min = float(np.nanmin(lot_sizes)) if has_values else 0.0
        lot_max = float(np.nanmax(lot_sizes)) if has_values else 1.0

        if not np.isfinite(lot_min):
            lot_min = 0.0
        if not np.isfinite(lot_max) or lot_max < lot_min:
            lot_max = max(lot_min, 1.0)

        lot_size_components = html.Div([
            html.Div([
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=lot_min,
                    max=lot_max,
                    value=[lot_min, lot_max],
                    id="lot_size_slider",
                    updatemode="mouseup",
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatSqFt"
                    },
                ),
                dmc.Switch(
                    id="lot_size_missing_switch",
                    label="Include properties with an unknown lot size",
                    checked=True,
                    size="md",
                    color="teal",
                    style={"marginTop": "10px"},
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'lot_size'}
            ),
        ],
        style={
            "marginBottom": "10px",
        },
        id="lot_size_div_buy"
        )

        return lot_size_components
    
    def create_hoa_fee_components(self):
        # Calculate the number of steps
        num_steps = 5
        step_value = (self.df['hoa_fee'].max() - self.df['hoa_fee'].min()) / num_steps
        # Make sure the step value is a round number for better slider usability
        step_value = np.round(step_value, -int(np.floor(np.log10(step_value))))

        hoa_fee_components = html.Div([
            # Title, subheading, and toggle button
            html.Div([
                html.H6([html.Em("Applies only to SFR and CONDO/TWNHS.")], style={'display': 'inline-block', 'marginRight': '10px'}),
            ]),
            # The actual RangeSlider and RadioItems
            html.Div([
                dcc.RangeSlider(
                    id='hoa_fee_slider',
                    min=self.df['hoa_fee'].min(),
                    max=self.df['hoa_fee'].max(),
                    value=[self.df['hoa_fee'].min(), self.df['hoa_fee'].max()],
                    step=step_value,
                    tooltip={
                        'always_visible': True,
                        'placement': 'bottom',
                        'transform': 'formatCurrency'
                        },
                ),
                dmc.Switch(
                    id='hoa_fee_missing_switch',
                    label="Include properties with an unknown HOA fee",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'hoa_fee'},
            ),
            
        ],
        style={
            'marginBottom': '10px',
        },
        id='hoa_fee_div_buy'
        )

        return hoa_fee_components

    def create_hoa_fee_frequency_checklist(self):
        hoa_fee_frequency_checklist = html.Div(
            dmc.ChipGroup(
                id='hoa_fee_frequency_checklist',
                multiple=True,
                value=['N/A', 'Monthly'],
                children=[
                    dmc.Chip(children='N/A', value='N/A', radius="sm"),
                    dmc.Chip(children='Monthly', value='Monthly', radius="sm"),
                ],
            ),
            id={'type': 'dynamic_output_div_buy', 'index': 'hoa_fee_frequency'},
            className="d-flex flex-wrap gap-2",
        )

        return hoa_fee_frequency_checklist

    def create_list_price_slider(self):
        list_price_slider = html.Div([
            
            # Title and toggle button
            html.Div([
            ]),
            
            # The actual RangeSlider
            html.Div([
                dcc.RangeSlider(
                    min=self.df['list_price'].min(),
                    max=self.df['list_price'].max(),
                    value=[0, self.df['list_price'].max()],
                    id='list_price_slider',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True,
                        "transform": "formatCurrency"
                    },
                    updatemode='mouseup'
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'list_price'},
            ),
            
        ],
        style={
            'marginBottom': '10px',
        },
        id='list_price_div_buy'
        )

        return list_price_slider

    def create_year_built_components(self):
        min_year = int(self.df['year_built'].min())
        max_year = int(self.df['year_built'].max())
        marks_range = np.linspace(min_year, max_year, 5, dtype=int)  # 5 equally spaced marks
        year_built_components = html.Div([
            html.Div([
                dcc.RangeSlider(
                    min=min_year,
                    max=max_year,
                    value=[0, max_year],
                    id='yrbuilt_slider',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                    marks={int(year): str(int(year)) for year in marks_range},
                    updatemode='mouseup'
                ),
                dmc.Switch(
                    id='yrbuilt_missing_switch',
                    label="Include properties with an unknown year built",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'year_built'}
            ),
            
        ],
        style={
            'marginBottom': '10px',
        },
        id='yrbuilt_div_buy'
        )

        return year_built_components
    
    def create_listed_date_components(self):
        # Get today's date and set it as the end date for the date picker
        today = date.today()
        
        listed_date_components = html.Div([
            # Top header: Listed Date Range with toggle button
            html.Div([
            ]),
            # Main content for listed date: radio buttons then DatePicker and alert
            html.Div([
                # Radio buttons placed before the date picker
                html.Div([
                    html.H6(html.Em("I want to see listings posted in the last..."), 
                            style={'marginBottom': '5px'}),
                    dcc.RadioItems(
                        id='listed_time_range_radio',
                        options=[
                            {'label': '2 Weeks', 'value': 14},
                            {'label': '1 Month', 'value': 30},
                            {'label': '3 Months', 'value': 90},
                            {'label': 'All Time', 'value': 0}
                        ],
                        value=0,
                        inline=True,
                        labelStyle={'fontSize': '0.8rem', 'marginRight': '10px'}
                    )
                ], style={'marginBottom': '5px'}),
                # DatePicker component
                dcc.DatePickerRange(
                    id='listed_date_datepicker_buy',
                    max_date_allowed=today,
                    start_date=self.earliest_date,
                    end_date=today,
                    initial_visible_month=today,
                ),
                # Alert about missing listed dates
                dmc.Switch(
                    id='listed_date_missing_switch',
                    label="Include properties with an unknown listed date",
                    checked=True,
                    size="md",
                    color="teal",
                    style={'marginTop': '10px'},
                ),
            ], id={'type': 'dynamic_output_div_buy', 'index': 'listed_date'})
        ], style={'marginBottom': '10px'}, id='listed_date_div_buy')
        
        return listed_date_components

    def create_map(self):
        """
        Creates a Dash Leaflet map with multiple layers.

        Returns:
            dl.Map: A Dash Leaflet Map component.
        """
        # Create additional layers
        #oil_well_layer = self.create_oil_well_geojson_layer()
        #crime_layer = self.create_crime_layer()

        ns = Namespace("dash_props", "module")

        # Create the main map with the lease layer
        map = dl.Map(
            [
                dl.TileLayer(
                    detectRetina=False,
                ),
                dl.GeoJSON(
                    id='buy_geojson',
                    data=None,
                    cluster=True,
                    clusterToLayer=generate_convex_hulls,
                    onEachFeature=ns("on_each_feature"),
                    zoomToBoundsOnClick=True,
                    superClusterOptions={ # https://github.com/mapbox/supercluster#options
                        'radius': 160,
                        'minZoom': 3,
                    },
                ),
                dl.FullScreenControl()
            ],
            id='map',
            zoom=9,
            minZoom=9,
            center={
                "lat": float(self.df.geometry.y.mean()),
                "lng": float(self.df.geometry.x.mean())
            },
            preferCanvas=True,
            closePopupOnClick=True,
            style={'width': '100%', 'height': '90vh', 'margin': "auto", "display": "inline-block"}
        )

        # Add a layer control for the additional layers
        #layers_control = dl.LayersControl(
        #    [ # Create a list of layers to add to the control
        #        dl.Overlay(oil_well_layer, name="Oil & Gas Wells", checked=False),
        #        dl.Overlay(crime_layer, name="Crime", checked=False),
        #    ],
        #    collapsed=True,
        #    position='topleft'
        #)
        #map.children.append(layers_control)

        return map
    
    def create_user_options_card(self):
        accordion = dbc.Accordion(
            [
                dbc.AccordionItem(self.listed_date_components, title="Listed Date", item_id="listed_date"),
                dbc.AccordionItem(self.location_filter_components, title="Location", item_id="location"),
                dbc.AccordionItem(self.subtype_checklist, title="Subtypes", item_id="subtypes"),
                dbc.AccordionItem(self.list_price_slider, title="List Price", item_id="list_price"),
                dbc.AccordionItem(self.bedrooms_slider, title="Bedrooms", item_id="bedrooms"),
                dbc.AccordionItem(self.bathrooms_slider, title="Bathrooms", item_id="bathrooms"),
                dbc.AccordionItem(self.hoa_fee_components, title="HOA Fees", item_id="hoa_fees"),
                dbc.AccordionItem(self.hoa_fee_frequency_checklist, title="HOA Fee Frequency", item_id="hoa_fee_frequency"),
                dbc.AccordionItem(self.isp_speed_components, title="Internet Service Provider (ISP) Speed", item_id="isp_speed"),
                dbc.AccordionItem(self.lot_size_components, title="Lot Size", item_id="lot_size"),
                dbc.AccordionItem(self.ppsqft_components, title="Price Per Sqft", item_id="ppsqft"),
                dbc.AccordionItem(self.sqft_components, title="Square Footage", item_id="square_footage"),
                dbc.AccordionItem(self.year_built_components, title="Year Built", item_id="year_built"),
            ],
            flush=True,
            always_open=True,
            active_item=[
                "listed_date",
                "location",
                "subtypes",
                "list_price",
                "bedrooms",
                "bathrooms",
            ],
            className="options-accordion",
        )

        user_options_card = dbc.Card(
            [
                html.P(
                    "Use the options below to filter the map "
                    "according to your needs.",
                    className="card-text",
                ),
                accordion,
            ],
            body=True
        )
        return user_options_card
    
    def create_map_card(self):
        return dbc.Card(
            dbc.CardBody(
                html.Div(
                    [
                        # Spinner overlay (toggled via callback)
                        html.Div(
                            id=f"{self.page_type}-map-spinner",
                            children=[
                                dbc.Spinner(size="lg"),
                                html.P("Loading properties...", style={"marginTop": "10px", "marginLeft": "5px" ,"color": "white"})
                            ],
                            style={
                                "position": "absolute",
                                "inset": "0",
                                "display": "flex",
                                "alignItems": "center",
                                "justifyContent": "center",
                                "backgroundColor": "rgba(0, 0, 0, 0.25)",
                                "zIndex": "10000",
                            },
                        ),
                        # Map itself
                        html.Div(self.map, style={"position": "relative", "zIndex": "0"}),
                    ],
                    style={"position": "relative"},
                )
            ),
            className="d-block d-md-block sticky-top",
        )
    
    def create_title_card(self):
        return super().create_title_card(
            title="WhereToLive.LA",
            subtitle="An interactive map of available residential properties for sale in Los Angeles County. Updated weekly."
        )
