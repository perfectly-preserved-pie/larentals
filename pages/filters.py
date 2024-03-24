import pandas as pd

# Create a class to hold all of the filters for the lease page
class LeaseFilters:
    def __init__(self, df):
        self.df = df

    def sqft_radio_button(self, include_missing: bool, slider_begin: float, slider_end: float) -> pd.Series:
        """
        Filter the dataframe based on whether properties with missing square footage should be included.

        Args:
        - include_missing (bool): Whether properties with missing square footage should be included.
        - slider_begin (float): Start value of the square footage slider.
        - slider_end (float): End value of the square footage slider.

        Returns:
        - pd.Series: Boolean mask indicating which rows of the dataframe satisfy the filter conditions.
        """
        if include_missing:
            # Include properties with missing square footage
            sqft_choice = self.df['Sqft'].isnull() | self.df['Sqft'].between(slider_begin, slider_end)
        else:
            # Exclude properties with missing square footage
            sqft_choice = self.df['Sqft'].between(slider_begin, slider_end)
        return sqft_choice
    
    def yrbuilt_radio_button(self, include_missing: bool, slider_begin: int, slider_end: int) -> pd.Series:
        """
        Filter the dataframe based on whether properties with missing year built should be included.

        Args:
        - include_missing (bool): Whether properties with missing year built should be included.
        - slider_begin (int): Start value of the year built slider.
        - slider_end (int): End value of the year built slider.

        Returns:
        - pd.Series: Boolean mask indicating which rows of the dataframe satisfy the filter conditions.
        """
        if include_missing:
            # Include properties with missing year built
            yrbuilt_choice = self.df['YrBuilt'].isnull() | self.df['YrBuilt'].between(slider_begin, slider_end)
        else:
            # Exclude properties with missing year built
            yrbuilt_choice = self.df['YrBuilt'].between(slider_begin, slider_end)
        return yrbuilt_choice
    
    def garage_radio_button(self, include_missing: bool, slider_begin: int, slider_end: int) -> pd.Series:
        """
        Filter the dataframe based on whether properties with missing garage spaces should be included.

        Args:
        - include_missing (bool): Whether properties with missing garage spaces should be included.
        - slider_begin (int): Start value of the garage spaces slider.
        - slider_end (int): End value of the garage spaces slider.

        Returns:
        - pd.Series: Boolean mask indicating which rows of the dataframe satisfy the filter conditions.
        """
        if include_missing:
            # Include properties with missing garage spaces
            garage_choice = self.df['garage_spaces'].isnull() | self.df['garage_spaces'].between(slider_begin, slider_end)
        else:
            # Exclude properties with missing garage spaces
            garage_choice = self.df['garage_spaces'].between(slider_begin, slider_end)
        return garage_choice
    
    # Create a function to return a dataframe filter for missing ppqsft
    def ppsqft_radio_button(self, boolean, slider_begin, slider_end):
        if boolean == 'True': # If the user says "yes, I want properties without a garage space listed"
            # Then we want nulls to be included in the final dataframe 
            ppsqft_choice = self.df['ppsqft'].isnull() | self.df['ppsqft'].between(slider_begin, slider_end)
        elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
            ppsqft_choice = self.df['ppsqft'].between(slider_begin, slider_end)
        return (ppsqft_choice)

    # Create a function to return a dataframe filter for pet policy
    def pets_radio_button(self, choice):
        if choice == 'Yes': # If the user says "yes, I ONLY want properties that allow pets"
            # Then we want every row where the pet policy is NOT "No" or "No, Size Limit"
            pets_radio_choice = ~self.df['PetsAllowed'].isin(['No', 'No, Size Limit'])
        elif choice == 'No': # If the user says "No, I don't want properties where pets are allowed"
            pets_radio_choice = self.df['PetsAllowed'].isin(['No', 'No, Size Limit'])
        elif choice == 'Both': # If the user says "I don't care, I want both kinds of properties"
            pets_radio_choice = self.df['PetsAllowed']
        return (pets_radio_choice)

    # Create a function to return a dataframe filter for furnished dwellings
    def furnished_checklist_function(self, choice):
        # Presort the list first for faster performance
        choice.sort()
        if 'Unknown' in choice: # If Unknown is selected, return all rows with NaN OR the selected choices
            furnished_checklist_filter = (self.df['Furnished'].isnull()) | (self.df['Furnished'].isin(choice))
        elif 'Unknown' not in choice: # If Unknown is NOT selected, return the selected choices only, which implies .notnull()
            furnished_checklist_filter = self.df['Furnished'].isin(choice)
        return (furnished_checklist_filter)

    ## Create functions to return a dataframe filter for the various types of deposits
    # Security
    def security_deposit_function(self, boolean, slider_begin, slider_end):
        if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
            # Then we want nulls to be included in the final dataframe 
            security_deposit_filter = self.df['DepositSecurity'].isnull() | (self.df['DepositSecurity'].between(slider_begin, slider_end))
        elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
            security_deposit_filter = self.df['DepositSecurity'].between(slider_begin, slider_end)
        return (security_deposit_filter)

    # Pets
    def pet_deposit_function(self, boolean, slider_begin, slider_end):
        if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
            # Then we want nulls to be included in the final dataframe 
            pet_deposit_filter = self.df['DepositPets'].isnull() | (self.df['DepositPets'].between(slider_begin, slider_end))
        elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
            pet_deposit_filter = self.df['DepositPets'].between(slider_begin, slider_end)
        return (pet_deposit_filter)

    # Keys
    def key_deposit_function(self, boolean, slider_begin, slider_end):
        if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
            # Then we want nulls to be included in the final dataframe 
            key_deposit_filter = self.df['DepositKey'].isnull() | (self.df['DepositKey'].between(slider_begin, slider_end))
        elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
            key_deposit_filter = self.df['DepositKey'].between(slider_begin, slider_end)
        return (key_deposit_filter)

    # Other
    def other_deposit_function(self, boolean, slider_begin, slider_end):
        if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
            # Then we want nulls to be included in the final dataframe 
            other_deposit_filter = self.df['DepositOther'].isnull() | (self.df['DepositOther'].between(slider_begin, slider_end))
        elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
            other_deposit_filter = self.df['DepositOther'].between(slider_begin, slider_end)
        return (other_deposit_filter)

    # Listed Date
    def listed_date_function(self, boolean, start_date, end_date):
        if boolean == 'True': # If the user says "yes, I want properties without a security deposit listed"
            # Then we want nulls to be included in the final dataframe 
            listed_date_filter = (self.df['listed_date'].isnull()) | (self.df['listed_date'].between(start_date, end_date))
        elif boolean == 'False': # If the user says "No nulls", return the same dataframe as the slider would. The slider (by definition: a range between non-null integers) implies .notnull()
            listed_date_filter = self.df['listed_date'].between(start_date, end_date)
        return (listed_date_filter)

    # Terms
    def terms_function(self, choice):
        # Presort the list first for faster performance
        choice.sort()
        choice_regex = '|'.join(choice)  # Create a regex from choice
        if 'Unknown' in choice: 
            # If Unknown is selected, return all rows with NaN OR the selected choices
            terms_filter = self.df['Terms'].isnull() | self.df['Terms'].str.contains(choice_regex, na=False)
        elif 'Unknown' not in choice: 
            # If Unknown is NOT selected, return the selected choices only, which implies .notnull()
            terms_filter = self.df['Terms'].str.contains(choice_regex, na=False)
        # If there is no choice, return an empty dataframe
        if len(choice) == 0:
            terms_filter = pd.DataFrame()
        return (terms_filter)

    
    # We need to create a function to return a dataframe filter for laundry features
    # We need to account for every possible combination of choices
    def laundry_checklist_function(self, choice):
        # Create a list of options for the first drop-down menu
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
        # Return an empty dataframe if the choice list is empty
        if len(choice) == 0:
            return pd.DataFrame()
        # If the user selects only 'Other', return the properties that don't have any of the strings in the laundry_categories list
        if len(choice) == 1 and choice[0] == 'Other':
            laundry_features_filter = ~self.df['LaundryFeatures'].astype(str).apply(lambda x: any([cat in x for cat in laundry_categories]))
            return laundry_features_filter
        # First, create a filter for the first choice
        laundry_features_filter = self.df['LaundryFeatures'].str.contains(str(choice[0]))
        # Then, loop through the rest of the choices
        for i in range(1, len(choice)):
            # If the user selects "Other", we want to return all the properties that don't have any the strings in the laundry_categories list
            if choice[i] == 'Other':
                other = ~self.df['LaundryFeatures'].astype(str).apply(lambda x: any([cat in x for cat in laundry_categories]))
                # Then, we want to add the other filter to the laundry_features_filter
                laundry_features_filter = laundry_features_filter | other
            # If the user doesn't select "Other", we want to return all the properties that have the first choice, the second choice, etc.
            elif choice[i] != 'Other':
                laundry_features_filter = laundry_features_filter | self.df['LaundryFeatures'].str.contains(str(choice[i]))
        return (laundry_features_filter)

    # Subtype
    def subtype_checklist_function(self, choice):
        # Presort the list first for faster performance
        choice.sort()
        if 'Unknown' in choice: # If Unknown is selected, return all rows with NaN OR the selected choices
            subtype_filter = self.df['subtype'].isnull() | self.df['subtype'].isin(choice)
        elif 'Unknown' not in choice: # If Unknown is NOT selected, return the selected choices only, which implies .notnull()
            subtype_filter = self.df['subtype'].isin(choice)
        return (subtype_filter)
    
