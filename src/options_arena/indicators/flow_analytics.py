"""Options flow analytics: GEX, OI concentration, unusual activity, max pain magnet,
dollar volume trend, flow anomaly detection.

Functions for options flow analysis take pandas DataFrames/Series in, return
``float | None`` or NamedTuple out. No Pydantic models, no API calls. Pure math.
"""

from __future__ import annotations

import logging
import math
from typing import Any, NamedTuple

import numpy as np
import pandas as pd

from options_arena.indicators._validation import validate_aligned

logger = logging.getLogger(__name__)

# Minimum rows required for Isolation Forest anomaly detection
_MIN_ANOMALY_ROWS: int = 20

# Feature names for the anomaly detection feature matrix
_ANOMALY_FEATURE_NAMES: list[str] = [
    "vol_oi_ratio",
    "log_call_put_vol_ratio",
    "vol_avg_ratio",
    "large_trade_concentration",
]


class FlowAnomalyResult(NamedTuple):
    """Output of Isolation Forest flow anomaly detection.

    Attributes:
        anomaly_score: Isolation Forest decision function score (negative = more anomalous).
        is_anomalous: True when score < 0 (sklearn convention).
        feature_contributions: Per-feature z-scores of the aggregated row vs population.
    """

    anomaly_score: float
    is_anomalous: bool
    feature_contributions: dict[str, float]


def _get_isolation_forest() -> Any:  # noqa: ANN401
    """Attempt to import ``IsolationForest`` from sklearn. Returns class or ``None``."""
    try:
        from sklearn.ensemble import IsolationForest

        return IsolationForest
    except ImportError:
        logger.info("scikit-learn not installed -- flow anomaly detection disabled")
        return None


def compute_gex(
    chain_calls: pd.DataFrame,
    chain_puts: pd.DataFrame,
    spot: float,
) -> float | None:
    """Net Gamma Exposure (GEX).

    GEX = sum(call_OI * call_gamma * 100 * spot) - sum(put_OI * put_gamma * 100 * spot)
    for strikes within +/- 10% of spot price.

    Positive GEX implies dealer long gamma (stabilising); negative implies dealer
    short gamma (amplifying moves).

    Args:
        chain_calls: DataFrame with ``openInterest`` and ``gamma`` columns.
        chain_puts: DataFrame with ``openInterest`` and ``gamma`` columns.
        spot: Current underlying price.

    Returns:
        Net GEX as float, or ``None`` if insufficient data.
    """
    if not math.isfinite(spot) or spot <= 0.0:
        return None

    required_cols = {"openInterest", "gamma"}
    if (
        chain_calls.empty
        or chain_puts.empty
        or not required_cols.issubset(chain_calls.columns)
        or not required_cols.issubset(chain_puts.columns)
    ):
        return None

    # Filter to ATM +/- 10 strikes for performance
    if "strike" in chain_calls.columns:
        calls = chain_calls[
            (chain_calls["strike"] >= spot * 0.9) & (chain_calls["strike"] <= spot * 1.1)
        ].copy()
    else:
        calls = chain_calls.copy()

    if "strike" in chain_puts.columns:
        puts = chain_puts[
            (chain_puts["strike"] >= spot * 0.9) & (chain_puts["strike"] <= spot * 1.1)
        ].copy()
    else:
        puts = chain_puts.copy()

    if calls.empty and puts.empty:
        return None

    call_gex = float(
        np.nansum(calls["openInterest"].to_numpy() * calls["gamma"].to_numpy() * 100.0 * spot)
    )
    put_gex = float(
        np.nansum(puts["openInterest"].to_numpy() * puts["gamma"].to_numpy() * 100.0 * spot)
    )

    result = call_gex - put_gex
    return result if math.isfinite(result) else None


def compute_oi_concentration(chain: pd.DataFrame) -> float | None:
    """OI concentration: max_strike_OI / total_OI.

    Higher values indicate more concentrated positioning at a single strike,
    which can act as a magnet or resistance level.

    Args:
        chain: DataFrame with ``openInterest`` column.

    Returns:
        Concentration ratio in [0, 1], or ``None`` if insufficient data.
    """
    if chain.empty or "openInterest" not in chain.columns:
        return None

    oi = chain["openInterest"].to_numpy(dtype=float)
    total_oi = float(np.nansum(oi))

    if total_oi == 0.0:
        return None

    max_oi = float(np.nanmax(oi))
    ratio = max_oi / total_oi
    return ratio if math.isfinite(ratio) else None


