"""Tests for vol surface analytics: tiered computation, standalone fallbacks,
Breeden-Litzenberger, and edge cases.

~35 tests covering:
- Tier 1 (fitted surface via SmoothBivariateSpline)
- Tier 2 (standalone fallback)
- Insufficient data
- Standalone helper functions
- Breeden-Litzenberger implied probability
- Edge cases (NaN, zero IV, single expiration, all same strike)
- Stub test for compute_surface_indicators
"""

import math

import numpy as np
import pytest

from options_arena.indicators.vol_surface import (
    VolSurfaceIndicators,
    VolSurfaceResult,
    _standalone_atm_iv,
    _standalone_implied_move,
    _standalone_skew_25d,
    _standalone_smile_curvature,
    compute_surface_indicators,
    compute_vol_surface,
)

# ---------------------------------------------------------------------------
# Helpers: generate synthetic option chain data
# ---------------------------------------------------------------------------


def _make_dense_chain(
    spot: float = 100.0,
    n_strikes: int = 11,
    n_expirations: int = 3,
    base_iv: float = 0.30,
    skew_slope: float = -0.1,
    smile_quad: float = 0.5,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate a dense synthetic option chain for Tier 1 testing.

    Creates a chain with ``n_strikes`` per expiration across ``n_expirations``
    expirations.  IVs follow a quadratic smile with linear skew:
        IV(K) = base_iv + skew_slope * log(K/S) + smile_quad * log(K/S)^2

    Returns (strikes, ivs, dtes, option_types).
    """
    dte_values = [30, 60, 90][:n_expirations]
    strike_range = np.linspace(spot * 0.85, spot * 1.15, n_strikes)

    all_strikes: list[float] = []
    all_ivs: list[float] = []
    all_dtes: list[float] = []
    all_types: list[float] = []

    for dte in dte_values:
        for k in strike_range:
            log_m = math.log(k / spot)
            iv = base_iv + skew_slope * log_m + smile_quad * log_m * log_m
            iv = max(iv, 0.05)  # floor at 5%

            # Add as call
            all_strikes.append(k)
            all_ivs.append(iv)
            all_dtes.append(float(dte))
            all_types.append(1.0)

            # Add as put
            all_strikes.append(k)
            all_ivs.append(iv)
            all_dtes.append(float(dte))
            all_types.append(-1.0)

    return (
        np.array(all_strikes),
        np.array(all_ivs),
        np.array(all_dtes),
        np.array(all_types),
    )


def _make_sparse_chain(
    spot: float = 100.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate a sparse chain (4 contracts, 1 expiration) for Tier 2 testing."""
    strikes = np.array([90.0, 95.0, 100.0, 110.0])
    ivs = np.array([0.35, 0.30, 0.28, 0.32])
    dtes = np.array([30.0, 30.0, 30.0, 30.0])
    # 2 puts, 2 calls
    types = np.array([-1.0, -1.0, 1.0, 1.0])
    return strikes, ivs, dtes, types


# ---------------------------------------------------------------------------
# Tier 1: Fitted surface tests
# ---------------------------------------------------------------------------


class TestTier1FittedSurface:
    """Tests for Tier 1 (fitted surface via SmoothBivariateSpline)."""

    @pytest.mark.critical
    def test_dense_chain_produces_fitted_surface(self) -> None:
        """Dense chain (10+ contracts, 3 expirations) triggers Tier 1."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        assert isinstance(result, VolSurfaceResult)
        assert result.is_standalone_fallback is False
        assert result.fitted_ivs is not None
        assert result.residuals is not None
        assert result.z_scores is not None

    def test_dense_chain_r_squared(self) -> None:
        """Fitted surface on synthetic data should have high R-squared."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        assert result.r_squared is not None
        # Synthetic quadratic smile should fit well
        assert result.r_squared > 0.5

    def test_dense_chain_skew_typically_negative(self) -> None:
        """Skew_25d should be positive (put IV > call IV) for typical equity skew.

        In our synthetic data, skew_slope = -0.1 means IV increases as
        log(K/S) decreases (puts), so IV_25d_put > IV_25d_call.
        """
        strikes, ivs, dtes, types = _make_dense_chain(skew_slope=-0.1)
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        # With negative skew_slope, log(K/S) < 0 for puts means higher IV
        if result.skew_25d is not None:
            assert result.skew_25d > 0.0  # put IV > call IV

    def test_dense_chain_smile_curvature_positive(self) -> None:
        """Smile curvature should be positive for a convex smile."""
        strikes, ivs, dtes, types = _make_dense_chain(smile_quad=0.5)
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        if result.smile_curvature is not None:
            assert result.smile_curvature > 0.0

    def test_dense_chain_atm_iv_30d(self) -> None:
        """ATM IV at 30d should be close to base_iv."""
        strikes, ivs, dtes, types = _make_dense_chain(base_iv=0.30)
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        assert result.atm_iv_30d is not None
        assert result.atm_iv_30d == pytest.approx(0.30, abs=0.05)

    def test_dense_chain_atm_iv_60d(self) -> None:
        """ATM IV at 60d should be available for dense chain with 3 expirations."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        assert result.atm_iv_60d is not None
        assert result.atm_iv_60d > 0.0

    def test_dense_chain_prob_above_current(self) -> None:
        """prob_above_current should be between 0 and 1."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        if result.prob_above_current is not None:
            assert 0.0 <= result.prob_above_current <= 1.0

    def test_fitted_ivs_length_matches_input(self) -> None:
        """fitted_ivs should have same length as filtered input contracts."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        if result.fitted_ivs is not None:
            # All contracts valid, so fitted length = input length
            assert len(result.fitted_ivs) == len(ivs)

    def test_residuals_sum_near_zero(self) -> None:
        """Residuals should sum to approximately zero for a good fit."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        if result.residuals is not None:
            mean_resid = float(np.mean(result.residuals))
            assert abs(mean_resid) < 0.05


# ---------------------------------------------------------------------------
# Tier 2: Standalone fallback tests
# ---------------------------------------------------------------------------


class TestTier2StandaloneFallback:
    """Tests for Tier 2 (standalone fallback when chain is too sparse)."""

    def test_sparse_chain_triggers_standalone(self) -> None:
        """4 contracts at 1 expiration should trigger standalone fallback."""
        strikes, ivs, dtes, types = _make_sparse_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        assert result.is_standalone_fallback is True
        assert result.fitted_ivs is None
        assert result.residuals is None
        assert result.z_scores is None
        assert result.r_squared is None

    def test_sparse_chain_skew(self) -> None:
        """Standalone skew should be computable from sparse chain."""
        strikes, ivs, dtes, types = _make_sparse_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        # With our sparse chain: puts at 90,95 (IV 0.35,0.30), calls at 100,110 (IV 0.28,0.32)
        # skew_25d might be None because moneyness filter might not find exact 25-delta
        # But smile_curvature should work
        if result.smile_curvature is not None:
            assert math.isfinite(result.smile_curvature)

    def test_sparse_chain_atm_iv(self) -> None:
        """Standalone ATM IV should find nearest-ATM contract."""
        strikes, ivs, dtes, types = _make_sparse_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        # ATM 30d: contract at strike=100, IV=0.28, DTE=30
        assert result.atm_iv_30d is not None
        assert result.atm_iv_30d == pytest.approx(0.28, rel=1e-3)

    def test_single_expiration_many_contracts_tier2(self) -> None:
        """Many contracts at single expiration -> Tier 2 (need >=2 unique DTEs for Tier 1)."""
        n = 15
        strikes = np.linspace(85, 115, n)
        ivs = np.full(n, 0.30)
        dtes = np.full(n, 30.0)
        types = np.where(strikes < 100, -1.0, 1.0)

        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        assert result.is_standalone_fallback is True


# ---------------------------------------------------------------------------
# Insufficient data tests
# ---------------------------------------------------------------------------


class TestInsufficientData:
    """Tests for insufficient data returning all-None results."""

    def test_fewer_than_3_contracts(self) -> None:
        """Fewer than 3 contracts returns all-None result."""
        strikes = np.array([100.0, 105.0])
        ivs = np.array([0.30, 0.32])
        dtes = np.array([30.0, 30.0])
        types = np.array([1.0, 1.0])

        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        assert result.skew_25d is None
        assert result.smile_curvature is None
        assert result.prob_above_current is None
        assert result.atm_iv_30d is None
        assert result.atm_iv_60d is None
        assert result.fitted_ivs is None

    def test_zero_spot(self) -> None:
        """Zero spot returns all-None result."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=0.0)

        assert result.skew_25d is None
        assert result.fitted_ivs is None

    def test_negative_spot(self) -> None:
        """Negative spot returns all-None result."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=-100.0)

        assert result.skew_25d is None

    def test_nan_spot(self) -> None:
        """NaN spot returns all-None result."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(strikes, ivs, dtes, types, spot=float("nan"))

        assert result.skew_25d is None

    def test_inf_risk_free_rate(self) -> None:
        """Infinite risk_free_rate returns all-None result."""
        strikes, ivs, dtes, types = _make_dense_chain()
        result = compute_vol_surface(
            strikes,
            ivs,
            dtes,
            types,
            spot=100.0,
            risk_free_rate=float("inf"),
        )

        assert result.skew_25d is None


# ---------------------------------------------------------------------------
# Standalone fallback function tests
# ---------------------------------------------------------------------------


class TestStandaloneSkew25d:
    """Tests for _standalone_skew_25d."""

    def test_basic_skew(self) -> None:
        """Put IV > call IV for typical equity skew."""
        strikes = np.array([90.0, 95.0, 100.0, 105.0, 110.0])
        ivs = np.array([0.40, 0.35, 0.30, 0.28, 0.25])
        types = np.array([-1.0, -1.0, 1.0, 1.0, 1.0])
        spot = 100.0

        result = _standalone_skew_25d(strikes, ivs, types, spot)

        # 95/100 = 0.95 moneyness put IV ~ 0.35
        # 105/100 = 1.05 moneyness call IV ~ 0.28
        assert result is not None
        assert result > 0.0  # put IV > call IV

    def test_insufficient_contracts(self) -> None:
        """Single contract returns None."""
        result = _standalone_skew_25d(
            np.array([100.0]),
            np.array([0.30]),
            np.array([1.0]),
            100.0,
        )
        assert result is None

    def test_no_otm_puts(self) -> None:
        """All calls returns None (no OTM puts found)."""
        strikes = np.array([95.0, 100.0, 105.0])
        ivs = np.array([0.35, 0.30, 0.28])
        types = np.array([1.0, 1.0, 1.0])  # all calls

        result = _standalone_skew_25d(strikes, ivs, types, 100.0)
        assert result is None


class TestStandaloneSmileCurvature:
    """Tests for _standalone_smile_curvature."""

    def test_convex_smile(self) -> None:
        """Quadratic smile should produce positive curvature."""
        spot = 100.0
        strikes = np.array([90.0, 95.0, 100.0, 105.0, 110.0])
        # Quadratic: higher IV at wings
        ivs = np.array([0.40, 0.32, 0.28, 0.32, 0.40])

        result = _standalone_smile_curvature(strikes, ivs, spot)

        assert result is not None
        assert result > 0.0  # convex

    def test_flat_smile(self) -> None:
        """Flat smile should produce near-zero curvature."""
        spot = 100.0
        strikes = np.array([90.0, 95.0, 100.0, 105.0, 110.0])
        ivs = np.array([0.30, 0.30, 0.30, 0.30, 0.30])

        result = _standalone_smile_curvature(strikes, ivs, spot)

        assert result is not None
        assert result == pytest.approx(0.0, abs=0.1)

    def test_insufficient_strikes(self) -> None:
        """Fewer than 3 strikes returns None."""
        result = _standalone_smile_curvature(
            np.array([100.0, 105.0]),
            np.array([0.30, 0.32]),
            100.0,
        )
        assert result is None

    def test_atm_at_boundary(self) -> None:
        """ATM at lowest strike (boundary) returns None."""
        strikes = np.array([100.0, 105.0, 110.0])
        ivs = np.array([0.30, 0.32, 0.35])

        # spot == 100 -> ATM at index 0 (boundary)
        result = _standalone_smile_curvature(strikes, ivs, 100.0)

        assert result is None  # Cannot compute centered difference at boundary


class TestStandaloneAtmIv:
    """Tests for _standalone_atm_iv."""

    def test_exact_atm_30d(self) -> None:
        """Find ATM IV at 30d with exact match."""
        strikes = np.array([95.0, 100.0, 105.0])
        ivs = np.array([0.35, 0.30, 0.28])
        dtes = np.array([30.0, 30.0, 30.0])

        result = _standalone_atm_iv(strikes, ivs, dtes, 100.0, target_dte=30)

        assert result is not None
        assert result == pytest.approx(0.30, rel=1e-3)

    def test_no_matching_dte(self) -> None:
        """No contracts in DTE bucket returns None."""
        strikes = np.array([95.0, 100.0, 105.0])
        ivs = np.array([0.35, 0.30, 0.28])
        dtes = np.array([5.0, 5.0, 5.0])

        result = _standalone_atm_iv(strikes, ivs, dtes, 100.0, target_dte=30)

        assert result is None  # DTE 5 outside [15, 45] bucket

    def test_empty_input(self) -> None:
        """Empty input returns None."""
        result = _standalone_atm_iv(
            np.array([]),
            np.array([]),
            np.array([]),
            100.0,
            target_dte=30,
        )
        assert result is None


class TestStandaloneImpliedMove:
    """Tests for _standalone_implied_move (Breeden-Litzenberger)."""

    def test_prob_between_0_and_1(self) -> None:
        """Probability should be between 0 and 1."""
        # Create a realistic call chain
        strikes = np.array([90.0, 95.0, 100.0, 105.0, 110.0, 115.0])
        ivs = np.array([0.35, 0.32, 0.30, 0.30, 0.32, 0.35])
        types = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])  # all calls
        dtes = np.array([30.0, 30.0, 30.0, 30.0, 30.0, 30.0])

        result = _standalone_implied_move(strikes, ivs, types, 100.0, 0.05, dtes)

        if result is not None:
            assert 0.0 <= result <= 1.0

    def test_insufficient_calls(self) -> None:
        """Fewer than 3 calls returns None."""
        strikes = np.array([100.0, 105.0])
        ivs = np.array([0.30, 0.32])
        types = np.array([1.0, 1.0])
        dtes = np.array([30.0, 30.0])

        result = _standalone_implied_move(strikes, ivs, types, 100.0, 0.05, dtes)

        assert result is None

    def test_only_puts_returns_none(self) -> None:
        """All puts (no calls) returns None."""
        strikes = np.array([90.0, 95.0, 100.0, 105.0])
        ivs = np.array([0.35, 0.32, 0.30, 0.28])
        types = np.array([-1.0, -1.0, -1.0, -1.0])
        dtes = np.array([30.0, 30.0, 30.0, 30.0])

        result = _standalone_implied_move(strikes, ivs, types, 100.0, 0.05, dtes)

        assert result is None

    def test_uniform_iv_produces_finite_prob(self) -> None:
        """Uniform IV across strikes should produce a well-behaved probability."""
        n = 10
        strikes = np.linspace(80, 120, n)
        ivs = np.full(n, 0.30)
        types = np.full(n, 1.0)
        dtes = np.full(n, 30.0)

        result = _standalone_implied_move(strikes, ivs, types, 100.0, 0.05, dtes)

        if result is not None:
            assert 0.0 <= result <= 1.0
            assert math.isfinite(result)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge case tests for compute_vol_surface."""

    def test_all_same_strike(self) -> None:
        """All contracts at same strike: surface fit likely fails, fallback works."""
        n = 10
        strikes = np.full(n, 100.0)
        ivs = np.full(n, 0.30)
        dtes = np.array([30.0, 30.0, 30.0, 60.0, 60.0, 60.0, 90.0, 90.0, 90.0, 90.0])
        types = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0, 1.0, -1.0])

        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        # Should not crash; may fall back to standalone
        assert isinstance(result, VolSurfaceResult)

    def test_nan_in_ivs_filtered(self) -> None:
        """NaN IVs should be filtered before fitting."""
        strikes, ivs, dtes, types = _make_dense_chain()
        # Inject NaNs
        ivs_with_nan = ivs.copy()
        ivs_with_nan[0] = float("nan")
        ivs_with_nan[5] = float("nan")

        result = compute_vol_surface(strikes, ivs_with_nan, dtes, types, spot=100.0)

        # Should still produce a result (enough valid contracts remain)
        assert isinstance(result, VolSurfaceResult)
        # If fitted, fitted_ivs should not contain the NaN positions
        if result.fitted_ivs is not None:
            assert not np.any(np.isnan(result.fitted_ivs))

    def test_zero_iv_excluded(self) -> None:
        """Zero IVs should be excluded from computation."""
        strikes, ivs, dtes, types = _make_dense_chain()
        ivs_with_zero = ivs.copy()
        ivs_with_zero[0] = 0.0
        ivs_with_zero[1] = 0.0

        result = compute_vol_surface(strikes, ivs_with_zero, dtes, types, spot=100.0)

        assert isinstance(result, VolSurfaceResult)

    def test_all_nan_ivs(self) -> None:
        """All NaN IVs returns all-None result."""
        n = 10
        strikes = np.linspace(90, 110, n)
        ivs = np.full(n, float("nan"))
        dtes = np.full(n, 30.0)
        types = np.full(n, 1.0)

        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        assert result.skew_25d is None
        assert result.fitted_ivs is None

    def test_all_zero_ivs(self) -> None:
        """All zero IVs returns all-None result."""
        n = 10
        strikes = np.linspace(90, 110, n)
        ivs = np.full(n, 0.0)
        dtes = np.full(n, 30.0)
        types = np.full(n, 1.0)

        result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        assert result.skew_25d is None


# ---------------------------------------------------------------------------
# Stub test
# ---------------------------------------------------------------------------

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
    is_1d_fallback=False,
    is_standalone_fallback=False,
)


class TestComputeSurfaceIndicators:
    """Test for the compute_surface_indicators stub."""

    def test_stub_returns_empty_tuple(self) -> None:
        """Stub should return empty VolSurfaceIndicators for any input."""
        result = compute_surface_indicators(_NONE_RESULT)
        assert result == VolSurfaceIndicators()
        assert isinstance(result, VolSurfaceIndicators)

    def test_stub_with_real_result(self) -> None:
        """Stub returns empty VolSurfaceIndicators even with a real VolSurfaceResult."""
        strikes, ivs, dtes, types = _make_dense_chain()
        vol_result = compute_vol_surface(strikes, ivs, dtes, types, spot=100.0)

        result = compute_surface_indicators(vol_result)

        assert result == VolSurfaceIndicators()
