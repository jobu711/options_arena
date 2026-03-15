"""Correlation models for portfolio analysis.

Two models for pairwise correlation results:
  PairwiseCorrelation  -- a single pair's Pearson correlation (frozen).
  CorrelationMatrix    -- full matrix with all pairs and metadata (frozen).

Based on Markowitz (1952) portfolio theory -- correlation is essential for
understanding diversification benefits and concentration risk.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, computed_field, field_validator


class PairwiseCorrelation(BaseModel):
    """A single pairwise Pearson correlation result.

    Frozen (immutable after construction) -- represents a completed computation.
    ``correlation`` is validated to be finite and within [-1.0, 1.0].
    ``computed_at`` is validated to be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker_a: str
    ticker_b: str
    correlation: float  # Pearson [-1.0, 1.0]
    overlapping_days: int  # >= 0

    @field_validator("correlation")
    @classmethod
    def validate_correlation(cls, v: float) -> float:
        """Ensure correlation is finite and within [-1.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"correlation must be finite, got {v}")
        if not -1.0 <= v <= 1.0:
            raise ValueError(f"correlation must be in [-1, 1], got {v}")
        return v

    @field_validator("overlapping_days")
    @classmethod
    def validate_overlapping_days(cls, v: int) -> int:
        """Ensure overlapping_days is non-negative."""
        if v < 0:
            raise ValueError(f"overlapping_days must be >= 0, got {v}")
        return v


class CorrelationMatrix(BaseModel):
    """Full correlation matrix with all pairwise results.

    Frozen (immutable after construction) -- represents a completed computation.
    ``computed_at`` is validated to be UTC.
    """

    model_config = ConfigDict(frozen=True)

    tickers: list[str]
    pairs: list[PairwiseCorrelation]
    computed_at: datetime  # UTC validated

    @field_validator("computed_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure computed_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("computed_at must be UTC")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def avg_correlation(self) -> float | None:
        """Average correlation across all pairs, or None if no pairs."""
        if not self.pairs:
            return None
        total = sum(p.correlation for p in self.pairs)
        return total / len(self.pairs)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pair_count(self) -> int:
        """Number of computed pairs."""
        return len(self.pairs)
