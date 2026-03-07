"""Analysis models for Options Arena.

Nine models for market analysis and AI debate:
  MarketContext        -- flat snapshot of ticker state for analysis and debate agents.
  AgentResponse        -- structured response from a debate agent (frozen).
  TradeThesis          -- final trade recommendation from the debate (frozen).
  VolatilityThesis     -- structured output from the Volatility Agent (frozen).
  FlowThesis           -- structured output from the Flow Agent (frozen).
  RiskAssessment       -- expanded risk assessment from the Risk Agent (frozen).
  FundamentalThesis    -- structured output from the Fundamental Agent (frozen).
  ContrarianThesis     -- structured output from the Contrarian Agent (frozen).
  ExtendedTradeThesis  -- TradeThesis extension with DSE fields (frozen).

``MarketContext`` is intentionally flat (not nested) because agents parse flat
text better than nested objects.  ``AgentResponse``, ``TradeThesis``, and
``VolatilityThesis`` define shapes for the debate system.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from options_arena.models._validators import validate_non_empty_list, validate_unit_interval
from options_arena.models.enums import (
    CatalystImpact,
    ExerciseStyle,
    MacdSignal,
    RiskLevel,
    SignalDirection,
    SpreadType,
    VolAssessment,
)
from options_arena.models.scoring import DimensionalScores

logger = logging.getLogger(__name__)


class MarketContext(BaseModel):
    """Snapshot of ticker state for analysis and (v2) debate agents.

    Keep flat -- agents parse flat text better than nested objects.
    NOT frozen: mutable so fields can be populated incrementally.

    ``Decimal`` fields use ``field_serializer`` to prevent float precision loss
    in JSON serialization.
    """

    ticker: str
    current_price: Decimal
    price_52w_high: Decimal
    price_52w_low: Decimal
    iv_rank: float | None = None
    iv_percentile: float | None = None
    atm_iv_30d: float | None = None
    rsi_14: float = 50.0  # RSI has meaningful neutral at 50
    macd_signal: MacdSignal
    put_call_ratio: float | None = None
    max_pain_distance: float | None = None
    next_earnings: date | None
    dte_target: int
    target_strike: Decimal
    target_delta: float
    sector: str
    dividend_yield: float  # decimal fraction (0.005 = 0.5%), from TickerInfo
    exercise_style: ExerciseStyle  # for pricing dispatch (BAW vs BSM)
    data_timestamp: datetime

    # Scoring context (from TickerScore)
    composite_score: float = 0.0
    direction_signal: SignalDirection = SignalDirection.NEUTRAL

    # Key indicators (normalized 0-100, None = not computed)
    adx: float | None = None
    sma_alignment: float | None = None
    bb_width: float | None = None
    atr_pct: float | None = None
    stochastic_rsi: float | None = None
    relative_volume: float | None = None

    # Greeks beyond delta (from first recommended contract)
    target_gamma: float | None = None
    target_theta: float | None = None  # $/day time decay
    target_vega: float | None = None  # $/1% IV change
    target_rho: float | None = None

    # Contract pricing
    contract_mid: Decimal | None = None  # mid price of recommended contract

    # Short interest — from yfinance TickerInfo
    short_ratio: float | None = None  # days to cover
    short_pct_of_float: float | None = None  # decimal fraction (no upper bound — squeezes > 1.0)

    # OpenBB enrichment — fundamentals (from FundamentalSnapshot)
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    debt_to_equity: float | None = None
    revenue_growth: float | None = None
    profit_margin: float | None = None

    # OpenBB enrichment — unusual flow (from UnusualFlowSnapshot)
    net_call_premium: float | None = None
    net_put_premium: float | None = None
    options_put_call_ratio: float | None = None  # distinct from put_call_ratio (scan-derived)

    # OpenBB enrichment — news sentiment (from NewsSentimentSnapshot)
    news_sentiment: float | None = None  # -1.0 to 1.0
    news_sentiment_label: str | None = None  # "bullish"/"bearish"/"neutral"
    recent_headlines: list[str] | None = None  # up to 5 headline strings

    # --- Arena Recon: Analyst Intelligence ---
    analyst_target_mean: float | None = None
    analyst_target_upside_pct: float | None = None  # decimal fraction
    analyst_consensus_score: float | None = None  # [-1.0, 1.0]

    # --- Arena Recon: Analyst Activity ---
    analyst_upgrades_30d: int | None = None
    analyst_downgrades_30d: int | None = None

    # --- Arena Recon: Insider Activity ---
    insider_net_buys_90d: int | None = None

    # --- Arena Recon: Institutional Ownership ---
    insider_buy_ratio: float | None = None  # [0.0, 1.0]
    institutional_pct: float | None = None  # [0.0, 1.0]

    # --- DSE: Dimensional Scores (8 family sub-scores, 0-100) ---
    dim_trend: float | None = None
    dim_iv_vol: float | None = None
    dim_hv_vol: float | None = None
    dim_flow: float | None = None
    dim_microstructure: float | None = None
    dim_fundamental: float | None = None
    dim_regime: float | None = None
    dim_risk: float | None = None

    # --- DSE: High-Signal Individual Indicators ---
    vol_regime: float | None = None
    iv_hv_spread: float | None = None
    gex: float | None = None
    unusual_activity_score: float | None = None
    skew_ratio: float | None = None
    vix_term_structure: float | None = None
    market_regime: float | None = None
    rsi_divergence: float | None = None
    expected_move: float | None = None
    expected_move_ratio: float | None = None

    # --- DSE: Second-Order Greeks ---
    target_vanna: float | None = None
    target_charm: float | None = None
    target_vomma: float | None = None

    # --- DSE: Direction Confidence ---
    direction_confidence: float | None = None  # [0.0, 1.0]

    def completeness_ratio(self) -> float:
        """Fraction of optional context fields that are populated (not None).

        Checks ``float | None`` indicator and options-specific fields. Greeks
        fields (gamma, theta, vega, rho) are only included when a recommended
        contract exists (``contract_mid is not None``), so tickers without
        contracts are not penalised for inherently missing Greeks.

        Core identity fields (ticker, price, sector) and fields with meaningful
        defaults (rsi_14, composite_score) are excluded.

        Returns
        -------
        float
            Value in [0.0, 1.0]. 1.0 means all applicable optional fields are populated.
        """
        checkable_fields: list[float | None] = [
            self.iv_rank,
            self.iv_percentile,
            self.atm_iv_30d,
            self.put_call_ratio,
            self.max_pain_distance,
            self.adx,
            self.sma_alignment,
            self.bb_width,
            self.atr_pct,
            self.stochastic_rsi,
            self.relative_volume,
            self.short_ratio,
            self.short_pct_of_float,
        ]
        # Only count Greeks when contracts are available — without contracts,
        # Greeks are inherently absent and shouldn't lower the ratio.
        if self.contract_mid is not None:
            checkable_fields.extend(
                [
                    self.target_gamma,
                    self.target_theta,
                    self.target_vega,
                    self.target_rho,
                ]
            )
        if not checkable_fields:
            return 1.0
        populated = sum(1 for f in checkable_fields if f is not None)
        return populated / len(checkable_fields)

    def enrichment_ratio(self) -> float:
        """Fraction of OpenBB enrichment fields populated (0.0-1.0).

        Separate from ``completeness_ratio()`` so that OpenBB data doesn't
        penalise debates when the SDK is disabled or unavailable.
        """
        enrichment_fields: list[float | None] = [
            self.pe_ratio,
            self.forward_pe,
            self.peg_ratio,
            self.price_to_book,
            self.debt_to_equity,
            self.revenue_growth,
            self.profit_margin,
            self.net_call_premium,
            self.net_put_premium,
            self.options_put_call_ratio,
            self.news_sentiment,
        ]
        populated = sum(1 for f in enrichment_fields if f is not None)
        return populated / len(enrichment_fields)

    def intelligence_ratio(self) -> float:
        """Fraction of 8 intelligence fields populated (0.0-1.0).

        Separate from ``completeness_ratio()`` so that intelligence data
        doesn't penalise debates when intelligence fetching is disabled.
        """
        intel_fields: list[object] = [
            self.analyst_target_mean,
            self.analyst_target_upside_pct,
            self.analyst_consensus_score,
            self.analyst_upgrades_30d,
            self.analyst_downgrades_30d,
            self.insider_net_buys_90d,
            self.insider_buy_ratio,
            self.institutional_pct,
        ]
        populated = sum(1 for f in intel_fields if f is not None)
        return populated / len(intel_fields)

    def dse_ratio(self) -> float:
        """Fraction of 22 DSE fields populated (0.0-1.0).

        Separate from ``completeness_ratio()`` so that DSE data doesn't
        penalise debates for tickers not included in scan results.
        """
        dse_fields: list[float | None] = [
            self.dim_trend,
            self.dim_iv_vol,
            self.dim_hv_vol,
            self.dim_flow,
            self.dim_microstructure,
            self.dim_fundamental,
            self.dim_regime,
            self.dim_risk,
            self.vol_regime,
            self.iv_hv_spread,
            self.gex,
            self.unusual_activity_score,
            self.skew_ratio,
            self.vix_term_structure,
            self.market_regime,
            self.rsi_divergence,
            self.expected_move,
            self.expected_move_ratio,
            self.target_vanna,
            self.target_charm,
            self.target_vomma,
            self.direction_confidence,
        ]
        populated = sum(1 for f in dse_fields if f is not None)
        return populated / len(dse_fields)

    @field_validator("rsi_14", "target_delta", "dividend_yield", "composite_score")
    @classmethod
    def validate_required_finite(cls, v: float) -> float:
        """Reject NaN/Inf on required float fields."""
        if not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator(
        "iv_rank",
        "iv_percentile",
        "atm_iv_30d",
        "put_call_ratio",
        "max_pain_distance",
        "adx",
        "sma_alignment",
        "bb_width",
        "atr_pct",
        "stochastic_rsi",
        "relative_volume",
        "target_gamma",
        "target_theta",
        "target_vega",
        "target_rho",
        # Short interest
        "short_ratio",
        "short_pct_of_float",
        # OpenBB enrichment float fields
        "pe_ratio",
        "forward_pe",
        "peg_ratio",
        "price_to_book",
        "debt_to_equity",
        "revenue_growth",
        "profit_margin",
        "net_call_premium",
        "net_put_premium",
        "options_put_call_ratio",
        "news_sentiment",
        # Arena Recon intelligence float fields
        "analyst_target_mean",
        "analyst_target_upside_pct",
        "analyst_consensus_score",
        "insider_buy_ratio",
        "institutional_pct",
        # DSE dimensional scores
        "dim_trend",
        "dim_iv_vol",
        "dim_hv_vol",
        "dim_flow",
        "dim_microstructure",
        "dim_fundamental",
        "dim_regime",
        "dim_risk",
        # DSE high-signal indicators
        "vol_regime",
        "iv_hv_spread",
        "gex",
        "unusual_activity_score",
        "skew_ratio",
        "vix_term_structure",
        "market_regime",
        "rsi_divergence",
        "expected_move",
        "expected_move_ratio",
        # DSE second-order Greeks
        "target_vanna",
        "target_charm",
        "target_vomma",
        # DSE direction confidence
        "direction_confidence",
    )
    @classmethod
    def validate_optional_finite(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on optional float fields while allowing None."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"must be finite, got {v}")
        return v

    @field_validator("data_timestamp")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure data_timestamp is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("data_timestamp must be UTC")
        return v

    @field_serializer("current_price", "price_52w_high", "price_52w_low", "target_strike")
    def serialize_decimal(self, v: Decimal) -> str:
        """Serialize Decimal fields to str to avoid float precision loss in JSON."""
        return str(v)

    @field_serializer("contract_mid")
    def serialize_contract_mid(self, v: Decimal | None) -> str | None:
        """Serialize optional Decimal to str for JSON precision safety."""
        return str(v) if v is not None else None


class AgentResponse(BaseModel):
    """Structured response from a debate agent.

    Frozen (immutable after construction) -- represents a completed agent output.
    ``confidence`` is validated to be within [0.0, 1.0].
    """

    model_config = ConfigDict(frozen=True)

    agent_name: str  # "bull", "bear", "risk"
    direction: SignalDirection
    confidence: float  # 0.0 to 1.0
    argument: str
    key_points: list[str]
    risks_cited: list[str]
    contracts_referenced: list[str]  # specific strikes/expirations
    model_used: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        return validate_unit_interval(v, "confidence")

    @field_validator("key_points")
    @classmethod
    def validate_key_points(cls, v: list[str]) -> list[str]:
        """Ensure at least one key point is cited."""
        return validate_non_empty_list(v, "key_points")

    @field_validator("risks_cited")
    @classmethod
    def validate_risks_cited(cls, v: list[str]) -> list[str]:
        """Ensure at least one risk is cited."""
        return validate_non_empty_list(v, "risks_cited")


class TradeThesis(BaseModel):
    """Final trade recommendation produced by the debate system.

    Frozen (immutable after construction) -- represents a completed verdict.
    ``confidence`` is validated to be within [0.0, 1.0].
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    direction: SignalDirection
    confidence: float  # 0.0 to 1.0
    summary: str
    bull_score: float
    bear_score: float
    key_factors: list[str]
    risk_assessment: str
    recommended_strategy: SpreadType | None = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        return validate_unit_interval(v, "confidence")

    @field_validator("bull_score", "bear_score")
    @classmethod
    def validate_scores(cls, v: float) -> float:
        """Ensure bull/bear scores are finite and within [0.0, 10.0]."""
        if not math.isfinite(v):
            raise ValueError(f"score must be finite, got {v}")
        if not 0.0 <= v <= 10.0:
            raise ValueError(f"score must be in [0, 10], got {v}")
        return v

    @field_validator("key_factors")
    @classmethod
    def validate_key_factors(cls, v: list[str]) -> list[str]:
        """Ensure at least one key factor is cited."""
        return validate_non_empty_list(v, "key_factors")

    @model_validator(mode="after")
    def clamp_confidence_on_mismatch(self) -> Self:
        """Warn and clamp confidence when scores contradict direction.

        Uses ``object.__setattr__`` to mutate the frozen instance during validation —
        this is the standard Pydantic v2 pattern for frozen model validators.
        """
        clamped = self.confidence
        reason = ""

        if (
            self.bull_score > self.bear_score
            and self.direction == SignalDirection.BEARISH
            and self.confidence > 0.5
        ):
            clamped = 0.5
            reason = (
                f"bull_score ({self.bull_score}) > bear_score ({self.bear_score}) "
                f"but direction is BEARISH"
            )
        elif (
            self.bear_score > self.bull_score
            and self.direction == SignalDirection.BULLISH
            and self.confidence > 0.5
        ):
            clamped = 0.5
            reason = (
                f"bear_score ({self.bear_score}) > bull_score ({self.bull_score}) "
                f"but direction is BULLISH"
            )

        if max(self.bull_score, self.bear_score) < 4.0 and self.confidence > 0.5:
            clamped = min(clamped, 0.5)
            reason = reason or f"max score ({max(self.bull_score, self.bear_score)}) < 4.0"

        if clamped < self.confidence:
            logger.warning(
                "Clamping confidence for %s from %.2f to %.2f: %s",
                self.ticker,
                self.confidence,
                clamped,
                reason,
            )
            object.__setattr__(self, "confidence", clamped)
        return self


