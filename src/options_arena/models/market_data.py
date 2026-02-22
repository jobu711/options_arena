"""Market data models for Options Arena.

Three immutable snapshot models for market data:
  OHLCV      — historical daily price bar (open/high/low/close/volume).
  Quote      — real-time price snapshot with bid/ask.
  TickerInfo  — fundamental data including dividend yield with provenance tracking.

All models are ``frozen=True`` (immutable after construction).
All ``Decimal`` fields use ``field_serializer`` to prevent float precision loss in JSON.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from options_arena.models.enums import DividendSource, MarketCapTier


class OHLCV(BaseModel):
    """Historical daily price bar.

    Represents a single day's OHLCV data for a ticker.
    All price fields use ``Decimal`` constructed from strings for financial precision.
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
    market_cap: int | None = None
    market_cap_tier: MarketCapTier | None = None

    # Dividend fields — populated by service layer 3-tier waterfall (FR-M7/M7.1)
    dividend_yield: float = 0.0
    dividend_source: DividendSource = DividendSource.NONE
    dividend_rate: float | None = None
    trailing_dividend_rate: float | None = None

    current_price: Decimal
    fifty_two_week_high: Decimal
    fifty_two_week_low: Decimal

    @field_serializer("current_price", "fifty_two_week_high", "fifty_two_week_low")
    def serialize_decimal(self, v: Decimal) -> str:
        """Serialize Decimal fields to str to avoid float precision loss in JSON."""
        return str(v)
