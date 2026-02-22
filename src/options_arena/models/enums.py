"""Options Arena — StrEnum definitions for all domain enumerations.

All enums use Python 3.13+ ``enum.StrEnum`` with lowercase string values.
No business logic — pure data definitions only.
"""

from enum import StrEnum


class OptionType(StrEnum):
    """Type of option contract."""

    CALL = "call"
    PUT = "put"


class PositionSide(StrEnum):
    """Direction of a position (long or short)."""

    LONG = "long"
    SHORT = "short"


class SignalDirection(StrEnum):
    """Directional signal from indicators or analysis."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ExerciseStyle(StrEnum):
    """Exercise style of an option contract.

    AMERICAN for all U.S. equity options; EUROPEAN for index options (SPX, etc.).
    Drives pricing dispatch: BAW for AMERICAN, BSM for EUROPEAN.
    """

    AMERICAN = "american"
    EUROPEAN = "european"


class PricingModel(StrEnum):
    """Pricing model used to compute Greeks.

    Tracked on every ``OptionGreeks`` instance so downstream consumers
    know which model produced the values.
    """

    BSM = "bsm"
    BAW = "baw"


class MarketCapTier(StrEnum):
    """Market capitalisation tier for ticker classification."""

    MEGA = "mega"
    LARGE = "large"
    MID = "mid"
    SMALL = "small"
    MICRO = "micro"


class DividendSource(StrEnum):
    """Provenance of the dividend yield value on ``TickerInfo``.

    Tracks which tier of the 3-tier waterfall produced the value:
      FORWARD  — yfinance ``info["dividendYield"]``
      TRAILING — yfinance ``info["trailingAnnualDividendYield"]``
      COMPUTED — ``sum(get_dividends("1y")) / price``
      NONE     — no dividend data available (yield defaults to 0.0)
    """

    FORWARD = "forward"
    TRAILING = "trailing"
    COMPUTED = "computed"
    NONE = "none"


class SpreadType(StrEnum):
    """Type of option spread strategy."""

    VERTICAL = "vertical"
    CALENDAR = "calendar"
    IRON_CONDOR = "iron_condor"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    BUTTERFLY = "butterfly"


class MacdSignal(StrEnum):
    """MACD crossover signal for market context.

    BULLISH_CROSSOVER — MACD line crossed above signal line.
    BEARISH_CROSSOVER — MACD line crossed below signal line.
    NEUTRAL           — no recent crossover.
    """

    BULLISH_CROSSOVER = "bullish_crossover"
    BEARISH_CROSSOVER = "bearish_crossover"
    NEUTRAL = "neutral"


class ScanPreset(StrEnum):
    """Scan universe preset for the scan pipeline.

    FULL  — full CBOE optionable universe.
    SP500 — S&P 500 constituents only.
    ETFS  — ETFs only.
    """

    FULL = "full"
    SP500 = "sp500"
    ETFS = "etfs"


class GreeksSource(StrEnum):
    """Source of Greeks values on an option contract.

    COMPUTED — locally computed via ``pricing/dispatch.py`` (BAW or BSM).
    MARKET   — sourced from market data provider (not used in MVP).
    """

    COMPUTED = "computed"
    MARKET = "market"
