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
    SectorInfo,
    TickerDetail,
    UniverseStats,
)
from options_arena.models import GICSSector, ScanPreset, SignalDirection


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
    """UniverseStats holds counts including etf_count."""
    stats = UniverseStats(optionable_count=5000, sp500_count=500)
    assert stats.optionable_count == 5000
    # etf_count defaults to 0
    assert stats.etf_count == 0


def test_universe_stats_with_etf_count() -> None:
    """UniverseStats includes etf_count when provided."""
    stats = UniverseStats(optionable_count=5000, sp500_count=500, etf_count=42)
    assert stats.etf_count == 42


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


# ---------------------------------------------------------------------------
# ScanRequest sector validation (#162)
# ---------------------------------------------------------------------------


def test_scan_request_default_sectors_empty() -> None:
    """ScanRequest defaults to empty sectors list."""
    req = ScanRequest()
    assert req.sectors == []


def test_scan_request_sectors_canonical_name() -> None:
    """ScanRequest accepts canonical GICS sector names."""
    req = ScanRequest(sectors=["Information Technology", "Energy"])
    assert GICSSector.INFORMATION_TECHNOLOGY in req.sectors
    assert GICSSector.ENERGY in req.sectors
    assert len(req.sectors) == 2


def test_scan_request_sectors_alias_normalization() -> None:
    """ScanRequest normalizes sector aliases (technology -> Information Technology)."""
    req = ScanRequest(sectors=["technology", "healthcare"])
    assert GICSSector.INFORMATION_TECHNOLOGY in req.sectors
    assert GICSSector.HEALTH_CARE in req.sectors


def test_scan_request_sectors_short_names() -> None:
    """ScanRequest normalizes short names: tech, telecom, staples."""
    req = ScanRequest(sectors=["tech", "telecom", "staples"])
    assert GICSSector.INFORMATION_TECHNOLOGY in req.sectors
    assert GICSSector.COMMUNICATION_SERVICES in req.sectors
    assert GICSSector.CONSUMER_STAPLES in req.sectors


def test_scan_request_sectors_hyphenated() -> None:
    """ScanRequest normalizes hyphenated variants."""
    req = ScanRequest(sectors=["health-care", "real-estate"])
    assert GICSSector.HEALTH_CARE in req.sectors
    assert GICSSector.REAL_ESTATE in req.sectors


def test_scan_request_sectors_underscored() -> None:
    """ScanRequest normalizes underscored variants."""
    req = ScanRequest(sectors=["information_technology", "consumer_discretionary"])
    assert GICSSector.INFORMATION_TECHNOLOGY in req.sectors
    assert GICSSector.CONSUMER_DISCRETIONARY in req.sectors


def test_scan_request_sectors_invalid_raises_422() -> None:
    """ScanRequest rejects invalid sector names with clear error."""
    with pytest.raises(ValidationError, match="Unknown sector"):
        ScanRequest(sectors=["nonexistent_sector"])


def test_scan_request_sectors_enum_passthrough() -> None:
    """ScanRequest accepts GICSSector enum values directly."""
    req = ScanRequest(sectors=[GICSSector.ENERGY, GICSSector.UTILITIES])
    assert req.sectors == [GICSSector.ENERGY, GICSSector.UTILITIES]


def test_scan_request_sectors_json_roundtrip() -> None:
    """ScanRequest with sectors survives JSON roundtrip."""
    req = ScanRequest(preset=ScanPreset.SP500, sectors=["technology", "energy"])
    json_str = req.model_dump_json()
    rebuilt = ScanRequest.model_validate_json(json_str)
    assert rebuilt.sectors == req.sectors
    assert rebuilt.preset == req.preset


# ---------------------------------------------------------------------------
# SectorInfo schema (#162)
# ---------------------------------------------------------------------------


def test_sector_info() -> None:
    """SectorInfo holds name and ticker_count."""
    info = SectorInfo(name="Information Technology", ticker_count=75)
    assert info.name == "Information Technology"
    assert info.ticker_count == 75


def test_sector_info_json_roundtrip() -> None:
    """SectorInfo survives JSON roundtrip."""
    info = SectorInfo(name="Energy", ticker_count=21)
    json_str = info.model_dump_json()
    rebuilt = SectorInfo.model_validate_json(json_str)
    assert rebuilt == info


# ---------------------------------------------------------------------------
# DebateResultDetail typed agent fields (#258)
# ---------------------------------------------------------------------------


def test_debate_result_detail_fields_accept_typed_models() -> None:
    """DebateResultDetail agent fields accept typed Pydantic models directly."""
    from options_arena.api.schemas import DebateResultDetail
    from options_arena.models import (
        ContrarianThesis,
        FlowThesis,
        FundamentalThesis,
        RiskAssessment,
    )
    from options_arena.models.enums import CatalystImpact, RiskLevel

    flow = FlowThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        gex_interpretation="Positive GEX.",
        smart_money_signal="Net call buying.",
        oi_analysis="Call OI concentrated.",
        volume_confirmation="Call volume elevated.",
        key_flow_factors=["GEX positive"],
        model_used="test",
    )
    fundamental = FundamentalThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.68,
        catalyst_impact=CatalystImpact.HIGH,
        earnings_assessment="Beat expectations.",
        iv_crush_risk="Moderate.",
        key_fundamental_factors=["Strong earnings"],
        model_used="test",
    )
    risk = RiskAssessment(
        risk_level=RiskLevel.MODERATE,
        confidence=0.65,
        max_loss_estimate="$190 per contract.",
        key_risks=["Earnings volatility"],
        risk_mitigants=["Stop-loss"],
        model_used="test",
    )
    contrarian = ContrarianThesis(
        dissent_direction=SignalDirection.BEARISH,
        dissent_confidence=0.55,
        primary_challenge="Rising bond yields.",
        overlooked_risks=["Credit tightening"],
        consensus_weakness="Over-weights momentum.",
        alternative_scenario="Growth names re-rate lower.",
        model_used="test",
    )

    detail = DebateResultDetail(
        id=1,
        ticker="AAPL",
        is_fallback=False,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        total_tokens=2000,
        created_at=datetime(2026, 2, 26, tzinfo=UTC),
        flow_response=flow,
        fundamental_response=fundamental,
        risk_response=risk,
        contrarian_response=contrarian,
    )

    # Typed model instances are preserved
    assert isinstance(detail.flow_response, FlowThesis)
    assert isinstance(detail.fundamental_response, FundamentalThesis)
    assert isinstance(detail.risk_response, RiskAssessment)
    assert isinstance(detail.contrarian_response, ContrarianThesis)


def test_debate_result_detail_fields_default_none() -> None:
    """DebateResultDetail agent fields default to None when not provided."""
    from options_arena.api.schemas import DebateResultDetail

    detail = DebateResultDetail(
        id=1,
        ticker="AAPL",
        is_fallback=False,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        total_tokens=2000,
        created_at=datetime(2026, 2, 26, tzinfo=UTC),
    )

    assert detail.flow_response is None
    assert detail.fundamental_response is None
    assert detail.risk_response is None
    assert detail.contrarian_response is None
