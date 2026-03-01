"""Watchlist models for Options Arena.

Three models for user-defined watchlists:
  Watchlist        -- a named collection of tickers (frozen).
  WatchlistTicker  -- a ticker membership in a watchlist (frozen).
  WatchlistDetail  -- enriched view with tickers, scores, and debate dates.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.enums import SignalDirection


class Watchlist(BaseModel):
    """A user-defined watchlist.

    Frozen (immutable after construction) -- represents a persisted snapshot.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure created_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return v


class WatchlistTicker(BaseModel):
    """A ticker belonging to a watchlist.

    Frozen (immutable after construction) -- represents a persisted snapshot.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    watchlist_id: int
    ticker: str
    added_at: datetime

    @field_validator("added_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure added_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("added_at must be UTC")
        return v


class WatchlistTickerDetail(BaseModel):
    """Enriched ticker entry for the watchlist detail view.

    Includes latest score and last debate date from the database.
    Not frozen -- populated incrementally during enrichment.
    """

    ticker: str
    added_at: datetime
    composite_score: float | None = None
    direction: SignalDirection | None = None
    last_debate_at: datetime | None = None

    @field_validator("composite_score")
    @classmethod
    def validate_composite_score(cls, v: float | None) -> float | None:
        """Ensure composite_score is finite when provided."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"composite_score must be finite, got {v}")
        return v

    @field_validator("added_at", "last_debate_at")
    @classmethod
    def validate_utc(cls, v: datetime | None) -> datetime | None:
        """Ensure datetime fields are UTC when provided."""
        if v is not None and (v.tzinfo is None or v.utcoffset() != timedelta(0)):
            raise ValueError("datetime must be UTC")
        return v


class WatchlistDetail(BaseModel):
    """Enriched watchlist with ticker details, scores, and debate dates.

    Frozen (immutable after construction) -- fully populated before return.
    """

    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    created_at: datetime
    tickers: list[WatchlistTickerDetail]

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure created_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return v
