"""Intelligence data models for Options Arena.

Frozen Pydantic v2 models representing intelligence snapshots from yfinance:
  AnalystSnapshot         — analyst consensus targets and ratings.
  UpgradeDowngrade        — single analyst upgrade/downgrade event.
  AnalystActivitySnapshot — recent analyst activity summary.
  InsiderTransaction      — single insider transaction.
  InsiderSnapshot         — insider trading activity summary.
  InstitutionalSnapshot   — institutional ownership data.
  IntelligencePackage     — combined intelligence data for a ticker.

All models are frozen (immutable), have NaN/Inf validators on float fields,
and UTC validators on datetime fields. Follows the same pattern as openbb.py.
"""

import math
from datetime import date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTION_MAP: dict[str, str] = {
    "up": "Upgrade",
    "down": "Downgrade",
    "init": "Initiated",
    "main": "Maintained",
    "reit": "Reiterated",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _parse_transaction_type(text: str) -> str:
    """Parse insider transaction type from descriptive text.

    Args:
        text: Raw transaction description text (e.g. "Sale of shares").

    Returns:
        One of "Sale", "Purchase", "Gift", "Exercise", or "Other".
    """
    if "Exercise" in text or "Option Exercise" in text:
        return "Exercise"
    if "Sale" in text:
        return "Sale"
    if "Purchase" in text:
        return "Purchase"
    if "Gift" in text:
        return "Gift"
    return "Other"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AnalystSnapshot(BaseModel):
    """Point-in-time analyst consensus data for a ticker.

    ``consensus_score`` and ``target_upside_pct`` are computed fields derived
    from the raw analyst counts and price targets. ``fetched_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    target_low: float | None = None
    target_high: float | None = None
    target_mean: float | None = None
    target_median: float | None = None
    current_price: float | None = None
    strong_buy: int = 0
    buy: int = 0
    hold: int = 0
    sell: int = 0
    strong_sell: int = 0
    fetched_at: datetime

    @field_validator(
        "target_low",
        "target_high",
        "target_mean",
        "target_median",
        "current_price",
    )
    @classmethod
    def validate_finite(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on optional float fields."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("strong_buy", "buy", "hold", "sell", "strong_sell")
    @classmethod
    def validate_non_negative_counts(cls, v: int) -> int:
        """Ensure analyst counts are non-negative."""
        if v < 0:
            raise ValueError(f"must be non-negative, got {v}")
        return v

    @field_validator("fetched_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure fetched_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def consensus_score(self) -> float | None:
        """Weighted analyst consensus score in [-1.0, 1.0].

        Formula: (strong_buy*2 + buy*1 + hold*0 + sell*-1 + strong_sell*-2) / (total * 2).
        Returns None when total is 0.
        """
        total = self.strong_buy + self.buy + self.hold + self.sell + self.strong_sell
        if total == 0:
            return None
        weighted = (
            self.strong_buy * 2
            + self.buy * 1
            + self.hold * 0
            + self.sell * (-1)
            + self.strong_sell * (-2)
        )
        return weighted / (total * 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def target_upside_pct(self) -> float | None:
        """Target upside percentage: (target_mean - current_price) / current_price.

        Returns None when target_mean or current_price is None, or when
        current_price is 0 (avoid division by zero).
        """
        if self.target_mean is None or self.current_price is None:
            return None
        if self.current_price <= 0:
            return None
        return (self.target_mean - self.current_price) / self.current_price


class UpgradeDowngrade(BaseModel):
    """Single analyst upgrade/downgrade event.

    ``action`` is mapped via ``ACTION_MAP`` from abbreviations to full names.
    ``from_grade`` empty strings are converted to None.
    ``price_target`` and ``prior_price_target`` of 0.0 are converted to None.
    """

    model_config = ConfigDict(frozen=True)

    firm: str
    action: str
    to_grade: str
    from_grade: str | None = None
    date: date
    price_target: float | None = None
    prior_price_target: float | None = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Map abbreviated action codes to full names via ACTION_MAP."""
        return ACTION_MAP.get(v, v)

    @field_validator("from_grade")
    @classmethod
    def validate_from_grade(cls, v: str | None) -> str | None:
        """Convert empty string from_grade to None."""
        if v is not None and v == "":
            return None
        return v

    @field_validator("price_target", "prior_price_target")
    @classmethod
    def validate_price_target(cls, v: float | None) -> float | None:
        """Reject NaN/Inf and convert 0.0 to None."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        if v is not None and v == 0.0:
            return None
        return v


class AnalystActivitySnapshot(BaseModel):
    """Recent analyst activity summary for a ticker.

    ``recent_changes`` is capped at 10 entries. ``fetched_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    recent_changes: list[UpgradeDowngrade]
    upgrades_30d: int = 0
    downgrades_30d: int = 0
    net_sentiment_30d: int = 0
    fetched_at: datetime

    @field_validator("recent_changes")
    @classmethod
    def validate_recent_changes_cap(cls, v: list[UpgradeDowngrade]) -> list[UpgradeDowngrade]:
        """Cap recent_changes at 10 entries."""
        return v[:10]

    @field_validator("upgrades_30d", "downgrades_30d")
    @classmethod
    def validate_non_negative_counts(cls, v: int) -> int:
        """Ensure upgrade/downgrade counts are non-negative."""
        if v < 0:
            raise ValueError(f"must be non-negative, got {v}")
        return v

    @field_validator("fetched_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure fetched_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        return v


class InsiderTransaction(BaseModel):
    """Single insider transaction record.

    ``value`` is converted to None when NaN/Inf (common in raw data).
    """

    model_config = ConfigDict(frozen=True)

    insider_name: str
    position: str
    transaction_type: str
    shares: int
    value: float | None = None
    ownership_type: str = "Direct"
    transaction_date: date | None = None

    @field_validator("shares")
    @classmethod
    def validate_shares_non_negative(cls, v: int) -> int:
        """Ensure shares is non-negative."""
        if v < 0:
            raise ValueError(f"must be non-negative, got {v}")
        return v

    @field_validator("value")
    @classmethod
    def validate_value_finite(cls, v: float | None) -> float | None:
        """Convert NaN/Inf value to None instead of rejecting."""
        if v is not None and not math.isfinite(v):
            return None
        return v


class InsiderSnapshot(BaseModel):
    """Insider trading activity summary for a ticker.

    ``transactions`` is capped at 20 entries. ``insider_buy_ratio`` is
    bounded to [0.0, 1.0]. ``fetched_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    transactions: list[InsiderTransaction]
    net_insider_buys_90d: int = 0
    net_insider_value_90d: float | None = None
    insider_buy_ratio: float | None = None
    fetched_at: datetime

    @field_validator("transactions")
    @classmethod
    def validate_transactions_cap(cls, v: list[InsiderTransaction]) -> list[InsiderTransaction]:
        """Cap transactions at 20 entries."""
        return v[:20]

    @field_validator("net_insider_value_90d")
    @classmethod
    def validate_net_insider_value_finite(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on net_insider_value_90d."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("insider_buy_ratio")
    @classmethod
    def validate_insider_buy_ratio(cls, v: float | None) -> float | None:
        """Ensure insider_buy_ratio is finite and within [0.0, 1.0]."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("fetched_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure fetched_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        return v


class InstitutionalSnapshot(BaseModel):
    """Institutional ownership data for a ticker.

    Percentage fields are bounded to [0.0, 1.0]. ``top_holders`` and
    ``top_holder_pcts`` are capped at 5 entries. ``fetched_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    institutional_pct: float | None = None
    institutional_float_pct: float | None = None
    insider_pct: float | None = None
    institutions_count: int | None = None
    top_holders: list[str] = []
    top_holder_pcts: list[float] = []
    fetched_at: datetime

    @field_validator("institutional_pct", "institutional_float_pct", "insider_pct")
    @classmethod
    def validate_pct_bounded(cls, v: float | None) -> float | None:
        """Ensure percentage fields are finite and within [0.0, 1.0]."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("institutions_count")
    @classmethod
    def validate_institutions_count(cls, v: int | None) -> int | None:
        """Ensure institutions_count is non-negative when present."""
        if v is not None and v < 0:
            raise ValueError(f"must be non-negative, got {v}")
        return v

    @field_validator("top_holders")
    @classmethod
    def validate_top_holders_cap(cls, v: list[str]) -> list[str]:
        """Cap top_holders at 5 entries."""
        return v[:5]

    @field_validator("top_holder_pcts")
    @classmethod
    def validate_top_holder_pcts_cap(cls, v: list[float]) -> list[float]:
        """Cap top_holder_pcts at 5 entries."""
        return v[:5]

    @field_validator("fetched_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure fetched_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        return v


class IntelligencePackage(BaseModel):
    """Combined intelligence data for a ticker.

    Aggregates all intelligence categories into a single frozen model.
    ``news_headlines`` is capped at 5 when not None. ``fetched_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    analyst: AnalystSnapshot | None = None
    analyst_activity: AnalystActivitySnapshot | None = None
    insider: InsiderSnapshot | None = None
    institutional: InstitutionalSnapshot | None = None
    news_headlines: list[str] | None = None
    fetched_at: datetime

    @field_validator("news_headlines")
    @classmethod
    def validate_news_headlines_cap(cls, v: list[str] | None) -> list[str] | None:
        """Cap news_headlines at 5 when not None."""
        if v is not None:
            return v[:5]
        return v

    @field_validator("fetched_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure fetched_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("fetched_at must be UTC")
        return v

    def intelligence_completeness(self) -> float:
        """Fraction of the 5 intelligence categories that are populated.

        Categories: analyst, analyst_activity, insider, institutional, news_headlines.
        Returns a float in [0.0, 1.0].
        """
        categories = [
            self.analyst,
            self.analyst_activity,
            self.insider,
            self.institutional,
            self.news_headlines,
        ]
        populated = sum(1 for c in categories if c is not None)
        return populated / len(categories)
