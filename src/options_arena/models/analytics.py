"""Analytics persistence models for Options Arena.

Nine frozen Pydantic v2 models for the analytics persistence layer:
  RecommendedContract  — mirrors ``recommended_contracts`` table.
  ContractOutcome      — mirrors ``contract_outcomes`` table.
  NormalizationStats   — mirrors ``normalization_metadata`` table.
  WinRateResult        — analytics query result (win rate by direction).
  ScoreCalibrationBucket — analytics query result (return by score bucket).
  IndicatorAttributionResult — analytics query result (indicator-return correlation).
  HoldingPeriodResult  — analytics query result (return by holding period).
  DeltaPerformanceResult — analytics query result (return by delta bucket).
  PerformanceSummary   — aggregate analytics result.

All snapshot models use ``frozen=True``. All float validators check ``math.isfinite()``.
All Decimal validators check ``v.is_finite()``. All datetime fields enforce UTC.
All Decimal fields use ``field_serializer`` returning ``str(v)``.
"""

import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, computed_field, field_serializer, field_validator

from options_arena.models.enums import (
    ExerciseStyle,
    GreeksSource,
    OptionType,
    OutcomeCollectionMethod,
    PricingModel,
    SignalDirection,
)


class RecommendedContract(BaseModel):
    """A recommended option contract persisted from a scan run.

    Mirrors the ``recommended_contracts`` table schema. All Decimal fields are
    stored as TEXT in SQLite and serialized as strings in JSON to prevent
    precision loss.

    Attributes:
        id: DB-assigned primary key (None before persistence).
        scan_run_id: Foreign key to scan_runs table.
        ticker: Underlying ticker symbol.
        option_type: CALL or PUT.
        strike: Strike price (Decimal).
        bid: Bid price (Decimal).
        ask: Ask price (Decimal).
        last: Last traded price (Decimal, optional — can be stale/unavailable).
        expiration: Expiration date.
        volume: Trading volume (whole number).
        open_interest: Open interest (whole number).
        market_iv: Implied volatility from market data.
        exercise_style: AMERICAN or EUROPEAN.
        delta: Price sensitivity, in [-1, 1] (optional).
        gamma: Delta acceleration, >= 0 (optional).
        theta: Time decay (optional).
        vega: Volatility sensitivity, >= 0 (optional).
        rho: Interest rate sensitivity (optional).
        pricing_model: Which model (BSM/BAW) produced the Greeks (optional).
        greeks_source: Where the Greeks came from (optional).
        entry_stock_price: Stock price at time of recommendation (None if unavailable).
        entry_mid: Mid price of the contract at entry.
        direction: Signal direction from scoring.
        composite_score: Composite score from scoring pipeline.
        risk_free_rate: Risk-free rate used for pricing.
        created_at: Timestamp of creation (UTC).
        mid: Computed mid price ``(bid + ask) / 2``.
    """

    model_config = ConfigDict(frozen=True)

    id: int | None = None
    scan_run_id: int
    ticker: str
    option_type: OptionType
    strike: Decimal
    bid: Decimal
    ask: Decimal
    last: Decimal | None = None
    expiration: date
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
    entry_stock_price: Decimal | None = None
    entry_mid: Decimal
    direction: SignalDirection
    composite_score: float
    risk_free_rate: float
    created_at: datetime

    @field_validator("strike", "bid", "ask", "entry_mid")
    @classmethod
    def validate_decimal_finite(cls, v: Decimal) -> Decimal:
        """Ensure required Decimal fields are finite."""
        if not v.is_finite():
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("last", "entry_stock_price")
    @classmethod
    def validate_optional_decimal_finite(cls, v: Decimal | None) -> Decimal | None:
        """Ensure optional Decimal fields are finite when provided."""
        if v is not None and not v.is_finite():
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("risk_free_rate")
    @classmethod
    def validate_float_finite(cls, v: float) -> float:
        """Ensure required float fields are finite."""
        if not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("market_iv")
    @classmethod
    def validate_market_iv(cls, v: float) -> float:
        """Ensure market_iv is finite and non-negative."""
        if not math.isfinite(v):
            raise ValueError(f"market_iv must be finite, got {v}")
        if v < 0.0:
            raise ValueError(f"market_iv must be >= 0, got {v}")
        return v

    @field_validator("composite_score")
    @classmethod
    def validate_composite_score(cls, v: float) -> float:
        """Ensure composite_score is finite and within [0, 100]."""
        if not math.isfinite(v):
            raise ValueError(f"composite_score must be finite, got {v}")
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"composite_score must be in [0, 100], got {v}")
        return v

    @field_validator("delta")
    @classmethod
    def validate_delta_range(cls, v: float | None) -> float | None:
        """Ensure delta is finite and in [-1, 1] when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"delta must be finite, got {v}")
            if not -1.0 <= v <= 1.0:
                raise ValueError(f"delta must be in [-1, 1], got {v}")
        return v

    @field_validator("gamma", "vega")
    @classmethod
    def validate_non_negative_greeks(cls, v: float | None) -> float | None:
        """Ensure gamma and vega are finite and >= 0 when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"must be finite, got {v}")
            if v < 0.0:
                raise ValueError(f"must be >= 0, got {v}")
        return v

    @field_validator("theta", "rho")
    @classmethod
    def validate_optional_float_finite(cls, v: float | None) -> float | None:
        """Ensure theta and rho are finite when provided."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure created_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mid(self) -> Decimal:
        """Mid price: ``(bid + ask) / Decimal("2")``."""
        return (self.bid + self.ask) / Decimal("2")

    @field_serializer("strike", "bid", "ask", "last", "entry_stock_price", "entry_mid")
    def serialize_decimal(self, v: Decimal | None) -> str | None:
        """Serialize Decimal fields to string to prevent float precision loss."""
        if v is None:
            return None
        return str(v)


class ContractOutcome(BaseModel):
    """Outcome data for a recommended contract at a given exit point.

    Mirrors the ``contract_outcomes`` table schema. Links to a
    ``RecommendedContract`` via ``recommended_contract_id``.

    Attributes:
        id: DB-assigned primary key (None before persistence).
        recommended_contract_id: Foreign key to recommended_contracts.
        exit_stock_price: Stock price at exit (optional).
        exit_contract_mid: Contract mid price at exit (optional).
        exit_contract_bid: Contract bid price at exit (optional).
        exit_contract_ask: Contract ask price at exit (optional).
        exit_date: Date of exit observation (optional).
        stock_return_pct: Stock return percentage (optional).
        contract_return_pct: Contract return percentage (optional).
        is_winner: Whether the trade was profitable (optional).
        holding_days: Number of trading days held (optional).
        dte_at_exit: Days to expiration at exit (optional).
        collection_method: How the outcome was collected.
        collected_at: Timestamp of collection (UTC).
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

    @field_validator("holding_days", "dte_at_exit")
    @classmethod
    def validate_optional_int_non_negative(cls, v: int | None) -> int | None:
        """Ensure holding_days and dte_at_exit are non-negative when provided."""
        if v is not None and v < 0:
            raise ValueError(f"must be >= 0, got {v}")
        return v

    @field_validator(
        "exit_stock_price",
        "exit_contract_mid",
        "exit_contract_bid",
        "exit_contract_ask",
    )
    @classmethod
    def validate_optional_decimal_finite(cls, v: Decimal | None) -> Decimal | None:
        """Ensure optional Decimal fields are finite when provided."""
        if v is not None and not v.is_finite():
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("stock_return_pct", "contract_return_pct")
    @classmethod
    def validate_optional_return_finite(cls, v: float | None) -> float | None:
        """Ensure return percentages are finite when provided."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"return pct must be finite, got {v}")
        return v

    @field_validator("collected_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure collected_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("collected_at must be UTC")
        return v

    @field_serializer(
        "exit_stock_price",
        "exit_contract_mid",
        "exit_contract_bid",
        "exit_contract_ask",
    )
    def serialize_decimal(self, v: Decimal | None) -> str | None:
        """Serialize Decimal fields to string to prevent float precision loss."""
        if v is None:
            return None
        return str(v)


class NormalizationStats(BaseModel):
    """Normalization statistics for a single indicator in a scan run.

    Mirrors the ``normalization_metadata`` table schema. Captures the
    distribution statistics used for percentile-rank normalization.

    Attributes:
        id: DB-assigned primary key (None before persistence).
        scan_run_id: Foreign key to scan_runs table.
        indicator_name: Name of the indicator (e.g. "rsi", "adx").
        ticker_count: Number of tickers in the normalization sample.
        min_value: Minimum raw indicator value (optional).
        max_value: Maximum raw indicator value (optional).
        median_value: Median raw indicator value (optional).
        mean_value: Mean raw indicator value (optional).
        std_dev: Standard deviation (optional).
        p25: 25th percentile (optional).
        p75: 75th percentile (optional).
        created_at: Timestamp of creation (UTC).
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

    @field_validator("ticker_count")
    @classmethod
    def validate_ticker_count_non_negative(cls, v: int) -> int:
        """Ensure ticker_count is non-negative (zero is valid for empty scans)."""
        if v < 0:
            raise ValueError(f"ticker_count must be >= 0, got {v}")
        return v

    @field_validator(
        "min_value", "max_value", "median_value", "mean_value", "std_dev", "p25", "p75"
    )
    @classmethod
    def validate_optional_float_finite(cls, v: float | None) -> float | None:
        """Ensure optional float stats are finite when provided."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure created_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("created_at must be UTC")
        return v


class WinRateResult(BaseModel):
    """Win rate analytics result grouped by signal direction.

    Attributes:
        direction: Signal direction (bullish/bearish/neutral).
        total_contracts: Total contracts in this direction.
        winners: Number of winning contracts.
        losers: Number of losing contracts.
        win_rate: Win rate as fraction in [0.0, 1.0].
    """

    model_config = ConfigDict(frozen=True)

    direction: SignalDirection
    total_contracts: int
    winners: int
    losers: int
    win_rate: float

    @field_validator("total_contracts", "winners", "losers")
    @classmethod
    def validate_counts_non_negative(cls, v: int) -> int:
        """Ensure count fields are non-negative."""
        if v < 0:
            raise ValueError(f"must be >= 0, got {v}")
        return v

    @field_validator("win_rate")
    @classmethod
    def validate_win_rate(cls, v: float) -> float:
        """Ensure win_rate is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"win_rate must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"win_rate must be in [0.0, 1.0], got {v}")
        return v


