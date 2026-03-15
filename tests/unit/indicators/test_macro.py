"""Tests for macro regime classification.

Tests compute_macro_regime() with:
1. Expansionary regime (positive spread, low unemployment)
2. Contractionary regime (inverted curve, high unemployment)
3. Transitional regime (mixed signals)
4. Insufficient data (< 50% completeness)
5. Edge cases (boundary values, NaN inputs, all-None)

compute_macro_regime() accepts keyword-only float params and a
completeness_ratio, returning a MacroClassification NamedTuple.
"""

from __future__ import annotations

import pytest

from options_arena.indicators.macro import compute_macro_regime


def _full_completeness() -> float:
    """Return completeness ratio for all 8 fields populated."""
    return 1.0


def _half_completeness() -> float:
    """Return completeness ratio for 4 of 8 fields populated."""
    return 0.5


class TestExpansionary:
    """Tests for expansionary regime classification."""

    def test_clear_expansion(self) -> None:
        """Positive yield spread + low unemployment -> expansionary."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,  # positive: normal curve
            unemployment_rate=0.035,  # 3.5% < 4.5% threshold
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.5,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "expansionary"
        assert 0.3 <= result.confidence <= 0.9

    def test_strong_expansion(self) -> None:
        """Very steep curve + very low unemployment -> high confidence expansionary."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.03,  # very steep
            unemployment_rate=0.025,  # very low
            fed_funds_rate=0.03,
            vix=12.0,
            cpi_yoy=2.0,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "expansionary"
        assert result.confidence >= 0.6

    def test_expansion_boundary_unemployment(self) -> None:
        """Unemployment at exactly 4.5% -> NOT expansionary (must be < 0.045)."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,
            unemployment_rate=0.045,  # exactly at threshold, not below
            fed_funds_rate=0.04,
            vix=16.0,
            cpi_yoy=2.5,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "transitional"


class TestContractionary:
    """Tests for contractionary regime classification."""

    def test_clear_contraction(self) -> None:
        """Inverted yield curve + high unemployment -> contractionary."""
        result = compute_macro_regime(
            yield_spread_10y2y=-0.01,  # inverted
            unemployment_rate=0.065,  # 6.5% > 5.0% threshold
            fed_funds_rate=0.055,
            vix=28.0,
            cpi_yoy=4.0,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "contractionary"
        assert 0.3 <= result.confidence <= 0.9

    def test_deep_inversion(self) -> None:
        """Deep inversion + very high unemployment -> high confidence contraction."""
        result = compute_macro_regime(
            yield_spread_10y2y=-0.02,  # deep inversion
            unemployment_rate=0.08,  # very high
            fed_funds_rate=0.055,
            vix=32.0,
            cpi_yoy=5.0,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "contractionary"
        assert result.confidence >= 0.6

    def test_contraction_boundary_unemployment(self) -> None:
        """Unemployment at exactly 5.0% -> NOT contractionary (must be > 0.05)."""
        result = compute_macro_regime(
            yield_spread_10y2y=-0.01,
            unemployment_rate=0.05,  # exactly at threshold, not above
            fed_funds_rate=0.05,
            vix=25.0,
            cpi_yoy=3.5,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "transitional"


class TestTransitional:
    """Tests for transitional (mixed signals) regime."""

    def test_inverted_but_low_unemployment(self) -> None:
        """Inverted curve but low unemployment -> transitional (mixed)."""
        result = compute_macro_regime(
            yield_spread_10y2y=-0.005,  # inverted
            unemployment_rate=0.038,  # low unemployment
            fed_funds_rate=0.04,
            vix=18.0,
            cpi_yoy=2.5,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "transitional"

    def test_positive_spread_high_unemployment(self) -> None:
        """Positive spread but high unemployment -> transitional (mixed)."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,  # positive
            unemployment_rate=0.06,  # high unemployment
            fed_funds_rate=0.04,
            vix=22.0,
            cpi_yoy=3.0,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "transitional"

    def test_flat_curve(self) -> None:
        """Flat yield curve (spread=0) -> transitional."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.0,  # flat, not > 0
            unemployment_rate=0.04,
            fed_funds_rate=0.04,
            vix=18.0,
            cpi_yoy=2.5,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "transitional"

    def test_missing_unemployment(self) -> None:
        """Missing unemployment -> transitional (cannot determine expansion/contraction)."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,
            unemployment_rate=None,
            fed_funds_rate=0.04,
            vix=16.0,
            cpi_yoy=2.5,
            completeness_ratio=0.625,  # 5/8 fields populated
        )
        assert result is not None
        assert result.regime == "transitional"

    def test_missing_yield_spread(self) -> None:
        """Missing yield spread -> transitional."""
        result = compute_macro_regime(
            yield_spread_10y2y=None,
            unemployment_rate=0.035,
            fed_funds_rate=0.04,
            vix=16.0,
            cpi_yoy=2.5,
            completeness_ratio=0.625,  # 5/8 fields populated
        )
        assert result is not None
        assert result.regime == "transitional"


