"""Tests for extended options-specific indicators: compute_pop, compute_optimal_dte,
compute_spread_quality, compute_max_loss_ratio.

Every indicator is tested with:
1. Known-value test (with calculation in docstring)
2. Edge cases (zero/None inputs, division guards)
3. Both CALL and PUT for PoP
"""

import pandas as pd
import pytest
from scipy.stats import norm

from options_arena.indicators.options_specific import (
    compute_max_loss_ratio,
    compute_optimal_dte,
    compute_pop,
    compute_spread_quality,
)
from options_arena.models.enums import OptionType

# ---------------------------------------------------------------------------
# compute_pop tests
# ---------------------------------------------------------------------------


class TestComputePoP:
    """Tests for Probability of Profit."""

    def test_known_value_call(self) -> None:
        """Known-value: PoP for call = N(d2).

        d2 = 0.5 => N(0.5) = 0.6915 (approx)
        Reference: BSM standard normal CDF.
        """
        result = compute_pop(d2=0.5, option_type=OptionType.CALL)
        assert result is not None
        assert result == pytest.approx(float(norm.cdf(0.5)), rel=1e-4)

    def test_known_value_put(self) -> None:
        """Known-value: PoP for put = N(-d2).

        d2 = 0.5 => N(-0.5) = 0.3085 (approx)
        Reference: BSM standard normal CDF.
        """
        result = compute_pop(d2=0.5, option_type=OptionType.PUT)
        assert result is not None
        assert result == pytest.approx(float(norm.cdf(-0.5)), rel=1e-4)

    def test_d2_zero_call(self) -> None:
        """d2=0: call PoP = N(0) = 0.5 (ATM, at-the-forward)."""
        result = compute_pop(d2=0.0, option_type=OptionType.CALL)
        assert result is not None
        assert result == pytest.approx(0.5, rel=1e-4)

    def test_d2_zero_put(self) -> None:
        """d2=0: put PoP = N(0) = 0.5 (ATM, at-the-forward)."""
        result = compute_pop(d2=0.0, option_type=OptionType.PUT)
        assert result is not None
        assert result == pytest.approx(0.5, rel=1e-4)

    def test_deep_itm_call(self) -> None:
        """Large positive d2: call PoP approaches 1.0."""
        result = compute_pop(d2=3.0, option_type=OptionType.CALL)
        assert result is not None
        assert result > 0.99

    def test_deep_otm_call(self) -> None:
        """Large negative d2: call PoP approaches 0.0."""
        result = compute_pop(d2=-3.0, option_type=OptionType.CALL)
        assert result is not None
        assert result < 0.01

    def test_deep_itm_put(self) -> None:
        """Large negative d2: put PoP = N(-d2) = N(3) approaches 1.0."""
        result = compute_pop(d2=-3.0, option_type=OptionType.PUT)
        assert result is not None
        assert result > 0.99

    def test_deep_otm_put(self) -> None:
        """Large positive d2: put PoP = N(-d2) = N(-3) approaches 0.0."""
        result = compute_pop(d2=3.0, option_type=OptionType.PUT)
        assert result is not None
        assert result < 0.01

    def test_call_put_complement(self) -> None:
        """Call PoP + Put PoP = 1.0 for same d2."""
        d2 = 0.75
        call_pop = compute_pop(d2=d2, option_type=OptionType.CALL)
        put_pop = compute_pop(d2=d2, option_type=OptionType.PUT)
        assert call_pop is not None
        assert put_pop is not None
        assert (call_pop + put_pop) == pytest.approx(1.0, rel=1e-6)

    def test_nan_d2_returns_none(self) -> None:
        """NaN d2 returns None."""
        result = compute_pop(d2=float("nan"), option_type=OptionType.CALL)
        assert result is None

    def test_inf_d2_returns_none(self) -> None:
        """Infinite d2 returns None."""
        result = compute_pop(d2=float("inf"), option_type=OptionType.CALL)
        assert result is None

    def test_result_bounded(self) -> None:
        """PoP is always in [0, 1] for finite d2."""
        for d2 in [-10.0, -1.0, 0.0, 1.0, 10.0]:
            for otype in (OptionType.CALL, OptionType.PUT):
                result = compute_pop(d2=d2, option_type=otype)
                assert result is not None
                assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# compute_optimal_dte tests
