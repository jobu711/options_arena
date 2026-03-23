"""Generate regression test fixtures from historical wrong recommendations.

Queries the outcomes table for recommendations that were high-confidence
but had negative P&L, then serializes the market context and assessment
as JSON fixtures for regression testing.

Usage:
    python tools/generate_regression_fixtures.py [--min-confidence 0.6] [--max-pnl -20.0]
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Project root → data directory
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"
_FIXTURES_DIR = _PROJECT_ROOT / "tests" / "regression" / "fixtures"


async def generate_fixtures(
    min_confidence: float = 0.6,
    max_pnl: float = -20.0,
) -> int:
    """Query outcomes for wrong recommendations and serialize as fixtures.

    Parameters
    ----------
    min_confidence
        Minimum confidence of the original recommendation (higher = more wrong).
    max_pnl
        Maximum P&L percentage (negative = lost money).

    Returns
    -------
    int
        Number of fixtures generated.
    """
    from options_arena.data import Database, Repository  # noqa: PLC0415

    db = Database(_DATA_DIR / "options_arena.db")
    await db.connect()
    repo = Repository(db)

    try:
        # Query outcomes with recommendation data
        conn = repo._db.conn
        query = (
            "SELECT rc.ticker, rc.direction, rc.confidence, "
            "co.pnl_pct, co.holding_days, co.collected_at "
            "FROM contract_outcomes co "
            "JOIN recommended_contracts rc ON co.contract_id = rc.id "
            "WHERE rc.confidence >= ? AND co.pnl_pct <= ? "
            "ORDER BY co.pnl_pct ASC "
            "LIMIT 20"
        )
        async with conn.execute(query, (min_confidence, max_pnl)) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            logger.info("No high-confidence failures found matching criteria")
            return 0

        _FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
        count = 0

        for row in rows:
            ticker = str(row["ticker"])
            direction = str(row["direction"])
            confidence = float(row["confidence"])
            pnl_pct = float(row["pnl_pct"])
            holding_days = int(row["holding_days"])

            fixture = {
                "ticker": ticker,
                "original_direction": direction,
                "original_confidence": confidence,
                "actual_pnl_pct": pnl_pct,
                "holding_days": holding_days,
                "description": (
                    f"High-confidence {direction} call on {ticker} "
                    f"(conf={confidence:.2f}) lost {pnl_pct:.1f}% "
                    f"over {holding_days} days"
                ),
            }

            fixture_path = _FIXTURES_DIR / f"{ticker.lower()}_{direction}_{count}.json"
            fixture_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
            logger.info("Generated fixture: %s", fixture_path.name)
            count += 1

        logger.info("Generated %d regression fixtures in %s", count, _FIXTURES_DIR)
        return count

    finally:
        await db.close()


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate regression test fixtures")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.6,
        help="Minimum confidence threshold (default: 0.6)",
    )
    parser.add_argument(
        "--max-pnl",
        type=float,
        default=-20.0,
        help="Maximum P&L percentage (default: -20.0)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    count = asyncio.run(generate_fixtures(args.min_confidence, args.max_pnl))
    sys.exit(0 if count >= 0 else 1)


if __name__ == "__main__":
    main()