class TestInsufficientData:
    """Tests for insufficient data (< 50% completeness)."""

    def test_all_none(self) -> None:
        """All fields None -> completeness 0.0 -> None."""
        result = compute_macro_regime(
            yield_spread_10y2y=None,
            unemployment_rate=None,
            fed_funds_rate=None,
            vix=None,
            cpi_yoy=None,
            completeness_ratio=0.0,
        )
        assert result is None

    def test_one_field(self) -> None:
        """Only 1/8 fields -> completeness 12.5% -> None."""
        result = compute_macro_regime(
            yield_spread_10y2y=None,
            unemployment_rate=None,
            fed_funds_rate=None,
            vix=None,
            cpi_yoy=None,
            completeness_ratio=0.125,
        )
        assert result is None

    def test_three_fields(self) -> None:
        """Only 3/8 fields -> completeness 37.5% -> None."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,
            unemployment_rate=None,
            fed_funds_rate=None,
            vix=None,
            cpi_yoy=None,
            completeness_ratio=0.375,
        )
        assert result is None

    def test_exactly_four_fields(self) -> None:
        """4/8 fields -> completeness 50% -> succeeds (>= 0.5 threshold)."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,
            unemployment_rate=0.035,
            fed_funds_rate=None,
            vix=None,
            cpi_yoy=None,
            completeness_ratio=0.5,
        )
        assert result is not None
        assert result.regime == "expansionary"


class TestEdgeCases:
    """Edge cases and NaN/Inf guards."""

    def test_nan_yield_spread_treated_as_missing(self) -> None:
        """NaN yield_spread treated as missing by isfinite() guard -> transitional."""
        result = compute_macro_regime(
            yield_spread_10y2y=float("nan"),
            unemployment_rate=0.035,
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.5,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        # NaN spread fails isfinite() -> treated as missing -> transitional
        assert result.regime == "transitional"

    def test_inf_unemployment_treated_as_missing(self) -> None:
        """Inf unemployment treated as missing by isfinite() guard -> transitional."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,
            unemployment_rate=float("inf"),
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.5,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert result.regime == "transitional"

    def test_confidence_bounds(self) -> None:
        """Confidence should always be in [0.0, 1.0]."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,
            unemployment_rate=0.035,
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.5,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert 0.0 <= result.confidence <= 1.0

    def test_result_is_namedtuple(self) -> None:
        """MacroClassification is a NamedTuple (regime, confidence)."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,
            unemployment_rate=0.035,
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.5,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] == result.regime
        assert result[1] == result.confidence

    def test_fallback_completeness_returns_none(self) -> None:
        """Zero completeness -> None."""
        result = compute_macro_regime(
            yield_spread_10y2y=None,
            unemployment_rate=None,
            fed_funds_rate=None,
            vix=None,
            cpi_yoy=None,
            completeness_ratio=0.0,
        )
        assert result is None

    def test_completeness_at_threshold(self) -> None:
        """Exactly 50% completeness -> should classify."""
        result = compute_macro_regime(
            yield_spread_10y2y=None,  # missing
            unemployment_rate=0.065,
            fed_funds_rate=0.04,
            vix=16.0,
            cpi_yoy=None,
            completeness_ratio=0.5,
        )
        assert result is not None
        # yield_spread is None, so cannot classify directionally
        assert result.regime == "transitional"

    def test_negative_unemployment_extreme(self) -> None:
        """Extremely negative unemployment (invalid real-world) is accepted as data."""
        result = compute_macro_regime(
            yield_spread_10y2y=0.01,
            unemployment_rate=-0.01,  # impossible but not NaN/Inf
            fed_funds_rate=0.04,
            vix=15.0,
            cpi_yoy=2.0,
            completeness_ratio=_full_completeness(),
        )
        assert result is not None
        # Negative unemployment < 0.045 threshold -> expansionary
        assert result.regime == "expansionary"

    def test_isfinite_guard_in_compute_confidence(self) -> None:
        """_compute_confidence returns 0.3 for non-finite inputs (belt-and-suspenders)."""
        # This is an indirect test — NaN/Inf are caught by the outer isfinite check
        # in compute_macro_regime, but _compute_confidence has its own guard.
        # With NaN yield spread, the function falls to transitional path.
        result = compute_macro_regime(
            yield_spread_10y2y=float("nan"),
            unemployment_rate=float("nan"),
            fed_funds_rate=None,
            vix=None,
            cpi_yoy=None,
            completeness_ratio=0.75,
        )
        assert result is not None
        assert result.regime == "transitional"
        assert result.confidence == pytest.approx(0.3, abs=0.01)
