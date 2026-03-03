"""Options Arena — Analytics persistence models.

Defines data shapes for the analytics feedback loop:
- ``RecommendedContract``: snapshot of a contract recommendation with entry prices
- ``ContractOutcome``: P&L tracking at configurable holding periods
- ``NormalizationStats``: per-indicator distribution metadata from scans
- 6 query result models for analytics endpoints

All snapshot models are frozen (immutable). Decimal fields use ``field_serializer``
to prevent float precision loss in JSON. Every float validator calls ``math.isfinite()``
before range checks. Every datetime validator enforces UTC.
"""

import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    computed_field,
    field_serializer,
    field_validator,
)

from options_arena.models.enums import (
    ExerciseStyle,
    GreeksSource,
    OptionType,
    OutcomeCollectionMethod,
    PricingModel,
    SignalDirection,
)

# ---------------------------------------------------------------------------
# Helper validators (reusable across models)
# ---------------------------------------------------------------------------


def _validate_utc(v: datetime, field_name: str) -> datetime:
    """Enforce UTC on a datetime value."""
    if v.tzinfo is None or v.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be UTC")
    return v


def _validate_finite_float(v: float, field_name: str) -> float:
    """Reject NaN/Inf on a required float."""
    if not math.isfinite(v):
        raise ValueError(f"{field_name} must be finite, got {v}")
    return v


def _validate_optional_finite_float(v: float | None, field_name: str) -> float | None:
    """Reject NaN/Inf on an optional float."""
    if v is not None and not math.isfinite(v):
        raise ValueError(f"{field_name} must be finite, got {v}")
    return v


def _validate_finite_decimal(v: Decimal, field_name: str) -> Decimal:
    """Reject NaN/Inf on a required Decimal."""
    if not v.is_finite():
        raise ValueError(f"{field_name} must be finite, got {v}")
    return v


def _validate_optional_finite_decimal(v: Decimal | None, field_name: str) -> Decimal | None:
    """Reject NaN/Inf on an optional Decimal."""
    if v is not None and not v.is_finite():
        raise ValueError(f"{field_name} must be finite, got {v}")
    return v


def _validate_win_rate(v: float, field_name: str) -> float:
    """Validate a win rate is finite and in [0.0, 1.0]."""
    if not math.isfinite(v):
        raise ValueError(f"{field_name} must be finite, got {v}")
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"{field_name} must be in [0.0, 1.0], got {v}")
    return v


