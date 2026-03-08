"""Tests for INDICATOR_WEIGHTS sum assertion (issue #176, AUDIT-011).

The assertion fires at import time. This test verifies the weights are correct
and that the module can be imported without error.
"""

from __future__ import annotations

import pytest

from options_arena.scoring.composite import INDICATOR_WEIGHTS


def test_indicator_weights_sum_to_one() -> None:
    """INDICATOR_WEIGHTS individual weights sum to 1.0."""
    total = sum(w for w, _ in INDICATOR_WEIGHTS.values())
    assert total == pytest.approx(1.0, abs=1e-9)


def test_indicator_weights_has_21_entries() -> None:
    """INDICATOR_WEIGHTS has exactly 21 entries (19 original + 2 liquidity)."""
    assert len(INDICATOR_WEIGHTS) == 21


def test_all_weights_are_positive() -> None:
    """Every indicator weight must be positive."""
    for name, (weight, _category) in INDICATOR_WEIGHTS.items():
        assert weight > 0.0, f"Weight for {name} must be positive, got {weight}"
