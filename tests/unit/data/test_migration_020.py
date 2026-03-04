"""Tests for migration 020 — fix contract_outcomes UNIQUE constraint.

Tests verify:
  - Migration 020 recreates contract_outcomes with UNIQUE(recommended_contract_id, holding_days)
  - Existing data is preserved through the table recreation
  - Migration is idempotent (safe to run twice)
  - Duplicate (recommended_contract_id, holding_days) pairs are rejected after migration
"""

from __future__ import annotations

import sqlite3

import pytest
import pytest_asyncio

from options_arena.data.database import Database


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database with all migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


def _insert_prerequisite_rows() -> str:
    """SQL to insert prerequisite rows for foreign key constraints.

    Returns a multi-statement SQL string that creates a scan_run and
    a recommended_contract so contract_outcomes FK is satisfied.
    """
    return (
        "INSERT INTO scan_runs "
        "(started_at, preset, tickers_scanned, tickers_scored, recommendations) "
        "VALUES ('2026-03-01T00:00:00+00:00', 'sp500', 100, 50, 5);"
        "INSERT INTO recommended_contracts "
        "(scan_run_id, ticker, option_type, strike, expiration, bid, ask, "
        "volume, open_interest, market_iv, exercise_style, entry_stock_price, "
        "entry_mid, direction, composite_score, risk_free_rate, created_at) "
        "VALUES (1, 'AAPL', 'call', '150.00', '2026-06-20', '5.00', '5.50', "
        "1000, 5000, 0.35, 'american', '148.50', '5.25', 'bullish', 82.5, "
        "0.045, '2026-03-01T00:00:00+00:00');"
    )


@pytest.mark.asyncio
async def test_migration_creates_correct_constraint(db: Database) -> None:
    """Verify UNIQUE(recommended_contract_id, holding_days) exists after migration."""
    async with db.conn.execute("PRAGMA index_list(contract_outcomes)") as cursor:
        rows = await cursor.fetchall()

    # Find unique indexes (unique=1)
    unique_indexes = [row for row in rows if row[2] == 1]
    assert len(unique_indexes) >= 1, "Expected at least one UNIQUE index on contract_outcomes"

    # Verify the unique index covers (recommended_contract_id, holding_days)
    found_constraint = False
    for idx_row in unique_indexes:
        idx_name = idx_row[1]
        async with db.conn.execute(
            f"PRAGMA index_info('{idx_name}')"  # noqa: S608
        ) as cursor:
            idx_columns = await cursor.fetchall()
        column_names = {col[2] for col in idx_columns}
        if column_names == {"recommended_contract_id", "holding_days"}:
            found_constraint = True
            break

    assert found_constraint, (
        "UNIQUE(recommended_contract_id, holding_days) constraint not found "
        "on contract_outcomes table"
    )


@pytest.mark.asyncio
async def test_migration_preserves_existing_data(db: Database) -> None:
    """Verify all rows from old table are preserved after migration.

    Since we run all migrations on connect(), we insert data after connect
    to verify the table structure is correct and data round-trips.
    """
    # Insert prerequisite rows + outcome data
    await db.conn.executescript(_insert_prerequisite_rows())
    await db.conn.execute(
        "INSERT INTO contract_outcomes "
        "(recommended_contract_id, holding_days, exit_stock_price, "
        "exit_contract_mid, exit_contract_bid, exit_contract_ask, "
        "exit_date, stock_return_pct, contract_return_pct, is_winner, "
        "dte_at_exit, collection_method, collected_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            5,
            "152.00",
            "6.10",
            "6.00",
            "6.20",
            "2026-03-06T00:00:00+00:00",
            2.36,
            16.19,
            1,
            106,
            "live_quote",
            "2026-03-06T12:00:00+00:00",
        ),
    )
    await db.conn.execute(
        "INSERT INTO contract_outcomes "
        "(recommended_contract_id, holding_days, exit_stock_price, "
        "exit_contract_mid, exit_contract_bid, exit_contract_ask, "
        "exit_date, stock_return_pct, contract_return_pct, is_winner, "
        "dte_at_exit, collection_method, collected_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            10,
            "155.00",
            "7.50",
            "7.40",
            "7.60",
            "2026-03-11T00:00:00+00:00",
            4.38,
            42.86,
            1,
            101,
            "live_quote",
            "2026-03-11T12:00:00+00:00",
        ),
    )
    await db.conn.commit()

    # Verify both rows exist
    async with db.conn.execute("SELECT COUNT(*) FROM contract_outcomes") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 2

    # Verify specific data survived
    async with db.conn.execute(
        "SELECT exit_stock_price, holding_days FROM contract_outcomes ORDER BY holding_days"
    ) as cursor:
        rows = await cursor.fetchall()
    assert rows[0][0] == "152.00"
    assert rows[0][1] == 5
    assert rows[1][0] == "155.00"
    assert rows[1][1] == 10