def compute_unusual_activity(chain: pd.DataFrame) -> float | None:
    """Unusual activity score: premium-weighted volume/OI for strikes where vol > 2x OI.

    Identifies smart-money or institutional flow by flagging strikes with
    unusually high volume relative to open interest. Weighting by premium
    (mid price) ensures high-value trades dominate the score.

    Args:
        chain: DataFrame with ``volume``, ``openInterest``, ``bid``, and ``ask`` columns.

    Returns:
        Unusual activity score as float (>= 0), or ``None`` if insufficient data.
    """
    required_cols = {"volume", "openInterest", "bid", "ask"}
    if chain.empty or not required_cols.issubset(chain.columns):
        return None

    vol = chain["volume"].to_numpy(dtype=float)
    oi = chain["openInterest"].to_numpy(dtype=float)
    bid = chain["bid"].to_numpy(dtype=float)
    ask = chain["ask"].to_numpy(dtype=float)
    mid = (bid + ask) / 2.0

    # Filter to unusual: volume > 2 * OI, and OI > 0 to avoid div-by-zero noise
    unusual_mask = (vol > 2.0 * oi) & (oi > 0)

    if not np.any(unusual_mask):
        return 0.0

    # Premium-weighted vol/OI ratio for unusual strikes
    # Guard against zero OI in the denominator (already filtered but be safe)
    safe_oi = np.where(oi[unusual_mask] == 0.0, np.nan, oi[unusual_mask])
    ratios = vol[unusual_mask] / safe_oi
    premiums = mid[unusual_mask]

    total_premium = float(np.nansum(premiums))
    if total_premium == 0.0:
        return 0.0

    weighted_score = float(np.nansum(ratios * premiums)) / total_premium
    return weighted_score


def compute_max_pain_magnet(spot: float, max_pain: float | None) -> float | None:
    """Max pain magnet strength: 1 - (|spot - max_pain| / spot).

    Closer to 1.0 means price is near max pain (stronger gravitational pull).
    Below 0.0 means spot is more than 100% away from max pain (extreme divergence).

    Args:
        spot: Current underlying price.
        max_pain: Max pain strike price, or ``None`` if not computed.

    Returns:
        Magnet strength as float, or ``None`` if max_pain is ``None`` or spot is zero.
    """
    if max_pain is None:
        return None

    if not math.isfinite(spot) or spot <= 0.0:
        return None
    if not math.isfinite(max_pain):
        return None

    distance = abs(spot - max_pain) / spot
    return 1.0 - distance


