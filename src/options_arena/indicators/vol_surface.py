"""Implied volatility surface analytics with tiered computation.

Tiered approach:
- **Tier 1 (fitted surface)**: ``SmoothBivariateSpline`` over log-moneyness x sqrt-time
  when >=6 contracts across >=2 unique DTEs.  Derives skew_25d, smile_curvature,
  atm_iv_30d/60d from spline evaluation.  Produces per-contract residuals and z-scores.
- **Tier 2 (standalone fallback)**: Finite-difference curvature, raw 25-delta extraction,
  nearest-ATM IV, Breeden-Litzenberger implied probability when chain is too sparse for
  a full surface fit.
- **Insufficient data**: Returns all-None ``VolSurfaceResult`` when <3 valid contracts.

Shared file: created by ``native-quant`` epic; extended by ``volatility-intelligence``.

Rules (indicators module):
- Pure numpy/scipy math.  No Pydantic models, no API calls, no I/O.
- ``math.isfinite()`` guard on all numeric outputs.
- Return ``None`` on insufficient data, never NaN or 0.0.

References:
- Breeden & Litzenberger (1978) "Prices of State-Contingent Claims Implicit in Option Prices"
- Gatheral (2006) "The Volatility Surface: A Practitioner's Guide"
"""

import logging
import math
from typing import NamedTuple

import numpy as np
from scipy.interpolate import SmoothBivariateSpline
from scipy.stats import norm as _norm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_CONTRACTS_TIER2: int = 3
_MIN_CONTRACTS_TIER1: int = 6
_MIN_UNIQUE_DTES_TIER1: int = 2
_ATM_MONEYNESS_TOL: float = 0.05  # 5% of spot
_25D_MONEYNESS_CALL: float = 0.05  # approximate log-moneyness for 25-delta call
_25D_MONEYNESS_PUT: float = -0.05  # approximate log-moneyness for 25-delta put


# ---------------------------------------------------------------------------
# VolSurfaceResult
# ---------------------------------------------------------------------------


class VolSurfaceResult(NamedTuple):
    """Result of volatility surface computation.

    Fields set to ``None`` when insufficient data prevents computation.
    ``fitted_ivs``, ``residuals``, ``z_scores``, ``r_squared`` are ``None``
    when the standalone fallback (Tier 2) is used instead of a fitted surface.

    ``fitted_strikes`` and ``fitted_dtes`` are the filtered arrays that
    correspond positionally to ``z_scores``.  Consumers MUST use these
    (not the original unfiltered arrays) for index lookups.
    """

    skew_25d: float | None
    smile_curvature: float | None
    prob_above_current: float | None
    atm_iv_30d: float | None
    atm_iv_60d: float | None
    fitted_ivs: np.ndarray | None
    residuals: np.ndarray | None
    z_scores: np.ndarray | None
    r_squared: float | None
    fitted_strikes: np.ndarray | None
    fitted_dtes: np.ndarray | None
    is_1d_fallback: bool
    is_standalone_fallback: bool


