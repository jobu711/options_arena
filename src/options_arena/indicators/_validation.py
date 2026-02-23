"""Shared validation helpers for indicator functions."""

import pandas as pd


def validate_aligned(*series: pd.Series) -> None:
    """Validate that all input Series have the same length.

    Raises:
        ValueError: If any Series have mismatched lengths.
    """
    if len(series) < 2:
        return
    first_len = len(series[0])
    for i, s in enumerate(series[1:], start=1):
        if len(s) != first_len:
            msg = (
                f"All input Series must have equal length, "
                f"got {first_len} and {len(s)} (at position {i})"
            )
            raise ValueError(msg)
