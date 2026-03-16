"""Neural implied volatility surface model using PyTorch Lightning.

Maps (log_moneyness, dte_normalized) to implied volatility via an MLP.  Uses
guarded imports so the module returns ``None`` when ``torch`` or ``lightning``
are not installed (optional ``[neural]`` extra).

Architecture:
    Linear(2, 64) -> ReLU -> BN -> Linear(64, 64) -> ReLU -> BN ->
    Linear(64, 64) -> ReLU -> BN -> Linear(64, 1) -> Softplus

The Softplus output activation guarantees positive IV predictions.

Rules (pricing module):
- Scalar float in/out at public boundary.  No pandas.
- ``math.isfinite()`` guard on all numeric inputs and outputs.
- Return ``None`` on insufficient data, missing deps, or failure.
- Logging only, never ``print()``.
- Config via injection (``MLConfig``), never import ``AppSettings`` directly.

References:
- Gatheral (2006) "The Volatility Surface: A Practitioner's Guide"
- Goodfellow, Bengio, Courville (2016) "Deep Learning", Ch. 6 (MLPs)
"""

from __future__ import annotations

import logging
import math
import os
from typing import TYPE_CHECKING, Any, NamedTuple

import numpy as np

if TYPE_CHECKING:
    from options_arena.models.config import MLConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimum data requirements
# ---------------------------------------------------------------------------

_MIN_SAMPLES: int = 10

# ---------------------------------------------------------------------------
# Guarded imports
# ---------------------------------------------------------------------------


def _get_torch() -> Any:  # noqa: ANN401
    """Attempt to import ``torch``. Returns the module or ``None``."""
    try:
        import torch

        return torch
    except ImportError:
        logger.info("torch not installed -- neural surface features disabled")
        return None


def _get_lightning() -> Any:  # noqa: ANN401
    """Attempt to import ``lightning``. Returns the module or ``None``."""
    try:
        import lightning as L  # noqa: N812

        return L
    except ImportError:
        logger.info("lightning not installed -- neural surface features disabled")
        return None


# ---------------------------------------------------------------------------
# NeuralSurfaceResult
# ---------------------------------------------------------------------------


class NeuralSurfaceResult(NamedTuple):
    """Result of neural IV surface fitting.

    Fields:
        fitted_ivs: Predicted IV values for each input contract (numpy array).
        residuals: Observed IV minus fitted IV (numpy array).
        z_scores: Residuals divided by their standard deviation (numpy array).
        r_squared: Coefficient of determination of the fit.
        is_neural: Always ``True`` for this result type.
    """

    fitted_ivs: np.ndarray
    residuals: np.ndarray
    z_scores: np.ndarray
    r_squared: float
    is_neural: bool


# ---------------------------------------------------------------------------
# IVSurfaceNet — Lightning Module
# ---------------------------------------------------------------------------