class VolatilityThesis(BaseModel):
    """Structured output from the Volatility Agent.

    Frozen (immutable after construction) -- represents a completed vol assessment.
    ``confidence`` is validated to be within [0.0, 1.0] with ``math.isfinite()`` guard.
    """

    model_config = ConfigDict(frozen=True)

    iv_assessment: VolAssessment
    iv_rank_interpretation: str  # Human-readable IV rank context
    confidence: float  # 0.0 to 1.0
    recommended_strategy: SpreadType | None = None
    strategy_rationale: str
    target_iv_entry: float | None = None
    target_iv_exit: float | None = None
    suggested_strikes: list[str]
    key_vol_factors: list[str]
    model_used: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        return validate_unit_interval(v, "confidence")

    @field_validator("target_iv_entry", "target_iv_exit")
    @classmethod
    def validate_iv_target(cls, v: float | None) -> float | None:
        """Ensure IV targets are finite and non-negative when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"IV target must be finite, got {v}")
            if v < 0.0:
                raise ValueError(f"IV target must be >= 0.0, got {v}")
        return v

    @field_validator("key_vol_factors")
    @classmethod
    def validate_key_vol_factors(cls, v: list[str]) -> list[str]:
        """Ensure at least one volatility factor is cited."""
        return validate_non_empty_list(v, "key_vol_factors")


class FlowThesis(BaseModel):
    """Structured output from the Flow Agent.

    Frozen (immutable after construction) -- represents a completed flow assessment.
    ``confidence`` is validated to be within [0.0, 1.0] with ``math.isfinite()`` guard.
    """

    model_config = ConfigDict(frozen=True)

    direction: SignalDirection
    confidence: float  # 0.0 to 1.0
    gex_interpretation: str
    smart_money_signal: str
    oi_analysis: str
    volume_confirmation: str
    key_flow_factors: list[str]
    model_used: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        return validate_unit_interval(v, "confidence")

    @field_validator("key_flow_factors")
    @classmethod
    def validate_key_flow_factors(cls, v: list[str]) -> list[str]:
        """Ensure at least one flow factor is cited."""
        return validate_non_empty_list(v, "key_flow_factors")


class RiskAssessment(BaseModel):
    """Expanded risk assessment output from the Risk Agent.

    Frozen (immutable after construction) -- represents a completed risk assessment.
    ``confidence`` is validated to be within [0.0, 1.0] with ``math.isfinite()`` guard.
    ``pop_estimate`` (probability of profit) is also validated to [0.0, 1.0] when provided.
    """

    model_config = ConfigDict(frozen=True)

    risk_level: RiskLevel
    confidence: float  # 0.0 to 1.0
    pop_estimate: float | None = None  # Probability of Profit
    max_loss_estimate: str
    charm_decay_warning: str | None = None
    spread_quality_assessment: str | None = None
    key_risks: list[str]
    risk_mitigants: list[str]  # intentionally allows empty — a risk may have no mitigants
    recommended_position_size: str | None = None
    model_used: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        return validate_unit_interval(v, "confidence")

    @field_validator("pop_estimate")
    @classmethod
    def validate_pop_estimate(cls, v: float | None) -> float | None:
        """Ensure pop_estimate is finite and within [0.0, 1.0] when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"pop_estimate must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"pop_estimate must be in [0, 1], got {v}")
        return v

    @field_validator("key_risks")
    @classmethod
    def validate_key_risks(cls, v: list[str]) -> list[str]:
        """Ensure at least one risk is cited."""
        return validate_non_empty_list(v, "key_risks")


