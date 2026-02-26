"""API-only request/response wrappers.

Thin wrappers added here as needed by route handlers.
Most responses use existing Pydantic models from ``models/`` directly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from options_arena.models import ScanPreset, SignalDirection

# ---------------------------------------------------------------------------
# Scan schemas (#126)
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    """Request body for ``POST /api/scan``."""

    preset: ScanPreset = ScanPreset.SP500


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
    contracts: list[dict[str, object]]


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


class UniverseStats(BaseModel):
    """Universe statistics."""

    optionable_count: int
    sp500_count: int
