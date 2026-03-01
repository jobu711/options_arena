"""API-only request/response wrappers.

Thin wrappers added here as needed by route handlers.
Most responses use existing Pydantic models from ``models/`` directly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from options_arena.models import (
    AgentResponse,
    GICSSector,
    ScanPreset,
    SignalDirection,
    TradeThesis,
)
from options_arena.models.enums import SECTOR_ALIASES

# ---------------------------------------------------------------------------
# Scan schemas (#126, #162)
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    """Request body for ``POST /api/scan``."""

    preset: ScanPreset = ScanPreset.SP500
    sectors: list[GICSSector] = []

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

    ticker: str
    scan_id: int | None = None


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


# ---------------------------------------------------------------------------
# Batch debate schemas (#127)
# ---------------------------------------------------------------------------


class BatchDebateRequest(BaseModel):
    """Request body for ``POST /api/debate/batch``."""

    scan_id: int
    limit: int = 5
    tickers: list[str] | None = None


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

    ticker: str


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
