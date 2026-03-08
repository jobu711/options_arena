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
        "macd",
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
        "chain_spread_pct",
        "chain_oi_depth",
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


_PHI_SCALE: float = math.pi / math.sqrt(3)
"""Logistic CDF scaling factor that approximates the normal CDF to within 0.01."""


def compute_direction_signal(
    signals: IndicatorSignals,
    direction: SignalDirection,
) -> DirectionSignal:
    """Compute continuous direction confidence via z-test on mean shift.

    Percentile-ranked signals are approximately uniform on [0, 100].
    Under the null hypothesis "no directional bias," the mean of *n*
    such values is 50 with known standard error ``100 / sqrt(12 * n)``.

    The z-score measures how far the observed signal mean deviates from
    neutral, then maps through a logistic CDF (approximates normal CDF)
    to produce a probability in [0, 1].

    Args:
        signals: Percentile-ranked indicator signals (0--100 scale).
        direction: The discrete direction classification.

    Returns:
        Frozen ``DirectionSignal`` with direction, confidence (0.10--0.95),
        and contributing_signals list.
    """
    # 1. Collect non-None, finite values
    values: list[float] = []
    field_values: dict[str, float] = {}
    for field_name in IndicatorSignals.model_fields:
        v: float | None = getattr(signals, field_name)
        if v is not None and math.isfinite(v):
            values.append(v)
            field_values[field_name] = v

    n = len(values)
    if n == 0:
        return DirectionSignal(
            direction=SignalDirection.NEUTRAL,
            confidence=0.1,
            contributing_signals=["no_valid_indicators"],
        )

    # 2. Z-test: how far does the signal mean deviate from neutral (50)?
    mean_val = sum(values) / n
    se = 100.0 / (12.0 * n) ** 0.5  # SE under uniform[0,100]
    z = (mean_val - 50.0) / se
    p = 1.0 / (1.0 + math.exp(-_PHI_SCALE * z))  # logistic ≈ Φ(z)

    # 3. Map to directional confidence
    if direction == SignalDirection.BULLISH:
        raw_confidence = p
    elif direction == SignalDirection.BEARISH:
        raw_confidence = 1.0 - p
    else:
        raw_confidence = 1.0 - 2.0 * abs(p - 0.5)

    confidence = max(0.10, min(0.95, raw_confidence))

    # 4. Contributing signals: those leaning in the direction
    contributing: list[str] = []
    for name, v in field_values.items():
        lean = (v - 50.0) / 50.0  # [-1, +1]
        is_contributor = (
            (direction == SignalDirection.BULLISH and lean > 0.10)
            or (direction == SignalDirection.BEARISH and lean < -0.10)
            or (direction == SignalDirection.NEUTRAL and abs(lean) > 0.10)
        )
        if is_contributor:
            contributing.append(name)

    if not contributing:
        contributing = ["composite_score"]

    logger.debug(
        "Direction signal: %s conf=%.3f (mean=%.1f, z=%.2f, p=%.3f, n=%d)",
        direction.value,
        confidence,
        mean_val,
        z,
        p,
        n,
    )

    return DirectionSignal(
        direction=direction,
        confidence=confidence,
        contributing_signals=contributing,
    )