_NONE_RESULT = VolSurfaceResult(
    skew_25d=None,
    smile_curvature=None,
    prob_above_current=None,
    atm_iv_30d=None,
    atm_iv_60d=None,
    fitted_ivs=None,
    residuals=None,
    z_scores=None,
    r_squared=None,
    fitted_strikes=None,
    fitted_dtes=None,
    is_1d_fallback=False,
    is_standalone_fallback=False,
)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_vol_surface(
    strikes: np.ndarray,
    ivs: np.ndarray,
    dtes: np.ndarray,
    option_types: np.ndarray,
    spot: float,
    risk_free_rate: float = 0.05,
) -> VolSurfaceResult:
    """Compute implied volatility surface analytics with tiered fallback.

    Parameters
    ----------
    strikes
        Strike prices for each contract.
    ivs
        Implied volatilities (annualized, decimal) for each contract.
    dtes
        Days to expiration for each contract.
    option_types
        1.0 for call, -1.0 for put.
    spot
        Current underlying price.
    risk_free_rate
        Annualized risk-free rate (decimal).  Default 0.05.

    Returns
    -------
    VolSurfaceResult
        Surface analytics.  All fields ``None`` when data is insufficient.
    """
    if not math.isfinite(spot) or spot <= 0.0:
        return _NONE_RESULT
    if not math.isfinite(risk_free_rate):
        return _NONE_RESULT

    # ----- filter NaN/zero/non-finite IVs -----
    valid_mask = np.isfinite(ivs) & (ivs > 0.0) & np.isfinite(strikes) & np.isfinite(dtes)
    strikes_f = strikes[valid_mask]
    ivs_f = ivs[valid_mask]
    dtes_f = dtes[valid_mask]
    types_f = option_types[valid_mask]

    n_contracts = len(ivs_f)
    if n_contracts < _MIN_CONTRACTS_TIER2:
        return _NONE_RESULT

    unique_dtes = np.unique(dtes_f[dtes_f > 0])

    # ----- Tier 1: fitted surface -----
    if n_contracts >= _MIN_CONTRACTS_TIER1 and len(unique_dtes) >= _MIN_UNIQUE_DTES_TIER1:
        result = _fit_surface(strikes_f, ivs_f, dtes_f, types_f, spot, risk_free_rate)
        if result is not None:
            return result
        # Fall through to Tier 2 on spline failure
        logger.debug("Spline fit failed; falling back to standalone methods")

    # ----- Tier 2: standalone fallback -----
    skew = _standalone_skew_25d(strikes_f, ivs_f, types_f, spot)
    curvature = _standalone_smile_curvature(strikes_f, ivs_f, spot)
    atm_30 = _standalone_atm_iv(strikes_f, ivs_f, dtes_f, spot, target_dte=30)
    atm_60 = _standalone_atm_iv(strikes_f, ivs_f, dtes_f, spot, target_dte=60)
    prob = _standalone_implied_move(
        strikes_f,
        ivs_f,
        types_f,
        spot,
        risk_free_rate,
        dtes_f,
    )

    return VolSurfaceResult(
        skew_25d=skew,
        smile_curvature=curvature,
        prob_above_current=prob,
        atm_iv_30d=atm_30,
        atm_iv_60d=atm_60,
        fitted_ivs=None,
        residuals=None,
        z_scores=None,
        r_squared=None,
        fitted_strikes=None,
        fitted_dtes=None,
        is_1d_fallback=False,
        is_standalone_fallback=True,
    )


# ---------------------------------------------------------------------------
# Tier 1: Fitted surface via SmoothBivariateSpline
# ---------------------------------------------------------------------------


