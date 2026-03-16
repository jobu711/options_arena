"""Tests for ML indicator computation in Phase 2 scoring.

Validates:
- GARCH forecast computed when ``enable_garch`` is True.
- Markov regime computed when ``enable_markov`` is True.
- ML indicators skipped when feature flags are False.
- Timeout handling for slow ML computations.
- ``iv_vs_forecast_spread`` computation from GARCH + EWMA data.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from options_arena.models.config import MLConfig
from options_arena.models.scan import IndicatorSignals
from options_arena.scan.phase_scoring import (
    _compute_garch_for_ticker,
    _compute_markov_for_ticker,
    _compute_ml_indicators,
)

# Mock paths — these functions are lazily imported inside the async helpers,
# so we patch them at their source module, not at the phase_scoring namespace.
_GARCH_PATH = "options_arena.indicators.vol_forecast.compute_garch_forecast"
_MARKOV_PATH = "options_arena.indicators.regime_ml.compute_markov_regime"
_TIMEOUT_PATH = "options_arena.scan.phase_scoring._ML_COMPUTATION_TIMEOUT"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_returns_series(n: int = 300) -> pd.Series:
    """Create a synthetic daily percentage log returns series."""
    import numpy as np

    rng = np.random.default_rng(42)
    returns = rng.normal(0.05, 1.5, size=n)
    index = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series(returns, index=index)


def _make_ohlcv_list(n: int = 300) -> list[object]:
    """Create a minimal synthetic OHLCV list for testing.

    Returns simple objects with date/open/high/low/close/volume attributes
    that ``ohlcv_to_dataframe`` can convert.
    """
    from datetime import date, timedelta
    from decimal import Decimal

    from options_arena.models.market_data import OHLCV

    bars: list[OHLCV] = []
    base_price = 100.0
    for i in range(n):
        d = date(2023, 1, 2) + timedelta(days=i)
        close = base_price + i * 0.01
        bars.append(
            OHLCV(
                ticker="TEST",
                date=d,
                open=Decimal(str(round(close - 0.5, 2))),
                high=Decimal(str(round(close + 1.0, 2))),
                low=Decimal(str(round(close - 1.0, 2))),
                close=Decimal(str(round(close, 2))),
                adjusted_close=Decimal(str(round(close, 2))),
                volume=1_000_000,
            )
        )
    return bars


# ---------------------------------------------------------------------------
# Test: GARCH computation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_garch_populates_vol_forecast_when_enabled() -> None:
    """GARCH forecast should populate vol_forecast_garch when successful."""
    signals = IndicatorSignals()
    returns = _make_returns_series(300)
    ml_config = MLConfig(enable_garch=True)

    with patch(_GARCH_PATH, return_value=0.25) as mock_garch:
        await _compute_garch_for_ticker(
            signals=signals,
            returns_series=returns,
            ml_config=ml_config,
        )

    assert signals.vol_forecast_garch == pytest.approx(0.25)
    mock_garch.assert_called_once()


@pytest.mark.asyncio
async def test_garch_leaves_none_when_returns_none() -> None:
    """GARCH forecast should leave fields as None when compute returns None."""
    signals = IndicatorSignals()
    returns = _make_returns_series(300)
    ml_config = MLConfig(enable_garch=True)

    with patch(_GARCH_PATH, return_value=None):
        await _compute_garch_for_ticker(
            signals=signals,
            returns_series=returns,
            ml_config=ml_config,
        )

    assert signals.vol_forecast_garch is None


@pytest.mark.asyncio
async def test_garch_timeout_leaves_none() -> None:
    """GARCH should gracefully handle timeout and leave fields as None."""
    signals = IndicatorSignals()
    returns = _make_returns_series(300)
    ml_config = MLConfig(enable_garch=True)

    def slow_garch(*args: object, **kwargs: object) -> float:
        """Simulate a slow GARCH computation that will exceed timeout."""
        import time

        time.sleep(10)
        return 0.25

    with (
        patch(_GARCH_PATH, side_effect=slow_garch),
        patch(_TIMEOUT_PATH, 0.01),
    ):
        await _compute_garch_for_ticker(
            signals=signals,
            returns_series=returns,
            ml_config=ml_config,
        )

    assert signals.vol_forecast_garch is None


@pytest.mark.asyncio
async def test_iv_vs_forecast_spread_computed() -> None:
    """iv_vs_forecast_spread = ewma_vol_forecast - garch_vol when both available."""
    signals = IndicatorSignals(ewma_vol_forecast=0.30)
    returns = _make_returns_series(300)
    ml_config = MLConfig(enable_garch=True)

    with patch(_GARCH_PATH, return_value=0.25):
        await _compute_garch_for_ticker(
            signals=signals,
            returns_series=returns,
            ml_config=ml_config,
        )

    assert signals.vol_forecast_garch == pytest.approx(0.25)
    assert signals.iv_vs_forecast_spread is not None
    assert signals.iv_vs_forecast_spread == pytest.approx(0.05, abs=1e-9)


@pytest.mark.asyncio
async def test_iv_vs_forecast_spread_none_without_ewma() -> None:
    """iv_vs_forecast_spread stays None when ewma_vol_forecast is not available."""
    signals = IndicatorSignals()  # ewma_vol_forecast defaults to None
    returns = _make_returns_series(300)
    ml_config = MLConfig(enable_garch=True)

    with patch(_GARCH_PATH, return_value=0.25):
        await _compute_garch_for_ticker(
            signals=signals,
            returns_series=returns,
            ml_config=ml_config,
        )

    assert signals.vol_forecast_garch == pytest.approx(0.25)
    assert signals.iv_vs_forecast_spread is None


# ---------------------------------------------------------------------------
# Test: Markov regime computation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_markov_populates_regime_when_enabled() -> None:
    """Markov regime should populate regime_markov_label and transition_prob."""
    from options_arena.indicators.regime_ml import MarkovRegimeOutput

    signals = IndicatorSignals()
    returns = _make_returns_series(300)
    ml_config = MLConfig(enable_markov=True)

    mock_result = MarkovRegimeOutput(
        current_regime=1,
        regime_probabilities=[0.1, 0.7, 0.2],
        transition_matrix=[[0.9, 0.08, 0.02], [0.05, 0.85, 0.1], [0.03, 0.12, 0.85]],
        regime_label="normal",
    )

    with patch(_MARKOV_PATH, return_value=mock_result):
        await _compute_markov_for_ticker(
            signals=signals,
            returns_series=returns,
            ml_config=ml_config,
        )

    assert signals.regime_markov_label == pytest.approx(1.0)  # "normal" -> 1.0
    assert signals.regime_transition_prob is not None
    assert signals.regime_transition_prob == pytest.approx(0.85, abs=1e-9)


@pytest.mark.asyncio
async def test_markov_leaves_none_when_returns_none() -> None:
    """Markov regime should leave fields as None when compute returns None."""
    signals = IndicatorSignals()
    returns = _make_returns_series(300)
    ml_config = MLConfig(enable_markov=True)

    with patch(_MARKOV_PATH, return_value=None):
        await _compute_markov_for_ticker(
            signals=signals,
            returns_series=returns,
            ml_config=ml_config,
        )

    assert signals.regime_markov_label is None
    assert signals.regime_transition_prob is None


# ---------------------------------------------------------------------------
# Test: _compute_ml_indicators (top-level dispatcher)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ml_indicators_skipped_when_disabled() -> None:
    """No ML indicators computed when both flags are False (default)."""
    signals = IndicatorSignals()
    raw_signals = {"AAPL": signals}
    ohlcv_map: dict[str, list[object]] = {"AAPL": _make_ohlcv_list(300)}
    ml_config = MLConfig()  # defaults: all disabled

    await _compute_ml_indicators(
        raw_signals=raw_signals,
        ohlcv_map=ohlcv_map,
        ml_config=ml_config,
    )

    assert signals.vol_forecast_garch is None
    assert signals.regime_markov_label is None
    assert signals.regime_transition_prob is None


@pytest.mark.asyncio
async def test_ml_indicators_computed_for_tickers_with_sufficient_data() -> None:
    """ML indicators computed for tickers with >= 252 bars."""
    from options_arena.indicators.regime_ml import MarkovRegimeOutput

    signals = IndicatorSignals()
    raw_signals = {"AAPL": signals}
    ohlcv_map: dict[str, list[object]] = {"AAPL": _make_ohlcv_list(300)}
    ml_config = MLConfig(enable_garch=True, enable_markov=True)

    mock_markov = MarkovRegimeOutput(
        current_regime=0,
        regime_probabilities=[0.8, 0.15, 0.05],
        transition_matrix=[[0.95, 0.04, 0.01], [0.1, 0.8, 0.1], [0.05, 0.15, 0.8]],
        regime_label="low_vol",
    )

    with (
        patch(_GARCH_PATH, return_value=0.20),
        patch(_MARKOV_PATH, return_value=mock_markov),
    ):
        await _compute_ml_indicators(
            raw_signals=raw_signals,
            ohlcv_map=ohlcv_map,
            ml_config=ml_config,
        )

    assert signals.vol_forecast_garch == pytest.approx(0.20)
    assert signals.regime_markov_label == pytest.approx(0.0)  # "low_vol" -> 0.0
    assert signals.regime_transition_prob is not None
    assert signals.regime_transition_prob == pytest.approx(0.95, abs=1e-9)


@pytest.mark.asyncio
async def test_ml_indicators_skipped_for_short_series() -> None:
    """ML indicators not computed for tickers with < 252 bars."""
    signals = IndicatorSignals()
    raw_signals = {"AAPL": signals}
    ohlcv_map: dict[str, list[object]] = {"AAPL": _make_ohlcv_list(100)}  # too short
    ml_config = MLConfig(enable_garch=True, enable_markov=True)

    await _compute_ml_indicators(
        raw_signals=raw_signals,
        ohlcv_map=ohlcv_map,
        ml_config=ml_config,
    )

    assert signals.vol_forecast_garch is None
    assert signals.regime_markov_label is None
