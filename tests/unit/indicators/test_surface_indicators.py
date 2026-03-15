"""Tests for VolSurfaceIndicators and compute_surface_indicators.

~10 tests covering:
- Default (all-None) construction
- Populated construction
- Matching contract returns correct z-score
- Standalone fallback returns all None
- No z-scores returns residual None, R² still populated
- No matching key returns residual None, R² populated
- R² always populated when fitted surface exists
- is_1d passthrough
- Multiple contracts get different z-scores
- R² passthrough parametrized
"""

import numpy as np
import pytest

from options_arena.indicators.vol_surface import (
    VolSurfaceIndicators,
    VolSurfaceResult,
    compute_surface_indicators,
)

# ---------------------------------------------------------------------------
# Helpers: build synthetic VolSurfaceResult
# ---------------------------------------------------------------------------


def _make_fitted_result(
    *,
    z_scores: np.ndarray | None = None,
    r_squared: float | None = 0.92,
    fitted_strikes: np.ndarray | None = None,
    fitted_dtes: np.ndarray | None = None,
    is_1d_fallback: bool = False,
    is_standalone_fallback: bool = False,
) -> VolSurfaceResult:
    """Build a synthetic VolSurfaceResult for testing."""
    n = len(z_scores) if z_scores is not None else 0
    fitted_ivs = np.full(n, 0.30) if z_scores is not None else None
    residuals = z_scores * 0.01 if z_scores is not None else None
    return VolSurfaceResult(
        skew_25d=0.05,
        smile_curvature=1.2,
        prob_above_current=0.55,
        atm_iv_30d=0.30,
        atm_iv_60d=0.28,
        fitted_ivs=fitted_ivs,
        residuals=residuals,
        z_scores=z_scores,
        r_squared=r_squared,
        fitted_strikes=fitted_strikes,
        fitted_dtes=fitted_dtes,
        is_1d_fallback=is_1d_fallback,
        is_standalone_fallback=is_standalone_fallback,
    )


