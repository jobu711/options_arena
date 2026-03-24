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

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.data.repository import Repository
from options_arena.models import (
    ConditionOperator,
    RuleStatus,
    StrategyCondition,
    StrategyRule,
)
from options_arena.models.enums import GICSSector, SignalDirection

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

ADX_BUCKETS: list[tuple[float, float, str]] = [
    (0, 20, "weak"),
    (20, 30, "moderate"),
    (30, 100, "strong"),
]

ATR_PCT_BUCKETS: list[tuple[float, float, str]] = [
    (0, 1.5, "low"),
    (1.5, 3.0, "medium"),
    (3.0, 100, "high"),
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
    iv_level: float  # raw IV * 100 (NOT IV rank — see fetch_outcomes_with_context)
    dte_at_entry: int
    direction: str
    return_pct: float
    is_winner: bool
    adx: float | None = None
    atr_pct: float | None = None
    rsi: float | None = None

    @field_validator("iv_level")
    @classmethod
    def _validate_iv_level(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("iv_level must be finite")
        return v

    @field_validator("return_pct")
    @classmethod
    def _validate_return_pct(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("return_pct must be finite")
        return v

    @field_validator("adx", "atr_pct", "rsi")
    @classmethod
    def _validate_context_float(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError("context field must be finite")
        return v


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

    @field_validator("win_rate")
    @classmethod
    def _validate_win_rate(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("win_rate must be finite")
        return v

    @field_validator("avg_return")
    @classmethod
    def _validate_avg_return(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("avg_return must be finite")
        return v


# ---------------------------------------------------------------------------
# Bucket classification helpers
# ---------------------------------------------------------------------------


def _classify_iv(iv_level: float) -> str:
    """Classify IV level (raw IV * 100) into a bucket label."""
    for low, high, label in IV_BUCKETS:
        if low <= iv_level < high:
            return label
    return "high"  # 100.0 falls in the last bucket


def _classify_dte(dte: int) -> str:
    """Classify DTE into a bucket label."""
    for low, high, label in DTE_BUCKETS:
        if low <= dte < high:
            return label
    return "extended"  # >= 365 falls in the last bucket


def _classify_adx(adx: float | None) -> str | None:
    """Classify ADX into a bucket label, or ``None`` if unavailable."""
    if adx is None:
        return None
    for low, high, label in ADX_BUCKETS:
        if low <= adx < high:
            return label
    return "strong"  # >= 100 falls in the last bucket


def _classify_atr_pct(atr_pct: float | None) -> str | None:
    """Classify ATR% into a bucket label, or ``None`` if unavailable."""
    if atr_pct is None:
        return None
    for low, high, label in ATR_PCT_BUCKETS:
        if low <= atr_pct < high:
            return label
    return "high"  # >= 100 falls in the last bucket


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
        iv_bucket = _classify_iv(o.iv_level)
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
    # Allowlists for prompt-injection defense (P1 audit finding)
    valid_sectors = {s.value for s in GICSSector} | {"Unknown"}
    valid_directions = {d.value for d in SignalDirection}

    now = datetime.now(UTC)
    rules: list[StrategyRule] = []

    for cell in significant_cells:
        # Sanitize sector/direction against known-good values
        if cell.sector not in valid_sectors:
            logger.warning("Skipping rule with unknown sector: %.40s", cell.sector)
            continue
        if cell.direction not in valid_directions:
            logger.warning("Skipping rule with unknown direction: %.40s", cell.direction)
            continue

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


_CONFIDENCE_RENDER_THRESHOLD = 0.3
_STRONG_PATTERN_THRESHOLD = 0.8


def render_learned_patterns(rules: list[StrategyRule]) -> str:
    """Render approved rules as a prompt-injectable text block.

    Only rules with ``status == APPROVED`` and ``confidence >= 0.3`` are
    included.  Rules are sorted by confidence descending and labelled with
    confidence tiers: ``>= 0.8`` → ``"Strong pattern:"``, otherwise
    ``"Pattern:"``.

    Parameters
    ----------
    rules
        Strategy rules (any status — filtering happens here).

    Returns
    -------
    str
        Delimited text block for injection, or empty string.
    """
    approved = [
        r
        for r in rules
        if r.status == RuleStatus.APPROVED and r.confidence >= _CONFIDENCE_RENDER_THRESHOLD
    ]
    if not approved:
        return ""

    approved.sort(key=lambda r: r.confidence, reverse=True)

    lines = ["<<<LEARNED_PATTERNS>>>"]
    for rule in approved:
        prefix = "Strong pattern" if rule.confidence >= _STRONG_PATTERN_THRESHOLD else "Pattern"
        lines.append(f"{prefix}: {rule.pattern} (confidence: {rule.confidence:.0%})")
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
    outcomes = await fetch_outcomes_with_context(repo)

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


async def fetch_outcomes_with_context(
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
        "  COALESCE(tm.sector, 'Unknown') AS sector, "
        "  p.adx, p.atr_pct, p.rsi "
        "FROM contract_outcomes co "
        "JOIN recommended_contracts rc "
        "  ON co.recommended_contract_id = rc.id "
        "LEFT JOIN ticker_metadata tm "
        "  ON rc.ticker = tm.ticker "
        "LEFT JOIN recommendation_results rr "
        "  ON rr.scan_run_id = rc.scan_run_id AND rr.ticker = rc.ticker "
        "LEFT JOIN predictions p "
        "  ON p.recommendation_id = rr.id AND p.source = 'synthesis' "
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
        raw_iv = float(market_iv) if market_iv is not None else None
        # iv_level is raw IV * 100 (NOT IV rank — see P2-2 audit note)
        iv_level = raw_iv * 100.0 if raw_iv is not None and math.isfinite(raw_iv) else 50.0

        # Indicator context from prediction snapshot (may be None if no prediction)
        raw_adx = row["adx"]
        adx = float(raw_adx) if raw_adx is not None else None
        raw_atr_pct = row["atr_pct"]
        atr_pct = float(raw_atr_pct) if raw_atr_pct is not None else None
        raw_rsi = row["rsi"]
        rsi = float(raw_rsi) if raw_rsi is not None else None

        results.append(
            OutcomeWithContext(
                sector=str(row["sector"]),
                iv_level=iv_level,
                dte_at_entry=int(row["dte_at_entry"]),
                direction=str(row["direction"]),
                return_pct=return_pct,
                is_winner=bool(row["is_winner"]),
                adx=adx,
                atr_pct=atr_pct,
                rsi=rsi,
            )
        )

    return results
