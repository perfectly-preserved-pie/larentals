from loguru import logger
from typing import Any
import numpy as np
import pandas as pd
import sys
from string import Formatter

logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

def _format_template_value(value: Any, template: str | None = None) -> str:
  if template is None:
    return f"{value}"

  formatted_parts: list[str] = []
  field_count = 0
  for literal_text, field_name, format_spec, conversion in Formatter().parse(template):
    formatted_parts.append(literal_text)
    if field_name is None:
      continue

    field_count += 1
    if field_name not in ("", "0"):
      raise ValueError("format template must use one positional replacement field")
    if field_count > 1:
      raise ValueError("format template must use only one replacement field")

    if conversion == "r":
      formatted_parts.append(f"{value!r:{format_spec}}")
    elif conversion == "s":
      formatted_parts.append(f"{value!s:{format_spec}}")
    elif conversion == "a":
      formatted_parts.append(f"{value!a:{format_spec}}")
    elif conversion is None:
      formatted_parts.append(f"{value:{format_spec}}")
    else:
      raise ValueError(f"unsupported format conversion: {conversion}")

  if field_count == 0:
    return template
  return "".join(formatted_parts)

def format_value_lease(value: Any, template: str | None = None) -> str:
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
      formatted_value = _format_template_value(value, template)
      return formatted_value  # Apply the format only if value is float or int
    else:
      return str(value)
  except Exception as e:
    logger.error(f"An exception occurred in format_value_lease: {e}")  # Debug statement
    raise

def format_value_buy(value: Any, template: str | None = None) -> str:
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
      return _format_template_value(value, template)  # Apply the format only if value is float or int
    else:
      return str(value)
  except Exception as e:
    logger.error(f"An exception occurred in format_value_buy: {e}")
    raise
