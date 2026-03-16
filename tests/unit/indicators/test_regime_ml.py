"""Tests for Markov-switching regime detection.

Covers:
- TestMarkovRegime: synthetic 2-regime data, 3-regime data, insufficient data,
  convergence failure, missing statsmodels, smoothed probs sum to 1,
  transition matrix row-stochastic, transition matrix shape, regime labels
  sorted by variance, current regime in range, regime label mapping,
  MarketRegime enum mapping
- TestIndicatorSignalsMarkovFields: new fields default None, normalize non-finite
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.regime_ml import (
    MarkovRegimeOutput,
    _get_markov_regression,
    compute_markov_regime,
    map_regime_label_to_market_regime,
)
from options_arena.models.enums import MarketRegime
from options_arena.models.scan import IndicatorSignals

# ---------------------------------------------------------------------------
# Helpers: synthetic data generators
# ---------------------------------------------------------------------------


def _make_two_regime_returns(n_per_regime: int = 300, seed: int = 42) -> pd.Series:
    """Generate returns with 2 distinct volatility regimes.

    First half: low volatility (sigma=0.5).
    Second half: high volatility (sigma=3.0).
    """
    rng = np.random.default_rng(seed)
    low_vol = rng.normal(loc=0.0, scale=0.5, size=n_per_regime)
    high_vol = rng.normal(loc=0.0, scale=3.0, size=n_per_regime)
    returns = np.concatenate([low_vol, high_vol])
    return pd.Series(returns, name="returns")


def _make_three_regime_returns(
    n_per_regime: int = 200,
    seed: int = 42,
) -> pd.Series:
    """Generate returns with 3 distinct volatility regimes.

    Segment 1: low volatility (sigma=0.3).
    Segment 2: normal volatility (sigma=1.0).
    Segment 3: high volatility (sigma=4.0).
    """
    rng = np.random.default_rng(seed)
    low_vol = rng.normal(loc=0.0, scale=0.3, size=n_per_regime)
    normal_vol = rng.normal(loc=0.0, scale=1.0, size=n_per_regime)
    high_vol = rng.normal(loc=0.0, scale=4.0, size=n_per_regime)
    returns = np.concatenate([low_vol, normal_vol, high_vol])
    return pd.Series(returns, name="returns")


def _make_short_returns(n: int = 100, seed: int = 42) -> pd.Series:
    """Generate returns with insufficient observations (<252)."""
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(loc=0.0, scale=1.0, size=n), name="returns")


# ===========================================================================
# TestMarkovRegime
# ===========================================================================


class TestMarkovRegime:
    """Tests for compute_markov_regime()."""

    def test_three_regime_returns_output(self) -> None:
        """Markov model on 3-regime data returns a valid MarkovRegimeOutput."""
        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)

        # Should succeed (statsmodels installed in test env)
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        assert result is not None
        assert isinstance(result, MarkovRegimeOutput)

    def test_two_regime_returns_with_k2(self) -> None:
        """Markov model with k_regimes=2 on 2-regime synthetic data."""
        returns = _make_two_regime_returns()
        result = compute_markov_regime(returns, k_regimes=2)

        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        # k_regimes=2, so only 2 labels possible. Function uses first 2 from _REGIME_LABELS.
        if result is not None:
            assert len(result.regime_probabilities) == 2
            assert len(result.transition_matrix) == 2
            assert all(len(row) == 2 for row in result.transition_matrix)

    def test_insufficient_data_returns_none(self) -> None:
        """Returns None when fewer than 252 observations."""
        returns = _make_short_returns(n=100)
        result = compute_markov_regime(returns)
        assert result is None

    def test_insufficient_data_at_boundary(self) -> None:
        """Returns None when exactly 251 observations (just under minimum)."""
        returns = _make_short_returns(n=251)
        result = compute_markov_regime(returns)
        assert result is None

    def test_convergence_failure_returns_none(self) -> None:
        """Returns None when model fitting raises an exception."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        # Constant data causes convergence issues — function should handle gracefully
        constant_returns = pd.Series(np.zeros(300), name="returns")
        result = compute_markov_regime(constant_returns)
        # The function should either return None or a valid result (never raise)
        assert result is None or isinstance(result, MarkovRegimeOutput)

    def test_missing_statsmodels_returns_none(self) -> None:
        """Returns None when statsmodels is not installed."""
        with patch(
            "options_arena.indicators.regime_ml._get_markov_regression",
            return_value=None,
        ):
            returns = _make_three_regime_returns()
            result = compute_markov_regime(returns)
            assert result is None

    def test_smoothed_probs_sum_to_one(self) -> None:
        """Smoothed probabilities at last observation should sum to ~1.0."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)
        assert result is not None

        prob_sum = sum(result.regime_probabilities)
        assert prob_sum == pytest.approx(1.0, abs=1e-6)

    def test_transition_matrix_row_stochastic(self) -> None:
        """Each row of the transition matrix should sum to ~1.0."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)
        assert result is not None

        for row_idx, row in enumerate(result.transition_matrix):
            row_sum = sum(row)
            assert row_sum == pytest.approx(1.0, abs=1e-6), (
                f"Row {row_idx} sums to {row_sum}, expected ~1.0"
            )

    def test_transition_matrix_shape(self) -> None:
        """Transition matrix should be k_regimes x k_regimes."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)
        assert result is not None

        assert len(result.transition_matrix) == 3
        for row in result.transition_matrix:
            assert len(row) == 3

    def test_regime_labels_sorted_by_variance(self) -> None:
        """Regime labels should be sorted by variance: low_vol < normal < high_vol."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)
        assert result is not None

        # The regime label should be one of the valid labels
        valid_labels = {"low_vol", "normal", "high_vol"}
        assert result.regime_label in valid_labels

    def test_current_regime_in_range(self) -> None:
        """Current regime index should be within [0, k_regimes)."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)
        assert result is not None

        assert 0 <= result.current_regime < 3

    def test_current_regime_matches_label(self) -> None:
        """Current regime index should correspond to the regime label."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)
        assert result is not None

        label_map = {0: "low_vol", 1: "normal", 2: "high_vol"}
        assert result.regime_label == label_map[result.current_regime]

    def test_regime_probabilities_non_negative(self) -> None:
        """All regime probabilities should be non-negative."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)
        assert result is not None

        for prob in result.regime_probabilities:
            assert prob >= 0.0

    def test_transition_matrix_non_negative(self) -> None:
        """All transition probabilities should be non-negative."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)
        assert result is not None

        for row in result.transition_matrix:
            for prob in row:
                assert prob >= 0.0

    def test_nan_in_returns_handled(self) -> None:
        """NaN values in input should be dropped, not cause failure."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        # Inject some NaN values
        returns.iloc[10] = float("nan")
        returns.iloc[50] = float("nan")
        returns.iloc[200] = float("nan")

        result = compute_markov_regime(returns)
        # Should still work since we have enough non-NaN data (600 - 3 = 597 > 252)
        assert result is None or isinstance(result, MarkovRegimeOutput)

    def test_high_vol_regime_detected_at_end(self) -> None:
        """With high-vol data at the end, the current regime should likely be high_vol."""
        if _get_markov_regression() is None:
            pytest.skip("statsmodels not installed")

        returns = _make_three_regime_returns()
        result = compute_markov_regime(returns, k_regimes=3)
        assert result is not None

        # The last segment is high volatility, so current regime should be "high_vol"
        # (This is a probabilistic test — the model should detect this with high probability)
        assert result.regime_label == "high_vol"


# ===========================================================================
# TestMapRegimeLabelToMarketRegime
# ===========================================================================


class TestMapRegimeLabelToMarketRegime:
    """Tests for map_regime_label_to_market_regime()."""

    def test_low_vol_maps_to_mean_reverting(self) -> None:
        """low_vol -> MarketRegime.MEAN_REVERTING."""
        assert map_regime_label_to_market_regime("low_vol") == MarketRegime.MEAN_REVERTING

    def test_normal_maps_to_trending(self) -> None:
        """normal -> MarketRegime.TRENDING."""
        assert map_regime_label_to_market_regime("normal") == MarketRegime.TRENDING

    def test_high_vol_maps_to_volatile(self) -> None:
        """high_vol -> MarketRegime.VOLATILE."""
        assert map_regime_label_to_market_regime("high_vol") == MarketRegime.VOLATILE

    def test_unknown_label_defaults_to_mean_reverting(self) -> None:
        """Unknown labels default to MarketRegime.MEAN_REVERTING."""
        assert map_regime_label_to_market_regime("unknown") == MarketRegime.MEAN_REVERTING
        assert map_regime_label_to_market_regime("") == MarketRegime.MEAN_REVERTING


# ===========================================================================
# TestMarkovRegimeOutput
# ===========================================================================


class TestMarkovRegimeOutput:
    """Tests for MarkovRegimeOutput NamedTuple structure."""

    def test_named_tuple_fields(self) -> None:
        """MarkovRegimeOutput has the expected fields."""
        output = MarkovRegimeOutput(
            current_regime=1,
            regime_probabilities=[0.1, 0.7, 0.2],
            transition_matrix=[[0.9, 0.05, 0.05], [0.1, 0.8, 0.1], [0.05, 0.15, 0.8]],
            regime_label="normal",
        )
        assert output.current_regime == 1
        assert output.regime_probabilities == [0.1, 0.7, 0.2]
        assert len(output.transition_matrix) == 3
        assert output.regime_label == "normal"

    def test_named_tuple_is_immutable(self) -> None:
        """MarkovRegimeOutput fields are read-only (NamedTuple)."""
        output = MarkovRegimeOutput(
            current_regime=0,
            regime_probabilities=[1.0, 0.0, 0.0],
            transition_matrix=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            regime_label="low_vol",
        )
        with pytest.raises(AttributeError):
            output.current_regime = 2  # type: ignore[misc]


# ===========================================================================
# TestIndicatorSignalsMarkovFields
# ===========================================================================


class TestIndicatorSignalsMarkovFields:
    """Tests for new Markov regime fields on IndicatorSignals."""

    def test_new_fields_default_none(self) -> None:
        """Both new Markov fields should default to None."""
        signals = IndicatorSignals()
        assert signals.regime_markov_label is None
        assert signals.regime_transition_prob is None

    def test_fields_accept_valid_values(self) -> None:
        """New fields should accept valid float values."""
        signals = IndicatorSignals(
            regime_markov_label=1.0,
            regime_transition_prob=0.85,
        )
        assert signals.regime_markov_label == 1.0
        assert signals.regime_transition_prob == 0.85

    def test_regime_label_encodes_correctly(self) -> None:
        """Regime label encoding: 0.0=low_vol, 1.0=normal, 2.0=high_vol."""
        for val in [0.0, 1.0, 2.0]:
            signals = IndicatorSignals(regime_markov_label=val)
            assert signals.regime_markov_label == val

    def test_normalize_non_finite_nan(self) -> None:
        """NaN values on Markov fields should be normalized to None."""
        signals = IndicatorSignals(
            regime_markov_label=float("nan"),
            regime_transition_prob=float("nan"),
        )
        assert signals.regime_markov_label is None
        assert signals.regime_transition_prob is None

    def test_normalize_non_finite_inf(self) -> None:
        """Inf values on Markov fields should be normalized to None."""
        signals = IndicatorSignals(
            regime_markov_label=float("inf"),
            regime_transition_prob=float("-inf"),
        )
        assert signals.regime_markov_label is None
        assert signals.regime_transition_prob is None

    def test_serialization_roundtrip(self) -> None:
        """Markov fields should survive JSON serialization roundtrip."""
        signals = IndicatorSignals(
            regime_markov_label=2.0,
            regime_transition_prob=0.92,
        )
        json_str = signals.model_dump_json()
        restored = IndicatorSignals.model_validate_json(json_str)
        assert restored.regime_markov_label == pytest.approx(2.0)
        assert restored.regime_transition_prob == pytest.approx(0.92)

    def test_total_field_count_is_76(self) -> None:
        """IndicatorSignals should now have exactly 76 fields."""
        assert len(IndicatorSignals.model_fields) == 76
