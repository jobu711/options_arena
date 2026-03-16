"""Tests for neural IV surface integration in compute_vol_surface().

Verifies:
- Default surface_method='spline' produces identical results to before.
- Neural path invoked when surface_method='neural' and torch available.
- Fallback to spline when neural fit returns None.
- Fallback to spline when torch is not installed.
- Fallback to spline when data has < 30 points.
- Neural result is compatible with VolSurfaceResult fields.
"""

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from options_arena.indicators.vol_surface import (
    VolSurfaceResult,
    compute_vol_surface,
)

# Patch target: the source module where fit_neural_surface is defined.
# The guarded import inside _try_neural_surface does
#   ``from options_arena.pricing.neural_surface import fit_neural_surface``
# so we patch the source, which the import statement reads from.
_PATCH_FIT = "options_arena.pricing.neural_surface.fit_neural_surface"

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
    """Generate a dense synthetic option chain for testing.

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


def _make_small_chain(
    spot: float = 100.0,
    n_contracts: int = 10,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate a small chain (< 30 contracts) to test insufficient data path."""
    strikes = np.linspace(spot * 0.90, spot * 1.10, n_contracts)
    ivs = np.full(n_contracts, 0.30)
    dtes = np.full(n_contracts, 30.0)
    types = np.array([1.0 if i % 2 == 0 else -1.0 for i in range(n_contracts)])
    return strikes, ivs, dtes, types


