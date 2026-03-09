"""Tests for export endpoint agent field population (#259).

Validates that the export endpoint correctly deserializes agent JSON fields
from DebateRow and passes them to the DebateResult constructor, producing
markdown exports that include section renderers.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from options_arena.data.repository import DebateRow
from options_arena.models import (
    AgentResponse,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    MarketContext,
    RiskAssessment,
    SignalDirection,
    TradeThesis,
)
from options_arena.models.enums import (
    CatalystImpact,
    ExerciseStyle,
    MacdSignal,
    RiskLevel,
)

# ---------------------------------------------------------------------------
# Helpers — shared fixtures for export tests
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
        argument="Strong momentum with RSI at 62.",
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


def _make_debate_row(debate_id: int = 1) -> DebateRow:
    """Create a DebateRow with agent output fields populated."""
    bull = _make_bull_response()
    thesis = _make_thesis()
    flow = _make_flow_thesis()
    fundamental = _make_fundamental_thesis()
    risk_assessment = _make_risk_assessment()
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
        risk_assessment_json=risk_assessment.model_dump_json(),
        contrarian_json=contrarian.model_dump_json(),
    )


def _make_debate_row_v1(debate_id: int = 2) -> DebateRow:
    """Create a DebateRow WITHOUT extended agent fields."""
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
    )


# ---------------------------------------------------------------------------
# Test 1: Debate export includes all agent section headers
# ---------------------------------------------------------------------------


async def test_debate_export_includes_all_sections(
    client: AsyncClient,
    mock_repo: MagicMock,
) -> None:
    """Export of debate markdown includes all agent section headers."""
    mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row())
    response = await client.get("/api/debate/1/export?format=md")
    assert response.status_code == 200

    md_content = response.text

    # Section headers from the export renderers
    assert "## Flow Analysis" in md_content
    assert "## Fundamental Analysis" in md_content
    assert "## Risk Assessment" in md_content
    assert "## Contrarian Challenge" in md_content

    # Verify agent-specific content is present
    assert "GEX Interpretation" in md_content
    assert "Catalyst Impact" in md_content
    assert "Risk Level" in md_content
    assert "Dissent Direction" in md_content


# ---------------------------------------------------------------------------
# Test 2: Malformed agent JSON still exports successfully
# ---------------------------------------------------------------------------


async def test_export_with_malformed_agent_json_still_succeeds(
    client: AsyncClient,
    mock_repo: MagicMock,
) -> None:
    """Export succeeds when one agent JSON field is malformed (graceful degradation)."""
    row = _make_debate_row()
    # Corrupt the flow_json — other fields remain valid
    row.flow_json = '{"invalid": true, "not_a_flow_thesis": 1}'
    mock_repo.get_debate_by_id = AsyncMock(return_value=row)

    response = await client.get("/api/debate/1/export?format=md")
    assert response.status_code == 200

    md_content = response.text

    # Flow section should be absent (malformed), but others should be present
    assert "## Flow Analysis" not in md_content
    assert "## Fundamental Analysis" in md_content
    assert "## Risk Assessment" in md_content
    assert "## Contrarian Challenge" in md_content
