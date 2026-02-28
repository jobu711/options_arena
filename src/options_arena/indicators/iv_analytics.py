"""IV and volatility analytics indicators.

13 indicator functions for IV modeling: IV-HV spread, term structure analysis,
skew metrics, volatility regime classification, EWMA forecasting, volatility
cone percentile, VIX correlation, and expected move computations.

Rules:
- Takes typed inputs (float, pd.Series), returns float | None.
- NO Pydantic models, NO API calls — pure math on pre-fetched data.
- Division-by-zero: guard with ``math.isfinite()`` and None checks.
- Return ``None`` on insufficient data, not NaN or 0.0.
"""

import math

import numpy as np
import pandas as pd

from options_arena.models.enums import IVTermStructureShape, VolRegime


def compute_iv_hv_spread(
    atm_iv_30d: float | None,
    hv_20d: float | None,
) -> float | None:
    """IV-HV spread: implied volatility minus realized volatility.

    Positive = IV > realized (premium sellers favored).
    Negative = IV < realized (premium buyers favored).

    Formula: IV_HV_spread = ATM_IV_30d - HV_20d

    Reference: Natenberg (1994) "Option Volatility and Pricing", Ch. 19.

    Args:
        atm_iv_30d: 30-day ATM implied volatility (annualized, decimal).
        hv_20d: 20-day historical volatility (annualized, decimal).

    Returns:
        IV-HV spread as float, or ``None`` if either input is unavailable.
    """
    if atm_iv_30d is None or hv_20d is None:
        return None
    if not math.isfinite(atm_iv_30d) or not math.isfinite(hv_20d):
        return None
    return atm_iv_30d - hv_20d


def compute_hv_20d(close_series: pd.Series) -> float | None:
    """20-day historical volatility (annualized standard deviation of log returns).

    Formula: HV_20d = std(ln(close_t / close_{t-1}), ddof=1) * sqrt(252)

    Reference: Hull (2018) "Options, Futures, and Other Derivatives", Ch. 15.

    Args:
        close_series: Daily close prices. Requires at least 21 data points
            (20 log returns).

    Returns:
        Annualized 20-day historical volatility, or ``None`` if insufficient data.
    """
    if len(close_series) < 21:
        return None

    # Use last 21 prices to get 20 log returns
    recent: pd.Series = close_series.iloc[-21:]
    log_returns: pd.Series = pd.Series(
        np.log(recent.to_numpy() / recent.shift(1).to_numpy()),
        index=recent.index,
    ).dropna()

    if len(log_returns) < 20:
        return None

    std = float(log_returns.std(ddof=1))
    if not math.isfinite(std):
        return None

    hv = std * math.sqrt(252)
    return hv if math.isfinite(hv) else None


def compute_iv_term_slope(
    iv_60d: float | None,
    iv_30d: float | None,
) -> float | None:
    """IV term structure slope: (IV_60d - IV_30d) / IV_30d.

    Positive = contango (normal: longer-dated IV higher).
    Negative = backwardation (inverted: near-term IV elevated, often pre-event).

    Reference: Sinclair (2013) "Volatility Trading", Ch. 8.

    Args:
        iv_60d: 60-day ATM implied volatility.
        iv_30d: 30-day ATM implied volatility.

    Returns:
        Term structure slope as float, or ``None`` if inputs are unavailable
        or iv_30d is zero/non-finite.
    """
    if iv_60d is None or iv_30d is None:
        return None
    if not math.isfinite(iv_60d) or not math.isfinite(iv_30d):
        return None
    if iv_30d == 0.0:
        return None
    slope = (iv_60d - iv_30d) / iv_30d
    return slope if math.isfinite(slope) else None


def compute_iv_term_shape(slope: float | None) -> IVTermStructureShape | None:
    """Classify IV term structure shape from slope.

    Thresholds:
        - slope > 0.02: CONTANGO (normal upward-sloping)
        - slope < -0.02: BACKWARDATION (inverted, near-term elevated)
        - -0.02 <= slope <= 0.02: FLAT

    Args:
        slope: IV term structure slope from ``compute_iv_term_slope()``.

    Returns:
        ``IVTermStructureShape`` enum value, or ``None`` if slope is unavailable.
    """
    if slope is None:
        return None
    if not math.isfinite(slope):
        return None
    if slope > 0.02:
        return IVTermStructureShape.CONTANGO
    if slope < -0.02:
        return IVTermStructureShape.BACKWARDATION
    return IVTermStructureShape.FLAT


