"""API-only request/response wrappers.

Thin wrappers added here as needed by route handlers.
Most responses use existing Pydantic models from ``models/`` directly.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from options_arena.models import (
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
    TradeThesis,
)
from options_arena.models.enums import INDUSTRY_GROUP_ALIASES, SECTOR_ALIASES

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

    @field_validator("min_dte", "max_dte")
    @classmethod
    def validate_dte_fields(cls, v: int | None) -> int | None:
        """Ensure DTE values are positive when set."""
        if v is not None and v <= 0:
            raise ValueError(f"DTE must be positive, got {v}")
        return v

    @model_validator(mode="after")
    def validate_cross_field_ranges(self) -> Self:
        """Reject min > max for price and DTE when both are set."""
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
    direction: str
    confidence: float
    is_fallback: bool
    model_name: str
    duration_ms: int
    created_at: datetime


class DebateResultDetail(BaseModel):
    """Full debate result returned by ``GET /api/debate/{id}``.

    Includes DSE fields from 6-agent protocol (v2). These are None/empty
    for legacy 4-agent debates.
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
    # DSE fields from 6-agent protocol (v2)
    contrarian_dissent: str | None = None
    agent_agreement_score: float | None = None
    dissenting_agents: list[str] = Field(default_factory=list)
    agents_completed: int | None = None
    # v2 agent structured outputs (6-agent protocol)
    flow_response: FlowThesis | None = None
    fundamental_response: FundamentalThesis | None = None
    risk_v2_response: RiskAssessment | None = None
    contrarian_response: ContrarianThesis | None = None
    debate_protocol: str | None = None
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
    direction: str | None = None
    confidence: float | None = None
    error: str | None = None


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
