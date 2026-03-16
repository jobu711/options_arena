"""Unit tests for pricing/trajectory.py — LSTM trajectory forecasting.

Tests cover:
- TrajectoryLSTM: forward shape, positive stds, training step loss
- fit_trajectory_model: synthetic data, insufficient data, torch unavailable,
  horizon matching, NaN rejection, checkpoint save/load
- compute_prob_profit: ATM near half, deep ITM high, deep OTM low,
  no forecasts, unit interval clamping
- MarketContext prob_profit_neural field: accept, reject NaN, reject out of range
- MLConfig trajectory fields: defaults, horizon validation, sequence length range
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from options_arena.models.analysis import MarketContext
from options_arena.models.config import MLConfig
from options_arena.models.enums import ExerciseStyle, MacdSignal
from options_arena.pricing.trajectory import (
    TrajectoryForecast,
    _build_trajectory_lstm,
    compute_prob_profit,
    fit_trajectory_model,
)

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_MARKET_CONTEXT_KWARGS = {
    "ticker": "AAPL",
    "current_price": Decimal("186.50"),
    "price_52w_high": Decimal("199.62"),
    "price_52w_low": Decimal("164.08"),
    "rsi_14": 42.0,
    "macd_signal": MacdSignal.BULLISH_CROSSOVER,
    "next_earnings": date(2025, 7, 24),
    "dte_target": 45,
    "target_strike": Decimal("185.00"),
    "target_delta": 0.35,
    "sector": "Technology",
    "dividend_yield": 0.005,
    "exercise_style": ExerciseStyle.AMERICAN,
    "data_timestamp": datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
}


def _make_config(
    horizons: list[int] | None = None,
    seq_len: int = 20,
    hidden_dim: int = 32,
) -> MLConfig:
    """Create a minimal MLConfig for testing."""
    return MLConfig(
        enable_trajectory=True,
        trajectory_horizons=horizons or [30, 60, 90],
        trajectory_sequence_length=seq_len,
        trajectory_hidden_dim=hidden_dim,
    )


def _make_synthetic_data(
    n_samples: int = 50,
    seq_len: int = 20,
    n_features: int = 8,
    n_horizons: int = 3,
) -> tuple[list[list[float]], list[list[float]]]:
    """Generate synthetic feature sequences and target returns."""
    import random

    random.seed(42)
    features: list[list[float]] = []
    targets: list[list[float]] = []
    for _ in range(n_samples):
        # Flat sequence: seq_len * n_features
        seq = [random.gauss(0, 1) for _ in range(seq_len * n_features)]
        features.append(seq)
        target = [random.gauss(0.01, 0.05) for _ in range(n_horizons)]
        targets.append(target)
    return features, targets


# ===========================================================================
# TestTrajectoryLSTM
# ===========================================================================


class TestTrajectoryLSTM:
    """Tests for the TrajectoryLSTM LightningModule."""

    def test_forward_shape(self) -> None:
        """Verify output shape is (batch, 2 * n_horizons)."""
        torch = pytest.importorskip("torch")
        pytest.importorskip("lightning")

        n_horizons = 3
        model = _build_trajectory_lstm(
            input_dim=8, hidden_dim=32, n_layers=2, dropout=0.2, n_horizons=n_horizons
        )
        assert model is not None

        batch_size = 4
        seq_len = 20
        x = torch.randn(batch_size, seq_len, 8)
        model.eval()
        with torch.no_grad():
            output = model(x)

        assert output.shape == (batch_size, 2 * n_horizons)

    def test_std_positive_softplus(self) -> None:
        """Verify std outputs are strictly positive (softplus)."""
        torch = pytest.importorskip("torch")
        pytest.importorskip("lightning")

        n_horizons = 3
        model = _build_trajectory_lstm(
            input_dim=8, hidden_dim=32, n_layers=2, dropout=0.2, n_horizons=n_horizons
        )
        assert model is not None

        x = torch.randn(10, 20, 8)
        model.eval()
        with torch.no_grad():
            output = model(x)

        # Stds are the last n_horizons columns
        stds = output[:, n_horizons:]
        assert (stds > 0).all(), f"Expected all stds > 0, got min={stds.min().item()}"

    def test_training_step_returns_loss(self) -> None:
        """Verify training_step returns finite loss tensor."""
        torch = pytest.importorskip("torch")
        pytest.importorskip("lightning")

        n_horizons = 3
        model = _build_trajectory_lstm(
            input_dim=8, hidden_dim=32, n_layers=2, dropout=0.2, n_horizons=n_horizons
        )
        assert model is not None

        features = torch.randn(8, 20, 8)
        targets = torch.randn(8, n_horizons)
        batch = (features, targets)

        model.train()
        loss = model.training_step(batch, 0)

        assert loss is not None
        assert torch.isfinite(loss).item(), f"Expected finite loss, got {loss.item()}"


# ===========================================================================
# TestFitTrajectoryModel
# ===========================================================================


class TestFitTrajectoryModel:
    """Tests for the fit_trajectory_model function."""

    def test_fit_on_synthetic_data(self) -> None:
        """Verify fitting on synthetic return sequences produces valid forecasts."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        config = _make_config(seq_len=20, hidden_dim=32)
        features, targets = _make_synthetic_data(n_samples=50, seq_len=20)

        result = fit_trajectory_model(features, targets, config)

        assert result is not None
        assert len(result) > 0
        for forecast in result:
            assert isinstance(forecast, TrajectoryForecast)
            assert math.isfinite(forecast.mean)
            assert math.isfinite(forecast.std)
            assert forecast.std > 0

    def test_returns_none_insufficient_data(self) -> None:
        """Verify returns None when sequence too short (< 2 samples)."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        config = _make_config(seq_len=20, hidden_dim=32)
        features = [[0.1] * (20 * 8)]  # Only 1 sample
        targets = [[0.01, 0.02, 0.03]]

        result = fit_trajectory_model(features, targets, config)
        assert result is None

    def test_returns_none_torch_unavailable(self) -> None:
        """Verify returns None when torch not installed."""
        config = _make_config()
        features, targets = _make_synthetic_data(n_samples=10, seq_len=20)

        with patch("options_arena.pricing.trajectory._get_torch", return_value=None):
            result = fit_trajectory_model(features, targets, config)

        assert result is None

    def test_forecast_horizons_match_config(self) -> None:
        """Verify output contains forecasts for each configured horizon."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        horizons = [30, 60, 90]
        config = _make_config(horizons=horizons, seq_len=20, hidden_dim=32)
        features, targets = _make_synthetic_data(n_samples=50, seq_len=20, n_horizons=3)

        result = fit_trajectory_model(features, targets, config)

        assert result is not None
        result_horizons = {f.horizon_days for f in result}
        for h in horizons:
            assert h in result_horizons, f"Missing horizon {h} in forecasts"

    def test_nan_input_rejected(self) -> None:
        """Verify NaN/Inf inputs return None."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        config = _make_config(seq_len=20, hidden_dim=32)
        features, targets = _make_synthetic_data(n_samples=10, seq_len=20)

        # Inject NaN into first sample
        features[0][0] = float("nan")

        result = fit_trajectory_model(features, targets, config)
        assert result is None

    def test_inf_input_rejected(self) -> None:
        """Verify Inf inputs return None."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        config = _make_config(seq_len=20, hidden_dim=32)
        features, targets = _make_synthetic_data(n_samples=10, seq_len=20)

        # Inject Inf into first sample
        features[0][0] = float("inf")

        result = fit_trajectory_model(features, targets, config)
        assert result is None

    def test_checkpoint_save_load(self, tmp_path: Path) -> None:
        """Verify checkpoint saved to disk and loadable for inference."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        config = _make_config(seq_len=20, hidden_dim=32)
        features, targets = _make_synthetic_data(n_samples=50, seq_len=20)

        ckpt_dir = str(tmp_path / "model_cache")
        result = fit_trajectory_model(features, targets, config, checkpoint_dir=ckpt_dir)

        assert result is not None

        # Verify checkpoint file exists
        import os

        ckpt_path = os.path.join(ckpt_dir, "trajectory.ckpt")
        assert os.path.exists(ckpt_path), f"Checkpoint not found at {ckpt_path}"
        assert os.path.getsize(ckpt_path) > 0, "Checkpoint file is empty"

    def test_empty_features(self) -> None:
        """Verify returns None when feature sequence is empty."""
        pytest.importorskip("torch")
        pytest.importorskip("lightning")

        config = _make_config(seq_len=20, hidden_dim=32)
        result = fit_trajectory_model([], [], config)
        assert result is None

    def test_returns_none_lightning_unavailable(self) -> None:
        """Verify returns None when lightning not installed."""
        config = _make_config()
        features, targets = _make_synthetic_data(n_samples=10, seq_len=20)

        with patch("options_arena.pricing.trajectory._get_lightning", return_value=None):
            result = fit_trajectory_model(features, targets, config)

        assert result is None


# ===========================================================================
# TestComputeProbProfit
# ===========================================================================


class TestComputeProbProfit:
    """Tests for the compute_prob_profit function."""

    def test_atm_probability_near_half(self) -> None:
        """Verify ATM option has prob_profit near 0.5.

        With mean=0 (no drift) and spot == strike, P(S_T > K) should
        be approximately 0.5.
        """
        from scipy.stats import norm as scipy_norm

        forecasts = [TrajectoryForecast(horizon_days=30, mean=0.0, std=0.2)]
        spot = 100.0
        strike = 100.0

        result = compute_prob_profit(forecasts, spot, strike)

        assert result is not None
        # With mean=0, log(K/S)=0, so P = 1 - Phi(0, 0, 0.2) = 0.5
        expected = float(1.0 - scipy_norm.cdf(0.0, loc=0.0, scale=0.2))
        assert result == pytest.approx(expected, abs=0.01)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_deep_itm_high_probability(self) -> None:
        """Verify deep ITM call has high prob_profit."""
        forecasts = [TrajectoryForecast(horizon_days=30, mean=0.1, std=0.15)]
        spot = 150.0
        strike = 100.0  # Deep ITM

        result = compute_prob_profit(forecasts, spot, strike)

        assert result is not None
        assert result > 0.9, f"Expected high probability for deep ITM, got {result}"

    def test_deep_otm_low_probability(self) -> None:
        """Verify deep OTM call has low prob_profit."""
        forecasts = [TrajectoryForecast(horizon_days=30, mean=-0.05, std=0.1)]
        spot = 100.0
        strike = 200.0  # Deep OTM

        result = compute_prob_profit(forecasts, spot, strike)

        assert result is not None
        assert result < 0.05, f"Expected low probability for deep OTM, got {result}"

    def test_returns_none_no_forecasts(self) -> None:
        """Verify returns None when no valid forecasts."""
        result = compute_prob_profit([], 100.0, 100.0)
        assert result is None

    def test_clamped_to_unit_interval(self) -> None:
        """Verify output clamped to [0, 1]."""
        # Use a forecast that should give a valid probability
        forecasts = [TrajectoryForecast(horizon_days=30, mean=0.0, std=0.3)]
        result = compute_prob_profit(forecasts, 100.0, 100.0)

        assert result is not None
        assert 0.0 <= result <= 1.0

    def test_returns_none_invalid_spot(self) -> None:
        """Verify returns None when spot is non-positive."""
        forecasts = [TrajectoryForecast(horizon_days=30, mean=0.0, std=0.2)]
        assert compute_prob_profit(forecasts, 0.0, 100.0) is None
        assert compute_prob_profit(forecasts, -10.0, 100.0) is None

    def test_returns_none_invalid_strike(self) -> None:
        """Verify returns None when strike is non-positive."""
        forecasts = [TrajectoryForecast(horizon_days=30, mean=0.0, std=0.2)]
        assert compute_prob_profit(forecasts, 100.0, 0.0) is None
        assert compute_prob_profit(forecasts, 100.0, -10.0) is None

    def test_returns_none_nan_spot(self) -> None:
        """Verify returns None when spot is NaN."""
        forecasts = [TrajectoryForecast(horizon_days=30, mean=0.0, std=0.2)]
        assert compute_prob_profit(forecasts, float("nan"), 100.0) is None

    def test_selects_nearest_horizon(self) -> None:
        """Verify nearest horizon is selected when DTE is provided."""
        forecasts = [
            TrajectoryForecast(horizon_days=30, mean=0.05, std=0.15),
            TrajectoryForecast(horizon_days=60, mean=0.10, std=0.20),
            TrajectoryForecast(horizon_days=90, mean=0.15, std=0.25),
        ]
        # DTE=55 should select the 60-day forecast
        result_55 = compute_prob_profit(forecasts, 100.0, 100.0, dte=55)
        # Compare directly using the 60-day forecast
        result_60 = compute_prob_profit(
            [TrajectoryForecast(horizon_days=60, mean=0.10, std=0.20)],
            100.0,
            100.0,
        )
        assert result_55 is not None
        assert result_60 is not None
        assert result_55 == pytest.approx(result_60, abs=1e-10)

    def test_zero_std_degenerate(self) -> None:
        """Verify degenerate case with std=0."""
        # With mean > 0 and spot > strike -> expected price above strike
        forecasts = [TrajectoryForecast(horizon_days=30, mean=0.1, std=0.0)]
        result = compute_prob_profit(forecasts, 100.0, 90.0)  # ITM
        assert result == 1.0

        # With mean < 0 and spot < strike -> expected price below strike
        forecasts2 = [TrajectoryForecast(horizon_days=30, mean=-0.1, std=0.0)]
        result2 = compute_prob_profit(forecasts2, 80.0, 100.0)  # OTM
        assert result2 == 0.0


# ===========================================================================
# TestProbProfitNeuralField
# ===========================================================================


class TestProbProfitNeuralField:
    """Tests for prob_profit_neural on MarketContext."""

    def test_market_context_accepts_field(self) -> None:
        """Verify MarketContext accepts prob_profit_neural."""
        ctx = MarketContext(**_SAMPLE_MARKET_CONTEXT_KWARGS, prob_profit_neural=0.65)
        assert ctx.prob_profit_neural == pytest.approx(0.65)

    def test_market_context_accepts_none(self) -> None:
        """Verify MarketContext defaults to None for prob_profit_neural."""
        ctx = MarketContext(**_SAMPLE_MARKET_CONTEXT_KWARGS)
        assert ctx.prob_profit_neural is None

    def test_market_context_rejects_nan(self) -> None:
        """Verify MarketContext rejects NaN prob_profit_neural."""
        with pytest.raises(ValidationError, match="finite"):
            MarketContext(**_SAMPLE_MARKET_CONTEXT_KWARGS, prob_profit_neural=float("nan"))

    def test_market_context_rejects_inf(self) -> None:
        """Verify MarketContext rejects Inf prob_profit_neural."""
        with pytest.raises(ValidationError, match="finite"):
            MarketContext(**_SAMPLE_MARKET_CONTEXT_KWARGS, prob_profit_neural=float("inf"))

    def test_market_context_rejects_out_of_range_high(self) -> None:
        """Verify MarketContext rejects prob_profit_neural > 1.0."""
        with pytest.raises(ValidationError, match="prob_profit_neural"):
            MarketContext(**_SAMPLE_MARKET_CONTEXT_KWARGS, prob_profit_neural=1.5)

    def test_market_context_rejects_out_of_range_low(self) -> None:
        """Verify MarketContext rejects prob_profit_neural < 0.0."""
        with pytest.raises(ValidationError, match="prob_profit_neural"):
            MarketContext(**_SAMPLE_MARKET_CONTEXT_KWARGS, prob_profit_neural=-0.1)


# ===========================================================================
# TestTrajectoryConfig
# ===========================================================================


class TestTrajectoryConfig:
    """Tests for trajectory-related MLConfig fields."""

    def test_default_trajectory_disabled(self) -> None:
        """Verify enable_trajectory defaults to False."""
        config = MLConfig()
        assert config.enable_trajectory is False

    def test_default_horizons(self) -> None:
        """Verify default trajectory_horizons is [30, 60, 90]."""
        config = MLConfig()
        assert config.trajectory_horizons == [30, 60, 90]

    def test_default_sequence_length(self) -> None:
        """Verify default trajectory_sequence_length is 60."""
        config = MLConfig()
        assert config.trajectory_sequence_length == 60

    def test_default_hidden_dim(self) -> None:
        """Verify default trajectory_hidden_dim is 128."""
        config = MLConfig()
        assert config.trajectory_hidden_dim == 128

    def test_horizons_validation(self) -> None:
        """Verify trajectory_horizons rejects non-positive values."""
        with pytest.raises(ValidationError, match="trajectory horizon must be >= 1"):
            MLConfig(trajectory_horizons=[30, 0, 90])

        with pytest.raises(ValidationError, match="trajectory horizon must be >= 1"):
            MLConfig(trajectory_horizons=[-5])

    def test_horizons_accepts_valid(self) -> None:
        """Verify trajectory_horizons accepts valid positive values."""
        config = MLConfig(trajectory_horizons=[7, 14, 30, 60])
        assert config.trajectory_horizons == [7, 14, 30, 60]

    def test_sequence_length_range(self) -> None:
        """Verify trajectory_sequence_length within [20, 252]."""
        with pytest.raises(ValidationError, match="trajectory_sequence_length"):
            MLConfig(trajectory_sequence_length=19)

        with pytest.raises(ValidationError, match="trajectory_sequence_length"):
            MLConfig(trajectory_sequence_length=253)

    def test_sequence_length_boundaries(self) -> None:
        """Verify boundary values are accepted."""
        config_min = MLConfig(trajectory_sequence_length=20)
        assert config_min.trajectory_sequence_length == 20

        config_max = MLConfig(trajectory_sequence_length=252)
        assert config_max.trajectory_sequence_length == 252

    def test_hidden_dim_range(self) -> None:
        """Verify trajectory_hidden_dim within [32, 512]."""
        with pytest.raises(ValidationError, match="trajectory_hidden_dim"):
            MLConfig(trajectory_hidden_dim=31)

        with pytest.raises(ValidationError, match="trajectory_hidden_dim"):
            MLConfig(trajectory_hidden_dim=513)

    def test_hidden_dim_boundaries(self) -> None:
        """Verify boundary values are accepted."""
        config_min = MLConfig(trajectory_hidden_dim=32)
        assert config_min.trajectory_hidden_dim == 32

        config_max = MLConfig(trajectory_hidden_dim=512)
        assert config_max.trajectory_hidden_dim == 512
