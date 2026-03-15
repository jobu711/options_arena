"""Performance benchmark fixtures — deterministic, representative inputs.

Provides fixtures for all 4 function groups:
- Pricing: ATM, 30 DTE, sigma=0.25 scalars
- Indicators: 250-row synthetic DataFrame with realistic OHLCV data
- Scoring: 50-ticker universe with pre-computed indicator values
- Orchestration: 6-agent confidence and direction arrays
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from options_arena.models.enums import (
    ExerciseStyle,
    GreeksSource,
    OptionType,
    PricingModel,
    SignalDirection,
)
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.models.scan import IndicatorSignals

_BENCHMARK_EXPIRATION = date(2099, 2, 15)

# ---------------------------------------------------------------------------
# Pricing fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def atm_pricing_params() -> dict[str, float]:
    """ATM pricing parameters: S=100, K=100, T=30/365, r=0.05, q=0.0, sigma=0.25."""
    return {
        "S": 100.0,
        "K": 100.0,
        "T": 30.0 / 365.0,
        "r": 0.05,
        "q": 0.0,
        "sigma": 0.25,
    }


@pytest.fixture()
def iv_market_price() -> float:
    """A realistic market price for IV solver benchmarks (ATM call ~$2.89)."""
    return 2.89


# ---------------------------------------------------------------------------
# Indicator fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_ohlcv_df() -> pd.DataFrame:
    """250-row synthetic DataFrame with realistic OHLCV data.

    Simulates a stock starting at $100 with ~20% annualized volatility.
    Columns: open, high, low, close, volume.
    """
    rng = np.random.default_rng(42)
    n = 250

    # Geometric Brownian Motion for close prices
    daily_vol = 0.20 / np.sqrt(252)
    returns = rng.normal(0.0003, daily_vol, n)
    close = 100.0 * np.cumprod(1.0 + returns)

    # Realistic OHLC from close
    intraday_range = close * rng.uniform(0.005, 0.025, n)
    high = close + intraday_range * rng.uniform(0.3, 0.7, n)
    low = close - intraday_range * rng.uniform(0.3, 0.7, n)
    open_ = close + rng.normal(0, 0.003, n) * close

    # Ensure OHLC validity: high >= max(open, close), low <= min(open, close)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    # Ensure all prices are positive
    low = np.maximum(low, 0.01)

    volume = rng.integers(500_000, 5_000_000, n).astype(float)

    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


@pytest.fixture()
def sample_close_series(sample_ohlcv_df: pd.DataFrame) -> pd.Series:
    """250-element pandas Series of close prices."""
    result: pd.Series = sample_ohlcv_df["close"]
    return result


@pytest.fixture()
def sample_volume_series(sample_ohlcv_df: pd.DataFrame) -> pd.Series:
    """250-element pandas Series of volume."""
    result: pd.Series = sample_ohlcv_df["volume"]
    return result


@pytest.fixture()
def sample_high_series(sample_ohlcv_df: pd.DataFrame) -> pd.Series:
    """250-element pandas Series of high prices."""
    result: pd.Series = sample_ohlcv_df["high"]
    return result


@pytest.fixture()
def sample_low_series(sample_ohlcv_df: pd.DataFrame) -> pd.Series:
    """250-element pandas Series of low prices."""
    result: pd.Series = sample_ohlcv_df["low"]
    return result


@pytest.fixture()
def sample_open_series(sample_ohlcv_df: pd.DataFrame) -> pd.Series:
    """250-element pandas Series of open prices."""
    result: pd.Series = sample_ohlcv_df["open"]
    return result


@pytest.fixture()
def sample_returns_series(sample_close_series: pd.Series) -> pd.Series:
    """Daily log returns derived from close prices."""
    result: pd.Series = np.log(sample_close_series / sample_close_series.shift(1)).dropna()
    return result


@pytest.fixture()
def sample_iv_history() -> pd.Series:
    """250-element pandas Series of historical implied volatilities."""
    rng = np.random.default_rng(99)
    return pd.Series(rng.uniform(0.15, 0.55, 250))


@pytest.fixture()
def sample_option_chain_df() -> pd.DataFrame:
    """Synthetic option chain DataFrame for options-specific indicators.

    Contains: strike, bid, ask, volume, openInterest, impliedVolatility, gamma,
    option_type columns for 20 strikes.
    """
    rng = np.random.default_rng(123)
    n_strikes = 20
    strikes = np.linspace(85, 115, n_strikes)
    bid = rng.uniform(0.10, 8.0, n_strikes)
    ask = bid + rng.uniform(0.05, 0.50, n_strikes)
    volume = rng.integers(10, 5000, n_strikes)
    oi = rng.integers(100, 20000, n_strikes)
    iv = rng.uniform(0.18, 0.45, n_strikes)
    gamma = rng.uniform(0.001, 0.05, n_strikes)

    return pd.DataFrame(
        {
            "strike": strikes,
            "bid": bid,
            "ask": ask,
            "volume": volume,
            "openInterest": oi,
            "impliedVolatility": iv,
            "gamma": gamma,
        }
    )


@pytest.fixture()
def vol_surface_arrays() -> dict[str, np.ndarray | float]:
    """Arrays for compute_vol_surface benchmark."""
    rng = np.random.default_rng(77)
    n = 30
    spot = 100.0
    strikes = np.linspace(85, 115, n)
    ivs = rng.uniform(0.18, 0.45, n)
    dtes = rng.choice([30.0, 45.0, 60.0, 90.0], n)
    option_types = rng.choice([1.0, -1.0], n)
    return {
        "strikes": strikes,
        "ivs": ivs,
        "dtes": dtes,
        "option_types": option_types,
        "spot": spot,
    }


# ---------------------------------------------------------------------------
# Scoring fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def scoring_universe() -> dict[str, IndicatorSignals]:
    """50-ticker universe with pre-computed indicator values for scoring benchmarks."""
    rng = np.random.default_rng(555)
    universe: dict[str, IndicatorSignals] = {}
    for i in range(50):
        ticker = f"TICK{i:03d}"
        universe[ticker] = IndicatorSignals(
            rsi=float(rng.uniform(20, 80)),
            stochastic_rsi=float(rng.uniform(10, 90)),
            williams_r=float(rng.uniform(-90, -10)),
            adx=float(rng.uniform(10, 60)),
            roc=float(rng.uniform(-20, 20)),
            supertrend=float(rng.choice([-1.0, 1.0])),
            macd=float(rng.uniform(-3, 3)),
            bb_width=float(rng.uniform(0.01, 0.15)),
            atr_pct=float(rng.uniform(0.01, 0.06)),
            keltner_width=float(rng.uniform(0.01, 0.15)),
            obv=float(rng.uniform(-5e6, 5e6)),
            ad=float(rng.uniform(-5e6, 5e6)),
            relative_volume=float(rng.uniform(0.5, 3.0)),
            sma_alignment=float(rng.uniform(-0.5, 0.5)),
            vwap_deviation=float(rng.uniform(-0.05, 0.05)),
            iv_rank=float(rng.uniform(10, 90)),
            iv_percentile=float(rng.uniform(10, 90)),
            put_call_ratio=float(rng.uniform(0.5, 2.0)),
            max_pain_distance=float(rng.uniform(-0.1, 0.1)),
        )
    return universe


@pytest.fixture()
def single_ticker_signals() -> IndicatorSignals:
    """A single ticker's raw indicator values for composite_score and direction."""
    return IndicatorSignals(
        rsi=55.0,
        stochastic_rsi=48.0,
        williams_r=-52.0,
        adx=28.0,
        roc=3.5,
        supertrend=1.0,
        macd=0.5,
        bb_width=0.06,
        atr_pct=0.025,
        keltner_width=0.08,
        obv=1_500_000.0,
        ad=800_000.0,
        relative_volume=1.2,
        sma_alignment=0.3,
        vwap_deviation=0.01,
        iv_rank=45.0,
        iv_percentile=52.0,
        put_call_ratio=0.85,
        max_pain_distance=0.02,
    )


