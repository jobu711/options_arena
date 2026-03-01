"""Shared field-validation helpers for Pydantic v2 models.

Centralizes duplicated validation logic so each ``field_validator`` is a one-liner
delegation. Changes to validation logic (e.g. epsilon tolerance, NaN handling)
only need to be made once.
"""

import math


def validate_unit_interval(v: float, field_name: str = "confidence") -> float:
    """Validate a float is finite and within [0.0, 1.0].

    Use for confidence, probability, and agreement-score fields.
    """
    if not math.isfinite(v):
        raise ValueError(f"{field_name} must be finite, got {v}")
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"{field_name} must be in [0, 1], got {v}")
    return v


def validate_non_empty_list(v: list[str], field_name: str = "list") -> list[str]:
    """Validate a list of strings has at least one element."""
    if len(v) < 1:
        raise ValueError(f"{field_name} must have at least 1 item")
    return v