# ---------------------------------------------------------------------------


class TestComputeOptimalDTE:
    """Tests for theta-normalised expected value."""

    def test_known_value(self) -> None:
        """Known-value: EV=10, theta=-2, optimal = 10/2 = 5.0."""
        result = compute_optimal_dte(theta=-2.0, expected_value=10.0)
        assert result is not None
        assert result == pytest.approx(5.0, rel=1e-4)

    def test_positive_theta(self) -> None:
        """Positive theta (short option): still divides by |theta|."""
        result = compute_optimal_dte(theta=2.0, expected_value=10.0)
        assert result is not None
        assert result == pytest.approx(5.0, rel=1e-4)

    def test_negative_ev(self) -> None:
        """Negative expected value produces negative ratio."""
        result = compute_optimal_dte(theta=-1.0, expected_value=-5.0)
        assert result is not None
        assert result == pytest.approx(-5.0, rel=1e-4)

    def test_zero_theta_returns_none(self) -> None:
        """Zero theta returns None (undefined ratio)."""
        result = compute_optimal_dte(theta=0.0, expected_value=10.0)
        assert result is None

    def test_none_ev_returns_none(self) -> None:
        """None expected_value returns None."""
        result = compute_optimal_dte(theta=-2.0, expected_value=None)
        assert result is None

    def test_nan_theta_returns_none(self) -> None:
        """NaN theta returns None."""
        result = compute_optimal_dte(theta=float("nan"), expected_value=10.0)
        assert result is None

    def test_inf_theta_returns_none(self) -> None:
        """Inf theta returns None."""
        result = compute_optimal_dte(theta=float("inf"), expected_value=10.0)
        assert result is None

    def test_nan_ev_returns_none(self) -> None:
        """NaN expected_value returns None."""
        result = compute_optimal_dte(theta=-2.0, expected_value=float("nan"))
        assert result is None

    def test_inf_ev_returns_none(self) -> None:
        """Inf expected_value returns None."""
        result = compute_optimal_dte(theta=-2.0, expected_value=float("inf"))
        assert result is None


# ---------------------------------------------------------------------------
# compute_spread_quality tests
# ---------------------------------------------------------------------------


class TestComputeSpreadQuality:
    """Tests for OI-weighted average bid-ask spread."""

    def test_known_value(self) -> None:
        """Known-value: OI-weighted average.

        Strike 1: spread=0.50, OI=200 => 0.50*200 = 100
        Strike 2: spread=1.00, OI=800 => 1.00*800 = 800
        Weighted avg = (100 + 800) / (200 + 800) = 900/1000 = 0.90
        """
        chain = pd.DataFrame(
            {
                "bid": [2.00, 3.00],
                "ask": [2.50, 4.00],
                "openInterest": [200, 800],
            }
        )
        result = compute_spread_quality(chain)
        assert result is not None
        assert result == pytest.approx(0.90, rel=1e-4)

    def test_uniform_oi(self) -> None:
        """Uniform OI: weighted avg equals simple avg of spreads."""
        chain = pd.DataFrame(
            {
                "bid": [1.0, 2.0, 3.0],
                "ask": [1.5, 2.5, 3.5],
                "openInterest": [100, 100, 100],
            }
        )
        result = compute_spread_quality(chain)
        assert result is not None
        # All spreads are 0.5, avg = 0.5
        assert result == pytest.approx(0.5, rel=1e-4)

    def test_tight_spreads_better(self) -> None:
        """Lower spread_quality value indicates better liquidity."""
        tight = pd.DataFrame({"bid": [10.0], "ask": [10.05], "openInterest": [1000]})
        wide = pd.DataFrame({"bid": [10.0], "ask": [11.00], "openInterest": [1000]})
        tight_result = compute_spread_quality(tight)
        wide_result = compute_spread_quality(wide)
        assert tight_result is not None
        assert wide_result is not None
        assert tight_result < wide_result

    def test_zero_total_oi_returns_none(self) -> None:
        """All zero OI returns None."""
        chain = pd.DataFrame({"bid": [1.0], "ask": [1.5], "openInterest": [0]})
        result = compute_spread_quality(chain)
        assert result is None

    def test_empty_chain_returns_none(self) -> None:
        """Empty DataFrame returns None."""
        chain = pd.DataFrame(columns=["bid", "ask", "openInterest"])
        result = compute_spread_quality(chain)
        assert result is None

    def test_missing_columns_returns_none(self) -> None:
        """Missing required columns returns None."""
        chain = pd.DataFrame({"bid": [1.0], "ask": [1.5]})
        result = compute_spread_quality(chain)
        assert result is None

    def test_inf_spread_returns_none(self) -> None:
        """Inf spread values produce None result."""
        chain = pd.DataFrame({"bid": [0.0], "ask": [float("inf")], "openInterest": [100]})
        result = compute_spread_quality(chain)
        assert result is None


