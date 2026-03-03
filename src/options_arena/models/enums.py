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


class VolAssessment(StrEnum):
    """Implied volatility assessment from the Volatility Agent.

    OVERPRICED  — IV is elevated, favors selling premium.
    UNDERPRICED — IV is depressed, favors buying premium.
    FAIR        — IV is fairly valued, no vol play warranted.
    """

    OVERPRICED = "overpriced"
    UNDERPRICED = "underpriced"
    FAIR = "fair"


class MarketRegime(StrEnum):
    """Market regime classification for regime-adjusted scoring weights."""

    TRENDING = "trending"
    MEAN_REVERTING = "mean_reverting"
    VOLATILE = "volatile"
    CRISIS = "crisis"


class VolRegime(StrEnum):
    """Implied volatility regime classification."""

    LOW = "low"
    NORMAL = "normal"
    ELEVATED = "elevated"
    EXTREME = "extreme"


class IVTermStructureShape(StrEnum):
    """IV term structure shape classification."""

    CONTANGO = "contango"
    FLAT = "flat"
    BACKWARDATION = "backwardation"


class RiskLevel(StrEnum):
    """Quantified risk level for risk assessment."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


class CatalystImpact(StrEnum):
    """Expected impact of upcoming catalysts (earnings, dividends, etc.)."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class SentimentLabel(StrEnum):
    """Sentiment classification for news or social media analysis.

    Used by OpenBB integration to label aggregate news sentiment.
    """

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class OutcomeCollectionMethod(StrEnum):
    """Method used to collect contract outcome data.

    MARKET          — outcome computed from live market prices (bid/ask mid).
    INTRINSIC       — expired contract valued via intrinsic value (S-K or K-S).
    EXPIRED_WORTHLESS — expired OTM contract, value is zero, return is -100%.
    """

    MARKET = "market"
    INTRINSIC = "intrinsic"
    EXPIRED_WORTHLESS = "expired_worthless"


class GICSSector(StrEnum):
    """Global Industry Classification Standard (GICS) sectors.

    Exactly 11 sectors matching the canonical GICS taxonomy.
    Used for sector filtering in the scan pipeline.
    """

    COMMUNICATION_SERVICES = "Communication Services"
    CONSUMER_DISCRETIONARY = "Consumer Discretionary"
    CONSUMER_STAPLES = "Consumer Staples"
    ENERGY = "Energy"
    FINANCIALS = "Financials"
    HEALTH_CARE = "Health Care"
    INDUSTRIALS = "Industrials"
    INFORMATION_TECHNOLOGY = "Information Technology"
    MATERIALS = "Materials"
    REAL_ESTATE = "Real Estate"
    UTILITIES = "Utilities"


class LLMProvider(StrEnum):
    """LLM provider for the AI debate agents.

    GROQ     — Groq cloud API (free tier, Llama 3.3 70B).
    ANTHROPIC — Anthropic API (Claude, paid).
    """

    GROQ = "groq"
    ANTHROPIC = "anthropic"


SECTOR_ALIASES: dict[str, GICSSector] = {
    # Canonical names (lowercase)
    "communication services": GICSSector.COMMUNICATION_SERVICES,
    "consumer discretionary": GICSSector.CONSUMER_DISCRETIONARY,
    "consumer staples": GICSSector.CONSUMER_STAPLES,
    "energy": GICSSector.ENERGY,
    "financials": GICSSector.FINANCIALS,
    "health care": GICSSector.HEALTH_CARE,
    "industrials": GICSSector.INDUSTRIALS,
    "information technology": GICSSector.INFORMATION_TECHNOLOGY,
    "materials": GICSSector.MATERIALS,
    "real estate": GICSSector.REAL_ESTATE,
    "utilities": GICSSector.UTILITIES,
    # Short names
    "communication": GICSSector.COMMUNICATION_SERVICES,
    "telecom": GICSSector.COMMUNICATION_SERVICES,
    "discretionary": GICSSector.CONSUMER_DISCRETIONARY,
    "staples": GICSSector.CONSUMER_STAPLES,
    "healthcare": GICSSector.HEALTH_CARE,
    "technology": GICSSector.INFORMATION_TECHNOLOGY,
    "tech": GICSSector.INFORMATION_TECHNOLOGY,
    "it": GICSSector.INFORMATION_TECHNOLOGY,
    # Hyphenated variants
    "communication-services": GICSSector.COMMUNICATION_SERVICES,
    "consumer-discretionary": GICSSector.CONSUMER_DISCRETIONARY,
    "consumer-staples": GICSSector.CONSUMER_STAPLES,
    "health-care": GICSSector.HEALTH_CARE,
    "information-technology": GICSSector.INFORMATION_TECHNOLOGY,
    "real-estate": GICSSector.REAL_ESTATE,
    # Underscored variants
    "communication_services": GICSSector.COMMUNICATION_SERVICES,
    "consumer_discretionary": GICSSector.CONSUMER_DISCRETIONARY,
    "consumer_staples": GICSSector.CONSUMER_STAPLES,
    "health_care": GICSSector.HEALTH_CARE,
    "information_technology": GICSSector.INFORMATION_TECHNOLOGY,
    "real_estate": GICSSector.REAL_ESTATE,
}
