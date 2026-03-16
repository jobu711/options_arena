"""Unit tests for neural IV surface model (pricing/neural_surface.py).

Tests cover:
- IVSurfaceNet: forward shape, Softplus positivity, training_step loss
- fit_neural_surface: synthetic data fit, insufficient data, missing deps,
  checkpoint save/load, NaN rejection, finite residuals
- predict_iv: positive prediction, missing checkpoint
- MLConfig neural fields: defaults, validation, surface_method consistency

Uses ``pytest.importorskip("torch")`` for tests requiring torch/lightning.
Uses ``unittest.mock.patch`` to test missing-dependency code paths.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from options_arena.models.config import MLConfig
from options_arena.pricing.neural_surface import (
    _MIN_SAMPLES,
    NeuralSurfaceResult,
    _build_iv_surface_net,
    _get_lightning,
    _get_torch,
    fit_neural_surface,
    predict_iv,
)

# ---------------------------------------------------------------------------
# Helper: synthetic IV surface data
# ---------------------------------------------------------------------------


def _make_synthetic_data(
    n: int = 100,
    spot: float = 100.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Generate synthetic IV surface data.

    IV = 0.2 + 0.1 * |log_moneyness| + 0.05 * sqrt(dte/365)
    """
    rng = np.random.default_rng(42)
    strikes = spot * np.exp(rng.uniform(-0.3, 0.3, n))
    dtes = rng.uniform(7, 90, n)
    log_m = np.log(strikes / spot)
    sqrt_t = np.sqrt(dtes / 365.0)
    ivs = 0.2 + 0.1 * np.abs(log_m) + 0.05 * sqrt_t
    # Add small noise
    ivs += rng.normal(0, 0.005, n)
    ivs = np.clip(ivs, 0.01, None)
    return strikes, ivs, dtes, spot


# ---------------------------------------------------------------------------
# TestIVSurfaceNet — model architecture tests
# ---------------------------------------------------------------------------


class TestIVSurfaceNet:
    """Tests for the IVSurfaceNet LightningModule architecture."""

    def test_forward_shape(self) -> None:
        """Forward pass produces (batch, 1) output from (batch, 2) input."""
        torch = pytest.importorskip("torch")
        pytest.importorskip("lightning")

        model = _build_iv_surface_net(lr=0.001)
        assert model is not None

        batch_size = 16
        x = torch.randn(batch_size, 2)
        model.eval()
        with torch.no_grad():
            out = model(x)

        assert out.shape == (batch_size, 1)

    def test_softplus_output_positive(self) -> None:
        """Softplus activation guarantees all outputs are strictly positive."""
        torch = pytest.importorskip("torch")
        pytest.importorskip("lightning")

        model = _build_iv_surface_net(lr=0.001)
        assert model is not None

        # Use a range of inputs including extreme negative values
        x = torch.tensor(
            [
                [-5.0, 0.01],
                [0.0, 0.5],
                [5.0, 1.0],
                [-3.0, 0.001],
            ]
        )
        model.eval()
        with torch.no_grad():
            out = model(x)

        assert (out > 0.0).all(), f"Softplus should produce positive outputs, got {out}"

    def test_training_step_returns_loss(self) -> None:
        """training_step returns a scalar loss tensor."""
        torch = pytest.importorskip("torch")
        pytest.importorskip("lightning")

        model = _build_iv_surface_net(lr=0.001)
        assert model is not None

        # Simulate a training batch
        x = torch.randn(8, 2)
        y = torch.rand(8, 1) * 0.5 + 0.1  # positive IV targets
        batch = (x, y)

        # training_step should return a loss (scalar tensor)
        loss = model.training_step(batch, batch_idx=0)
        assert loss is not None
        assert loss.ndim == 0, "Loss should be a scalar tensor"
        assert loss.item() > 0.0, "MSE loss should be positive"


# ---------------------------------------------------------------------------
# TestFitNeuralSurface — fitting pipeline tests
# ---------------------------------------------------------------------------