# ---------------------------------------------------------------------------
# compute_max_loss_ratio tests
# ---------------------------------------------------------------------------


class TestComputeMaxLossRatio:
    """Tests for max loss ratio: contract_cost / account_risk_budget."""

    def test_known_value(self) -> None:
        """Known-value: 500 / 10000 = 0.05 (5% of risk budget)."""
        result = compute_max_loss_ratio(
            contract_cost=500.0,
            account_risk_budget=10000.0,
        )
        assert result is not None
        assert result == pytest.approx(0.05, rel=1e-4)

    def test_cost_equals_budget(self) -> None:
        """Cost equals budget: ratio = 1.0 (full risk budget)."""
        result = compute_max_loss_ratio(
            contract_cost=10000.0,
            account_risk_budget=10000.0,
        )
        assert result is not None
        assert result == pytest.approx(1.0, rel=1e-4)

    def test_cost_exceeds_budget(self) -> None:
        """Cost exceeds budget: ratio > 1.0 (over-sized position)."""
        result = compute_max_loss_ratio(
            contract_cost=15000.0,
            account_risk_budget=10000.0,
        )
        assert result is not None
        assert result > 1.0

    def test_zero_cost_returns_none(self) -> None:
        """Zero contract cost returns None."""
        result = compute_max_loss_ratio(
            contract_cost=0.0,
            account_risk_budget=10000.0,
        )
        assert result is None

    def test_negative_cost_returns_none(self) -> None:
        """Negative contract cost returns None."""
        result = compute_max_loss_ratio(
            contract_cost=-100.0,
            account_risk_budget=10000.0,
        )
        assert result is None

    def test_zero_budget_returns_none(self) -> None:
        """Zero risk budget returns None (div-by-zero guard)."""
        result = compute_max_loss_ratio(
            contract_cost=500.0,
            account_risk_budget=0.0,
        )
        assert result is None

    def test_negative_budget_returns_none(self) -> None:
        """Negative risk budget returns None."""
        result = compute_max_loss_ratio(
            contract_cost=500.0,
            account_risk_budget=-10000.0,
        )
        assert result is None

    def test_nan_cost_returns_none(self) -> None:
        """NaN contract cost returns None."""
        result = compute_max_loss_ratio(
            contract_cost=float("nan"),
            account_risk_budget=10000.0,
        )
        assert result is None

    def test_inf_cost_returns_none(self) -> None:
        """Inf contract cost returns None."""
        result = compute_max_loss_ratio(
            contract_cost=float("inf"),
            account_risk_budget=10000.0,
        )
        assert result is None

    def test_nan_budget_returns_none(self) -> None:
        """NaN risk budget returns None."""
        result = compute_max_loss_ratio(
            contract_cost=500.0,
            account_risk_budget=float("nan"),
        )
        assert result is None

    def test_inf_budget_returns_none(self) -> None:
        """Inf risk budget returns None."""
        result = compute_max_loss_ratio(
            contract_cost=500.0,
            account_risk_budget=float("inf"),
        )
        assert result is None

    def test_small_ratio_good_sizing(self) -> None:
        """Small ratio indicates conservative position sizing."""
        result = compute_max_loss_ratio(
            contract_cost=100.0,
            account_risk_budget=50000.0,
        )
        assert result is not None
        assert result < 0.01
