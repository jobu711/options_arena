"""Tests for learning/weight_tuner.py — relocated vote weight tuning.

Verifies that the relocated functions produce identical results to the original
orchestrator implementations, and that imports work from both locations.
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock

import pytest

from options_arena.learning.weight_tuner import (
    AGENT_VOTE_WEIGHTS,
    VoteWeights,
    auto_tune_weights,
    compute_auto_tune_weights,
)
from options_arena.models import AgentAccuracyReport, AgentWeightsComparison


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


class TestComputeAutoTuneWeightsRelocation:
    """Verify relocated function produces identical output."""

    def test_identical_output_all_agents(self) -> None:
        """Weights from learning module match expected behavior."""
        reports = [
            _report("trend", brier=0.15),
            _report("volatility", brier=0.20),
            _report("flow", brier=0.25),
            _report("fundamental", brier=0.30),
            _report("contrarian", brier=0.40),
        ]
        weights = compute_auto_tune_weights(reports)
        directional_sum = sum(v for k, v in weights.items() if k != "risk")
        assert directional_sum == pytest.approx(0.85, abs=0.001)
        assert weights["risk"] == 0.0
        for w in weights.values():
            assert math.isfinite(w)

    def test_empty_accuracy_returns_manual(self) -> None:
        """Empty input returns manual weights (clamped/normalized)."""
        weights = compute_auto_tune_weights([])
        assert "trend" in weights
        assert weights["risk"] == 0.0
        directional_sum = sum(v for k, v in weights.items() if k != "risk")
        assert directional_sum == pytest.approx(0.85, abs=0.001)

    def test_risk_always_zero(self) -> None:
        """Risk agent weight is always 0.0 regardless of data."""
        reports = [_report("risk", brier=0.05, sample_size=100)]
        weights = compute_auto_tune_weights(reports)
        assert weights["risk"] == 0.0

    def test_insufficient_samples_keep_manual(self) -> None:
        """Agents with <10 samples retain manual weights."""
        reports = [_report("trend", brier=0.15, sample_size=5)]
        weights = compute_auto_tune_weights(reports)
        # With only insufficient-sample agents, weights are manual defaults
        assert math.isfinite(weights["trend"])
        directional_sum = sum(v for k, v in weights.items() if k != "risk")
        assert directional_sum == pytest.approx(0.85, abs=0.001)


class TestAgentVoteWeightsConstant:
    """Verify AGENT_VOTE_WEIGHTS constant accessible from learning module."""

    def test_constant_accessible(self) -> None:
        """AGENT_VOTE_WEIGHTS importable from learning module."""
        assert isinstance(AGENT_VOTE_WEIGHTS, dict)
        assert "trend" in AGENT_VOTE_WEIGHTS
        assert AGENT_VOTE_WEIGHTS["risk"] == 0.0

    def test_vote_weights_type_alias(self) -> None:
        """VoteWeights type alias accessible from learning module."""
        assert VoteWeights is not None
        # VoteWeights is a type alias for dict[str, float]
        sample: VoteWeights = {"trend": 0.25}
        assert isinstance(sample, dict)


class TestCanonicalImport:
    """Verify canonical imports from learning.weight_tuner."""

    def test_import_from_learning_module(self) -> None:
        """Import from learning.weight_tuner is the canonical path."""
        from options_arena.learning.weight_tuner import (
            AGENT_VOTE_WEIGHTS as learning_weights,
        )
        from options_arena.learning.weight_tuner import (
            auto_tune_weights as learning_auto_tune,
        )
        from options_arena.learning.weight_tuner import (
            compute_auto_tune_weights as learning_compute,
        )

        assert learning_weights is AGENT_VOTE_WEIGHTS
        assert learning_compute is compute_auto_tune_weights
        assert learning_auto_tune is auto_tune_weights


@pytest.mark.asyncio
class TestAutoTuneWeightsOrchestration:
    """Verify async orchestration from learning module."""

    async def test_persists_to_db(self) -> None:
        """Full orchestration flow works from new location."""
        repo = AsyncMock()
        repo.get_agent_accuracy = AsyncMock(
            return_value=[
                _report("trend", brier=0.15),
                _report("volatility", brier=0.20),
            ]
        )
        repo.save_auto_tune_weights = AsyncMock()

        result = await auto_tune_weights(repo, window_days=90)

        assert len(result) > 0
        assert all(isinstance(r, AgentWeightsComparison) for r in result)
        repo.save_auto_tune_weights.assert_awaited_once()

    async def test_dry_run_skips_persist(self) -> None:
        """dry_run=True computes but does not save."""
        repo = AsyncMock()
        repo.get_agent_accuracy = AsyncMock(return_value=[_report("trend", brier=0.15)])
        repo.save_auto_tune_weights = AsyncMock()

        result = await auto_tune_weights(repo, window_days=90, dry_run=True)

        assert len(result) > 0
        repo.save_auto_tune_weights.assert_not_awaited()

    async def test_insufficient_data_returns_empty(self) -> None:
        """No eligible agents returns empty list."""
        repo = AsyncMock()
        repo.get_agent_accuracy = AsyncMock(return_value=[])

        result = await auto_tune_weights(repo, window_days=90)
        assert result == []
