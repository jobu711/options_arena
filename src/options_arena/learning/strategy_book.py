"""Strategy mining algorithms for Options Arena self-improvement.

Mines historical outcome data for significant patterns across dimensional
groupings (sector × IV bucket × DTE bucket × direction).  Significant patterns
become ``StrategyRule`` candidates for human approval; approved rules are
injected into desk agent prompts via ``render_learned_patterns()``.

All orchestration functions follow the never-raises contract.
"""

from __future__ import annotations

import logging
import math
import statistics
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from options_arena.data.repository import Repository
from options_arena.models import (
    ConditionOperator,
    RuleStatus,
    StrategyCondition,
    StrategyRule,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dimensional bucket definitions
# ---------------------------------------------------------------------------

IV_BUCKETS: list[tuple[float, float, str]] = [
    (0, 25, "low"),
    (25, 50, "mid_low"),
    (50, 75, "mid_high"),
    (75, 100, "high"),
]

DTE_BUCKETS: list[tuple[float, float, str]] = [
    (0, 30, "short"),
    (30, 60, "medium"),
    (60, 120, "long"),
    (120, 365, "extended"),
]

MIN_TOTAL_OUTCOMES = 100
MIN_CELL_SAMPLES = 20
SIGNIFICANCE_LEVEL = 0.05
MAX_PATTERN_TEXT_CHARS = 1800


# ---------------------------------------------------------------------------
# Internal models (not exported from models/)
# ---------------------------------------------------------------------------


class OutcomeWithContext(BaseModel):
    """Outcome enriched with dimensional context for mining."""

    model_config = ConfigDict(frozen=True)

    sector: str
    iv_rank: float
    dte_at_entry: int
    direction: str
    return_pct: float
    is_winner: bool


class PatternCell(BaseModel):
    """Aggregated statistics for a dimensional grouping."""

    model_config = ConfigDict(frozen=True)

    sector: str
    iv_bucket: str
    dte_bucket: str
    direction: str
    win_rate: float
    avg_return: float
    sample_size: int


# ---------------------------------------------------------------------------
# Bucket classification helpers
# ---------------------------------------------------------------------------


def _classify_iv(iv_rank: float) -> str:
    """Classify IV rank into a bucket label."""
    for low, high, label in IV_BUCKETS:
        if low <= iv_rank < high:
            return label
    return "high"  # 100.0 falls in the last bucket


def _classify_dte(dte: int) -> str:
    """Classify DTE into a bucket label."""
    for low, high, label in DTE_BUCKETS:
        if low <= dte < high:
            return label
    return "extended"  # >= 365 falls in the last bucket


# ---------------------------------------------------------------------------
# Core computation functions (pure — no I/O)
# ---------------------------------------------------------------------------


def mine_patterns(outcomes: list[OutcomeWithContext]) -> list[PatternCell]:
    """Group outcomes by dimensional key and compute per-cell statistics.

    Only cells with at least ``MIN_CELL_SAMPLES`` outcomes are returned.

    Parameters
    ----------
    outcomes
        Enriched outcomes with sector, IV rank, DTE, direction, return.

    Returns
    -------
    list[PatternCell]
        Cells meeting the minimum sample size threshold.
    """
    if not outcomes:
        return []

    # Group by (sector, iv_bucket, dte_bucket, direction)
    cells: dict[tuple[str, str, str, str], list[OutcomeWithContext]] = {}
    for o in outcomes:
        iv_bucket = _classify_iv(o.iv_rank)
        dte_bucket = _classify_dte(o.dte_at_entry)
        key = (o.sector, iv_bucket, dte_bucket, o.direction)
        cells.setdefault(key, []).append(o)

    result: list[PatternCell] = []
    for (sector, iv_bucket, dte_bucket, direction), group in cells.items():
        n = len(group)
        if n < MIN_CELL_SAMPLES:
            continue

        wins = sum(1 for o in group if o.is_winner)
        returns = [o.return_pct for o in group if math.isfinite(o.return_pct)]
        avg_ret = statistics.mean(returns) if returns else 0.0

        result.append(
            PatternCell(
                sector=sector,
                iv_bucket=iv_bucket,
                dte_bucket=dte_bucket,
                direction=direction,
                win_rate=wins / n,
                avg_return=avg_ret,
                sample_size=n,
            )
        )

    return result


def filter_significant(
    cells: list[PatternCell],
    baseline_win_rate: float,
) -> list[PatternCell]:
    """Filter cells to those with statistically significant win rates.

    Uses a chi-squared goodness-of-fit test comparing observed win rate
    against the ``baseline_win_rate``.  Cells where p < ``SIGNIFICANCE_LEVEL``
    are kept.

    Parameters
    ----------
    cells
        Pattern cells from ``mine_patterns()``.
    baseline_win_rate
        Overall win rate across all outcomes (expected proportion).

    Returns
    -------
    list[PatternCell]
        Only cells with statistically significant deviation.
    """
    if not cells or not math.isfinite(baseline_win_rate):
        return []

    # Guard degenerate baselines
    if baseline_win_rate <= 0.0 or baseline_win_rate >= 1.0:
        return []

    significant: list[PatternCell] = []
    for cell in cells:
        n = cell.sample_size
        observed_wins = round(cell.win_rate * n)
        observed_losses = n - observed_wins
        expected_wins = baseline_win_rate * n
        expected_losses = (1.0 - baseline_win_rate) * n

        # Guard against zero expected values
        if expected_wins < 1.0 or expected_losses < 1.0:
            continue

        # Chi-squared statistic (1 degree of freedom)
        chi2 = (observed_wins - expected_wins) ** 2 / expected_wins + (
            observed_losses - expected_losses
        ) ** 2 / expected_losses

        # Critical value for p < 0.05 with 1 df is 3.841
        if chi2 >= 3.841:
            significant.append(cell)

    return significant


def generate_rules(significant_cells: list[PatternCell]) -> list[StrategyRule]:
    """Convert significant pattern cells into ``StrategyRule`` candidates.

    Parameters
    ----------
    significant_cells
        Cells that passed significance testing.

    Returns
    -------
    list[StrategyRule]
        One candidate rule per significant cell.
    """
    now = datetime.now(UTC)
    rules: list[StrategyRule] = []

    for cell in significant_cells:
        rule_id = (
            (
                f"rule_{cell.sector[:12]}_{cell.iv_bucket}_{cell.dte_bucket}"
                f"_{cell.direction}_{uuid.uuid4().hex[:6]}"
            )
            .replace(" ", "_")
            .lower()
        )

        # Build conditions from cell dimensions
        conditions = [
            StrategyCondition(
                field="sector",
                operator=ConditionOperator.EQ,
                value=cell.sector,
            ),
        ]

        # IV range condition
        for low, high, label in IV_BUCKETS:
            if label == cell.iv_bucket:
                conditions.append(
                    StrategyCondition(
                        field="iv_rank_min",
                        operator=ConditionOperator.GTE,
                        value=float(low),
                    )
                )
                conditions.append(
                    StrategyCondition(
                        field="iv_rank_max",
                        operator=ConditionOperator.LT,
                        value=float(high),
                    )
                )
                break

        # DTE range condition
        for low, high, label in DTE_BUCKETS:
            if label == cell.dte_bucket:
                conditions.append(
                    StrategyCondition(
                        field="dte_min",
                        operator=ConditionOperator.GTE,
                        value=float(low),
                    )
                )
                conditions.append(
                    StrategyCondition(
                        field="dte_max",
                        operator=ConditionOperator.LT,
                        value=float(high),
                    )
                )
                break

        conditions.append(
            StrategyCondition(
                field="direction",
                operator=ConditionOperator.EQ,
                value=cell.direction,
            )
        )

        pattern = (
            f"{cell.sector} | IV {cell.iv_bucket} | DTE {cell.dte_bucket} "
            f"| {cell.direction} -> {cell.win_rate:.0%} win rate"
        )

        rules.append(
            StrategyRule(
                rule_id=rule_id,
                pattern=pattern,
                conditions=conditions,
                win_rate=cell.win_rate,
                avg_return=cell.avg_return,
                sample_size=cell.sample_size,
                status=RuleStatus.CANDIDATE,
                created_at=now,
            )
        )

    return rules


def render_learned_patterns(rules: list[StrategyRule]) -> str:
    """Render approved rules as a prompt-injectable text block.

    Only rules with ``status == APPROVED`` are included. Returns an empty
    string when no approved rules exist.

    Parameters
    ----------
    rules
        Strategy rules (any status — filtering happens here).

    Returns
    -------
    str
        Delimited text block for injection, or empty string.
    """
    approved = [r for r in rules if r.status == RuleStatus.APPROVED]
    if not approved:
        return ""

    lines = ["<<<LEARNED_PATTERNS>>>"]
    for rule in approved:
        lines.append(f"Pattern: {rule.pattern}")
        lines.append(f"Win Rate: {rule.win_rate:.1%} (n={rule.sample_size})")
        lines.append(f"Avg Return: {rule.avg_return:+.1%}")
        lines.append("---")
    lines.append("<<<END_LEARNED_PATTERNS>>>")

    text = "\n".join(lines)
    # Truncate at pattern boundaries to prevent prompt bloat
    if len(text) > MAX_PATTERN_TEXT_CHARS:
        # Find last complete pattern entry (ends with "\n---\n")
        cutoff = text.rfind("\n---\n", 0, MAX_PATTERN_TEXT_CHARS)
        if cutoff > 0:
            text = text[: cutoff + 4] + "\n<<<END_LEARNED_PATTERNS>>>"
        else:
            text = "<<<LEARNED_PATTERNS>>>\n<<<END_LEARNED_PATTERNS>>>"
    return text


# ---------------------------------------------------------------------------
# Orchestration wrapper (I/O boundary — never-raises)
# ---------------------------------------------------------------------------


async def run_strategy_mining(repo: Repository) -> list[StrategyRule]:
    """Mine outcomes for significant strategy patterns and persist results.

    This is the top-level orchestration function called by API and CLI.
    It follows the never-raises contract: all exceptions are caught, logged,
    and an empty list is returned on failure.

    Parameters
    ----------
    repo
        Repository instance for DB reads (outcomes) and writes (rules).

    Returns
    -------
    list[StrategyRule]
        Generated candidate rules (may be empty).
    """
    try:
        return await _run_mining_pipeline(repo)
    except Exception:
        logger.exception("Strategy mining failed — returning empty list")
        return []


async def _run_mining_pipeline(repo: Repository) -> list[StrategyRule]:
    """Internal mining pipeline (may raise)."""
    # Fetch outcome data with dimensional context
    outcomes = await _fetch_outcomes_with_context(repo)

    if len(outcomes) < MIN_TOTAL_OUTCOMES:
        logger.warning(
            "Insufficient outcomes for mining: %d < %d",
            len(outcomes),
            MIN_TOTAL_OUTCOMES,
        )
        return []

    # Compute baseline win rate across all outcomes
    total_wins = sum(1 for o in outcomes if o.is_winner)
    baseline_win_rate = total_wins / len(outcomes)

    # Run the mining pipeline
    cells = mine_patterns(outcomes)
    significant = filter_significant(cells, baseline_win_rate)
    rules = generate_rules(significant)

    # Persist generated rules
    for rule in rules:
        await repo.save_strategy_rule(rule)

    logger.info(
        "Strategy mining complete: %d outcomes -> %d cells -> %d significant -> %d rules",
        len(outcomes),
        len(cells),
        len(significant),
        len(rules),
    )
    return rules


async def _fetch_outcomes_with_context(
    repo: Repository,
) -> list[OutcomeWithContext]:
    """Fetch outcomes with dimensional context from the database.

    Joins contract_outcomes with recommended_contracts and ticker_scores
    to get sector, IV rank, DTE at entry, direction, and P&L.
    """
    conn = repo._db.conn  # noqa: SLF001

    sql = (
        "SELECT "
        "  rc.ticker, rc.direction, rc.market_iv, "
        "  CAST(julianday(rc.expiration) - julianday(rc.created_at) AS INTEGER) AS dte_at_entry, "
        "  co.contract_return_pct, co.is_winner, "
        "  COALESCE(tm.sector, 'Unknown') AS sector "
        "FROM contract_outcomes co "
        "JOIN recommended_contracts rc "
        "  ON co.recommended_contract_id = rc.id "
        "LEFT JOIN ticker_metadata tm "
        "  ON rc.ticker = tm.ticker "
        "WHERE co.contract_return_pct IS NOT NULL "
        "  AND co.is_winner IS NOT NULL"
    )

    async with conn.execute(sql) as cursor:
        rows = await cursor.fetchall()

    results: list[OutcomeWithContext] = []
    for row in rows:
        return_pct = float(row["contract_return_pct"])
        if not math.isfinite(return_pct):
            continue

        market_iv = row["market_iv"]
        iv_rank = float(market_iv) * 100.0 if market_iv is not None else 50.0

        results.append(
            OutcomeWithContext(
                sector=str(row["sector"]),
                iv_rank=iv_rank,
                dte_at_entry=int(row["dte_at_entry"]),
                direction=str(row["direction"]),
                return_pct=return_pct,
                is_winner=bool(row["is_winner"]),
            )
        )

    return results
