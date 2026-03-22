"""Tests for learning module recommendation protocol awareness.

Verifies that:
- ``auto_tune_weights()`` works with existing debate-era data (no protocol filter yet)
- ``compute_auto_tune_weights()`` is protocol-agnostic (pure computation)
- ``auto_tune_indicator_weights()`` is unaffected by the cutover (uses scan scores)
- ``DebateConfig.recommendation_protocol`` defaults to ``unified_v1``
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from options_arena.learning.weight_tuner import (
    AGENT_VOTE_WEIGHTS,
    auto_tune_indicator_weights,
    auto_tune_weights,
    compute_auto_tune_weights,
)
from options_arena.models import AgentAccuracyReport, DebateConfig


def _report(
    name: str,
    brier: float = 0.20,
    sample_size: int = 50,
) -> AgentAccuracyReport:
    """Shorthand for creating an AgentAccuracyReport."""
    return AgentAccuracyReport(
        agent_name=name,
        direction_hit_rate=0.7,
        mean_confidence=0.65,
        brier_score=brier,
        sample_size=sample_size,
    )


class TestLearningRecommendationFilter:
    """Tests for learning module recommendation protocol awareness."""

    @pytest.mark.asyncio
    async def test_tune_vote_weights_works_with_existing_data(self) -> None:
        """Verify auto_tune_weights works with debate-era agent accuracy data.

        The vote weight tuning queries agent_predictions which now has a
        recommendation_protocol column. Existing rows default to 'debate_v1'.
        The function should work regardless of protocol.
        """
        reports = [
            _report("trend", brier=0.15),
            _report("volatility", brier=0.20),
            _report("flow", brier=0.25),
            _report("fundamental", brier=0.30),
            _report("contrarian", brier=0.40),
        ]
        repo = AsyncMock()
        repo.get_agent_accuracy = AsyncMock(return_value=reports)
        repo.save_auto_tune_weights = AsyncMock(return_value=None)

        result = await auto_tune_weights(repo, window_days=90, dry_run=True)

        assert len(result) > 0
        repo.get_agent_accuracy.assert_awaited_once_with(window_days=90)
        # Dry run: save NOT called
        repo.save_auto_tune_weights.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tune_vote_weights_empty_returns_empty(self) -> None:
        """Verify auto_tune_weights returns empty list when no data available.

        When no unified_v1 predictions exist yet and old debate data is
        insufficient, the function should gracefully return empty.
        """
        repo = AsyncMock()
        repo.get_agent_accuracy = AsyncMock(return_value=[])
        repo.save_auto_tune_weights = AsyncMock(return_value=None)

        result = await auto_tune_weights(repo, window_days=90, dry_run=True)

        assert result == []

    def test_compute_auto_tune_weights_protocol_agnostic(self) -> None:
        """Verify compute_auto_tune_weights is a pure function.

        It takes accuracy reports regardless of what protocol produced them.
        The recommendation_protocol filter is at the query level, not here.
        """
        reports = [
            _report("trend", brier=0.15),
            _report("volatility", brier=0.20),
        ]
        weights = compute_auto_tune_weights(reports)

        assert "risk" in weights
        assert weights["risk"] == 0.0
        directional = sum(v for k, v in weights.items() if k != "risk")
        assert directional == pytest.approx(0.85, abs=0.001)

    @pytest.mark.asyncio
    async def test_tune_indicator_weights_unchanged(self) -> None:
        """Verify indicator weight tuning is unaffected by cutover.

        Indicator tuning uses scan scores + contract outcomes, not
        debate/recommendation data. It should work identically.
        """
        repo = AsyncMock()
        repo.get_outcome_signal_pairs = AsyncMock(return_value=[])

        result = await auto_tune_indicator_weights(repo, window_days=90, dry_run=True)

        # Empty data -> empty result (insufficient samples)
        assert result == []
        repo.get_outcome_signal_pairs.assert_awaited_once_with(window_days=90)

    def test_recommendation_protocol_constant(self) -> None:
        """Verify recommendation_protocol default matches expected value."""
        config = DebateConfig()
        assert config.recommendation_protocol == "unified_v1"

    def test_agent_vote_weights_keys(self) -> None:
        """Verify AGENT_VOTE_WEIGHTS has expected agent names."""
        expected_agents = {"trend", "volatility", "flow", "fundamental", "contrarian", "risk"}
        assert set(AGENT_VOTE_WEIGHTS.keys()) == expected_agents