def _validate_optional_win_rate(v: float | None, field_name: str) -> float | None:
    """Validate an optional win rate is finite and in [0.0, 1.0]."""
    if v is not None:
        if not math.isfinite(v):
            raise ValueError(f"{field_name} must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"{field_name} must be in [0.0, 1.0], got {v}")
    return v


# ---------------------------------------------------------------------------
# 1. RecommendedContract — persisted contract snapshot with entry prices
# ---------------------------------------------------------------------------


class RecommendedContract(BaseModel):
    """Snapshot of a recommended option contract from a scan run.

    Captures the full contract state at recommendation time including entry
    stock price, entry mid price, Greeks, and the composite score that
    triggered the recommendation.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    scan_run_id: int
    ticker: str
    option_type: OptionType
    strike: Decimal
    expiration: date
    bid: Decimal
    ask: Decimal
    last: Decimal | None = None
    volume: int
    open_interest: int
    market_iv: float
    exercise_style: ExerciseStyle
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    pricing_model: PricingModel | None = None
    greeks_source: GreeksSource | None = None
    entry_stock_price: Decimal
    entry_mid: Decimal
    direction: SignalDirection
    composite_score: float
    risk_free_rate: float
    created_at: datetime

    # --- Decimal validators ---

    @field_validator("strike", "entry_stock_price", "entry_mid")
    @classmethod
    def validate_decimal_finite(cls, v: Decimal) -> Decimal:
        """Ensure required Decimal fields are finite."""
        return _validate_finite_decimal(v, "field")

    @field_validator("bid", "ask")
    @classmethod
    def validate_price_non_negative(cls, v: Decimal) -> Decimal:
        """Ensure bid/ask are finite and non-negative."""
        if not v.is_finite() or v < Decimal("0"):
            raise ValueError(f"price must be finite and non-negative, got {v}")
        return v

    @field_validator("last")
    @classmethod
    def validate_last_optional(cls, v: Decimal | None) -> Decimal | None:
        """Ensure last is finite when provided."""
        return _validate_optional_finite_decimal(v, "last")

    # --- Float validators ---

    @field_validator("market_iv")
    @classmethod
    def validate_market_iv(cls, v: float) -> float:
        """Ensure market_iv is finite and non-negative."""
        if not math.isfinite(v) or v < 0.0:
            raise ValueError(f"market_iv must be finite and >= 0, got {v}")
        return v

    @field_validator("composite_score")
    @classmethod
    def validate_composite_score(cls, v: float) -> float:
        """Ensure composite_score is finite."""
        return _validate_finite_float(v, "composite_score")

    @field_validator("risk_free_rate")
    @classmethod
    def validate_risk_free_rate(cls, v: float) -> float:
        """Ensure risk_free_rate is finite."""
        return _validate_finite_float(v, "risk_free_rate")

    @field_validator("delta")
    @classmethod
    def validate_delta(cls, v: float | None) -> float | None:
        """Ensure delta is finite and in [-1.0, 1.0] when provided."""
        if v is not None and (not math.isfinite(v) or not -1.0 <= v <= 1.0):
            raise ValueError(f"delta must be finite and in [-1.0, 1.0], got {v}")
        return v

    @field_validator("gamma", "vega")
    @classmethod
    def validate_non_negative_optional(cls, v: float | None) -> float | None:
        """Ensure gamma/vega are finite and >= 0 when provided."""
        if v is not None and (not math.isfinite(v) or v < 0.0):
            raise ValueError(f"must be finite and >= 0, got {v}")
        return v

    @field_validator("theta", "rho")
    @classmethod
    def validate_finite_optional(cls, v: float | None) -> float | None:
        """Ensure theta/rho are finite when provided."""
        return _validate_optional_finite_float(v, "field")

    # --- Datetime validator ---

    @field_validator("created_at")
    @classmethod
    def validate_created_at_utc(cls, v: datetime) -> datetime:
        """Ensure created_at is UTC."""
        return _validate_utc(v, "created_at")

    # --- Int validators ---

    @field_validator("volume", "open_interest")
    @classmethod
    def validate_int_non_negative(cls, v: int) -> int:
        """Ensure volume and open_interest are non-negative."""
        if v < 0:
            raise ValueError(f"must be >= 0, got {v}")
        return v

    # --- Computed fields ---

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mid(self) -> Decimal:
        """Mid price: ``(bid + ask) / Decimal("2")``."""
        return (self.bid + self.ask) / Decimal("2")

    # --- Serializers ---

    @field_serializer("strike", "bid", "ask", "last", "entry_stock_price", "entry_mid")
    def serialize_decimal(self, v: Decimal | None) -> str | None:
        """Serialize Decimal fields to string to prevent float precision loss."""
        return str(v) if v is not None else None


# ---------------------------------------------------------------------------
# 2. ContractOutcome — P&L tracking at holding periods
# ---------------------------------------------------------------------------


class ContractOutcome(BaseModel):
    """Outcome measurement for a recommended contract at a specific holding period.

    Tracks exit prices, return percentages, and the collection method used
    (market, intrinsic, or expired_worthless).
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    recommended_contract_id: int
    exit_stock_price: Decimal | None = None
    exit_contract_mid: Decimal | None = None
    exit_contract_bid: Decimal | None = None
    exit_contract_ask: Decimal | None = None
    exit_date: date | None = None
    stock_return_pct: float | None = None
    contract_return_pct: float | None = None
    is_winner: bool | None = None
    holding_days: int | None = None
    dte_at_exit: int | None = None
    collection_method: OutcomeCollectionMethod
    collected_at: datetime

    # --- Int validators ---

    @field_validator("holding_days", "dte_at_exit")
    @classmethod
    def validate_non_negative_int(cls, v: int | None) -> int | None:
        """Ensure holding_days and dte_at_exit are non-negative when provided."""
        if v is not None and v < 0:
            raise ValueError(f"must be >= 0, got {v}")
        return v

    # --- Decimal validators ---

    @field_validator(
        "exit_stock_price", "exit_contract_mid", "exit_contract_bid", "exit_contract_ask"
    )
    @classmethod
    def validate_optional_decimal(cls, v: Decimal | None) -> Decimal | None:
        """Ensure optional Decimal fields are finite when provided."""
        return _validate_optional_finite_decimal(v, "field")

    # --- Float validators ---

    @field_validator("stock_return_pct", "contract_return_pct")
    @classmethod
    def validate_return_pct(cls, v: float | None) -> float | None:
        """Ensure return percentages are finite when provided."""
        return _validate_optional_finite_float(v, "return_pct")

    # --- Datetime validator ---

    @field_validator("collected_at")
    @classmethod
    def validate_collected_at_utc(cls, v: datetime) -> datetime:
        """Ensure collected_at is UTC."""
        return _validate_utc(v, "collected_at")

    # --- Serializers ---

    @field_serializer(
        "exit_stock_price", "exit_contract_mid", "exit_contract_bid", "exit_contract_ask"
    )
    def serialize_decimal(self, v: Decimal | None) -> str | None:
        """Serialize Decimal fields to string to prevent float precision loss."""
        return str(v) if v is not None else None


# ---------------------------------------------------------------------------
# 3. NormalizationStats — per-indicator distribution metadata
# ---------------------------------------------------------------------------


class NormalizationStats(BaseModel):
    """Distribution statistics for a single indicator across all tickers in a scan.

    Captures min, max, median, mean, std_dev, p25, p75 for calibration analytics.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    scan_run_id: int
    indicator_name: str
    ticker_count: int
    min_value: float | None = None
    max_value: float | None = None
    median_value: float | None = None
    mean_value: float | None = None
    std_dev: float | None = None
    p25: float | None = None
    p75: float | None = None
    created_at: datetime

    # --- Int validators ---

    @field_validator("ticker_count")
    @classmethod
    def validate_ticker_count(cls, v: int) -> int:
        """Ensure ticker_count is non-negative."""
        if v < 0:
            raise ValueError(f"ticker_count must be >= 0, got {v}")
        return v

    # --- Float validators ---

    @field_validator(
        "min_value", "max_value", "median_value", "mean_value", "p25", "p75"
    )
    @classmethod
    def validate_stats_finite(cls, v: float | None) -> float | None:
        """Ensure all optional stat fields are finite when provided."""
        return _validate_optional_finite_float(v, "stat")

    @field_validator("std_dev")
    @classmethod
    def validate_std_dev(cls, v: float | None) -> float | None:
        """Ensure std_dev is finite and non-negative when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"std_dev must be finite, got {v}")
            if v < 0.0:
                raise ValueError(f"std_dev must be >= 0, got {v}")
        return v

    # --- Datetime validator ---

    @field_validator("created_at")
    @classmethod
    def validate_created_at_utc(cls, v: datetime) -> datetime:
        """Ensure created_at is UTC."""
        return _validate_utc(v, "created_at")