@pytest.mark.asyncio
async def test_migration_is_idempotent(db: Database) -> None:
    """Verify running migration 020 twice does not error or corrupt data."""
    # db already has all migrations applied via connect().
    # Run migration 020 SQL again manually — should not error.
    from pathlib import Path

    migration_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "migrations"
        / "020_fix_outcomes_constraint.sql"
    )
    sql_content = migration_path.read_text(encoding="utf-8")

    # Insert some data first
    await db.conn.executescript(_insert_prerequisite_rows())
    await db.conn.execute(
        "INSERT INTO contract_outcomes "
        "(recommended_contract_id, holding_days, collection_method, collected_at) "
        "VALUES (?, ?, ?, ?)",
        (1, 5, "live_quote", "2026-03-06T12:00:00+00:00"),
    )
    await db.conn.commit()

    # Run migration 020 again (simulating re-run)
    await db.conn.executescript(sql_content)

    # Data should still be intact
    async with db.conn.execute("SELECT COUNT(*) FROM contract_outcomes") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1

    # Table should still have the correct constraint
    async with db.conn.execute("PRAGMA index_list(contract_outcomes)") as cursor:
        rows = await cursor.fetchall()
    unique_indexes = [row for row in rows if row[2] == 1]
    assert len(unique_indexes) >= 1


@pytest.mark.asyncio
async def test_duplicate_outcomes_rejected_after_migration(db: Database) -> None:
    """After migration, inserting duplicate (contract_id, holding_days) raises IntegrityError."""
    # Insert prerequisite rows
    await db.conn.executescript(_insert_prerequisite_rows())

    # Insert first outcome
    await db.conn.execute(
        "INSERT INTO contract_outcomes "
        "(recommended_contract_id, holding_days, collection_method, collected_at) "
        "VALUES (?, ?, ?, ?)",
        (1, 5, "live_quote", "2026-03-06T12:00:00+00:00"),
    )
    await db.conn.commit()

    # Attempt duplicate — same (recommended_contract_id, holding_days) pair
    with pytest.raises(sqlite3.IntegrityError):
        await db.conn.execute(
            "INSERT INTO contract_outcomes "
            "(recommended_contract_id, holding_days, collection_method, collected_at) "
            "VALUES (?, ?, ?, ?)",
            (1, 5, "live_quote", "2026-03-07T12:00:00+00:00"),
        )


@pytest.mark.asyncio
async def test_contract_outcomes_table_columns(db: Database) -> None:
    """Verify contract_outcomes has all expected columns after migration."""
    expected_columns = {
        "id": "INTEGER",
        "recommended_contract_id": "INTEGER",
        "exit_stock_price": "TEXT",
        "exit_contract_mid": "TEXT",
        "exit_contract_bid": "TEXT",
        "exit_contract_ask": "TEXT",
        "exit_date": "TEXT",
        "stock_return_pct": "REAL",
        "contract_return_pct": "REAL",
        "is_winner": "INTEGER",
        "holding_days": "INTEGER",
        "dte_at_exit": "INTEGER",
        "collection_method": "TEXT",
        "collected_at": "TEXT",
    }
    async with db.conn.execute("PRAGMA table_info(contract_outcomes)") as cursor:
        rows = await cursor.fetchall()
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    columns = {row[1]: row[2] for row in rows}
    assert columns == expected_columns


@pytest.mark.asyncio
async def test_contract_outcomes_index_exists(db: Database) -> None:
    """Index idx_co_rec_id exists on contract_outcomes after migration."""
    async with db.conn.execute("PRAGMA index_list(contract_outcomes)") as cursor:
        rows = await cursor.fetchall()
    index_names = {row[1] for row in rows}
    assert "idx_co_rec_id" in index_names