def _fit_surface(
    strikes: np.ndarray,
    ivs: np.ndarray,
    dtes: np.ndarray,
    option_types: np.ndarray,
    spot: float,
    risk_free_rate: float,
) -> VolSurfaceResult | None:
    """Fit IV surface via bivariate spline and extract analytics.

    Returns ``None`` if the spline fit fails (e.g. too few unique knots).
    """
    # Transform to log-moneyness and sqrt-time
    log_m = np.log(strikes / spot)
    sqrt_t = np.sqrt(dtes / 365.0)

    # Guard: need positive time dimension
    time_mask = sqrt_t > 0.0
    if np.sum(time_mask) < _MIN_CONTRACTS_TIER1:
        return None
    log_m = log_m[time_mask]
    sqrt_t = sqrt_t[time_mask]
    ivs_clean = ivs[time_mask]
    types_clean = option_types[time_mask]
    strikes_clean = strikes[time_mask]
    dtes_clean = dtes[time_mask]

    try:
        # SmoothBivariateSpline expects unstructured (x, y, z) triples
        spline = SmoothBivariateSpline(
            log_m,
            sqrt_t,
            ivs_clean,
            kx=3,
            ky=3,
        )
    except Exception:
        logger.debug("SmoothBivariateSpline fit failed", exc_info=True)
        return None

    def _eval(x: float, y: float) -> float:
        """Evaluate spline at a single (x, y) point."""
        return float(spline(np.array([x]), np.array([y]), grid=False)[0])

    # ----- Extract skew_25d from spline at 30-day horizon -----
    sqrt_t_30 = math.sqrt(30.0 / 365.0)
    try:
        iv_25d_put = _eval(_25D_MONEYNESS_PUT, sqrt_t_30)
        iv_25d_call = _eval(_25D_MONEYNESS_CALL, sqrt_t_30)
        skew_val = iv_25d_put - iv_25d_call
        skew_25d: float | None = skew_val if math.isfinite(skew_val) else None
    except Exception:
        logger.debug("Spline skew_25d extraction failed", exc_info=True)
        skew_25d = None

    # ----- Extract smile curvature (second derivative at ATM) -----
    curvature: float | None = None
    try:
        # Finite-difference second derivative of IV w.r.t. log-moneyness at ATM
        h = 0.01
        iv_minus = _eval(-h, sqrt_t_30)
        iv_center = _eval(0.0, sqrt_t_30)
        iv_plus = _eval(h, sqrt_t_30)
        curv_val = (iv_plus - 2.0 * iv_center + iv_minus) / (h * h)
        curvature = curv_val if math.isfinite(curv_val) else None
    except Exception:
        logger.debug("Spline smile curvature extraction failed", exc_info=True)
        curvature = None

    # ----- ATM IV at 30d and 60d -----
    atm_iv_30d: float | None = None
    try:
        val = _eval(0.0, sqrt_t_30)
        atm_iv_30d = val if math.isfinite(val) and val > 0.0 else None
    except Exception:
        logger.debug("Spline ATM IV 30d extraction failed", exc_info=True)

    atm_iv_60d: float | None = None
    try:
        sqrt_t_60 = math.sqrt(60.0 / 365.0)
        val = _eval(0.0, sqrt_t_60)
        atm_iv_60d = val if math.isfinite(val) and val > 0.0 else None
    except Exception:
        logger.debug("Spline ATM IV 60d extraction failed", exc_info=True)

    # ----- Fitted values, residuals, z-scores -----
    fitted_arr: np.ndarray | None = None
    resid_arr: np.ndarray | None = None
    z_arr: np.ndarray | None = None
    r_squared: float | None = None
    try:
        fitted_arr = np.array(
            [_eval(float(lm), float(st)) for lm, st in zip(log_m, sqrt_t, strict=True)],
            dtype=float,
        )
        resid_arr = ivs_clean - fitted_arr
        resid_std = float(np.std(resid_arr))
        if math.isfinite(resid_std) and resid_std > 0.0:
            z_arr = resid_arr / resid_std
        else:
            z_arr = np.zeros_like(resid_arr)

        # R-squared
        ss_res = float(np.sum(resid_arr**2))
        ss_tot = float(np.sum((ivs_clean - np.mean(ivs_clean)) ** 2))
        if math.isfinite(ss_tot) and ss_tot > 0.0:
            r2 = 1.0 - ss_res / ss_tot
            r_squared = r2 if math.isfinite(r2) else None
    except Exception:
        logger.debug("Fitted values computation failed", exc_info=True)
        fitted_arr = None
        resid_arr = None
        z_arr = None
        r_squared = None

    # ----- Breeden-Litzenberger prob_above_current -----
    prob = _standalone_implied_move(
        strikes_clean,
        ivs_clean,
        types_clean,
        spot,
        risk_free_rate,
        dtes_clean,
    )

    return VolSurfaceResult(
        skew_25d=skew_25d,
        smile_curvature=curvature,
        prob_above_current=prob,
        atm_iv_30d=atm_iv_30d,
        atm_iv_60d=atm_iv_60d,
        fitted_ivs=fitted_arr,
        residuals=resid_arr,
        z_scores=z_arr,
        r_squared=r_squared,
        fitted_strikes=strikes_clean,
        fitted_dtes=dtes_clean,
        is_1d_fallback=False,
        is_standalone_fallback=False,
    )


# ---------------------------------------------------------------------------
# Tier 2: Standalone fallback functions
# ---------------------------------------------------------------------------