def _build_iv_surface_net(
    lr: float = 0.001,
    weight_decay: float = 1e-5,
) -> Any:  # noqa: ANN401
    """Build and return an ``IVSurfaceNet`` LightningModule instance.

    Returns ``None`` if torch or lightning are unavailable.
    """
    torch = _get_torch()
    L = _get_lightning()  # noqa: N806
    if torch is None or L is None:
        return None

    class IVSurfaceNet(L.LightningModule):  # type: ignore[misc, name-defined]
        """MLP that maps (log_moneyness, dte_normalized) -> implied volatility.

        Architecture:
            Linear(2, 64) -> ReLU -> BN(64) ->
            Linear(64, 64) -> ReLU -> BN(64) ->
            Linear(64, 64) -> ReLU -> BN(64) ->
            Linear(64, 1) -> Softplus

        The Softplus activation on the output ensures positive IV predictions.
        """

        def __init__(self, lr: float = 0.001, weight_decay: float = 1e-5) -> None:
            super().__init__()
            self.save_hyperparameters()
            self.lr = lr
            self.weight_decay = weight_decay

            self.net = torch.nn.Sequential(
                torch.nn.Linear(2, 64),
                torch.nn.ReLU(),
                torch.nn.BatchNorm1d(64),
                torch.nn.Linear(64, 64),
                torch.nn.ReLU(),
                torch.nn.BatchNorm1d(64),
                torch.nn.Linear(64, 64),
                torch.nn.ReLU(),
                torch.nn.BatchNorm1d(64),
                torch.nn.Linear(64, 1),
                torch.nn.Softplus(),
            )

        def forward(self, x: Any) -> Any:  # noqa: ANN401
            """Forward pass: (batch, 2) -> (batch, 1)."""
            return self.net(x)

        def training_step(self, batch: Any, batch_idx: int) -> Any:  # noqa: ANN401
            """Compute MSE loss on a training batch."""
            x, y = batch
            y_hat = self(x)
            loss = torch.nn.functional.mse_loss(y_hat, y)
            self.log("train_loss", loss, prog_bar=True)
            return loss

        def configure_optimizers(self) -> Any:  # noqa: ANN401
            """Adam optimizer with weight decay."""
            return torch.optim.Adam(
                self.parameters(),
                lr=self.lr,
                weight_decay=self.weight_decay,
            )

    return IVSurfaceNet(lr=lr, weight_decay=weight_decay)


# ---------------------------------------------------------------------------
# Public API: fit_neural_surface
# ---------------------------------------------------------------------------


