"""Migrate ai_theses rows to recommendation_results table.

Issue: #736 — (DEFERRED) Plan data migration for ai_theses sunset

This is a SKELETON script — placeholder functions document the migration logic
without executing production changes. Each function includes schema documentation
and field mapping constants.

Usage (when activated):
    python tools/migrate_theses.py                # Execute migration
    python tools/migrate_theses.py --dry-run      # Preview without writing
    python tools/migrate_theses.py --verify       # Verify post-migration
    python tools/migrate_theses.py --rollback     # Remove migrated rows
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema documentation
# ---------------------------------------------------------------------------

# ai_theses columns (source) — built across migrations 001, 002, 003, 004, 005,
# 009, 019, 026:
AI_THESES_COLUMNS: list[str] = [
    "id",
    "scan_run_id",
    "ticker",
    "bull_json",
    "bear_json",
    "risk_json",
    "verdict_json",
    "vol_json",
    "rebuttal_json",
    "total_tokens",
    "model_name",
    "duration_ms",
    "is_fallback",
    "created_at",
    "debate_mode",
    "citation_density",
    "market_context_json",
    "flow_json",
    "fundamental_json",
    "risk_assessment_json",
    "contrarian_json",
    "debate_protocol",
]

# recommendation_results columns (target) — migration 037:
RECOMMENDATION_RESULTS_COLUMNS: list[str] = [
    "ticker",
    "scan_run_id",
    "direction",
    "confidence",
    "recommended_contract",
    "entry_price",
    "entry_criteria",
    "exit_criteria",
    "stop_loss",
    "take_profit",
    "position_size_pct",
    "risk_reward_ratio",
    "recommended_strategy",
    "summary",
    "key_factors_json",
    "risk_assessment",
    "agent_agreement_score",
    "dissenting_desks_json",
    "assessments_json",
    "total_input_tokens",
    "total_output_tokens",
    "duration_ms",
    "is_fallback",
    "citation_density",
    "position_rationale",
    "strategy_rationale",
    "max_loss_estimate",
    "model_used",
    "created_at",
]

# ---------------------------------------------------------------------------
# Field mapping constants
# ---------------------------------------------------------------------------

# Direct 1:1 mappings: ai_theses column -> recommendation_results column
DIRECT_FIELD_MAP: dict[str, str] = {
    "ticker": "ticker",
    "scan_run_id": "scan_run_id",
    "duration_ms": "duration_ms",
    "is_fallback": "is_fallback",
    "citation_density": "citation_density",
    "created_at": "created_at",
    "model_name": "model_used",
}

# Fields extracted from verdict_json (TradeThesis / ExtendedTradeThesis)
VERDICT_FIELD_MAP: dict[str, str] = {
    "direction": "direction",
    "confidence": "confidence",
    "summary": "summary",
    "risk_assessment": "risk_assessment",
    "recommended_strategy": "recommended_strategy",
    # Extended-only fields (may be absent in base TradeThesis):
    "agent_agreement_score": "agent_agreement_score",
}

# Default values for fields that have no ai_theses equivalent
SYNTHESIZED_DEFAULTS: dict[str, Any] = {
    "entry_price": "0.00",
    "entry_criteria": "Legacy debate -- no entry criteria specified",
    "exit_criteria": "Legacy debate -- no exit criteria specified",
    "stop_loss": None,
    "take_profit": None,
    "position_size_pct": 0.02,
    "risk_reward_ratio": 0.0,
    "position_rationale": "Migrated from legacy debate system",
}

# Token split ratio: ai_theses stores a single total_tokens count.
# We estimate 60% input, 40% output for the split.
TOKEN_INPUT_RATIO = 0.6
TOKEN_OUTPUT_RATIO = 0.4

# Desk name mapping for assessment reconstruction
AGENT_JSON_TO_DESK: dict[str, str] = {
    "bull_json": "trend",
    "vol_json": "volatility",
    "flow_json": "flow",
    "fundamental_json": "fundamental",
    "risk_assessment_json": "risk",
    "contrarian_json": "contrarian",
}

# Marker value used to identify migrated rows (for rollback)
MIGRATION_MARKER = "Migrated from legacy debate system"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MigrationResult:
    """Summary of a migration run."""

    total_source_rows: int
    migrated_count: int
    skipped_count: int
    error_count: int
    errors: list[str]


@dataclass
class VerificationResult:
    """Summary of post-migration verification."""

    source_count: int
    target_count: int
    missing_tickers: list[str]
    sample_checks_passed: int
    sample_checks_failed: int


# ---------------------------------------------------------------------------
# Placeholder functions
# ---------------------------------------------------------------------------


def _parse_verdict_json(verdict_json: str | None) -> dict[str, Any] | None:
    """Parse verdict_json into a dict, trying ExtendedTradeThesis then TradeThesis.

    Returns None if parsing fails (row should be skipped).

    The actual implementation would use:
        from options_arena.models import ExtendedTradeThesis, TradeThesis
        try:
            thesis = ExtendedTradeThesis.model_validate_json(verdict_json)
        except ValidationError:
            thesis = TradeThesis.model_validate_json(verdict_json)
    """
    if not verdict_json:
        return None

    try:
        return json.loads(verdict_json)
    except (json.JSONDecodeError, TypeError):
        return None


def _reconstruct_assessments(row: dict[str, Any]) -> str:
    """Reconstruct assessments_json from individual agent JSON columns.

    Iterates over AGENT_JSON_TO_DESK, parses each non-NULL agent JSON column,
    and builds a list of assessment dicts with desk, direction, confidence,
    and summary fields.

    Returns a JSON string (array of assessment objects).
    """
    assessments: list[dict[str, Any]] = []

    for column, desk_name in AGENT_JSON_TO_DESK.items():
        raw_json = row.get(column)
        if not raw_json:
            continue

        try:
            agent_data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Failed to parse %s for thesis id=%s", column, row.get("id")
            )
            continue

        # Extract direction and confidence based on agent type
        if desk_name == "contrarian":
            direction = agent_data.get("dissent_direction", "neutral")
            confidence = agent_data.get("dissent_confidence", 0.0)
            summary = agent_data.get("primary_challenge", "")
        elif desk_name == "risk":
            direction = "neutral"
            confidence = agent_data.get("confidence", 0.0)
            summary = agent_data.get("max_loss_estimate", "")
        elif desk_name == "trend":
            direction = agent_data.get("direction", "neutral")
            confidence = agent_data.get("confidence", 0.0)
            summary = agent_data.get("argument", "")
        elif desk_name == "volatility":
            direction = agent_data.get("direction", "neutral")
            confidence = agent_data.get("confidence", 0.0)
            summary = agent_data.get("strategy_rationale", "")
        elif desk_name == "flow":
            direction = agent_data.get("direction", "neutral")
            confidence = agent_data.get("confidence", 0.0)
            summary = agent_data.get("gex_interpretation", "")
        elif desk_name == "fundamental":
            direction = agent_data.get("direction", "neutral")
            confidence = agent_data.get("confidence", 0.0)
            summary = agent_data.get("earnings_assessment", "")
        else:
            direction = agent_data.get("direction", "neutral")
            confidence = agent_data.get("confidence", 0.0)
            summary = ""

        assessments.append(
            {
                "desk": desk_name,
                "direction": direction,
                "confidence": confidence,
                "summary": summary,
                "key_factors": agent_data.get("key_points", []),
            }
        )

    return json.dumps(assessments)


def _extract_strategy_rationale(row: dict[str, Any]) -> str:
    """Extract strategy_rationale from vol_json if available."""
    vol_json = row.get("vol_json")
    if not vol_json:
        return ""
    try:
        vol_data = json.loads(vol_json)
        return str(vol_data.get("strategy_rationale", ""))
    except (json.JSONDecodeError, TypeError):
        return ""


def _extract_max_loss_estimate(row: dict[str, Any]) -> str:
    """Extract max_loss_estimate from risk_assessment_json if available."""
    risk_json = row.get("risk_assessment_json")
    if not risk_json:
        return ""
    try:
        risk_data = json.loads(risk_json)
        return str(risk_data.get("max_loss_estimate", ""))
    except (json.JSONDecodeError, TypeError):
        return ""


def migrate_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Transform a single ai_theses row into a recommendation_results row.

    Args:
        row: Dict representing a row from ai_theses (column name -> value).

    Returns:
        Dict ready for INSERT into recommendation_results, or None if the row
        cannot be migrated (e.g., unparseable verdict_json).

    Field mapping logic:
        1. Copy direct-mapped fields (ticker, scan_run_id, etc.)
        2. Parse verdict_json for direction, confidence, summary, etc.
        3. Split total_tokens into input/output estimates
        4. Reconstruct assessments_json from individual agent JSON columns
        5. Apply synthesized defaults for fields with no ai_theses equivalent
        6. Extract strategy_rationale from vol_json
        7. Extract max_loss_estimate from risk_assessment_json
    """
    # Step 1: Direct mappings
    result: dict[str, Any] = {}
    for source_col, target_col in DIRECT_FIELD_MAP.items():
        result[target_col] = row.get(source_col)

    # Step 2: Parse verdict
    verdict = _parse_verdict_json(row.get("verdict_json"))
    if verdict is None:
        logger.warning(
            "Skipping thesis id=%s: unparseable verdict_json", row.get("id")
        )
        return None

    for verdict_field, target_col in VERDICT_FIELD_MAP.items():
        result[target_col] = verdict.get(verdict_field)

    # Ensure direction has a value
    if not result.get("direction"):
        result["direction"] = "neutral"

    # Ensure confidence is in range
    conf = result.get("confidence")
    if conf is None or not isinstance(conf, (int, float)):
        result["confidence"] = 0.0
    else:
        result["confidence"] = max(0.0, min(1.0, float(conf)))

    # key_factors -> key_factors_json
    key_factors = verdict.get("key_factors", [])
    result["key_factors_json"] = json.dumps(key_factors)

    # dissenting_agents -> dissenting_desks_json (Extended only)
    dissenting = verdict.get("dissenting_agents", [])
    result["dissenting_desks_json"] = json.dumps(dissenting)

    # recommended_contract placeholder
    ticker = row.get("ticker", "UNKNOWN")
    result["recommended_contract"] = f"{ticker} legacy debate"

    # Step 3: Token split
    total_tokens = row.get("total_tokens", 0) or 0
    result["total_input_tokens"] = int(total_tokens * TOKEN_INPUT_RATIO)
    result["total_output_tokens"] = int(total_tokens * TOKEN_OUTPUT_RATIO)

    # Step 4: Reconstruct assessments
    result["assessments_json"] = _reconstruct_assessments(row)

    # Step 5: Synthesized defaults
    for field, default in SYNTHESIZED_DEFAULTS.items():
        if field not in result:
            result[field] = default

    # Step 6: Strategy rationale from vol_json
    result["strategy_rationale"] = _extract_strategy_rationale(row)

    # Step 7: Max loss estimate from risk_assessment_json
    result["max_loss_estimate"] = _extract_max_loss_estimate(row)

    return result


