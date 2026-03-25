"""Unit tests for composite_score() weight_overrides parameter.

Tests that weight overrides:
- Do not change behavior when None or empty
- Change the computed score when non-trivial overrides are provided
- Reject weight sets that sum outside ±0.05 of 1.0
- Accept weight sets within tolerance
- Merge partial overrides with defaults
- Reject NaN/Inf override values
"""

import math

import pytest

from options_arena.models.scan import IndicatorSignals
from options_arena.scoring.composite import (
    INDICATOR_WEIGHTS,
    composite_score,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Fields with unit-interval [0, 1] validators — cannot accept arbitrary 0-100 values.
_UNIT_INTERVAL_FIELDS: set[str] = {"ml_regime_confidence"}


def _make_signals(**kwargs: float | None) -> IndicatorSignals:
    """Build IndicatorSignals with explicit values."""
    return IndicatorSignals(**kwargs)


def _make_uniform_signals(value: float) -> IndicatorSignals:
    """Build IndicatorSignals with all weighted fields set to *value*.

    Fields with restricted ranges (e.g. [0, 1]) are set to None when the value
    falls outside their valid range.
    """
    all_fields = list(IndicatorSignals.model_fields.keys())
    return IndicatorSignals(
        **{
            field: (value if 0.0 <= value <= 1.0 else None)
            if field in _UNIT_INTERVAL_FIELDS
            else value
            for field in all_fields
        }
    )


def _default_weight_sum() -> float:
    """Return the sum of all default indicator weights."""
    return sum(w for w, _ in INDICATOR_WEIGHTS.values())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompositeWeightOverrides:
    """Tests for composite_score() weight_overrides parameter."""

    @pytest.mark.critical
    def test_no_overrides_unchanged(self) -> None:
        """composite_score without overrides produces same result as before."""
        signals = _make_signals(rsi=80.0, adx=40.0)

        score_default = composite_score(signals)
        score_none = composite_score(signals, weight_overrides=None)
        score_empty = composite_score(signals, weight_overrides={})

        assert score_default == pytest.approx(score_none, rel=1e-9)
        assert score_default == pytest.approx(score_empty, rel=1e-9)

    def test_overrides_change_score(self) -> None:
        """composite_score with overrides produces different result.

        Heavily weight RSI while de-weighting ADX.  With rsi=80 and adx=40,
        increasing RSI's weight should raise the score.
        """
        signals = _make_signals(rsi=80.0, adx=40.0)
        score_default = composite_score(signals)

        # Build overrides: increase RSI weight, decrease ADX weight by same amount
        rsi_default = INDICATOR_WEIGHTS["rsi"][0]
        adx_default = INDICATOR_WEIGHTS["adx"][0]
        shift = 0.03
        overrides = {
            "rsi": rsi_default + shift,
            "adx": adx_default - shift,
        }

        score_override = composite_score(signals, weight_overrides=overrides)

        # Scores must differ because weight distribution changed
        assert score_override != pytest.approx(score_default, rel=1e-6)
        # With more weight on the higher value (80 vs 40), score should increase
        assert score_override > score_default

    def test_invalid_sum_rejected(self) -> None:
        """Weights summing to 0.5 raises ValueError."""
        signals = _make_signals(rsi=50.0)

        # Override RSI weight to 0.5 — makes sum >> 1.0
        overrides = {"rsi": 0.5}

        with pytest.raises(ValueError, match="sum to ~1.0"):
            composite_score(signals, weight_overrides=overrides)

    def test_valid_sum_tolerance(self) -> None:
        """Weights summing to 0.97 accepted (within ±0.05)."""
        signals = _make_signals(rsi=80.0, adx=40.0)

        # Shift a small amount between two weights so sum drops by 0.03
        rsi_default = INDICATOR_WEIGHTS["rsi"][0]
        overrides = {"rsi": rsi_default - 0.03}

        # Sum = 1.0 - 0.03 = 0.97 — within ±0.05 tolerance
        score = composite_score(signals, weight_overrides=overrides)
        assert math.isfinite(score)
        assert 0.0 <= score <= 100.0

    def test_partial_overrides_merged(self) -> None:
        """Only overridden keys replaced, rest keep defaults."""
        signals = _make_signals(rsi=80.0, adx=40.0, bb_width=60.0)
        score_default = composite_score(signals)

        # Override only RSI weight — ADX and bb_width keep default weights
        rsi_default = INDICATOR_WEIGHTS["rsi"][0]
        adx_default = INDICATOR_WEIGHTS["adx"][0]
        # Shift weight from RSI to ADX so sum stays 1.0
        overrides = {
            "rsi": rsi_default - 0.02,
            "adx": adx_default + 0.02,
        }

        score_override = composite_score(signals, weight_overrides=overrides)

        # bb_width's contribution should be unchanged (same weight)
        # but overall score differs due to rsi/adx rebalancing
        assert score_override != pytest.approx(score_default, rel=1e-6)

    def test_nan_override_rejected(self) -> None:
        """NaN in weight override values is rejected by isfinite() check."""
        signals = _make_signals(rsi=50.0)

        with pytest.raises(ValueError, match="finite"):
            composite_score(signals, weight_overrides={"rsi": float("nan")})

    def test_inf_override_rejected(self) -> None:
        """Inf in weight override values is rejected by isfinite() check."""
        signals = _make_signals(rsi=50.0)

        with pytest.raises(ValueError, match="finite"):
            composite_score(signals, weight_overrides={"rsi": float("inf")})

    def test_negative_inf_override_rejected(self) -> None:
        """Negative Inf in weight override values is rejected."""
        signals = _make_signals(rsi=50.0)

        with pytest.raises(ValueError, match="finite"):
            composite_score(signals, weight_overrides={"rsi": float("-inf")})

    def test_unknown_keys_ignored(self) -> None:
        """Override keys not in INDICATOR_WEIGHTS are silently ignored."""
        signals = _make_signals(rsi=80.0)
        score_default = composite_score(signals)

        # "nonexistent_indicator" is not in INDICATOR_WEIGHTS — should be ignored
        score_with_unknown = composite_score(
            signals, weight_overrides={"nonexistent_indicator": 0.5}
        )

        assert score_with_unknown == pytest.approx(score_default, rel=1e-9)

    def test_empty_overrides_identical_to_default(self) -> None:
        """Empty dict overrides produce identical score to no overrides."""
        signals = _make_uniform_signals(50.0)

        score_default = composite_score(signals)
        score_empty = composite_score(signals, weight_overrides={})

        assert score_empty == pytest.approx(score_default, rel=1e-9)

    def test_weight_sum_guard(self) -> None:
        """Verify the default INDICATOR_WEIGHTS sum to ~1.0."""
        total = _default_weight_sum()
        assert total == pytest.approx(1.0, abs=1e-9)
