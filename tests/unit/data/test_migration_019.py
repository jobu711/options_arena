"""Tests for migration 019 — v2 agent columns on ai_theses.

Tests verify:
  - Migration 019 applies cleanly and adds all 5 columns
  - Existing rows get NULL for v2 JSON columns and 'v1' for debate_protocol
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from options_arena.data.database import Database


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database for each test."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest.mark.asyncio
async def test_migration_applies_cleanly(db: Database) -> None:
    """Migration 019 adds 5 columns to ai_theses: flow_json, fundamental_json,
    risk_v2_json, contrarian_json, debate_protocol."""
    expected_v2_columns = {
        "flow_json",
        "fundamental_json",
        "risk_v2_json",
        "contrarian_json",
        "debate_protocol",
    }
    async with db.conn.execute("PRAGMA table_info(ai_theses)") as cursor:
        rows = await cursor.fetchall()
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    column_names = {row[1] for row in rows}
    assert expected_v2_columns <= column_names, (
        f"Missing columns: {expected_v2_columns - column_names}"
    )


@pytest.mark.asyncio
async def test_v2_column_types(db: Database) -> None:
    """v2 columns have correct SQL types: TEXT for all 5."""
    async with db.conn.execute("PRAGMA table_info(ai_theses)") as cursor:
        rows = await cursor.fetchall()
    columns = {row[1]: row[2] for row in rows}
    assert columns["flow_json"] == "TEXT"
    assert columns["fundamental_json"] == "TEXT"
    assert columns["risk_v2_json"] == "TEXT"
    assert columns["contrarian_json"] == "TEXT"
    assert columns["debate_protocol"] == "TEXT"


@pytest.mark.asyncio
async def test_existing_rows_get_defaults(db: Database) -> None:
    """Existing ai_theses rows have NULL for v2 JSON columns and 'v1' for protocol."""
    # Insert a row using only pre-v2 columns (scan_run_id required by FK)
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
        "SELECT flow_json, fundamental_json, risk_v2_json, contrarian_json, debate_protocol "
        "FROM ai_theses WHERE ticker = ?",
        ("AAPL",),
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    # v2 JSON columns default to NULL
    assert row[0] is None  # flow_json
    assert row[1] is None  # fundamental_json
    assert row[2] is None  # risk_v2_json
    assert row[3] is None  # contrarian_json
    # debate_protocol defaults to 'v1'
    assert row[4] == "v1"


@pytest.mark.asyncio
async def test_debate_protocol_default_value(db: Database) -> None:
    """debate_protocol column has DEFAULT 'v1' in schema."""
    async with db.conn.execute("PRAGMA table_info(ai_theses)") as cursor:
        rows = await cursor.fetchall()
    # Find debate_protocol row: cid, name, type, notnull, dflt_value, pk
    protocol_rows = [row for row in rows if row[1] == "debate_protocol"]
    assert len(protocol_rows) == 1
    dflt_value = protocol_rows[0][4]
    assert dflt_value == "'v1'"
