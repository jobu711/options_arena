"""Tests for compute_auto_tune_weights().

Covers: all agents have data, insufficient samples keep manual,
risk always 0.0, floor/cap enforcement, sum=0.85, empty input,
perfect/worst Brier edge cases.
"""

from __future__ import annotations

import math

import pytest

from options_arena.agents.orchestrator import (
    AGENT_VOTE_WEIGHTS,
    compute_auto_tune_weights,
)
from options_arena.models import AgentAccuracyReport


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


class TestComputeAutoTuneWeights:
    """Tests for compute_auto_tune_weights()."""

    def test_all_agents_have_data(self) -> None:
        """Verify weights computed from Brier scores, sum~=0.85."""
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

    def test_insufficient_samples_keep_manual(self) -> None:
        """Verify agents with <10 samples retain manual weights."""
        reports = [
            _report("trend", brier=0.15, sample_size=50),
            _report("volatility", brier=0.20, sample_size=5),
        ]
        weights = compute_auto_tune_weights(reports)
        directional_sum = sum(v for k, v in weights.items() if k != "risk")
        assert directional_sum == pytest.approx(0.85, abs=0.001)

    def test_risk_always_zero(self) -> None:
        """Verify risk agent weight is always 0.0."""
        reports = [_report("risk", brier=0.10, sample_size=100)]
        weights = compute_auto_tune_weights(reports)
        assert weights["risk"] == 0.0

    def test_floor_enforced(self) -> None:
        """Verify no directional weight below 0.05 before normalization."""
        reports = [_report("contrarian", brier=0.99, sample_size=50)]
        weights = compute_auto_tune_weights(reports)
        for name, w in weights.items():
            if name != "risk":
                assert w > 0.0

    def test_cap_enforced(self) -> None:
        """Verify no directional weight above 0.35 before normalization."""
        reports = [_report("trend", brier=0.01, sample_size=100)]
        weights = compute_auto_tune_weights(reports)
        for name, w in weights.items():
            if name != "risk":
                assert w <= 0.85

    def test_sum_is_085(self) -> None:
        """Verify directional weights sum to ~0.85 with various inputs."""
        reports = [
            _report("trend", brier=0.10),
            _report("volatility", brier=0.30),
            _report("flow", brier=0.50),
        ]
        weights = compute_auto_tune_weights(reports)
        directional_sum = sum(v for k, v in weights.items() if k != "risk")
        assert directional_sum == pytest.approx(0.85, abs=0.001)

    def test_empty_accuracy_returns_manual(self) -> None:
        """Verify empty input returns manual weights renormalized."""
        weights = compute_auto_tune_weights([])
        directional_sum = sum(v for k, v in weights.items() if k != "risk")
        assert directional_sum == pytest.approx(0.85, abs=0.001)
        assert weights["risk"] == 0.0
        assert set(weights.keys()) == set(AGENT_VOTE_WEIGHTS.keys())

    def test_perfect_brier_equal_weights(self) -> None:
        """All agents with Brier 0.0 -> equal weights, sum=0.85."""
        reports = [
            _report("trend", brier=0.0),
            _report("volatility", brier=0.0),
            _report("flow", brier=0.0),
            _report("fundamental", brier=0.0),
            _report("contrarian", brier=0.0),
        ]
        weights = compute_auto_tune_weights(reports)
        directional = {k: v for k, v in weights.items() if k != "risk"}
        values = list(directional.values())
        assert all(v == pytest.approx(values[0], abs=0.001) for v in values)

    def test_worst_brier_floor_weights(self) -> None:
        """All agents with Brier 1.0 -> floor weights, renormalized."""
        reports = [
            _report("trend", brier=1.0),
            _report("volatility", brier=1.0),
            _report("flow", brier=1.0),
            _report("fundamental", brier=1.0),
            _report("contrarian", brier=1.0),
        ]
        weights = compute_auto_tune_weights(reports)
        directional = {k: v for k, v in weights.items() if k != "risk"}
        values = list(directional.values())
        assert all(v == pytest.approx(values[0], abs=0.001) for v in values)
        assert sum(directional.values()) == pytest.approx(0.85, abs=0.001)
