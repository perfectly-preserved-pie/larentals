from loguru import logger
from typing import Any
import numpy as np
import pandas as pd
import sys

logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

def format_value_lease(value: Any, template: str = "{}") -> str:
  """
  Formats the given value based on its type and value.
  
  Parameters:
  value (Any): The value to be formatted.
  template (str): A format template for the value.
  
  Returns:
  str: The formatted value as a string.
  """
  try:
    if pd.isna(value):
      return 'Unknown'
    elif isinstance(value, (float, int, np.float64, np.int64)):
      formatted_value = template.format(value)
      return formatted_value  # Apply the format only if value is float or int
    else:
      return str(value)
  except Exception as e:
    logger.error(f"An exception occurred in format_value_lease: {e}")  # Debug statement
    raise

def format_value_buy(value: Any, template: str = "{}") -> str:
  """
  Formats the given value based on its type and value.
  
  Parameters:
  value (Any): The value to be formatted.
  template (str): A format template for the value.
  
  Returns:
  str: The formatted value as a string.
  """
  try:
    if pd.isna(value) or value is pd.NaT:
      return 'N/A'
    elif isinstance(value, (float, int)) or pd.api.types.is_integer_dtype(type(value)):
      return template.format(value)  # Apply the format only if value is float or int
    else:
      return str(value)
  except Exception as e:
    logger.error(f"An exception occurred in format_value_buy: {e}")
    raise