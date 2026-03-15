"""Audit test configuration — function registry and Hypothesis profiles.

``MATH_FUNCTION_REGISTRY`` maps all 87 mathematical functions in the codebase
to their callables for audit testing. Hypothesis profiles control example
count for property-based stability tests.
"""

from __future__ import annotations

import os
from typing import Any

from hypothesis import settings

# ---------------------------------------------------------------------------
# Hypothesis profiles
# ---------------------------------------------------------------------------

settings.register_profile("ci", max_examples=100)
settings.register_profile("thorough", max_examples=1000)

_active_profile = os.environ.get("HYPOTHESIS_PROFILE", "ci")
settings.load_profile(_active_profile)

# ---------------------------------------------------------------------------
# Lazy imports — resolved at first access via _build_registry()
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, Any] | None = None


def _build_registry() -> dict[str, Any]:
    """Build the math function registry by importing all 87 functions."""
    # -- Pricing: BSM (5) --
    # -- Indicators: Flow Analytics (5) --
    # -- Orchestration (5) --
    from options_arena.agents._parsing import compute_citation_density
    from options_arena.agents.orchestrator import (
        _get_majority_direction,
        _log_odds_pool,
        _vote_entropy,
        compute_agreement_score,
    )
    from options_arena.indicators.flow_analytics import (
        compute_dollar_volume_trend,
        compute_gex,
        compute_max_pain_magnet,
        compute_oi_concentration,
        compute_unusual_activity,
    )

    # -- Indicators: HV Estimators (3) --
    from options_arena.indicators.hv_estimators import (
        compute_hv_parkinson,
        compute_hv_rogers_satchell,
        compute_hv_yang_zhang,
    )

    # -- Indicators: IV Analytics (13) --
    from options_arena.indicators.iv_analytics import (
        classify_vol_regime,
        compute_call_skew,
        compute_ewma_vol_forecast,
        compute_expected_move,
        compute_expected_move_ratio,
        compute_hv_20d,
        compute_iv_hv_spread,
        compute_iv_term_shape,
        compute_iv_term_slope,
        compute_put_skew,
        compute_skew_ratio,
        compute_vix_correlation,
        compute_vol_cone_pctl,
    )

    # -- Indicators: Moving Averages (2) --
    from options_arena.indicators.moving_averages import sma_alignment, vwap_deviation

    # -- Indicators: Options Specific (9) --
    from options_arena.indicators.options_specific import (
        compute_max_loss_ratio,
        compute_optimal_dte,
        compute_pop,
        compute_spread_quality,
        iv_percentile,
        iv_rank,
        max_pain,
        put_call_ratio_oi,
        put_call_ratio_volume,
    )

    # -- Indicators: Oscillators (3) --
    from options_arena.indicators.oscillators import rsi, stoch_rsi, williams_r

    # -- Indicators: Regime (7) --
    from options_arena.indicators.regime import (
        classify_market_regime,
        compute_correlation_regime_shift,
        compute_risk_on_off,
        compute_rs_vs_spx,
        compute_sector_momentum,
        compute_vix_term_structure,
        compute_volume_profile_skew,
    )

    # -- Indicators: Trend (7) --
    from options_arena.indicators.trend import (
        adx,
        compute_adx_exhaustion,
        compute_multi_tf_alignment,
        compute_rsi_divergence,
        macd,
        roc,
        supertrend,
    )

    # -- Indicators: Vol Surface (2) --
    from options_arena.indicators.vol_surface import (
        compute_surface_indicators,
        compute_vol_surface,
    )

    # -- Indicators: Volatility (3) --
    from options_arena.indicators.volatility import atr_percent, bb_width, keltner_width

    # -- Indicators: Volume (3) --
    from options_arena.indicators.volume import ad_trend, obv_trend, relative_volume

    # -- Pricing: Common (1) --
    from options_arena.pricing._common import intrinsic_value

    # -- Pricing: American / BAW (4) --
    from options_arena.pricing.american import (
        american_greeks,
        american_iv,
        american_price,
        american_second_order_greeks,
    )
    from options_arena.pricing.bsm import (
        bsm_greeks,
        bsm_iv,
        bsm_price,
        bsm_second_order_greeks,
        bsm_vega,
    )

    # -- Pricing: Dispatch (4) --
    from options_arena.pricing.dispatch import (
        option_greeks,
        option_iv,
        option_price,
        option_second_order_greeks,
    )

    # -- Scoring: Composite (2) --
    from options_arena.scoring.composite import composite_score, score_universe

    # -- Scoring: Contracts (5) --
    from options_arena.scoring.contracts import (
        compute_greeks,
        filter_contracts,
        recommend_contracts,
        select_by_delta,
        select_expiration,
    )

    # -- Scoring: Dimensional (3) --
    from options_arena.scoring.dimensional import (
        apply_regime_weights,
        compute_dimensional_scores,
        compute_direction_signal,
    )

    # -- Scoring: Direction (1) --
    from options_arena.scoring.direction import determine_direction

    # -- Scoring: Normalization (5) --
    from options_arena.scoring.normalization import (
        compute_normalization_stats,
        get_active_indicators,
        invert_indicators,
        normalize_single_ticker,
        percentile_rank_normalize,
    )

    return {
        # ---- Pricing: BSM (5) ----
        "pricing.bsm.bsm_price": bsm_price,
        "pricing.bsm.bsm_greeks": bsm_greeks,
        "pricing.bsm.bsm_vega": bsm_vega,
        "pricing.bsm.bsm_iv": bsm_iv,
        "pricing.bsm.bsm_second_order_greeks": bsm_second_order_greeks,
        # ---- Pricing: American / BAW (4) ----
        "pricing.american.american_price": american_price,
        "pricing.american.american_greeks": american_greeks,
        "pricing.american.american_iv": american_iv,
        "pricing.american.american_second_order_greeks": american_second_order_greeks,
        # ---- Pricing: Dispatch (4) ----
        "pricing.dispatch.option_price": option_price,
        "pricing.dispatch.option_greeks": option_greeks,
        "pricing.dispatch.option_iv": option_iv,
        "pricing.dispatch.option_second_order_greeks": option_second_order_greeks,
        # ---- Pricing: Common (1) ----
        "pricing._common.intrinsic_value": intrinsic_value,
        # ---- Indicators: Oscillators (3) ----
        "indicators.oscillators.rsi": rsi,
        "indicators.oscillators.stoch_rsi": stoch_rsi,
        "indicators.oscillators.williams_r": williams_r,
        # ---- Indicators: Trend (7) ----
        "indicators.trend.roc": roc,
        "indicators.trend.adx": adx,
        "indicators.trend.supertrend": supertrend,
        "indicators.trend.macd": macd,
        "indicators.trend.compute_multi_tf_alignment": compute_multi_tf_alignment,
        "indicators.trend.compute_rsi_divergence": compute_rsi_divergence,
        "indicators.trend.compute_adx_exhaustion": compute_adx_exhaustion,
        # ---- Indicators: Volatility (3) ----
        "indicators.volatility.bb_width": bb_width,
        "indicators.volatility.atr_percent": atr_percent,
        "indicators.volatility.keltner_width": keltner_width,
        # ---- Indicators: Volume (3) ----
        "indicators.volume.obv_trend": obv_trend,
        "indicators.volume.relative_volume": relative_volume,
        "indicators.volume.ad_trend": ad_trend,
        # ---- Indicators: Moving Averages (2) ----
        "indicators.moving_averages.sma_alignment": sma_alignment,
        "indicators.moving_averages.vwap_deviation": vwap_deviation,
        # ---- Indicators: Options Specific (9) ----
        "indicators.options_specific.iv_rank": iv_rank,
        "indicators.options_specific.iv_percentile": iv_percentile,
        "indicators.options_specific.put_call_ratio_volume": put_call_ratio_volume,
        "indicators.options_specific.put_call_ratio_oi": put_call_ratio_oi,
        "indicators.options_specific.max_pain": max_pain,
        "indicators.options_specific.compute_pop": compute_pop,
        "indicators.options_specific.compute_optimal_dte": compute_optimal_dte,
        "indicators.options_specific.compute_spread_quality": compute_spread_quality,
        "indicators.options_specific.compute_max_loss_ratio": compute_max_loss_ratio,
        # ---- Indicators: IV Analytics (13) ----
        "indicators.iv_analytics.compute_iv_hv_spread": compute_iv_hv_spread,
        "indicators.iv_analytics.compute_hv_20d": compute_hv_20d,
        "indicators.iv_analytics.compute_iv_term_slope": compute_iv_term_slope,
        "indicators.iv_analytics.compute_iv_term_shape": compute_iv_term_shape,
        "indicators.iv_analytics.compute_put_skew": compute_put_skew,
        "indicators.iv_analytics.compute_call_skew": compute_call_skew,
        "indicators.iv_analytics.compute_skew_ratio": compute_skew_ratio,
        "indicators.iv_analytics.classify_vol_regime": classify_vol_regime,
        "indicators.iv_analytics.compute_ewma_vol_forecast": compute_ewma_vol_forecast,
        "indicators.iv_analytics.compute_vol_cone_pctl": compute_vol_cone_pctl,
        "indicators.iv_analytics.compute_vix_correlation": compute_vix_correlation,
        "indicators.iv_analytics.compute_expected_move": compute_expected_move,
        "indicators.iv_analytics.compute_expected_move_ratio": compute_expected_move_ratio,
        # ---- Indicators: HV Estimators (3) ----
        "indicators.hv_estimators.compute_hv_parkinson": compute_hv_parkinson,
        "indicators.hv_estimators.compute_hv_rogers_satchell": compute_hv_rogers_satchell,
        "indicators.hv_estimators.compute_hv_yang_zhang": compute_hv_yang_zhang,
        # ---- Indicators: Flow Analytics (5) ----
        "indicators.flow_analytics.compute_gex": compute_gex,
        "indicators.flow_analytics.compute_oi_concentration": compute_oi_concentration,
        "indicators.flow_analytics.compute_unusual_activity": compute_unusual_activity,
        "indicators.flow_analytics.compute_max_pain_magnet": compute_max_pain_magnet,
        "indicators.flow_analytics.compute_dollar_volume_trend": compute_dollar_volume_trend,
        # ---- Indicators: Regime (7) ----
        "indicators.regime.classify_market_regime": classify_market_regime,
        "indicators.regime.compute_vix_term_structure": compute_vix_term_structure,
        "indicators.regime.compute_risk_on_off": compute_risk_on_off,
        "indicators.regime.compute_sector_momentum": compute_sector_momentum,
        "indicators.regime.compute_rs_vs_spx": compute_rs_vs_spx,
        "indicators.regime.compute_correlation_regime_shift": compute_correlation_regime_shift,
        "indicators.regime.compute_volume_profile_skew": compute_volume_profile_skew,
        # ---- Indicators: Vol Surface (2) ----
        "indicators.vol_surface.compute_vol_surface": compute_vol_surface,
        "indicators.vol_surface.compute_surface_indicators": compute_surface_indicators,
        # ---- Scoring: Normalization (5) ----
        "scoring.normalization.percentile_rank_normalize": percentile_rank_normalize,
        "scoring.normalization.invert_indicators": invert_indicators,
        "scoring.normalization.normalize_single_ticker": normalize_single_ticker,
        "scoring.normalization.get_active_indicators": get_active_indicators,
        "scoring.normalization.compute_normalization_stats": compute_normalization_stats,
        # ---- Scoring: Composite (2) ----
        "scoring.composite.composite_score": composite_score,
        "scoring.composite.score_universe": score_universe,
        # ---- Scoring: Direction (1) ----
        "scoring.direction.determine_direction": determine_direction,
        # ---- Scoring: Dimensional (3) ----
        "scoring.dimensional.compute_dimensional_scores": compute_dimensional_scores,
        "scoring.dimensional.apply_regime_weights": apply_regime_weights,
        "scoring.dimensional.compute_direction_signal": compute_direction_signal,
        # ---- Scoring: Contracts (5) ----
        "scoring.contracts.filter_contracts": filter_contracts,
        "scoring.contracts.select_expiration": select_expiration,
        "scoring.contracts.compute_greeks": compute_greeks,
        "scoring.contracts.select_by_delta": select_by_delta,
        "scoring.contracts.recommend_contracts": recommend_contracts,
        # ---- Orchestration (5) ----
        "orchestration.compute_agreement_score": compute_agreement_score,
        "orchestration._vote_entropy": _vote_entropy,
        "orchestration._log_odds_pool": _log_odds_pool,
        "orchestration.compute_citation_density": compute_citation_density,
        "orchestration._get_majority_direction": _get_majority_direction,
    }


def get_math_function_registry() -> dict[str, Any]:
    """Return the math function registry, building it on first access."""
    global _REGISTRY  # noqa: PLW0603
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


# Eagerly build at import time so tests can reference it directly.
MATH_FUNCTION_REGISTRY: dict[str, Any] = _build_registry()
