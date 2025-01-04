from typing import Union
import pandas as pd
    
# Create a class to hold all of the filters for the sale page
class BuyFilters:
    def __init__(self, df):
        self.df = df

    def subtype_checklist_function(self, choice: list[str]) -> pd.Series:
        """
        Filters the DataFrame for properties based on selected property subtypes.
        
        Special handling is provided for 'Unknown' to include properties without a specified subtype.
        
        Args:
        - choice (list[str]): A list of user-selected property subtypes, including a special 'Unknown'
                              option to include properties without a specified subtype.
        
        Returns:
        - pd.Series: A boolean Series indicating which rows of the DataFrame satisfy
                     the filter conditions based on property subtypes.
        """
        # Ensure the choice list is not empty
        if not choice:
            return pd.Series([False] * len(self.df), index=self.df.index)

        # Handle 'Unknown' selection
        if 'Unknown' in choice:
            # Include rows where subtype is NaN OR matches one of the selected choices
            subtype_filter = self.df['subtype'].isnull() | self.df['subtype'].isin(choice)
        else:
            # If 'Unknown' is NOT selected, filter by the selected choices
            subtype_filter = self.df['subtype'].isin(choice)

        return subtype_filter

    def sqft_function(self, include_missing: bool, slider_begin: float, slider_end: float) -> pd.Series:
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
            sqft_choice = self.df['sqft'].isnull() | self.df['sqft'].between(slider_begin, slider_end)
        else:
            # Exclude properties with missing square footage
            sqft_choice = self.df['sqft'].between(slider_begin, slider_end)
        return sqft_choice

    def year_built_function(self, include_missing: bool, slider_begin: int, slider_end: int) -> pd.Series:
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
            yrbuilt_choice = self.df['year_built'].isnull() | self.df['year_built'].between(slider_begin, slider_end)
        else:
            # Exclude properties with missing year built
            yrbuilt_choice = self.df['year_built'].between(slider_begin, slider_end)
        return yrbuilt_choice

    def ppsqft_function(self, include_missing: bool, slider_begin: float, slider_end: float) -> pd.Series:
        """
        Filter the dataframe based on whether properties with missing price per square foot should be included.

        Args:
        - include_missing (bool): Whether properties with missing price per square foot should be included.
        - slider_begin (float): Start value of the price per square foot slider.
        - slider_end (float): End value of the price per square foot slider.

        Returns:
        - pd.Series: Boolean mask indicating which rows of the dataframe satisfy the filter conditions.
        """
        if include_missing:
            # Include properties with missing price per square foot
            ppsqft_choice = self.df['ppsqft'].isnull() | self.df['ppsqft'].between(slider_begin, slider_end)
        else:
            # Exclude properties with missing price per square foot
            ppsqft_choice = self.df['ppsqft'].between(slider_begin, slider_end)
        return ppsqft_choice
    
    def listed_date_function(self, include_missing: bool, start_date: str, end_date: str) -> pd.Series:
        """
        Filters the DataFrame for properties based on the listing date criteria, allowing
        for the inclusion of properties without a listed date.

        This function allows filtering properties based on whether there is a listing date
        specified and whether this date falls within a given range.

        Args:
        - include_missing (bool): Whether to include properties with no listed date.
        - start_date (str): The starting date of the range for the listing date, formatted as 'YYYY-MM-DD'.
        - end_date (str): The ending date of the range for the listing date, formatted as 'YYYY-MM-DD'.

        Returns:
        - pd.Series: A boolean Series indicating which rows of the DataFrame satisfy the
                     filter conditions based on the listing date.
        """
        if include_missing:
            # Include properties with no listed date or within the specified date range
            listed_date_filter = self.df['listed_date'].isnull() | self.df['listed_date'].between(start_date, end_date)
        else:
            # Include properties within the specified date range, implicitly excludes nulls
            listed_date_filter = self.df['listed_date'].between(start_date, end_date)
        return listed_date_filter

    def hoa_fee_function(self, include_missing: bool, slider_begin: float, slider_end: float) -> pd.Series:
        """
        Filters the DataFrame for properties based on HOA fee criteria, with an option
        to include properties without an HOA fee listed.

        Args:
        - include_missing (bool): Indicates whether to include properties with no HOA fee listed.
        - slider_begin (float): The minimum value of the HOA fee range.
        - slider_end (float): The maximum value of the HOA fee range.

        Returns:
        - pd.Series: A boolean Series indicating which rows of the DataFrame satisfy the filter
                     conditions based on HOA fees.
        """
        if include_missing:
            hoa_fee_filter = self.df['hoa_fee'].isnull() | self.df['hoa_fee'].between(slider_begin, slider_end)
        else:
            hoa_fee_filter = self.df['hoa_fee'].between(slider_begin, slider_end)

        return hoa_fee_filter

    def hoa_fee_frequency_function(self, choice: list[str]) -> pd.Series:
        """
        Filters the DataFrame for properties based on selected HOA fee frequency criteria,
        including handling for properties without HOA fees ('N/A').

        Args:
        - choice (list[str]): A list of user-selected HOA fee frequencies, e.g., ['Monthly', 'N/A'].

        Returns:
        - pd.Series: A boolean Series indicating which rows of the DataFrame satisfy the filter
                     conditions based on HOA fee frequency.
        """
        # No selection returns False for all rows
        if not choice:
            return pd.Series([False] * len(self.df), index=self.df.index)

        # Initialize filter to capture no selections
        hoa_fee_frequency_filter = pd.Series([False] * len(self.df), index=self.df.index)

        # Special handling for 'N/A'
        if 'N/A' in choice:
            hoa_fee_frequency_filter |= self.df['hoa_fee_frequency'].isnull()

        # Handling other selections
        for freq in choice:
            if freq != 'N/A':  # Skip 'N/A' since it's already handled
                hoa_fee_frequency_filter |= self.df['hoa_fee_frequency'].str.contains(freq, na=False)

        return hoa_fee_frequency_filter

    def space_rent_function(self, include_missing: bool, slider_begin: float, slider_end: float) -> pd.Series:
        """
        Filters the DataFrame for properties based on space rent criteria, including
        an option to include properties without space rent listed.

        Args:
        - include_missing (bool): Indicates whether to include properties with no space rent listed.
        - slider_begin (float): The minimum value of the space rent range.
        - slider_end (float): The maximum value of the space rent range.

        Returns:
        - pd.Series: A boolean Series indicating which rows of the DataFrame satisfy
                     the filter conditions based on space rent.
        """
        if include_missing:
            return self.df['space_rent'].isnull() | self.df['space_rent'].between(slider_begin, slider_end)
        else:
            return self.df['space_rent'].between(slider_begin, slider_end)

    def pet_policy_function(self, choice: str, subtype_selected: list[str]) -> pd.Series:
        """
        Filters the DataFrame based on pet policy preferences, with special consideration
        for properties classified under the 'MH' subtype. The choice parameter can be a boolean
        (True, False) indicating a preference for properties that allow or do not allow pets, respectively,
        or the string "Both" indicating no preference.

        Args:
        - choice (bool or str): The user's choice regarding pet policy. True for properties that allow pets,
                                False for properties that do not allow pets, and "Both" for all properties
                                regardless of pet policy.
        - subtype_selected (list[str]): A list of user-selected property subtypes.

        Returns:
        - pd.Series: A boolean Series indicating which rows of the DataFrame satisfy the filter
                     conditions based on pet policy and selected subtypes.
        """
        if 'MH' not in subtype_selected or choice == 'Both':
            # If 'MH' is not selected or user is indifferent about pet policy, all rows are valid
            return pd.Series([True] * len(self.df), index=self.df.index)

        # Handling cases when 'MH' is selected with a specific pet policy preference
        is_mh_only = len(subtype_selected) == 1 and 'MH' in subtype_selected
        pets_allowed_column = self.df['pets_allowed'].astype(str)  # Ensure comparison is string-based

        if choice:
            # User wants properties that allow pets
            return (~pets_allowed_column.str.contains('No', na=is_mh_only)) if is_mh_only else pets_allowed_column.notnull()
        else:
            # User does not want properties that allow pets
            return (pets_allowed_column.str.contains('No', na=is_mh_only)) if is_mh_only else pets_allowed_column.isnull()

    def senior_community_function(self, choice: Union[bool, str], subtype_selected: list[str]) -> pd.Series:
        """
        Filters the DataFrame for properties based on the senior community criteria, with special consideration
        for properties classified under the 'MH' subtype. The choice parameter can be a boolean
        indicating a preference for senior community properties or 'Both' indicating no preference.

        Args:
        - choice (bool or str): The user's choice regarding senior community properties. True for properties
                                within a senior community, False for properties not within a senior community,
                                and "Both" for all properties regardless of senior community status.
        - subtype_selected (list[str]): A list of user-selected property subtypes.

        Returns:
        - pd.Series: A boolean Series indicating which rows of the DataFrame satisfy the filter
                     conditions based on senior community status and selected subtypes.
        """
        # If 'MH' is not selected or user is indifferent about senior community, all rows are valid
        if 'MH' not in subtype_selected or choice == 'Both':
            return pd.Series([True] * len(self.df), index=self.df.index)

        # Specific logic for when 'MH' is selected
        senior_community_column = self.df['senior_community'].astype(str)  # Ensure comparison is string-based
        
        if choice is True:
            # User prefers properties within a senior community
            return senior_community_column.str.contains('Y', na=False)
        elif choice is False:
            # User prefers properties not within a senior community
            return senior_community_column.str.contains('N', na=False)
        else:  # Covers the case if somehow an unexpected choice value is passed
            return pd.Series([False] * len(self.df), index=self.df.index)