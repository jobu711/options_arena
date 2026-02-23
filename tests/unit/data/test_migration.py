"""Tests for migration schema — verify table structure via PRAGMA introspection."""

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
async def test_all_six_tables_exist(db: Database) -> None:
    """Fresh database has all 6 business tables after connect."""
    expected = {
        "scan_runs",
        "ticker_scores",
        "service_cache",
        "ai_theses",
        "watchlists",
        "watchlist_tickers",
    }
    async with db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ) as cursor:
        rows = await cursor.fetchall()
    tables = {row[0] for row in rows}
    assert expected <= tables


@pytest.mark.asyncio
async def test_scan_runs_columns(db: Database) -> None:
    """scan_runs table has expected columns."""
    expected_columns = {
        "id": "INTEGER",
        "started_at": "TEXT",
        "completed_at": "TEXT",
        "preset": "TEXT",
        "tickers_scanned": "INTEGER",
        "tickers_scored": "INTEGER",
        "recommendations": "INTEGER",
    }
    async with db.conn.execute("PRAGMA table_info(scan_runs)") as cursor:
        rows = await cursor.fetchall()
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    columns = {row[1]: row[2] for row in rows}
    assert columns == expected_columns


@pytest.mark.asyncio
async def test_ticker_scores_columns(db: Database) -> None:
    """ticker_scores table has expected columns."""
    expected_columns = {
        "id": "INTEGER",
        "scan_run_id": "INTEGER",
        "ticker": "TEXT",
        "composite_score": "REAL",
        "direction": "TEXT",
        "signals_json": "TEXT",
    }
    async with db.conn.execute("PRAGMA table_info(ticker_scores)") as cursor:
        rows = await cursor.fetchall()
    columns = {row[1]: row[2] for row in rows}
    assert columns == expected_columns


@pytest.mark.asyncio
async def test_ticker_scores_index_exists(db: Database) -> None:
    """Index idx_ticker_scores_scan_id exists on ticker_scores."""
    async with db.conn.execute("PRAGMA index_list(ticker_scores)") as cursor:
        rows = await cursor.fetchall()
    # PRAGMA index_list returns: seq, name, unique, origin, partial
    index_names = {row[1] for row in rows}
    assert "idx_ticker_scores_scan_id" in index_names


@pytest.mark.asyncio
async def test_ticker_scores_foreign_key(db: Database) -> None:
    """ticker_scores.scan_run_id has FK to scan_runs.id."""
    async with db.conn.execute("PRAGMA foreign_key_list(ticker_scores)") as cursor:
        rows = await cursor.fetchall()
    # PRAGMA foreign_key_list returns: id, seq, table, from, to, ...
    fk_targets = [(row[2], row[3], row[4]) for row in rows]
    assert ("scan_runs", "scan_run_id", "id") in fk_targets
