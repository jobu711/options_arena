"""Weight tuning algorithms for Options Arena self-improvement.

Phase 1: Vote weight tuning (relocated from ``agents/orchestrator.py``) and
indicator weight tuning (new). Both algorithms produce optimized weights from
historical outcome data.

Vote weights use inverse Brier score, clamped to [0.05, 0.35], normalized to
sum=0.85 (Bordley 1982 log-odds pooling convention).

All orchestration functions follow the never-raises contract: catch exceptions,
log, and return empty/fallback results.
"""

from __future__ import annotations

import logging
import math
import statistics

from options_arena.data.repository import Repository
from options_arena.models import (
    AgentAccuracyReport,
    AgentWeightsComparison,
    IndicatorWeightComparison,
)
from options_arena.models.scan import IndicatorSignals
from options_arena.scoring.composite import INDICATOR_WEIGHTS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vote Weight Tuning (relocated from agents/orchestrator.py)
# ---------------------------------------------------------------------------

# Mapping from agent name to its directional vote weight.
type VoteWeights = dict[str, float]

# Mapping from indicator field name to its composite weight.
type IndicatorWeights = dict[str, float]

# Agent vote weights for verdict synthesis.
# Directional weights sum to 0.85 — unnormalized weights are correct for
# Bordley 1982 log-odds pooling.
AGENT_VOTE_WEIGHTS: VoteWeights = {
    "trend": 0.25,
    "volatility": 0.20,
    "flow": 0.20,
    "fundamental": 0.15,
    "contrarian": 0.05,
    "risk": 0.0,  # Risk agent is advisory-only — informs but doesn't vote on direction
}


def compute_auto_tune_weights(
    accuracy: list[AgentAccuracyReport],
) -> VoteWeights:
    """Compute auto-tuned vote weights from agent accuracy data.

    Uses inverse Brier score, clamped to [0.05, 0.35], normalized to sum=0.85.
    Agents with <10 samples keep manual weights. Risk is always 0.0.
    """
    weights = dict(AGENT_VOTE_WEIGHTS)
    agents_with_data = {r.agent_name: r for r in accuracy if r.sample_size >= 10}

    for name in weights:
        if name == "risk":
            weights[name] = 0.0
            continue
        if name in agents_with_data:
            raw = 1.0 - agents_with_data[name].brier_score
            if not math.isfinite(raw):
                continue
            weights[name] = raw

    for name in weights:
        if name == "risk":
            continue
        weights[name] = max(0.05, min(0.35, weights[name]))

    directional = {k: v for k, v in weights.items() if k != "risk"}
    total = sum(directional.values())
    if total > 0:
        for name in directional:
            weights[name] = (directional[name] / total) * 0.85

    return weights


async def auto_tune_weights(
    repo: Repository,
    window_days: int = 90,
    dry_run: bool = False,
) -> list[AgentWeightsComparison]:
    """Orchestrate end-to-end auto-tune: accuracy -> weights -> compare -> persist.

    Never-raises: catches all exceptions, logs, returns empty list.

    Args:
        repo: Repository instance for DB access.
        window_days: Calendar-day lookback window passed to accuracy query.
        dry_run: When ``True``, skip persistence and return comparisons only.

    Returns:
        List of ``AgentWeightsComparison`` — one per agent with tuned weights.
        Empty list when no accuracy data meets the minimum sample threshold.
    """
    try:
        return await _auto_tune_weights_inner(repo, window_days, dry_run)
    except Exception:
        logger.warning(
            "Vote weight auto-tune failed (window=%d)",
            window_days,
            exc_info=True,
        )
        return []


