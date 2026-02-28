"""Dimensional scoring engine for the Deep Signal Engine.

Computes 8 per-family sub-scores from IndicatorSignals using weighted
mean scoped per family.  Supports regime-adjusted weights.

Family scores are simple arithmetic means of non-None indicator values
within each family, producing a 0--100 scale score per family.
"""

import logging
import math

from options_arena.models.enums import MarketRegime, SignalDirection
from options_arena.models.scan import IndicatorSignals
from options_arena.models.scoring import DimensionalScores, DirectionSignal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Family -> indicator field names mapping
# ---------------------------------------------------------------------------

FAMILY_INDICATOR_MAP: dict[str, list[str]] = {
    "trend": [
        "rsi",
        "stochastic_rsi",
        "williams_r",
        "adx",
        "roc",
        "supertrend",
        "sma_alignment",
        "multi_tf_alignment",
        "rsi_divergence",
        "adx_exhaustion",
        "rs_vs_spx",
    ],
    "iv_vol": [
        "iv_rank",
        "iv_percentile",
        "iv_hv_spread",
        "hv_20d",
        "iv_term_slope",
        "iv_term_shape",
        "vol_regime",
        "ewma_vol_forecast",
        "vol_cone_percentile",
        "vix_correlation",
        "put_skew_index",
        "call_skew_index",
        "skew_ratio",
        "expected_move",
        "expected_move_ratio",
    ],
    "hv_vol": [
        "bb_width",
        "atr_pct",
        "keltner_width",
    ],
    "flow": [
        "put_call_ratio",
        "max_pain_distance",
        "gex",
        "oi_concentration",
        "unusual_activity_score",
        "max_pain_magnet",
        "dollar_volume_trend",
    ],
    "microstructure": [
        "obv",
        "ad",
        "relative_volume",
        "vwap_deviation",
        "spread_quality",
        "volume_profile_skew",
    ],
    "fundamental": [
        "earnings_em_ratio",
        "days_to_earnings_impact",
        "short_interest_ratio",
        "div_ex_date_impact",
        "iv_crush_history",
    ],
    "regime": [
        "market_regime",
        "vix_term_structure",
        "risk_on_off_score",
        "sector_relative_momentum",
        "correlation_regime_shift",
    ],
    "risk": [
        "pop",
        "optimal_dte_score",
        "max_loss_ratio",
        "vanna",
        "charm",
        "vomma",
    ],
}

# All 8 family names, for iteration and validation.
_FAMILY_NAMES: tuple[str, ...] = (
    "trend",
    "iv_vol",
    "hv_vol",
    "flow",
    "microstructure",
    "fundamental",
    "regime",
    "risk",
)

# ---------------------------------------------------------------------------
# Default weights (sum to 1.0)
# ---------------------------------------------------------------------------

DEFAULT_FAMILY_WEIGHTS: dict[str, float] = {
    "trend": 0.22,
    "iv_vol": 0.20,
    "flow": 0.18,
    "hv_vol": 0.05,
    "microstructure": 0.08,
    "fundamental": 0.10,
    "regime": 0.07,
    "risk": 0.10,
}

# ---------------------------------------------------------------------------
# Regime-adjusted weight profiles (4 regimes)
# ---------------------------------------------------------------------------

