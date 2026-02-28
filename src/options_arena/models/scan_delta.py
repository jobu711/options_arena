"""Scan delta models for Options Arena.

Two models for comparing scan results:
  TickerDelta -- score change for a single ticker between two scans (frozen).
  ScanDiff    -- full diff between two scans: added, removed, movers (frozen).

These are computed at the API layer (not persisted) from two calls to
``repository.get_scores_for_scan()``.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, field_validator


class TickerDelta(BaseModel):
    """Score change for a single ticker between two scans.

    Frozen (immutable after construction) -- represents a computed snapshot.
    ``current_score``, ``previous_score``, and ``score_change`` must all be finite.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    current_score: float
    previous_score: float
    score_change: float
    current_direction: str
    previous_direction: str
    is_new: bool

    @field_validator("current_score", "previous_score", "score_change")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        """Ensure numeric fields are finite (reject NaN and Inf)."""
        if not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v


class ScanDiff(BaseModel):
    """Full diff between two scans.

    Frozen (immutable after construction) -- represents a computed snapshot.
    ``movers`` is sorted by ``abs(score_change)`` descending.
    ``added`` contains tickers in the current scan but not the base.
    ``removed`` contains tickers in the base scan but not the current.
    """

    model_config = ConfigDict(frozen=True)

    current_scan_id: int
    base_scan_id: int
    added: list[str]
    removed: list[str]
    movers: list[TickerDelta]
