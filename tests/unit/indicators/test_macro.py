"""Tests for macro regime classification.

Tests compute_macro_regime() with:
1. Expansionary regime (positive spread, low unemployment)
2. Contractionary regime (inverted curve, high unemployment)
3. Transitional regime (mixed signals)
4. Insufficient data (< 50% completeness)
5. Edge cases (boundary values, NaN inputs, all-None)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from options_arena.indicators.macro import compute_macro_regime
from options_arena.models.macro import MacroContext


class TestExpansionary:
    """Tests for expansionary regime classification."""

    def test_clear_expansion(self) -> None:
        """Positive yield spread + low unemployment -> expansionary."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,  # positive: normal curve
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.5,
            industrial_production_yoy=3.0,
            unemployment_rate=0.035,  # 3.5% < 4.5% threshold
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "expansionary"
        assert 0.3 <= result.confidence <= 0.9

    def test_strong_expansion(self) -> None:
        """Very steep curve + very low unemployment -> high confidence expansionary."""
        macro = MacroContext(
            treasury_10y=0.05,
            treasury_2y=0.02,
            yield_spread_10y2y=0.03,  # very steep
            fed_funds_rate=0.03,
            vix=12.0,
            cpi_yoy=2.0,
            industrial_production_yoy=5.0,
            unemployment_rate=0.025,  # very low
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "expansionary"
        assert result.confidence >= 0.6

    def test_expansion_boundary_unemployment(self) -> None:
        """Unemployment at exactly 4.5% -> NOT expansionary (must be < 0.045)."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,
            fed_funds_rate=0.04,
            vix=16.0,
            cpi_yoy=2.5,
            industrial_production_yoy=2.0,
            unemployment_rate=0.045,  # exactly at threshold, not below
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "transitional"


class TestContractionary:
    """Tests for contractionary regime classification."""

    def test_clear_contraction(self) -> None:
        """Inverted yield curve + high unemployment -> contractionary."""
        macro = MacroContext(
            treasury_10y=0.035,
            treasury_2y=0.045,
            yield_spread_10y2y=-0.01,  # inverted
            fed_funds_rate=0.055,
            vix=28.0,
            cpi_yoy=4.0,
            industrial_production_yoy=-1.0,
            unemployment_rate=0.065,  # 6.5% > 5.0% threshold
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "contractionary"
        assert 0.3 <= result.confidence <= 0.9

    def test_deep_inversion(self) -> None:
        """Deep inversion + very high unemployment -> high confidence contraction."""
        macro = MacroContext(
            treasury_10y=0.03,
            treasury_2y=0.05,
            yield_spread_10y2y=-0.02,  # deep inversion
            fed_funds_rate=0.055,
            vix=32.0,
            cpi_yoy=5.0,
            industrial_production_yoy=-3.0,
            unemployment_rate=0.08,  # very high
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "contractionary"
        assert result.confidence >= 0.6

    def test_contraction_boundary_unemployment(self) -> None:
        """Unemployment at exactly 5.0% -> NOT contractionary (must be > 0.05)."""
        macro = MacroContext(
            treasury_10y=0.035,
            treasury_2y=0.045,
            yield_spread_10y2y=-0.01,
            fed_funds_rate=0.05,
            vix=25.0,
            cpi_yoy=3.5,
            industrial_production_yoy=0.0,
            unemployment_rate=0.05,  # exactly at threshold, not above
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "transitional"


class TestTransitional:
    """Tests for transitional (mixed signals) regime."""

    def test_inverted_but_low_unemployment(self) -> None:
        """Inverted curve but low unemployment -> transitional (mixed)."""
        macro = MacroContext(
            treasury_10y=0.035,
            treasury_2y=0.04,
            yield_spread_10y2y=-0.005,  # inverted
            fed_funds_rate=0.04,
            vix=18.0,
            cpi_yoy=2.5,
            industrial_production_yoy=1.5,
            unemployment_rate=0.038,  # low unemployment
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "transitional"

    def test_positive_spread_high_unemployment(self) -> None:
        """Positive spread but high unemployment -> transitional (mixed)."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,  # positive
            fed_funds_rate=0.04,
            vix=22.0,
            cpi_yoy=3.0,
            industrial_production_yoy=0.5,
            unemployment_rate=0.06,  # high unemployment
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "transitional"

    def test_flat_curve(self) -> None:
        """Flat yield curve (spread=0) -> transitional."""
        macro = MacroContext(
            treasury_10y=0.04,
            treasury_2y=0.04,
            yield_spread_10y2y=0.0,  # flat, not > 0
            fed_funds_rate=0.04,
            vix=18.0,
            cpi_yoy=2.5,
            industrial_production_yoy=1.0,
            unemployment_rate=0.04,
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "transitional"

    def test_missing_unemployment(self) -> None:
        """Missing unemployment -> transitional (cannot determine expansion/contraction)."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,
            fed_funds_rate=0.04,
            vix=16.0,
            cpi_yoy=2.5,
            industrial_production_yoy=2.0,
            # unemployment_rate is None
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "transitional"

    def test_missing_yield_spread(self) -> None:
        """Missing yield spread -> transitional."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            # yield_spread_10y2y is None
            fed_funds_rate=0.04,
            vix=16.0,
            cpi_yoy=2.5,
            industrial_production_yoy=2.0,
            unemployment_rate=0.035,
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "transitional"


class TestInsufficientData:
    """Tests for insufficient data (< 50% completeness)."""

    def test_all_none(self) -> None:
        """All fields None -> completeness 0.0 -> None."""
        macro = MacroContext()
        result = compute_macro_regime(macro)
        assert result is None

    def test_one_field(self) -> None:
        """Only 1/8 fields -> completeness 12.5% -> None."""
        macro = MacroContext(treasury_10y=0.045)
        result = compute_macro_regime(macro)
        assert result is None

    def test_three_fields(self) -> None:
        """Only 3/8 fields -> completeness 37.5% -> None."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,
        )
        result = compute_macro_regime(macro)
        assert result is None

    def test_exactly_four_fields(self) -> None:
        """4/8 fields -> completeness 50% -> succeeds (>= 0.5 threshold)."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,
            unemployment_rate=0.035,
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert result.regime == "expansionary"


class TestEdgeCases:
    """Edge cases and NaN/Inf guards."""

    def test_nan_yield_spread(self) -> None:
        """NaN yield_spread should be rejected by MacroContext validator."""
        with pytest.raises(ValueError, match="must be finite"):
            MacroContext(yield_spread_10y2y=float("nan"))

    def test_inf_unemployment(self) -> None:
        """Inf unemployment should be rejected by MacroContext validator."""
        with pytest.raises(ValueError, match="must be finite"):
            MacroContext(unemployment_rate=float("inf"))

    def test_confidence_bounds(self) -> None:
        """Confidence should always be in [0.0, 1.0]."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.5,
            industrial_production_yoy=3.0,
            unemployment_rate=0.035,
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_signals_populated(self) -> None:
        """Signals dict should contain key indicators."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.5,
            industrial_production_yoy=3.0,
            unemployment_rate=0.035,
        )
        result = compute_macro_regime(macro)
        assert result is not None
        assert "yield_spread_10y2y" in result.signals
        assert "unemployment_rate" in result.signals
        assert "fed_funds_rate" in result.signals
        assert "vix" in result.signals
        assert result.signals["yield_spread_10y2y"] == pytest.approx(0.01)

    def test_result_is_frozen(self) -> None:
        """MacroRegimeResult should be frozen (immutable)."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.5,
            industrial_production_yoy=3.0,
            unemployment_rate=0.035,
        )
        result = compute_macro_regime(macro)
        assert result is not None
        with pytest.raises(ValidationError):  # frozen model rejects mutation
            result.regime = "something"  # type: ignore[misc]

    def test_fallback_returns_none(self) -> None:
        """MacroContext.fallback() has 0% completeness -> None."""
        macro = MacroContext.fallback()
        result = compute_macro_regime(macro)
        assert result is None

    def test_completeness_at_threshold(self) -> None:
        """Exactly 4 of 8 fields = 50% completeness -> should classify."""
        macro = MacroContext(
            treasury_10y=0.045,
            fed_funds_rate=0.04,
            vix=16.0,
            unemployment_rate=0.065,
            # 4/8 = 50%, yield_spread missing so -> transitional
        )
        result = compute_macro_regime(macro)
        assert result is not None
        # yield_spread is None, so cannot classify directionally
        assert result.regime == "transitional"

    def test_negative_unemployment_extreme(self) -> None:
        """Extremely negative unemployment (invalid real-world) is accepted as data."""
        macro = MacroContext(
            treasury_10y=0.045,
            treasury_2y=0.035,
            yield_spread_10y2y=0.01,
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.0,
            industrial_production_yoy=3.0,
            unemployment_rate=-0.01,  # impossible but not NaN/Inf
        )
        result = compute_macro_regime(macro)
        assert result is not None
        # Negative unemployment < 0.045 threshold -> expansionary
        assert result.regime == "expansionary"