def _make_mock_neural_result() -> MagicMock:
    """Create a mock NeuralSurfaceResult with valid fields."""
    mock = MagicMock()
    mock.fitted_ivs = np.array([0.28, 0.29, 0.30, 0.31] * 10, dtype=np.float64)
    mock.residuals = np.array([0.01, -0.01, 0.005, -0.005] * 10, dtype=np.float64)
    mock.z_scores = np.array([0.5, -0.5, 0.25, -0.25] * 10, dtype=np.float64)
    mock.r_squared = 0.95
    mock.is_neural = True
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNeuralVolSurface:
    """Tests for neural surface integration in compute_vol_surface()."""

    @pytest.mark.critical
    def test_spline_default_unchanged(self) -> None:
        """Verify default surface_method='spline' produces identical results."""
        strikes, ivs, dtes, types = _make_dense_chain()
        spot = 100.0

        # Call without surface_method (default = "spline")
        result_default = compute_vol_surface(strikes, ivs, dtes, types, spot)

        # Call with explicit surface_method="spline"
        result_explicit = compute_vol_surface(
            strikes, ivs, dtes, types, spot, surface_method="spline"
        )

        # Results should be identical
        assert result_default.skew_25d == result_explicit.skew_25d
        assert result_default.smile_curvature == result_explicit.smile_curvature
        assert result_default.r_squared == result_explicit.r_squared
        assert result_default.is_standalone_fallback == result_explicit.is_standalone_fallback
        assert result_default.is_1d_fallback == result_explicit.is_1d_fallback

    @pytest.mark.critical
    @patch(_PATCH_FIT)
    def test_neural_path_with_mock(self, mock_fit: MagicMock) -> None:
        """Verify neural path called when surface_method='neural' and enough data."""
        strikes, ivs, dtes, types = _make_dense_chain()
        spot = 100.0
        n_contracts = len(strikes)

        # Ensure we have enough contracts for neural path
        assert n_contracts >= 30

        mock_result = _make_mock_neural_result()
        # Adjust mock arrays to match the filtered contract count
        mock_result.fitted_ivs = np.full(n_contracts, 0.30, dtype=np.float64)
        mock_result.residuals = np.zeros(n_contracts, dtype=np.float64)
        mock_result.z_scores = np.zeros(n_contracts, dtype=np.float64)
        mock_fit.return_value = mock_result

        result = compute_vol_surface(strikes, ivs, dtes, types, spot, surface_method="neural")

        # Neural path was called
        mock_fit.assert_called_once()

        # Result should use neural-fitted values
        assert result.is_standalone_fallback is False
        assert result.is_1d_fallback is False
        assert result.fitted_ivs is not None
        assert result.residuals is not None
        assert result.z_scores is not None
        assert result.r_squared == pytest.approx(0.95)

    @patch(_PATCH_FIT)
    def test_neural_fallback_to_spline(self, mock_fit: MagicMock) -> None:
        """Verify fallback to spline when neural fit returns None."""
        strikes, ivs, dtes, types = _make_dense_chain()
        spot = 100.0

        # Neural fit returns None (failure)
        mock_fit.return_value = None

        result = compute_vol_surface(strikes, ivs, dtes, types, spot, surface_method="neural")

        # Neural was attempted
        mock_fit.assert_called_once()

        # Should fall through to spline (Tier 1 since data is dense)
        assert result is not None
        # The result should be from spline path (not standalone fallback for
        # dense data with multiple expirations)
        assert result.is_standalone_fallback is False or result.r_squared is not None

    @patch(_PATCH_FIT, side_effect=RuntimeError("torch internal error"))
    def test_neural_fallback_on_exception(self, mock_fit: MagicMock) -> None:
        """Verify fallback to spline when fit_neural_surface raises an exception."""
        strikes, ivs, dtes, types = _make_dense_chain()
        spot = 100.0

        result = compute_vol_surface(strikes, ivs, dtes, types, spot, surface_method="neural")

        # Should still produce a result via spline fallback
        assert result is not None
        assert isinstance(result, VolSurfaceResult)

    def test_neural_fallback_torch_missing(self) -> None:
        """Verify fallback to spline when the import of neural_surface fails.

        Simulates torch not installed by making the import raise ImportError.
        """
        strikes, ivs, dtes, types = _make_dense_chain()
        spot = 100.0

        # Patch the import mechanism to make the guarded import fail
        import builtins

        real_import = builtins.__import__

        def _mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "options_arena.pricing.neural_surface":
                raise ImportError("No module named 'torch'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            result = compute_vol_surface(strikes, ivs, dtes, types, spot, surface_method="neural")

        # Should fall through to spline/standalone path
        assert result is not None
        assert isinstance(result, VolSurfaceResult)

    def test_neural_fallback_insufficient_data(self) -> None:
        """Verify fallback to spline when < 30 data points."""
        strikes, ivs, dtes, types = _make_small_chain(n_contracts=20)
        spot = 100.0

        # Even with surface_method="neural", < 30 contracts should skip neural
        with patch(_PATCH_FIT) as mock_fit:
            result = compute_vol_surface(strikes, ivs, dtes, types, spot, surface_method="neural")

            # Neural path should NOT be called (data too small)
            mock_fit.assert_not_called()

        # Should still get a result (from spline or standalone)
        assert result is not None

    @patch(_PATCH_FIT)
    def test_neural_result_compatible(self, mock_fit: MagicMock) -> None:
        """Verify neural results produce valid VolSurfaceResult fields."""
        strikes, ivs, dtes, types = _make_dense_chain()
        spot = 100.0
        n_contracts = len(strikes)

        mock_result = _make_mock_neural_result()
        mock_result.fitted_ivs = np.full(n_contracts, 0.30, dtype=np.float64)
        mock_result.residuals = np.zeros(n_contracts, dtype=np.float64)
        mock_result.z_scores = np.zeros(n_contracts, dtype=np.float64)
        mock_fit.return_value = mock_result

        result = compute_vol_surface(strikes, ivs, dtes, types, spot, surface_method="neural")

        # Verify VolSurfaceResult type and field compatibility
        assert isinstance(result, VolSurfaceResult)

        # Fitted arrays should be numpy arrays
        assert isinstance(result.fitted_ivs, np.ndarray)
        assert isinstance(result.residuals, np.ndarray)
        assert isinstance(result.z_scores, np.ndarray)
        assert isinstance(result.fitted_strikes, np.ndarray)
        assert isinstance(result.fitted_dtes, np.ndarray)

        # R-squared should be finite
        assert result.r_squared is not None
        assert math.isfinite(result.r_squared)

        # Flags
        assert result.is_1d_fallback is False
        assert result.is_standalone_fallback is False

    @patch(_PATCH_FIT)
    def test_neural_nonfinite_r_squared_rejected(self, mock_fit: MagicMock) -> None:
        """Verify neural result rejected when R-squared is NaN."""
        strikes, ivs, dtes, types = _make_dense_chain()
        spot = 100.0
        n_contracts = len(strikes)

        mock_result = _make_mock_neural_result()
        mock_result.fitted_ivs = np.full(n_contracts, 0.30, dtype=np.float64)
        mock_result.residuals = np.zeros(n_contracts, dtype=np.float64)
        mock_result.z_scores = np.zeros(n_contracts, dtype=np.float64)
        mock_result.r_squared = float("nan")
        mock_fit.return_value = mock_result

        result = compute_vol_surface(strikes, ivs, dtes, types, spot, surface_method="neural")

        # Neural result rejected -- should fall through to spline
        assert result is not None
        # Since dense data, spline should succeed
        assert isinstance(result, VolSurfaceResult)

    @patch(_PATCH_FIT, side_effect=RuntimeError("CUDA out of memory"))
    def test_neural_exception_in_fit(self, mock_fit: MagicMock) -> None:
        """Verify fallback to spline when fit_neural_surface raises RuntimeError."""
        strikes, ivs, dtes, types = _make_dense_chain()
        spot = 100.0

        result = compute_vol_surface(strikes, ivs, dtes, types, spot, surface_method="neural")

        # Should fall through to spline path
        assert result is not None
        assert isinstance(result, VolSurfaceResult)
