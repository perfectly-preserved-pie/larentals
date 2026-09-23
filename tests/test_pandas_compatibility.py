import pandas as pd
import pyarrow


def test_pandas_3_uses_installed_pyarrow_for_default_strings() -> None:
    """Verify that pandas 3 uses installed pyarrow for default strings.

    Pandas 3 string defaults rely on PyArrow, so the configured runtime dependency must be importable.

    Returns:
        None.
    """
    series = pd.Series(["ready", None])

    assert pyarrow.__version__
    assert isinstance(series.dtype, pd.StringDtype)
    assert series.dtype.storage == "pyarrow"
    assert type(series.array).__name__ == "ArrowStringArray"
    assert pd.isna(series.iloc[1])
