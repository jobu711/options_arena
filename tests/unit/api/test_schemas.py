"""Tests for API schemas."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from options_arena.api.schemas import (
    ConfigResponse,
    DebateRequest,
    DebateResultSummary,
    DebateStarted,
    PaginatedResponse,
    ScanRequest,
    ScanStarted,
    TickerDetail,
    UniverseStats,
)
from options_arena.models import ScanPreset, SignalDirection


def test_scan_request_default_preset() -> None:
    """ScanRequest defaults to SP500."""
    req = ScanRequest()
    assert req.preset == ScanPreset.SP500


def test_scan_request_custom_preset() -> None:
    """ScanRequest accepts custom preset."""
    req = ScanRequest(preset=ScanPreset.FULL)
    assert req.preset == ScanPreset.FULL


def test_scan_started() -> None:
    """ScanStarted holds scan_id."""
    resp = ScanStarted(scan_id=42)
    assert resp.scan_id == 42


def test_paginated_response() -> None:
    """PaginatedResponse serializes correctly."""
    resp = PaginatedResponse[str](items=["a", "b"], total=5, page=1, pages=3)
    assert resp.total == 5
    assert len(resp.items) == 2


def test_ticker_detail() -> None:
    """TickerDetail holds score + contracts."""
    detail = TickerDetail(
        ticker="AAPL",
        composite_score=78.5,
        direction=SignalDirection.BULLISH,
        contracts=[],
    )
    assert detail.ticker == "AAPL"


def test_debate_request() -> None:
    """DebateRequest with ticker and optional scan_id."""
    req = DebateRequest(ticker="AAPL")
    assert req.ticker == "AAPL"
    assert req.scan_id is None

    req2 = DebateRequest(ticker="MSFT", scan_id=5)
    assert req2.scan_id == 5


def test_debate_started() -> None:
    """DebateStarted holds debate_id."""
    resp = DebateStarted(debate_id=7)
    assert resp.debate_id == 7


def test_debate_result_summary() -> None:
    """DebateResultSummary is frozen."""
    summary = DebateResultSummary(
        id=1,
        ticker="AAPL",
        direction="bullish",
        confidence=0.75,
        is_fallback=False,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        created_at=datetime(2026, 2, 26, tzinfo=UTC),
    )
    assert summary.ticker == "AAPL"
    # Frozen model
    with pytest.raises(ValidationError):
        summary.ticker = "MSFT"  # type: ignore[misc]


def test_config_response() -> None:
    """ConfigResponse holds safe config values."""
    resp = ConfigResponse(
        groq_api_key_set=True,
        scan_preset_default="sp500",
        enable_rebuttal=False,
        enable_volatility_agent=False,
        agent_timeout=60.0,
    )
    assert resp.groq_api_key_set is True
    assert resp.agent_timeout == 60.0


def test_universe_stats() -> None:
    """UniverseStats holds counts."""
    stats = UniverseStats(optionable_count=5000, sp500_count=500)
    assert stats.optionable_count == 5000


def test_scan_request_json_roundtrip() -> None:
    """ScanRequest survives JSON roundtrip."""
    req = ScanRequest(preset=ScanPreset.SP500)
    json_str = req.model_dump_json()
    rebuilt = ScanRequest.model_validate_json(json_str)
    assert rebuilt.preset == req.preset


def test_debate_result_summary_json_roundtrip() -> None:
    """DebateResultSummary survives JSON roundtrip."""
    summary = DebateResultSummary(
        id=1,
        ticker="AAPL",
        direction="bullish",
        confidence=0.75,
        is_fallback=False,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        created_at=datetime(2026, 2, 26, tzinfo=UTC),
    )
    json_str = summary.model_dump_json()
    rebuilt = DebateResultSummary.model_validate_json(json_str)
    assert rebuilt == summary
