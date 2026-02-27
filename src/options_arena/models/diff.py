"""Scan diff and debate trend models for Options Arena.

Three immutable snapshot models for tracking changes between scans:
  ScoreChange      -- score delta for a single ticker between two scans.
  ScanDiffResult   -- complete diff between two scan runs.
  DebateTrendPoint -- single point in a debate confidence trend.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.enums import SignalDirection


class ScoreChange(BaseModel):
    """Score delta for a single ticker between two scans.

    Frozen (immutable after construction) -- represents a computed diff.
    ``old_score`` and ``new_score`` are validated to be finite and in [0.0, 100.0].
    ``score_delta`` is validated to be finite.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    old_score: float
    new_score: float
    old_direction: SignalDirection
    new_direction: SignalDirection
    direction_changed: bool
    score_delta: float

    @field_validator("old_score", "new_score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        """Ensure score is finite and within [0.0, 100.0]."""
        if not math.isfinite(v):
            raise ValueError(f"score must be finite, got {v}")
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"score must be in [0, 100], got {v}")
        return v

    @field_validator("score_delta")
    @classmethod
    def validate_score_delta(cls, v: float) -> float:
        """Ensure score_delta is finite."""
        if not math.isfinite(v):
            raise ValueError(f"score_delta must be finite, got {v}")
        return v


class ScanDiffResult(BaseModel):
    """Complete diff between two scan runs.

    Frozen (immutable after construction) -- represents a computed comparison.
    ``created_at`` must be a UTC-aware datetime.
    """

    model_config = ConfigDict(frozen=True)

    old_scan_id: int
    new_scan_id: int
    changes: list[ScoreChange]
    new_entries: list[str]
    removed_entries: list[str]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure created_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return v


class DebateTrendPoint(BaseModel):
    """Single point in a debate confidence trend.

    Frozen (immutable after construction) -- represents a historical debate result.
    ``confidence`` is validated to be finite and within [0.0, 1.0].
    ``created_at`` must be a UTC-aware datetime.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    direction: SignalDirection
    confidence: float
    is_fallback: bool
    created_at: datetime

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure created_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return v