def compute_dollar_volume_trend(
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> float | None:
    """20-day slope of dollar volume (close x volume).

    Positive slope indicates increasing institutional flow; negative indicates
    waning interest.

    Args:
        close: Series of closing prices.
        volume: Series of volume values.
        period: Lookback window for slope calculation (default 20).

    Returns:
        Slope of dollar volume (float), or ``None`` if insufficient data.
    """
    validate_aligned(close, volume)

    if len(close) < period:
        return None

    dollar_vol = close * volume
    recent = dollar_vol.iloc[-period:].to_numpy(dtype=float)

    # Drop NaN values
    mask = np.isfinite(recent)
    if np.sum(mask) < 2:
        return None

    clean = recent[mask]
    x = np.arange(len(clean), dtype=float)

    # Linear regression slope via least squares
    x_mean = np.mean(x)
    y_mean = np.mean(clean)
    denom = float(np.sum((x - x_mean) ** 2))

    if denom == 0.0:
        return 0.0

    slope = float(np.sum((x - x_mean) * (clean - y_mean))) / denom
    return slope if math.isfinite(slope) else None


def _build_anomaly_features(
    chain: pd.DataFrame,
    avg_volume_20d: float | None,
) -> np.ndarray[Any, np.dtype[np.floating[Any]]] | None:
    """Build the 4-feature matrix for Isolation Forest anomaly detection.

    Features per-strike row:
        1. volume / open_interest ratio (capped at 10.0)
        2. log(call_volume / put_volume) ratio (log-transformed, signed)
        3. volume / 20-day average volume ratio
        4. large trade concentration: cumulative % of volume in top-5 strikes

    Returns None if required columns are missing or data is insufficient.
    """
    required_cols = {"volume", "openInterest"}
    if not required_cols.issubset(chain.columns):
        return None

    vol = chain["volume"].to_numpy(dtype=float)
    oi = chain["openInterest"].to_numpy(dtype=float)
    n = len(vol)

    # Feature 1: volume / OI ratio, capped at 10.0
    safe_oi = np.where(oi == 0.0, np.nan, oi)
    vol_oi_ratio = np.clip(vol / safe_oi, 0.0, 10.0)
    vol_oi_ratio = np.where(np.isfinite(vol_oi_ratio), vol_oi_ratio, 0.0)

    # Feature 2: log call/put volume ratio
    # If 'optionType' or 'contractType' column exists, compute per-strike;
    # otherwise use a uniform ratio of 1.0 (log(1) = 0)
    log_cp_ratio = np.zeros(n, dtype=float)
    type_col: str | None = None
    for candidate in ("optionType", "contractType", "type"):
        if candidate in chain.columns:
            type_col = candidate
            break

    if type_col is not None:
        types = chain[type_col].astype(str).str.lower()
        call_mask = types.isin(["call", "c"])
        put_mask = types.isin(["put", "p"])
        total_call_vol = float(np.nansum(vol[call_mask.to_numpy()]))
        total_put_vol = float(np.nansum(vol[put_mask.to_numpy()]))
        # Guard against zero denominator
        if total_put_vol > 0.0:
            ratio = total_call_vol / total_put_vol
        elif total_call_vol > 0.0:
            ratio = 10.0  # all calls, no puts — cap
        else:
            ratio = 1.0
        log_cp_ratio[:] = math.log(max(ratio, 1e-10))
    # else: stays 0.0 (neutral)

    # Feature 3: volume / 20d average volume
    if avg_volume_20d is not None and math.isfinite(avg_volume_20d) and avg_volume_20d > 0.0:
        vol_avg_ratio = vol / avg_volume_20d
    else:
        # Fallback: use per-strike median volume as proxy
        median_vol = float(np.nanmedian(vol))
        vol_avg_ratio = vol / median_vol if median_vol > 0.0 else np.ones(n, dtype=float)

    vol_avg_ratio = np.where(np.isfinite(vol_avg_ratio), vol_avg_ratio, 0.0)

    # Feature 4: large trade concentration — fraction of total volume in top-5 strikes
    total_vol = float(np.nansum(vol))
    if total_vol > 0.0:
        sorted_vol = np.sort(vol)[::-1]
        top5_vol = float(np.nansum(sorted_vol[:5]))
        concentration = np.full(n, top5_vol / total_vol, dtype=float)
    else:
        concentration = np.zeros(n, dtype=float)

    # Stack into (n, 4) feature matrix
    features = np.column_stack([vol_oi_ratio, log_cp_ratio, vol_avg_ratio, concentration])

    # Drop rows that are all NaN or all zero (uninformative)
    row_finite = np.all(np.isfinite(features), axis=1)
    features = features[row_finite]

    if len(features) < _MIN_ANOMALY_ROWS:
        return None

    return features


def detect_flow_anomalies(
    chain: pd.DataFrame,
    avg_volume_20d: float | None = None,
) -> FlowAnomalyResult | None:
    """Detect anomalous options flow patterns using Isolation Forest.

    Fits an Isolation Forest on a 4-feature matrix derived from the options chain:
        1. Volume/OI ratio (capped at 10.0)
        2. Log call/put volume ratio
        3. Volume / 20-day average volume ratio
        4. Large trade concentration (top-5 strikes)

    The anomaly score is the mean ``decision_function`` value across all chain rows.
    Negative scores indicate more anomalous flow patterns.

    Args:
        chain: Options chain DataFrame with at least ``volume`` and ``openInterest``
            columns. Optionally ``optionType`` for call/put classification.
        avg_volume_20d: Average daily volume over the last 20 trading days.
            Used to normalise volume. If ``None``, falls back to per-strike median.

    Returns:
        ``FlowAnomalyResult`` with anomaly score, flag, and feature contributions,
        or ``None`` if scikit-learn not installed, insufficient data (<20 rows),
        or feature extraction fails.

    Reference:
        Liu, F.T., Ting, K.M. and Zhou, Z.-H. (2008) "Isolation Forest",
        ICDM 2008, pp. 413-422.
    """
    if chain.empty:
        return None

    iso_forest_cls = _get_isolation_forest()
    if iso_forest_cls is None:
        return None

    features = _build_anomaly_features(chain, avg_volume_20d)
    if features is None:
        return None

    try:
        model = iso_forest_cls(
            contamination=0.1,
            n_estimators=100,
            random_state=42,
        )
        model.fit(features)

        # Decision function: negative = more anomalous
        scores = model.decision_function(features)
        anomaly_score = float(np.mean(scores))

        if not math.isfinite(anomaly_score):
            return None

        is_anomalous = anomaly_score < 0.0

        # Feature contributions via z-score deviation of the most anomalous row
        # vs the per-feature population statistics
        means = np.mean(features, axis=0)
        stds = np.std(features, axis=0)
        # Guard against zero std
        safe_stds = np.where(stds == 0.0, 1.0, stds)

        # Compute how much the most anomalous row deviates from the mean
        min_score_idx = int(np.argmin(scores))
        anomalous_row = features[min_score_idx]
        z_contributions = (anomalous_row - means) / safe_stds

        feature_contributions: dict[str, float] = {}
        for i, name in enumerate(_ANOMALY_FEATURE_NAMES):
            val = float(z_contributions[i])
            feature_contributions[name] = val if math.isfinite(val) else 0.0

        return FlowAnomalyResult(
            anomaly_score=anomaly_score,
            is_anomalous=is_anomalous,
            feature_contributions=feature_contributions,
        )

    except Exception:
        logger.warning("Flow anomaly detection failed", exc_info=True)
        return None
