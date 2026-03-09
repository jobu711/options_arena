"""Tests for migration 019 — agent columns on ai_theses.

Tests verify:
  - Migration 019 adds agent columns (flow_json, fundamental_json, contrarian_json,
    debate_protocol) and migration 026 renames risk_v2_json → risk_assessment_json
  - Existing rows get NULL for agent JSON columns and 'current' for debate_protocol
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from options_arena.data.database import Database

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database for each test."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest.mark.asyncio
async def test_migration_applies_cleanly(db: Database) -> None:
    """Migrations 019+026 add agent columns to ai_theses: flow_json, fundamental_json,
    risk_assessment_json (renamed from risk_v2_json), contrarian_json, debate_protocol."""
    expected_agent_columns = {
        "flow_json",
        "fundamental_json",
        "risk_assessment_json",
        "contrarian_json",
        "debate_protocol",
    }
    async with db.conn.execute("PRAGMA table_info(ai_theses)") as cursor:
        rows = await cursor.fetchall()
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    column_names = {row[1] for row in rows}
    assert expected_agent_columns <= column_names, (
        f"Missing columns: {expected_agent_columns - column_names}"
    )


@pytest.mark.asyncio
async def test_agent_column_types(db: Database) -> None:
    """Agent columns have correct SQL types: TEXT for all 5."""
    async with db.conn.execute("PRAGMA table_info(ai_theses)") as cursor:
        rows = await cursor.fetchall()
    columns = {row[1]: row[2] for row in rows}
    assert columns["flow_json"] == "TEXT"
    assert columns["fundamental_json"] == "TEXT"
    assert columns["risk_assessment_json"] == "TEXT"
    assert columns["contrarian_json"] == "TEXT"
    assert columns["debate_protocol"] == "TEXT"


@pytest.mark.asyncio
async def test_existing_rows_get_defaults(db: Database) -> None:
    """Existing ai_theses rows have NULL for agent JSON columns and 'current' for protocol."""
    # Insert a row using only pre-agent columns (scan_run_id required by FK)
    await db.conn.execute(
        "INSERT INTO scan_runs "
        "(started_at, preset, tickers_scanned, tickers_scored, recommendations) "
        "VALUES (?, ?, ?, ?, ?)",
        ("2026-03-01T00:00:00+00:00", "sp500", 100, 50, 5),
    )
    await db.conn.execute(
        """INSERT INTO ai_theses (scan_run_id, ticker, bull_json, bear_json, risk_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (1, "AAPL", '{"a":1}', '{"b":2}', '{"c":3}', "2026-03-01T00:00:00+00:00"),
    )
    await db.conn.commit()

    # Read back the row
    async with db.conn.execute(
        "SELECT flow_json, fundamental_json, risk_assessment_json, "
        "contrarian_json, debate_protocol "
        "FROM ai_theses WHERE ticker = ?",
        ("AAPL",),
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    # Agent JSON columns default to NULL
    assert row[0] is None  # flow_json
    assert row[1] is None  # fundamental_json
    assert row[2] is None  # risk_assessment_json
    assert row[3] is None  # contrarian_json
    # debate_protocol defaults to 'v1' (migration 019 column DEFAULT);
    # migration 026 normalizes pre-existing rows but can't alter the column default
    assert row[4] == "v1"


@pytest.mark.asyncio
async def test_debate_protocol_column_exists(db: Database) -> None:
    """debate_protocol column exists in schema (kept for historical data)."""
    async with db.conn.execute("PRAGMA table_info(ai_theses)") as cursor:
        rows = await cursor.fetchall()
    # Find debate_protocol row: cid, name, type, notnull, dflt_value, pk
    protocol_rows = [row for row in rows if row[1] == "debate_protocol"]
    assert len(protocol_rows) == 1