async def _auto_tune_weights_inner(
    repo: Repository,
    window_days: int,
    dry_run: bool,
) -> list[AgentWeightsComparison]:
    """Inner implementation — may raise."""
    accuracy = await repo.get_agent_accuracy(window_days=window_days)

    # Skip persistence when no agent has enough scored outcomes
    has_eligible = any(
        r.agent_name != "risk" and r.sample_size >= 10 and math.isfinite(r.brier_score)
        for r in accuracy
    )
    if not has_eligible:
        logger.info(
            "Auto-tune skipped: no directional agent has enough scored outcomes (window=%d)",
            window_days,
        )
        return []

    tuned = compute_auto_tune_weights(accuracy)

    comparisons = [
        AgentWeightsComparison(
            agent_name=name,
            manual_weight=AGENT_VOTE_WEIGHTS.get(name, 0.0),
            auto_weight=tuned.get(name, 0.0),
            brier_score=next((a.brier_score for a in accuracy if a.agent_name == name), None),
            sample_size=next((a.sample_size for a in accuracy if a.agent_name == name), 0),
        )
        for name in tuned
    ]

    if not dry_run:
        await repo.save_auto_tune_weights(comparisons, window_days=window_days)

    logger.info(
        "Auto-tune weights computed for %d agents (window=%d, dry_run=%s)",
        len(comparisons),
        window_days,
        dry_run,
    )
    return comparisons


# ---------------------------------------------------------------------------
# Indicator Weight Tuning
# ---------------------------------------------------------------------------

# Bounds for indicator weight clamping.
_INDICATOR_WEIGHT_FLOOR: float = 0.01
_INDICATOR_WEIGHT_CAP: float = 0.15
_MIN_INDICATOR_SAMPLES: int = 10


def _pearson_r(xs: list[float], ys: list[float]) -> float | None:
    """Compute Pearson correlation coefficient.

    Returns ``None`` when fewer than 2 pairs or zero variance in either series.
    """
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None

    try:
        mean_x = statistics.mean(xs)
        mean_y = statistics.mean(ys)
    except statistics.StatisticsError:
        return None

    sum_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    sum_x2 = sum((x - mean_x) ** 2 for x in xs)
    sum_y2 = sum((y - mean_y) ** 2 for y in ys)

    denom = math.sqrt(sum_x2 * sum_y2)
    if denom == 0.0:
        return None

    r = sum_xy / denom
    return r if math.isfinite(r) else None


def _static_indicator_weights() -> IndicatorWeights:
    """Extract the weight-only values from INDICATOR_WEIGHTS."""
    return {name: w for name, (w, _cat) in INDICATOR_WEIGHTS.items()}


def compute_indicator_tune_weights(
    samples: list[tuple[IndicatorSignals, float]],
) -> IndicatorWeights:
    """Compute optimized indicator weights from signal-P&L correlations.

    For each indicator field on :class:`IndicatorSignals`, computes Pearson *r*
    between the percentile-rank values and the corresponding contract P&L
    returns. The absolute correlation is converted to a raw weight, clamped to
    ``[0.01, 0.15]``, and normalized so all weights sum to 1.0.

    Indicators with fewer than ``_MIN_INDICATOR_SAMPLES`` non-None data points
    retain their static weight from :data:`INDICATOR_WEIGHTS`.

    This function is **pure** — no I/O, no database calls.

    Args:
        samples: List of ``(IndicatorSignals, pnl_return)`` pairs. Each pair
            associates a ticker's percentile-ranked indicator snapshot with the
            subsequent contract P&L return (as a float, e.g. 0.15 for +15%).

    Returns:
        Mapping of indicator field name to weight, summing to 1.0.
        On any error, returns the static ``INDICATOR_WEIGHTS`` defaults.
    """
    static = _static_indicator_weights()

    if not samples:
        return static

    try:
        return _compute_indicator_weights_inner(samples, static)
    except Exception:
        logger.warning(
            "Indicator weight tuning failed, returning static weights",
            exc_info=True,
        )
        return static