# ---------------------------------------------------------------------------
# 4. WinRateResult — analytics query result
# ---------------------------------------------------------------------------


class WinRateResult(BaseModel):
    """Win rate statistics grouped by signal direction."""

    model_config = ConfigDict(frozen=True)

    direction: SignalDirection
    total_contracts: int
    winners: int
    losers: int
    win_rate: float

    @field_validator("win_rate")
    @classmethod
    def validate_win_rate(cls, v: float) -> float:
        """Ensure win_rate is finite and in [0.0, 1.0]."""
        return _validate_win_rate(v, "win_rate")


# ---------------------------------------------------------------------------
# 5. ScoreCalibrationBucket — analytics query result
# ---------------------------------------------------------------------------


class ScoreCalibrationBucket(BaseModel):
    """Score calibration bucket — maps composite score ranges to outcomes."""

    model_config = ConfigDict(frozen=True)

    score_min: float
    score_max: float
    contract_count: int
    avg_return_pct: float
    win_rate: float

    @field_validator("score_min", "score_max", "avg_return_pct")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        """Ensure float fields are finite."""
        return _validate_finite_float(v, "field")

    @field_validator("win_rate")
    @classmethod
    def validate_win_rate(cls, v: float) -> float:
        """Ensure win_rate is finite and in [0.0, 1.0]."""
        return _validate_win_rate(v, "win_rate")


