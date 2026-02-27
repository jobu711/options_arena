"""Watchlist models for Options Arena.

Three immutable snapshot models for user-defined watchlists:
  Watchlist       -- watchlist metadata (id, name, timestamps).
  WatchlistTicker -- single ticker in a watchlist.
  WatchlistDetail -- watchlist with its tickers (for API responses).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator


class Watchlist(BaseModel):
    """Watchlist metadata.

    Frozen (immutable after construction) -- represents a stored watchlist snapshot.
    ``id`` is ``None`` before the database assigns it.
    ``created_at`` and ``updated_at`` must be UTC-aware datetimes.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure timestamp is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return v


class WatchlistTicker(BaseModel):
    """Single ticker membership in a watchlist.

    Frozen (immutable after construction) -- represents a stored ticker-watchlist link.
    ``id`` is ``None`` before the database assigns it.
    ``added_at`` must be a UTC-aware datetime.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
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


class WatchlistDetail(BaseModel):
    """Watchlist with its tickers for API responses.

    Frozen (immutable after construction) -- represents a complete watchlist snapshot
    including all ticker memberships.
    ``id`` is ``None`` before the database assigns it.
    ``created_at`` and ``updated_at`` must be UTC-aware datetimes.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    tickers: list[WatchlistTicker]

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure timestamp is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return v
