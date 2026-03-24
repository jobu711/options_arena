"""Tests for ADX/ATR%/RSI condition dimensions on OutcomeWithContext.

Covers the new classifier functions and extended OutcomeWithContext fields
added in Task #779.
"""

from __future__ import annotations

import math

import pytest

from options_arena.learning.strategy_book import (
    OutcomeWithContext,
    _classify_adx,
    _classify_atr_pct,
)

# ---------------------------------------------------------------------------
# TestClassifyAdx
# ---------------------------------------------------------------------------


class TestClassifyAdx:
    """Tests for ``_classify_adx()`` bucket classification."""

    @pytest.mark.parametrize(
        ("adx", "expected"),
        [
            (10.0, "weak"),
            (20.0, "moderate"),
            (25.0, "moderate"),
            (35.0, "strong"),
            (None, None),
        ],
    )
    def test_classify_adx(self, adx: float | None, expected: str | None) -> None:
        assert _classify_adx(adx) == expected

    def test_boundary_zero(self) -> None:
        """ADX of 0.0 falls in 'weak' bucket."""
        assert _classify_adx(0.0) == "weak"

    def test_boundary_30(self) -> None:
        """ADX of 30.0 falls in 'strong' bucket (lower-bound inclusive)."""
        assert _classify_adx(30.0) == "strong"

    def test_overflow_above_100(self) -> None:
        """ADX above 100 falls through to last bucket fallback."""
        assert _classify_adx(150.0) == "strong"


# ---------------------------------------------------------------------------
# TestClassifyAtrPct
# ---------------------------------------------------------------------------


class TestClassifyAtrPct:
    """Tests for ``_classify_atr_pct()`` bucket classification."""

    @pytest.mark.parametrize(
        ("atr_pct", "expected"),
        [
            (0.5, "low"),
            (1.5, "medium"),
            (2.0, "medium"),
            (4.0, "high"),
            (None, None),
        ],
    )
    def test_classify_atr_pct(self, atr_pct: float | None, expected: str | None) -> None:
        assert _classify_atr_pct(atr_pct) == expected

    def test_boundary_zero(self) -> None:
        """ATR% of 0.0 falls in 'low' bucket."""
        assert _classify_atr_pct(0.0) == "low"

    def test_boundary_3(self) -> None:
        """ATR% of 3.0 falls in 'high' bucket (lower-bound inclusive)."""
        assert _classify_atr_pct(3.0) == "high"

    def test_overflow_above_100(self) -> None:
        """ATR% above 100 falls through to last bucket fallback."""
        assert _classify_atr_pct(200.0) == "high"


# ---------------------------------------------------------------------------
# TestOutcomeWithContextExtension
# ---------------------------------------------------------------------------


class TestOutcomeWithContextExtension:
    """Tests for backward compatibility and new fields on OutcomeWithContext."""

    def test_backward_compatible_construction(self) -> None:
        """Existing construction without new fields works."""
        outcome = OutcomeWithContext(
            sector="Information Technology",
            iv_level=50.0,
            dte_at_entry=30,
            direction="bullish",
            return_pct=5.0,
            is_winner=True,
        )
        assert outcome.sector == "Information Technology"
        assert outcome.adx is None
        assert outcome.atr_pct is None
        assert outcome.rsi is None

    def test_new_fields_populated(self) -> None:
        """Construction with adx, atr_pct, rsi works."""
        outcome = OutcomeWithContext(
            sector="Energy",
            iv_level=40.0,
            dte_at_entry=20,
            direction="bearish",
            return_pct=-3.0,
            is_winner=False,
            adx=25.0,
            atr_pct=2.5,
            rsi=45.0,
        )
        assert outcome.adx == pytest.approx(25.0)
        assert outcome.atr_pct == pytest.approx(2.5)
        assert outcome.rsi == pytest.approx(45.0)

    def test_new_fields_default_none(self) -> None:
        """New fields default to None."""
        outcome = OutcomeWithContext(
            sector="Financials",
            iv_level=30.0,
            dte_at_entry=50,
            direction="bullish",
            return_pct=1.0,
            is_winner=True,
        )
        assert outcome.adx is None
        assert outcome.atr_pct is None
        assert outcome.rsi is None

    def test_rejects_nan_adx(self) -> None:
        """NaN adx is rejected by validator."""
        with pytest.raises(ValueError, match="context field must be finite"):
            OutcomeWithContext(
                sector="Tech",
                iv_level=50.0,
                dte_at_entry=30,
                direction="bullish",
                return_pct=1.0,
                is_winner=True,
                adx=float("nan"),
            )

    def test_rejects_inf_atr_pct(self) -> None:
        """Inf atr_pct is rejected by validator."""
        with pytest.raises(ValueError, match="context field must be finite"):
            OutcomeWithContext(
                sector="Tech",
                iv_level=50.0,
                dte_at_entry=30,
                direction="bullish",
                return_pct=1.0,
                is_winner=True,
                atr_pct=math.inf,
            )

    def test_rejects_neg_inf_rsi(self) -> None:
        """Negative inf rsi is rejected by validator."""
        with pytest.raises(ValueError, match="context field must be finite"):
            OutcomeWithContext(
                sector="Tech",
                iv_level=50.0,
                dte_at_entry=30,
                direction="bullish",
                return_pct=1.0,
                is_winner=True,
                rsi=float("-inf"),
            )

    def test_frozen_immutability(self) -> None:
        """OutcomeWithContext is frozen — new fields cannot be mutated."""
        outcome = OutcomeWithContext(
            sector="Tech",
            iv_level=50.0,
            dte_at_entry=30,
            direction="bullish",
            return_pct=1.0,
            is_winner=True,
            adx=25.0,
        )
        with pytest.raises(Exception):  # noqa: B017
            outcome.adx = 30.0  # type: ignore[misc]
