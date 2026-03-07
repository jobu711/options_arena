"""Score history models for Options Arena.

Two models for score history tracking:
  HistoryPoint    -- a single scan result for a ticker (frozen).
  TrendingTicker  -- a ticker with consistent direction over multiple scans (frozen).
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.enums import ScanPreset, SignalDirection


class HistoryPoint(BaseModel):
    """A single scan-score data point for a ticker.

    Frozen (immutable after construction) -- represents a persisted snapshot.
    ``scan_date`` must be UTC.  ``composite_score`` must be finite.
    """

    model_config = ConfigDict(frozen=True)

    scan_id: int
    scan_date: datetime
    composite_score: float
    direction: SignalDirection
    preset: ScanPreset

    @field_validator("scan_date")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure scan_date is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("scan_date must be UTC")
        return v

    @field_validator("composite_score")
    @classmethod
    def validate_composite_score(cls, v: float) -> float:
        """Ensure composite_score is finite and within [0, 100]."""
        if not math.isfinite(v):
            raise ValueError(f"composite_score must be finite, got {v}")
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"composite_score must be in [0, 100], got {v}")
        return v


class TrendingTicker(BaseModel):
    """A ticker trending in one direction over multiple consecutive scans.

    Frozen (immutable after construction) -- represents a computed snapshot.
    ``latest_score`` and ``score_change`` must be finite.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    direction: SignalDirection
    consecutive_scans: int
    latest_score: float
    score_change: float

    @field_validator("consecutive_scans")
    @classmethod
    def validate_consecutive_scans(cls, v: int) -> int:
        """Ensure consecutive_scans is at least 1."""
        if v < 1:
            raise ValueError(f"consecutive_scans must be >= 1, got {v}")
        return v

    @field_validator("latest_score", "score_change")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        """Ensure numeric fields are finite."""
        if not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v
