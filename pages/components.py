from dash import html, dcc
from dash_extensions.javascript import Namespace
from datetime import date
from functions.convex_hull import generate_convex_hulls
from functions.layers import LayersClass
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import dash_mantine_components as dmc
import geopandas as gpd
import json
import numpy as np
import pandas as pd

def create_toggle_button(index, page_type, initial_label="Hide"):
    """Creates a toggle button with an initial label."""
    return html.Button(
        id={'type': f'dynamic_toggle_button_{page_type}', 'index': index},
        children=initial_label, 
        style={'display': 'inline-block'}
    )

# Create a class to hold all common components for both Lease and Buy pages
class BaseClass:
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
            html.A("About This Project", href='https://automateordie.io/wheretolivedotla/', target='_blank'),
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

    def __init__(self):
        # Initalize these first because they are used in other components
        self.df = gpd.read_file("assets/datasets/lease.geojson")

        self.df['laundry'] = self.df['laundry'].apply(self.categorize_laundry_features)

        self.bathrooms_slider = self.create_bathrooms_slider()
        self.bedrooms_slider = self.create_bedrooms_slider()
        self.furnished_checklist = self.create_furnished_checklist()
        self.garage_spaces_components = self.create_garage_spaces_components()
        self.key_deposit_components = self.create_key_deposit_components()
        self.last_updated = self.df['date_processed'].max().strftime('%m/%d/%Y')
        self.laundry_checklist = self.create_laundry_checklist()
        self.listed_date_components = self.create_listed_date_components()
        self.map = self.create_map()
        self.map_card = self.create_map_card()
        self.other_deposit_components = self.create_other_deposit_components()
        self.pet_deposit_components = self.create_pet_deposit_components()
        self.pets_radio = self.create_pets_radio_button()
        self.ppsqft_components = self.create_ppsqft_components()
        self.rental_price_slider = self.create_rental_price_slider()
        self.rental_terms_checklist = self.create_rental_terms_checklist()
        self.security_deposit_components = self.create_security_deposit_components()
        self.square_footage_components = self.create_sqft_components()
        self.subtype_checklist = self.create_subtype_checklist()
        self.title_card = self.create_title_card()
        self.year_built_components = self.create_year_built_components()

        # Initialize these last because they depend on other components
        self.more_options = self.create_more_options()
        self.user_options_card = self.create_user_options_card()

    def return_geojson(self):
        """
        Load the GeoJSON data from the file and return it as an object.
        """
        with open("assets/datasets/lease.geojson", "r") as file:
            return json.load(file)
    
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
        Creates a Dash MultiSelect of the flattened subtypes, without grouping.
        """
        flattened_subtypes = [
            'Apartment', 'Cabin', 'Combo - Res & Com', 'Commercial Residential',
            'Condominium', 'Duplex', 'Loft', 'Quadplex', 'Room For Rent',
            'Single Family', 'Stock Cooperative', 'Studio', 'Townhouse',
            'Triplex', 'Unknown'
        ]

        # Create data in the format dmc.MultiSelect expects
        # Each item is { 'label': '...', 'value': '...' }
        data = [{"label": st, "value": st} for st in sorted(flattened_subtypes)]

        # Default to everything selected
        initial_values = [item["value"] for item in data]

        # Custom styles for the MultiSelect
        custom_styles = {
            "dropdown": {"color": "white"},
            "groupLabel": {"color": "#ADD8E6", "fontWeight": "bold"},
            "input": {"color": "white"},
            "label": {"color": "white"},
            "pill": {"color": "white"},
        }

        subtype_checklist = html.Div([
            html.Div([
                html.H5("Subtypes", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='subtype', initial_label="Hide", page_type='lease')
            ]),
            html.Div([
                dmc.MultiSelect(
                    id='subtype_checklist',
                    data=data,
                    value=initial_values,
                    searchable=False,
                    nothingFoundMessage="No options found",
                    clearable=True,
                    style={"marginBottom": "10px"},
                    styles=custom_styles
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'subtype'},
            style={
                "overflowY": "scroll",
                "overflowX": 'hidden',
                "maxHeight": '120px',
            })
        ])

        return subtype_checklist
    
    def create_bedrooms_slider(self):
        bedrooms_slider = html.Div([
            html.Div([
                html.H5("Bedrooms", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='bedrooms', initial_label="Hide", page_type='lease')
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
                html.H5("Bathrooms", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='bathrooms', initial_label="Hide", page_type='lease')
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
                html.H5("Square Footage", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='sqft', initial_label="Hide", page_type='lease')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown square footage?",
                        dcc.RadioItems(
                            id='sqft_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '15px'}
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
                html.H5("Price Per Square Foot ($)", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='ppsqft', initial_label="Hide", page_type='lease')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown price per square foot?",
                        dcc.RadioItems(
                            id='ppsqft_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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
                html.H5("Pet Policy", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='pets', initial_label="Hide", page_type='lease')
            ], style={'display': 'inline-block'}),
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
                        "marginRight": "5px",
                        "marginLeft": "5px"
                    },
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
            term.strip() for sublist in terms_series.str.split(',')
            if sublist for term in sublist
        ]).unique()

        unique_terms = sorted(unique_terms)

        # Define term abbreviations and labels
        term_abbreviations = {
            '12M': '12 Months',
            '24M': '24 Months',
            '6M': '6 Months',
            'DL': 'Day-to-Day',
            'MO': 'Month-to-Month',
            'NG': 'Negotiable',
            'SN': 'Seasonal',
            'STL': 'Short Term Lease',
            'Unknown': 'Unknown',
            'VR': 'Vacation Rental',
            'WK': 'Week-to-Week',
        }

        terms = {k: term_abbreviations.get(k, k) for k in unique_terms}

        # Create the Dash component
        rental_terms_checklist = html.Div([
            html.Div([
                html.H5("Rental Terms", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='rental_terms', initial_label="Hide", page_type='lease')
            ], style={'display': 'inline-block'}),
            html.Div([
                dcc.Checklist(
                    id='terms_checklist',
                    options=[{'label': f"{terms[term]} ({term})", 'value': term} for term in terms],
                    value=unique_terms,  # Select all terms by default
                    inputStyle={"marginRight": "5px", "marginLeft": "5px"},
                    inline=False
                ),
            ],
                id={'type': 'dynamic_output_div_lease', 'index': 'rental_terms'},
            ),
        ],
            id='rental_terms_div'
        )
        return rental_terms_checklist

    def create_garage_spaces_components(self):
        garage_spaces_components = html.Div([
            html.Div([
                html.H5("Parking Spaces", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='garage_spaces', initial_label="Hide", page_type='lease')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown number of garage spaces?",
                        dcc.RadioItems(
                            id='garage_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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
                html.H5("Price (Monthly)", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='rental_price', initial_label="Hide", page_type='lease')
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
                html.H5("Year Built", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='year_built', initial_label="Hide", page_type='lease')
            ], style={'display': 'inline-block'}),
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown year built?",
                        dcc.RadioItems(
                            id='yrbuilt_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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

    def create_furnished_checklist(self):
        furnished_checklist = html.Div([
            html.Div([
                html.H5("Furnished/Unfurnished", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='furnished', initial_label="Hide", page_type='lease')
            ], style={'display': 'inline-block'}),
            html.Div([
                dcc.Checklist(
                    id='furnished_checklist',
                    options=[
                        {'label': 'Furnished Or Unfurnished', 'value': 'Furnished Or Unfurnished'},
                        {'label': 'Furnished', 'value': 'Furnished'},
                        {'label': 'Negotiable', 'value': 'Negotiable'},
                        {'label': 'Partially', 'value': 'Partially'},
                        {'label': 'Unfurnished', 'value': 'Unfurnished'},
                        {'label': 'Unknown', 'value': 'Unknown'},
                    ],
                    value=[
                        'Furnished Or Unfurnished',
                        'Furnished',
                        'Negotiable',
                        'Partially',
                        'Unfurnished',
                        'Unknown',
                    ],
                    labelStyle={'display': 'block'},
                    inputStyle={
                        "marginRight": "5px",
                        "marginLeft": "5px"
                    },
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'furnished'},
            ),
        ],
        id='furnished_div'
        )

        return furnished_checklist

    def create_security_deposit_components(self):
        security_deposit_components = html.Div([
            html.Div([
                html.H5("Security Deposit", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='security_deposit', initial_label="Hide", page_type='lease')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown security deposit?",
                        dcc.RadioItems(
                            id='security_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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
                create_toggle_button(index='other_deposit', initial_label="Hide", page_type='lease')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown misc/other deposit?",
                        dcc.RadioItems(
                            id='other_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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
                create_toggle_button(index='pet_deposit', initial_label="Hide", page_type='lease')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown pet deposit?",
                        dcc.RadioItems(
                            id='pet_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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
                create_toggle_button(index='key_deposit', initial_label="Hide", page_type='lease')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown key deposit?",
                        dcc.RadioItems(
                            id='key_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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
                create_toggle_button(index='key_deposit', initial_label="Hide", page_type='lease')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown key deposit?",
                        dcc.RadioItems(
                            id='key_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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

        # Create options for the checklist
        laundry_options = [
            {'label': category, 'value': category}
            for category in unique_categories
        ]

        laundry_checklist = html.Div([
            html.Div([
                html.H5("Laundry Features", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='laundry', initial_label="Hide", page_type='lease')
            ]),
            html.Div([
                dcc.Checklist(
                    id='laundry_checklist',
                    options=laundry_options,
                    value=[option['value'] for option in laundry_options],
                    labelStyle={'display': 'block'}
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'laundry'}
            ),
        ],
        id='laundry_checklist_div'
        )

        return laundry_checklist
    
    def create_listed_date_components(self):
        # Get today's date and set it as the end date for the date picker
        today = date.today()
        # Get the earliest date and convert it to Pythonic datetime for Dash
        self.df['listed_date'] = pd.to_datetime(self.df['listed_date'], errors='coerce')
        earliest_date = (self.df['listed_date'].min()).to_pydatetime()
        
        listed_date_components = html.Div([
            html.Div([
                html.H5("Listed Date Range", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='listed_date', initial_label="Hide", page_type='lease')
            ]),
            html.Div([
                dcc.DatePickerRange(
                    id='listed_date_datepicker',
                    max_date_allowed=today,
                    start_date=earliest_date,
                    end_date=today
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown listed date?",
                        dcc.RadioItems(
                            id='listed_date_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
                ),
            ],
            id={'type': 'dynamic_output_div_lease', 'index': 'listed_date'}
            ),
        ],
        id='listed_date_div'
        )
        
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
        farmers_market_layer = LayersClass.create_farmers_markets_layer()

        ns = Namespace("dash_props", "module")

        # Create the main map with the lease layer
        map = dl.Map(
            [
                dl.TileLayer(),
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
            center=(self.df['latitude'].mean(), self.df['longitude'].mean()),
            preferCanvas=True,
            closePopupOnClick=True,
            style={'width': '100%', 'height': '90vh', 'margin': "auto", "display": "inline-block"}
        )

        # Add a layer control for the additional layers
        layers_control = dl.LayersControl(
            [ # Create a list of layers to add to the control
                #dl.Overlay(oil_well_layer, name="Oil & Gas Wells", checked=False),
                #dl.Overlay(crime_layer, name="Crime", checked=False),
                dl.Overlay(farmers_market_layer, name="Farmers Markets", checked=False),
            ],
            collapsed=True,
            position='topleft'
        )
        map.children.append(layers_control)

        return map
        
    # Create a button to toggle the collapsed section in the user options card
    # https://dash-bootstrap-components.opensource.faculty.ai/docs/components/collapse/
    def create_more_options(self):
        more_options = dbc.Collapse(
            [
                self.square_footage_components,  
                self.ppsqft_components,
                self.garage_spaces_components,
                self.year_built_components,
                self.rental_terms_checklist,
                self.furnished_checklist,
                self.laundry_checklist,
                self.security_deposit_components,
                self.pet_deposit_components,
                self.key_deposit_components,
                self.other_deposit_components,
            ],
            id='more-options-collapse-lease'
        )

        return more_options

    def create_user_options_card(self):
        user_options_card = dbc.Card(
            [
                html.P(
                    "Use the options below to filter the map "
                    "according to your needs.",
                    className="card-text",
                ),
                self.listed_date_components,
                self.subtype_checklist,
                self.rental_price_slider,
                self.bedrooms_slider,
                self.bathrooms_slider,
                self.pets_radio,
                dbc.Button("More Options", id='more-options-button-lease', className='mt-2'),
                self.more_options,
            ],
            body=True
        )
        return user_options_card
    
    def create_map_card(self):
        map_card = dbc.Card(
            [self.map], 
            body = True,
            # Make the graph stay in view as the page is scrolled down
            # https://getbootstrap.com/docs/4.0/utilities/position/
            # Apply sticky-top class only on non-mobile devices
            className='d-block d-md-block sticky-top'
        )
    
        return map_card
    
    def create_title_card(self):
        return super().create_title_card(
            title="WhereToLive.LA",
            subtitle="An interactive map of available rentals in Los Angeles County. Updated weekly."
        )

# Create a class to hold all the components for the buy page
class BuyComponents(BaseClass):
    def __init__(self):
        # Initalize these first because they are used in other components
        self.df = gpd.read_file("assets/datasets/buy.geojson")

        self.bathrooms_slider = self.create_bathrooms_slider()
        self.bedrooms_slider = self.create_bedrooms_slider()
        self.df['listed_date'] = pd.to_datetime(self.df['listed_date'], errors='coerce')
        self.earliest_date = (self.df['listed_date'].min()).to_pydatetime()
        self.hoa_fee_components = self.create_hoa_fee_components()
        self.hoa_fee_frequency_checklist = self.create_hoa_fee_frequency_checklist()
        self.last_updated = self.df['date_processed'].max().strftime('%m/%d/%Y')
        self.list_price_slider = self.create_list_price_slider()
        self.listed_date_components = self.create_listed_date_components()
        self.map = self.create_map()
        self.map_card = self.create_map_card()
        self.pet_policy_radio_button = self.create_pets_radio_button()
        self.ppsqft_components = self.create_ppsqft_components()
        self.senior_community_components = self.create_senior_community_components()
        self.space_rent_components = self.create_space_rent_components()
        self.sqft_components = self.create_sqft_components()
        self.subtype_checklist = self.create_subtype_checklist()
        self.title_card = self.create_title_card()
        self.year_built_components = self.create_year_built_components()

        # Initialize these last because they depend on other components
        self.more_options = self.create_more_options()
        self.user_options_card = self.create_user_options_card()

    def return_geojson(self):
        """
        Load the GeoJSON data from the file and return it as an object.
        """
        with open("assets/datasets/buy.geojson", "r") as file:
            return json.load(file)
        
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
                html.H5("Subtypes", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='subtype', initial_label="Hide", page_type='buy')
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
                html.H5("bedrooms", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='bedrooms', initial_label="Hide", page_type='buy')
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
                html.H5("Bathrooms", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='bathrooms', initial_label="Hide", page_type='buy')
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
                html.H5("Square Footage", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='sqft', initial_label="Hide", page_type='buy')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown square footage?",
                        dcc.RadioItems(
                            id='sqft_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '15px'}
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
                html.H5("Price Per Square Foot ($)", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='ppsqft', initial_label="Hide", page_type='buy')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown price per square foot?",
                        dcc.RadioItems(
                            id='ppsqft_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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
    
    def create_pets_radio_button(self):
        pets_radio = html.Div([
            
            # Title, subheading, and toggle button
            html.Div([
                html.H5("Pet Policy", style={'display': 'inline-block', 'marginRight': '10px'}),
                html.H6([html.Em("Applies only to Mobile Homes (MH).")], style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='pet_policy', initial_label="Hide", page_type='buy')
            ]),
            
            # The actual RadioItems
            html.Div([
                dcc.RadioItems(
                    id = 'pets_radio',
                    options=[
                        {'label': 'Pets Allowed', 'value': True},
                        {'label': 'Pets NOT Allowed', 'value': False},
                        {'label': 'Both', 'value': 'Both'},
                    ],
                    value='Both', # A value needs to be selected upon page load otherwise we error out.
                    inputStyle = {
                        "marginRight": "5px",
                        "marginLeft": "5px"
                    },
                    inline=True  
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'pet_policy'},
            ),
        ],
        id='pet_policy_div_buy'
        )
        
        return pets_radio

    def create_hoa_fee_components(self):
        # Calculate the number of steps
        num_steps = 5
        step_value = (self.df['hoa_fee'].max() - self.df['hoa_fee'].min()) / num_steps
        # Make sure the step value is a round number for better slider usability
        step_value = np.round(step_value, -int(np.floor(np.log10(step_value))))

        hoa_fee_components = html.Div([
            # Title, subheading, and toggle button
            html.Div([
                html.H5("HOA Fee", style={'display': 'inline-block', 'marginRight': '10px'}),
                html.H6([html.Em("Applies only to SFR and CONDO/TWNHS.")], style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='hoa_fee', initial_label="Hide", page_type='buy')
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown HOA fee?",
                        dcc.RadioItems(
                            id='hoa_fee_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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
        hoa_fee_frequency_checklist = html.Div([
            
            # Title, subheading, and toggle button
            html.Div([
                html.H5("HOA Fee Frequency", style={'display': 'inline-block', 'marginRight': '10px'}),
                html.H6([html.Em("Applies only to SFR and CONDO/TWNHS.")], style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='hoa_fee_frequency', initial_label="Hide", page_type='buy')
            ]),
            
            # The actual Checklist
            html.Div([
                dcc.Checklist(
                    id='hoa_fee_frequency_checklist',
                    options=[
                        {'label': 'N/A', 'value': 'N/A'},
                        {'label': 'Monthly', 'value': 'Monthly'}
                    ],
                    value=['N/A', 'Monthly'],
                    labelStyle={'display': 'block'},
                    inputStyle={
                        "marginRight": "5px",
                        "marginLeft": "5px"
                    },
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'hoa_fee_frequency'},
            ),
            
        ],
        style={
            'marginBottom': '10px',
        },
        id='hoa_fee_frequency_div_buy'
        )

        return hoa_fee_frequency_checklist

    def create_space_rent_components(self):
        space_rent_components = html.Div([
            
            # Title, subheading, and toggle button
            html.Div([
                html.H5("Space Rent", style={'display': 'inline-block', 'marginRight': '10px'}),
                html.H6([html.Em("Applies only to Mobile Homes (MH).")], style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='space_rent', initial_label="Hide", page_type='buy')
            ]),
            
            # The actual RangeSlider
            html.Div([
                dcc.RangeSlider(
                    id='space_rent_slider',
                    min=self.df['space_rent'].min(),
                    max=self.df['space_rent'].max(),
                    value=[self.df['space_rent'].min(), self.df['space_rent'].max()],
                    tooltip={
                        'always_visible': True,
                        'placement': 'bottom',
                        'transform': 'formatCurrency'
                    },
                ),
                # Radio button for unknown space rent
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown space rent?",
                        dcc.RadioItems(
                            id='space_rent_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'space_rent'},
            ),
            
        ],
        style={
            'marginBottom': '10px',
        },
        id='space_rent_div_buy'
        )

        return space_rent_components
    
    def create_senior_community_components(self):
        senior_community_components = html.Div([
            
            # Title, subheading, and toggle button
            html.Div([
                html.H5("Senior Community", style={'display': 'inline-block', 'marginRight': '10px'}),
                html.H6([html.Em("Applies only to Mobile Homes (MH).")], style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='senior_community', initial_label="Hide", page_type='buy')
            ]),
            
            # The actual RadioItems
            html.Div([
                dcc.RadioItems(
                    id='senior_community_radio',
                    options=[
                        {'label': 'Yes', 'value': True},
                        {'label': 'No', 'value': False},
                        {'label': 'Both', 'value': 'Both'},
                    ],
                    value='Both',
                    inputStyle={
                        "marginRight": "5px",
                        "marginLeft": "5px"
                    },
                    inline=True
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'senior_community'},
            ),
            
        ],
        style={
            'marginBottom': '10px',
        },
        id='senior_community_div_buy'
        )

        return senior_community_components
    
    def create_list_price_slider(self):
        list_price_slider = html.Div([
            
            # Title and toggle button
            html.Div([
                html.H5("List Price", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='list_price', initial_label="Hide", page_type='buy')
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
            
            # Title and toggle button
            html.Div([
                html.H5("Year Built", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='year_built', initial_label="Hide", page_type='buy')
            ]),
            
            # The actual RangeSlider and Radio button
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
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown year built?",
                        dcc.RadioItems(
                            id='yrbuilt_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True     
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
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
            
            # Title and toggle button
            html.Div([
                html.H5("Listed Date Range", style={'display': 'inline-block', 'marginRight': '10px'}),
                create_toggle_button(index='listed_date', initial_label="Hide", page_type='buy')
            ]),
            
            # DatePicker and Radio button
            html.Div([
                dcc.DatePickerRange(
                    id='listed_date_datepicker',
                    max_date_allowed=today,
                    start_date=self.earliest_date,
                    end_date=today
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown listed date?",
                        dcc.RadioItems(
                            id='listed_date_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': True},
                                {'label': 'No', 'value': False}
                            ],
                            value=True,
                            inputStyle={
                                "marginRight": "5px",
                                "marginLeft": "5px"
                            },
                            inline=True     
                        ),
                    ],
                    color="info",
                    style={'marginTop': '5px'}
                ),
            ],
            id={'type': 'dynamic_output_div_buy', 'index': 'listed_date'}
            ),
            
        ],
        style={
            'marginBottom': '10px',
        },
        id='listed_date_div_buy'
        )

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
                dl.TileLayer(),
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
            center=(self.df['latitude'].mean(), self.df['longitude'].mean()),
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
    
    def create_more_options(self):
        more_options = dbc.Collapse(
            [
                self.ppsqft_components,
                self.hoa_fee_components,
                self.hoa_fee_frequency_checklist,
                self.space_rent_components,
                self.year_built_components,
                self.pet_policy_radio_button,
                self.senior_community_components,         
            ],
            id='more-options-collapse-buy'
        )

        return more_options
    
    def create_user_options_card(self):
        user_options_card = dbc.Card(
            [
                html.P(
                    "Use the options below to filter the map "
                    "according to your needs.",
                    className="card-text",
                ),
                self.listed_date_components,
                self.subtype_checklist,
                self.list_price_slider,
                self.bedrooms_slider,
                self.bathrooms_slider,
                self.sqft_components,
                dbc.Button("More Options", id='more-options-button-buy', className='mt-2'),
                self.more_options,
            ],
            body=True
        )
        return user_options_card
    
    def create_map_card(self):
        map_card = dbc.Card(
            [self.map], 
            body = True,
            # Make the graph stay in view as the page is scrolled down
            # https://getbootstrap.com/docs/4.0/utilities/position/
            className = 'sticky-top'
        )
    
        return map_card
    
    def create_title_card(self):
        return super().create_title_card(
            title="WhereToLive.LA",
            subtitle="An interactive map of available residential properties for sale in Los Angeles County. Updated weekly."
        )