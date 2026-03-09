"""Tests for synthesize_verdict() vote_weights parameter.

Covers backward compatibility (None uses defaults) and custom weight injection.
"""

from __future__ import annotations

import pytest
from pydantic_ai import models

from options_arena.agents.orchestrator import (
    AGENT_VOTE_WEIGHTS,
    synthesize_verdict,
)
from options_arena.models import (
    AgentResponse,
    DebateConfig,
    SignalDirection,
)

models.ALLOW_MODEL_REQUESTS = False


def _agent_response(
    direction: str = "bullish",
    confidence: float = 0.7,
) -> AgentResponse:
    """Create a minimal AgentResponse for testing."""
    return AgentResponse(
        agent_name="test",
        direction=SignalDirection(direction),
        confidence=confidence,
        argument="Test argument with RSI at 65.",
        key_points=["Point 1"],
        risks_cited=["Risk 1"],
        contracts_referenced=["AAPL 190C 2026-04-18"],
        model_used="test-model",
    )


class TestSynthesizeVerdictWeights:
    """Tests for vote_weights parameter on synthesize_verdict()."""

    def test_none_weights_uses_default(self) -> None:
        """Verify vote_weights=None uses AGENT_VOTE_WEIGHTS."""
        agent_outputs: dict[str, AgentResponse] = {
            "trend": _agent_response("bullish", 0.8),
            "volatility": _agent_response("bullish", 0.7),
        }
        thesis = synthesize_verdict(
            agent_outputs=agent_outputs,
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=DebateConfig(),
        )
        assert thesis is not None
        assert thesis.direction in (
            SignalDirection.BULLISH,
            SignalDirection.BEARISH,
            SignalDirection.NEUTRAL,
        )

    def test_custom_weights_affect_output(self) -> None:
        """Verify provided vote_weights are used instead of defaults."""
        agent_outputs: dict[str, AgentResponse] = {
            "trend": _agent_response("bullish", 0.9),
            "volatility": _agent_response("bearish", 0.9),
        }
        bull_weights = {"trend": 0.80, "volatility": 0.05, "risk": 0.0}
        thesis_bull = synthesize_verdict(
            agent_outputs=agent_outputs,
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=DebateConfig(),
            vote_weights=bull_weights,
        )
        bear_weights = {"trend": 0.05, "volatility": 0.80, "risk": 0.0}
        thesis_bear = synthesize_verdict(
            agent_outputs=agent_outputs,
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=DebateConfig(),
            vote_weights=bear_weights,
        )
        assert thesis_bull is not None
        assert thesis_bear is not None

    def test_empty_custom_weights_still_works(self) -> None:
        """Verify passing empty dict doesn't crash."""
        agent_outputs: dict[str, AgentResponse] = {
            "trend": _agent_response("bullish", 0.7),
        }
        thesis = synthesize_verdict(
            agent_outputs=agent_outputs,
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=DebateConfig(),
            vote_weights={},
        )
        assert thesis is not None

    def test_default_weights_keys_match(self) -> None:
        """Verify AGENT_VOTE_WEIGHTS has expected agents."""
        expected = {"trend", "volatility", "flow", "fundamental", "contrarian", "risk"}
        assert set(AGENT_VOTE_WEIGHTS.keys()) == expected
        assert AGENT_VOTE_WEIGHTS["risk"] == 0.0
        directional = sum(v for k, v in AGENT_VOTE_WEIGHTS.items() if k != "risk")
        assert directional == pytest.approx(0.85, abs=0.01)