REGIME_WEIGHT_PROFILES: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.TRENDING: {
        "trend": 0.30,
        "iv_vol": 0.15,
        "flow": 0.15,
        "hv_vol": 0.05,
        "microstructure": 0.08,
        "fundamental": 0.10,
        "regime": 0.07,
        "risk": 0.10,
    },
    MarketRegime.MEAN_REVERTING: {
        "trend": 0.15,
        "iv_vol": 0.25,
        "flow": 0.15,
        "hv_vol": 0.08,
        "microstructure": 0.10,
        "fundamental": 0.10,
        "regime": 0.07,
        "risk": 0.10,
    },
    MarketRegime.VOLATILE: {
        "trend": 0.15,
        "iv_vol": 0.25,
        "flow": 0.20,
        "hv_vol": 0.05,
        "microstructure": 0.05,
        "fundamental": 0.08,
        "regime": 0.07,
        "risk": 0.15,
    },
    MarketRegime.CRISIS: {
        "trend": 0.10,
        "iv_vol": 0.15,
        "flow": 0.15,
        "hv_vol": 0.05,
        "microstructure": 0.05,
        "fundamental": 0.05,
        "regime": 0.15,
        "risk": 0.30,
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_dimensional_scores(signals: IndicatorSignals) -> DimensionalScores:
    """Compute 8 per-family sub-scores from IndicatorSignals.

    For each family:
    - Collect non-None, finite indicator values from the family's fields.
    - If ALL are None/non-finite, the family score is ``None``.
    - Otherwise, compute the arithmetic mean of the valid values (0--100 scale).

    Args:
        signals: Indicator signals (percentile-ranked, 0--100).

    Returns:
        Frozen ``DimensionalScores`` with 8 family sub-scores.
    """
    family_scores: dict[str, float | None] = {}

    for family in _FAMILY_NAMES:
        indicator_fields = FAMILY_INDICATOR_MAP[family]
        values: list[float] = []

        for field_name in indicator_fields:
            value: float | None = getattr(signals, field_name)
            if value is not None and math.isfinite(value):
                values.append(value)

        if not values:
            family_scores[family] = None
        else:
            raw_mean = sum(values) / len(values)
            # Clamp to [0, 100] for safety (inputs should already be 0-100)
            family_scores[family] = max(0.0, min(100.0, raw_mean))

    return DimensionalScores(**family_scores)


def apply_regime_weights(
    scores: DimensionalScores,
    regime: MarketRegime | None = None,
    enable_regime_weights: bool = False,
) -> float:
    """Compute weighted composite from dimensional scores.

    If *enable_regime_weights* is ``True`` and *regime* is provided, use
    the corresponding ``REGIME_WEIGHT_PROFILES`` profile.  Otherwise use
    ``DEFAULT_FAMILY_WEIGHTS``.

    Families with ``None`` scores are skipped, and their weight is
    redistributed proportionally to the remaining families so that the
    composite is still on a 0--100 scale.

    Args:
        scores: Per-family dimensional scores.
        regime: Current market regime (optional).
        enable_regime_weights: Whether to use regime-adjusted weights.

    Returns:
        Composite score clamped to [0.0, 100.0].  Returns 0.0 when all
        family scores are ``None``.
    """
    if enable_regime_weights and regime is not None:
        weights = REGIME_WEIGHT_PROFILES[regime]
    else:
        weights = DEFAULT_FAMILY_WEIGHTS

    weighted_sum: float = 0.0
    weight_sum: float = 0.0

    for family in _FAMILY_NAMES:
        family_score: float | None = getattr(scores, family)
        if family_score is None:
            continue
        weight = weights[family]
        weighted_sum += weight * family_score
        weight_sum += weight

    if weight_sum == 0.0:
        return 0.0

    # Renormalize so partial coverage still produces 0-100 scale
    raw_composite = weighted_sum / weight_sum
    return max(0.0, min(100.0, raw_composite))


def compute_direction_signal(
    signals: IndicatorSignals,
    composite_score: float,
    direction: SignalDirection,
) -> DirectionSignal:
    """Compute continuous direction confidence with contributing signals.

    Analyzes which indicators contributed to the direction call.  Confidence
    is derived from:
    - How many indicators agree with the direction.
    - The composite score magnitude (distance from 50).
    - The spread between bullish and bearish indicator counts.

    Args:
        signals: Raw or percentile-ranked indicator signals.
        composite_score: The composite score (0--100) for this ticker.
        direction: The discrete direction classification.

    Returns:
        Frozen ``DirectionSignal`` with direction, confidence (0--1), and
        contributing_signals list.
    """
    # Thresholds for directional classification of individual indicators
    _BULLISH_THRESHOLD: float = 60.0
    _BEARISH_THRESHOLD: float = 40.0

    bullish_signals: list[str] = []
    bearish_signals: list[str] = []
    total_valid: int = 0

    # Assess each indicator for directional agreement
    for field_name in IndicatorSignals.model_fields:
        value: float | None = getattr(signals, field_name)
        if value is None or not math.isfinite(value):
            continue
        total_valid += 1

        if value > _BULLISH_THRESHOLD:
            bullish_signals.append(field_name)
        elif value < _BEARISH_THRESHOLD:
            bearish_signals.append(field_name)

    # If no valid indicators, return neutral with low confidence
    if total_valid == 0:
        return DirectionSignal(
            direction=SignalDirection.NEUTRAL,
            confidence=0.1,
            contributing_signals=["no_valid_indicators"],
        )

    # Determine contributing signals based on direction
    if direction == SignalDirection.BULLISH:
        contributing = bullish_signals
    elif direction == SignalDirection.BEARISH:
        contributing = bearish_signals
    else:
        # Neutral: report whichever side has more, or both if equal
        contributing = bullish_signals + bearish_signals

    # Ensure at least one contributing signal (model requires >= 1)
    if not contributing:
        contributing = ["composite_score"]

    # Compute confidence components
    # 1) Agreement ratio: fraction of valid indicators agreeing with direction
    if direction == SignalDirection.BULLISH:
        agreement_count = len(bullish_signals)
    elif direction == SignalDirection.BEARISH:
        agreement_count = len(bearish_signals)
    else:
        agreement_count = max(len(bullish_signals), len(bearish_signals))

    agreement_ratio = agreement_count / total_valid if total_valid > 0 else 0.0

    # 2) Score magnitude: how far the composite score is from 50 (neutral)
    score_magnitude = abs(composite_score - 50.0) / 50.0  # 0.0 to 1.0

    # 3) Spread: difference between bullish and bearish counts, normalized
    spread = abs(len(bullish_signals) - len(bearish_signals))
    spread_ratio = min(spread / max(total_valid, 1), 1.0)

    # Combined confidence: weighted blend of the three components
    raw_confidence = 0.40 * agreement_ratio + 0.35 * score_magnitude + 0.25 * spread_ratio

    # Clamp to [0.1, 1.0] -- never zero confidence (always some signal)
    confidence = max(0.1, min(1.0, raw_confidence))

    logger.debug(
        "Direction signal: %s conf=%.3f (agreement=%.2f, magnitude=%.2f, spread=%.2f)",
        direction.value,
        confidence,
        agreement_ratio,
        score_magnitude,
        spread_ratio,
    )

    return DirectionSignal(
        direction=direction,
        confidence=confidence,
        contributing_signals=contributing,
    )
