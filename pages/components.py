from dash import html, dcc
from datetime import date
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import pandas as pd

def create_toggle_button(index, initial_label="Hide"):
    """Creates a toggle button with an initial label."""
    return html.Button(
        id={'type': 'dynamic_toggle_button', 'index': index}, 
        children=initial_label, 
        style={'display': 'inline-block'}
    )

# Create a class to hold all of the Dash components for the Lease page
class LeaseComponents:
    # Class Variables
    subtype_meaning = {
        'APT': 'Apartment (Unspecified)',
        'APT/A': 'Apartment (Attached)',
        'APT/D': 'Apartment (Detached)',
        'CABIN/D': 'Cabin (Detached)',
        'COMRES/A': 'Commercial/Residential (Attached)',
        'COMRES/D': 'Commercial/Residential (Detached)',
        'CONDO': 'Condo (Unspecified)',
        'CONDO/A': 'Condo (Attached)',
        'CONDO/D': 'Condo (Detached)',
        'COOP/A': 'Cooperative (Attached)',
        'DPLX/A': 'Duplex (Attached)',
        'DPLX/D': 'Duplex (Detached)',
        'LOFT/A': 'Loft (Attached)',
        'MANL/D': '??? (Detached)',
        'MH': 'Mobile Home',
        'OYO/D': 'Own-Your-Own (Detached)',
        'QUAD': 'Quadplex (Unspecified)',
        'QUAD/A': 'Quadplex (Attached)',
        'QUAD/D': 'Quadplex (Detached)',
        'RMRT/A': '??? (Attached)',
        'RMRT/D': '??? (Detached)',
        'SFR': 'Single Family Residence (Unspecified)',
        'SFR/A': 'Single Family Residence (Attached)',
        'SFR/D': 'Single Family Residence (Detached)',
        'STUD/A': 'Studio (Attached)',
        'STUD/D': 'Studio (Detached)',
        'TPLX': 'Triplex (Unspecified)',
        'TPLX/A': 'Triplex (Attached)',
        'TPLX/D': 'Triplex (Detached)',
        'TWNHS': 'Townhouse (Unspecified)',
        'TWNHS/A': 'Townhouse (Attached)',
        'TWNHS/D': 'Townhouse (Detached)',
        'Unknown': 'Unknown',
    }
    laundry_categories = [
        'Dryer Hookup',
        'Dryer Included',
        'Washer Hookup',
        'Washer Included',
        'Community Laundry',
        'Other',
        'Unknown',
        'None',
    ]

    def __init__(self, df):
        # Initalize these first because they are used in other components
        self.df = df 

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
        
    def create_subtype_checklist(self):
        # Instance Variable
        unique_values = self.df['subtype'].dropna().unique().tolist()
        unique_values = ["Unknown" if i == "/D" else i for i in unique_values]
        if "Unknown" not in unique_values:
            unique_values.append("Unknown")

        # Dash Component as Class Method
        subtype_checklist = html.Div([ 
            html.Div([
                html.H5("Subtypes", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='subtype', initial_label="Hide")
            ]),
            html.Div([
                html.H6([html.Em("Use the scrollbar on the right to view more subtype options.")]),
                dcc.Checklist( 
                    id='subtype_checklist',
                    options=sorted(
                        [
                            {'label': f"{i} - {self.subtype_meaning.get(i, 'Unknown')}", 'value': i}
                            for i in set(unique_values)
                        ], 
                        key=lambda x: x['label']
                    ),
                    value=[term['value'] for term in [{'label': "Unknown" if pd.isnull(term) else term, 'value': "Unknown" if pd.isnull(term) else term} for term in self.df['subtype'].unique()]],
                    labelStyle={'display': 'block'},
                    inputStyle={"margin-right": "5px", "margin-left": "5px"},
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'subtype'},
            style={
                "overflow-y": "scroll",
                "overflow-x": 'hidden',
                "height": '220px'
            })
        ])

        return subtype_checklist
    
    def create_bedrooms_slider(self):
        bedrooms_slider = html.Div([
            html.Div([
                html.H5("Bedrooms", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='bedrooms', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=0,
                    max=self.df['Bedrooms'].max(),
                    step=1,
                    value=[0, self.df['Bedrooms'].max()],
                    id='bedrooms_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'bedrooms'},
            ),
        ],
        id='bedrooms_div'
        )

        return bedrooms_slider

    def create_bathrooms_slider(self):
        bathrooms_slider = html.Div([
            html.Div([
                html.H5("Bathrooms", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='bathrooms', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=0,
                    max=self.df['Total Bathrooms'].max(),
                    step=1,
                    value=[0, self.df['Total Bathrooms'].max()],
                    id='bathrooms_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'bathrooms'},
            ),
        ],
        id='bathrooms_div'
        )

        return bathrooms_slider

    def create_sqft_components(self):
        square_footage_components = html.Div([
            html.Div([
                html.H5("Square Footage", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='sqft', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['Sqft'].min(),
                    max=self.df['Sqft'].max(),
                    value=[self.df['Sqft'].min(), self.df['Sqft'].max()],
                    id='sqft_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown square footage?",
                        dcc.RadioItems(
                            id='sqft_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'sqft'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='square_footage_div'
        )

        return square_footage_components

    def create_ppsqft_components(self):
        ppsqft_components = html.Div([
            html.Div([
                html.H5("Price Per Square Foot ($)", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='ppsqft', initial_label="Hide")
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
                        "always_visible": True
                    },
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown price per square foot?",
                        dcc.RadioItems(
                            id='ppsqft_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'ppsqft'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='ppsqft_div'
        )

        return ppsqft_components

    
    def create_pets_radio_button(self):
        pets_radio = html.Div([
            html.Div([
                html.H5("Pet Policy", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='pets', initial_label="Hide")
            ], style={'display': 'inline-block'}),
            html.Div([
                dcc.RadioItems(
                    id='pets_radio',
                    options=[
                        {'label': 'Pets Allowed', 'value': 'Yes'},
                        {'label': 'Pets NOT Allowed', 'value': 'No'},
                        {'label': 'Both', 'value': 'Both'}
                    ],
                    value='Both',
                    inputStyle={
                        "margin-right": "5px",
                        "margin-left": "5px"
                    },
                    inline=True
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'pets'}
            ),
        ],
        id='pet_policy_div'
        )

        return pets_radio

    def create_rental_terms_checklist(self):
        # Logic to calculate unique_terms
        unique_terms = pd.Series([term for sublist in self.df['Terms'].fillna('Unknown').str.split(',') for term in sublist]).unique()
        unique_terms = sorted(unique_terms)

        # Define term_abbreviations and terms
        term_abbreviations = {
            '12M': '12 Months',
            '24M': '24 Months',
            '6M': '6 Months',
            'MO': 'Month-to-Month',
            'NG': 'Negotiable',
            'SN': 'Seasonal',
            'STL': 'Short Term Lease',
            'Unknown': 'Unknown',
            'VR': 'Vacation Rental',
        }
        terms = {k: term_abbreviations[k] for k in sorted(term_abbreviations)}

        # Create the Dash component
        rental_terms_checklist = html.Div([
            html.Div([
                html.H5("Lease Length", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='rental_terms', initial_label="Hide")
            ], style={'display': 'inline-block'}),
            html.Div([
                dcc.Checklist(
                    id='terms_checklist',
                    options=[{'label': f"{terms[term]} ({term})", 'value': term} for term in terms],
                    value=[term['value'] for term in [{'label': "Unknown" if pd.isnull(term) else term, 'value': "Unknown" if pd.isnull(term) else term} for term in unique_terms]],
                    inputStyle={
                        "margin-right": "5px",
                        "margin-left": "5px"
                    },
                    inline=False
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'rental_terms'},
            ),
        ],
        id='rental_terms_div'
        )

        return rental_terms_checklist

    def create_garage_spaces_components(self):
        garage_spaces_components = html.Div([
            html.Div([
                html.H5("Garage Spaces", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='garage_spaces', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=0, 
                    max=self.df['garage_spaces'].max(),
                    value=[0, self.df['garage_spaces'].max()], 
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
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'garage_spaces'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='garage_spaces_div'
        )

        return garage_spaces_components

    def create_rental_price_slider(self):
        rental_price_components = html.Div([
            html.Div([
                html.H5("Price (Monthly)", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='rental_price', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['list_price'].min(),
                    max=self.df['list_price'].max(),
                    value=[0, self.df['list_price'].max()],
                    id='rental_price_slider',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                    updatemode='mouseup'
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'rental_price'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='rental_price_div'
        )

        return rental_price_components

    def create_year_built_components(self):
        year_built_components = html.Div([
            html.Div([
                html.H5("Year Built", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='year_built', initial_label="Hide")
            ], style={'display': 'inline-block'}),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['YrBuilt'].min(),
                    max=self.df['YrBuilt'].max(),
                    value=[0, self.df['YrBuilt'].max()],
                    id='yrbuilt_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                    marks={
                        float(self.df['YrBuilt'].min() + i*20): str(self.df['YrBuilt'].min() + i*20) for i in range(8)
                    }
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown year built?",
                        dcc.RadioItems(
                            id='yrbuilt_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'year_built'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='year_built_div'
        )

        return year_built_components

    def create_furnished_checklist(self):
        furnished_checklist = html.Div([
            html.Div([
                html.H5("Furnished/Unfurnished", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='furnished', initial_label="Hide")
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
                        "margin-right": "5px",
                        "margin-left": "5px"
                    },
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'furnished'},
            ),
        ],
        id='furnished_div'
        )

        return furnished_checklist

    def create_security_deposit_components(self):
        security_deposit_components = html.Div([
            html.Div([
                html.H5("Security Deposit", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='security_deposit', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['DepositSecurity'].min(),
                    max=self.df['DepositSecurity'].max(),
                    value=[self.df['DepositSecurity'].min(), self.df['DepositSecurity'].max()],
                    id='security_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown security deposit?",
                        dcc.RadioItems(
                            id='security_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'security_deposit'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='security_deposit_div'
        )

        return security_deposit_components

    def create_other_deposit_components(self):
        other_deposit_components = html.Div([
            html.Div([
                html.H5("Other Deposit", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='other_deposit', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['DepositOther'].min(),
                    max=self.df['DepositOther'].max(),
                    value=[self.df['DepositOther'].min(), self.df['DepositOther'].max()],
                    id='other_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown misc/other deposit?",
                        dcc.RadioItems(
                            id='other_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'other_deposit'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='other_deposit_div'
        )

        return other_deposit_components

    def create_pet_deposit_components(self):
        pet_deposit_components = html.Div([
            html.Div([
                html.H5("Pet Deposit", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='pet_deposit', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['DepositPets'].min(),
                    max=self.df['DepositPets'].max(),
                    value=[self.df['DepositPets'].min(), self.df['DepositPets'].max()],
                    id='pet_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown pet deposit?",
                        dcc.RadioItems(
                            id='pet_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'pet_deposit'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='pet_deposit_div'
        )

        return pet_deposit_components

    def create_key_deposit_components(self):
        key_deposit_components = html.Div([
            html.Div([
                html.H5("Key Deposit", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='key_deposit', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['DepositKey'].min(),
                    max=self.df['DepositKey'].max(),
                    value=[self.df['DepositKey'].min(), self.df['DepositKey'].max()],
                    id='key_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown key deposit?",
                        dcc.RadioItems(
                            id='key_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'key_deposit'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='key_deposit_div'
        )

        return key_deposit_components

    def create_key_deposit_components(self):
        key_deposit_components = html.Div([
            html.Div([
                html.H5("Key Deposit", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='key_deposit', initial_label="Hide")
            ]),
            html.Div([
                dcc.RangeSlider(
                    min=self.df['DepositKey'].min(),
                    max=self.df['DepositKey'].max(),
                    value=[self.df['DepositKey'].min(), self.df['DepositKey'].max()],
                    id='key_deposit_slider',
                    updatemode='mouseup',
                    tooltip={
                        "placement": "bottom",
                        "always_visible": True
                    },
                ),
                dbc.Alert(
                    [
                        html.I(className="bi bi-info-circle-fill me-2"),
                        "Should we include properties with an unknown key deposit?",
                        dcc.RadioItems(
                            id='key_deposit_missing_radio',
                            options=[
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'key_deposit'}
            ),
        ],
        style={
            'margin-bottom': '10px',
        },
        id='key_deposit_div'
        )

        return key_deposit_components

    def create_laundry_checklist(self):
        laundry_checklist = html.Div([
            html.Div([
                html.H5("Laundry Features", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='laundry', initial_label="Hide")
            ]),
            html.Div([
                dcc.Checklist(
                    id='laundry_checklist',
                    options=sorted([{'label': i, 'value': i} for i in self.laundry_categories], key=lambda x: x['label']),
                    value=self.laundry_categories,
                    labelStyle={'display': 'block'},
                    inputStyle={
                        "margin-right": "5px",
                        "margin-left": "5px"
                    },
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'laundry'}
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
                html.H5("Listed Date Range", style={'display': 'inline-block', 'margin-right': '10px'}),
                create_toggle_button(index='listed_date', initial_label="Hide")
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
                                {'label': 'Yes', 'value': 'True'},
                                {'label': 'No', 'value': 'False'}
                            ],
                            value='True',
                            inputStyle={
                                "margin-right": "5px",
                                "margin-left": "5px"
                            },
                            inline=True
                        ),
                    ],
                    color="info",
                ),
            ],
            id={'type': 'dynamic_output_div', 'index': 'listed_date'}
            ),
        ],
        id='listed_date_div'
        )
        
        return listed_date_components
    
    def create_map(self):
        map = dl.Map(
        [dl.TileLayer(), dl.LayerGroup(id="lease_geojson"), dl.FullScreenControl()],
        id='map',
        zoom=9,
        minZoom=9,
        center=(self.df['Latitude'].mean(), self.df['Longitude'].mean()),
        preferCanvas=True,
        closePopupOnClick=True,
        style={'width': '100%', 'height': '90vh', 'margin': "auto", "display": "inline-block"}
        )

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
            className = 'sticky-top'
        )
    
        return map_card
    
    def create_title_card(self):
        title_card = dbc.Card(
            [
                html.H3("WhereToLive.LA", className="card-title"),
                html.P("An interactive map of available rentals in Los Angeles County. Updated weekly."),
                html.P(f"Last updated: {self.last_updated}", style={'margin-bottom': '5px'}),
                html.I(
                  className="bi bi-github",
                  style = {
                    "margin-right": "5px",
                  },
                ),
                html.A("GitHub", href='https://github.com/perfectly-preserved-pie/larentals', target='_blank'),
                html.I(
                  className="fa-solid fa-blog",
                  style = {
                    "margin-right": "5px",
                    "margin-left": "15px"
                  },
                ),
                html.A("About This Project", href='https://automateordie.io/wheretolivedotla/', target='_blank'),
                dbc.Button(
                  " Looking to buy a property instead?",
                  href="/for-sale",
                  color="primary",
                  external_link=True,
                  className="bi bi-house-door-fill w-100 mt-2",
                ),
            ],
            body = True
        )

        return title_card

# Create a class to hold all the components for the for-sale page
class BuyComponents:
    # Class Variables
    subtype_meaning = { # Define a dictionary that maps each subtype to its corresponding meaning
        'CONDO': 'Condo (Unspecified)',
        'CONDO/A': 'Condo (Attached)',
        'CONDO/D': 'Condo (Detached)',
        'MH': 'Mobile Home',
        'SFR': 'Single Family Residence (Unspecified)',
        'SFR/A': 'Single Family Residence (Attached)',
        'SFR/D': 'Single Family Residence (Detached)',
        'TWNHS': 'Townhouse (Unspecified)',
        'TWNHS/A': 'Townhouse (Attached)',
        'TWNHS/D': 'Townhouse (Detached)',
        'Unknown': 'Unknown'
    }

    def __init__(self, df):
        # Initalize these first because they are used in other components
        self.df = df

        self.bathrooms_slider = self.create_bathrooms_slider()
        self.bedrooms_slider = self.create_bedrooms_slider()
        self.df['listed_date'] = pd.to_datetime(self.df['listed_date'], errors='coerce')
        self.earliest_date = (self.df['listed_date'].min()).to_pydatetime()
        self.hoa_fee_frequncy_checklist = self.create_hoa_fee_frequency_checklist()
        self.hoa_fee_slider = self.create_hoa_fee_slider()
        self.last_updated = self.df['date_processed'].max().strftime('%m/%d/%Y')
        self.list_price_slider = self.create_list_price_slider()
        self.listed_date_datepicker = self.create_listed_date_datepicker()
        self.listed_date_radio_button = self.create_unknown_listed_date_radio_button()
        self.map = self.create_map()
        self.map_card = self.create_map_card()
        self.pet_policy_radio_button = self.create_pets_radio_button()
        self.ppsqft_radio_button = self.create_unknown_ppsqft_radio_button()
        self.ppsqft_slider = self.create_ppsqft_slider()
        self.senior_community_radio_button = self.create_senior_community_radio_button()
        self.space_rent_slider = self.create_space_rent_slider()
        self.square_footage_radio_button = self.create_unknown_square_footage_radio_button()
        self.square_footage_slider = self.create_square_footage_slider()
        self.subtype_checklist = self.create_subtype_checklist()
        self.title_card = self.create_title_card()
        self.unknown_hoa_fee_radio_button = self.create_unknown_hoa_fee_radio_button()
        self.unknown_space_rent_radio_button = self.create_unknown_space_rent_radio_button()
        self.unknown_year_built_radio_button = self.create_unknown_year_built_radio_button()
        self.year_built_slider = self.create_year_built_slider()

        # Initialize these last because they depend on other components
        self.more_options = self.create_more_options()
        self.user_options_card = self.create_user_options_card()

    # Create a checklist for the user to select the subtypes they want to see
    def create_subtype_checklist(self):
        subtype_checklist = html.Div([ 
            # Title this section
            html.H5("Subtypes"), 
            # Create a checklist of options for the user
            # https://dash.plotly.com/dash-core-components/checklist
            dcc.Checklist( 
                id = 'subtype_checklist',
                # Loop through the list of subtypes and create a dictionary of options
                options = sorted(
                [
                    {
                        'label': f"{i if not pd.isna(i) else 'Unknown'} - {self.subtype_meaning.get(i if not pd.isna(i) else 'Unknown', 'Unknown')}", 
                        'value': i if not pd.isna(i) else 'Unknown'
                    }
                    for i in self.df['subtype'].unique()
                ], 
                key=lambda x: x['label']
                ), 
                # Set the default values to all of the subtypes while handling nulls
                value = [i if not pd.isna(i) else 'Unknown' for i in self.df['subtype'].unique()],
                labelStyle = {'display': 'block'},
                # add some spacing in between the checkbox and the label
                # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
                inputStyle = {
                "margin-right": "5px",
                "margin-left": "5px"
                },
        ),
        ],
        id = 'subtypes_div',
        )

        return subtype_checklist
    
    def create_bedrooms_slider(self):
        bedrooms_slider = html.Div([
            html.H5("Bedrooms"),
            # Create a range slider for # of bedrooms
            dcc.RangeSlider(
            min=0, 
            max=self.df['Bedrooms'].max(), # Dynamically calculate the maximum number of bedrooms
            step=1, 
            value=[0, self.df['Bedrooms'].max()], 
            id='bedrooms_slider',
            updatemode='mouseup',
            tooltip={
                "placement": "bottom",
                "always_visible": True
            },
            ),
        ],
        id = 'bedrooms_div'
        )
        
        return bedrooms_slider
    
    def create_bathrooms_slider(self):
        bathrooms_slider = html.Div([
            html.H5("Bathrooms"),
            # Create a range slider for # of total bathrooms
            dcc.RangeSlider(
            min=0, 
            max=self.df['Total Bathrooms'].max(), 
            step=1, 
            value=[0, self.df['Total Bathrooms'].max()], 
            id='bathrooms_slider',
            updatemode='mouseup',
            tooltip={
                "placement": "bottom",
                "always_visible": True
            },
            ),
        ],
        id = 'bathrooms_div'
        )

        return bathrooms_slider
    
    def create_square_footage_slider(self):
        # Create a range slider for square footage
        square_footage_slider = html.Div([
        html.H5("Square Footage"),
        dcc.RangeSlider(
            min=self.df['Sqft'].min(), 
            max=self.df['Sqft'].max(),
            value=[self.df['Sqft'].min(), self.df['Sqft'].max()], 
            id='sqft_slider',
            tooltip={
            "placement": "bottom",
            "always_visible": True
            },
            updatemode='mouseup'
        ),
        ],
        style = {
        'margin-bottom' : '10px',
        }, 
        id = 'square_footage_div'
        )

        return square_footage_slider
    
    def create_unknown_square_footage_radio_button(self):
        unknown_square_footage_radio = html.Div([
        dbc.Alert(
            [
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown square footage?"),
            dcc.RadioItems(
                id='sqft_missing_radio',
                options=[
                    {'label': 'Yes', 'value': 'True'},
                    {'label': 'No', 'value': 'False'}
                ],
                value='True',
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
                inline=True     
            ),
            ],
        color="info",
        ),
        ],
        id = 'unknown_square_footage_div'
        )

        return unknown_square_footage_radio
    
    def create_ppsqft_slider(self):
        ppsqft_slider = html.Div([
            html.H5("Price Per Square Foot"),
            # Create a range slider for price per square foot
            dcc.RangeSlider(
            min=self.df['ppsqft'].min(), 
            max=self.df['ppsqft'].max(),
            value=[self.df['ppsqft'].min(), self.df['ppsqft'].max()], 
            id='ppsqft_slider',
            tooltip={
                "placement": "bottom",
                "always_visible": True
            },
            updatemode='mouseup'
            ),
        ],
        style = {
            'margin-bottom' : '10px',
        },
        id = 'ppsqft_div'
        )

        return ppsqft_slider
    
    def create_unknown_ppsqft_radio_button(self):
        unknown_ppsqft_radio = html.Div([
        dbc.Alert(
            [
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown price per square foot?"),
            dcc.RadioItems(
                id='ppsqft_missing_radio',
                options=[
                    {'label': 'Yes', 'value': 'True'},
                    {'label': 'No', 'value': 'False'}
                ],
                value='True',
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
                inline=True     
            ),
            ],
        color="info",
        ),
        ],
        id = 'unknown_ppsqft_div'
        )

        return unknown_ppsqft_radio
    
    def create_pets_radio_button(self):
        pets_radio = html.Div([
            html.H5("Pet Policy"),
            html.H6([html.Em("Applies only to Mobile Homes (MH).")]),
            # Create a radio button for pet policy
            dcc.RadioItems(
                id = 'pets_radio',
                options=[
                    {'label': 'Pets Allowed', 'value': 'True'},
                    {'label': 'Pets NOT Allowed', 'value': 'False'},
                    {'label': 'Both', 'value': 'Both'},
                ],
                value='Both', # A value needs to be selected upon page load otherwise we error out. See https://community.plotly.com/t/how-to-convert-a-nonetype-object-i-get-from-a-checklist-to-a-list-or-int32/26256/2
                # add some spacing in between the checkbox and the label
                # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
                inline=True  
            ),
        ],
        id = 'pet_policy_div'
        )

        return pets_radio

    def create_hoa_fee_slider(self):
        # Create a slider for HOA fees
        hoa_fee_slider = html.Div([
            # Title this section
            html.H5("HOA Fee"),
            html.H6([html.Em("Applies only to SFR and CONDO/TWNHS.")]),
            # Create a slider for the user to select the range of HOA fees they want to see
            # https://dash.plotly.com/dash-core-components/slider
            dcc.RangeSlider(
                id = 'hoa_fee_slider',
                # Set the min and max values to the min and max of the HOA fee column
                min = self.df['hoa_fee'].min(),
                max = self.df['hoa_fee'].max(),
                # Set the default values to the min and max of the HOA fee column
                value = [self.df['hoa_fee'].min(), self.df['hoa_fee'].max()],
                # Set the tooltip to be the value of the slider
                tooltip = {'always_visible': True, 'placement': 'bottom'},
            ),
            # Create a radio button for the user to select whether they want to include properties with no HOA fee listed
            # https://dash.plotly.com/dash-core-components/radioitems
            dcc.RadioItems(
                id = 'hoa_fee_missing_radio',
                options=[
                    {'label': 'Yes', 'value': 'True'},
                    {'label': 'No', 'value': 'False'}
                ],
                value='True',
                # add some spacing in between the checkbox and the label
                # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
                inline=True     
            ),
        ],
        style = {
            'margin-bottom' : '10px',
        },
        id = 'hoa_fee_div',
        )

        return hoa_fee_slider
    
    def create_unknown_hoa_fee_radio_button(self):
        unknown_hoa_fee_radio = html.Div([
        dbc.Alert(
            [
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown HOA fee?"),
            dcc.RadioItems(
                id='hoa_fee_missing_radio',
                options=[
                    {'label': 'Yes', 'value': 'True'},
                    {'label': 'No', 'value': 'False'}
                ],
                value='True',
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
                inline=True     
            ),
            ],
        color="info",
        ),
        ],
        id = 'unknown_hoa_fee_div'
        )

        return unknown_hoa_fee_radio

    def create_hoa_fee_frequency_checklist(self):
        # Create a checklist for HOA fee frequency
        hoa_fee_frequency_checklist = html.Div([
            # Title this section
            html.H5("HOA Fee Frequency"),
            html.H6([html.Em("Applies only to SFR and CONDO/TWNHS.")]),
            # Create a checklist for the user to select the frequency of HOA fees they want to see
            dcc.Checklist(
                id = 'hoa_fee_frequency_checklist',
                options=[
                    {'label': 'N/A', 'value': 'N/A'},
                    {'label': 'Monthly', 'value': 'Monthly'}
                ],
                # Set the value to all of the values in options
                value = ['N/A', 'Monthly'],
                labelStyle = {'display': 'block'},
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
            ),
        ],
        id = 'hoa_fee_frequency_div',
        )

        return hoa_fee_frequency_checklist

    def create_space_rent_slider(self):
        # Create a slider for space rent
        space_rent_slider = html.Div([
            # Title this section
            html.H5("Space Rent"),
            html.H6([html.Em("Applies only to Mobile Homes (MH).")]),
            # Create a slider for the user to select the range of space rent they want to see
            # https://dash.plotly.com/dash-core-components/slider
            dcc.RangeSlider(
                id = 'space_rent_slider',
                # Set the min and max values to the min and max of the space rent column
                min = self.df['space_rent'].min(),
                max = self.df['space_rent'].max(),
                # Set the default values to the min and max of the space rent column
                value = [self.df['space_rent'].min(), self.df['space_rent'].max()],
                # Set the tooltip to be the value of the slider
                tooltip = {'always_visible': True, 'placement': 'bottom'},
            ),
        ],
        style = {
            'margin-bottom' : '10px',
        },
        id = 'space_rent_div',
        )

        return space_rent_slider

    def create_unknown_space_rent_radio_button(self):
        unknown_space_rent_radio = html.Div([
        dbc.Alert(
            [
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown space rent?"),
            dcc.RadioItems(
                id='space_rent_missing_radio',
                options=[
                    {'label': 'Yes', 'value': 'True'},
                    {'label': 'No', 'value': 'False'}
                ],
                value='True',
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
                inline=True     
            ),
            ],
        color="info",
        ),
        ],
        id = 'unknown_space_rent_div'
        )

        return unknown_space_rent_radio
    
    def create_senior_community_radio_button(self):
        # Create a radio button for the user to select whether they want to see properties in Senior Communities
        # https://dash.plotly.com/dash-core-components/radioitems
        senior_community_radio = html.Div([
            html.H5("Senior Community"),
            html.H6([html.Em("Applies only to Mobile Homes (MH).")]),
            dcc.RadioItems(
                id = 'senior_community_radio',
                options=[
                    {'label': 'Yes', 'value': 'True'},
                    {'label': 'No', 'value': 'False'},
                    {'label': 'Both', 'value': 'Both'},
                ],
                value='Both',
                # add some spacing in between the checkbox and the label
                # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
                inline=True   
            ),
        ],
        id = 'senior_community_div'
        )

        return senior_community_radio
    
    def create_list_price_slider(self):
        # Create a range slider for list price
        list_price_slider = html.Div([ 
        html.H5("List Price"),
        dcc.RangeSlider(
            min=self.df['list_price'].min(),
            max=self.df['list_price'].max(),
            value=[0, self.df['list_price'].max()],
            id='list_price_slider',
            tooltip={
            "placement": "bottom",
            "always_visible": True
            },
            updatemode='mouseup'
        ),
        ],
        style = {
        'margin-bottom' : '10px',
        },
        id = 'list_price_div'
        )

        return list_price_slider

    def create_year_built_slider(self):
        year_built_slider = html.Div([
            html.H5("Year Built"),
            # Create a range slider for year built
            dcc.RangeSlider(
            min=self.df['year_built'].min(),
            max=self.df['year_built'].max(),
            value=[0, self.df['year_built'].max()],
            id='yrbuilt_slider',
            tooltip={
                "placement": "bottom",
                "always_visible": True
            },
            marks = { # Create custom tick marks
                # The left column should be floats, the right column should be strings
                f"{self.df['year_built'].min()}": f"{self.df['year_built'].min()}", # first mark is oldest house
                float(f"{self.df['year_built'].min()}") + 20: str(float(f"{self.df['year_built'].min()}") + 20), # next mark is oldest house + 20 years
                float(f"{self.df['year_built'].min()}") + 40: str(float(f"{self.df['year_built'].min()}") + 40),
                float(f"{self.df['year_built'].min()}") + 60: str(float(f"{self.df['year_built'].min()}") + 60),
                float(f"{self.df['year_built'].min()}") + 80: str(float(f"{self.df['year_built'].min()}") + 80),
                float(f"{self.df['year_built'].min()}") + 100: str(float(f"{self.df['year_built'].min()}") + 100),
                float(f"{self.df['year_built'].min()}") + 120: str(float(f"{self.df['year_built'].min()}") + 120),
                float(f"{self.df['year_built'].min()}") + 140: str(float(f"{self.df['year_built'].min()}") + 140),
                f"{self.df['year_built'].max()}": str(f"{self.df['year_built'].max()}") # last mark is newest house
            },
            updatemode='mouseup'
            ),
        ],
        style = {
            'margin-bottom' : '10px',
        },
        id = 'yrbuilt_div'
        )

        return year_built_slider
    
    def create_unknown_year_built_radio_button(self):
        unknown_year_built_radio = html.Div([
        dbc.Alert(
            [
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown year built?"),
            dcc.RadioItems(
                id='yrbuilt_missing_radio',
                options=[
                    {'label': 'Yes', 'value': 'True'},
                    {'label': 'No', 'value': 'False'}
                ],
                value='True',
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
                inline=True     
            ),
            ],
        color="info",
        ),
        ],
        id = 'yrbuilt_missing_div'
        )

        return unknown_year_built_radio
    
    def create_listed_date_datepicker(self):
        # Get today's date and set it as the end date for the date picker
        today = date.today()
        listed_date_datepicker = html.Div([
            html.H5("Listed Date Range"),
            dcc.DatePickerRange(
                id='listed_date_datepicker',
                max_date_allowed=today,
                start_date=self.earliest_date,
                end_date=today
            ),
        ],
        id='listed_date_datepicker_div'
        )
        return listed_date_datepicker
    
    def create_unknown_listed_date_radio_button(self):
        unknown_listed_date_radio = html.Div([
        dbc.Alert(
            [
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown listed date?"),
            dcc.RadioItems(
                id='listed_date_missing_radio',
                options=[
                    {'label': 'Yes', 'value': 'True'},
                    {'label': 'No', 'value': 'False'}
                ],
                value='True',
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
                inline=True     
            ),
            ],
        color="info",
        ),
        ],
        id = 'unknown_listed_date_div'
        )

        return unknown_listed_date_radio

    def create_map(self):
        map = dl.Map(
        [dl.TileLayer(), dl.LayerGroup(id="buy_geojson"), dl.FullScreenControl()],
        id='map',
        zoom=9,
        minZoom=9,
        center=(self.df['Latitude'].mean(), self.df['Longitude'].mean()),
        preferCanvas=True,
        closePopupOnClick=True,
        style={'width': '100%', 'height': '90vh', 'margin': "auto", "display": "inline-block"}
        )

        return map
    
    def create_more_options(self):
        more_options = dbc.Collapse(
            [
                self.ppsqft_slider,
                self.ppsqft_radio_button,
                self.hoa_fee_slider,
                self.unknown_hoa_fee_radio_button,
                self.hoa_fee_frequncy_checklist,
                self.space_rent_slider,
                self.unknown_space_rent_radio_button,
                self.year_built_slider,
                self.unknown_year_built_radio_button,
                self.pet_policy_radio_button,
                self.senior_community_radio_button,         
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
                self.listed_date_datepicker,
                self.listed_date_radio_button,
                self.subtype_checklist,
                self.list_price_slider,
                self.bedrooms_slider,
                self.bathrooms_slider,
                self.square_footage_slider,
                self.square_footage_radio_button,
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
        title_card = dbc.Card(
        [
            html.H3("WhereToLive.LA", className="card-title"),
            html.P("An interactive map of available residential properties for sale in Los Angeles County. Updated weekly."),
            html.P(f"Last updated: {self.last_updated}", style={'margin-bottom': '5px'}),
            # Use a GitHub icon for my repo
            html.I(
            className="bi bi-github",
            style = {
                "margin-right": "5px",
            },
            ),
            html.A("GitHub", href='https://github.com/perfectly-preserved-pie/larentals', target='_blank'),
            # Add an icon for my blog
            html.I(
            className="fa-solid fa-blog",
            style = {
                "margin-right": "5px",
                "margin-left": "15px"
            },
            ),
            html.A("About This Project", href='https://automateordie.io/wheretolivedotla/', target='_blank'),
            dbc.Button(
            " Looking to rent a property instead?",
            href="/",
            color="primary",
            external_link=True,
            className="bi bi-building-fill w-100 mt-2",
            ),
        ],
        body = True
        )

        return title_card