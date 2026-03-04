"""OpenBB integration models for Options Arena.

Frozen Pydantic v2 models representing snapshots from the OpenBB Platform SDK:
  FundamentalSnapshot — equity fundamental ratios and metrics.
  UnusualFlowSnapshot — unusual options/dark-pool flow signals.
  NewsHeadline        — single news article with VADER sentiment score.
  NewsSentimentSnapshot — aggregated news sentiment for a ticker.
  OpenBBHealthStatus  — health status of OpenBB data providers.

All models are optional-dependency safe: they are pure data definitions
with no OpenBB SDK imports. The service layer handles SDK interaction.
"""

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.enums import SentimentLabel


class FundamentalSnapshot(BaseModel):
    """Point-in-time fundamental metrics for a ticker.

    All ratio/metric fields are optional — providers may not supply every field.
    ``fetched_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    debt_to_equity: float | None = None
    revenue_growth: float | None = None
    profit_margin: float | None = None
    market_cap: int | None = None
    sector: str | None = None
    industry: str | None = None
    fetched_at: datetime

    @field_validator(
        "pe_ratio",
        "forward_pe",
        "peg_ratio",
        "price_to_book",
        "debt_to_equity",
        "revenue_growth",
        "profit_margin",
    )
    @classmethod
    def validate_finite(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on optional float fields."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("fetched_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure fetched_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        return v


class UnusualFlowSnapshot(BaseModel):
    """Point-in-time unusual options/dark-pool flow data for a ticker.

    Fields represent net premium flows and volume signals.
    ``fetched_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    net_call_premium: float | None = None
    net_put_premium: float | None = None
    call_volume: int | None = None
    put_volume: int | None = None
    put_call_ratio: float | None = None
    fetched_at: datetime

    @field_validator("net_call_premium", "net_put_premium", "put_call_ratio")
    @classmethod
    def validate_finite(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on optional float fields."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("fetched_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure fetched_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        return v


class NewsHeadline(BaseModel):
    """Single news headline with VADER sentiment score.

    ``sentiment_score`` is the VADER compound score ranging from -1.0 to 1.0.
    """

    model_config = ConfigDict(frozen=True)

    title: str
    published_at: datetime | None = None
    sentiment_score: float
    source: str | None = None

    @field_validator("sentiment_score")
    @classmethod
    def validate_sentiment_score(cls, v: float) -> float:
        """Ensure sentiment_score is finite and within [-1.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"sentiment_score must be finite, got {v}")
        if not -1.0 <= v <= 1.0:
            raise ValueError(f"sentiment_score must be in [-1.0, 1.0], got {v}")
        return v

    @field_validator("published_at")
    @classmethod
    def validate_utc(cls, v: datetime | None) -> datetime | None:
        """Ensure published_at is UTC when provided."""
        if v is not None and (v.tzinfo is None or v.utcoffset() != timedelta(0)):
            raise ValueError("published_at must be UTC")
        return v


class NewsSentimentSnapshot(BaseModel):
    """Aggregated news sentiment for a ticker.

    ``aggregate_sentiment`` is the mean VADER compound score across all headlines.
    ``sentiment_label`` classifies the aggregate into BULLISH/BEARISH/NEUTRAL.
    ``fetched_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    headlines: list[NewsHeadline]
    aggregate_sentiment: float
    sentiment_label: SentimentLabel
    article_count: int
    fetched_at: datetime

    @field_validator("aggregate_sentiment")
    @classmethod
    def validate_aggregate_sentiment(cls, v: float) -> float:
        """Ensure aggregate_sentiment is finite and within [-1.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"aggregate_sentiment must be finite, got {v}")
        if not -1.0 <= v <= 1.0:
            raise ValueError(f"aggregate_sentiment must be in [-1.0, 1.0], got {v}")
        return v

    @field_validator("article_count")
    @classmethod
    def validate_article_count(cls, v: int) -> int:
        """Ensure article_count is non-negative."""
        if v < 0:
            raise ValueError(f"article_count must be >= 0, got {v}")
        return v

    @field_validator("fetched_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure fetched_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        return v


class OpenBBHealthStatus(BaseModel):
    """Health status of OpenBB data providers.

    Reports availability of the OpenBB SDK and each data provider.
    ``last_checked`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    openbb_available: bool
    yahoo_fundamentals: bool
    stockgrid_flow: bool
    last_checked: datetime

    @field_validator("last_checked")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure last_checked is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("last_checked must be UTC")
        return v