def compute_put_skew(
    iv_25d_put: float | None,
    iv_atm: float | None,
) -> float | None:
    """Put skew index: (IV_25delta_put - IV_ATM) / IV_ATM.

    Positive values indicate OTM puts are more expensive relative to ATM,
    which is the normal state (protective put demand).

    Reference: Bollen & Whaley (2004) "Does Net Buying Pressure Affect the
    Shape of Implied Volatility Functions?"

    Args:
        iv_25d_put: IV at 25-delta put.
        iv_atm: ATM implied volatility.

    Returns:
        Put skew index as float, or ``None`` if inputs are unavailable.
    """
    if iv_25d_put is None or iv_atm is None:
        return None
    if not math.isfinite(iv_25d_put) or not math.isfinite(iv_atm):
        return None
    if iv_atm == 0.0:
        return None
    skew = (iv_25d_put - iv_atm) / iv_atm
    return skew if math.isfinite(skew) else None


def compute_call_skew(
    iv_25d_call: float | None,
    iv_atm: float | None,
) -> float | None:
    """Call skew index: (IV_25delta_call - IV_ATM) / IV_ATM.

    Positive = OTM calls expensive relative to ATM (rare, often pre-takeover).
    Negative = OTM calls cheaper than ATM (normal).

    Reference: Bollen & Whaley (2004).

    Args:
        iv_25d_call: IV at 25-delta call.
        iv_atm: ATM implied volatility.

    Returns:
        Call skew index as float, or ``None`` if inputs are unavailable.
    """
    if iv_25d_call is None or iv_atm is None:
        return None
    if not math.isfinite(iv_25d_call) or not math.isfinite(iv_atm):
        return None
    if iv_atm == 0.0:
        return None
    skew = (iv_25d_call - iv_atm) / iv_atm
    return skew if math.isfinite(skew) else None


def compute_skew_ratio(
    iv_25d_put: float | None,
    iv_25d_call: float | None,
) -> float | None:
    """Skew ratio: IV_25d_put / IV_25d_call.

    >1 = put skew dominant (normal for equity options).
    <1 = call skew dominant (unusual, potential upside fear).
    =1 = symmetric smile.

    Reference: Sinclair (2013) "Volatility Trading", Ch. 6.

    Args:
        iv_25d_put: IV at 25-delta put.
        iv_25d_call: IV at 25-delta call.

    Returns:
        Skew ratio as float, or ``None`` if inputs are unavailable.
    """
    if iv_25d_put is None or iv_25d_call is None:
        return None
    if not math.isfinite(iv_25d_put) or not math.isfinite(iv_25d_call):
        return None
    if iv_25d_call == 0.0:
        return None
    ratio = iv_25d_put / iv_25d_call
    return ratio if math.isfinite(ratio) else None


def classify_vol_regime(iv_rank: float | None) -> VolRegime | None:
    """Classify volatility regime from IV rank.

    Thresholds:
        - iv_rank < 25: LOW
        - 25 <= iv_rank < 50: NORMAL
        - 50 <= iv_rank < 75: ELEVATED
        - iv_rank >= 75: EXTREME

    Reference: tastytrade/tastyworks volatility regime classifications.

    Args:
        iv_rank: IV rank as percentage (0-100).

    Returns:
        ``VolRegime`` enum value, or ``None`` if iv_rank is unavailable.
    """
    if iv_rank is None:
        return None
    if not math.isfinite(iv_rank):
        return None
    if iv_rank < 25.0:
        return VolRegime.LOW
    if iv_rank < 50.0:
        return VolRegime.NORMAL
    if iv_rank < 75.0:
        return VolRegime.ELEVATED
    return VolRegime.EXTREME


def compute_ewma_vol_forecast(
    returns: pd.Series,
    lambda_: float = 0.94,
) -> float | None:
    """EWMA volatility forecast (RiskMetrics methodology).

    Exponentially weighted moving average of squared returns, annualized.

    Formula:
        sigma^2_t = lambda * sigma^2_{t-1} + (1 - lambda) * r^2_{t-1}
        Annualized = sqrt(sigma^2_t * 252)

    Reference: JP Morgan RiskMetrics Technical Document (1996), lambda=0.94
    for daily data.

    Args:
        returns: Daily log returns series. Requires at least 20 data points.
        lambda_: Decay factor (0 < lambda < 1). Default 0.94 (RiskMetrics daily).

    Returns:
        Annualized EWMA volatility forecast, or ``None`` if insufficient data.
    """
    if len(returns) < 20:
        return None
    if not math.isfinite(lambda_) or not (0.0 < lambda_ < 1.0):
        return None

    clean = returns.dropna()
    if len(clean) < 20:
        return None

    # alpha = 1 - lambda for pandas ewm
    alpha = 1.0 - lambda_
    ewma_var = clean.pow(2).ewm(alpha=alpha, adjust=False).mean()

    # Take the last value as the forecast
    last_var = float(ewma_var.iloc[-1])
    if not math.isfinite(last_var) or last_var < 0.0:
        return None

    annualized = math.sqrt(last_var * 252)
    return annualized if math.isfinite(annualized) else None


