from typing import Any, Optional
import pandas as pd

def format_value_lease(value: Any, template: str = "{}") -> str:
  """
  Formats the given value based on its type and value.
  
  Parameters:
  value (Any): The value to be formatted.
  template (str): A format template for the value.
  
  Returns:
  str: The formatted value as a string.
  """
  if pd.isna(value):
    return 'Unknown'
  else:
    return template.format(value)
  
def format_value_buy(value: Any, fmt: Optional[str] = None) -> str:
  """
  Formats the given value based on its type and value.
  
  Parameters:
  value (Any): The value to be formatted.
  fmt (Optional[str]): Optional format string.
  
  Returns:
  str: The formatted value as a string.
  """
  if pd.isna(value):
    return 'Unknown'
  elif isinstance(value, float) or isinstance(value, int):
    return f"{value:,.0f}" if fmt is None else fmt.format(value)
  else:
    return str(value)

def lease_popup_html(dataframe: pd.DataFrame, row: pd.Series) -> str:
  """
  Generates HTML code for the popup based on the given DataFrame row.
  
  Parameters:
  dataframe (pd.DataFrame): The DataFrame containing all the data.
  row (pd.Series): The row for which the popup HTML is to be generated.
  
  Returns:
  str: The HTML code for the popup.
  """
  i = row.Index
  df = dataframe.loc[i]

  # Prepare all the fields for the HTML snippet
  context = {key: format_value_lease(df[key]) for key in df.keys()}

  # Additional formatting for special fields
  context['lc_price'] = format_value_lease(df['list_price'], "${:,.0f}")
  context['listed_date'] = format_value_lease(pd.to_datetime(df['listed_date']).date())
  context['price_per_sqft'] = format_value_lease(df['ppsqft'], "${:,.2f}")
  context['security_deposit'] = format_value_lease(df['DepositSecurity'], "${:,.0f}")
  context['square_ft'] = format_value_lease(df['Sqft'], "{:,.0f} sq. ft")
  context['full_address'] = f"{context['short_address']} {context['PostalCode']}"

  # Handle the MLS photo
  if context['mls_photo'] == 'Unknown':
    mls_photo_html_block = "<img src='' referrerPolicy='noreferrer' style='display:block;width:100%;margin-left:auto;margin-right:auto' id='mls_photo_div'>"
  else:
    mls_photo_html_block = f"""
    <a href="{context['mls_number_hyperlink']}" referrerPolicy="noreferrer" target="_blank">
    <img src="{context['mls_photo']}" referrerPolicy="noreferrer" style="display:block;width:100%;margin-left:auto;margin-right:auto" id="mls_photo_div">
    </a>
    """

  # Handle the MLS number hyperlink
  if context['mls_number_hyperlink'] == 'Unknown':
    listing_url_block = f"""
      <tr>
        <td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id' target='_blank'>Listing ID (MLS#)</a></td>
        <td>{context['mls_number']}</td>
      </tr>
    """
  else:
    listing_url_block = f"""
      <tr>
        <td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id' target='_blank'>Listing ID (MLS#)</a></td>
        <td><a href='{context['mls_number_hyperlink']}' referrerPolicy='noreferrer' target='_blank'>{context['mls_number']}</a></td>
      </tr>
    """

  # Return the HTML snippet
  return f"""<div>{mls_photo_html_block}</div>
  <table id='popup_html_table'>
    <tbody id='popup_html_table_body'>
      <tr id='listed_date'><td>Listed Date</td><td>{context['listed_date']}</td></tr>
      <tr id='street_address'><td>Street Address</td><td>{context['full_address']}</td></tr>
      {listing_url_block}
      <tr id='list_office_phone'><td>List Office Phone</td><td><a href='tel:{context['phone']}'>{context['phone']}</a></td></tr>
      <tr id='rental_price'><td>Rental Price</td><td>{context['lc_price']}</td></tr>
      <tr id='security_deposit'><td>Security Deposit</td><td>{context['security_deposit']}</td></tr>
      <tr id='pet_deposit'><td>Pet Deposit</td><td>{context['pet_deposit']}</td></tr>
      <tr id='key_deposit'><td>Key Deposit</td><td>{context['key_deposit']}</td></tr>
      <tr id='other_deposit'><td>Other Deposit</td><td>{context['other_deposit']}</td></tr>
      <tr id='square_feet'><td>Square Feet</td><td>{context['square_ft']}</td></tr>
      <tr id='price_per_sqft'><td>Price Per Square Foot</td><td>{context['price_per_sqft']}</td></tr>
      <tr id='bedrooms_bathrooms'><td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#bedroomsbathrooms' target='_blank'>Bedrooms/Bathrooms</a></td><td>{context['brba']}</td></tr>
      <tr id='garage_spaces'><td>Garage Spaces</td><td>{context['garage']}</td></tr>
      <tr id='pets_allowed'><td>Pets Allowed?</td><td>{context['pets']}</td></tr>
      <tr id='furnished'><td>Furnished?</td><td>{context['furnished']}</td></tr>
      <tr id='laundry_features'><td>Laundry Features</td><td>{context['laundry']}</td></tr>
      <tr id='year_built'><td>Year Built</td><td>{context['year']}</td></tr>
      <tr id='rental_terms'><td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#rental-terms' target='_blank'>Rental Terms</a></td><td>{context['terms']}</td></tr>
      <tr id='subtype'><td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#physical-sub-type' target='_blank'>Physical Sub Type</a></td><td>{context['sub_type']}</td></tr>
    </tbody>
  </table>"""


