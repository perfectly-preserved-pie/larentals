from dash import html, dcc
import dash_bootstrap_components as dbc
import pandas as pd

# Create a class to hold all of the Dash components for the Lease page
class LeaseComponents:
    # Class Variable
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