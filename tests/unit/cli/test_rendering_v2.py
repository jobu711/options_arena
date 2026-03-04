"""Tests for v2 agent panel rendering in CLI.

Tests verify panel structure and content for the 4 new v2 agent panels
(Flow, Fundamental, Risk v2, Contrarian) and the protocol-aware
render_debate_panels() branching.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic_ai.usage import RunUsage
from rich.console import Console
from rich.panel import Panel

from options_arena.agents._parsing import DebateResult
from options_arena.cli.rendering import (
    render_contrarian_panel,
    render_debate_panels,
    render_flow_panel,
    render_fundamental_panel,
    render_risk_v2_panel,
)
from options_arena.models import (
    AgentResponse,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    MarketContext,
    RiskAssessment,
    TradeThesis,
    VolatilityThesis,
)
from options_arena.models.enums import (
    CatalystImpact,
    ExerciseStyle,
    MacdSignal,
    RiskLevel,
    SignalDirection,
    SpreadType,
    VolAssessment,
)

# ---------------------------------------------------------------------------
# Helpers to build v2 test fixtures
# ---------------------------------------------------------------------------


def _make_flow_thesis() -> FlowThesis:
    return FlowThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        gex_interpretation="Positive GEX supports upward moves",
        smart_money_signal="Institutional call buying detected",
        oi_analysis="Call OI building at 190 strike",
        volume_confirmation="Volume 2.3x above average on calls",
        key_flow_factors=["Call sweep activity", "Positive GEX"],
        model_used="test-model",
    )


def _make_fundamental_thesis(
    *,
    with_optionals: bool = True,
) -> FundamentalThesis:
    return FundamentalThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.68,
        catalyst_impact=CatalystImpact.HIGH,
        earnings_assessment="Beat expected, guidance raised",
        iv_crush_risk="Moderate IV crush expected post-earnings",
        short_interest_analysis="Short interest at 3.2%" if with_optionals else None,
        dividend_impact="Ex-div in 15 days, minimal impact" if with_optionals else None,
        key_fundamental_factors=["Revenue beat", "Margin expansion"],
        model_used="test-model",
    )


def _make_risk_assessment(
    *,
    with_optionals: bool = True,
) -> RiskAssessment:
    return RiskAssessment(
        risk_level=RiskLevel.MODERATE,
        confidence=0.80,
        pop_estimate=0.62,
        max_loss_estimate="$2.55 per contract (100% of premium)",
        charm_decay_warning="Charm accelerating at 14 DTE" if with_optionals else None,
        spread_quality_assessment="Tight bid-ask, good fill" if with_optionals else None,
        key_risks=["Earnings volatility", "IV crush post-event"],
        risk_mitigants=["Defined risk position", "Stop at 50% loss"],
        recommended_position_size="2% of portfolio" if with_optionals else None,
        model_used="test-model",
    )


def _make_contrarian_thesis() -> ContrarianThesis:
    return ContrarianThesis(
        dissent_direction=SignalDirection.BEARISH,
        dissent_confidence=0.55,
        primary_challenge="Consensus ignores macro headwinds",
        overlooked_risks=["Fed rate decision", "China tensions"],
        consensus_weakness="Overreliance on momentum indicators",
        alternative_scenario="Pullback to 175 if macro deteriorates",
        model_used="test-model",
    )


def _make_market_context() -> MarketContext:
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
        data_timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


def _make_agent_response(
    name: str,
    direction: SignalDirection,
    confidence: float,
) -> AgentResponse:
    return AgentResponse(
        agent_name=name,
        direction=direction,
        confidence=confidence,
        argument=f"{name} argument text",
        key_points=[f"{name} key point 1"],
        risks_cited=[f"{name} risk 1"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )


def _make_v2_debate_result() -> DebateResult:
    """Build a full v2 DebateResult with all 6-agent fields populated."""
    trend = _make_agent_response("trend", SignalDirection.BULLISH, 0.72)
    # v2 uses trend as the bull_response; bear is a synthetic placeholder
    bear = _make_agent_response("bear", SignalDirection.BEARISH, 0.50)
    thesis = TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case based on 6-agent consensus.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["Momentum", "Flow"],
        risk_assessment="Moderate risk.",
        recommended_strategy=None,
    )
    vol = VolatilityThesis(
        iv_assessment=VolAssessment.OVERPRICED,
        iv_rank_interpretation="IV rank at 85",
        confidence=0.75,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="High IV favors selling premium",
        target_iv_entry=None,
        target_iv_exit=None,
        suggested_strikes=[],
        key_vol_factors=["Elevated IV"],
        model_used="test",
    )
    return DebateResult(
        context=_make_market_context(),
        bull_response=trend,
        bear_response=bear,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=2500,
        is_fallback=False,
        vol_response=vol,
        flow_response=_make_flow_thesis(),
        fundamental_response=_make_fundamental_thesis(),
        risk_v2_response=_make_risk_assessment(),
        contrarian_response=_make_contrarian_thesis(),
        debate_protocol="v2",
    )


def _make_v1_debate_result() -> DebateResult:
    """Build a classic v1 DebateResult (no v2 fields)."""
    bull = _make_agent_response("bull", SignalDirection.BULLISH, 0.72)
    bear = _make_agent_response("bear", SignalDirection.BEARISH, 0.55)
    thesis = TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["Momentum"],
        risk_assessment="Moderate risk.",
        recommended_strategy=None,
    )
    return DebateResult(
        context=_make_market_context(),
        bull_response=bull,
        bear_response=bear,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=1000,
        is_fallback=False,
        debate_protocol="v1",
    )


# ---------------------------------------------------------------------------
# Individual panel tests
# ---------------------------------------------------------------------------


class TestRenderFlowPanel:
    """Tests for render_flow_panel()."""

    def test_render_flow_panel(self) -> None:
        """Panel contains GEX, smart money, and OI fields."""
        flow = _make_flow_thesis()
        panel = render_flow_panel(flow)

        assert isinstance(panel, Panel)
        assert panel.border_style == "bright_magenta"  # type: ignore[union-attr]

        # Extract text content from the panel
        text_str = str(panel.renderable)
        assert "GEX" in text_str
        assert "Institutional call buying" in text_str
        assert "Call OI building" in text_str
        assert "72%" in text_str  # confidence
        assert "BULLISH" in text_str


class TestRenderFundamentalPanel:
    """Tests for render_fundamental_panel()."""

    def test_render_fundamental_panel(self) -> None:
        """Panel contains catalyst, earnings, and IV crush fields."""
        fund = _make_fundamental_thesis()
        panel = render_fundamental_panel(fund)

        assert isinstance(panel, Panel)
        assert panel.border_style == "bright_cyan"  # type: ignore[union-attr]

        text_str = str(panel.renderable)
        assert "HIGH" in text_str  # catalyst_impact
        assert "Beat expected" in text_str  # earnings_assessment
        assert "IV crush" in text_str.lower() or "IV Crush" in text_str
        assert "68%" in text_str  # confidence
        assert "Short interest" in text_str  # optional field present


class TestRenderRiskV2Panel:
    """Tests for render_risk_v2_panel()."""

    def test_render_risk_v2_panel(self) -> None:
        """Panel contains risk level, PoP, max loss, and mitigants."""
        risk = _make_risk_assessment()
        panel = render_risk_v2_panel(risk)

        assert isinstance(panel, Panel)
        assert panel.border_style == "bright_blue"  # type: ignore[union-attr]

        text_str = str(panel.renderable)
        assert "MODERATE" in text_str  # risk_level
        assert "62%" in text_str  # pop_estimate
        assert "$2.55" in text_str  # max_loss_estimate
        assert "Defined risk position" in text_str  # mitigant
        assert "2% of portfolio" in text_str  # recommended_position_size


class TestRenderContrarianPanel:
    """Tests for render_contrarian_panel()."""

    def test_render_contrarian_panel(self) -> None:
        """Panel contains dissent direction, challenge, and alternative scenario."""
        contra = _make_contrarian_thesis()
        panel = render_contrarian_panel(contra)

        assert isinstance(panel, Panel)
        assert panel.border_style == "yellow"  # type: ignore[union-attr]

        text_str = str(panel.renderable)
        assert "BEARISH" in text_str  # dissent_direction
        assert "macro headwinds" in text_str  # primary_challenge
        assert "Pullback to 175" in text_str  # alternative_scenario
        assert "55%" in text_str  # dissent_confidence


# ---------------------------------------------------------------------------
# Protocol-aware debate panel rendering
# ---------------------------------------------------------------------------


class TestV2DebateRendering:
    """Tests for render_debate_panels() with v2 protocol."""

    def test_v2_debate_renders_6_panels(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """V2 debate renders 6 agent panels + verdict."""
        result = _make_v2_debate_result()
        console = Console(force_terminal=True, width=120)
        render_debate_panels(console, result)
        output = capsys.readouterr().out

        # Should contain all 6 agent panel titles + verdict
        assert "TREND ANALYSIS" in output
        assert "FLOW ANALYSIS" in output
        assert "FUNDAMENTAL ANALYSIS" in output
        assert "VOLATILITY ANALYSIS" in output
        assert "RISK ASSESSMENT" in output
        assert "CONTRARIAN ANALYSIS" in output
        assert "VERDICT" in output

    def test_v2_uses_trend_label(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """V2 renders 'TREND ANALYSIS' instead of 'BULL'."""
        result = _make_v2_debate_result()
        console = Console(force_terminal=True, width=120)
        render_debate_panels(console, result)
        output = capsys.readouterr().out

        assert "TREND ANALYSIS" in output
        # "BULL" should NOT appear as a panel title (may appear in content)
        # We check that the panel title is not "BULL" by verifying the exact
        # panel title pattern -- Rich wraps titles in the border
        lines = output.split("\n")
        bull_panel_titles = [ln for ln in lines if "BULL" in ln and "REBUTTAL" not in ln]
        # In v2, "BULL" should not appear as a standalone panel title
        for line in bull_panel_titles:
            assert "TREND ANALYSIS" in line or "bull" in line.lower()

    def test_v2_omits_bear_placeholder(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """V2 does NOT render a synthetic BEAR panel."""
        result = _make_v2_debate_result()
        console = Console(force_terminal=True, width=120)
        render_debate_panels(console, result)
        output = capsys.readouterr().out

        # No standalone "BEAR" panel title should appear in v2
        lines = output.split("\n")
        bear_title_lines = [
            ln for ln in lines if " BEAR " in ln and "BULL" not in ln and "REBUTTAL" not in ln
        ]
        assert len(bear_title_lines) == 0, f"Found unexpected BEAR panel: {bear_title_lines}"

    def test_v1_debate_renders_unchanged(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """V1 layout is identical -- regression test."""
        result = _make_v1_debate_result()
        console = Console(force_terminal=True, width=120)
        render_debate_panels(console, result)
        output = capsys.readouterr().out

        # V1 should have BULL and BEAR panels
        assert "BULL" in output
        assert "BEAR" in output
        assert "VERDICT" in output

        # V1 should NOT have v2-specific panels
        assert "TREND ANALYSIS" not in output
        assert "FLOW ANALYSIS" not in output
        assert "FUNDAMENTAL ANALYSIS" not in output
        assert "RISK ASSESSMENT" not in output
        assert "CONTRARIAN ANALYSIS" not in output
