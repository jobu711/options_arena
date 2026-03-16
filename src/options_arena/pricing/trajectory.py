"""LSTM trajectory forecasting for probabilistic price paths.

Implements ``TrajectoryLSTM`` (a PyTorch Lightning module) that produces
probabilistic (mean, std) forecasts at configurable DTE horizons (30/60/90).
Derives ``prob_profit_neural = P(S_T > strike)`` from the predicted lognormal
distribution.

Rules:
- Scalar float in/out at public boundary. No pandas.
- Guarded imports: returns ``None`` when ``torch``/``lightning`` not installed.
- ``math.isfinite()`` guards on all outputs.
- ``logging`` only, never ``print()``.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any, NamedTuple

from scipy.stats import norm

if TYPE_CHECKING:
    from options_arena.models.config import MLConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Guarded imports
# ---------------------------------------------------------------------------


def _get_torch() -> Any:  # noqa: ANN401
    """Attempt to import ``torch``. Returns module or ``None``."""
    try:
        import torch

        return torch
    except ImportError:
        logger.info("torch not installed -- trajectory LSTM features disabled")
        return None


def _get_lightning() -> Any:  # noqa: ANN401
    """Attempt to import ``lightning``. Returns module or ``None``."""
    try:
        import lightning as L  # noqa: N812

        return L
    except ImportError:
        logger.info("lightning not installed -- trajectory LSTM features disabled")
        return None


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class TrajectoryForecast(NamedTuple):
    """Per-horizon probabilistic forecast from the trajectory LSTM."""

    horizon_days: int
    mean: float
    std: float


# ---------------------------------------------------------------------------
# Model definition
# ---------------------------------------------------------------------------

# Default horizons (DTE buckets) for trajectory forecasting.
_DEFAULT_HORIZONS: list[int] = [30, 60, 90]


def _build_trajectory_lstm(
    input_dim: int = 8,
    hidden_dim: int = 128,
    n_layers: int = 2,
    dropout: float = 0.2,
    n_horizons: int = 3,
) -> Any:  # noqa: ANN401
    """Construct a ``TrajectoryLSTM`` Lightning module.

    Returns the module instance, or ``None`` if torch/lightning are unavailable.
    """
    torch = _get_torch()
    L = _get_lightning()  # noqa: N806
    if torch is None or L is None:
        return None

    nn = torch.nn

    class TrajectoryLSTM(L.LightningModule):  # type: ignore[name-defined,misc]
        """LSTM for probabilistic price trajectory forecasting.

        Input: (batch, seq_len, input_dim) tensor of normalized features.
        Output: (batch, 2 * n_horizons) -- mean and std per horizon.
        """

        def __init__(
            self,
            input_dim: int = input_dim,
            hidden_dim: int = hidden_dim,
            n_layers: int = n_layers,
            dropout: float = dropout,
            n_horizons: int = n_horizons,
        ) -> None:
            super().__init__()
            self.save_hyperparameters()
            self.n_horizons = n_horizons

            # LSTM: dropout applied between LSTM layers only when n_layers > 1.
            # Separate nn.Dropout on the output (per acceptance criteria).
            self.lstm = nn.LSTM(
                input_size=input_dim,
                hidden_size=hidden_dim,
                num_layers=n_layers,
                batch_first=True,
            )
            self.dropout = nn.Dropout(dropout)
            self.head = nn.Linear(hidden_dim, 2 * n_horizons)
            self.softplus = nn.Softplus()

        def forward(self, x: Any) -> Any:  # noqa: ANN401
            """Forward pass.

            Args:
                x: Tensor of shape (batch, seq_len, input_dim).

            Returns:
                Tensor of shape (batch, 2 * n_horizons) where the first
                ``n_horizons`` columns are means and the last ``n_horizons``
                columns are positive standard deviations (via Softplus).
            """
            # lstm_out: (batch, seq_len, hidden_dim)
            lstm_out, _ = self.lstm(x)
            # Take the last time step
            last_hidden = lstm_out[:, -1, :]
            out = self.dropout(last_hidden)
            out = self.head(out)

            # Split into means and raw_stds
            means = out[:, : self.n_horizons]
            raw_stds = out[:, self.n_horizons :]
            stds = self.softplus(raw_stds)

            return torch.cat([means, stds], dim=1)

        def training_step(self, batch: Any, batch_idx: int) -> Any:  # noqa: ANN401
            """Compute Gaussian NLL loss for a training batch.

            Args:
                batch: Tuple of (features, targets) where features is
                    (batch, seq_len, input_dim) and targets is
                    (batch, n_horizons).
                batch_idx: Index of the current batch.

            Returns:
                Scalar loss tensor.
            """
            features, targets = batch
            output = self(features)
            means = output[:, : self.n_horizons]
            stds = output[:, self.n_horizons :]

            # Gaussian NLL: -log p(y | mu, sigma)
            loss = nn.functional.gaussian_nll_loss(means, targets, stds**2)
            self.log("train_loss", loss)
            return loss

        def configure_optimizers(self) -> Any:  # noqa: ANN401
            """Adam optimizer with lr=0.001."""
            return torch.optim.Adam(self.parameters(), lr=0.001)

    return TrajectoryLSTM(
        input_dim=input_dim,
        hidden_dim=hidden_dim,
        n_layers=n_layers,
        dropout=dropout,
        n_horizons=n_horizons,
    )


# ---------------------------------------------------------------------------
# Fitting function
# ---------------------------------------------------------------------------


def fit_trajectory_model(
    features_seq: list[list[float]],
    target_returns: list[list[float]],
    config: MLConfig,
    checkpoint_dir: str | None = None,
) -> list[TrajectoryForecast] | None:
    """Fit a trajectory LSTM and produce per-horizon forecasts.

    Args:
        features_seq: List of feature sequences, each of length
            ``config.trajectory_sequence_length`` with 8 features per step.
            Shape: (n_samples, seq_len, 8).
        target_returns: List of target return vectors, each of length
            ``len(config.trajectory_horizons)``.
            Shape: (n_samples, n_horizons).
        config: MLConfig with trajectory hyperparameters.
        checkpoint_dir: Optional directory to save model checkpoint.

    Returns:
        List of ``TrajectoryForecast`` (one per horizon) from the last
        sample's inference, or ``None`` if torch is unavailable, data is
        insufficient, or fitting fails.
    """
    torch = _get_torch()
    L = _get_lightning()  # noqa: N806
    if torch is None or L is None:
        return None

    n_horizons = len(config.trajectory_horizons)
    seq_len = config.trajectory_sequence_length

    # Validate input dimensions
    if len(features_seq) < 2:
        logger.debug("Insufficient data for trajectory model: %d samples", len(features_seq))
        return None

    if len(target_returns) != len(features_seq):
        logger.debug(
            "Feature/target length mismatch: %d vs %d",
            len(features_seq),
            len(target_returns),
        )
        return None

    # Validate all inputs are finite
    for i, seq in enumerate(features_seq):
        if len(seq) != seq_len * 8:
            # Flat sequence expected: seq_len * input_dim
            # Also accept nested list format
            pass
        for val in seq:
            if not math.isfinite(val):
                logger.debug("Non-finite value in features_seq at sample %d", i)
                return None
    for i, ret in enumerate(target_returns):
        for val in ret:
            if not math.isfinite(val):
                logger.debug("Non-finite value in target_returns at sample %d", i)
                return None

    try:
        # Convert to tensors
        # features_seq is (n_samples, seq_len * 8) flat or (n_samples, seq_len, 8) nested
        n_samples = len(features_seq)

        # Detect format: if first element has seq_len * 8 elements, it's flat
        first_len = len(features_seq[0])
        if first_len == seq_len * 8:
            # Flat format: reshape to (n_samples, seq_len, 8)
            features_tensor = torch.tensor(
                [features_seq[i] for i in range(n_samples)], dtype=torch.float32
            ).reshape(n_samples, seq_len, 8)
        else:
            # Nested format: already (n_samples, seq_len, 8) as list of lists
            features_tensor = torch.tensor(features_seq, dtype=torch.float32)

        targets_tensor = torch.tensor(target_returns, dtype=torch.float32)

        if features_tensor.shape[0] < 2:
            return None

        # Build model
        model = _build_trajectory_lstm(
            input_dim=8,
            hidden_dim=config.trajectory_hidden_dim,
            n_layers=2,
            dropout=0.2,
            n_horizons=n_horizons,
        )
        if model is None:
            return None

        # Create simple DataLoader
        dataset = torch.utils.data.TensorDataset(features_tensor, targets_tensor)
        dataloader = torch.utils.data.DataLoader(
            dataset, batch_size=min(32, n_samples), shuffle=True
        )

        # Train with Lightning Trainer (brief fit for inference)
        trainer = L.Trainer(
            max_epochs=5,
            enable_progress_bar=False,
            enable_model_summary=False,
            enable_checkpointing=False,
            logger=False,
            accelerator="cpu",
        )
        trainer.fit(model, dataloader)

        # Save checkpoint if requested
        if checkpoint_dir is not None:
            import os

            os.makedirs(checkpoint_dir, exist_ok=True)
            ckpt_path = os.path.join(checkpoint_dir, "trajectory.ckpt")
            trainer.save_checkpoint(ckpt_path)

        # Inference on the last sample
        model.eval()
        with torch.no_grad():
            last_features = features_tensor[-1:, :, :]
            output = model(last_features)  # (1, 2 * n_horizons)

        output_np = output.squeeze(0).cpu().numpy()
        forecasts: list[TrajectoryForecast] = []
        for j, horizon in enumerate(config.trajectory_horizons):
            mean_val = float(output_np[j])
            std_val = float(output_np[n_horizons + j])
            if not math.isfinite(mean_val) or not math.isfinite(std_val):
                logger.debug("Non-finite forecast at horizon %d", horizon)
                continue
            if std_val <= 0.0:
                logger.debug("Non-positive std at horizon %d: %f", horizon, std_val)
                continue
            forecasts.append(TrajectoryForecast(horizon_days=horizon, mean=mean_val, std=std_val))

        return forecasts if forecasts else None

    except Exception:
        logger.warning("Trajectory model fitting failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Probability computation
# ---------------------------------------------------------------------------


def compute_prob_profit(
    forecasts: list[TrajectoryForecast],
    spot: float,
    strike: float,
    dte: int | None = None,
) -> float | None:
    """Compute P(S_T > strike) from trajectory forecasts.

    Uses the lognormal CDF:
        P(S_T > K) = 1 - Phi(log(K/S), loc=mean, scale=std)

    where (mean, std) come from the nearest-horizon forecast to the
    contract's DTE.

    Args:
        forecasts: List of ``TrajectoryForecast`` from the LSTM.
        spot: Current spot price.
        strike: Option strike price.
        dte: Days to expiration of the contract. If ``None``, uses the
            first available forecast.

    Returns:
        Probability in [0.0, 1.0], or ``None`` if no valid forecast
        is available or inputs are invalid.
    """
    if not forecasts:
        return None

    if not math.isfinite(spot) or spot <= 0.0:
        return None
    if not math.isfinite(strike) or strike <= 0.0:
        return None

    # Select nearest-horizon forecast to DTE
    if dte is not None and dte > 0:
        # Find forecast with horizon closest to dte
        best = min(forecasts, key=lambda f: abs(f.horizon_days - dte))
    else:
        best = forecasts[0]

    if not math.isfinite(best.mean) or not math.isfinite(best.std):
        return None
    if best.std <= 0.0:
        # Degenerate case: deterministic forecast
        # If mean > 0, price expected to rise above current -> check if spot > strike
        expected_price = spot * math.exp(best.mean)
        return 1.0 if expected_price > strike else 0.0

    # P(S_T > K) = 1 - Phi(log(K/S), loc=mean, scale=std)
    log_moneyness = math.log(strike / spot)
    prob: float = float(1.0 - norm.cdf(log_moneyness, loc=best.mean, scale=best.std))

    # Clamp to [0, 1] for safety
    prob = max(0.0, min(1.0, prob))

    if not math.isfinite(prob):
        return None

    return prob