def _standalone_skew_25d(
    strikes: np.ndarray,
    ivs: np.ndarray,
    option_types: np.ndarray,
    spot: float,
) -> float | None:
    """Compute 25-delta skew from raw chain data.

    Finds the nearest OTM put and OTM call at ~25-delta moneyness
    (approximately 5% OTM) and returns ``IV_25d_put - IV_25d_call``.
    Typically negative (put IV > call IV is normal equity skew, but we
    report the signed difference which is positive when put IV > call IV).

    Returns ``None`` if suitable contracts cannot be found.
    """
    if len(strikes) < 2:
        return None

    moneyness = strikes / spot

    # 25-delta put ~ 0.90-0.98 moneyness (OTM put, strike < spot)
    put_mask = (option_types < 0.0) & (moneyness >= 0.85) & (moneyness <= 1.0)
    # 25-delta call ~ 1.02-1.10 moneyness (OTM call, strike > spot)
    call_mask = (option_types > 0.0) & (moneyness >= 1.0) & (moneyness <= 1.15)

    if not np.any(put_mask) or not np.any(call_mask):
        return None

    # Find contracts closest to 25-delta moneyness points
    put_strikes = moneyness[put_mask]
    put_ivs = ivs[put_mask]
    # Target moneyness for 25-delta put: ~0.95
    put_idx = int(np.argmin(np.abs(put_strikes - 0.95)))
    iv_25d_put = float(put_ivs[put_idx])

    call_strikes = moneyness[call_mask]
    call_ivs = ivs[call_mask]
    # Target moneyness for 25-delta call: ~1.05
    call_idx = int(np.argmin(np.abs(call_strikes - 1.05)))
    iv_25d_call = float(call_ivs[call_idx])

    if not math.isfinite(iv_25d_put) or not math.isfinite(iv_25d_call):
        return None

    skew = iv_25d_put - iv_25d_call
    return skew if math.isfinite(skew) else None


def _standalone_smile_curvature(
    strikes: np.ndarray,
    ivs: np.ndarray,
    spot: float,
) -> float | None:
    """Compute smile curvature via finite-difference second derivative at ATM.

    Finds ATM strike and its two nearest neighbors, then computes the
    centered second derivative: ``(IV(K+) - 2*IV(K_atm) + IV(K-)) / dK^2``
    where dK is in log-moneyness space.

    Positive curvature indicates a volatility smile (convex).

    Returns ``None`` if fewer than 3 unique strikes near ATM.
    """
    if len(strikes) < 3:
        return None
    if spot <= 0.0:
        return None

    # Deduplicate strikes by averaging IVs at the same strike
    unique_strikes, inverse_idx = np.unique(strikes, return_inverse=True)
    if len(unique_strikes) < 3:
        return None
    avg_ivs = np.zeros(len(unique_strikes), dtype=float)
    counts = np.zeros(len(unique_strikes), dtype=float)
    for i, idx in enumerate(inverse_idx):
        avg_ivs[idx] += ivs[i]
        counts[idx] += 1.0
    avg_ivs = avg_ivs / counts

    sorted_strikes = unique_strikes  # already sorted by np.unique
    sorted_ivs = avg_ivs

    # Find ATM index (closest strike to spot)
    atm_idx = int(np.argmin(np.abs(sorted_strikes - spot)))

    # Need at least one strike on each side
    if atm_idx == 0 or atm_idx == len(sorted_strikes) - 1:
        return None

    k_minus = sorted_strikes[atm_idx - 1]
    k_atm = sorted_strikes[atm_idx]
    k_plus = sorted_strikes[atm_idx + 1]

    iv_minus = sorted_ivs[atm_idx - 1]
    iv_atm = sorted_ivs[atm_idx]
    iv_plus = sorted_ivs[atm_idx + 1]

    # Log-moneyness differences
    log_k_minus = math.log(k_minus / spot)
    log_k_atm = math.log(k_atm / spot)
    log_k_plus = math.log(k_plus / spot)

    h1 = log_k_atm - log_k_minus
    h2 = log_k_plus - log_k_atm

    if h1 <= 0.0 or h2 <= 0.0:
        return None

    # Centered second derivative with possibly unequal spacing
    curvature = float(
        2.0 * (iv_plus / h2 - iv_atm * (1.0 / h1 + 1.0 / h2) + iv_minus / h1) / (h1 + h2)
    )

    return curvature if math.isfinite(curvature) else None


