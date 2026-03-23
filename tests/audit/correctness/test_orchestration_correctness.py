"""Correctness tests for orchestration functions.

Covers:
  - compute_citation_density: fraction of context labels cited in agent text.
"""

from __future__ import annotations

import pytest

from options_arena.agents._parsing import compute_citation_density


class TestComputeCitationDensity:
    """Known-value correctness tests for compute_citation_density."""

    def test_all_labels_cited(self) -> None:
        """All context labels appear in text -> density 1.0."""
        context = "RSI(14): 65.0\nADX: 30.0\nIV RANK: 45"
        text = "The RSI(14) is elevated and ADX shows trending. IV RANK is moderate."
        assert compute_citation_density(context, text) == pytest.approx(1.0)

    def test_no_labels_cited(self) -> None:
        """No context labels cited in text -> density 0.0."""
        context = "RSI(14): 65.0\nADX: 30.0"
        text = "The stock looks good for a long position."
        assert compute_citation_density(context, text) == pytest.approx(0.0)

    def test_partial_citation(self) -> None:
        """Some labels cited -> fraction between 0 and 1."""
        context = "RSI(14): 65.0\nADX: 30.0\nIV RANK: 45\nMACD: 2.1"
        text = "RSI(14) suggests strength. The MACD confirms momentum."
        density = compute_citation_density(context, text)
        assert density == pytest.approx(0.5)

    def test_empty_context_returns_zero(self) -> None:
        """Empty context block (no labels) -> 0.0."""
        assert compute_citation_density("", "some text") == pytest.approx(0.0)

    def test_empty_text_returns_zero(self) -> None:
        """Context has labels but empty text -> 0.0."""
        context = "RSI(14): 65.0\nADX: 30.0"
        assert compute_citation_density(context, "") == pytest.approx(0.0)

    def test_result_in_unit_interval(self) -> None:
        """Result is always in [0.0, 1.0]."""
        context = "RSI(14): 65.0"
        text = "RSI(14) RSI(14) RSI(14)"  # repeated citations
        density = compute_citation_density(context, text)
        assert 0.0 <= density <= 1.0
