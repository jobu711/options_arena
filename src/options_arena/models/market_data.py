"""Market data models for Options Arena.

Three immutable snapshot models for market data:
  OHLCV      — historical daily price bar (open/high/low/close/volume).
  Quote      — real-time price snapshot with bid/ask.
  TickerInfo  — fundamental data including dividend yield with provenance tracking.

All models are ``frozen=True`` (immutable after construction).
All ``Decimal`` fields use ``field_serializer`` to prevent float precision loss in JSON.
"""

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from options_arena.models.enums import DividendSource, MarketCapTier


class OHLCV(BaseModel):
    """Historical daily price bar.

    Represents a single day's OHLCV data for a ticker.
    All price fields use ``Decimal`` constructed from strings for financial precision.

    Validators enforce:
      - All price fields are finite and > 0.
      - Volume is non-negative (zero is valid for non-trading days).
      - Candle consistency: high >= low, open and close within [low, high].
      - adjusted_close is NOT constrained by high/low (splits/dividends can move it outside).
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    adjusted_close: Decimal

    @field_validator("open", "high", "low", "close", "adjusted_close")
    @classmethod
    def validate_price_positive(cls, v: Decimal) -> Decimal:
        """Reject non-finite and non-positive prices."""
        if not v.is_finite() or v <= Decimal("0"):
            raise ValueError(f"price must be finite and > 0, got {v}")
        return v

    @field_validator("volume")
    @classmethod
    def validate_volume_non_negative(cls, v: int) -> int:
        """Reject negative volume (zero is valid)."""
        if v < 0:
            raise ValueError(f"volume must be >= 0, got {v}")
        return v

    @model_validator(mode="after")
    def validate_candle_consistency(self) -> Self:
        """Enforce OHLC candle consistency.

        Rules:
          - high must be >= low.
          - open must be in [low, high].
          - close must be in [low, high].
          - adjusted_close is exempt (splits/dividends can move it outside the range).
        """
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) must be >= low ({self.low})")
        if not (self.low <= self.open <= self.high):
            raise ValueError(
                f"open ({self.open}) must be in [low ({self.low}), high ({self.high})]"
            )
        if not (self.low <= self.close <= self.high):
            raise ValueError(
                f"close ({self.close}) must be in [low ({self.low}), high ({self.high})]"
            )
        return self

    @field_serializer("open", "high", "low", "close", "adjusted_close")
    def serialize_decimal(self, v: Decimal) -> str:
        """Serialize Decimal fields to str to avoid float precision loss in JSON."""
        return str(v)


class Quote(BaseModel):
    """Real-time price snapshot with bid/ask.

    Represents a point-in-time quote for a ticker.
    Timestamp must include timezone info (UTC).
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    timestamp: datetime

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: Decimal) -> Decimal:
        """Ensure price is finite and positive."""
        if not v.is_finite() or v <= Decimal("0"):
            raise ValueError(f"price must be finite and positive, got {v}")
        return v

    @field_validator("bid", "ask")
    @classmethod
    def validate_bid_ask(cls, v: Decimal) -> Decimal:
        """Ensure bid/ask is finite and non-negative (zero is valid for illiquid)."""
        if not v.is_finite() or v < Decimal("0"):
            raise ValueError(f"bid/ask must be finite and non-negative, got {v}")
        return v

    @field_validator("volume")
    @classmethod
    def validate_volume_non_negative(cls, v: int) -> int:
        """Ensure volume is non-negative."""
        if v < 0:
            raise ValueError(f"volume must be >= 0, got {v}")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure timestamp is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be UTC")
        return v

    @field_serializer("price", "bid", "ask")
    def serialize_decimal(self, v: Decimal) -> str:
        """Serialize Decimal fields to str to avoid float precision loss in JSON."""
        return str(v)


class TickerInfo(BaseModel):
    """Fundamental data for a ticker including dividend yield with provenance tracking.

    Dividend fields follow the 3-tier waterfall spec (FR-M7/M7.1):
      1. ``dividendYield`` from yfinance info  -> source = FORWARD
      2. ``trailingAnnualDividendYield``        -> source = TRAILING
      3. ``sum(get_dividends("1y")) / price``   -> source = COMPUTED
      4. ``0.0``                                -> source = NONE

    ``dividend_yield`` is always ``float`` (never ``None``). Default ``0.0`` ensures
    the pricing engine receives a guaranteed float without None handling.
    Values are decimal fractions: 0.005 = 0.5%.

    ``dividend_rate`` and ``trailing_dividend_rate`` are audit fields for
    cross-validation only — not used in pricing.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    company_name: str
    sector: str
    industry: str = "Unknown"
    market_cap: int | None = None
    market_cap_tier: MarketCapTier | None = None

    # Dividend fields — populated by service layer 3-tier waterfall (FR-M7/M7.1)
    dividend_yield: float = 0.0
    dividend_source: DividendSource = DividendSource.NONE

    @field_validator("dividend_yield")
    @classmethod
    def validate_dividend_yield_non_negative(cls, v: float) -> float:
        """Ensure dividend_yield is finite and non-negative."""
        if not math.isfinite(v) or v < 0.0:
            raise ValueError(f"dividend_yield must be finite and >= 0, got {v}")
        return v

    dividend_rate: float | None = None
    trailing_dividend_rate: float | None = None

    @field_validator("dividend_rate", "trailing_dividend_rate")
    @classmethod
    def validate_optional_dividend_finite(cls, v: float | None) -> float | None:
        """Ensure audit dividend fields are finite when provided."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    current_price: Decimal
    fifty_two_week_high: Decimal
    fifty_two_week_low: Decimal

    @field_validator("current_price", "fifty_two_week_high", "fifty_two_week_low")
    @classmethod
    def validate_price_positive(cls, v: Decimal) -> Decimal:
        """Ensure price fields are finite and positive."""
        if not v.is_finite() or v <= Decimal("0"):
            raise ValueError(f"price must be finite and positive, got {v}")
        return v

    # Short interest — populated from yfinance info dict
    short_ratio: float | None = None  # days to cover
    short_pct_of_float: float | None = None  # decimal fraction (no upper bound — squeezes > 1.0)

    @field_validator("short_ratio", "short_pct_of_float")
    @classmethod
    def validate_short_interest_fields(cls, v: float | None) -> float | None:
        """Ensure short interest fields are finite and non-negative when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"must be finite, got {v}")
            if v < 0.0:
                raise ValueError(f"must be >= 0, got {v}")
        return v

    @field_serializer("current_price", "fifty_two_week_high", "fifty_two_week_low")
    def serialize_decimal(self, v: Decimal) -> str:
        """Serialize Decimal fields to str to avoid float precision loss in JSON."""
        return str(v)
