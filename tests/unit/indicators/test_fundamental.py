"""Tests for fundamental catalyst indicators.

Tests for all 5 functions: earnings EM ratio, earnings impact, short interest,
dividend impact, and IV crush history. Each function tested with:
1. Known-value / expected-behavior test
2. None/missing input test
3. Division-by-zero guard test
4. Edge cases
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.fundamental import (
    compute_div_impact,
    compute_earnings_em_ratio,
    compute_earnings_impact,
    compute_iv_crush_history,
    compute_short_interest,
)

# ---------------------------------------------------------------------------
# compute_earnings_em_ratio tests
# ---------------------------------------------------------------------------


class TestEarningsEmRatio:
    """Tests for earnings expected move ratio."""

    def test_overpriced_iv(self) -> None:
        """Expected move > actual → ratio > 1 (IV overpricing)."""
        result = compute_earnings_em_ratio(5.0, 3.0)
        assert result is not None
        assert result == pytest.approx(5.0 / 3.0, rel=1e-6)

    def test_underpriced_iv(self) -> None:
        """Expected move < actual → ratio < 1 (IV underpricing)."""
        result = compute_earnings_em_ratio(2.0, 4.0)
        assert result is not None
        assert result == pytest.approx(0.5, rel=1e-6)

    def test_equal_moves(self) -> None:
        """Equal expected and actual → ratio = 1.0 (fair pricing)."""
        result = compute_earnings_em_ratio(3.0, 3.0)
        assert result is not None
        assert result == pytest.approx(1.0, rel=1e-6)

    def test_none_expected(self) -> None:
        """None expected move → None."""
        assert compute_earnings_em_ratio(None, 3.0) is None

    def test_none_actual(self) -> None:
        """None actual move → None."""
        assert compute_earnings_em_ratio(5.0, None) is None

    def test_both_none(self) -> None:
        """Both None → None."""
        assert compute_earnings_em_ratio(None, None) is None

    def test_zero_denominator(self) -> None:
        """Zero actual move → None (division by zero guard)."""
        assert compute_earnings_em_ratio(5.0, 0.0) is None

    def test_inf_input(self) -> None:
        """Infinity input → None."""
        assert compute_earnings_em_ratio(float("inf"), 3.0) is None

    def test_nan_input(self) -> None:
        """NaN input → None."""
        assert compute_earnings_em_ratio(float("nan"), 3.0) is None


# ---------------------------------------------------------------------------
# compute_earnings_impact tests
# ---------------------------------------------------------------------------


class TestEarningsImpact:
    """Tests for earnings impact score."""

    def test_earnings_at_start(self) -> None:
        """Earnings tomorrow with 30 DTE → high impact (~0.97)."""
        result = compute_earnings_impact(1, 30)
        assert result is not None
        assert result == pytest.approx(1.0 - 1 / 30, rel=1e-6)

    def test_earnings_at_expiry(self) -> None:
        """Earnings at DTE → impact = 0.0."""
        result = compute_earnings_impact(30, 30)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-6)

    def test_earnings_midway(self) -> None:
        """Earnings at half DTE → impact = 0.5."""
        result = compute_earnings_impact(15, 30)
        assert result is not None
        assert result == pytest.approx(0.5, rel=1e-6)

    def test_earnings_today(self) -> None:
        """Earnings today (0 days) → impact = 1.0."""
        result = compute_earnings_impact(0, 30)
        assert result is not None
        assert result == pytest.approx(1.0, rel=1e-6)

    def test_earnings_outside_dte(self) -> None:
        """Earnings after expiration → 0.0."""
        result = compute_earnings_impact(45, 30)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_earnings_passed(self) -> None:
        """Negative days (earnings already passed) → 0.0."""
        result = compute_earnings_impact(-5, 30)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_none_days_to_earnings(self) -> None:
        """None days to earnings → None."""
        assert compute_earnings_impact(None, 30) is None

    def test_zero_dte(self) -> None:
        """Zero DTE → None (can't compute ratio)."""
        assert compute_earnings_impact(5, 0) is None

    def test_negative_dte(self) -> None:
        """Negative DTE → None."""
        assert compute_earnings_impact(5, -1) is None


# ---------------------------------------------------------------------------
# compute_short_interest tests
# ---------------------------------------------------------------------------


class TestShortInterest:
    """Tests for short interest ratio passthrough."""

    def test_valid_ratio(self) -> None:
        """Valid short ratio passes through unchanged."""
        assert compute_short_interest(3.5) == pytest.approx(3.5, rel=1e-6)

    def test_zero_ratio(self) -> None:
        """Zero short ratio is valid."""
        assert compute_short_interest(0.0) == pytest.approx(0.0, abs=1e-9)

    def test_none(self) -> None:
        """None input → None."""
        assert compute_short_interest(None) is None

    def test_negative(self) -> None:
        """Negative short ratio → None (invalid)."""
        assert compute_short_interest(-1.0) is None

    def test_inf(self) -> None:
        """Infinity → None."""
        assert compute_short_interest(float("inf")) is None

    def test_nan(self) -> None:
        """NaN → None."""
        assert compute_short_interest(float("nan")) is None

    def test_large_ratio(self) -> None:
        """Large but valid ratio passes through."""
        result = compute_short_interest(25.0)
        assert result is not None
        assert result == pytest.approx(25.0, rel=1e-6)


# ---------------------------------------------------------------------------
# compute_div_impact tests
# ---------------------------------------------------------------------------


class TestDivImpact:
    """Tests for dividend impact score."""

    def test_ex_date_tomorrow_high_yield(self) -> None:
        """Ex-date in 1 day, 5% yield, 30 DTE → high impact."""
        result = compute_div_impact(0.05, 30, 1)
        assert result is not None
        # proximity = 1 - 1/30 = 0.9667, yield_weight = min(0.05/0.05, 1.0) = 1.0
        expected = (1.0 - 1 / 30) * 1.0
        assert result == pytest.approx(expected, rel=1e-4)

    def test_ex_date_far_low_yield(self) -> None:
        """Ex-date in 25 days, 1% yield, 30 DTE → low impact."""
        result = compute_div_impact(0.01, 30, 25)
        assert result is not None
        # proximity = 1 - 25/30 = 0.1667, yield_weight = min(0.01/0.05, 1.0) = 0.2
        expected = (1.0 - 25 / 30) * 0.2
        assert result == pytest.approx(expected, rel=1e-4)

    def test_ex_date_outside_dte(self) -> None:
        """Ex-date after expiration → 0.0."""
        result = compute_div_impact(0.03, 30, 45)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_ex_date_passed(self) -> None:
        """Negative days to ex → 0.0."""
        result = compute_div_impact(0.03, 30, -5)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_none_days_to_ex(self) -> None:
        """None days to ex → None."""
        assert compute_div_impact(0.03, 30, None) is None

    def test_zero_dte(self) -> None:
        """Zero DTE → None."""
        assert compute_div_impact(0.03, 0, 5) is None

    def test_zero_yield(self) -> None:
        """Zero dividend yield → 0.0 impact (no yield weight)."""
        result = compute_div_impact(0.0, 30, 5)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_high_yield_cap(self) -> None:
        """Yield > 5% → yield_weight capped at 1.0."""
        result = compute_div_impact(0.10, 30, 15)
        assert result is not None
        # proximity = 1 - 15/30 = 0.5, yield_weight = min(0.10/0.05, 1.0) = 1.0
        expected = 0.5 * 1.0
        assert result == pytest.approx(expected, rel=1e-4)

    def test_inf_yield(self) -> None:
        """Infinity yield → None."""
        assert compute_div_impact(float("inf"), 30, 5) is None


# ---------------------------------------------------------------------------
# compute_iv_crush_history tests
# ---------------------------------------------------------------------------


class TestIvCrushHistory:
    """Tests for IV crush history proxy."""

    def test_typical_crush(self) -> None:
        """Pre-earnings HV > post-earnings HV → ratio > 1 (crush)."""
        hv_pre = pd.Series([25.0, 28.0, 30.0, 27.0, 26.0])
        hv_post = pd.Series([15.0, 16.0, 14.0, 15.5, 14.5])
        result = compute_iv_crush_history(hv_pre, hv_post)
        assert result is not None
        expected = hv_pre.mean() / hv_post.mean()
        assert result == pytest.approx(expected, rel=1e-6)
        assert result > 1.0

    def test_expansion(self) -> None:
        """Pre-earnings HV < post-earnings HV → ratio < 1 (expansion)."""
        hv_pre = pd.Series([15.0, 16.0, 14.0])
        hv_post = pd.Series([25.0, 28.0, 30.0])
        result = compute_iv_crush_history(hv_pre, hv_post)
        assert result is not None
        assert result < 1.0

    def test_equal_hv(self) -> None:
        """Equal HV → ratio = 1.0."""
        hv_pre = pd.Series([20.0, 20.0, 20.0])
        hv_post = pd.Series([20.0, 20.0, 20.0])
        result = compute_iv_crush_history(hv_pre, hv_post)
        assert result is not None
        assert result == pytest.approx(1.0, rel=1e-6)

    def test_none_pre(self) -> None:
        """None pre-earnings → None."""
        assert compute_iv_crush_history(None, pd.Series([20.0])) is None

    def test_none_post(self) -> None:
        """None post-earnings → None."""
        assert compute_iv_crush_history(pd.Series([20.0]), None) is None

    def test_empty_pre(self) -> None:
        """Empty pre-earnings → None."""
        assert compute_iv_crush_history(pd.Series([], dtype=float), pd.Series([20.0])) is None

    def test_empty_post(self) -> None:
        """Empty post-earnings → None."""
        assert compute_iv_crush_history(pd.Series([20.0]), pd.Series([], dtype=float)) is None

    def test_zero_post_mean(self) -> None:
        """Zero post-earnings mean → None (division by zero)."""
        hv_pre = pd.Series([20.0, 25.0])
        hv_post = pd.Series([0.0, 0.0])
        assert compute_iv_crush_history(hv_pre, hv_post) is None

    def test_all_nan_pre(self) -> None:
        """All NaN in pre-earnings → None."""
        hv_pre = pd.Series([np.nan, np.nan])
        hv_post = pd.Series([20.0, 25.0])
        assert compute_iv_crush_history(hv_pre, hv_post) is None

    def test_partial_nan_handled(self) -> None:
        """Partial NaN in data → computes from clean values."""
        hv_pre = pd.Series([25.0, np.nan, 30.0])
        hv_post = pd.Series([15.0, 16.0, np.nan])
        result = compute_iv_crush_history(hv_pre, hv_post)
        assert result is not None
        # pre_mean = (25+30)/2 = 27.5, post_mean = (15+16)/2 = 15.5
        expected = 27.5 / 15.5
        assert result == pytest.approx(expected, rel=1e-6)
