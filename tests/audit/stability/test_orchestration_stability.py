"""Stability tests for orchestration functions: edge cases and invariants.

Covers:
  - compute_citation_density: robust against extreme/unusual inputs.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from options_arena.agents._parsing import compute_citation_density

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_text_strategy = st.text(min_size=0, max_size=500)


class TestComputeCitationDensityStability:
    """Stability tests for compute_citation_density."""

    def test_no_crash_on_special_characters(self) -> None:
        """Special regex characters in context don't crash."""
        context = "RSI(14): 65.0\n[BRACKETS]: 10\n(PARENS): 5"
        text = "RSI(14) is noted."
        result = compute_citation_density(context, text)
        assert 0.0 <= result <= 1.0

    def test_case_insensitive_matching(self) -> None:
        """Citation matching is case-insensitive."""
        context = "RSI(14): 65.0"
        text = "rsi(14) looks good"
        result = compute_citation_density(context, text)
        assert result == pytest.approx(1.0)

    def test_multiple_text_arguments(self) -> None:
        """Multiple text arguments are concatenated."""
        context = "RSI(14): 65.0\nADX: 30.0"
        result = compute_citation_density(context, "RSI(14) is high", "ADX confirms trend")
        assert result == pytest.approx(1.0)

    @given(text=_text_strategy)
    @settings(max_examples=50)
    def test_result_always_in_unit_interval(self, text: str) -> None:
        """Output is always in [0.0, 1.0] for any text input."""
        context = "RSI(14): 65.0\nADX: 30.0\nIV RANK: 45"
        result = compute_citation_density(context, text)
        assert 0.0 <= result <= 1.0

    def test_empty_context_empty_text(self) -> None:
        """Both empty -> 0.0, no crash."""
        assert compute_citation_density("", "") == pytest.approx(0.0)

    def test_very_long_context(self) -> None:
        """Large context block doesn't cause performance issues."""
        labels = [f"INDICATOR_{i}: {i * 1.5}" for i in range(100)]
        context = "\n".join(labels)
        text = "INDICATOR_0 and INDICATOR_50 are interesting"
        result = compute_citation_density(context, text)
        assert 0.0 <= result <= 1.0
