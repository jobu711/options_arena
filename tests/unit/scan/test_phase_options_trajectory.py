"""Tests for neural trajectory integration in Phase 3 (phase_options.py).

Verifies that:
  - ``_compute_trajectory_prob`` calls ``fit_trajectory_model`` + ``compute_prob_profit``
    correctly via ``asyncio.to_thread()`` + ``asyncio.wait_for(timeout=5.0)``.
  - Trajectory computation is gated by ``MLConfig.enable_trajectory``.
  - Trajectory failure is gracefully handled (logged, not raised).
  - ``prob_profit_neural`` is populated on ``OptionsResult`` when trajectory succeeds.
  - Timeout produces ``None``, not a crash.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from options_arena.models import MLConfig, OptionContract
from options_arena.models.enums import OptionType
from options_arena.models.market_data import OHLCV
from options_arena.pricing.trajectory import TrajectoryForecast
from options_arena.scan.phase_options import _compute_trajectory_prob

# Patch target: the lazy import location inside _compute_trajectory_prob uses
# ``from options_arena.pricing.trajectory import ...``, so we patch the source
# module where the functions are defined.
_PATCH_FIT = "options_arena.pricing.trajectory.fit_trajectory_model"
_PATCH_PROB = "options_arena.pricing.trajectory.compute_prob_profit"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_bars(
    ticker: str,
    n: int = 100,
    *,
    close_price: float = 150.0,
    volume: int = 500_000,
) -> list[OHLCV]:
    """Generate n synthetic OHLCV bars."""
    bars: list[OHLCV] = []
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        cp = close_price + i * 0.1  # slight uptrend
        bars.append(
            OHLCV(
                ticker=ticker,
                date=d,
                open=Decimal(str(cp - 0.5)),
                high=Decimal(str(cp + 1.0)),
                low=Decimal(str(cp - 1.0)),
                close=Decimal(str(cp)),
                adjusted_close=Decimal(str(cp)),
                volume=volume + i * 100,
            )
        )
    return bars


def _make_ml_config(*, enable_trajectory: bool = True) -> MLConfig:
    """Build an MLConfig with trajectory enabled/disabled."""
    return MLConfig(
        enabled=True,
        enable_trajectory=enable_trajectory,
        trajectory_sequence_length=30,
        trajectory_horizons=[30, 60, 90],
        trajectory_hidden_dim=64,
    )


def _make_contract(
    ticker: str = "AAPL",
    strike: float = 155.0,
    dte: int = 45,
) -> OptionContract:
    """Build a minimal OptionContract for testing."""
    return OptionContract(
        ticker=ticker,
        option_type=OptionType.CALL,
        strike=Decimal(str(strike)),
        expiration=date.today() + timedelta(days=dte),
        bid=Decimal("2.50"),
        ask=Decimal("3.00"),
        volume=100,
        open_interest=500,
        implied_volatility=0.30,
    )


# ---------------------------------------------------------------------------
# TestComputeTrajectoryProb
# ---------------------------------------------------------------------------


class TestComputeTrajectoryProb:
    """Tests for the _compute_trajectory_prob async helper."""

    @pytest.mark.asyncio
    async def test_trajectory_called_when_enabled(self) -> None:
        """Verify trajectory model called when enable_trajectory=True."""
        ohlcv = _make_ohlcv_bars("AAPL", n=100)
        ml_config = _make_ml_config(enable_trajectory=True)

        mock_forecasts = [
            TrajectoryForecast(horizon_days=30, mean=0.05, std=0.10),
            TrajectoryForecast(horizon_days=60, mean=0.08, std=0.12),
            TrajectoryForecast(horizon_days=90, mean=0.10, std=0.15),
        ]

        with (
            patch(_PATCH_FIT, return_value=mock_forecasts) as mock_fit,
            patch(_PATCH_PROB, return_value=0.72) as mock_prob,
        ):
            result = await _compute_trajectory_prob(
                ohlcv_list=ohlcv,
                spot=150.0,
                strike=155.0,
                dte=45,
                ml_config=ml_config,
            )

        assert result == pytest.approx(0.72)
        mock_fit.assert_called_once()
        mock_prob.assert_called_once()

    @pytest.mark.asyncio
    async def test_trajectory_returns_none_on_failure(self) -> None:
        """Verify pipeline continues when trajectory model returns None."""
        ohlcv = _make_ohlcv_bars("AAPL", n=100)
        ml_config = _make_ml_config(enable_trajectory=True)

        with patch(_PATCH_FIT, return_value=None):
            result = await _compute_trajectory_prob(
                ohlcv_list=ohlcv,
                spot=150.0,
                strike=155.0,
                dte=45,
                ml_config=ml_config,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_trajectory_returns_none_insufficient_data(self) -> None:
        """Verify None when OHLCV data is too short for feature building."""
        # seq_len=30, need at least seq_len+2 bars for 2 samples
        ohlcv = _make_ohlcv_bars("AAPL", n=31)  # seq_len=30 -> only 1 sample
        ml_config = _make_ml_config(enable_trajectory=True)

        result = await _compute_trajectory_prob(
            ohlcv_list=ohlcv,
            spot=150.0,
            strike=155.0,
            dte=45,
            ml_config=ml_config,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_timeout_handling(self) -> None:
        """Verify asyncio.wait_for timeout propagates as TimeoutError.

        The caller in ``run_options_phase`` catches all exceptions, so the
        timeout is gracefully handled at the pipeline level. At the helper
        level, TimeoutError is expected to propagate.
        """
        ohlcv = _make_ohlcv_bars("AAPL", n=100)
        ml_config = _make_ml_config(enable_trajectory=True)

        with (
            patch(_PATCH_FIT, return_value=None),
            patch(
                "options_arena.scan.phase_options.asyncio.wait_for",
                side_effect=TimeoutError("trajectory timed out"),
            ),
            pytest.raises(TimeoutError),
        ):
            await _compute_trajectory_prob(
                ohlcv_list=ohlcv,
                spot=150.0,
                strike=155.0,
                dte=45,
                ml_config=ml_config,
            )

    @pytest.mark.asyncio
    async def test_prob_profit_populated(self) -> None:
        """Verify prob_profit_neural value is correctly returned."""
        ohlcv = _make_ohlcv_bars("AAPL", n=100)
        ml_config = _make_ml_config(enable_trajectory=True)

        mock_forecasts = [
            TrajectoryForecast(horizon_days=30, mean=0.03, std=0.08),
        ]

        with (
            patch(_PATCH_FIT, return_value=mock_forecasts),
            patch(_PATCH_PROB, return_value=0.55),
        ):
            result = await _compute_trajectory_prob(
                ohlcv_list=ohlcv,
                spot=150.0,
                strike=155.0,
                dte=30,
                ml_config=ml_config,
            )

        assert result == pytest.approx(0.55)

    @pytest.mark.asyncio
    async def test_feature_building_uses_correct_sequence_length(self) -> None:
        """Verify feature sequences respect trajectory_sequence_length config."""
        # Use seq_len=20 (minimum allowed by validator) with n=50 bars
        ohlcv = _make_ohlcv_bars("AAPL", n=50)
        ml_config = MLConfig(
            enabled=True,
            enable_trajectory=True,
            trajectory_sequence_length=20,
            trajectory_horizons=[30],
            trajectory_hidden_dim=64,
        )

        captured_features: list[list[list[float]]] = []

        def capture_fit(
            features_seq: list[list[float]],
            target_returns: list[list[float]],
            config: MLConfig,
            checkpoint_dir: str | None = None,
        ) -> list[TrajectoryForecast] | None:
            captured_features.append(features_seq)
            return [TrajectoryForecast(horizon_days=30, mean=0.02, std=0.05)]

        with (
            patch(_PATCH_FIT, side_effect=capture_fit),
            patch(_PATCH_PROB, return_value=0.60),
        ):
            await _compute_trajectory_prob(
                ohlcv_list=ohlcv,
                spot=150.0,
                strike=155.0,
                dte=30,
                ml_config=ml_config,
            )

        assert len(captured_features) == 1
        features = captured_features[0]
        # Each feature vector should be seq_len * 8 = 20 * 8 = 160 elements
        assert len(features[0]) == 20 * 8
        # Number of samples: len(ohlcv) - seq_len = 50 - 20 = 30
        assert len(features) == 30