@pytest.fixture()
def sample_contracts() -> list[OptionContract]:
    """10 synthetic OptionContract instances for contract selection benchmarks."""
    contracts: list[OptionContract] = []
    base_exp = _BENCHMARK_EXPIRATION
    for i in range(10):
        strike = Decimal(str(95 + i * 2))
        bid = Decimal(str(max(0.10, 5.0 - i * 0.5)))
        ask = bid + Decimal("0.15")
        contracts.append(
            OptionContract(
                ticker="TEST",
                option_type=OptionType.CALL,
                strike=strike,
                expiration=base_exp,
                bid=bid,
                ask=ask,
                last=bid + Decimal("0.05"),
                volume=500 + i * 100,
                open_interest=2000 + i * 500,
                exercise_style=ExerciseStyle.AMERICAN,
                market_iv=0.25 + i * 0.01,
                greeks=OptionGreeks(
                    delta=0.55 - i * 0.04,
                    gamma=0.03,
                    theta=-0.05,
                    vega=0.15,
                    rho=0.02,
                    pricing_model=PricingModel.BAW,
                ),
                greeks_source=GreeksSource.COMPUTED,
            )
        )
    return contracts


@pytest.fixture()
def sample_contracts_no_greeks() -> list[OptionContract]:
    """5 synthetic OptionContract instances without Greeks for compute_greeks benchmark."""
    contracts: list[OptionContract] = []
    base_exp = _BENCHMARK_EXPIRATION
    for i in range(5):
        strike = Decimal(str(95 + i * 2))
        bid = Decimal(str(max(0.10, 5.0 - i * 0.5)))
        ask = bid + Decimal("0.15")
        contracts.append(
            OptionContract(
                ticker="TEST",
                option_type=OptionType.CALL,
                strike=strike,
                expiration=base_exp,
                bid=bid,
                ask=ask,
                last=bid + Decimal("0.05"),
                volume=500 + i * 100,
                open_interest=2000 + i * 500,
                exercise_style=ExerciseStyle.AMERICAN,
                market_iv=0.25 + i * 0.01,
            )
        )
    return contracts


