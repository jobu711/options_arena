"""Macro-economic context models for Options Arena.

Two models for macro data from FRED:
  FredSeriesConfig   -- NamedTuple configuring a single FRED series.
  MacroContext       -- frozen snapshot of 8 FRED economic indicators.

``MacroContext`` follows the same completeness-ratio pattern as ``MarketContext``
in ``analysis.py``. All numeric fields are ``float | None`` — ``None`` means the
series could not be fetched. ``math.isfinite()`` validators reject NaN/Inf.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.enums import FredTransform


class FredSeriesConfig(NamedTuple):
    """Configuration for a single FRED data series.

    Attributes:
        series_id: FRED series identifier (e.g. ``"DGS10"``).
        display_name: Human-readable label for logs and prompts.
        ttl_hours: Cache TTL in hours (24 for daily, 168 for monthly).
        transform: How to convert the raw FRED value. Enum member of
            ``FredTransform``.
    """

    series_id: str
    display_name: str
    ttl_hours: int
    transform: FredTransform


# ---------------------------------------------------------------------------
# Field names on MacroContext, used for completeness_ratio
# ---------------------------------------------------------------------------
_MACRO_FIELDS: tuple[str, ...] = (
    "treasury_10y",
    "treasury_2y",
    "yield_spread_10y2y",
    "fed_funds_rate",
    "vix",
    "cpi_yoy",
    "industrial_production_yoy",
    "unemployment_rate",
)


class MacroContext(BaseModel):
    """Frozen snapshot of macro-economic indicators from FRED.

    All 8 fields are ``float | None`` — ``None`` when the series could not be
    fetched. Validators reject NaN and Inf values via ``math.isfinite()``.

    The ``completeness_ratio()`` method returns the fraction of non-None fields,
    following the same pattern as ``MarketContext.completeness_ratio()``.
    """

    model_config = ConfigDict(frozen=True)

    treasury_10y: float | None = None
    """10-Year Treasury yield as decimal fraction (0.045 = 4.5%)."""

    treasury_2y: float | None = None
    """2-Year Treasury yield as decimal fraction."""

    yield_spread_10y2y: float | None = None
    """10Y-2Y yield spread as decimal fraction (negative = inverted curve)."""

    fed_funds_rate: float | None = None
    """Federal Funds effective rate as decimal fraction."""

    vix: float | None = None
    """CBOE VIX index level (not a percentage, passthrough)."""

    cpi_yoy: float | None = None
    """CPI year-over-year percent change (via FRED ``units=pc1``)."""

    industrial_production_yoy: float | None = None
    """Industrial Production Index year-over-year percent change (via FRED ``units=pc1``)."""

    unemployment_rate: float | None = None
    """Unemployment rate as decimal fraction (0.035 = 3.5%)."""

    @field_validator(*_MACRO_FIELDS, mode="before")
    @classmethod
    def _validate_finite(cls, v: float | None) -> float | None:
        """Reject NaN and Inf on all numeric fields."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    def completeness_ratio(self) -> float:
        """Return the fraction of non-None fields (0.0 to 1.0)."""
        total = len(_MACRO_FIELDS)
        populated = sum(1 for f in _MACRO_FIELDS if getattr(self, f) is not None)
        return populated / total

    @classmethod
    def fallback(cls) -> MacroContext:
        """Create an all-None instance for graceful degradation."""
        return cls()
