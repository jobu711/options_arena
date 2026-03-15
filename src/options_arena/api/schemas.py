"""API-only request/response wrappers.

Thin wrappers added here as needed by route handlers.
Most responses use existing Pydantic models from ``models/`` directly.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from options_arena.models import (
    INDUSTRY_GROUP_ALIASES,
    SECTOR_ALIASES,
    TICKER_RE,
    AgentResponse,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    GICSIndustryGroup,
    GICSSector,
    MarketCapTier,
    RecommendedContract,
    RiskAssessment,
    ScanPreset,
    ScanSource,
    SentimentLabel,
    SignalDirection,
    SpreadAnalysis,
    TradeThesis,
)

# ---------------------------------------------------------------------------
# Scan schemas (#126, #162)
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    """Request body for ``POST /api/scan``."""

    preset: ScanPreset = ScanPreset.SP500
    sectors: list[GICSSector] = []
    industry_groups: list[GICSIndustryGroup] = []
    market_cap_tiers: list[MarketCapTier] = []
    exclude_near_earnings_days: int | None = None
    direction_filter: SignalDirection | None = None
    min_iv_rank: float | None = None
    custom_tickers: list[str] = []
    min_price: float | None = None
    max_price: float | None = None
    min_dte: int | None = None
    max_dte: int | None = None
    min_score: float | None = None
    min_direction_confidence: float | None = None
    top_n: int | None = None
    min_dollar_volume: float | None = None
    min_oi: int | None = None
    min_volume: int | None = None
    max_spread_pct: float | None = None
    delta_primary_min: float | None = None
    delta_primary_max: float | None = None
    delta_fallback_min: float | None = None
    delta_fallback_max: float | None = None
    source: ScanSource = ScanSource.MANUAL

    @field_validator("min_price", "max_price")
    @classmethod
    def validate_price_fields(cls, v: float | None) -> float | None:
        """Ensure price fields are finite and positive when set."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"price must be finite, got {v}")
            if v <= 0.0:
                raise ValueError(f"price must be positive, got {v}")
        return v

    @field_validator("min_score")
    @classmethod
    def validate_min_score(cls, v: float | None) -> float | None:
        """Ensure min_score is finite and non-negative when set."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"min_score must be finite, got {v}")
            if v < 0.0:
                raise ValueError(f"min_score must be non-negative, got {v}")
        return v

    @field_validator("min_direction_confidence")
    @classmethod
    def validate_min_direction_confidence(cls, v: float | None) -> float | None:
        """Ensure min_direction_confidence is finite and in [0.0, 1.0] when set."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"min_direction_confidence must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"min_direction_confidence must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("top_n")
    @classmethod
    def validate_top_n(cls, v: int | None) -> int | None:
        """Ensure top_n is at least 1 when set."""
        if v is not None and v < 1:
            raise ValueError(f"top_n must be >= 1, got {v}")
        return v

    @field_validator("min_dollar_volume")
    @classmethod
    def validate_min_dollar_volume(cls, v: float | None) -> float | None:
        """Ensure min_dollar_volume is finite and non-negative when set."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"min_dollar_volume must be finite, got {v}")
            if v < 0.0:
                raise ValueError(f"min_dollar_volume must be non-negative, got {v}")
        return v

    @field_validator("min_oi", "min_volume")
    @classmethod
    def validate_non_negative_int(cls, v: int | None) -> int | None:
        """Ensure min_oi and min_volume are non-negative when set."""
        if v is not None and v < 0:
            raise ValueError(f"value must be non-negative, got {v}")
        return v

    @field_validator("max_spread_pct")
    @classmethod
    def validate_max_spread_pct(cls, v: float | None) -> float | None:
        """Ensure max_spread_pct is finite and non-negative when set."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"max_spread_pct must be finite, got {v}")
            if v < 0.0:
                raise ValueError(f"max_spread_pct must be non-negative, got {v}")
        return v

    @field_validator(
        "delta_primary_min",
        "delta_primary_max",
        "delta_fallback_min",
        "delta_fallback_max",
    )
    @classmethod
    def validate_delta(cls, v: float | None) -> float | None:
        """Ensure delta fields are finite and in [0.0, 1.0] when set."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"delta must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"delta must be in [0.0, 1.0], got {v}")
        return v

    @field_validator("min_dte", "max_dte")
    @classmethod
    def validate_dte_fields(cls, v: int | None) -> int | None:
        """Ensure DTE values are positive when set."""
        if v is not None and v <= 0:
            raise ValueError(f"DTE must be positive, got {v}")
        return v

    @model_validator(mode="after")
    def validate_cross_field_ranges(self) -> Self:
        """Reject min > max for price, DTE, and delta ranges when both are set."""
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError(
                f"min_price ({self.min_price}) must not exceed max_price ({self.max_price})"
            )
        if self.min_dte is not None and self.max_dte is not None and self.min_dte > self.max_dte:
            raise ValueError(f"min_dte ({self.min_dte}) must not exceed max_dte ({self.max_dte})")
        if (
            self.delta_primary_min is not None
            and self.delta_primary_max is not None
            and self.delta_primary_min > self.delta_primary_max
        ):
            raise ValueError(
                f"delta_primary_min ({self.delta_primary_min}) must not exceed "
                f"delta_primary_max ({self.delta_primary_max})"
            )
        if (
            self.delta_fallback_min is not None
            and self.delta_fallback_max is not None
            and self.delta_fallback_min > self.delta_fallback_max
        ):
            raise ValueError(
                f"delta_fallback_min ({self.delta_fallback_min}) must not exceed "
                f"delta_fallback_max ({self.delta_fallback_max})"
            )
        return self

    @field_validator("market_cap_tiers", mode="before")
    @classmethod
    def deduplicate_market_cap_tiers(
        cls,
        v: list[str | MarketCapTier],
    ) -> list[MarketCapTier]:
        """Deduplicate market cap tier inputs."""
        result: list[MarketCapTier] = []
        for item in v:
            if isinstance(item, MarketCapTier):
                result.append(item)
            else:
                result.append(MarketCapTier(str(item).strip().lower()))
        return list(dict.fromkeys(result))

    @field_validator("sectors", mode="before")
    @classmethod
    def normalize_sectors(cls, v: list[str | GICSSector]) -> list[GICSSector]:
        """Normalize sector input strings via SECTOR_ALIASES.

        Same alias resolution as ``ScanConfig.normalize_sectors`` — accepts
        canonical enum values, lowercase names, hyphenated, underscored,
        and short-name variants. Raises ValueError for unrecognised inputs.
        """
        result: list[GICSSector] = []
        for item in v:
            if isinstance(item, GICSSector):
                result.append(item)
                continue
            # Normalize: lowercase, strip whitespace
            key = str(item).strip().lower()
            if key in SECTOR_ALIASES:
                result.append(SECTOR_ALIASES[key])
            else:
                # Try direct enum construction (handles canonical values)
                try:
                    result.append(GICSSector(str(item).strip()))
                except ValueError:
                    valid = sorted({s.value for s in GICSSector})
                    raise ValueError(
                        f"Unknown sector {item!r}. Valid sectors: {', '.join(valid)}"
                    ) from None
        return list(dict.fromkeys(result))

    @field_validator("industry_groups", mode="before")
    @classmethod
    def normalize_industry_groups(
        cls,
        v: list[str | GICSIndustryGroup],
    ) -> list[GICSIndustryGroup]:
        """Normalize industry group input strings via INDUSTRY_GROUP_ALIASES.

        Same alias resolution as ``ScanConfig.normalize_industry_groups`` — accepts
        canonical enum values, lowercase names, and short-name variants.
        Raises ValueError for unrecognised inputs.
        """
        result: list[GICSIndustryGroup] = []
        for item in v:
            if isinstance(item, GICSIndustryGroup):
                result.append(item)
                continue
            key = str(item).strip().lower()
            if key in INDUSTRY_GROUP_ALIASES:
                result.append(INDUSTRY_GROUP_ALIASES[key])
            else:
                try:
                    result.append(GICSIndustryGroup(str(item).strip()))
                except ValueError:
                    valid = sorted({ig.value for ig in GICSIndustryGroup})
                    raise ValueError(
                        f"Unknown industry group {item!r}. Valid groups: {', '.join(valid)}"
                    ) from None
        return list(dict.fromkeys(result))

    @field_validator("custom_tickers", mode="before")
    @classmethod
    def validate_custom_tickers(cls, v: list[str]) -> list[str]:
        """Uppercase, strip, validate format, deduplicate, and cap at 200."""
        result: list[str] = []
        for item in v:
            if not isinstance(item, str):
                raise ValueError(f"each custom ticker must be a string, got {type(item).__name__}")
            normalized = item.upper().strip()
            if not TICKER_RE.match(normalized):
                raise ValueError(
                    f"Invalid ticker format: {normalized!r}. "
                    "Must be 1-10 characters: A-Z, 0-9, dots, hyphens, or caret."
                )
            result.append(normalized)
        result = list(dict.fromkeys(result))
        if len(result) > 200:
            raise ValueError(f"custom_tickers exceeds 200 tickers ({len(result)})")
        return result


class ScanStarted(BaseModel):
    """Response for ``POST /api/scan`` (202)."""

    scan_id: int


class PaginatedResponse[T](BaseModel):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    pages: int


class TickerDetail(BaseModel):
    """Single ticker detail: score + recommended contracts."""

    ticker: str
    composite_score: float
    direction: SignalDirection
    contracts: list[RecommendedContract]
    spread: SpreadDetail | None = None

    @field_validator("composite_score")
    @classmethod
    def _validate_composite_score(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"composite_score must be finite, got {v}")
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"composite_score must be in [0, 100], got {v}")
        return v


# ---------------------------------------------------------------------------
# Spread schemas (#521)
# ---------------------------------------------------------------------------

_UNLIMITED_SENTINEL = "999999.99"


class SpreadLegDetail(BaseModel):
    """Individual leg in a spread strategy."""

    option_type: str
    strike: str  # Decimal as string for precision
    expiration: str
    side: str  # "long" or "short"
    quantity: int
    bid: str | None = None
    ask: str | None = None
    delta: float | None = None

    @field_validator("delta")
    @classmethod
    def _validate_delta(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("delta must be finite")
        return v


class SpreadDetail(BaseModel):
    """Spread strategy recommendation with P&L analytics."""

    spread_type: str
    legs: list[SpreadLegDetail]
    net_premium: str  # Decimal as string
    max_profit: str
    max_loss: str
    risk_reward_ratio: float | None = None
    pop_estimate: float | None = None
    breakevens: list[str]
    strategy_rationale: str

    @field_validator("risk_reward_ratio", "pop_estimate")
    @classmethod
    def _validate_finite(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("value must be finite")
        return v


def spread_detail_from_analysis(analysis: SpreadAnalysis) -> SpreadDetail:
    """Convert a ``SpreadAnalysis`` model to an API ``SpreadDetail`` response.

    Handles the ``Decimal("999999.99")`` sentinel for unlimited max profit
    by converting it to the string ``"Unlimited"``.

    Args:
        analysis: The spread analysis from the scoring/data layer.

    Returns:
        API-facing ``SpreadDetail`` with string-encoded Decimal values.
    """
    legs: list[SpreadLegDetail] = []
    for leg in analysis.spread.legs:
        contract = leg.contract
        greeks = contract.greeks
        legs.append(
            SpreadLegDetail(
                option_type=contract.option_type.value,
                strike=str(contract.strike),
                expiration=str(contract.expiration),
                side=leg.side.value,
                quantity=leg.quantity,
                bid=str(contract.bid) if contract.bid else None,
                ask=str(contract.ask) if contract.ask else None,
                delta=greeks.delta if greeks is not None else None,
            )
        )

    max_profit_str = (
        "Unlimited"
        if str(analysis.max_profit) == _UNLIMITED_SENTINEL
        else str(analysis.max_profit)
    )

    rr = analysis.risk_reward_ratio if math.isfinite(analysis.risk_reward_ratio) else None
    pop = analysis.pop_estimate if math.isfinite(analysis.pop_estimate) else None

    return SpreadDetail(
        spread_type=analysis.spread.spread_type.value,
        legs=legs,
        net_premium=str(analysis.net_premium),
        max_profit=max_profit_str,
        max_loss=str(analysis.max_loss),
        risk_reward_ratio=rr,
        pop_estimate=pop,
        breakevens=[str(b) for b in analysis.breakevens],
        strategy_rationale=analysis.strategy_rationale,
    )


# ---------------------------------------------------------------------------
# Debate schemas (#123)
# ---------------------------------------------------------------------------


class DebateRequest(BaseModel):
    """Request body for ``POST /api/debate``."""

    ticker: str = Field(min_length=1, max_length=10)
    scan_id: int | None = None
    enable_rebuttal: bool | None = None
    enable_volatility_agent: bool | None = None

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        """Uppercase and strip whitespace before pattern validation."""
        if not isinstance(v, str):
            raise ValueError("ticker must be a string")
        v = v.upper().strip()
        if not TICKER_RE.match(v):
            raise ValueError(
                f"Invalid ticker format: {v!r}. "
                "Must be 1-10 characters: A-Z, 0-9, dots, hyphens, or caret."
            )
        return v


class DebateStarted(BaseModel):
    """Response for ``POST /api/debate`` (202)."""

    debate_id: int


class DebateResultSummary(BaseModel):
    """Lightweight debate summary for list endpoint."""

    model_config = ConfigDict(frozen=True)

    id: int
    ticker: str
    direction: SignalDirection
    confidence: float
    is_fallback: bool
    model_name: str
    duration_ms: int
    created_at: datetime

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("confidence must be finite")
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v

    @field_validator("created_at")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("must be UTC")
        return v


class DebateResultDetail(BaseModel):
    """Full debate result returned by ``GET /api/debate/{id}``.

    Includes DSE fields from 6-agent protocol. These are None/empty
    for legacy debates.
    """

    id: int
    ticker: str
    is_fallback: bool
    model_name: str
    duration_ms: int
    total_tokens: int
    created_at: datetime
    debate_mode: str | None = None
    citation_density: float | None = None
    bull_response: AgentResponse | None = None
    bear_response: AgentResponse | None = None
    thesis: TradeThesis | None = None
    vol_response: str | None = None
    bull_rebuttal: str | None = None
    # DSE fields from 6-agent protocol
    contrarian_dissent: str | None = None
    agent_agreement_score: float | None = None
    dissenting_agents: list[str] = Field(default_factory=list)
    agents_completed: int | None = None
    # Agent structured outputs (6-agent protocol)
    flow_response: FlowThesis | None = None
    fundamental_response: FundamentalThesis | None = None
    risk_response: RiskAssessment | None = None
    contrarian_response: ContrarianThesis | None = None
    # Scan linkage
    scan_run_id: int | None = None
    # OpenBB enrichment (extracted from MarketContext)
    pe_ratio: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    price_to_book: float | None = None
    debt_to_equity: float | None = None
    revenue_growth: float | None = None
    profit_margin: float | None = None
    net_call_premium: float | None = None
    net_put_premium: float | None = None
    news_sentiment_score: float | None = None
    news_sentiment_label: SentimentLabel | None = None
    enrichment_ratio: float | None = None
    # Native Quant: HV & vol surface metrics (extracted from MarketContext)
    hv_yang_zhang: float | None = None
    skew_25d: float | None = None
    smile_curvature: float | None = None
    prob_above_current: float | None = None
    # Native Quant: second-order Greeks on target contract (from MarketContext)
    target_vanna: float | None = None
    target_charm: float | None = None
    target_vomma: float | None = None
    # Volatility Intelligence: Surface Mispricing (from MarketContext)
    iv_surface_residual: float | None = None
    surface_fit_r2: float | None = None
    surface_is_1d: bool | None = None
    # Spread strategy (#521)
    spread: SpreadDetail | None = None

    @field_validator(
        "pe_ratio",
        "forward_pe",
        "peg_ratio",
        "price_to_book",
        "debt_to_equity",
        "revenue_growth",
        "profit_margin",
        "net_call_premium",
        "net_put_premium",
        "news_sentiment_score",
        "enrichment_ratio",
        "citation_density",
        "agent_agreement_score",
        "hv_yang_zhang",
        "skew_25d",
        "smile_curvature",
        "prob_above_current",
        "target_vanna",
        "target_charm",
        "target_vomma",
        "iv_surface_residual",
        "surface_fit_r2",
    )
    @classmethod
    def _validate_finite(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("value must be finite")
        return v

    @field_validator("prob_above_current")
    @classmethod
    def _validate_prob_above_current(cls, v: float | None) -> float | None:
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("prob_above_current must be between 0.0 and 1.0")
        return v

    @field_validator("surface_fit_r2")
    @classmethod
    def _validate_surface_fit_r2(cls, v: float | None) -> float | None:
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("surface_fit_r2 must be between 0.0 and 1.0")
        return v

    @field_validator("created_at")
    @classmethod
    def _validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("must be UTC")
        return v


# ---------------------------------------------------------------------------
# Batch debate schemas (#127)
# ---------------------------------------------------------------------------


class BatchDebateRequest(BaseModel):
    """Request body for ``POST /api/debate/batch``."""

    scan_id: int
    limit: int = 5
    tickers: list[str] | None = Field(default=None, max_length=50)

    @field_validator("tickers", mode="before")
    @classmethod
    def normalize_tickers(cls, v: list[str] | None) -> list[str] | None:
        """Uppercase, strip, and validate each ticker in the batch list."""
        if v is None:
            return None
        result: list[str] = []
        for item in v:
            if not isinstance(item, str):
                raise ValueError("each ticker must be a string")
            normalized = item.upper().strip()
            if not TICKER_RE.match(normalized):
                raise ValueError(
                    f"Invalid ticker format: {normalized!r}. "
                    "Must be 1-10 characters: A-Z, 0-9, dots, hyphens, or caret."
                )
            result.append(normalized)
        return result


class BatchDebateStarted(BaseModel):
    """Response for ``POST /api/debate/batch`` (202)."""

    batch_id: int
    tickers: list[str]


class BatchTickerResult(BaseModel):
    """Per-ticker result summary in batch completion event."""

    ticker: str
    debate_id: int | None = None
    direction: SignalDirection | None = None
    confidence: float | None = None
    error: str | None = None

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float | None) -> float | None:
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"confidence must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v


# ---------------------------------------------------------------------------
# Supporting page schemas (#129)
# ---------------------------------------------------------------------------


class ConfigResponse(BaseModel):
    """Read-only safe config values (no secrets)."""

    groq_api_key_set: bool
    scan_preset_default: str
    enable_rebuttal: bool
    enable_volatility_agent: bool
    agent_timeout: float


class CancelScanResponse(BaseModel):
    """Response for cancelling a scan."""

    status: str


class SectorInfo(BaseModel):
    """Sector name with count of tickers in that sector."""

    name: str
    ticker_count: int


class IndustryGroupInfo(BaseModel):
    """Industry group with ticker count."""

    name: str
    ticker_count: int


class SectorHierarchy(BaseModel):
    """Sector with nested industry groups."""

    name: str
    ticker_count: int
    industry_groups: list[IndustryGroupInfo]


class UniverseStats(BaseModel):
    """Universe statistics."""

    optionable_count: int
    sp500_count: int
    etf_count: int = 0


# ---------------------------------------------------------------------------
# Analytics schemas (#210-#213)
# ---------------------------------------------------------------------------


class OperationStatus(BaseModel):
    """Response for ``GET /api/status`` — current system operation state."""

    busy: bool
    active_scan_ids: list[int] = []
    active_debate_ids: list[int] = []


class OutcomeCollectionResult(BaseModel):
    """Response for ``POST /api/analytics/collect-outcomes`` (202)."""

    outcomes_collected: int


# ---------------------------------------------------------------------------
# Metadata index schemas (#274)
# ---------------------------------------------------------------------------


class MetadataStats(BaseModel):
    """Metadata coverage statistics."""

    total: int
    with_sector: int
    with_industry_group: int
    coverage: float  # with_sector / total, 0.0 if total == 0

    @field_validator("coverage")
    @classmethod
    def _validate_coverage(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"coverage must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"coverage must be in [0, 1], got {v}")
        return v


class IndexStarted(BaseModel):
    """Response for ``POST /api/universe/index`` (202)."""

    index_task_id: int


# ---------------------------------------------------------------------------
# Pre-scan preset schemas (#285)
# ---------------------------------------------------------------------------


class PresetInfo(BaseModel):
    """Describes a scan preset for the frontend preset picker."""

    preset: ScanPreset
    label: str
    description: str
    estimated_count: int


# ---------------------------------------------------------------------------
# Heatmap schemas (#367)
# ---------------------------------------------------------------------------


class HeatmapTicker(BaseModel):
    """Single ticker entry for the S&P 500 heatmap treemap.

    Frozen (immutable) — represents a point-in-time snapshot for rendering.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    company_name: str
    sector: str
    industry_group: str
    market_cap_weight: float
    change_pct: float | None
    price: Decimal
    volume: int

    @field_validator("market_cap_weight")
    @classmethod
    def _validate_market_cap_weight(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("market_cap_weight must be finite")
        if v < 0:
            raise ValueError("market_cap_weight must be non-negative")
        return v

    @field_validator("price")
    @classmethod
    def _validate_price(cls, v: Decimal) -> Decimal:
        if not math.isfinite(float(v)):
            raise ValueError("price must be finite")
        if v <= 0:
            raise ValueError("price must be positive")
        return v

    @field_validator("change_pct")
    @classmethod
    def _validate_change_pct(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("change_pct must be finite")
        return v
