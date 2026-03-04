"""Tests for v2 agent output fields in API schema and debate routes (#254).

Validates that the API layer correctly surfaces, serializes, and persists
the 5 new v2 agent output fields (flow_response, fundamental_response,
risk_v2_response, contrarian_response, debate_protocol).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateResult
from options_arena.api.routes.debate import _run_debate_background
from options_arena.api.schemas import DebateResultDetail
from options_arena.api.ws import DebateProgressBridge
from options_arena.data.repository import DebateRow
from options_arena.models import (
    AgentResponse,
    AppSettings,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    MarketContext,
    Quote,
    RiskAssessment,
    SignalDirection,
    TickerInfo,
    TradeThesis,
)
from options_arena.models.enums import (
    CatalystImpact,
    DividendSource,
    ExerciseStyle,
    MacdSignal,
    RiskLevel,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_flow_thesis() -> FlowThesis:
    """Create a realistic FlowThesis fixture."""
    return FlowThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        gex_interpretation="Positive GEX suggests dealer hedging supports upside.",
        smart_money_signal="Net call buying above $190 strike.",
        oi_analysis="Call OI concentrated at $195, put OI at $175.",
        volume_confirmation="Call volume 2.3x average.",
        key_flow_factors=["GEX positive", "Smart money call buying"],
        model_used="test",
    )


def _make_fundamental_thesis() -> FundamentalThesis:
    """Create a realistic FundamentalThesis fixture."""
    return FundamentalThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.68,
        catalyst_impact=CatalystImpact.HIGH,
        earnings_assessment="Beat expectations by 8% last quarter.",
        iv_crush_risk="Moderate IV crush risk post-earnings.",
        short_interest_analysis="Short interest at 1.2%, low.",
        key_fundamental_factors=["Strong earnings", "Low short interest"],
        model_used="test",
    )


def _make_risk_assessment() -> RiskAssessment:
    """Create a realistic RiskAssessment fixture."""
    return RiskAssessment(
        risk_level=RiskLevel.MODERATE,
        confidence=0.65,
        pop_estimate=0.58,
        max_loss_estimate="$190 per contract (premium paid).",
        charm_decay_warning="Theta accelerates below 14 DTE.",
        spread_quality_assessment="Tight bid-ask spread.",
        key_risks=["Earnings volatility", "Sector rotation risk"],
        risk_mitigants=["Stop-loss at -50%"],
        recommended_position_size="2% of portfolio.",
        model_used="test",
    )


def _make_contrarian_thesis() -> ContrarianThesis:
    """Create a realistic ContrarianThesis fixture."""
    return ContrarianThesis(
        dissent_direction=SignalDirection.BEARISH,
        dissent_confidence=0.55,
        primary_challenge="Consensus ignores rising bond yields.",
        overlooked_risks=["Credit tightening", "Margin compression"],
        consensus_weakness="Consensus over-weights momentum.",
        alternative_scenario="If bond yields spike, growth names re-rate lower.",
        model_used="test",
    )


def _make_bull_response() -> AgentResponse:
    """Create a minimal AgentResponse for bull agent."""
    return AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        argument="Strong momentum.",
        key_points=["RSI trending up"],
        risks_cited=["Earnings risk"],
        contracts_referenced=["AAPL 190C"],
        model_used="test",
    )


def _make_thesis() -> TradeThesis:
    """Create a minimal TradeThesis fixture."""
    return TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.70,
        summary="Buy the dip.",
        bull_score=7.5,
        bear_score=4.5,
        key_factors=["Strong RSI"],
        risk_assessment="Moderate risk.",
    )


def _make_market_context() -> MarketContext:
    """Create a MarketContext fixture."""
    return MarketContext(
        ticker="AAPL",
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.2,
        iv_percentile=52.1,
        atm_iv_30d=28.5,
        rsi_14=62.3,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC),
    )


def _make_debate_row_v2(debate_id: int = 1) -> DebateRow:
    """Create a DebateRow with v2 agent output fields populated."""
    bull = _make_bull_response()
    thesis = _make_thesis()
    flow = _make_flow_thesis()
    fundamental = _make_fundamental_thesis()
    risk_v2 = _make_risk_assessment()
    contrarian = _make_contrarian_thesis()
    mc = _make_market_context()

    return DebateRow(
        id=debate_id,
        scan_run_id=1,
        ticker="AAPL",
        bull_json=bull.model_dump_json(),
        bear_json=bull.model_dump_json(),
        risk_json=thesis.model_dump_json(),
        verdict_json=thesis.model_dump_json(),
        vol_json=None,
        rebuttal_json=None,
        total_tokens=2000,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        is_fallback=False,
        created_at=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
        market_context=mc,
        flow_json=flow.model_dump_json(),
        fundamental_json=fundamental.model_dump_json(),
        risk_v2_json=risk_v2.model_dump_json(),
        contrarian_json=contrarian.model_dump_json(),
        debate_protocol="v2",
    )


def _make_debate_row_v1(debate_id: int = 2) -> DebateRow:
    """Create a DebateRow WITHOUT v2 fields (legacy v1 debate)."""
    bull = _make_bull_response()
    thesis = _make_thesis()

    return DebateRow(
        id=debate_id,
        scan_run_id=1,
        ticker="AAPL",
        bull_json=bull.model_dump_json(),
        bear_json=bull.model_dump_json(),
        risk_json=thesis.model_dump_json(),
        verdict_json=thesis.model_dump_json(),
        vol_json=None,
        rebuttal_json=None,
        total_tokens=1000,
        model_name="llama-3.3-70b",
        duration_ms=3000,
        is_fallback=False,
        created_at=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
        # No v2 fields — all default to None / "v1"
    )


def _make_debate_result_v2() -> DebateResult:
    """Create a DebateResult with v2 agent output fields populated."""
    bull = _make_bull_response()
    bear = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="IV is elevated, limiting upside.",
        key_points=["IV elevated"],
        risks_cited=["Potential reversal"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )
    thesis = _make_thesis()
    ctx = _make_market_context()

    return DebateResult(
        context=ctx,
        bull_response=bull,
        bear_response=bear,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=1500,
        is_fallback=False,
        flow_response=_make_flow_thesis(),
        fundamental_response=_make_fundamental_thesis(),
        risk_v2_response=_make_risk_assessment(),
        contrarian_response=_make_contrarian_thesis(),
        debate_protocol="v2",
    )


def _make_quote() -> Quote:
    """Create a realistic Quote fixture."""
    return Quote(
        ticker="AAPL",
        price=Decimal("185.05"),
        bid=Decimal("185.00"),
        ask=Decimal("185.10"),
        volume=42_000_000,
        timestamp=datetime(2026, 3, 4, 15, 0, 0, tzinfo=UTC),
    )


def _make_ticker_info() -> TickerInfo:
    """Create a realistic TickerInfo fixture."""
    return TickerInfo(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Information Technology",
        market_cap=2_800_000_000_000,
        current_price=Decimal("185.05"),
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("164.08"),
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
    )


def _make_mock_request() -> MagicMock:
    """Create a mock Request with app.state populated."""
    request = MagicMock()
    request.app.state.openbb = None
    request.app.state.intelligence = None
    request.app.state.debate_queues = {}
    return request


# ---------------------------------------------------------------------------
# Test 1: GET /api/debate/{id} includes v2 agent outputs
# ---------------------------------------------------------------------------


async def test_get_debate_returns_v2_fields(
    client: AsyncClient,
    mock_repo: MagicMock,
) -> None:
    """GET /api/debate/{id} includes v2 agent outputs when present."""
    mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row_v2())
    response = await client.get("/api/debate/1")
    assert response.status_code == 200

    data = response.json()

    # v2 agent fields are present and non-None
    assert data["flow_response"] is not None
    assert data["flow_response"]["direction"] == "bullish"
    assert data["flow_response"]["confidence"] == pytest.approx(0.72, abs=0.01)

    assert data["fundamental_response"] is not None
    assert data["fundamental_response"]["direction"] == "bullish"

    assert data["risk_v2_response"] is not None
    assert data["risk_v2_response"]["risk_level"] == "moderate"
    assert data["risk_v2_response"]["confidence"] == pytest.approx(0.65, abs=0.01)

    assert data["contrarian_response"] is not None
    assert data["contrarian_response"]["dissent_direction"] == "bearish"

    assert data["debate_protocol"] == "v2"


# ---------------------------------------------------------------------------
# Test 2: v1 debate has None for v2 fields
# ---------------------------------------------------------------------------


async def test_get_debate_v1_returns_none_v2(
    client: AsyncClient,
    mock_repo: MagicMock,
) -> None:
    """GET /api/debate/{id} returns None for v2 fields on a legacy v1 debate."""
    mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row_v1())
    response = await client.get("/api/debate/2")
    assert response.status_code == 200

    data = response.json()

    # v2 fields should all be None / missing
    assert data["flow_response"] is None
    assert data["fundamental_response"] is None
    assert data["risk_v2_response"] is None
    assert data["contrarian_response"] is None
    assert data["debate_protocol"] is None or data["debate_protocol"] == "v1"


# ---------------------------------------------------------------------------
# Test 3: _run_debate_background passes v2 JSON to save_debate
# ---------------------------------------------------------------------------


@patch("options_arena.api.routes.debate.run_debate_v2", new_callable=AsyncMock)
@patch("options_arena.api.routes.debate.compute_dimensional_scores")
async def test_debate_background_persists_v2(
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """_run_debate_background passes v2 fields from DebateResult to save_debate."""
    mock_dim_scores.return_value = None
    debate_result = _make_debate_result_v2()
    mock_run_debate.return_value = debate_result

    request = _make_mock_request()
    mock_repo = AsyncMock()
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    mock_repo.save_debate = AsyncMock(return_value=1)

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=_make_quote())
    mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info())

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    bridge = DebateProgressBridge()

    await _run_debate_background(
        request=request,
        debate_id=1,
        ticker="AAPL",
        scan_id=None,
        settings=AppSettings(),
        repo=mock_repo,
        market_data=mock_market_data,
        options_data=mock_options_data,
        bridge=bridge,
    )

    # Verify save_debate was called with v2 keyword arguments
    mock_repo.save_debate.assert_awaited_once()
    call_kwargs = mock_repo.save_debate.call_args.kwargs

    assert call_kwargs["flow_thesis"] is debate_result.flow_response
    assert call_kwargs["fundamental_thesis"] is debate_result.fundamental_response
    assert call_kwargs["risk_v2_assessment"] is debate_result.risk_v2_response
    assert call_kwargs["contrarian_thesis"] is debate_result.contrarian_response
    assert call_kwargs["debate_protocol"] == "v2"


# ---------------------------------------------------------------------------
# Test 4: DebateResultDetail with v2 fields serializes to valid JSON
# ---------------------------------------------------------------------------


def test_schema_serialization() -> None:
    """DebateResultDetail with v2 fields serializes to valid JSON."""
    flow = _make_flow_thesis()
    fundamental = _make_fundamental_thesis()
    risk_v2 = _make_risk_assessment()
    contrarian = _make_contrarian_thesis()

    detail = DebateResultDetail(
        id=1,
        ticker="AAPL",
        is_fallback=False,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        total_tokens=2000,
        created_at=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
        debate_protocol="v2",
        flow_response=flow,
        fundamental_response=fundamental,
        risk_v2_response=risk_v2,
        contrarian_response=contrarian,
    )

    # Should not raise
    json_str = detail.model_dump_json()
    parsed = json.loads(json_str)

    # Round-trip check: all v2 fields survive serialization
    assert parsed["debate_protocol"] == "v2"
    assert parsed["flow_response"]["direction"] == "bullish"
    assert parsed["fundamental_response"]["catalyst_impact"] == "high"
    assert parsed["risk_v2_response"]["risk_level"] == "moderate"
    assert parsed["contrarian_response"]["dissent_direction"] == "bearish"


# ---------------------------------------------------------------------------
# Test 5: debate_protocol field appears in API response
# ---------------------------------------------------------------------------


async def test_debate_protocol_in_response(
    client: AsyncClient,
    mock_repo: MagicMock,
) -> None:
    """debate_protocol field appears in the API response JSON."""
    v2_row = _make_debate_row_v2()
    mock_repo.get_debate_by_id = AsyncMock(return_value=v2_row)
    response = await client.get("/api/debate/1")
    assert response.status_code == 200

    data = response.json()
    assert "debate_protocol" in data
    assert data["debate_protocol"] == "v2"

    # Also verify with a v1 debate
    v1_row = _make_debate_row_v1()
    mock_repo.get_debate_by_id = AsyncMock(return_value=v1_row)
    response = await client.get("/api/debate/2")
    assert response.status_code == 200

    data = response.json()
    assert "debate_protocol" in data


# ---------------------------------------------------------------------------
# Test 6: V2 fields are typed Pydantic models, not raw dicts (#258)
# ---------------------------------------------------------------------------


def test_v2_fields_are_typed_models_not_dicts() -> None:
    """Verify V2 fields on DebateResultDetail are typed Pydantic models, not dicts."""
    flow = _make_flow_thesis()
    fundamental = _make_fundamental_thesis()
    risk_v2 = _make_risk_assessment()
    contrarian = _make_contrarian_thesis()

    detail = DebateResultDetail(
        id=1,
        ticker="AAPL",
        is_fallback=False,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        total_tokens=2000,
        created_at=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
        debate_protocol="v2",
        flow_response=flow,
        fundamental_response=fundamental,
        risk_v2_response=risk_v2,
        contrarian_response=contrarian,
    )

    # Fields should be actual model instances, not plain dicts
    assert isinstance(detail.flow_response, FlowThesis)
    assert isinstance(detail.fundamental_response, FundamentalThesis)
    assert isinstance(detail.risk_v2_response, RiskAssessment)
    assert isinstance(detail.contrarian_response, ContrarianThesis)

    # Verify model fields are accessible as attributes (not dict keys)
    assert detail.flow_response.direction == SignalDirection.BULLISH
    assert detail.fundamental_response.catalyst_impact == CatalystImpact.HIGH
    assert detail.risk_v2_response.risk_level == RiskLevel.MODERATE
    assert detail.contrarian_response.dissent_direction == SignalDirection.BEARISH


# ---------------------------------------------------------------------------
# Test 7: GET /api/debate/{id} returns typed V2 model JSON (#258)
# ---------------------------------------------------------------------------


async def test_get_debate_returns_typed_v2_model_json(
    client: AsyncClient,
    mock_repo: MagicMock,
) -> None:
    """GET /api/debate/{id} returns V2 fields with full model structure."""
    mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row_v2())
    response = await client.get("/api/debate/1")
    assert response.status_code == 200

    data = response.json()

    # FlowThesis fields
    flow = data["flow_response"]
    assert "gex_interpretation" in flow
    assert "smart_money_signal" in flow
    assert "oi_analysis" in flow
    assert "volume_confirmation" in flow
    assert "key_flow_factors" in flow
    assert isinstance(flow["key_flow_factors"], list)

    # FundamentalThesis fields
    fundamental = data["fundamental_response"]
    assert "catalyst_impact" in fundamental
    assert "earnings_assessment" in fundamental
    assert "iv_crush_risk" in fundamental
    assert "key_fundamental_factors" in fundamental

    # RiskAssessment fields
    risk_v2 = data["risk_v2_response"]
    assert "risk_level" in risk_v2
    assert "pop_estimate" in risk_v2
    assert "max_loss_estimate" in risk_v2
    assert "key_risks" in risk_v2

    # ContrarianThesis fields
    contrarian = data["contrarian_response"]
    assert "dissent_direction" in contrarian
    assert "dissent_confidence" in contrarian
    assert "primary_challenge" in contrarian
    assert "overlooked_risks" in contrarian


# ---------------------------------------------------------------------------
# Test 8: V1 debates return null for all V2 fields (typed version) (#258)
# ---------------------------------------------------------------------------


async def test_get_debate_v2_null_fields_when_v1(
    client: AsyncClient,
    mock_repo: MagicMock,
) -> None:
    """Verify V1 debates return null for all V2 typed model fields."""
    mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row_v1())
    response = await client.get("/api/debate/2")
    assert response.status_code == 200

    data = response.json()

    # All V2 typed model fields should be null
    assert data["flow_response"] is None
    assert data["fundamental_response"] is None
    assert data["risk_v2_response"] is None
    assert data["contrarian_response"] is None


# ---------------------------------------------------------------------------
# Test 9: Malformed V2 JSON raises validation error (#258)
# ---------------------------------------------------------------------------


async def test_malformed_v2_json_raises_error(
    client: AsyncClient,
    mock_repo: MagicMock,
) -> None:
    """Malformed V2 JSON in DB produces a ValidationError (not silent garbage)."""
    from pydantic import ValidationError as PydanticValidationError  # noqa: PLC0415

    row = _make_debate_row_v1()
    # Inject malformed JSON that won't parse into FlowThesis
    row.flow_json = '{"invalid_field": "not a FlowThesis"}'

    mock_repo.get_debate_by_id = AsyncMock(return_value=row)

    # model_validate_json raises ValidationError -- not silently swallowed
    with pytest.raises(PydanticValidationError, match="FlowThesis"):
        await client.get("/api/debate/2")


# ---------------------------------------------------------------------------
# Test 10: Empty string V2 JSON treated as absent (#258)
# ---------------------------------------------------------------------------


async def test_empty_string_v2_json_treated_as_none(
    client: AsyncClient,
    mock_repo: MagicMock,
) -> None:
    """Empty string V2 JSON is falsy, treated same as None (returns null)."""
    row = _make_debate_row_v1()
    # Empty string is falsy -- should be treated like None
    object.__setattr__(row, "flow_json", "")
    object.__setattr__(row, "fundamental_json", "")
    object.__setattr__(row, "risk_v2_json", "")
    object.__setattr__(row, "contrarian_json", "")

    mock_repo.get_debate_by_id = AsyncMock(return_value=row)
    response = await client.get("/api/debate/2")
    assert response.status_code == 200

    data = response.json()
    assert data["flow_response"] is None
    assert data["fundamental_response"] is None
    assert data["risk_v2_response"] is None
    assert data["contrarian_response"] is None


# ---------------------------------------------------------------------------
# Test 11: DebateResultDetail V2 JSON round-trip (#258)
# ---------------------------------------------------------------------------


def test_debate_result_detail_v2_json_roundtrip() -> None:
    """DebateResultDetail with typed V2 models survives JSON round-trip."""
    detail = DebateResultDetail(
        id=1,
        ticker="AAPL",
        is_fallback=False,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        total_tokens=2000,
        created_at=datetime(2026, 3, 4, 12, 0, 0, tzinfo=UTC),
        debate_protocol="v2",
        flow_response=_make_flow_thesis(),
        fundamental_response=_make_fundamental_thesis(),
        risk_v2_response=_make_risk_assessment(),
        contrarian_response=_make_contrarian_thesis(),
    )

    json_str = detail.model_dump_json()
    rebuilt = DebateResultDetail.model_validate_json(json_str)

    # Typed model fields survive round-trip
    assert isinstance(rebuilt.flow_response, FlowThesis)
    assert isinstance(rebuilt.fundamental_response, FundamentalThesis)
    assert isinstance(rebuilt.risk_v2_response, RiskAssessment)
    assert isinstance(rebuilt.contrarian_response, ContrarianThesis)
    assert rebuilt.flow_response.confidence == pytest.approx(0.72, abs=0.01)
    assert rebuilt.risk_v2_response.risk_level == RiskLevel.MODERATE