def buy_popup_html(dataframe: pd.DataFrame, row: pd.Series) -> str:
  """
  Generates HTML code for the popup based on the given DataFrame row.
  
  Parameters:
  dataframe (pd.DataFrame): The DataFrame containing all the data.
  row (pd.Series): The row for which the popup HTML is to be generated.
  
  Returns:
  str: The HTML code for the popup.
  """
  i = row.Index
  df = dataframe.loc[i]
  # Prepare all the fields for the HTML snippet
  context = {
    'brba': format_value_buy(df['Br/Ba']),
    'full_address': f"{format_value_buy(df['short_address'])} {format_value_buy(df['PostalCode'])}",
    'pets': format_value_buy(df['pets_allowed']),
    'senior_community': format_value_buy(df['senior_community']),
    'subtype': format_value_buy(df['subtype']),
    'year': format_value_buy(df['year_built']),
    'hoa_fee': format_value_buy(df['hoa_fee'], "${:,.2f}"),
    'hoa_fee_frequency': format_value_buy(df['hoa_fee_frequency']),
    'space_rent': format_value_buy(df['space_rent'], "${:,.2f}"),
    'square_ft': format_value_buy(df['Sqft'], "{:,.0f} sq. ft"),
    'listed_date': format_value_buy(pd.to_datetime(df['listed_date']).date()),
    'mls_number': format_value_buy(df['mls_number']),
    'mls_number_hyperlink': format_value_buy(df['listing_url']),
    'mls_photo': format_value_buy(df['mls_photo']),
    'lc_price': format_value_buy(df['list_price'], "${:,.0f}"),
    'park_name': format_value_buy(df['park_name']),
    'price_per_sqft': format_value_buy(df['ppsqft'], "${:,.2f}"),
  }
  
  # Handle the MLS photo
  if context['mls_photo'] == 'Unknown':
    mls_photo_html_block = "<img src='' referrerPolicy='noreferrer' style='display:block;width:100%;margin-left:auto;margin-right:auto' id='mls_photo_div'>"
  else:
    mls_photo_html_block = f"""
    <a href="{context['mls_number_hyperlink']}" referrerPolicy="noreferrer" target="_blank">
    <img src="{context['mls_photo']}" referrerPolicy="noreferrer" style="display:block;width:100%;margin-left:auto;margin-right:auto" id="mls_photo_div">
    </a>
    """
      
  # Handle the MLS number hyperlink
  if context['mls_number_hyperlink'] == 'Unknown':
    listing_url_block = f"""
      <tr>
        <td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id' target='_blank'>Listing ID (MLS#)</a></td>
        <td>{context['mls_number']}</td>
      </tr>
    """
  else:
    listing_url_block = f"""
      <tr>
        <td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#listing-id' target='_blank'>Listing ID (MLS#)</a></td>
        <td><a href='{context['mls_number_hyperlink']}' referrerPolicy='noreferrer' target='_blank'>{context['mls_number']}</a></td>
      </tr>
    """
  
  # Generate the HTML snippet
  return f"""<div>{mls_photo_html_block}</div>
  <table id='popup_html_table'>
    <tbody id='popup_html_table_body'>
      <tr id='listed_date'><td>Listed Date</td><td>{context['listed_date']}</td></tr>
      <tr id='street_address'><td>Street Address</td><td>{context['full_address']}</td></tr>
      <tr id='park_name'><td>Park Name</td><td>{context['park_name']}</td></tr>
      {listing_url_block}
      <tr id='list_price'><td>List Price</td><td>{context['lc_price']}</td></tr>
      <tr id='hoa_fee'><td>HOA Fee</td><td>{context['hoa_fee']}</td></tr>
      <tr id='hoa_fee_frequency'><td>HOA Fee Frequency</td><td>{context['hoa_fee_frequency']}</td></tr>
      <tr id='square_feet'><td>Square Feet</td><td>{context['square_ft']}</td></tr>
      <tr id='space_rent'><td>Space Rent</td><td>{context['space_rent']}</td></tr>
      <tr id='price_per_sqft'><td>Price Per Square Foot</td><td>{context['price_per_sqft']}</td></tr>
      <tr id='bedrooms_bathrooms'><td><a href='https://github.com/perfectly-preserved-pie/larentals/wiki#bedroomsbathrooms' target='_blank'>Bedrooms/Bathrooms</a></td><td>{context['brba']}</td></tr>
      <tr id='year_built'><td>Year Built</td><td>{context['year']}</td></tr>
      <tr id='pets_allowed'><td>Pets Allowed?</td><td>{context['pets']}</td></tr>
      <tr id='senior_community'><td>Senior Community</td><td>{context['senior_community']}</td></tr>
      <tr id='subtype'><td>Sub Type</td><td>{context['subtype']}</td></tr>
    </tbody>
  </table>"""