class ScoreCalibrationBucket(BaseModel):
    """Score calibration analytics result for a score range bucket.

    Attributes:
        score_min: Lower bound of score bucket.
        score_max: Upper bound of score bucket.
        contract_count: Number of contracts in this bucket.
        avg_return_pct: Average return percentage.
        win_rate: Win rate as fraction in [0.0, 1.0].
    """

    model_config = ConfigDict(frozen=True)

    score_min: float
    score_max: float
    contract_count: int
    avg_return_pct: float
    win_rate: float

    @field_validator("contract_count")
    @classmethod
    def validate_contract_count_non_negative(cls, v: int) -> int:
        """Ensure contract_count is non-negative."""
        if v < 0:
            raise ValueError(f"must be >= 0, got {v}")
        return v

    @field_validator("score_min", "score_max", "avg_return_pct")
    @classmethod
    def validate_float_finite(cls, v: float) -> float:
        """Ensure float fields are finite."""
        if not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("win_rate")
    @classmethod
    def validate_win_rate(cls, v: float) -> float:
        """Ensure win_rate is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"win_rate must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"win_rate must be in [0.0, 1.0], got {v}")
        return v


class IndicatorAttributionResult(BaseModel):
    """Indicator attribution analytics result.

    Shows the correlation between an indicator's normalized value
    and subsequent contract returns.

    Attributes:
        indicator_name: Name of the indicator.
        holding_days: Holding period in trading days.
        correlation: Pearson correlation in [-1.0, 1.0].
        avg_return_when_high: Average return when indicator is in top quartile.
        avg_return_when_low: Average return when indicator is in bottom quartile.
        sample_size: Number of contracts in the sample.
    """

    model_config = ConfigDict(frozen=True)

    indicator_name: str
    holding_days: int
    correlation: float
    avg_return_when_high: float
    avg_return_when_low: float
    sample_size: int

    @field_validator("holding_days", "sample_size")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        """Ensure holding_days and sample_size are positive."""
        if v < 1:
            raise ValueError(f"must be >= 1, got {v}")
        return v

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
    def validate_float_finite(cls, v: float) -> float:
        """Ensure average return fields are finite."""
        if not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v


class HoldingPeriodResult(BaseModel):
    """Holding period analytics result.

    Shows return statistics for a specific holding period and direction.

    Attributes:
        holding_days: Holding period in trading days.
        direction: Signal direction.
        avg_return_pct: Average return percentage.
        median_return_pct: Median return percentage.
        win_rate: Win rate as fraction in [0.0, 1.0].
        sample_size: Number of contracts in the sample.
    """

    model_config = ConfigDict(frozen=True)

    holding_days: int
    direction: SignalDirection
    avg_return_pct: float
    median_return_pct: float
    win_rate: float
    sample_size: int

    @field_validator("holding_days", "sample_size")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        """Ensure holding_days and sample_size are positive."""
        if v < 1:
            raise ValueError(f"must be >= 1, got {v}")
        return v

    @field_validator("avg_return_pct", "median_return_pct")
    @classmethod
    def validate_float_finite(cls, v: float) -> float:
        """Ensure return fields are finite."""
        if not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("win_rate")
    @classmethod
    def validate_win_rate(cls, v: float) -> float:
        """Ensure win_rate is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"win_rate must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"win_rate must be in [0.0, 1.0], got {v}")
        return v


