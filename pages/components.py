from dash import html, dcc
from datetime import date
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import pandas as pd

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
        self.df = df
        # You can call the method to initialize the component
        self.subtype_checklist = self.create_subtype_checklist()
        self.bedrooms_slider = self.create_bedrooms_slider()
        self.bathrooms_slider = self.create_bathrooms_slider()
        self.square_footage_slider = self.create_sqft_slider()
        self.square_footage_radio = self.create_sqft_radio_button()
        self.ppsqft_slider = self.create_ppsqft_slider()
        self.ppsqft_radio = self.create_ppsqft_radio_button()
        self.pets_radio = self.create_pets_radio_button()
        self.rental_terms_checklist = self.create_rental_terms_checklist()
        self.garage_spaces_slider = self.create_garage_spaces_slider()
        self.unknown_garage_radio = self.create_unknown_garage_radio_button()
        self.rental_price_slider = self.create_rental_price_slider()
        self.year_built_slider = self.create_year_built_slider()
        self.unknown_year_built_radio = self.create_unknown_year_built_radio_button()
        self.furnished_checklist = self.create_furnished_checklist()
        self.security_deposit_slider = self.create_security_deposit_slider()
        self.unknown_security_deposit_radio = self.create_unknown_security_deposit_radio_button()
        self.pet_deposit_slider = self.create_pet_deposit_slider()
        self.unknown_pet_deposit_radio = self.create_unknown_pet_deposit_radio_button()
        self.key_deposit_slider = self.create_key_deposit_slider()
        self.unknown_key_deposit_radio = self.create_unknown_key_deposit_radio_button()
        self.other_deposit_slider = self.create_other_deposit_slider()
        self.unknown_other_deposit_radio = self.create_unknown_other_deposit_radio_button()
        self.laundry_checklist = self.create_laundry_checklist()
        self.listed_date_datepicker = self.create_listed_date_datepicker()
        self.listed_date_radio = self.create_listed_date_radio_button()
        self.map = self.create_map()
        self.map_card = self.create_map_card()
        self.more_options = self.create_more_options()
        self.user_options_card = self.create_user_options_card()
        self.last_updated = self.df['date_processed'].max().strftime('%m/%d/%Y')
        self.title_card = self.create_title_card()
        
    def create_subtype_checklist(self):
        # Instance Variable
        unique_values = self.df['subtype'].dropna().unique().tolist()
        unique_values = ["Unknown" if i == "/D" else i for i in unique_values]
        if "Unknown" not in unique_values:
            unique_values.append("Unknown")

        # Dash Component as Class Method
        subtype_checklist = html.Div([ 
            html.H5("Subtypes"),
            html.H6([html.Em("Use the scrollbar on the right to view more subtype options.")]),
            dcc.Checklist( 
                id = 'subtype_checklist',
                options = sorted(
                    [
                        {
                            'label': f"{i} - {self.subtype_meaning.get(i, 'Unknown')}", 
                            'value': i
                        }
                        for i in set(unique_values)
                    ], 
                    key=lambda x: x['label']
                ),
                value = [term['value'] for term in [{'label': "Unknown" if pd.isnull(term) else term, 'value': "Unknown" if pd.isnull(term) else term} for term in self.df['subtype'].unique()]],
                labelStyle = {'display': 'block'},
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
            ),
        ],
        id = 'subtypes_div',
        style = {
            "overflow-y": "scroll",
            "overflow-x": 'hidden',
            "height": '220px'
        })

        return subtype_checklist
    
    def create_bedrooms_slider(self):
        bedrooms_slider = html.Div([
            html.H5("Bedrooms"),
            # Create a range slider for # of bedrooms
            dcc.RangeSlider(
                min=0, 
                max=self.df['Bedrooms'].max(),  # Use self.df to refer to the DataFrame
                step=1, 
                value=[0, self.df['Bedrooms'].max()],  # Use self.df to refer to the DataFrame
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

    def create_sqft_slider(self):
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

    def create_sqft_radio_button(self):
        square_footage_radio = html.Div([
        dbc.Alert(
            [
            # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown square footage?"),
            dcc.RadioItems(
                id='sqft_missing_radio',
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
        color="info",
        ),
        ],
        id = 'unknown_sqft_div',
        )

        return square_footage_radio

    def create_ppsqft_slider(self):
        ppsqft_slider = html.Div([
            html.H5("Price Per Square Foot ($)"),
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
    
    def create_ppsqft_radio_button(self):
        ppsqft_radio = html.Div([
        dbc.Alert(
            [
            # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
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

        return ppsqft_radio
    
    def create_pets_radio_button(self):
        pets_radio = html.Div([
            html.H5("Pet Policy"),
            # Create a checklist for pet policy
            dcc.RadioItems(
            id = 'pets_radio',
            options=[
                {'label': 'Pets Allowed', 'value': 'Yes'},
                {'label': 'Pets NOT Allowed', 'value': 'No'},
                {'label': 'Both', 'value': 'Both'}
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
            html.H5("Lease Length"),
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
        id='rental_terms_div'
        )

        return rental_terms_checklist
    
    def create_garage_spaces_slider(self):
        garage_spaces_slider = html.Div([
            html.H5("Garage Spaces"),
            # Create a range slider for # of garage spaces
            dcc.RangeSlider(
            min=0, 
            max=self.df['garage_spaces'].max(), # Dynamically calculate the maximum number of garage spaces
            step=1, 
            value=[0, self.df['garage_spaces'].max()], 
            id='garage_spaces_slider',
            updatemode='mouseup',
            tooltip={
                "placement": "bottom",
                "always_visible": True
            },
            ),
        ],
        style = {
            'margin-bottom' : '10px',
        },
        id = 'garage_div'
        )

        return garage_spaces_slider

    def create_unknown_garage_radio_button(self):
        unknown_garage_radio = html.Div([
        dbc.Alert(
            [
            # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown number of garage spaces?"),
            dcc.RadioItems(
                id='garage_missing_radio',
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
        id = 'unknown_garage_spaces_div'
        )

        return unknown_garage_radio

    def create_rental_price_slider(self):
        rental_price_slider = html.Div([ 
            html.H5("Price (Monthly)"),
            # Create a range slider for rental price
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
        id = 'price_div'
        )

        return rental_price_slider

    def create_year_built_slider(self):
        year_built_slider = html.Div([
            html.H5("Year Built"),
            # Create a range slider for year built
            dcc.RangeSlider(
            min=self.df['YrBuilt'].min(),
            max=self.df['YrBuilt'].max(),
            value=[0, self.df['YrBuilt'].max()],
            id='yrbuilt_slider',
            tooltip={
                "placement": "bottom",
                "always_visible": True
            },
            marks = { # Create custom tick marks
                # The left column should be floats, the right column should be strings
                f"{self.df['YrBuilt'].min()}": f"{self.df['YrBuilt'].min()}", # first mark is oldest house
                float(f"{self.df['YrBuilt'].min()}") + 20: str(float(f"{self.df['YrBuilt'].min()}") + 20), # next mark is oldest house + 20 years
                float(f"{self.df['YrBuilt'].min()}") + 40: str(float(f"{self.df['YrBuilt'].min()}") + 40),
                float(f"{self.df['YrBuilt'].min()}") + 60: str(float(f"{self.df['YrBuilt'].min()}") + 60),
                float(f"{self.df['YrBuilt'].min()}") + 80: str(float(f"{self.df['YrBuilt'].min()}") + 80),
                float(f"{self.df['YrBuilt'].min()}") + 100: str(float(f"{self.df['YrBuilt'].min()}") + 100),
                float(f"{self.df['YrBuilt'].min()}") + 120: str(float(f"{self.df['YrBuilt'].min()}") + 120),
                float(f"{self.df['YrBuilt'].min()}") + 140: str(float(f"{self.df['YrBuilt'].min()}") + 140),
                f"{self.df['YrBuilt'].max()}": str(f"{self.df['YrBuilt'].max()}") # last mark is newest house
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
            # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
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

    def create_furnished_checklist(self):
        furnished_checklist = html.Div([ 
            # Title this section
            html.H5("Furnished/Unfurnished"), 
            # Create a checklist of options for the user
            # https://dash.plotly.com/dash-core-components/checklist
            dcc.Checklist( 
                id = 'furnished_checklist',
                options = [ 
                    {'label': 'Furnished Or Unfurnished', 'value': 'Furnished Or Unfurnished'},
                    {'label': 'Furnished', 'value': 'Furnished'},
                    {'label': 'Negotiable', 'value': 'Negotiable'},
                    {'label': 'Partially', 'value': 'Partially'},
                    {'label': 'Unfurnished', 'value': 'Unfurnished'},
                    {'label': 'Unknown', 'value': 'Unknown'},
                ],
                value=[ # Set the default value
                    'Furnished Or Unfurnished',
                    'Furnished',
                    'Negotiable',
                    'Partially',
                    'Unfurnished',
                    'Unknown',
                ],
                labelStyle = {'display': 'block'},
                # add some spacing in between the checkbox and the label
                # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
                inputStyle = {
                    "margin-right": "5px",
                    "margin-left": "5px"
                },
            ),
        ],
        id = 'furnished_div',
        )

        return furnished_checklist
    
    def create_security_deposit_slider(self):
        security_deposit_slider =  html.Div([
            html.H5("Security Deposit"),
            # Create a range slider for security deposit cost
            dcc.RangeSlider(
            min=self.df['DepositSecurity'].min(), # Dynamically calculate the minimum security deposit
            max=self.df['DepositSecurity'].max(), # Dynamically calculate the maximum security deposit
            value=[self.df['DepositSecurity'].min(), self.df['DepositSecurity'].max()], 
            id='security_deposit_slider',
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
        id = 'security_deposit_slider_div'
        )

        return security_deposit_slider

    def create_unknown_security_deposit_radio_button(self):
        unknown_security_deposit_radio = html.Div([
        dbc.Alert(
            [
            # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown security deposit?"),
            dcc.RadioItems(
                id='security_deposit_missing_radio',
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
        color="info",
        ),
        ],
        id = 'unknown_security_deposit_div',
        )

        return unknown_security_deposit_radio

    def create_pet_deposit_slider(self):
        pet_deposit_slider =  html.Div([
            html.H5("Pet Deposit"),
            # Create a range slider for pet deposit cost
            dcc.RangeSlider(
            min=self.df['DepositPets'].min(), # Dynamically calculate the minimum pet deposit
            max=self.df['DepositPets'].max(), # Dynamically calculate the maximum pet deposit
            value=[self.df['DepositPets'].min(), self.df['DepositPets'].max()], 
            id='pet_deposit_slider',
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
        id = 'pet_deposit_slider_div'
        )

        return pet_deposit_slider
    
    def create_unknown_pet_deposit_radio_button(self):
        unknown_pet_deposit_radio = html.Div([
        dbc.Alert(
            [
            # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown pet deposit?"),
            dcc.RadioItems(
                id='pet_deposit_missing_radio',
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
        color="info",
        ),
        ],
        id = 'unknown_pet_deposit_div',
        )

        return unknown_pet_deposit_radio

    def create_key_deposit_slider(self):
        key_deposit_slider =  html.Div([
            html.H5("Key Deposit"),
            # Create a range slider for key deposit cost
            dcc.RangeSlider(
            min=self.df['DepositKey'].min(), # Dynamically calculate the minimum key deposit
            max=self.df['DepositKey'].max(), # Dynamically calculate the maximum key deposit
            value=[self.df['DepositKey'].min(), self.df['DepositKey'].max()], 
            id='key_deposit_slider',
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
        id = 'key_deposit_slider_div'
        )

        return key_deposit_slider

    def create_unknown_key_deposit_radio_button(self):
        unknown_key_deposit_radio = html.Div([
        dbc.Alert(
            [
            # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown key deposit?"),
            dcc.RadioItems(
                id='key_deposit_missing_radio',
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
        color="info",
        ),
        ],
        id = 'unknown_key_deposit_div',
        )

        return unknown_key_deposit_radio
    
    def create_other_deposit_slider(self):
        other_deposit_slider =  html.Div([
            html.H5("Other Deposit"),
            # Create a range slider for other deposit cost
            dcc.RangeSlider(
            min=self.df['DepositOther'].min(), # Dynamically calculate the minimum other deposit
            max=self.df['DepositOther'].max(), # Dynamically calculate the maximum other deposit
            value=[self.df['DepositOther'].min(), self.df['DepositOther'].max()], 
            id='other_deposit_slider',
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
        id = 'other_deposit_slider_div'
        )

        return other_deposit_slider
    
    def create_unknown_other_deposit_radio_button(self):
        unknown_other_deposit_radio = html.Div([
        dbc.Alert(
            [
            # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown misc/other deposit?"),
            dcc.RadioItems(
                id='other_deposit_missing_radio',
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
        color="info",
        ),
        ],
        id = 'unknown_other_deposit_div',
        )

        return unknown_other_deposit_radio
    
    def create_laundry_checklist(self):
        laundry_checklist = html.Div([
            html.H5("Laundry Features"),
            # Create a checklist for laundry features
            dcc.Checklist(
            id='laundry_checklist',
            options=sorted([{'label': i, 'value': i} for i in self.laundry_categories], key=lambda x: x['label']),
            value=self.laundry_categories,
            labelStyle = {'display': 'block'},
            # add some spacing in between the checkbox and the label
            # https://community.plotly.com/t/styling-radio-buttons-and-checklists-spacing-between-button-checkbox-and-label/15224/4
            inputStyle = {
                "margin-right": "5px",
                "margin-left": "5px"
            },
            ),
        ],
        id = 'laundry_checklist_div'
        )

        return laundry_checklist
    
    def create_listed_date_datepicker(self):
        # Get today's date and set it as the end date for the date picker
        today = date.today()
        # Get the earliest date and convert it to to Pythonic datetime for Dash
        self.df['listed_date'] = pd.to_datetime(self.df['listed_date'], errors='coerce')
        earliest_date = (self.df['listed_date'].min()).to_pydatetime()
        listed_date_datepicker = html.Div([
            html.H5("Listed Date Range"),
            # Create a range slider for the listed date
            dcc.DatePickerRange(
            id='listed_date_datepicker',
            max_date_allowed=today,
            start_date=earliest_date,
            end_date=today
            ),
        ],
        id = 'listed_date_datepicker_div'
        )

        return listed_date_datepicker
    
    def create_listed_date_radio_button(self):
        listed_date_radio = html.Div([
        dbc.Alert(
            [
            # https://dash-bootstrap-components.opensource.faculty.ai/docs/icons/
            html.I(className="bi bi-info-circle-fill me-2"),
            ("Should we include properties with an unknown listed date?"),
            dcc.RadioItems(
                id='listed_date_missing_radio',
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
        color="info",
        ),
        ],
        id = 'unknown_listed_date_div',
        )

        return listed_date_radio
    
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
                self.square_footage_slider,  # Assuming these are already defined in this class
                self.square_footage_radio,
                self.ppsqft_slider,
                self.ppsqft_radio,
                self.garage_spaces_slider,
                self.unknown_garage_radio,
                self.year_built_slider,
                self.unknown_year_built_radio,
                self.rental_terms_checklist,
                self.furnished_checklist,
                self.laundry_checklist,
                self.security_deposit_slider,
                self.unknown_security_deposit_radio,
                self.pet_deposit_slider,
                self.unknown_pet_deposit_radio,
                self.key_deposit_slider,
                self.unknown_key_deposit_radio,
                self.other_deposit_slider,
                self.unknown_other_deposit_radio,
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
                self.listed_date_datepicker,
                self.listed_date_radio,
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