_NONE_RESULT = VolSurfaceResult(
    skew_25d=None,
    smile_curvature=None,
    prob_above_current=None,
    atm_iv_30d=None,
    atm_iv_60d=None,
    fitted_ivs=None,
    residuals=None,
    z_scores=None,
    r_squared=None,
    fitted_strikes=None,
    fitted_dtes=None,
    is_1d_fallback=False,
    is_standalone_fallback=False,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestVolSurfaceIndicatorsConstruction:
    """Tests for VolSurfaceIndicators NamedTuple construction."""

    def test_default_construction(self) -> None:
        """All-None construction yields a tuple with all fields None."""
        indicators = VolSurfaceIndicators()
        assert indicators.iv_surface_residual is None
        assert indicators.surface_fit_r2 is None
        assert indicators.surface_is_1d is None

    def test_populated_construction(self) -> None:
        """Full construction populates all fields correctly."""
        indicators = VolSurfaceIndicators(
            iv_surface_residual=1.5,
            surface_fit_r2=0.95,
            surface_is_1d=False,
        )
        assert indicators.iv_surface_residual == pytest.approx(1.5)
        assert indicators.surface_fit_r2 == pytest.approx(0.95)
        assert indicators.surface_is_1d is False


class TestComputeSurfaceIndicators:
    """Tests for compute_surface_indicators function."""

    def test_matching_contract_returns_zscore(self) -> None:
        """Contract at known (strike, dte) returns the correct z-score."""
        strikes = np.array([90.0, 95.0, 100.0, 105.0, 110.0])
        dtes = np.array([30.0, 30.0, 30.0, 30.0, 30.0])
        z_scores = np.array([-1.2, -0.5, 0.0, 0.8, 1.5])

        result_vol = _make_fitted_result(
            z_scores=z_scores,
            r_squared=0.90,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
        )

        indicators = compute_surface_indicators(
            result_vol,
            contract_strike=100.0,
            contract_dte=30.0,
        )

        assert indicators.iv_surface_residual is not None
        assert indicators.iv_surface_residual == pytest.approx(0.0)
        assert indicators.surface_fit_r2 == pytest.approx(0.90)
        assert indicators.surface_is_1d is False

    def test_standalone_fallback_returns_none(self) -> None:
        """is_standalone_fallback=True returns all-None indicators."""
        strikes = np.array([90.0, 100.0, 110.0])
        dtes = np.array([30.0, 30.0, 30.0])

        result_vol = _make_fitted_result(
            z_scores=np.array([0.1, 0.2, 0.3]),
            fitted_strikes=strikes,
            fitted_dtes=dtes,
            is_standalone_fallback=True,
        )

        indicators = compute_surface_indicators(
            result_vol,
            contract_strike=100.0,
            contract_dte=30.0,
        )

        assert indicators.iv_surface_residual is None
        assert indicators.surface_fit_r2 is None
        assert indicators.surface_is_1d is None

    def test_no_zscores_returns_none(self) -> None:
        """z_scores=None returns residual None; R² is NOT populated (all-None path)."""
        result_vol = _make_fitted_result(z_scores=None, r_squared=0.85)

        indicators = compute_surface_indicators(
            result_vol,
            contract_strike=100.0,
            contract_dte=30.0,
        )

        # z_scores is None → early return with all-None VolSurfaceIndicators
        assert indicators.iv_surface_residual is None
        assert indicators.surface_fit_r2 is None
        assert indicators.surface_is_1d is None

    def test_no_matching_key_returns_none_residual(self) -> None:
        """Contract not in arrays returns residual None, but R² is populated."""
        strikes = np.array([90.0, 95.0, 100.0])
        dtes = np.array([30.0, 30.0, 30.0])
        z_scores = np.array([-0.5, 0.0, 0.5])

        result_vol = _make_fitted_result(
            z_scores=z_scores,
            r_squared=0.88,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
        )

        indicators = compute_surface_indicators(
            result_vol,
            contract_strike=150.0,  # not in strikes array
            contract_dte=30.0,
        )

        assert indicators.iv_surface_residual is None
        assert indicators.surface_fit_r2 == pytest.approx(0.88)
        assert indicators.surface_is_1d is False

    def test_r2_always_populated(self) -> None:
        """R² populated even when residual is None (no matching contract)."""
        strikes = np.array([90.0, 100.0])
        dtes = np.array([30.0, 30.0])
        z_scores = np.array([0.1, 0.2])

        result_vol = _make_fitted_result(
            z_scores=z_scores,
            r_squared=0.75,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
        )

        # Query a DTE that doesn't match
        indicators = compute_surface_indicators(
            result_vol,
            contract_strike=100.0,
            contract_dte=60.0,  # no 60-day in array
        )

        assert indicators.iv_surface_residual is None
        assert indicators.surface_fit_r2 == pytest.approx(0.75)

    def test_is_1d_populated(self) -> None:
        """is_1d_fallback value from the result is passed through."""
        strikes = np.array([90.0, 100.0, 110.0])
        dtes = np.array([30.0, 30.0, 30.0])
        z_scores = np.array([0.1, 0.2, 0.3])

        result_vol = _make_fitted_result(
            z_scores=z_scores,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
            is_1d_fallback=True,
        )

        indicators = compute_surface_indicators(
            result_vol,
            contract_strike=100.0,
            contract_dte=30.0,
        )

        assert indicators.surface_is_1d is True

    def test_multiple_contracts_different_zscores(self) -> None:
        """Different contracts get different z-scores from the same surface."""
        strikes = np.array([90.0, 95.0, 100.0, 105.0, 110.0])
        dtes = np.array([30.0, 30.0, 30.0, 30.0, 30.0])
        z_scores = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])

        result_vol = _make_fitted_result(
            z_scores=z_scores,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
        )

        # Query strike=90
        ind_90 = compute_surface_indicators(
            result_vol,
            contract_strike=90.0,
            contract_dte=30.0,
        )
        # Query strike=110
        ind_110 = compute_surface_indicators(
            result_vol,
            contract_strike=110.0,
            contract_dte=30.0,
        )

        assert ind_90.iv_surface_residual is not None
        assert ind_110.iv_surface_residual is not None
        assert ind_90.iv_surface_residual == pytest.approx(-2.0)
        assert ind_110.iv_surface_residual == pytest.approx(2.0)
        assert ind_90.iv_surface_residual != ind_110.iv_surface_residual

    @pytest.mark.parametrize(
        "r2_value",
        [0.0, 0.25, 0.5, 0.75, 0.99, 1.0],
    )
    def test_r2_passthrough(self, r2_value: float) -> None:
        """R² from VolSurfaceResult is passed through unchanged."""
        strikes = np.array([100.0])
        dtes = np.array([30.0])
        z_scores = np.array([0.5])

        result_vol = _make_fitted_result(
            z_scores=z_scores,
            r_squared=r2_value,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
        )

        indicators = compute_surface_indicators(
            result_vol,
            contract_strike=100.0,
            contract_dte=30.0,
        )

        assert indicators.surface_fit_r2 == pytest.approx(r2_value)

    def test_nonfinite_zscore_returns_none_residual(self) -> None:
        """Non-finite z-score at the matched index returns None residual."""
        strikes = np.array([90.0, 100.0, 110.0])
        dtes = np.array([30.0, 30.0, 30.0])
        z_scores = np.array([0.5, float("nan"), 1.0])

        result_vol = _make_fitted_result(
            z_scores=z_scores,
            r_squared=0.80,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
        )

        indicators = compute_surface_indicators(
            result_vol,
            contract_strike=100.0,
            contract_dte=30.0,
        )

        # z_scores[1] is NaN, so residual should be None
        assert indicators.iv_surface_residual is None
        assert indicators.surface_fit_r2 == pytest.approx(0.80)

    def test_isclose_tolerances_match(self) -> None:
        """np.isclose default tolerance matches contracts with tiny float diffs."""
        strikes = np.array([100.00000001])
        dtes = np.array([30.0000001])
        z_scores = np.array([1.23])

        result_vol = _make_fitted_result(
            z_scores=z_scores,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
        )

        indicators = compute_surface_indicators(
            result_vol,
            contract_strike=100.0,
            contract_dte=30.0,
        )

        assert indicators.iv_surface_residual is not None
        assert indicators.iv_surface_residual == pytest.approx(1.23)