class FundamentalThesis(BaseModel):
    """Structured output from the Fundamental Agent.

    Frozen (immutable after construction) -- represents a completed fundamental assessment.
    ``confidence`` is validated to be within [0.0, 1.0] with ``math.isfinite()`` guard.
    """

    model_config = ConfigDict(frozen=True)

    direction: SignalDirection
    confidence: float  # 0.0 to 1.0
    catalyst_impact: CatalystImpact
    earnings_assessment: str
    iv_crush_risk: str
    short_interest_analysis: str | None = None
    dividend_impact: str | None = None
    key_fundamental_factors: list[str]
    model_used: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        return validate_unit_interval(v, "confidence")

    @field_validator("key_fundamental_factors")
    @classmethod
    def validate_key_fundamental_factors(cls, v: list[str]) -> list[str]:
        """Ensure at least one fundamental factor is cited."""
        return validate_non_empty_list(v, "key_fundamental_factors")


class ContrarianThesis(BaseModel):
    """Structured output from the Contrarian Agent.

    Frozen (immutable after construction) -- represents a completed contrarian assessment.
    ``dissent_confidence`` is validated to be within [0.0, 1.0] with ``math.isfinite()`` guard.
    """

    model_config = ConfigDict(frozen=True)

    dissent_direction: SignalDirection  # the contrarian's opposing view
    dissent_confidence: float  # 0.0 to 1.0 -- strength of the dissent
    primary_challenge: str  # main argument against consensus
    overlooked_risks: list[str]
    consensus_weakness: str
    alternative_scenario: str
    model_used: str

    @field_validator("dissent_confidence")
    @classmethod
    def validate_dissent_confidence(cls, v: float) -> float:
        """Ensure dissent_confidence is finite and within [0.0, 1.0]."""
        return validate_unit_interval(v, "dissent_confidence")

    @field_validator("overlooked_risks")
    @classmethod
    def validate_overlooked_risks(cls, v: list[str]) -> list[str]:
        """Ensure at least one overlooked risk is cited."""
        return validate_non_empty_list(v, "overlooked_risks")


class ExtendedTradeThesis(TradeThesis):
    """Extended trade thesis with contrarian dissent, agreement scoring, and dimensional scores.

    Inherits all fields from TradeThesis. Adds DSE-specific fields.
    Frozen (inherited from TradeThesis).
    """

    contrarian_dissent: str | None = None
    agent_agreement_score: float | None = None  # 0.0-1.0, fraction of agents agreeing
    dissenting_agents: list[str] = Field(default_factory=list)
    dimensional_scores: DimensionalScores | None = None
    agents_completed: int = 0

    @field_validator("agents_completed")
    @classmethod
    def validate_agents_completed(cls, v: int) -> int:
        """Ensure agents_completed is non-negative and within reasonable bounds."""
        if not 0 <= v <= 20:
            raise ValueError(f"agents_completed must be in [0, 20], got {v}")
        return v

    @field_validator("agent_agreement_score")
    @classmethod
    def validate_agent_agreement_score(cls, v: float | None) -> float | None:
        """Ensure agent_agreement_score is finite and within [0.0, 1.0] when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"agent_agreement_score must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"agent_agreement_score must be in [0, 1], got {v}")
        return v
