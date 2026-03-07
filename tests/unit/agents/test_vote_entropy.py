"""Tests for _vote_entropy() — Shannon entropy of agent vote distribution.

Verifies that the pure function correctly computes ensemble diversity:
- 0.0 = unanimous (all agents agree)
- 1.0 = perfect two-way split
- ~1.585 = equal three-way split (log2(3))
"""

from __future__ import annotations

import math

import pytest

from options_arena.agents.orchestrator import _vote_entropy
from options_arena.models import SignalDirection


class TestVoteEntropy:
    """Unit tests for _vote_entropy()."""

    def test_unanimous_zero(self) -> None:
        """All agents agree -> entropy = 0.0."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "flow": SignalDirection.BULLISH,
            "fundamental": SignalDirection.BULLISH,
            "volatility": SignalDirection.BULLISH,
        }
        result = _vote_entropy(directions)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_two_way_split(self) -> None:
        """2 bullish + 2 bearish -> entropy = 1.0."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "flow": SignalDirection.BULLISH,
            "fundamental": SignalDirection.BEARISH,
            "volatility": SignalDirection.BEARISH,
        }
        result = _vote_entropy(directions)
        assert result == pytest.approx(1.0, abs=1e-9)

    def test_three_way_split(self) -> None:
        """Equal 3-way -> entropy = log2(3) ~= 1.585."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "flow": SignalDirection.BEARISH,
            "fundamental": SignalDirection.NEUTRAL,
        }
        result = _vote_entropy(directions)
        assert result == pytest.approx(math.log2(3), abs=1e-6)

    def test_empty_dict(self) -> None:
        """Empty directions -> entropy = 0.0."""
        result = _vote_entropy({})
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_single_agent(self) -> None:
        """Single agent -> entropy = 0.0."""
        directions = {"trend": SignalDirection.BULLISH}
        result = _vote_entropy(directions)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_three_vs_one(self) -> None:
        """3 bullish + 1 bearish -> entropy ~0.811."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "flow": SignalDirection.BULLISH,
            "fundamental": SignalDirection.BULLISH,
            "volatility": SignalDirection.BEARISH,
        }
        result = _vote_entropy(directions)
        # H = -(3/4 * log2(3/4) + 1/4 * log2(1/4)) = 0.8113...
        expected = -(0.75 * math.log2(0.75) + 0.25 * math.log2(0.25))
        assert result == pytest.approx(expected, abs=1e-6)

    def test_all_neutral(self) -> None:
        """All agents neutral -> entropy = 0.0 (unanimous)."""
        directions = {
            "trend": SignalDirection.NEUTRAL,
            "flow": SignalDirection.NEUTRAL,
            "fundamental": SignalDirection.NEUTRAL,
        }
        result = _vote_entropy(directions)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_result_is_non_negative(self) -> None:
        """Shannon entropy is always non-negative."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "flow": SignalDirection.BEARISH,
        }
        result = _vote_entropy(directions)
        assert result >= 0.0