class DeltaPerformanceResult(BaseModel):
    """Delta performance analytics result.

    Shows return statistics for contracts in a delta range bucket.

    Attributes:
        delta_min: Lower bound of delta bucket.
        delta_max: Upper bound of delta bucket.
        holding_days: Holding period in trading days.
        avg_return_pct: Average return percentage.
        win_rate: Win rate as fraction in [0.0, 1.0].
        sample_size: Number of contracts in the sample.
    """

    model_config = ConfigDict(frozen=True)

    delta_min: float
    delta_max: float
    holding_days: int
    avg_return_pct: float
    win_rate: float
    sample_size: int

    @field_validator("holding_days", "sample_size")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        """Ensure holding_days and sample_size are positive."""
        if v < 1:
            raise ValueError(f"must be >= 1, got {v}")
        return v

    @field_validator("delta_min", "delta_max", "avg_return_pct")
    @classmethod
    def validate_float_finite(cls, v: float) -> float:
        """Ensure float fields are finite."""
        if not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("win_rate")
    @classmethod
    def validate_win_rate(cls, v: float) -> float:
        """Ensure win_rate is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"win_rate must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"win_rate must be in [0.0, 1.0], got {v}")
        return v


class PerformanceSummary(BaseModel):
    """Aggregate performance summary over a lookback period.

    All optional fields are ``None`` when no outcome data exists yet.

    Attributes:
        lookback_days: Number of calendar days in the lookback window.
        total_contracts: Total recommended contracts in the window.
        total_with_outcomes: Contracts that have outcome data.
        overall_win_rate: Overall win rate (None if no outcomes).
        avg_stock_return_pct: Average stock return (None if no outcomes).
        avg_contract_return_pct: Average contract return (None if no outcomes).
        best_direction: Direction with highest win rate (None if no outcomes).
        best_holding_days: Holding period with best returns (None if no outcomes).
    """

    model_config = ConfigDict(frozen=True)

    lookback_days: int
    total_contracts: int
    total_with_outcomes: int

    @field_validator("lookback_days")
    @classmethod
    def validate_lookback_positive(cls, v: int) -> int:
        """Ensure lookback_days is positive."""
        if v < 1:
            raise ValueError(f"lookback_days must be >= 1, got {v}")
        return v

    @field_validator("total_contracts", "total_with_outcomes")
    @classmethod
    def validate_totals_non_negative(cls, v: int) -> int:
        """Ensure total count fields are non-negative."""
        if v < 0:
            raise ValueError(f"must be >= 0, got {v}")
        return v

    overall_win_rate: float | None = None
    avg_stock_return_pct: float | None = None
    avg_contract_return_pct: float | None = None
    best_direction: SignalDirection | None = None
    best_holding_days: int | None = None

    @field_validator("overall_win_rate")
    @classmethod
    def validate_win_rate(cls, v: float | None) -> float | None:
        """Ensure overall_win_rate is finite and in [0.0, 1.0] when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"overall_win_rate must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"overall_win_rate must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("avg_stock_return_pct", "avg_contract_return_pct")
    @classmethod
    def validate_optional_float_finite(cls, v: float | None) -> float | None:
        """Ensure optional return fields are finite when provided."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v


# ---------------------------------------------------------------------------
# Agent calibration models
# ---------------------------------------------------------------------------


class AgentAccuracyReport(BaseModel):
    """Per-agent direction accuracy and Brier score."""

    model_config = ConfigDict(frozen=True)

    agent_name: str
    direction_hit_rate: float  # 0.0-1.0
    mean_confidence: float  # 0.0-1.0
    brier_score: float  # 0.0-1.0 (lower = better)
    sample_size: int

    @field_validator("direction_hit_rate")
    @classmethod
    def validate_direction_hit_rate(cls, v: float) -> float:
        """Ensure direction_hit_rate is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"direction_hit_rate must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"direction_hit_rate must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("mean_confidence")
    @classmethod
    def validate_mean_confidence(cls, v: float) -> float:
        """Ensure mean_confidence is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"mean_confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"mean_confidence must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("brier_score")
    @classmethod
    def validate_brier_score(cls, v: float) -> float:
        """Ensure brier_score is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"brier_score must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"brier_score must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("sample_size")
    @classmethod
    def validate_sample_size(cls, v: int) -> int:
        """Ensure sample_size is non-negative."""
        if v < 0:
            raise ValueError(f"sample_size must be >= 0, got {v}")
        return v


