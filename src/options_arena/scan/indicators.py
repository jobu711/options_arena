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
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from enum import StrEnum
from typing import NamedTuple

import pandas as pd

from options_arena.indicators.moving_averages import sma_alignment, vwap_deviation
from options_arena.indicators.oscillators import rsi, stoch_rsi, williams_r
from options_arena.indicators.trend import adx, roc, supertrend
from options_arena.indicators.volatility import atr_percent, bb_width, keltner_width
from options_arena.indicators.volume import ad_trend, obv_trend, relative_volume
from options_arena.models.market_data import OHLCV
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
