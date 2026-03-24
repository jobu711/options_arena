"""Contract guidance computation and rendering.

Computes optimal delta and DTE ranges from historical contract outcome data,
and renders them as a ``<<<CONTRACT_GUIDANCE>>>`` prompt block for injection
into the synthesis agent prompt.

Returns ``ContractGuidance`` when >= 30 outcomes exist with sufficient bucket
coverage, or ``None`` when data is insufficient. Follows the
``render_learned_patterns()`` delimiter pattern from ``strategy_book.py``.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models.attribution import ContractGuidance

if TYPE_CHECKING:
    from options_arena.data.repository import Repository

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DELTA_BUCKET_SIZE: float = 0.10
"""Width of each delta bucket (absolute delta, 0.0--1.0 range)."""

DTE_BUCKET_SIZE: int = 15
"""Width of each DTE bucket in calendar days."""

MIN_GUIDANCE_SAMPLES: int = 30
"""Minimum outcomes per bucket to be considered for optimal range selection."""

MAX_GUIDANCE_TEXT_CHARS: int = 1800
"""Maximum character length for the rendered contract guidance prompt block."""


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------


class OutcomeWithDelta(BaseModel):
    """Enriched outcome with delta and DTE at entry for guidance computation.

    Frozen snapshot — all fields immutable after construction.
    """

    model_config = ConfigDict(frozen=True)

    delta_at_entry: float
    dte_at_entry: int
    is_winner: bool

    @field_validator("delta_at_entry")
    @classmethod
    def _validate_delta(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"delta_at_entry must be finite, got {v}")
        return v

    @field_validator("dte_at_entry")
    @classmethod
    def _validate_dte(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"dte_at_entry must be >= 0, got {v}")
        return v


# ---------------------------------------------------------------------------
# Bucket helper
# ---------------------------------------------------------------------------


class _BucketStats:
    """Mutable accumulator for win rate within a bucket."""

    __slots__ = ("wins", "total")

    def __init__(self) -> None:
        self.wins: int = 0
        self.total: int = 0

    @property
    def win_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.wins / self.total


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def compute_contract_guidance(
    outcomes: list[OutcomeWithDelta],
) -> ContractGuidance | None:
    """Compute optimal delta and DTE ranges from historical outcomes.

    Buckets outcomes by delta (``DELTA_BUCKET_SIZE`` increments) and DTE
    (``DTE_BUCKET_SIZE`` increments), then selects the bucket with the
    highest win rate that has at least ``MIN_GUIDANCE_SAMPLES`` samples.

    Parameters
    ----------
    outcomes
        Enriched contract outcomes with delta and DTE at entry.

    Returns
    -------
    ContractGuidance | None
        Learned optimal ranges, or ``None`` if insufficient data.
    """
    if len(outcomes) < MIN_GUIDANCE_SAMPLES:
        logger.debug(
            "Insufficient outcomes for contract guidance: %d < %d",
            len(outcomes),
            MIN_GUIDANCE_SAMPLES,
        )
        return None

    # --- Delta bucketing ---
    delta_buckets: dict[int, _BucketStats] = {}
    for o in outcomes:
        abs_delta = abs(o.delta_at_entry)
        bucket_idx = int(abs_delta / DELTA_BUCKET_SIZE)
        stats = delta_buckets.setdefault(bucket_idx, _BucketStats())
        stats.total += 1
        if o.is_winner:
            stats.wins += 1

    # --- DTE bucketing ---
    dte_buckets: dict[int, _BucketStats] = {}
    for o in outcomes:
        bucket_idx = o.dte_at_entry // DTE_BUCKET_SIZE
        stats = dte_buckets.setdefault(bucket_idx, _BucketStats())
        stats.total += 1
        if o.is_winner:
            stats.wins += 1

    # --- Find optimal delta bucket ---
    best_delta: tuple[int, _BucketStats] | None = None
    for idx, stats in sorted(delta_buckets.items()):
        if stats.total < MIN_GUIDANCE_SAMPLES:
            continue
        if best_delta is None or stats.win_rate > best_delta[1].win_rate:
            best_delta = (idx, stats)
        elif stats.win_rate == best_delta[1].win_rate and idx < best_delta[0]:
            # Tie-break: prefer lower delta bucket for determinism
            best_delta = (idx, stats)

    if best_delta is None:
        logger.debug("No delta bucket meets minimum sample threshold of %d", MIN_GUIDANCE_SAMPLES)
        return None

    # --- Find optimal DTE bucket ---
    best_dte: tuple[int, _BucketStats] | None = None
    for idx, stats in sorted(dte_buckets.items()):
        if stats.total < MIN_GUIDANCE_SAMPLES:
            continue
        if best_dte is None or stats.win_rate > best_dte[1].win_rate:
            best_dte = (idx, stats)
        elif stats.win_rate == best_dte[1].win_rate and idx < best_dte[0]:
            # Tie-break: prefer lower DTE bucket for determinism
            best_dte = (idx, stats)

    if best_dte is None:
        logger.debug("No DTE bucket meets minimum sample threshold of %d", MIN_GUIDANCE_SAMPLES)
        return None

    # --- Build result ---
    delta_low = round(best_delta[0] * DELTA_BUCKET_SIZE, 2)
    delta_high = round(delta_low + DELTA_BUCKET_SIZE, 2)
    dte_low = best_dte[0] * DTE_BUCKET_SIZE
    dte_high = dte_low + DTE_BUCKET_SIZE

    return ContractGuidance(
        optimal_delta_low=delta_low,
        optimal_delta_high=delta_high,
        optimal_dte_low=dte_low,
        optimal_dte_high=dte_high,
        delta_win_rate=best_delta[1].win_rate,
        dte_win_rate=best_dte[1].win_rate,
        sample_count=len(outcomes),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_contract_guidance(guidance: ContractGuidance) -> str:
    """Render contract guidance as a prompt-injectable text block.

    Uses ``<<<CONTRACT_GUIDANCE>>>`` / ``<<<END_CONTRACT_GUIDANCE>>>``
    delimiters matching the pattern from ``render_learned_patterns()``.

    Parameters
    ----------
    guidance
        Computed contract guidance to render.

    Returns
    -------
    str
        Delimited text block for injection into the synthesis agent prompt.
    """
    lines = ["<<<CONTRACT_GUIDANCE>>>"]
    lines.append(
        f"Optimal delta range: {guidance.optimal_delta_low:.2f}-"
        f"{guidance.optimal_delta_high:.2f} "
        f"(win rate: {guidance.delta_win_rate:.0%}, n={guidance.sample_count})"
    )
    lines.append(
        f"Optimal DTE range: {guidance.optimal_dte_low}-"
        f"{guidance.optimal_dte_high} days "
        f"(win rate: {guidance.dte_win_rate:.0%})"
    )
    lines.append("<<<END_CONTRACT_GUIDANCE>>>")

    text = "\n".join(lines)
    if len(text) > MAX_GUIDANCE_TEXT_CHARS:
        # Truncate to fit — keep delimiters intact
        text = "<<<CONTRACT_GUIDANCE>>>\n<<<END_CONTRACT_GUIDANCE>>>"
    return text


# ---------------------------------------------------------------------------
# Orchestration wrapper (I/O boundary — never-raises)
# ---------------------------------------------------------------------------


async def fetch_contract_guidance(repo: Repository) -> ContractGuidance | None:
    """Fetch outcomes from the database and compute contract guidance.

    This is the top-level orchestration function called by API and CLI.
    It follows the never-raises contract: all exceptions are caught, logged,
    and ``None`` is returned on failure.

    Parameters
    ----------
    repo
        Repository instance for DB queries.

    Returns
    -------
    ContractGuidance | None
        Computed guidance, or ``None`` on insufficient data or error.
    """
    try:
        conn = repo._db.conn  # noqa: SLF001
        sql = (
            "SELECT "
            "  ABS(rc.delta) AS abs_delta, "
            "  CAST(julianday(rc.expiration) - julianday(rc.created_at) AS INTEGER) AS dte, "
            "  co.is_winner "
            "FROM contract_outcomes co "
            "JOIN recommended_contracts rc ON co.recommended_contract_id = rc.id "
            "WHERE rc.delta IS NOT NULL "
            "  AND co.is_winner IS NOT NULL "
            "ORDER BY co.collected_at DESC"
        )
        async with conn.execute(sql) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            logger.debug("No outcome rows with delta/DTE found for contract guidance")
            return None

        outcomes: list[OutcomeWithDelta] = []
        for row in rows:
            try:
                outcomes.append(
                    OutcomeWithDelta(
                        delta_at_entry=float(row["abs_delta"]),
                        dte_at_entry=max(0, int(row["dte"])),
                        is_winner=bool(row["is_winner"]),
                    )
                )
            except (ValueError, KeyError, TypeError) as exc:
                logger.debug("Skipping malformed outcome row: %s", exc)
                continue

        return compute_contract_guidance(outcomes)

    except Exception:
        logger.exception("Failed to fetch contract guidance")
        return None
