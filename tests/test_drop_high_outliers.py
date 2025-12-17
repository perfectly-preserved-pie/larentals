import os
import sys

import pandas as pd
from loguru import logger

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from functions.dataframe_utils import drop_high_outliers


def test_drops_numeric_like_values_and_logs_reason():
    df = pd.DataFrame(
        {
            "a": [1, 1, 1000, 2],
            "b": ["5", "5", "5000", "6"],
            "mls_number": ["x1", "x2", "x3", "x4"],
        }
    )

    messages = []
    sink_id = logger.add(lambda msg: messages.append(str(msg)), level="INFO")
    try:
        cleaned = drop_high_outliers(df, iqr_multiplier=1.5)
    finally:
        logger.remove(sink_id)

    assert set(cleaned["mls_number"]) == {"x1", "x2", "x4"}
    log_text = "\n".join(messages)
    assert "Dropping row 'x3'" in log_text
    assert "IQR threshold" in log_text


def test_absolute_cap_on_numeric_like_column_logs_reason():
    df = pd.DataFrame(
        {
            "c": ["1", "2", "9"],
            "mls_number": ["y1", "y2", "y3"],
        }
    )

    messages = []
    sink_id = logger.add(lambda msg: messages.append(str(msg)), level="INFO")
    try:
        cleaned = drop_high_outliers(df, cols=["c"], absolute_caps={"c": 5})
    finally:
        logger.remove(sink_id)

    assert set(cleaned["mls_number"]) == {"y1", "y2"}
    log_text = "\n".join(messages)
    assert "absolute cap 5" in log_text
    assert "y3" in log_text
