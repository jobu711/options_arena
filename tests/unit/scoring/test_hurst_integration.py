"""Verify hurst_exponent is properly wired into the scoring system."""

from options_arena.models.scan import IndicatorSignals
from options_arena.scoring.composite import INDICATOR_WEIGHTS
from options_arena.scoring.normalization import DOMAIN_BOUNDS, INVERTED_INDICATORS


class TestHurstScoringIntegration:
    """Verify hurst_exponent is properly wired into the scoring system."""

    def test_weights_sum_to_one(self) -> None:
        """INDICATOR_WEIGHTS must sum to exactly 1.0."""
        total = sum(w for w, _ in INDICATOR_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_hurst_in_weights(self) -> None:
        """hurst_exponent has weight 0.02 in regime category."""
        assert "hurst_exponent" in INDICATOR_WEIGHTS
        weight, category = INDICATOR_WEIGHTS["hurst_exponent"]
        assert weight == 0.02
        assert category == "regime"

    def test_hurst_in_domain_bounds(self) -> None:
        """hurst_exponent has bounds [0.0, 1.0]."""
        assert "hurst_exponent" in DOMAIN_BOUNDS
        lo, hi = DOMAIN_BOUNDS["hurst_exponent"]
        assert lo == 0.0
        assert hi == 1.0

    def test_hurst_not_inverted(self) -> None:
        """Higher H = trending = favorable -> NOT inverted."""
        assert "hurst_exponent" not in INVERTED_INDICATORS

    def test_normalization_bounds_valid(self) -> None:
        """Hurst domain bounds produce valid normalization (lo < hi)."""
        lo, hi = DOMAIN_BOUNDS["hurst_exponent"]
        assert lo < hi

    def test_hurst_field_on_indicator_signals(self) -> None:
        """IndicatorSignals has hurst_exponent field defaulting to None."""
        signals = IndicatorSignals()
        assert signals.hurst_exponent is None

    def test_hurst_field_settable(self) -> None:
        """IndicatorSignals accepts hurst_exponent value."""
        signals = IndicatorSignals(hurst_exponent=0.65)
        assert signals.hurst_exponent == 0.65

    def test_roc_weight_reduced(self) -> None:
        """roc weight reduced from 0.03 to 0.02 for redistribution."""
        weight, _ = INDICATOR_WEIGHTS["roc"]
        assert weight == 0.02

    def test_put_call_ratio_weight_reduced(self) -> None:
        """put_call_ratio weight reduced from 0.03 to 0.02 for redistribution."""
        weight, _ = INDICATOR_WEIGHTS["put_call_ratio"]
        assert weight == 0.02
