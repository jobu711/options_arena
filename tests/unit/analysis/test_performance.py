"""Tests for risk-adjusted performance metric computation."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from options_arena.analysis.performance import compute_risk_adjusted_metrics
from options_arena.models.analytics import RiskAdjustedMetrics


class TestComputeRiskAdjustedMetrics:
    """Tests for compute_risk_adjusted_metrics()."""

    def test_sharpe_known_returns(self) -> None:
        """Varying positive returns with zero risk-free rate produce a positive Sharpe."""
        returns = [0.02 + 0.001 * (i % 5) for i in range(50)]
        holding_days = [5] * 50
        result = compute_risk_adjusted_metrics(returns, holding_days, risk_free_rate=0.0)
        assert result.sharpe_ratio is not None
        assert result.sharpe_ratio > 0

    def test_sortino_only_downside_deviation(self) -> None:
        """Sortino uses only negative excess returns for denominator.

        With a mix of positive and negative returns, Sortino >= Sharpe
        because downside vol < total vol.
        """
        returns = [0.05, -0.02, 0.03, -0.01, 0.04] * 10  # 50 trades
        holding_days = [5] * 50
        result = compute_risk_adjusted_metrics(returns, holding_days, risk_free_rate=0.0)
        assert result.sortino_ratio is not None
        assert result.sharpe_ratio is not None
        # Sortino >= Sharpe when there are positive returns
        assert result.sortino_ratio >= result.sharpe_ratio

    def test_max_drawdown_known_curve(self) -> None:
        """Known equity curve with identifiable drawdown."""
        # Up 10%, down 20%, up 5% repeated — has a clear drawdown
        returns = [0.10, -0.20, 0.05] * 20  # 60 trades
        holding_days = [5] * 60
        result = compute_risk_adjusted_metrics(returns, holding_days)
        assert result.max_drawdown_pct is not None
        assert result.max_drawdown_pct > 0  # Positive means drawdown occurred
        assert result.max_drawdown_date is not None

    def test_fewer_than_min_trades_returns_none_ratios(self) -> None:
        """< 30 trades -> None for Sharpe and Sortino, but max drawdown still computed."""
        returns = [0.01] * 10
        holding_days = [5] * 10
        result = compute_risk_adjusted_metrics(returns, holding_days)
        assert result.sharpe_ratio is None
        assert result.sortino_ratio is None
        assert result.total_trades == 10
        # Max drawdown should still be computed
        assert result.max_drawdown_pct is not None

    def test_single_trade_returns_none_ratios(self) -> None:
        """Single trade -> None for Sharpe and Sortino."""
        result = compute_risk_adjusted_metrics([0.05], [5])
        assert result.sharpe_ratio is None
        assert result.sortino_ratio is None
        assert result.total_trades == 1

    def test_zero_std_returns_none_sharpe(self) -> None:
        """Constant returns with zero rf -> std = 0 -> None for Sharpe/Sortino."""
        returns = [0.02] * 50
        holding_days = [5] * 50
        result = compute_risk_adjusted_metrics(returns, holding_days, risk_free_rate=0.0)
        assert result.sharpe_ratio is None  # std == 0

    def test_all_positive_excess_sortino_none(self) -> None:
        """All positive excess returns -> downside deviation = 0 -> Sortino None."""
        returns = [0.10] * 50  # All very positive
        holding_days = [5] * 50
        result = compute_risk_adjusted_metrics(returns, holding_days, risk_free_rate=0.0)
        assert result.sortino_ratio is None  # No downside deviation

    def test_nan_returns_rejected(self) -> None:
        """NaN in returns list -> ValueError."""
        with pytest.raises(ValueError, match="finite"):
            compute_risk_adjusted_metrics([0.01, float("nan"), 0.02], [5, 5, 5])

    def test_inf_returns_rejected(self) -> None:
        """Inf in returns list -> ValueError."""
        with pytest.raises(ValueError, match="finite"):
            compute_risk_adjusted_metrics([0.01, float("inf"), 0.02], [5, 5, 5])

    def test_negative_inf_returns_rejected(self) -> None:
        """Negative infinity in returns list -> ValueError."""
        with pytest.raises(ValueError, match="finite"):
            compute_risk_adjusted_metrics([0.01, float("-inf"), 0.02], [5, 5, 5])

    def test_mismatched_lengths_rejected(self) -> None:
        """Mismatched returns and holding_days lengths -> ValueError."""
        with pytest.raises(ValueError, match="same length"):
            compute_risk_adjusted_metrics([0.01, 0.02], [5])

    def test_empty_returns(self) -> None:
        """Empty returns list -> total_trades=0, all ratios None."""
        result = compute_risk_adjusted_metrics([], [])
        assert result.total_trades == 0
        assert result.sharpe_ratio is None
        assert result.sortino_ratio is None
        assert result.max_drawdown_pct is None
        assert result.annualized_return_pct is None

    def test_frozen_model(self) -> None:
        """RiskAdjustedMetrics is immutable."""
        result = compute_risk_adjusted_metrics([0.01] * 50, [5] * 50)
        with pytest.raises(ValidationError):
            result.total_trades = 999  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        """Model serializes to JSON and back."""
        result = compute_risk_adjusted_metrics([0.01, -0.02, 0.03] * 20, [5] * 60)
        json_str = result.model_dump_json()
        restored = RiskAdjustedMetrics.model_validate_json(json_str)
        assert restored == result

    def test_annualized_return_computed(self) -> None:
        """Annualized return is computed for non-empty returns."""
        returns = [0.01] * 50
        holding_days = [5] * 50
        result = compute_risk_adjusted_metrics(returns, holding_days)
        assert result.annualized_return_pct is not None
        assert math.isfinite(result.annualized_return_pct)
        assert result.annualized_return_pct > 0  # Positive returns -> positive annualized

    def test_max_drawdown_zero_for_always_positive(self) -> None:
        """Strictly increasing equity has zero drawdown."""
        returns = [0.01] * 50  # Always positive, equity always rising
        holding_days = [5] * 50
        result = compute_risk_adjusted_metrics(returns, holding_days)
        assert result.max_drawdown_pct is not None
        assert result.max_drawdown_pct == 0.0

    def test_holding_days_zero_handled(self) -> None:
        """Holding days of 0 does not cause division by zero."""
        returns = [0.01] * 50
        holding_days = [0] * 50
        result = compute_risk_adjusted_metrics(returns, holding_days)
        assert result.total_trades == 50
        # Should not crash — excess returns computed with rf_adj=0

    def test_risk_free_rate_affects_sharpe(self) -> None:
        """Higher risk-free rate reduces Sharpe ratio."""
        returns = [0.02 + 0.001 * (i % 5) for i in range(50)]
        holding_days = [5] * 50

        result_low_rf = compute_risk_adjusted_metrics(returns, holding_days, risk_free_rate=0.0)
        result_high_rf = compute_risk_adjusted_metrics(returns, holding_days, risk_free_rate=0.10)

        assert result_low_rf.sharpe_ratio is not None
        assert result_high_rf.sharpe_ratio is not None
        # Higher risk-free rate means lower excess returns, so lower Sharpe
        assert result_low_rf.sharpe_ratio > result_high_rf.sharpe_ratio

    def test_negative_holding_days_rejected(self) -> None:
        """Negative holding days -> ValueError."""
        with pytest.raises(ValueError, match="must be >= 0"):
            compute_risk_adjusted_metrics([0.01], [-5])
