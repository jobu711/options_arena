"""Tests for volatility direction voting integration.

Verifies:
- Volatility agent direction is included in agent_directions during synthesize_verdict
- Volatility prompt contains IV regime calibration anchors for directional output
"""

from __future__ import annotations

import pytest

from options_arena.agents.orchestrator import synthesize_verdict
from options_arena.agents.volatility import VOLATILITY_SYSTEM_PROMPT
from options_arena.models import (
    AgentResponse,
    DebateConfig,
    FlowThesis,
    SignalDirection,
    SpreadType,
    VolatilityThesis,
)


def _make_agent_response(
    name: str,
    direction: SignalDirection,
    confidence: float = 0.7,
) -> AgentResponse:
    """Build a minimal AgentResponse."""
    return AgentResponse(
        agent_name=name,
        direction=direction,
        confidence=confidence,
        argument="Test argument.",
        key_points=["point1"],
        risks_cited=["risk1"],
        contracts_referenced=["AAPL 190C"],
        model_used="test",
    )


def _make_vol_thesis(
    direction: SignalDirection = SignalDirection.NEUTRAL,
    confidence: float = 0.7,
) -> VolatilityThesis:
    """Build a minimal VolatilityThesis with direction."""
    return VolatilityThesis(
        iv_assessment="overpriced",
        iv_rank_interpretation="IV rank at 85.",
        confidence=confidence,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="High IV favors selling premium.",
        suggested_strikes=["185C"],
        key_vol_factors=["IV rank"],
        model_used="test",
        direction=direction,
    )


def _make_flow_thesis(
    direction: SignalDirection = SignalDirection.BULLISH,
    confidence: float = 0.7,
) -> FlowThesis:
    """Build a minimal FlowThesis."""
    return FlowThesis(
        direction=direction,
        confidence=confidence,
        gex_interpretation="Positive GEX.",
        smart_money_signal="No signal.",
        oi_analysis="OI is flat.",
        volume_confirmation="Volume confirms.",
        key_flow_factors=["factor1"],
        model_used="test",
    )


class TestVolatilityDirectionVoting:
    """Tests for volatility direction inclusion in synthesize_verdict."""

    def test_volatility_included_in_directions(self) -> None:
        """Verify volatility agent direction counted in agent_directions."""
        agent_outputs: dict[str, AgentResponse | FlowThesis | VolatilityThesis] = {
            "trend": _make_agent_response("trend", SignalDirection.BULLISH),
            "volatility": _make_vol_thesis(direction=SignalDirection.BEARISH),
            "flow": _make_flow_thesis(direction=SignalDirection.BULLISH),
        }
        config = DebateConfig(api_key="test-key")
        thesis = synthesize_verdict(
            agent_outputs=agent_outputs,
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=config,
        )
        # With 2 bullish (trend, flow) and 1 bearish (volatility),
        # majority should be bullish, but volatility should be listed as dissenting
        assert thesis.direction == SignalDirection.BULLISH
        assert "volatility" in thesis.dissenting_agents

    def test_volatility_bearish_swings_majority(self) -> None:
        """Verify volatility direction can swing the majority direction."""
        agent_outputs: dict[str, AgentResponse | FlowThesis | VolatilityThesis] = {
            "trend": _make_agent_response("trend", SignalDirection.BEARISH),
            "volatility": _make_vol_thesis(direction=SignalDirection.BEARISH),
            "flow": _make_flow_thesis(direction=SignalDirection.BULLISH),
        }
        config = DebateConfig(api_key="test-key")
        thesis = synthesize_verdict(
            agent_outputs=agent_outputs,
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=config,
        )
        # 2 bearish (trend, volatility) vs 1 bullish (flow) -> bearish majority
        assert thesis.direction == SignalDirection.BEARISH

    def test_volatility_neutral_excluded_from_entropy(self) -> None:
        """Verify volatility NEUTRAL direction is excluded from both entropy and dissent."""
        agent_outputs: dict[str, AgentResponse | FlowThesis | VolatilityThesis] = {
            "trend": _make_agent_response("trend", SignalDirection.BULLISH),
            "volatility": _make_vol_thesis(direction=SignalDirection.NEUTRAL),
        }
        config = DebateConfig(api_key="test-key")
        thesis = synthesize_verdict(
            agent_outputs=agent_outputs,
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=config,
        )
        # NEUTRAL agents are not in dissenting_agents (they don't oppose majority)
        assert "volatility" not in thesis.dissenting_agents
        # NEUTRAL excluded from entropy (consistent with agreement_score)
        # Only 1 directional agent remains → unanimous → entropy = 0.0
        assert thesis.ensemble_entropy is not None
        assert thesis.ensemble_entropy == pytest.approx(0.0, abs=1e-9)

    def test_entropy_set_on_thesis(self) -> None:
        """Verify synthesize_verdict sets ensemble_entropy on the thesis."""
        agent_outputs: dict[str, AgentResponse | FlowThesis | VolatilityThesis] = {
            "trend": _make_agent_response("trend", SignalDirection.BULLISH),
            "volatility": _make_vol_thesis(direction=SignalDirection.BULLISH),
        }
        config = DebateConfig(api_key="test-key")
        thesis = synthesize_verdict(
            agent_outputs=agent_outputs,
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=config,
        )
        # Unanimous -> entropy = 0.0
        assert thesis.ensemble_entropy is not None
        assert thesis.ensemble_entropy == 0.0


class TestIVRegimeCalibrationInPrompt:
    """Tests for IV regime calibration anchors in volatility prompt."""

    def test_iv_regime_calibration_in_prompt(self) -> None:
        """Verify prompt contains IV regime calibration anchors."""
        assert "Directional Signal" in VOLATILITY_SYSTEM_PROMPT
        assert "IV Rank < 25" in VOLATILITY_SYSTEM_PROMPT
        assert "IV Rank 25-75" in VOLATILITY_SYSTEM_PROMPT
        assert "IV Rank > 75" in VOLATILITY_SYSTEM_PROMPT

    def test_direction_in_json_schema(self) -> None:
        """Verify the JSON schema in prompt includes direction field."""
        assert '"direction"' in VOLATILITY_SYSTEM_PROMPT

    def test_direction_values_documented(self) -> None:
        """Verify bullish/bearish/neutral direction values documented in prompt."""
        # Check the rules section mentions direction values
        assert '"bullish"' in VOLATILITY_SYSTEM_PROMPT
        assert '"bearish"' in VOLATILITY_SYSTEM_PROMPT
        assert '"neutral"' in VOLATILITY_SYSTEM_PROMPT

    def test_prompt_version_updated(self) -> None:
        """Verify the prompt version was bumped."""
        # The VERSION comment should be at v3.0 or higher
        from options_arena.agents import volatility

        source = open(volatility.__file__).read()  # noqa: SIM115
        assert "# VERSION: v3.0" in source