class CalibrationBucket(BaseModel):
    """Single confidence calibration bucket."""

    model_config = ConfigDict(frozen=True)

    bucket_label: str  # e.g. "0.0-0.2"
    bucket_low: float
    bucket_high: float
    mean_confidence: float
    actual_hit_rate: float
    count: int

    @field_validator("bucket_low", "bucket_high")
    @classmethod
    def validate_bucket_bounds(cls, v: float) -> float:
        """Ensure bucket bounds are finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"bucket bound must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"bucket bound must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("mean_confidence")
    @classmethod
    def validate_mean_confidence(cls, v: float) -> float:
        """Ensure mean_confidence is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"mean_confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"mean_confidence must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("actual_hit_rate")
    @classmethod
    def validate_actual_hit_rate(cls, v: float) -> float:
        """Ensure actual_hit_rate is finite and in [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"actual_hit_rate must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"actual_hit_rate must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("count")
    @classmethod
    def validate_count(cls, v: int) -> int:
        """Ensure count is non-negative."""
        if v < 0:
            raise ValueError(f"count must be >= 0, got {v}")
        return v


class AgentCalibrationData(BaseModel):
    """Per-agent or aggregate confidence calibration data."""

    model_config = ConfigDict(frozen=True)

    agent_name: str | None  # None = aggregate across all agents
    buckets: list[CalibrationBucket]
    sample_size: int

    @field_validator("sample_size")
    @classmethod
    def validate_sample_size(cls, v: int) -> int:
        """Ensure sample_size is non-negative."""
        if v < 0:
            raise ValueError(f"sample_size must be >= 0, got {v}")
        return v


class AgentWeightsComparison(BaseModel):
    """Manual vs auto-tuned weight comparison for a single agent."""

    model_config = ConfigDict(frozen=True)

    agent_name: str
    manual_weight: float
    auto_weight: float
    brier_score: float | None  # None if < 10 samples
    sample_size: int

    @field_validator("manual_weight", "auto_weight")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        """Ensure weight is finite and non-negative."""
        if not math.isfinite(v):
            raise ValueError(f"weight must be finite, got {v}")
        if v < 0.0:
            raise ValueError(f"weight must be >= 0.0, got {v}")
        return v

    @field_validator("brier_score")
    @classmethod
    def validate_brier_score(cls, v: float | None) -> float | None:
        """Ensure brier_score is finite and in [0.0, 1.0] when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"brier_score must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"brier_score must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("sample_size")
    @classmethod
    def validate_sample_size(cls, v: int) -> int:
        """Ensure sample_size is non-negative."""
        if v < 0:
            raise ValueError(f"sample_size must be >= 0, got {v}")
        return v