def _compute_indicator_weights_inner(
    samples: list[tuple[IndicatorSignals, float]],
    static: dict[str, float],
) -> dict[str, float]:
    """Inner implementation — may raise."""
    # Collect all indicator field names from static weights.
    field_names = list(static.keys())
    weights: dict[str, float] = {}

    for field_name in field_names:
        # Extract non-None (indicator, pnl) pairs for this field.
        xs: list[float] = []
        ys: list[float] = []
        for signals, pnl in samples:
            val = getattr(signals, field_name, None)
            if val is not None and math.isfinite(val) and math.isfinite(pnl):
                xs.append(val)
                ys.append(pnl)

        if len(xs) < _MIN_INDICATOR_SAMPLES:
            # Insufficient data — keep static weight.
            weights[field_name] = static[field_name]
            continue

        r = _pearson_r(xs, ys)
        if r is None:
            weights[field_name] = static[field_name]
            continue

        # Use absolute correlation as raw weight signal.
        raw = abs(r)
        weights[field_name] = max(_INDICATOR_WEIGHT_FLOOR, min(_INDICATOR_WEIGHT_CAP, raw))

    # Normalize to sum=1.0.
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}

    return weights


# ---------------------------------------------------------------------------
# Indicator Weight Tuning — Orchestration
# ---------------------------------------------------------------------------

_MIN_INDICATOR_TUNE_SAMPLES: int = 50


async def auto_tune_indicator_weights(
    repo: Repository,
    window_days: int = 90,
    dry_run: bool = False,
) -> list[IndicatorWeightComparison]:
    """Orchestrate indicator weight tuning: fetch data → compute → persist.

    Never-raises: catches all exceptions, logs, returns empty list.

    Args:
        repo: Repository instance for DB access.
        window_days: Calendar-day lookback for outcome data.
        dry_run: When ``True``, compute but skip persistence.

    Returns:
        List of ``IndicatorWeightComparison`` — one per indicator.
        Empty list when insufficient data or on error.
    """
    try:
        return await _auto_tune_indicator_weights_inner(repo, window_days, dry_run)
    except Exception:
        logger.warning(
            "Indicator weight tuning failed (window=%d)",
            window_days,
            exc_info=True,
        )
        return []


async def _auto_tune_indicator_weights_inner(
    repo: Repository,
    window_days: int,
    dry_run: bool,
) -> list[IndicatorWeightComparison]:
    """Inner implementation — may raise."""
    pairs = await repo.get_outcome_signal_pairs(window_days=window_days)

    if len(pairs) < _MIN_INDICATOR_TUNE_SAMPLES:
        logger.info(
            "Indicator tune skipped: only %d samples (need %d, window=%d)",
            len(pairs),
            _MIN_INDICATOR_TUNE_SAMPLES,
            window_days,
        )
        return []

    tuned = compute_indicator_tune_weights(pairs)
    static = _static_indicator_weights()

    # Build per-indicator Pearson r for comparison output
    field_names = list(static.keys())
    pearson_map: dict[str, float | None] = {}
    sample_counts: dict[str, int] = {}
    for name in field_names:
        xs: list[float] = []
        ys: list[float] = []
        for signals, pnl in pairs:
            val = getattr(signals, name, None)
            if val is not None and math.isfinite(val) and math.isfinite(pnl):
                xs.append(val)
                ys.append(pnl)
        sample_counts[name] = len(xs)
        pearson_map[name] = _pearson_r(xs, ys)

    comparisons = [
        IndicatorWeightComparison(
            indicator_name=name,
            static_weight=static.get(name, 0.0),
            tuned_weight=tuned.get(name, 0.0),
            pearson_r=pearson_map.get(name),
            sample_count=sample_counts.get(name, 0),
        )
        for name in field_names
    ]

    # Compute accuracy as win rate (fraction of positive P&L outcomes)
    positive_count = sum(1 for _, pnl in pairs if pnl > 0)
    accuracy = positive_count / len(pairs) if pairs else None

    if not dry_run:
        await repo.save_indicator_weights(
            tuned, static, window_days=window_days, accuracy=accuracy
        )

    logger.info(
        "Indicator weights tuned for %d indicators (%d samples, window=%d, dry_run=%s)",
        len(comparisons),
        len(pairs),
        window_days,
        dry_run,
    )
    return comparisons
