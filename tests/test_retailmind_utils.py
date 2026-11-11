import pandas as pd

from retailmind.utils import to_numeric_loose


def test_to_numeric_loose_handles_currency_formats() -> None:
    values = pd.Series(
        [
            "₹1,31,869.17",
            "Rs. 1,200",
            "INR 4500",
            "$1,200.00",
            "(1,200)",
            "(₹450)",
            "₹1 234.50",
            "10%",
            "not a number",
            None,
        ]
    )

    parsed = to_numeric_loose(values)

    assert parsed.iloc[0] == 131869.17
    assert parsed.iloc[1] == 1200
    assert parsed.iloc[2] == 4500
    assert parsed.iloc[3] == 1200
    assert parsed.iloc[4] == -1200
    assert parsed.iloc[5] == -450
    assert parsed.iloc[6] == 1234.5

    assert parsed.iloc[7] == 10
    assert pd.isna(parsed.iloc[8])
    assert pd.isna(parsed.iloc[9])


def test_to_numeric_loose_leaves_plain_numeric_values_untouched() -> None:
    parsed = to_numeric_loose(pd.Series([10, 20.5, None]))

    assert parsed.iloc[0] == 10
    assert parsed.iloc[1] == 20.5
    assert pd.isna(parsed.iloc[2])
