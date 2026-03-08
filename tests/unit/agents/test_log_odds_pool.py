"""Tests for _log_odds_pool() — weighted log-odds confidence pooling (Bordley 1982).

Verifies that the pure function correctly compounds independent agent probabilities
in log-odds space, handles edge cases (empty, clamping, single agent), and satisfies
NFR-7 (three agents at 0.9 -> combined > 0.95).
"""

from __future__ import annotations

import pytest

from options_arena.agents.orchestrator import _log_odds_pool


class TestLogOddsPool:
    """Unit tests for _log_odds_pool()."""

    def test_all_agree_high(self) -> None:
        """Three agents at 0.9 -> combined > 0.95 (NFR-7)."""
        result = _log_odds_pool([0.9, 0.9, 0.9], [1.0, 1.0, 1.0])
        assert result > 0.95

    def test_split_vote(self) -> None:
        """One agent 0.9, two at 0.5 -> combined between 0.5 and 0.9."""
        result = _log_odds_pool([0.9, 0.5, 0.5], [1.0, 1.0, 1.0])
        assert 0.5 < result < 0.9

    def test_extreme_probability_clamping_zero(self) -> None:
        """Agent at 0.0 -> clamped to 0.01, no math error."""
        result = _log_odds_pool([0.0], [1.0])
        assert result == pytest.approx(0.01, abs=0.001)

    def test_extreme_probability_clamping_one(self) -> None:
        """Agent at 1.0 -> clamped to 0.99, no math error."""
        result = _log_odds_pool([1.0], [1.0])
        assert result == pytest.approx(0.99, abs=0.001)

    def test_single_agent(self) -> None:
        """Single agent -> returns its own probability (approximately)."""
        result = _log_odds_pool([0.7], [1.0])
        assert result == pytest.approx(0.7, abs=0.01)

    def test_equal_weights_symmetric(self) -> None:
        """Equal weights with symmetric probabilities around 0.5 -> 0.5."""
        result = _log_odds_pool([0.7, 0.3], [1.0, 1.0])
        assert result == pytest.approx(0.5, abs=0.01)

    def test_unequal_weights(self) -> None:
        """Higher-weighted agent dominates result."""
        result = _log_odds_pool([0.9, 0.3], [10.0, 1.0])
        # With weight 10:1, result should be much closer to 0.9 than 0.3
        assert result > 0.8

    def test_empty_list(self) -> None:
        """Empty probabilities list -> 0.5 (neutral)."""
        result = _log_odds_pool([], [])
        assert result == pytest.approx(0.5, abs=1e-9)

    def test_all_at_half(self) -> None:
        """All agents at 0.5 -> result is 0.5."""
        result = _log_odds_pool([0.5, 0.5, 0.5], [1.0, 1.0, 1.0])
        assert result == pytest.approx(0.5, abs=1e-9)

    def test_zero_total_weight(self) -> None:
        """Zero total weight -> 0.5 (neutral)."""
        result = _log_odds_pool([0.8, 0.7], [0.0, 0.0])
        assert result == pytest.approx(0.5, abs=1e-9)

    def test_opposing_agents_cancel(self) -> None:
        """Equal-weight agents at 0.9 and 0.1 cancel to ~0.5."""
        result = _log_odds_pool([0.9, 0.1], [1.0, 1.0])
        assert result == pytest.approx(0.5, abs=0.01)

    def test_result_within_bounds(self) -> None:
        """Result is always strictly between 0 and 1."""
        result = _log_odds_pool([0.99, 0.99, 0.99], [1.0, 1.0, 1.0])
        assert 0.0 < result < 1.0
