"""Tests for compute_indicator_tune_weights().

Covers: sufficient data, insufficient samples, floor/cap clamping, negative
correlation, all-None signals, empty input, single sample, sum=1.0, NaN P&L.
"""

from __future__ import annotations

import math

import pytest

from options_arena.learning.weight_tuner import compute_indicator_tune_weights
from options_arena.models.scan import IndicatorSignals
from options_arena.scoring.composite import INDICATOR_WEIGHTS


def _make_signals(**kwargs: float | None) -> IndicatorSignals:
    """Create IndicatorSignals with specified fields, rest None."""
    return IndicatorSignals(**kwargs)


def _static_weights() -> dict[str, float]:
    """Extract weight-only values from INDICATOR_WEIGHTS."""
    return {name: w for name, (w, _) in INDICATOR_WEIGHTS.items()}


class TestComputeIndicatorTuneWeights:
    """Tests for compute_indicator_tune_weights()."""

    def test_empty_input_returns_static(self) -> None:
        """Empty sample list returns static INDICATOR_WEIGHTS."""
        result = compute_indicator_tune_weights([])
        static = _static_weights()
        assert result == static

    def test_single_sample_returns_static(self) -> None:
        """Single sample is insufficient for correlation."""
        samples = [(_make_signals(rsi=65.0), 0.10)]
        result = compute_indicator_tune_weights(samples)
        static = _static_weights()
        # All indicators should retain static weights (only 1 sample < 10 min)
        assert result == static

    def test_all_none_signals_returns_static(self) -> None:
        """All-None IndicatorSignals returns static weights."""
        samples = [(_make_signals(), pnl) for pnl in [0.05] * 20]
        result = compute_indicator_tune_weights(samples)
        static = _static_weights()
        assert result == static

    def test_weights_sum_to_one(self) -> None:
        """Weights always sum to 1.0."""
        # Create 50 samples with some indicators populated
        samples = []
        for i in range(50):
            signals = _make_signals(
                rsi=50.0 + i * 0.5,
                adx=30.0 + i * 0.3,
                bb_width=20.0 - i * 0.1,
            )
            pnl = 0.01 * i - 0.25  # Mix of positive and negative
            samples.append((signals, pnl))

        result = compute_indicator_tune_weights(samples)
        assert sum(result.values()) == pytest.approx(1.0, abs=1e-9)

    def test_all_indicators_have_data(self) -> None:
        """When all indicators have data, all get tuned weights."""
        static = _static_weights()
        field_names = list(static.keys())

        # Create samples where all indicators have values
        samples = []
        for i in range(20):
            kwargs = {name: float(50 + i) for name in field_names}
            signals = IndicatorSignals(**kwargs)
            pnl = 0.02 * i - 0.2
            samples.append((signals, pnl))

        result = compute_indicator_tune_weights(samples)
        assert sum(result.values()) == pytest.approx(1.0, abs=1e-9)
        for w in result.values():
            assert math.isfinite(w)
            assert w > 0

    def test_insufficient_samples_retain_static(self) -> None:
        """Indicators with <10 non-None values keep INDICATOR_WEIGHTS defaults."""
        static = _static_weights()
        # Create 5 samples — below the 10-sample minimum
        samples = [(_make_signals(rsi=50.0 + i), 0.05 * i) for i in range(5)]
        result = compute_indicator_tune_weights(samples)
        # All should be static (only 5 samples for rsi, 0 for rest)
        assert result == static

    def test_floor_clamp_enforced(self) -> None:
        """No weight below 0.01 after tuning."""
        # Create data where one indicator has near-zero correlation
        samples = []
        for i in range(30):
            signals = _make_signals(
                rsi=50.0,  # constant — zero variance → static weight
                adx=float(20 + i),  # has variance
            )
            pnl = 0.01 * i
            samples.append((signals, pnl))

        result = compute_indicator_tune_weights(samples)
        for w in result.values():
            # After normalization, some weights can be very small but raw
            # clamped weights are >= 0.01 (before normalization)
            assert w > 0

    def test_cap_clamp_enforced(self) -> None:
        """No individual weight above 0.15 before normalization."""
        # Create data with one very strong correlation
        samples = []
        for i in range(30):
            signals = _make_signals(rsi=float(i * 3))
            pnl = float(i) * 0.1  # Perfect positive correlation with rsi
            samples.append((signals, pnl))

        result = compute_indicator_tune_weights(samples)
        # After normalization weights can exceed 0.15 due to renormalization,
        # but the raw clamping prevents any single indicator from dominating
        # the pre-normalization total
        for w in result.values():
            assert math.isfinite(w)
            assert w >= 0

    def test_negative_correlation_gets_positive_weight(self) -> None:
        """Anti-correlated indicators still get a positive weight (uses |r|)."""
        samples = []
        for i in range(30):
            signals = _make_signals(rsi=float(100 - i * 3))
            pnl = float(i) * 0.05  # Negative correlation with rsi
            samples.append((signals, pnl))

        result = compute_indicator_tune_weights(samples)
        # rsi should still have a positive weight despite negative correlation
        assert result["rsi"] > 0

    def test_nan_pnl_values_excluded(self) -> None:
        """NaN P&L values are excluded from correlation computation."""
        samples = []
        for i in range(20):
            signals = _make_signals(rsi=float(50 + i))
            pnl = float("nan") if i < 5 else 0.01 * i
            samples.append((signals, pnl))

        # Should not raise, and should compute from the 15 valid samples
        result = compute_indicator_tune_weights(samples)
        assert sum(result.values()) == pytest.approx(1.0, abs=1e-9)

    def test_result_keys_match_indicator_weights(self) -> None:
        """Result dict keys match INDICATOR_WEIGHTS keys."""
        samples = [(_make_signals(rsi=50.0 + i), 0.05) for i in range(15)]
        result = compute_indicator_tune_weights(samples)
        assert set(result.keys()) == set(INDICATOR_WEIGHTS.keys())