def compute_vol_cone_pctl(
    hv_20d: float | None,
    hv_history: pd.Series,
) -> float | None:
    """Volatility cone percentile: where current HV sits in historical HV distribution.

    Percentile-based (count of historical values below current / total * 100).

    Reference: Natenberg (1994) "Option Volatility and Pricing", volatility cones.

    Args:
        hv_20d: Current 20-day historical volatility.
        hv_history: Historical series of 20-day HV values. Requires at least
            10 non-NaN observations.

    Returns:
        Percentile (0-100) of current HV in its historical distribution,
        or ``None`` if insufficient data.
    """
    if hv_20d is None:
        return None
    if not math.isfinite(hv_20d):
        return None

    clean = hv_history.dropna()
    if len(clean) < 10:
        return None

    count_below = int(np.sum(clean < hv_20d))
    pctl = float(count_below / len(clean) * 100.0)
    return pctl if math.isfinite(pctl) else None


def compute_vix_correlation(
    ticker_returns: pd.Series,
    vix_changes: pd.Series,
) -> float | None:
    """Rolling 60-day correlation between ticker returns and VIX changes.

    Most equities have negative correlation with VIX (market falls -> VIX rises).
    Stocks with weaker negative or positive VIX correlation may behave differently
    in vol spikes.

    Reference: Whaley (2009) "Understanding the VIX", Journal of Portfolio Management.

    Args:
        ticker_returns: Daily log returns for the ticker.
        vix_changes: Daily VIX percentage changes (or log changes).

    Returns:
        60-day rolling correlation (last value), or ``None`` if insufficient data
        or series lengths are mismatched.
    """
    if len(ticker_returns) < 60 or len(vix_changes) < 60:
        return None
    if len(ticker_returns) != len(vix_changes):
        return None

    # Use last 60 observations
    t_ret = ticker_returns.iloc[-60:]
    v_chg = vix_changes.iloc[-60:]

    # Drop pairs where either is NaN
    combined = pd.DataFrame({"t": t_ret.values, "v": v_chg.values}).dropna()
    if len(combined) < 30:
        return None

    corr = float(combined["t"].corr(combined["v"]))
    if not math.isfinite(corr):
        return None
    return corr


def compute_expected_move(
    spot: float,
    atm_iv: float | None,
    dte: int,
) -> float | None:
    """Expected move: spot * atm_iv * sqrt(dte / 365).

    This is the one-standard-deviation expected move of the underlying
    over the given time horizon, based on ATM implied volatility.

    Reference: CBOE expected move calculation.

    Args:
        spot: Current underlying price.
        atm_iv: ATM implied volatility (annualized, decimal).
        dte: Days to expiration.

    Returns:
        Expected move in price terms, or ``None`` if inputs are unavailable.
    """
    if atm_iv is None:
        return None
    if not math.isfinite(spot) or spot <= 0.0:
        return None
    if not math.isfinite(atm_iv) or atm_iv <= 0.0:
        return None
    if dte <= 0:
        return None

    em = spot * atm_iv * math.sqrt(dte / 365.0)
    return em if math.isfinite(em) else None


def compute_expected_move_ratio(
    iv_em: float | None,
    avg_actual_move: float | None,
) -> float | None:
    """Ratio of IV-implied expected move to average actual move.

    >1 = IV is overpricing actual moves (premium sellers favored).
    <1 = IV is underpricing actual moves (premium buyers favored).
    =1 = IV fairly prices actual moves.

    Reference: Sinclair (2013) "Volatility Trading", Ch. 11.

    Args:
        iv_em: IV-implied expected move (from ``compute_expected_move``).
        avg_actual_move: Average actual move over the same period.

    Returns:
        Expected move ratio as float, or ``None`` if inputs are unavailable.
    """
    if iv_em is None or avg_actual_move is None:
        return None
    if not math.isfinite(iv_em) or not math.isfinite(avg_actual_move):
        return None
    if avg_actual_move == 0.0:
        return None
    ratio = iv_em / avg_actual_move
    return ratio if math.isfinite(ratio) else None