def _standalone_atm_iv(
    strikes: np.ndarray,
    ivs: np.ndarray,
    dtes: np.ndarray,
    spot: float,
    target_dte: int,
) -> float | None:
    """Find ATM IV for the nearest expiration to ``target_dte``.

    Filters to contracts within ``_ATM_MONEYNESS_TOL`` of spot and within
    the DTE bucket ``[target_dte * 0.5, target_dte * 1.5]``.

    Returns ``None`` if no suitable contract exists.
    """
    if len(strikes) == 0:
        return None

    dte_low = target_dte * 0.5
    dte_high = target_dte * 1.5

    moneyness_dist = np.abs(strikes - spot) / spot
    dte_mask = (dtes >= dte_low) & (dtes <= dte_high)
    atm_mask = moneyness_dist <= _ATM_MONEYNESS_TOL

    combined = dte_mask & atm_mask
    if not np.any(combined):
        return None

    # Among matching contracts, pick the one closest to ATM
    candidates_dist = moneyness_dist[combined]
    candidates_iv = ivs[combined]
    best_idx = int(np.argmin(candidates_dist))
    result = float(candidates_iv[best_idx])

    if not math.isfinite(result) or result <= 0.0:
        return None

    return result


def _standalone_implied_move(
    strikes: np.ndarray,
    ivs: np.ndarray,
    option_types: np.ndarray,
    spot: float,
    risk_free_rate: float,
    dtes: np.ndarray,
) -> float | None:
    """Compute probability of spot being above current price via Breeden-Litzenberger.

    Uses the butterfly spread approximation to extract the risk-neutral
    probability density: ``f(K) ~ e^(rT) * [C(K-dK) - 2C(K) + C(K+dK)] / dK^2``
    then integrates the CDF via trapezoidal rule.

    Reference: Breeden & Litzenberger (1978).

    Returns ``None`` if fewer than 3 call contracts at a single expiration.
    """
    # Use calls only, at the most populated expiration
    call_mask = option_types > 0.0
    if np.sum(call_mask) < 3:
        return None

    call_strikes = strikes[call_mask]
    call_ivs = ivs[call_mask]
    call_dtes = dtes[call_mask]

    # Find the most populated expiration
    unique_exp, counts = np.unique(call_dtes, return_counts=True)
    best_exp_idx = int(np.argmax(counts))
    target_dte = unique_exp[best_exp_idx]

    if target_dte <= 0:
        return None

    exp_mask = call_dtes == target_dte
    if np.sum(exp_mask) < 3:
        return None

    exp_strikes = call_strikes[exp_mask]
    exp_ivs = call_ivs[exp_mask]

    # Sort by strike
    sort_idx = np.argsort(exp_strikes)
    k = exp_strikes[sort_idx]
    iv = exp_ivs[sort_idx]

    t = float(target_dte) / 365.0
    discount = math.exp(risk_free_rate * t)

    # Compute call prices via BSM for the butterfly spread
    n_strikes = len(k)
    call_prices = np.empty(n_strikes, dtype=float)
    for i in range(n_strikes):
        sigma = float(iv[i])
        strike = float(k[i])
        if sigma <= 0.0 or strike <= 0.0:
            call_prices[i] = 0.0
            continue
        d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * sigma * sigma) * t) / (
            sigma * math.sqrt(t)
        )
        d2 = d1 - sigma * math.sqrt(t)
        call_prices[i] = spot * float(_norm.cdf(d1)) - strike * math.exp(
            -risk_free_rate * t
        ) * float(_norm.cdf(d2))

    # Approximate risk-neutral PDF via second derivative of call prices w.r.t. strike
    if n_strikes < 3:
        return None

    pdf_k = np.empty(n_strikes - 2, dtype=float)
    pdf_strikes = np.empty(n_strikes - 2, dtype=float)

    for i in range(1, n_strikes - 1):
        h1 = float(k[i] - k[i - 1])
        h2 = float(k[i + 1] - k[i])
        if h1 <= 0.0 or h2 <= 0.0:
            pdf_k[i - 1] = 0.0
            pdf_strikes[i - 1] = float(k[i])
            continue
        # Unequal-spacing centered second derivative (Breeden-Litzenberger)
        d2c = (
            2.0
            * (
                call_prices[i + 1] / h2
                - call_prices[i] * (1.0 / h1 + 1.0 / h2)
                + call_prices[i - 1] / h1
            )
            / (h1 + h2)
        )
        pdf_k[i - 1] = max(0.0, discount * d2c)
        pdf_strikes[i - 1] = float(k[i])

    # Integrate: P(S > spot) = 1 - CDF(spot)
    # CDF(K) = integral from -inf to K of pdf
    total_mass = float(np.trapezoid(pdf_k, pdf_strikes))
    if total_mass <= 0.0 or not math.isfinite(total_mass):
        return None

    # Normalize PDF
    pdf_normalized = pdf_k / total_mass

    # CDF at spot
    below_spot = pdf_strikes <= spot
    if not np.any(below_spot):
        # All strikes above spot -> prob_above ~ 1
        return 1.0
    if np.all(below_spot):
        # All strikes below spot -> prob_above ~ 0
        return 0.0

    cdf_at_spot = float(np.trapezoid(pdf_normalized[below_spot], pdf_strikes[below_spot]))

    prob = 1.0 - cdf_at_spot
    if not math.isfinite(prob):
        return None

    # Clamp to [0, 1]
    return max(0.0, min(1.0, prob))


