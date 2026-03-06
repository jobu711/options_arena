"""Tests for MACD weight in INDICATOR_WEIGHTS.

Verifies that the MACD indicator has been added to the composite scoring
weights with the correct weight value and category, and that all weights
still sum to exactly 1.0.
"""

from __future__ import annotations

import pytest

from options_arena.scoring.composite import INDICATOR_WEIGHTS


class TestMacdWeight:
    """MACD weight is properly configured in INDICATOR_WEIGHTS."""

    def test_weights_contain_macd(self) -> None:
        """Verify INDICATOR_WEIGHTS has 'macd' key."""
        assert "macd" in INDICATOR_WEIGHTS

    def test_weights_sum_to_one(self) -> None:
        """Verify all weights sum to exactly 1.0 (within 1e-9 tolerance)."""
        total = sum(weight for weight, _category in INDICATOR_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_macd_weight_is_trend_category(self) -> None:
        """Verify MACD weight is in 'trend' category."""
        weight, category = INDICATOR_WEIGHTS["macd"]
        assert category == "trend"

    def test_macd_weight_value(self) -> None:
        """Verify MACD has weight of 0.05."""
        weight, _category = INDICATOR_WEIGHTS["macd"]
        assert weight == pytest.approx(0.05, abs=1e-9)

    def test_total_weight_count_is_19(self) -> None:
        """Verify INDICATOR_WEIGHTS has 19 entries (was 18 before MACD)."""
        assert len(INDICATOR_WEIGHTS) == 19