def fit_neural_surface(
    strikes: np.ndarray,
    ivs: np.ndarray,
    dtes: np.ndarray,
    spot: float,
    config: MLConfig | None = None,
) -> NeuralSurfaceResult | None:
    """Fit a neural IV surface model to observed option data.

    Transforms strikes and DTEs into (log_moneyness, dte_normalized) feature
    space, trains an MLP via PyTorch Lightning, and returns fitted values,
    residuals, z-scores, and R-squared.

    Args:
        strikes: Strike prices for each contract (1-D array).
        ivs: Implied volatilities (annualized, decimal) for each contract.
        dtes: Days to expiration for each contract.
        spot: Current underlying price.
        config: ML configuration.  Uses defaults if ``None``.

    Returns:
        ``NeuralSurfaceResult`` on success, or ``None`` if:
        - torch/lightning not installed
        - fewer than ``_MIN_SAMPLES`` valid data points
        - any input contains NaN/Inf
        - training fails
    """
    torch = _get_torch()
    L = _get_lightning()  # noqa: N806
    if torch is None or L is None:
        return None

    # Validate spot
    if not math.isfinite(spot) or spot <= 0.0:
        logger.warning("fit_neural_surface: invalid spot=%.4f", spot)
        return None

    try:
        # Validate array shapes match before composing mask
        if strikes.shape != ivs.shape or strikes.shape != dtes.shape:
            logger.debug(
                "fit_neural_surface: mismatched shapes strikes=%s ivs=%s dtes=%s",
                strikes.shape,
                ivs.shape,
                dtes.shape,
            )
            return None

        # Filter NaN/Inf/non-positive values
        valid_mask = (
            np.isfinite(strikes)
            & np.isfinite(ivs)
            & np.isfinite(dtes)
            & (strikes > 0.0)
            & (ivs > 0.0)
            & (dtes > 0.0)
        )
        strikes_f = strikes[valid_mask]
        ivs_f = ivs[valid_mask]
        dtes_f = dtes[valid_mask]

        n_samples = len(ivs_f)
        if n_samples < _MIN_SAMPLES:
            logger.debug(
                "fit_neural_surface: insufficient data (%d < %d)", n_samples, _MIN_SAMPLES
            )
            return None

        # Resolve config defaults
        epochs = 100
        lr = 0.001
        cache_dir: str | None = None
        if config is not None:
            epochs = config.neural_surface_epochs
            lr = config.neural_surface_lr
            cache_dir = config.model_cache_dir

        # Transform to feature space
        log_moneyness = np.log(strikes_f / spot).astype(np.float32)
        dte_normalized = (dtes_f / 365.0).astype(np.float32)
        iv_targets = ivs_f.astype(np.float32)

        # Stack features: (N, 2)
        features = np.column_stack([log_moneyness, dte_normalized])
        # Build dataset and dataloader
        x_tensor = torch.tensor(features, dtype=torch.float32)
        y_tensor = torch.tensor(iv_targets.reshape(-1, 1), dtype=torch.float32)
        dataset = torch.utils.data.TensorDataset(x_tensor, y_tensor)
        dataloader = torch.utils.data.DataLoader(
            dataset,
            batch_size=min(64, n_samples),
            shuffle=True,
        )

        # Build model
        model = _build_iv_surface_net(lr=lr)
        if model is None:
            return None

        # Train
        trainer = L.Trainer(
            max_epochs=epochs,
            enable_progress_bar=False,
            enable_model_summary=False,
            enable_checkpointing=bool(cache_dir),
            default_root_dir=cache_dir,
            logger=False,
            accelerator="cpu",
            devices=1,
        )
        trainer.fit(model, train_dataloaders=dataloader)

        # Generate predictions
        model.eval()
        with torch.no_grad():
            preds = model(x_tensor).numpy().flatten()

        fitted_ivs = preds.astype(np.float64)
        residuals = ivs_f - fitted_ivs

        # Z-scores
        resid_std = float(np.std(residuals))
        if math.isfinite(resid_std) and resid_std > 0.0:
            z_scores = residuals / resid_std
        else:
            z_scores = np.zeros_like(residuals)

        # R-squared
        ss_res = float(np.sum(residuals**2))
        ss_tot = float(np.sum((ivs_f - np.mean(ivs_f)) ** 2))
        r_squared = 1.0 - ss_res / ss_tot if math.isfinite(ss_tot) and ss_tot > 0.0 else 0.0

        if not math.isfinite(r_squared):
            r_squared = 0.0

        # Save checkpoint if cache_dir is set
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
            checkpoint_path = os.path.join(cache_dir, "neural_surface.ckpt")
            trainer.save_checkpoint(checkpoint_path)
            logger.info("Neural surface checkpoint saved: %s", checkpoint_path)

        return NeuralSurfaceResult(
            fitted_ivs=fitted_ivs,
            residuals=residuals,
            z_scores=z_scores,
            r_squared=r_squared,
            is_neural=True,
        )

    except Exception:
        logger.warning("Neural surface fitting failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Public API: predict_iv
# ---------------------------------------------------------------------------


def predict_iv(
    log_moneyness: float,
    dte_normalized: float,
    checkpoint_path: str,
) -> float | None:
    """Predict IV at a single point using a saved neural surface checkpoint.

    Args:
        log_moneyness: ln(K/S) — log-moneyness of the strike.
        dte_normalized: DTE / 365.0 — time to expiration in years.
        checkpoint_path: Path to a saved ``.ckpt`` checkpoint file.

    Returns:
        Predicted IV as a positive float, or ``None`` if:
        - torch/lightning not installed
        - checkpoint file does not exist
        - inputs are non-finite
        - prediction fails
    """
    torch = _get_torch()
    L = _get_lightning()  # noqa: N806
    if torch is None or L is None:
        return None

    # Guard inputs
    if not math.isfinite(log_moneyness) or not math.isfinite(dte_normalized):
        logger.warning(
            "predict_iv: non-finite inputs log_m=%.4f dte_n=%.4f",
            log_moneyness,
            dte_normalized,
        )
        return None

    if not os.path.isfile(checkpoint_path):
        logger.warning("predict_iv: checkpoint not found: %s", checkpoint_path)
        return None

    try:
        # Build a fresh model and load weights from checkpoint
        model = _build_iv_surface_net()
        if model is None:
            return None

        # Load checkpoint state dict
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()

        x = torch.tensor([[log_moneyness, dte_normalized]], dtype=torch.float32)
        with torch.no_grad():
            pred = float(model(x).item())

        if not math.isfinite(pred) or pred <= 0.0:
            return None

        return pred

    except Exception:
        logger.warning("predict_iv failed", exc_info=True)
        return None