class TestFitNeuralSurface:
    """Tests for the fit_neural_surface public function."""

    def test_fit_on_synthetic_data(self) -> None:
        """Fit on synthetic data produces a valid NeuralSurfaceResult."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        strikes, ivs, dtes, spot = _make_synthetic_data(n=100)
        config = MLConfig(
            enable_neural_surface=True,
            surface_method="neural",
            neural_surface_epochs=200,
            neural_surface_lr=0.01,
        )

        result = fit_neural_surface(strikes, ivs, dtes, spot, config=config)

        assert result is not None
        assert isinstance(result, NeuralSurfaceResult)
        assert result.is_neural is True
        assert len(result.fitted_ivs) == len(
            ivs[
                np.isfinite(strikes)
                & np.isfinite(ivs)
                & np.isfinite(dtes)
                & (strikes > 0)
                & (ivs > 0)
                & (dtes > 0)
            ]
        )
        assert len(result.residuals) == len(result.fitted_ivs)
        assert len(result.z_scores) == len(result.fitted_ivs)
        assert math.isfinite(result.r_squared)
        # Fitted values should be positive (Softplus output)
        assert np.all(result.fitted_ivs > 0.0)

    def test_returns_none_insufficient_data(self) -> None:
        """Returns None when fewer than _MIN_SAMPLES valid data points."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        strikes = np.array([100.0, 105.0, 110.0])
        ivs = np.array([0.20, 0.22, 0.25])
        dtes = np.array([30.0, 30.0, 30.0])
        spot = 100.0

        assert len(strikes) < _MIN_SAMPLES
        result = fit_neural_surface(strikes, ivs, dtes, spot)
        assert result is None

    def test_returns_none_torch_unavailable(self) -> None:
        """Returns None when torch is not installed."""
        strikes, ivs, dtes, spot = _make_synthetic_data(n=20)

        with patch("options_arena.pricing.neural_surface._get_torch", return_value=None):
            result = fit_neural_surface(strikes, ivs, dtes, spot)

        assert result is None

    def test_returns_none_lightning_unavailable(self) -> None:
        """Returns None when lightning is not installed."""
        strikes, ivs, dtes, spot = _make_synthetic_data(n=20)

        with patch("options_arena.pricing.neural_surface._get_lightning", return_value=None):
            result = fit_neural_surface(strikes, ivs, dtes, spot)

        assert result is None

    def test_checkpoint_save_load(self, tmp_path: Path) -> None:
        """Checkpoints are saved and can be loaded for prediction."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        strikes, ivs, dtes, spot = _make_synthetic_data(n=50)
        cache_dir = str(tmp_path / "model_cache")

        config = MLConfig(
            enable_neural_surface=True,
            surface_method="neural",
            neural_surface_epochs=10,
            neural_surface_lr=0.005,
            model_cache_dir=cache_dir,
        )

        result = fit_neural_surface(strikes, ivs, dtes, spot, config=config)
        assert result is not None

        checkpoint_path = os.path.join(cache_dir, "neural_surface.ckpt")
        assert os.path.isfile(checkpoint_path)

        # Use the checkpoint for prediction
        pred = predict_iv(0.0, 30.0 / 365.0, checkpoint_path)
        assert pred is not None
        assert pred > 0.0
        assert math.isfinite(pred)

    def test_nan_input_rejected(self) -> None:
        """NaN values in input arrays are filtered out; returns None if too few remain."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        # All NaN — should return None (no valid data)
        n = 20
        strikes = np.full(n, np.nan)
        ivs = np.full(n, np.nan)
        dtes = np.full(n, np.nan)

        result = fit_neural_surface(strikes, ivs, dtes, spot=100.0)
        assert result is None

    def test_nan_spot_rejected(self) -> None:
        """Returns None when spot is NaN."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        strikes, ivs, dtes, _ = _make_synthetic_data(n=20)
        result = fit_neural_surface(strikes, ivs, dtes, spot=float("nan"))
        assert result is None

    def test_residuals_finite(self) -> None:
        """All residuals and z-scores are finite after fitting."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        strikes, ivs, dtes, spot = _make_synthetic_data(n=50)
        config = MLConfig(
            enable_neural_surface=True,
            neural_surface_epochs=15,
            neural_surface_lr=0.005,
        )

        result = fit_neural_surface(strikes, ivs, dtes, spot, config=config)
        assert result is not None
        assert np.all(np.isfinite(result.residuals))
        assert np.all(np.isfinite(result.z_scores))
        assert np.all(np.isfinite(result.fitted_ivs))


# ---------------------------------------------------------------------------
# TestPredictIV — inference tests
# ---------------------------------------------------------------------------


