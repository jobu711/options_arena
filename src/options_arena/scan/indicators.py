"""Data-driven indicator dispatch for the scan pipeline.

Replaces v3's 14 copy-paste indicator blocks with a typed registry and
generic dispatch function.  Each ``IndicatorSpec`` maps an
``IndicatorSignals`` field name to an indicator function and its required
OHLCV column shape.

Public API:
  - ``InputShape``         -- StrEnum encoding OHLCV column requirements.
  - ``IndicatorSpec``      -- NamedTuple registry entry.
  - ``INDICATOR_REGISTRY`` -- 14 entries (options-specific indicators excluded).
  - ``ohlcv_to_dataframe`` -- Convert ``list[OHLCV]`` to indicator-ready DataFrame.
  - ``compute_indicators`` -- Generic dispatch: registry + DataFrame -> IndicatorSignals.
  - ``compute_options_indicators`` -- Compute put_call_ratio and max_pain_distance from chain.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from enum import StrEnum
from typing import NamedTuple

import numpy as np
import pandas as pd

from options_arena.indicators.moving_averages import sma_alignment, vwap_deviation
from options_arena.indicators.options_specific import max_pain, put_call_ratio_volume
from options_arena.indicators.oscillators import rsi, stoch_rsi, williams_r
from options_arena.indicators.trend import adx, roc, supertrend
from options_arena.indicators.volatility import atr_percent, bb_width, keltner_width
from options_arena.indicators.volume import ad_trend, obv_trend, relative_volume
from options_arena.models.enums import OptionType
from options_arena.models.market_data import OHLCV
from options_arena.models.options import OptionContract
from options_arena.models.scan import IndicatorSignals

logger = logging.getLogger(__name__)


class InputShape(StrEnum):
    """OHLCV column requirements for an indicator function.

    Each member tells ``compute_indicators`` which DataFrame columns to
    extract and pass to the indicator function.
    """

    CLOSE = "close"
    HLC = "hlc"
    CLOSE_VOLUME = "close_volume"
    HLCV = "hlcv"
    VOLUME = "volume"


class IndicatorSpec(NamedTuple):
    """Typed registry entry mapping a signal field to an indicator function.

    Attributes
    ----------
    field_name : str
        Must match an ``IndicatorSignals`` field name exactly.
    func : Callable[..., pd.Series]
        Indicator function from ``options_arena.indicators``.
    input_shape : InputShape
        Describes which OHLCV columns the function requires.
    """

    field_name: str
    func: Callable[..., pd.Series]
    input_shape: InputShape


# ---------------------------------------------------------------------------
# Registry — exactly 14 OHLCV-based indicators.
# The 4 options-specific indicators (iv_rank, iv_percentile, put_call_ratio,
# max_pain_distance) require chain data and are left as None.
# ---------------------------------------------------------------------------

INDICATOR_REGISTRY: list[IndicatorSpec] = [
    # Oscillators
    IndicatorSpec("rsi", rsi, InputShape.CLOSE),
    IndicatorSpec("stochastic_rsi", stoch_rsi, InputShape.CLOSE),
    IndicatorSpec("williams_r", williams_r, InputShape.HLC),
    # Trend
    IndicatorSpec("adx", adx, InputShape.HLC),
    IndicatorSpec("roc", roc, InputShape.CLOSE),
    IndicatorSpec("supertrend", supertrend, InputShape.HLC),
    # Volatility
    IndicatorSpec("bb_width", bb_width, InputShape.CLOSE),
    IndicatorSpec("atr_pct", atr_percent, InputShape.HLC),
    IndicatorSpec("keltner_width", keltner_width, InputShape.HLC),
    # Volume
    IndicatorSpec("obv", obv_trend, InputShape.CLOSE_VOLUME),
    IndicatorSpec("relative_volume", relative_volume, InputShape.VOLUME),
    IndicatorSpec("ad", ad_trend, InputShape.HLCV),
    # Moving Averages
    IndicatorSpec("sma_alignment", sma_alignment, InputShape.CLOSE),
    IndicatorSpec("vwap_deviation", vwap_deviation, InputShape.CLOSE_VOLUME),
]


def ohlcv_to_dataframe(ohlcv: list[OHLCV]) -> pd.DataFrame:
    """Convert OHLCV Pydantic models to a pandas DataFrame for indicators.

    Critical conversions:
      - ``Decimal`` -> ``float`` (prices): indicators use float math, not Decimal.
      - ``date`` -> ``DatetimeIndex``: standard pandas time-series convention.
      - Sorted ascending by date: indicators assume chronological order.

    The resulting DataFrame has columns ``open``, ``high``, ``low``,
    ``close``, ``volume``.  ``adjusted_close`` and ``ticker`` are excluded
    because indicators do not use them.
    """
    records: list[dict[str, object]] = [
        {
            "date": pd.Timestamp(bar.date),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": bar.volume,
        }
        for bar in ohlcv
    ]
    df = pd.DataFrame.from_records(records)
    df = df.set_index("date")
    df = df.sort_index(ascending=True)
    return df


def compute_indicators(
    df: pd.DataFrame,
    registry: list[IndicatorSpec],
) -> IndicatorSignals:
    """Dispatch each registry entry against the DataFrame and populate signals.

    For each ``IndicatorSpec`` in *registry*:
      1. Extract the columns dictated by ``spec.input_shape``.
      2. Call ``spec.func(...)`` with those columns.
      3. Take ``result.iloc[-1]`` as the scalar value.
      4. If the value is NaN, store ``None`` instead.

    Failures are isolated per indicator: an exception in one indicator is
    logged at WARNING and does **not** prevent the others from computing.
    """
    signals = IndicatorSignals()

    for spec in registry:
        try:
            match spec.input_shape:
                case InputShape.CLOSE:
                    result = spec.func(df["close"])
                case InputShape.HLC:
                    result = spec.func(df["high"], df["low"], df["close"])
                case InputShape.CLOSE_VOLUME:
                    result = spec.func(df["close"], df["volume"])
                case InputShape.HLCV:
                    result = spec.func(df["high"], df["low"], df["close"], df["volume"])
                case InputShape.VOLUME:
                    result = spec.func(df["volume"])

            value: float = float(result.iloc[-1])
            if math.isnan(value):
                setattr(signals, spec.field_name, None)
            else:
                setattr(signals, spec.field_name, value)

        except Exception:
            logger.warning(
                "Indicator %s failed; setting to None",
                spec.field_name,
                exc_info=True,
            )
            setattr(signals, spec.field_name, None)

    return signals


def compute_options_indicators(
    contracts: list[OptionContract],
    spot: float,
) -> IndicatorSignals:
    """Compute options-specific indicators from the full option chain.

    Calculates ``put_call_ratio`` (volume-weighted) and ``max_pain_distance``
    (percent distance from max-pain strike to spot) from the raw chain before
    any filtering.  These enrich ``TickerScore.signals`` so that
    ``MarketContext.completeness_ratio()`` reflects actual data availability.

    Parameters
    ----------
    contracts
        Full option chain (all expirations, unfiltered).
    spot
        Current underlying price (used for max_pain_distance calculation).

    Returns
    -------
    IndicatorSignals
        Partial signals with only ``put_call_ratio`` and ``max_pain_distance``
        set (all other fields remain ``None``).
    """
    signals = IndicatorSignals()

    if not contracts or spot <= 0:
        logger.debug("compute_options_indicators: no contracts or invalid spot (%.2f)", spot)
        return signals

    # Separate calls and puts
    calls = [c for c in contracts if c.option_type == OptionType.CALL]
    puts = [c for c in contracts if c.option_type == OptionType.PUT]

    # --- Put/Call Ratio (volume-weighted) ---
    if calls and puts:
        total_call_volume = sum(c.volume for c in calls)
        total_put_volume = sum(c.volume for c in puts)
        ratio = put_call_ratio_volume(total_put_volume, total_call_volume)
        if math.isfinite(ratio):
            signals.put_call_ratio = ratio
            logger.debug(
                "put_call_ratio=%.3f (put_vol=%d, call_vol=%d)",
                ratio,
                total_put_volume,
                total_call_volume,
            )
        else:
            logger.debug(
                "put_call_ratio is NaN (call_vol=%d) — setting to None",
                total_call_volume,
            )
    else:
        logger.debug(
            "put_call_ratio: skipped (calls=%d, puts=%d)",
            len(calls),
            len(puts),
        )

    # --- Max Pain Distance ---
    # Aggregate OI by unique strike across all contracts
    strike_oi: dict[float, tuple[int, int]] = {}  # strike → (call_oi, put_oi)
    for c in contracts:
        s = float(c.strike)
        call_oi, put_oi = strike_oi.get(s, (0, 0))
        if c.option_type == OptionType.CALL:
            call_oi += c.open_interest
        else:
            put_oi += c.open_interest
        strike_oi[s] = (call_oi, put_oi)

    if strike_oi:
        total_oi = sum(co + po for co, po in strike_oi.values())
        if total_oi > 0:
            try:
                sorted_strikes = sorted(strike_oi.keys())
                strikes_series = pd.Series(sorted_strikes, dtype=float)
                call_oi_series = pd.Series([strike_oi[s][0] for s in sorted_strikes], dtype=float)
                put_oi_series = pd.Series([strike_oi[s][1] for s in sorted_strikes], dtype=float)

                mp_strike = max_pain(strikes_series, call_oi_series, put_oi_series)
                if math.isfinite(mp_strike) and not np.isnan(mp_strike):
                    distance_pct = abs(mp_strike - spot) / spot * 100.0
                    signals.max_pain_distance = distance_pct
                    logger.debug(
                        "max_pain_distance=%.2f%% (max_pain_strike=%.2f, spot=%.2f)",
                        distance_pct,
                        mp_strike,
                        spot,
                    )
            except Exception:
                logger.warning("max_pain computation failed", exc_info=True)
        else:
            logger.debug("max_pain: skipped — total OI is 0")
    else:
        logger.debug("max_pain: skipped — no strike OI data")

    return signals
