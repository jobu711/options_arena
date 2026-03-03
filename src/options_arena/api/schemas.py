"""API-only request/response wrappers.

Thin wrappers added here as needed by route handlers.
Most responses use existing Pydantic models from ``models/`` directly.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from options_arena.models import (
    AgentResponse,
    GICSSector,
    MarketCapTier,
    ScanPreset,
    SentimentLabel,
    SignalDirection,
    TradeThesis,
)
from options_arena.models.enums import SECTOR_ALIASES

# Ticker: at least one alphanumeric required; allows caret prefix for indices
_TICKER_PATTERN = r"^(?=.*[A-Z0-9])[A-Z0-9^][A-Z0-9.\-^]{0,9}$"
_TICKER_RE = re.compile(_TICKER_PATTERN)

# ---------------------------------------------------------------------------
# Scan schemas (#126, #162)
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    """Request body for ``POST /api/scan``."""

    preset: ScanPreset = ScanPreset.SP500
    sectors: list[GICSSector] = []
    market_cap_tiers: list[MarketCapTier] = []
    exclude_near_earnings_days: int | None = None
    direction_filter: SignalDirection | None = None
    min_iv_rank: float | None = None

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
    contracts: list[str]  # Contract identifiers — empty until contracts are persisted


# ---------------------------------------------------------------------------
# Debate schemas (#123)
# ---------------------------------------------------------------------------


class DebateRequest(BaseModel):
    """Request body for ``POST /api/debate``."""

    ticker: str = Field(min_length=1, max_length=10)
    scan_id: int | None = None

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        """Uppercase and strip whitespace before pattern validation."""
        if not isinstance(v, str):
            raise ValueError("ticker must be a string")
        v = v.upper().strip()
        if not _TICKER_RE.match(v):
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
            if not _TICKER_RE.match(normalized):
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


# ---------------------------------------------------------------------------
# Watchlist schemas (#144)
# ---------------------------------------------------------------------------


class WatchlistCreateRequest(BaseModel):
    """Request body for ``POST /api/watchlist``."""

    name: str


class WatchlistCreateResponse(BaseModel):
    """Response for ``POST /api/watchlist`` (201)."""

    id: int
    name: str


class WatchlistTickerRequest(BaseModel):
    """Request body for ``POST /api/watchlist/{id}/tickers``."""

    ticker: str = Field(min_length=1, max_length=10)

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        """Uppercase and strip whitespace before pattern validation."""
        if not isinstance(v, str):
            raise ValueError("ticker must be a string")
        v = v.upper().strip()
        if not _TICKER_RE.match(v):
            raise ValueError(
                f"Invalid ticker format: {v!r}. "
                "Must be 1-10 characters: A-Z, 0-9, dots, hyphens, or caret."
            )
        return v


class ConfigResponse(BaseModel):
    """Read-only safe config values (no secrets)."""

    groq_api_key_set: bool
    scan_preset_default: str
    enable_rebuttal: bool
    enable_volatility_agent: bool
    agent_timeout: float


class WatchlistTickerAddedResponse(BaseModel):
    """Response for adding a ticker to a watchlist."""

    status: str
    ticker: str


class CancelScanResponse(BaseModel):
    """Response for cancelling a scan."""

    status: str


class SectorInfo(BaseModel):
    """Sector name with count of tickers in that sector."""

    name: str
    ticker_count: int


class UniverseStats(BaseModel):
    """Universe statistics."""

    optionable_count: int
    sp500_count: int
    etf_count: int = 0


# ---------------------------------------------------------------------------
# Analytics schemas (#210-#213)
# ---------------------------------------------------------------------------


class OutcomeCollectionResult(BaseModel):
    """Response for ``POST /api/analytics/collect-outcomes`` (202)."""

    outcomes_collected: int
