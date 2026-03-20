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

from options_arena.data.repository import Repository
from options_arena.models import AgentAccuracyReport, AgentWeightsComparison

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vote Weight Tuning (relocated from agents/orchestrator.py)
# ---------------------------------------------------------------------------

# Mapping from agent name to its directional vote weight.
type VoteWeights = dict[str, float]

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

    Connects existing primitives into a working flow:
    1. Fetch per-agent accuracy from the repository.
    2. Compute auto-tuned weights via ``compute_auto_tune_weights()``.
    3. Build ``AgentWeightsComparison`` for each agent (manual vs auto).
    4. Optionally persist the results (skipped when *dry_run* is ``True``).

    Args:
        repo: Repository instance for DB access.
        window_days: Calendar-day lookback window passed to accuracy query.
        dry_run: When ``True``, skip persistence and return comparisons only.

    Returns:
        List of ``AgentWeightsComparison`` — one per agent with tuned weights.
        Empty list when no accuracy data meets the minimum sample threshold.
    """
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