# ---------------------------------------------------------------------------
# Stub for volatility-intelligence epic
# ---------------------------------------------------------------------------


class VolSurfaceIndicators(NamedTuple):
    """Indicator signals derived from fitted vol surface.

    Fields:
        iv_surface_residual: z-score of the contract's IV versus the fitted
            surface.  Positive means the contract is "cheap" (IV below surface);
            negative means "expensive".  ``None`` when the contract cannot be
            located in the surface arrays or when the surface is a standalone
            fallback.
        surface_fit_r2: R-squared of the surface fit, in ``[0, 1]``.  ``None``
            when no fitted surface is available.
        surface_is_1d: ``True`` when a single-DTE 1-D fallback was used instead
            of the full 2-D spline.  ``None`` when the surface result is
            insufficient.
    """

    iv_surface_residual: float | None = None
    surface_fit_r2: float | None = None
    surface_is_1d: bool | None = None


def compute_surface_indicators(
    result: VolSurfaceResult,
    contract_strike: float,
    contract_dte: float,
    strikes: np.ndarray | None = None,
    dtes: np.ndarray | None = None,
) -> VolSurfaceIndicators:
    """Map per-contract z-scores from fitted surface to indicator signals.

    Parameters
    ----------
    result
        Output of :func:`compute_vol_surface`.
    contract_strike
        Strike price of the contract to look up.
    contract_dte
        Days-to-expiration of the contract to look up.
    strikes
        Deprecated — ignored.  Uses ``result.fitted_strikes`` instead.
    dtes
        Deprecated — ignored.  Uses ``result.fitted_dtes`` instead.

    Returns
    -------
    VolSurfaceIndicators
        Surface-derived indicators for the contract.  All ``None`` when the
        surface result is a standalone fallback or has no z-scores.
    """
    if result.is_standalone_fallback or result.z_scores is None:
        return VolSurfaceIndicators()

    # Use the filtered arrays stored alongside z_scores for correct indexing
    fit_strikes = result.fitted_strikes
    fit_dtes = result.fitted_dtes
    if fit_strikes is None or fit_dtes is None:
        return VolSurfaceIndicators(
            surface_fit_r2=result.r_squared,
            surface_is_1d=result.is_1d_fallback,
        )

    # Find the index where strikes[i] ≈ contract_strike AND dtes[i] ≈ contract_dte
    strike_match = np.isclose(fit_strikes, contract_strike)
    dte_match = np.isclose(fit_dtes, contract_dte)
    combined_mask = strike_match & dte_match

    matching_indices = np.flatnonzero(combined_mask)

    if len(matching_indices) > 0:
        idx = int(matching_indices[0])
        z_score = float(result.z_scores[idx])
        residual: float | None = z_score if math.isfinite(z_score) else None
        return VolSurfaceIndicators(
            iv_surface_residual=residual,
            surface_fit_r2=result.r_squared,
            surface_is_1d=result.is_1d_fallback,
        )

    # No matching contract found — still return R² and is_1d
    return VolSurfaceIndicators(
        iv_surface_residual=None,
        surface_fit_r2=result.r_squared,
        surface_is_1d=result.is_1d_fallback,
    )