# Create a class to hold all of the filters for the sale page
class BuyFilters:
    def __init__(self, df):
        self.df = df

    def subtype_checklist_function(self, choice):
        # Presort the list first for faster performance
        choice.sort()
        if 'Unknown' in choice: # If Unknown is selected, return all rows with NaN OR the selected choices
            subtype_filter = self.df['subtype'].isnull() | self.df['subtype'].isin(choice)
        elif 'Unknown' not in choice: # If Unknown is NOT selected, return the selected choices only, which implies .notnull()
            subtype_filter = self.df['subtype'].isin(choice)
        return (subtype_filter)

    # Create a function to return a dataframe filter based on if the user provides a Yes/No to the "should we include properties with missing sqft?" question
    def sqft_function(self, boolean, slider_begin, slider_end):
        if boolean == 'True':
            sqft_choice = self.df['Sqft'].isnull() | self.df['Sqft'].between(slider_begin, slider_end)
        elif boolean == 'False':
            sqft_choice = self.df['Sqft'].between(slider_begin, slider_end)

        return (sqft_choice)

    # Create a function to return a dataframe filter for year built
    def year_built_function(self, boolean, slider_begin, slider_end):
        if boolean == 'True':
            year_built_choice = self.df['year_built'].isnull() | self.df['year_built'].between(slider_begin, slider_end)
        elif boolean == 'False':
            year_built_choice = self.df['year_built'].between(slider_begin, slider_end)

        return (year_built_choice)

    # Create a function to return a dataframe filter for missing ppqsft
    def ppsqft_function(self, boolean, slider_begin, slider_end):
        if boolean == 'True':
            ppsqft_choice = self.df['ppsqft'].isnull() | self.df['ppsqft'].between(slider_begin, slider_end)
        elif boolean == 'False':
            ppsqft_choice = self.df['ppsqft'].between(slider_begin, slider_end)

        return (ppsqft_choice)
    
    def listed_date_function(self, boolean, start_date, end_date):
        if boolean == 'True':
            listed_date_filter = (self.df['listed_date'].isnull()) | (self.df['listed_date'].between(start_date, end_date))
        elif boolean == 'False':
            listed_date_filter = self.df['listed_date'].between(start_date, end_date)

        return (listed_date_filter)

    def hoa_fee_function(self, boolean, slider_begin, slider_end):
        if boolean == 'True':
            hoa_fee_filter = self.df['hoa_fee'].isnull() | (self.df.sort_values(by='hoa_fee')['hoa_fee'].between(slider_begin, slider_end))
        elif boolean == 'False':
            hoa_fee_filter = self.df.sort_values(by='hoa_fee')['hoa_fee'].between(slider_begin, slider_end)

        return (hoa_fee_filter)

    def hoa_fee_frequency_function(self, choice):
        if 'N/A' in choice and len(choice) == 1:
            hoa_fee_frequency_filter = self.df['hoa_fee_frequency'].isnull()
        elif 'Monthly' in choice and len(choice) == 1:
            hoa_fee_frequency_filter = self.df['hoa_fee_frequency'].str.contains('Monthly')
        elif len(choice) > 1:
            hoa_fee_frequency_filter = self.df['hoa_fee_frequency'].isnull() | self.df['hoa_fee_frequency'].str.contains('Monthly')

        return (hoa_fee_frequency_filter)

    def space_rent_function(self, boolean, slider_begin, slider_end):
        if boolean == 'True':
            space_rent_filter = self.df['space_rent'].isnull() | (self.df.sort_values(by='space_rent')['space_rent'].between(slider_begin, slider_end))
        elif boolean == 'False':
            space_rent_filter = self.df.sort_values(by='space_rent')['space_rent'].between(slider_begin, slider_end)

        return (space_rent_filter)

    def pet_policy_function(self, choice, subtype_selected):
        # If MH isn't selected, return every row where the pet policy is Yes, No, or null since it doesn't matter
        if 'MH' not in subtype_selected:
            pets_radio_choice = self.df['pets_allowed'].notnull() | self.df['pets_allowed'].isnull()
        # If MH is the only subtype selected and they want pets then we want every row where the pet policy DOES NOT contain "No"
        elif 'MH' in subtype_selected and choice == 'True' and len(subtype_selected) == 1:
            pets_radio_choice = ~self.df['pets_allowed'].str.contains('No')
        # If MH is the only subtype selected and they DON'T want pets then we want every row where the pet policy DOES NOT contain "No"
        elif 'MH' in subtype_selected and choice == 'False' and len(subtype_selected) == 1:
            pets_radio_choice = self.df['pets_allowed'].str.contains('No')
        # If the user says "I don't care, I want both kinds of properties"
        # Return every row where the pet policy is Yes or No
        elif 'MH' in subtype_selected and choice == 'Both' and len(subtype_selected) == 1: 
            pets_radio_choice = (~self.df['pets_allowed'].str.contains('No')) | (self.df['pets_allowed'].str.contains('No'))
        # If more than one subtype is selected and MH is one of them AND they want pets, return every row where the pet policy DOES contain "Yes" or is null
        elif 'MH' in subtype_selected and choice == 'True' and len(subtype_selected) > 1:
            pets_radio_choice = (~self.df['pets_allowed'].str.contains('No')) | self.df['pets_allowed'].isnull()
        # If more than one subtype is selected and MH is one of them AND they DON'T want pets, return every row where the pet policy DOES contain "No" or is null
        elif 'MH' in subtype_selected and choice == 'False' and len(subtype_selected) > 1:
            pets_radio_choice = (self.df['pets_allowed'].str.contains('No')) | self.df['pets_allowed'].isnull()
        # If more than one subtype is selected and MH is one of them AND they choose Both, return every row that is null OR non-null
        elif 'MH' in subtype_selected and choice == 'Both' and len(subtype_selected) > 1:
            pets_radio_choice = self.df['pets_allowed'].isnull() | self.df['pets_allowed'].notnull()
        return (pets_radio_choice)

    def senior_community_function(self, choice, subtype_selected):
        # If MH isn't selected, return every row where the pet policy is Yes, No, or null since it doesn't matter
        if 'MH' not in subtype_selected:
            senior_community_choice = self.df['senior_community'].notnull() | self.df['senior_community'].isnull()
        # If MH is the only subtype selected and they want a senior community then we want every row where the senior community DOES contain "Y"
        elif 'MH' in subtype_selected and choice == 'True' and len(subtype_selected) == 1:
            senior_community_choice = self.df['senior_community'].str.contains('Y')
        # If MH is the only subtype selected and they DON'T want a senior community then we want every row where the senior community DOES contain "N"
        elif 'MH' in subtype_selected and choice == 'False' and len(subtype_selected) == 1:
            senior_community_choice = self.df['senior_community'].str.contains('N')
        # If the user says "I don't care, I want both kinds of properties"
        # Return every row where the pet policy is Yes or No
        elif 'MH' in subtype_selected and choice == 'Both' and len(subtype_selected) == 1: 
            senior_community_choice = (self.df['senior_community'].str.contains('N')) | (self.df['senior_community'].str.contains('Y')) 
        # If more than one subtype is selected and MH is one of them AND they want a senior community, return every row where the senior community DOES contain "Y" or is null
        elif 'MH' in subtype_selected and choice == 'True' and len(subtype_selected) > 1:
            senior_community_choice = (self.df['senior_community'].str.contains('Y')) | self.df['pets_allowed'].isnull()
        # If more than one subtype is selected and MH is one of them AND they DON'T want a senior community, return every row where the senior community DOES contain "N" or is null
        elif 'MH' in subtype_selected and choice == 'False' and len(subtype_selected) > 1:
            senior_community_choice = (self.df['senior_community'].str.contains('N')) | self.df['pets_allowed'].isnull()
        # If more than one subtype is selected and MH is one of them AND they choose Both, return every row that is null OR non-null
        elif 'MH' in subtype_selected and choice == 'Both' and len(subtype_selected) > 1:
            senior_community_choice = self.df['senior_community'].isnull() | self.df['senior_community'].notnull()
        return (senior_community_choice)