def verify_migration(
    source_count: int,
    target_count_before: int,
    target_count_after: int,
) -> VerificationResult:
    """Verify that migration produced the expected number of rows.

    Args:
        source_count: Number of rows in ai_theses.
        target_count_before: Number of rows in recommendation_results before migration.
        target_count_after: Number of rows in recommendation_results after migration.

    Returns:
        VerificationResult with counts and any discrepancies.

    Verification checks:
        1. target_count_after >= target_count_before + source_count
           (some source rows may be skipped due to parse errors)
        2. Every ticker in ai_theses has at least one row in recommendation_results
        3. Spot-check: sample 10 rows, verify field values match expectations
    """
    migrated = target_count_after - target_count_before

    return VerificationResult(
        source_count=source_count,
        target_count=target_count_after,
        missing_tickers=[],  # Placeholder: actual impl queries both tables
        sample_checks_passed=0,
        sample_checks_failed=0,
    )


def rollback(marker: str = MIGRATION_MARKER) -> int:
    """Remove all recommendation_results rows created by the migration.

    Identifies migrated rows by the position_rationale marker field.

    Args:
        marker: The position_rationale value used to identify migrated rows.

    Returns:
        Number of rows deleted.

    SQL:
        DELETE FROM recommendation_results
        WHERE position_rationale = ?
    """
    logger.info("Rollback requested: would delete rows with marker=%r", marker)
    return 0  # Placeholder


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate action."""
    parser = argparse.ArgumentParser(
        description="Migrate ai_theses rows to recommendation_results.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without writing to the database.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run post-migration verification checks.",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Remove all rows created by a previous migration run.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/options_arena.db"),
        help="Path to the SQLite database file (default: data/options_arena.db).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.rollback:
        logger.info("=== ROLLBACK MODE ===")
        deleted = rollback()
        logger.info("Rolled back %d rows.", deleted)
    elif args.verify:
        logger.info("=== VERIFICATION MODE ===")
        result = verify_migration(
            source_count=0,
            target_count_before=0,
            target_count_after=0,
        )
        logger.info(
            "Verification: source=%d, target=%d, missing_tickers=%d",
            result.source_count,
            result.target_count,
            len(result.missing_tickers),
        )
    else:
        mode = "DRY RUN" if args.dry_run else "EXECUTE"
        logger.info("=== MIGRATION MODE: %s ===", mode)
        logger.info("Database: %s", args.db)
        logger.info(
            "This is a skeleton script. Actual migration logic is not yet implemented."
        )
        logger.info(
            "See docs/plans/debate-sunset-migration.md for the full migration plan."
        )


if __name__ == "__main__":
    main()
