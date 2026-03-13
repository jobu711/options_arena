"""Technical indicators for options analysis.

Pure math module: pandas Series/DataFrames in, pandas Series/DataFrames out.
No API calls, no Pydantic models, no I/O.
"""

from options_arena.indicators.hv_estimators import (
    compute_hv_parkinson,
    compute_hv_rogers_satchell,
    compute_hv_yang_zhang,
)
from options_arena.indicators.moving_averages import sma_alignment, vwap_deviation
from options_arena.indicators.options_specific import (
    iv_percentile,
    iv_rank,
    max_pain,
    put_call_ratio_oi,
    put_call_ratio_volume,
)
from options_arena.indicators.oscillators import rsi, stoch_rsi, williams_r
from options_arena.indicators.trend import adx, macd, roc, supertrend
from options_arena.indicators.vol_surface import (
    VolSurfaceIndicators,
    VolSurfaceResult,
    compute_surface_indicators,
    compute_vol_surface,
)
from options_arena.indicators.volatility import atr_percent, bb_width, keltner_width
from options_arena.indicators.volume import ad_trend, obv_trend, relative_volume

__all__ = [
    "VolSurfaceIndicators",
    "VolSurfaceResult",
    "ad_trend",
    "adx",
    "atr_percent",
    "bb_width",
    "compute_hv_parkinson",
    "compute_hv_rogers_satchell",
    "compute_hv_yang_zhang",
    "compute_surface_indicators",
    "compute_vol_surface",
    "iv_percentile",
    "iv_rank",
    "keltner_width",
    "macd",
    "max_pain",
    "obv_trend",
    "put_call_ratio_oi",
    "put_call_ratio_volume",
    "relative_volume",
    "roc",
    "rsi",
    "sma_alignment",
    "stoch_rsi",
    "supertrend",
    "vwap_deviation",
    "williams_r",
]