# ---------------------------------------------------------------------------
# Orchestration fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def agent_directions() -> dict[str, SignalDirection]:
    """6-agent direction map for orchestration benchmarks."""
    return {
        "trend": SignalDirection.BULLISH,
        "volatility": SignalDirection.BULLISH,
        "flow": SignalDirection.BEARISH,
        "fundamental": SignalDirection.BULLISH,
        "risk": SignalDirection.NEUTRAL,
        "contrarian": SignalDirection.BEARISH,
    }


@pytest.fixture()
def agent_probabilities() -> list[float]:
    """6-agent confidence probabilities for log-odds pooling benchmark."""
    return [0.75, 0.80, 0.35, 0.65, 0.50, 0.40]


@pytest.fixture()
def agent_weights() -> list[float]:
    """6-agent importance weights for log-odds pooling benchmark."""
    return [0.20, 0.15, 0.15, 0.15, 0.10, 0.10]


@pytest.fixture()
def citation_context_block() -> str:
    """Sample context block for citation density benchmark."""
    return (
        "RSI(14): 55.2\n"
        "ADX(14): 28.5\n"
        "MACD: 0.45\n"
        "IV RANK: 45.0\n"
        "PUT/CALL RATIO: 0.85\n"
        "SMA ALIGNMENT: 0.3\n"
        "ATR%: 2.5\n"
        "BB WIDTH: 0.06\n"
    )


@pytest.fixture()
def citation_agent_text() -> str:
    """Sample agent output referencing context labels."""
    return (
        "The RSI(14) reading of 55.2 suggests moderate momentum. "
        "With ADX(14) at 28.5 indicating a developing trend, the MACD "
        "crossover confirms bullish direction. IV RANK at 45 is neutral. "
        "The PUT/CALL RATIO of 0.85 shows balanced sentiment."
    )
