"""Confidence decay and outcome-triggered validation for strategy rules.

Applies time-based exponential decay to rule confidence (5% per month).
Rules that are never validated receive a 50% penalty.  The decay pipeline
also auto-promotes high-confidence candidates and demotes low-confidence
rules.

All orchestration functions follow the never-raises contract.
"""

from __future__ import annotations

import logging
from datetime import datetime

from options_arena.data.repository import Repository
from options_arena.learning.strategy_book import OutcomeWithContext
from options_arena.models.enums import ConditionOperator, RuleStatus
from options_arena.models.strategy import StrategyRule

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DECAY_RATE: float = 0.95  # 5% decay per month
_SECONDS_PER_MONTH: float = 30.44 * 86400  # average month in seconds
_PROMOTE_CONFIDENCE_THRESHOLD: float = 0.8
_PROMOTE_VALIDATION_COUNT: int = 5
_DEMOTE_CONFIDENCE_THRESHOLD: float = 0.3
_NEVER_VALIDATED_PENALTY: float = 0.5
_VALIDATION_WIN_RATE_TOLERANCE: float = 0.8  # outcome win rate must be >= 80% of rule's


# ---------------------------------------------------------------------------
# Pure computation functions (no I/O)
# ---------------------------------------------------------------------------


def decay_confidence(rule: StrategyRule, now: datetime) -> float:
    """Apply time-based exponential decay to a rule's confidence.

    Uses 5% per-month decay (``0.95 ** months``).  Rules that have never been
    validated (``last_validated is None`` and ``validation_count == 0``) receive
    an additional 50% penalty.

    Parameters
    ----------
    rule
        The strategy rule whose confidence to decay.
    now
        The current UTC datetime for computing elapsed time.

    Returns
    -------
    float
        Decayed confidence clamped to ``[0.0, 1.0]``.
    """
    reference_date = rule.last_validated if rule.last_validated is not None else rule.created_at

    elapsed_seconds = (now - reference_date).total_seconds()

    # Guard: if now is before the reference date, no decay
    if elapsed_seconds <= 0:
        return rule.confidence

    months = elapsed_seconds / _SECONDS_PER_MONTH

    decayed = rule.confidence * (_DECAY_RATE**months)

    # Never-validated penalty
    if rule.last_validated is None and rule.validation_count == 0:
        decayed *= _NEVER_VALIDATED_PENALTY

    clamped: float = max(0.0, min(1.0, decayed))
    return clamped


def validate_rules_against_outcomes(
    rules: list[StrategyRule],
    outcomes: list[OutcomeWithContext],
) -> list[tuple[str, bool]]:
    """Check whether outcome data supports each rule's conditions.

    A rule is "validated" when:
    1. There are matching outcomes (sector + direction match the rule's conditions).
    2. The win rate among matching outcomes is ``>= rule.win_rate * 0.8``.

    Parameters
    ----------
    rules
        Strategy rules to validate.
    outcomes
        Enriched outcome data to validate against.

    Returns
    -------
    list[tuple[str, bool]]
        List of ``(rule_id, is_validated)`` tuples, one per input rule.
    """
    results: list[tuple[str, bool]] = []

    for rule in rules:
        # Extract sector and direction conditions from the rule
        rule_sector: str | None = None
        rule_direction: str | None = None

        for cond in rule.conditions:
            if cond.field == "sector" and cond.operator == ConditionOperator.EQ:
                rule_sector = str(cond.value)
            elif cond.field == "direction" and cond.operator == ConditionOperator.EQ:
                rule_direction = str(cond.value)

        # Filter outcomes matching rule conditions
        matching = [
            o
            for o in outcomes
            if (rule_sector is None or o.sector == rule_sector)
            and (rule_direction is None or o.direction == rule_direction)
        ]

        if not matching:
            results.append((rule.rule_id, False))
            continue

        # Compute win rate from matching outcomes
        wins = sum(1 for o in matching if o.is_winner)
        outcome_win_rate = wins / len(matching)

        # Rule is validated if outcomes support its win rate (within tolerance)
        threshold = rule.win_rate * _VALIDATION_WIN_RATE_TOLERANCE
        is_validated = outcome_win_rate >= threshold
        results.append((rule.rule_id, is_validated))

    return results