class TestPredictIV:
    """Tests for the predict_iv public function."""

    def test_predict_returns_positive_float(self, tmp_path: Path) -> None:
        """predict_iv returns a positive finite float from a valid checkpoint."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        strikes, ivs, dtes, spot = _make_synthetic_data(n=50)
        cache_dir = str(tmp_path / "model_cache")

        config = MLConfig(
            enable_neural_surface=True,
            surface_method="neural",
            neural_surface_epochs=10,
            neural_surface_lr=0.005,
            model_cache_dir=cache_dir,
        )

        result = fit_neural_surface(strikes, ivs, dtes, spot, config=config)
        assert result is not None

        checkpoint_path = os.path.join(cache_dir, "neural_surface.ckpt")
        pred = predict_iv(0.0, 30.0 / 365.0, checkpoint_path)
        assert pred is not None
        assert isinstance(pred, float)
        assert pred > 0.0
        assert math.isfinite(pred)

    def test_predict_missing_checkpoint(self, tmp_path: Path) -> None:
        """Returns None when checkpoint file does not exist."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        fake_path = str(tmp_path / "nonexistent.ckpt")
        result = predict_iv(0.0, 0.1, fake_path)
        assert result is None

    def test_predict_nan_input(self, tmp_path: Path) -> None:
        """Returns None when inputs are NaN."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        # Even with a valid checkpoint path, NaN inputs should return None
        result = predict_iv(float("nan"), 0.1, str(tmp_path / "fake.ckpt"))
        assert result is None

        result = predict_iv(0.0, float("nan"), str(tmp_path / "fake.ckpt"))
        assert result is None

    def test_predict_torch_unavailable(self, tmp_path: Path) -> None:
        """Returns None when torch is not installed."""
        with patch("options_arena.pricing.neural_surface._get_torch", return_value=None):
            result = predict_iv(0.0, 0.1, str(tmp_path / "fake.ckpt"))
        assert result is None


# ---------------------------------------------------------------------------
# TestNeuralConfig — MLConfig neural field validation
# ---------------------------------------------------------------------------


class TestNeuralConfig:
    """Tests for MLConfig neural surface configuration fields."""

    def test_default_config(self) -> None:
        """Default MLConfig has neural features disabled."""
        config = MLConfig()
        assert config.enable_neural_surface is False
        assert config.surface_method == "spline"
        assert config.model_cache_dir == "data/model_cache"
        assert config.neural_surface_epochs == 100
        assert config.neural_surface_lr == pytest.approx(0.001)

    def test_surface_method_validation(self) -> None:
        """surface_method only accepts 'spline' or 'neural'."""
        # Valid values
        config_spline = MLConfig(surface_method="spline")
        assert config_spline.surface_method == "spline"

        config_neural = MLConfig(surface_method="neural")
        assert config_neural.surface_method == "neural"
        # Auto-enables neural surface when method is neural
        assert config_neural.enable_neural_surface is True

        # Invalid value
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MLConfig(surface_method="invalid")  # type: ignore[arg-type]

    def test_epochs_range_validation(self) -> None:
        """neural_surface_epochs must be in [10, 500]."""
        from pydantic import ValidationError

        # Valid bounds
        config_min = MLConfig(neural_surface_epochs=10)
        assert config_min.neural_surface_epochs == 10

        config_max = MLConfig(neural_surface_epochs=500)
        assert config_max.neural_surface_epochs == 500

        # Below minimum
        with pytest.raises(ValidationError):
            MLConfig(neural_surface_epochs=9)

        # Above maximum
        with pytest.raises(ValidationError):
            MLConfig(neural_surface_epochs=501)

    def test_lr_positive_finite(self) -> None:
        """neural_surface_lr must be finite and positive."""
        from pydantic import ValidationError

        # Valid
        config = MLConfig(neural_surface_lr=0.01)
        assert config.neural_surface_lr == pytest.approx(0.01)

        # Zero
        with pytest.raises(ValidationError):
            MLConfig(neural_surface_lr=0.0)

        # Negative
        with pytest.raises(ValidationError):
            MLConfig(neural_surface_lr=-0.001)

        # NaN
        with pytest.raises(ValidationError):
            MLConfig(neural_surface_lr=float("nan"))

        # Inf
        with pytest.raises(ValidationError):
            MLConfig(neural_surface_lr=float("inf"))

    def test_surface_method_auto_enables_neural(self) -> None:
        """Setting surface_method='neural' auto-enables enable_neural_surface."""
        config = MLConfig(surface_method="neural", enable_neural_surface=False)
        # The model_validator should auto-enable it
        assert config.enable_neural_surface is True


# ---------------------------------------------------------------------------
# TestGuardedImports — import guard tests
# ---------------------------------------------------------------------------


class TestGuardedImports:
    """Tests for guarded import functions."""

    def test_get_torch_returns_none_when_missing(self) -> None:
        """_get_torch returns None when torch cannot be imported."""
        with (
            patch.dict("sys.modules", {"torch": None}),
            patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: (
                    (_ for _ in ()).throw(ImportError)
                    if name == "torch"
                    else __builtins__.__import__(name, *a, **kw)
                ),  # type: ignore[union-attr]
            ),
        ):
            result = _get_torch()
            assert result is None

    def test_get_lightning_returns_none_when_missing(self) -> None:
        """_get_lightning returns None when lightning cannot be imported."""
        with (
            patch.dict("sys.modules", {"lightning": None}),
            patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: (
                    (_ for _ in ()).throw(ImportError)
                    if name == "lightning"
                    else __builtins__.__import__(name, *a, **kw)
                ),  # type: ignore[union-attr]
            ),
        ):
            result = _get_lightning()
            assert result is None


# ---------------------------------------------------------------------------
# TestNeuralSurfaceResult — NamedTuple tests
# ---------------------------------------------------------------------------


class TestNeuralSurfaceResult:
    """Tests for the NeuralSurfaceResult NamedTuple."""

    def test_construction(self) -> None:
        """NeuralSurfaceResult can be constructed with valid data."""
        fitted = np.array([0.2, 0.25, 0.3])
        residuals = np.array([0.01, -0.01, 0.005])
        z_scores = np.array([0.5, -0.5, 0.25])

        result = NeuralSurfaceResult(
            fitted_ivs=fitted,
            residuals=residuals,
            z_scores=z_scores,
            r_squared=0.95,
            is_neural=True,
        )

        assert result.is_neural is True
        assert result.r_squared == pytest.approx(0.95)
        np.testing.assert_array_equal(result.fitted_ivs, fitted)
        np.testing.assert_array_equal(result.residuals, residuals)
        np.testing.assert_array_equal(result.z_scores, z_scores)
