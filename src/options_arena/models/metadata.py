"""Ticker metadata models for Options Arena.

Two models for the metadata index:
  TickerMetadata    -- cached sector/industry/market-cap classification (frozen).
  MetadataCoverage  -- coverage statistics for the metadata index (frozen).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.enums import GICSIndustryGroup, GICSSector, MarketCapTier


class TickerMetadata(BaseModel):
    """Cached sector, industry group, and market-cap classification for a ticker.

    Frozen (immutable after construction) -- represents a persisted snapshot.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    sector: GICSSector | None = None
    industry_group: GICSIndustryGroup | None = None
    market_cap_tier: MarketCapTier | None = None
    company_name: str | None = None
    raw_sector: str = "Unknown"
    raw_industry: str = "Unknown"
    last_updated: datetime

    @field_validator("last_updated")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure last_updated is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("last_updated must be UTC")
        return v


class MetadataCoverage(BaseModel):
    """Coverage statistics for the ticker metadata index.

    Frozen (immutable after construction) -- fully populated before return.
    """

    model_config = ConfigDict(frozen=True)

    total: int
    with_sector: int
    with_industry_group: int
    coverage: float
