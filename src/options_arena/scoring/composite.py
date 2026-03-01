"""Weighted geometric mean composite scoring for the ticker universe.

Takes percentile-ranked (and inverted) indicator values and produces a single
composite score per ticker using a weighted geometric mean.  Tickers are
returned as :class:`~options_arena.models.scan.TickerScore` models sorted
descending by score.

All inputs and outputs use :class:`~options_arena.models.scan.IndicatorSignals`
typed model -- never ``dict[str, float]``.
"""

import logging
import math

from options_arena.models.enums import SignalDirection
from options_arena.models.scan import IndicatorSignals, TickerScore
from options_arena.scoring.normalization import (
    get_active_indicators,
    invert_indicators,
    percentile_rank_normalize,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Weight mapping: indicator field name -> (weight, category).
# Field names match IndicatorSignals fields exactly.
# Individual weights sum to 1.0.
INDICATOR_WEIGHTS: dict[str, tuple[float, str]] = {
    # Oscillators
    "rsi": (0.08, "oscillators"),
    "stochastic_rsi": (0.05, "oscillators"),
    "williams_r": (0.05, "oscillators"),
    # Trend
    "adx": (0.08, "trend"),
    "roc": (0.05, "trend"),
    "supertrend": (0.05, "trend"),
    # Volatility
    "atr_pct": (0.05, "volatility"),
    "bb_width": (0.05, "volatility"),
    "keltner_width": (0.04, "volatility"),
    # Volume
    "obv": (0.05, "volume"),
    "ad": (0.05, "volume"),
    "relative_volume": (0.05, "volume"),
    # Moving Averages
    "sma_alignment": (0.08, "moving_averages"),
    "vwap_deviation": (0.05, "moving_averages"),
    # Options
    "iv_rank": (0.06, "options"),
    "iv_percentile": (0.06, "options"),
    "put_call_ratio": (0.05, "options"),
    "max_pain_distance": (0.05, "options"),
}

# Validate weights sum to 1.0 at import time — catches drift before any scoring runs.
# Uses if/raise (not assert) so the guard is never stripped by python -O.
if abs(sum(w for w, _ in INDICATOR_WEIGHTS.values()) - 1.0) >= 1e-9:
    raise ValueError("Indicator weights must sum to 1.0")

# Floor value substituted for percentile ranks <= 0 to avoid log(0).
_FLOOR_VALUE: float = 1.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def composite_score(
    signals: IndicatorSignals,
    active_indicators: set[str] | None = None,
) -> float:
    """Compute a weighted geometric mean composite score for a single ticker.

    The score is ``exp(sum(w_i * ln(max(x_i, 1.0))) / sum(w_i))`` where
    *w_i* is the weight for indicator *i* and *x_i* is the percentile rank.

    Indicators that are ``None`` on *signals*, not present in
    :data:`INDICATOR_WEIGHTS`, or excluded by *active_indicators* are silently
    skipped.  The remaining weights are renormalized so that partial coverage
    still produces a meaningful score.

    Args:
        signals: Percentile-ranked (and inverted) indicator values for a
            single ticker.
        active_indicators: If provided, only indicators in this set are
            considered.  Indicators outside the set are skipped even if they
            have a non-None value on *signals*.

    Returns:
        Composite score clamped to [0.0, 100.0].  Returns 0.0 when no
        indicators contribute (all None or empty active set).
    """
    weighted_log_sum: float = 0.0
    weight_sum: float = 0.0

    for field_name, (weight, _category) in INDICATOR_WEIGHTS.items():
        # Skip if not in active set.
        if active_indicators is not None and field_name not in active_indicators:
            continue

        value: float | None = getattr(signals, field_name)
        if value is None or not math.isfinite(value):
            continue

        # Floor to avoid log(0).
        floored_value = max(value, _FLOOR_VALUE)
        weighted_log_sum += weight * math.log(floored_value)
        weight_sum += weight

    if weight_sum == 0.0:
        return 0.0

    raw_score = math.exp(weighted_log_sum / weight_sum)
    return max(0.0, min(100.0, raw_score))


def score_universe(
    universe: dict[str, IndicatorSignals],
) -> list[TickerScore]:
    """Score and rank an entire universe of tickers.

    Full pipeline:
        1. Determine which indicators have at least one valid value.
        2. Percentile-rank normalize all indicators across the universe.
        3. Invert indicators where higher raw value = worse signal.
        4. Compute composite score per ticker.
        5. Build :class:`TickerScore` list sorted descending by score.

    Direction is set to :attr:`SignalDirection.NEUTRAL` as a placeholder --
    direction classification is handled separately by ``direction.py``.

    .. warning::
        The ``signals`` field on the returned :class:`TickerScore` instances
        contains **percentile-ranked and inverted** values (0--100), NOT raw
        indicator values.  ``determine_direction()`` expects **raw** indicator
        values (e.g. RSI 20--80, ADX 0--100).  Callers must retain the
        original raw ``IndicatorSignals`` for direction classification.

    Args:
        universe: Mapping of ticker symbol to **raw** ``IndicatorSignals``
            (not yet normalized).

    Returns:
        List of :class:`TickerScore` sorted descending by ``composite_score``.
    """
    if not universe:
        return []

    # Step 1: Determine active indicators.
    active = get_active_indicators(universe)
    logger.debug("Active indicators (%d of %d): %s", len(active), len(INDICATOR_WEIGHTS), active)

    # Step 2-3: Normalize and invert.
    normalized = percentile_rank_normalize(universe)
    inverted = invert_indicators(normalized)

    # Step 4: Composite score per ticker.
    scored: list[tuple[str, float, IndicatorSignals]] = []
    for ticker, signals in inverted.items():
        score = composite_score(signals, active)
        scored.append((ticker, score, signals))

    # Step 5: Sort descending by score.
    scored.sort(key=lambda t: t[1], reverse=True)

    # Build TickerScore models.
    results: list[TickerScore] = []
    for ticker, score, signals in scored:
        results.append(
            TickerScore(
                ticker=ticker,
                composite_score=score,
                direction=SignalDirection.NEUTRAL,
                signals=signals,
            )
        )

    return results
