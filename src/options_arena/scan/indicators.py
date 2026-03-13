"""Data-driven indicator dispatch for the scan pipeline.

Replaces v3's 14 copy-paste indicator blocks with a typed registry and
generic dispatch function.  Each ``IndicatorSpec`` maps an
``IndicatorSignals`` field name to an indicator function and its required
OHLCV column shape.

Public API:
  - ``InputShape``         -- StrEnum encoding OHLCV column requirements.
  - ``IndicatorSpec``      -- NamedTuple registry entry.
  - ``INDICATOR_REGISTRY`` -- 15 entries (options-specific indicators excluded).
  - ``ohlcv_to_dataframe`` -- Convert ``list[OHLCV]`` to indicator-ready DataFrame.
  - ``compute_indicators`` -- Generic dispatch: registry + DataFrame -> IndicatorSignals.
  - ``compute_options_indicators`` -- Compute put_call_ratio and max_pain_distance from chain.
  - ``compute_phase3_indicators`` -- Compute DSE indicators requiring chain/ticker data.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import date
from enum import StrEnum
from typing import NamedTuple

import numpy as np
import pandas as pd

from options_arena.indicators.flow_analytics import (
    compute_dollar_volume_trend,
    compute_gex,
    compute_max_pain_magnet,
    compute_oi_concentration,
    compute_unusual_activity,
)
from options_arena.indicators.fundamental import (
    compute_div_impact,
    compute_earnings_em_ratio,
    compute_earnings_impact,
    compute_iv_crush_history,
)
from options_arena.indicators.hv_estimators import compute_hv_yang_zhang
from options_arena.indicators.iv_analytics import (
    compute_ewma_vol_forecast,
    compute_expected_move,
    compute_expected_move_ratio,
    compute_hv_20d,
    compute_iv_hv_spread,
    compute_iv_term_shape,
    compute_iv_term_slope,
    compute_vol_cone_pctl,
)
from options_arena.indicators.moving_averages import sma_alignment, vwap_deviation
from options_arena.indicators.options_specific import max_pain, put_call_ratio_volume
from options_arena.indicators.oscillators import rsi, stoch_rsi, williams_r
from options_arena.indicators.regime import (
    compute_correlation_regime_shift,
    compute_rs_vs_spx,
    compute_volume_profile_skew,
)
from options_arena.indicators.trend import (
    adx,
    compute_adx_exhaustion,
    compute_multi_tf_alignment,
    compute_rsi_divergence,
    macd,
    roc,
    supertrend,
)
from options_arena.indicators.vol_surface import VolSurfaceResult
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
# Registry — exactly 15 OHLCV-based indicators.
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
    IndicatorSpec("macd", macd, InputShape.CLOSE),
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

    After registry dispatch, computes DSE trend extension indicators
    (``multi_tf_alignment``, ``rsi_divergence``, ``adx_exhaustion``) which
    depend on intermediate results from the registry indicators.

    Additionally computes OHLCV-based DSE indicators that require close+volume
    but don't fit the registry's simple column dispatch model:
    ``dollar_volume_trend`` and ``volume_profile_skew``.

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

    # --- DSE trend extension indicators (depend on intermediate results) ---
    # Only compute when the full registry is used; an empty registry is a test
    # scenario that expects all fields to remain None.
    if registry:
        _compute_trend_extensions(df, signals)

        # --- OHLCV-based DSE indicators that don't fit registry dispatch ---
        _compute_ohlcv_dse(df, signals)

    return signals


def _compute_trend_extensions(
    df: pd.DataFrame,
    signals: IndicatorSignals,
) -> None:
    """Compute DSE trend extension indicators from intermediate results.

    These indicators require pre-computed indicator series (supertrend, RSI,
    ADX) and therefore cannot use the simple registry dispatch model.

    Mutates ``signals`` in place.
    """
    close: pd.Series = df["close"]

    # --- multi_tf_alignment: daily supertrend + weekly supertrend ---
    try:
        # Compute daily supertrend series (full series, not just last value)
        daily_st = supertrend(df["high"], df["low"], close)
        # Resample to weekly close for the weekly supertrend computation
        weekly_close = close.resample("W").last().dropna()
        mtf = compute_multi_tf_alignment(daily_st, weekly_close)
        if mtf is not None and math.isfinite(mtf):
            signals.multi_tf_alignment = mtf
    except Exception:
        logger.warning("Indicator multi_tf_alignment failed; setting to None", exc_info=True)

    # --- rsi_divergence: close + RSI series ---
    try:
        rsi_series = rsi(close)
        divergence = compute_rsi_divergence(close, rsi_series)
        if divergence is not None and math.isfinite(divergence):
            signals.rsi_divergence = divergence
    except Exception:
        logger.warning("Indicator rsi_divergence failed; setting to None", exc_info=True)

    # --- adx_exhaustion: ADX series ---
    try:
        adx_series = adx(df["high"], df["low"], close)
        exhaustion = compute_adx_exhaustion(adx_series)
        if exhaustion is not None and math.isfinite(exhaustion):
            signals.adx_exhaustion = exhaustion
    except Exception:
        logger.warning("Indicator adx_exhaustion failed; setting to None", exc_info=True)


def _compute_ohlcv_dse(
    df: pd.DataFrame,
    signals: IndicatorSignals,
) -> None:
    """Compute OHLCV-based DSE indicators that don't fit registry dispatch.

    These indicators take close+volume but have non-standard signatures
    (return ``float | None``, not ``pd.Series``).

    Mutates ``signals`` in place.
    """
    close: pd.Series = df["close"]
    volume: pd.Series = df["volume"]

    # --- dollar_volume_trend ---
    try:
        dvt = compute_dollar_volume_trend(close, volume)
        if dvt is not None and math.isfinite(dvt):
            signals.dollar_volume_trend = dvt
    except Exception:
        logger.warning("Indicator dollar_volume_trend failed; setting to None", exc_info=True)

    # --- volume_profile_skew ---
    try:
        vps = compute_volume_profile_skew(close, volume)
        if vps is not None and math.isfinite(vps):
            signals.volume_profile_skew = vps
    except Exception:
        logger.warning("Indicator volume_profile_skew failed; setting to None", exc_info=True)


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


def compute_phase3_indicators(
    contracts: list[OptionContract],
    spot: float,
    close_series: pd.Series,
    dividend_yield: float,
    next_earnings: date | None,
    mp_strike: float | None,
    spx_close: pd.Series | None = None,
    ohlcv_df: pd.DataFrame | None = None,
    vol_result: VolSurfaceResult | None = None,
) -> IndicatorSignals:
    """Compute DSE indicators that require chain, ticker, or SPX data.

    Called in Phase 3 for each top-N ticker after chains and ticker info have
    been fetched.  Computes IV analytics, flow analytics, fundamental, and
    relative strength indicators.

    All failures are isolated per indicator -- one failed indicator does not
    crash others.  Returns partial ``IndicatorSignals`` with only the DSE
    fields set (all original 14+4 fields remain ``None``).

    Parameters
    ----------
    contracts
        Full option chain (all expirations, unfiltered).
    spot
        Current underlying price.
    close_series
        Daily close price series from OHLCV (Phase 1 data).
    dividend_yield
        Annual dividend yield as decimal fraction (from TickerInfo).
    next_earnings
        Next earnings date (``None`` if unknown).
    mp_strike
        Max pain strike price (pre-computed from ``compute_options_indicators``),
        or ``None`` if unavailable.
    spx_close
        SPX daily close prices for relative-strength computation.
        ``None`` if unavailable (indicator will be skipped).
    ohlcv_df
        Full OHLCV DataFrame with columns ``open``, ``high``, ``low``,
        ``close``, ``volume``.  When provided, Yang-Zhang HV is computed
        from the OHLC columns.  ``None`` skips HV computation.
    vol_result
        Pre-computed volatility surface analytics from
        ``compute_vol_surface()``.  When provided, ``skew_25d``,
        ``smile_curvature``, ``prob_above_current``, and ``atm_iv_30d``
        are extracted.  ``None`` skips vol surface indicators.

    Returns
    -------
    IndicatorSignals
        Partial signals with DSE fields populated where data was available.
    """
    signals = IndicatorSignals()

    if not contracts or not math.isfinite(spot) or spot <= 0.0:
        return signals

    # --- Yang-Zhang Historical Volatility ---
    try:
        if ohlcv_df is not None and len(ohlcv_df) >= 22:
            hv_yz = compute_hv_yang_zhang(
                ohlcv_df["open"],
                ohlcv_df["high"],
                ohlcv_df["low"],
                ohlcv_df["close"],
            )
            if hv_yz is not None and math.isfinite(hv_yz):
                signals.hv_yang_zhang = hv_yz
    except Exception:
        logger.warning("Indicator hv_yang_zhang failed; setting to None", exc_info=True)

    # --- Vol Surface Metrics ---
    try:
        if vol_result is not None:
            if vol_result.skew_25d is not None and math.isfinite(vol_result.skew_25d):
                signals.skew_25d = vol_result.skew_25d
            if vol_result.smile_curvature is not None and math.isfinite(
                vol_result.smile_curvature
            ):
                signals.smile_curvature = vol_result.smile_curvature
            if vol_result.prob_above_current is not None and math.isfinite(
                vol_result.prob_above_current
            ):
                signals.prob_above_current = vol_result.prob_above_current
    except Exception:
        logger.warning("Vol surface metric extraction failed; setting to None", exc_info=True)

    # --- IV Analytics ---

    # hv_20d (historical volatility, needed by iv_hv_spread and vol_cone)
    hv_20d_val: float | None = None
    try:
        hv_20d_val = compute_hv_20d(close_series)
        if hv_20d_val is not None and math.isfinite(hv_20d_val):
            signals.hv_20d = hv_20d_val
    except Exception:
        logger.warning("Indicator hv_20d failed; setting to None", exc_info=True)

    # Gather ATM IV from contracts (nearest to spot) for 30d and 60d buckets.
    # Vol surface provides more accurate ATM IV when a fitted surface is available;
    # fall back to the per-contract extraction method otherwise.
    atm_iv_30d, atm_iv_60d = _extract_atm_iv_by_dte(contracts, spot)
    if vol_result is not None:
        if vol_result.atm_iv_30d is not None and math.isfinite(vol_result.atm_iv_30d):
            atm_iv_30d = vol_result.atm_iv_30d
        if vol_result.atm_iv_60d is not None and math.isfinite(vol_result.atm_iv_60d):
            atm_iv_60d = vol_result.atm_iv_60d

    # iv_hv_spread
    try:
        spread = compute_iv_hv_spread(atm_iv_30d, hv_20d_val)
        if spread is not None and math.isfinite(spread):
            signals.iv_hv_spread = spread
    except Exception:
        logger.warning("Indicator iv_hv_spread failed; setting to None", exc_info=True)

    # iv_term_slope and iv_term_shape
    try:
        slope = compute_iv_term_slope(atm_iv_60d, atm_iv_30d)
        if slope is not None and math.isfinite(slope):
            signals.iv_term_slope = slope
        shape_enum = compute_iv_term_shape(slope)
        if shape_enum is not None:
            # Store as float ordinal for normalization (CONTANGO=1, FLAT=0, BACKWARDATION=-1)
            shape_map = {"contango": 1.0, "flat": 0.0, "backwardation": -1.0}
            signals.iv_term_shape = shape_map.get(shape_enum.value, 0.0)
    except Exception:
        logger.warning("Indicator iv_term_slope/shape failed; setting to None", exc_info=True)

    # ewma_vol_forecast
    try:
        if len(close_series) >= 21:
            log_returns = np.log(close_series.to_numpy()[1:] / close_series.to_numpy()[:-1])
            returns_series = pd.Series(log_returns, index=close_series.index[1:])
            ewma = compute_ewma_vol_forecast(returns_series)
            if ewma is not None and math.isfinite(ewma):
                signals.ewma_vol_forecast = ewma
    except Exception:
        logger.warning("Indicator ewma_vol_forecast failed; setting to None", exc_info=True)

    # vol_cone_percentile
    try:
        if hv_20d_val is not None and len(close_series) >= 60:
            # Build a rolling HV history for the volatility cone
            hv_history = close_series.pct_change().rolling(20).std(ddof=1) * math.sqrt(252)
            hv_pctl = compute_vol_cone_pctl(hv_20d_val, hv_history.dropna())
            if hv_pctl is not None and math.isfinite(hv_pctl):
                signals.vol_cone_percentile = hv_pctl
    except Exception:
        logger.warning("Indicator vol_cone_percentile failed; setting to None", exc_info=True)

    # expected_move and expected_move_ratio
    try:
        if atm_iv_30d is not None:
            em = compute_expected_move(spot, atm_iv_30d, 30)
            if em is not None and math.isfinite(em):
                signals.expected_move = em
                # Compute average actual 30-day move for ratio
                if len(close_series) >= 30:
                    pct_changes = close_series.pct_change(periods=30).dropna().abs()
                    if len(pct_changes) > 0:
                        avg_actual = float(pct_changes.mean()) * spot
                        em_ratio = compute_expected_move_ratio(em, avg_actual)
                        if em_ratio is not None and math.isfinite(em_ratio):
                            signals.expected_move_ratio = em_ratio
    except Exception:
        logger.warning("Indicator expected_move/ratio failed; setting to None", exc_info=True)

    # --- Flow Analytics ---

    # Build DataFrames for GEX and OI concentration
    chain_df = _contracts_to_dataframe(contracts)

    # gex (requires gamma — only available on contracts with greeks)
    try:
        calls_with_greeks = chain_df[
            (chain_df["option_type"] == "call") & chain_df["gamma"].notna()
        ]
        puts_with_greeks = chain_df[(chain_df["option_type"] == "put") & chain_df["gamma"].notna()]
        if not calls_with_greeks.empty and not puts_with_greeks.empty:
            gex_val = compute_gex(calls_with_greeks, puts_with_greeks, spot)
            if gex_val is not None and math.isfinite(gex_val):
                signals.gex = gex_val
    except Exception:
        logger.warning("Indicator gex failed; setting to None", exc_info=True)

    # oi_concentration
    try:
        if not chain_df.empty:
            oi_conc = compute_oi_concentration(chain_df)
            if oi_conc is not None and math.isfinite(oi_conc):
                signals.oi_concentration = oi_conc
    except Exception:
        logger.warning("Indicator oi_concentration failed; setting to None", exc_info=True)

    # unusual_activity_score
    try:
        if not chain_df.empty:
            unusual = compute_unusual_activity(chain_df)
            if unusual is not None and math.isfinite(unusual):
                signals.unusual_activity_score = unusual
    except Exception:
        logger.warning("Indicator unusual_activity_score failed; setting to None", exc_info=True)

    # max_pain_magnet (uses pre-computed mp_strike from compute_options_indicators)
    try:
        magnet = compute_max_pain_magnet(spot, mp_strike)
        if magnet is not None and math.isfinite(magnet):
            signals.max_pain_magnet = magnet
    except Exception:
        logger.warning("Indicator max_pain_magnet failed; setting to None", exc_info=True)

    # --- Fundamental Indicators ---

    # days_to_earnings_impact
    try:
        if next_earnings is not None:
            today = date.today()
            days_to = (next_earnings - today).days
            dte_target = 45  # default DTE target for impact calculation
            impact = compute_earnings_impact(days_to, dte_target)
            if impact is not None and math.isfinite(impact):
                signals.days_to_earnings_impact = impact
    except Exception:
        logger.warning("Indicator days_to_earnings_impact failed; setting to None", exc_info=True)

    # earnings_em_ratio (uses expected_move computed above)
    try:
        if signals.expected_move is not None and len(close_series) >= 30:
            pct_changes = close_series.pct_change(periods=5).dropna().abs()
            if len(pct_changes) > 0:
                avg_post_move = float(pct_changes.mean()) * spot
                em_ratio_val = compute_earnings_em_ratio(signals.expected_move, avg_post_move)
                if em_ratio_val is not None and math.isfinite(em_ratio_val):
                    signals.earnings_em_ratio = em_ratio_val
    except Exception:
        logger.warning("Indicator earnings_em_ratio failed; setting to None", exc_info=True)

    # div_ex_date_impact
    try:
        if math.isfinite(dividend_yield) and dividend_yield > 0.0:
            # Approximate: next ex-date not available from yfinance reliably,
            # use None to skip (returns None from compute_div_impact)
            div_impact = compute_div_impact(dividend_yield, 45, None)
            if div_impact is not None and math.isfinite(div_impact):
                signals.div_ex_date_impact = div_impact
    except Exception:
        logger.warning("Indicator div_ex_date_impact failed; setting to None", exc_info=True)

    # iv_crush_history proxy
    try:
        if len(close_series) >= 60:
            hv_series = close_series.pct_change().rolling(20).std(ddof=1) * math.sqrt(252)
            hv_clean = hv_series.dropna()
            if len(hv_clean) >= 20:
                mid_point = len(hv_clean) // 2
                hv_pre = hv_clean.iloc[:mid_point]
                hv_post = hv_clean.iloc[mid_point:]
                crush = compute_iv_crush_history(hv_pre, hv_post)
                if crush is not None and math.isfinite(crush):
                    signals.iv_crush_history = crush
    except Exception:
        logger.warning("Indicator iv_crush_history failed; setting to None", exc_info=True)

    # --- Market Regime (from volatility data) ---
    try:
        vcp = signals.vol_cone_percentile
        if vcp is not None and math.isfinite(vcp):
            regime_score = vcp
            if (
                hv_20d_val is not None
                and signals.ewma_vol_forecast is not None
                and math.isfinite(signals.ewma_vol_forecast)
                and hv_20d_val > 0
            ):
                ewma = signals.ewma_vol_forecast
                if ewma > hv_20d_val * 1.10:
                    regime_score = min(100.0, regime_score + 10.0)
                elif ewma < hv_20d_val * 0.90:
                    regime_score = max(0.0, regime_score - 10.0)
            signals.market_regime = regime_score
    except Exception:
        logger.warning("Indicator market_regime failed; setting to None", exc_info=True)

    # --- Relative Strength ---

    # rs_vs_spx and correlation_regime_shift
    try:
        if spx_close is not None and len(close_series) >= 60:
            ticker_returns = close_series.pct_change().dropna()
            spx_returns = spx_close.pct_change().dropna()
            # Align by shared dates (inner join on index) to avoid mismatched days
            aligned = pd.concat(
                [ticker_returns.rename("ticker"), spx_returns.rename("spx")],
                axis=1,
                join="inner",
            ).dropna()
            if len(aligned) >= 60:
                t_ret = aligned["ticker"]
                s_ret = aligned["spx"]
                rs = compute_rs_vs_spx(t_ret, s_ret)
                if rs is not None and math.isfinite(rs):
                    signals.rs_vs_spx = rs

                # correlation_regime_shift (uses same aligned returns)
                corr_shift = compute_correlation_regime_shift(t_ret, s_ret)
                if corr_shift is not None and math.isfinite(corr_shift):
                    signals.correlation_regime_shift = corr_shift
    except Exception:
        logger.warning(
            "Indicator rs_vs_spx/correlation_regime_shift failed; setting to None",
            exc_info=True,
        )

    # --- Liquidity (chain-wide spread and depth) ---
    # Reuses chain_df built at line 536 for flow analytics (same contracts input).
    try:
        if not chain_df.empty:
            bid_arr = chain_df["bid"].to_numpy(dtype=float)
            ask_arr = chain_df["ask"].to_numpy(dtype=float)
            oi_arr = chain_df["openInterest"].to_numpy(dtype=float)
            mid_arr = (ask_arr + bid_arr) / 2.0

            # chain_spread_pct: OI-weighted avg spread as percentage points
            valid_mask = mid_arr > 0
            if valid_mask.any():
                spread_arr = ask_arr[valid_mask] - bid_arr[valid_mask]
                spread_pct_arr = (spread_arr / mid_arr[valid_mask]) * 100.0
                oi_valid_arr = oi_arr[valid_mask]
                total_oi_f = float(oi_valid_arr.sum())
                if total_oi_f > 0:
                    weighted_spread = max(
                        0.0, float((spread_pct_arr * oi_valid_arr).sum() / total_oi_f)
                    )
                    if math.isfinite(weighted_spread):
                        signals.chain_spread_pct = weighted_spread
    except Exception:
        logger.warning(
            "Indicator chain_spread_pct failed; setting to None",
            exc_info=True,
        )

    try:
        if not chain_df.empty:
            # chain_oi_depth: log10(total_oi + 1)
            total_oi_all = int(chain_df["openInterest"].sum())
            depth = math.log10(total_oi_all + 1)
            if math.isfinite(depth):
                signals.chain_oi_depth = depth
    except Exception:
        logger.warning(
            "Indicator chain_oi_depth failed; setting to None",
            exc_info=True,
        )

    return signals


def _extract_atm_iv_by_dte(
    contracts: list[OptionContract],
    spot: float,
) -> tuple[float | None, float | None]:
    """Extract ATM implied volatility for ~30d and ~60d expiration buckets.

    Finds the contract closest to ATM (smallest ``|strike - spot|``) within
    each DTE bucket.  Uses ``market_iv`` from yfinance as the IV source.

    Parameters
    ----------
    contracts
        Full option chain (all expirations, unfiltered).
    spot
        Current underlying price.

    Returns
    -------
    tuple[float | None, float | None]
        ``(atm_iv_30d, atm_iv_60d)`` — ATM IV for the nearest 30-day and
        60-day expirations.  ``None`` when no suitable contract exists.
    """
    if not contracts or spot <= 0.0:
        return None, None

    today = date.today()
    best_30d: tuple[float, float] | None = None  # (total_distance, iv)
    best_60d: tuple[float, float] | None = None

    for c in contracts:
        # Use calls for ATM IV (calls and puts should converge at ATM)
        if c.option_type != OptionType.CALL:
            continue
        dte = (c.expiration - today).days
        if dte <= 0:
            continue

        iv = c.market_iv
        if not math.isfinite(iv) or iv <= 0.0:
            continue

        strike_dist = abs(float(c.strike) - spot) / spot
        # Only consider contracts within 5% of ATM
        if strike_dist > 0.05:
            continue

        # 30d bucket: 20-45 DTE
        if 20 <= dte <= 45:
            dte_dist = abs(dte - 30)
            total_dist = float(dte_dist) + strike_dist * 100  # weight strike proximity
            if best_30d is None or total_dist < best_30d[0]:
                best_30d = (total_dist, iv)

        # 60d bucket: 45-90 DTE
        if 45 < dte <= 90:
            dte_dist = abs(dte - 60)
            total_dist = float(dte_dist) + strike_dist * 100
            if best_60d is None or total_dist < best_60d[0]:
                best_60d = (total_dist, iv)

    atm_iv_30d = best_30d[1] if best_30d is not None else None
    atm_iv_60d = best_60d[1] if best_60d is not None else None
    return atm_iv_30d, atm_iv_60d


def _contracts_to_dataframe(
    contracts: list[OptionContract],
) -> pd.DataFrame:
    """Convert option contracts to a DataFrame for flow analytics.

    Columns: ``strike``, ``openInterest``, ``volume``, ``bid``, ``ask``,
    ``gamma``, ``option_type``.

    ``gamma`` is ``NaN`` for contracts where ``greeks`` is ``None`` (i.e.,
    contracts before Greeks computation by ``recommend_contracts``).
    """
    if not contracts:
        return pd.DataFrame(
            columns=["strike", "openInterest", "volume", "bid", "ask", "gamma", "option_type"]
        )

    records: list[dict[str, object]] = []
    for c in contracts:
        gamma_val: float = float("nan")
        if c.greeks is not None:
            gamma_val = c.greeks.gamma

        records.append(
            {
                "strike": float(c.strike),
                "openInterest": c.open_interest,
                "volume": c.volume,
                "bid": float(c.bid),
                "ask": float(c.ask),
                "gamma": gamma_val,
                "option_type": c.option_type.value,
            }
        )

    return pd.DataFrame.from_records(records)