def auto_promote_demote(
    rules: list[StrategyRule],
) -> tuple[list[str], list[str]]:
    """Determine which rules should be promoted or demoted based on confidence.

    Promotion: CANDIDATE rules with ``confidence >= 0.8`` AND
    ``validation_count >= 5``.

    Demotion: CANDIDATE or APPROVED rules with ``confidence < 0.3``.

    Already REJECTED rules are never in either list.

    Parameters
    ----------
    rules
        Strategy rules to evaluate (typically after decay has been applied).

    Returns
    -------
    tuple[list[str], list[str]]
        ``(promote_ids, demote_ids)`` — rule IDs to promote/demote.
    """
    promote_ids: list[str] = []
    demote_ids: list[str] = []

    for rule in rules:
        if rule.status == RuleStatus.REJECTED:
            continue

        if (
            rule.status == RuleStatus.CANDIDATE
            and rule.confidence >= _PROMOTE_CONFIDENCE_THRESHOLD
            and rule.validation_count >= _PROMOTE_VALIDATION_COUNT
        ):
            promote_ids.append(rule.rule_id)
        elif (
            rule.status in {RuleStatus.CANDIDATE, RuleStatus.APPROVED}
            and rule.confidence < _DEMOTE_CONFIDENCE_THRESHOLD
        ):
            demote_ids.append(rule.rule_id)

    return promote_ids, demote_ids


# ---------------------------------------------------------------------------
# Orchestration wrapper (I/O boundary — never-raises)
# ---------------------------------------------------------------------------


async def run_confidence_decay(repo: Repository) -> None:
    """Apply confidence decay, auto-promote, and auto-demote to all strategy rules.

    This is the top-level orchestration function called by API and CLI.
    It follows the never-raises contract: all exceptions are caught, logged,
    and the function returns normally.

    Parameters
    ----------
    repo
        Repository instance for DB reads and writes.
    """
    try:
        await _run_decay_pipeline(repo)
    except Exception:
        logger.exception("Confidence decay pipeline failed")


async def _run_decay_pipeline(repo: Repository) -> None:
    """Internal decay pipeline (may raise)."""
    from datetime import UTC

    now = datetime.now(UTC)

    # Fetch all rules, filter out REJECTED in code
    all_rules = await repo.get_strategy_rules()
    active_rules = [r for r in all_rules if r.status != RuleStatus.REJECTED]

    if not active_rules:
        logger.info("No active strategy rules to decay")
        return

    # Apply decay to each rule and build updated copies for promote/demote logic
    decayed_rules: list[StrategyRule] = []
    for rule in active_rules:
        new_confidence = decay_confidence(rule, now)

        # Persist updated confidence
        await repo.update_rule_confidence(
            rule_id=rule.rule_id,
            confidence=new_confidence,
            last_validated=rule.last_validated,
            validation_count=rule.validation_count,
        )

        # Build a copy with the decayed confidence for promote/demote evaluation.
        # StrategyRule is frozen, so we use model_copy with update.
        decayed_rule = rule.model_copy(update={"confidence": new_confidence})
        decayed_rules.append(decayed_rule)

    # Auto-promote and auto-demote
    promote_ids, demote_ids = auto_promote_demote(decayed_rules)

    for rule_id in promote_ids:
        # Find the decayed confidence for this rule
        decayed = next((r for r in decayed_rules if r.rule_id == rule_id), None)
        if decayed is not None:
            await repo.update_rule_status_and_confidence(
                rule_id=rule_id,
                status=RuleStatus.APPROVED,
                confidence=decayed.confidence,
            )

    for rule_id in demote_ids:
        decayed = next((r for r in decayed_rules if r.rule_id == rule_id), None)
        if decayed is not None:
            await repo.update_rule_status_and_confidence(
                rule_id=rule_id,
                status=RuleStatus.REJECTED,
                confidence=decayed.confidence,
            )

    logger.info(
        "Confidence decay complete: %d rules processed, %d promoted, %d demoted",
        len(active_rules),
        len(promote_ids),
        len(demote_ids),
    )