# ---------------------------------------------------------------------------
# 6. IndicatorAttributionResult — analytics query result
# ---------------------------------------------------------------------------


class IndicatorAttributionResult(BaseModel):
    """Indicator attribution — correlation between indicator values and returns."""

    model_config = ConfigDict(frozen=True)

    indicator_name: str
    holding_days: int
    correlation: float
    avg_return_when_high: float
    avg_return_when_low: float
    sample_size: int

    @field_validator("correlation")
    @classmethod
    def validate_correlation(cls, v: float) -> float:
        """Ensure correlation is finite and in [-1.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"correlation must be finite, got {v}")
        if not -1.0 <= v <= 1.0:
            raise ValueError(f"correlation must be in [-1.0, 1.0], got {v}")
        return v

    @field_validator("avg_return_when_high", "avg_return_when_low")
    @classmethod
    def validate_returns_finite(cls, v: float) -> float:
        """Ensure return fields are finite."""
        return _validate_finite_float(v, "return")


# ---------------------------------------------------------------------------
# 7. HoldingPeriodResult — analytics query result
# ---------------------------------------------------------------------------


class HoldingPeriodResult(BaseModel):
    """Holding period analysis — performance by holding duration and direction."""

    model_config = ConfigDict(frozen=True)

    holding_days: int
    direction: SignalDirection
    avg_return_pct: float
    median_return_pct: float
    win_rate: float
    sample_size: int

    @field_validator("avg_return_pct", "median_return_pct")
    @classmethod
    def validate_returns_finite(cls, v: float) -> float:
        """Ensure return fields are finite."""
        return _validate_finite_float(v, "return")

    @field_validator("win_rate")
    @classmethod
    def validate_win_rate(cls, v: float) -> float:
        """Ensure win_rate is finite and in [0.0, 1.0]."""
        return _validate_win_rate(v, "win_rate")


# ---------------------------------------------------------------------------
# 8. DeltaPerformanceResult — analytics query result
# ---------------------------------------------------------------------------


class DeltaPerformanceResult(BaseModel):
    """Delta performance analysis — return by delta bucket and holding period."""

    model_config = ConfigDict(frozen=True)

    delta_min: float
    delta_max: float
    holding_days: int
    avg_return_pct: float
    win_rate: float
    sample_size: int

    @field_validator("delta_min", "delta_max", "avg_return_pct")
    @classmethod
    def validate_finite(cls, v: float) -> float:
        """Ensure float fields are finite."""
        return _validate_finite_float(v, "field")

    @field_validator("win_rate")
    @classmethod
    def validate_win_rate(cls, v: float) -> float:
        """Ensure win_rate is finite and in [0.0, 1.0]."""
        return _validate_win_rate(v, "win_rate")


# ---------------------------------------------------------------------------
# 9. PerformanceSummary — aggregate analytics result
# ---------------------------------------------------------------------------


class PerformanceSummary(BaseModel):
    """Aggregate performance summary across all tracked contracts."""

    model_config = ConfigDict(frozen=True)

    lookback_days: int
    total_contracts: int
    total_with_outcomes: int
    overall_win_rate: float | None = None
    avg_stock_return_pct: float | None = None
    avg_contract_return_pct: float | None = None
    best_direction: SignalDirection | None = None
    best_holding_days: int | None = None

    @field_validator("overall_win_rate")
    @classmethod
    def validate_win_rate(cls, v: float | None) -> float | None:
        """Ensure win_rate is finite and in [0.0, 1.0] when provided."""
        return _validate_optional_win_rate(v, "overall_win_rate")

    @field_validator("avg_stock_return_pct", "avg_contract_return_pct")
    @classmethod
    def validate_returns(cls, v: float | None) -> float | None:
        """Ensure return fields are finite when provided."""
        return _validate_optional_finite_float(v, "return")
