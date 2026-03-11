"""Tests for Database class — async SQLite lifecycle and migration runner."""

from datetime import datetime
from pathlib import Path

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


@pytest.mark.critical
@pytest.mark.asyncio
async def test_wal_mode_enabled(tmp_path: Path) -> None:
    """PRAGMA journal_mode returns 'wal' after connect (file-backed DB)."""
    database = Database(tmp_path / "test.db")
    await database.connect()
    try:
        async with database.conn.execute("PRAGMA journal_mode") as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "wal"
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_foreign_keys_enabled(db: Database) -> None:
    """PRAGMA foreign_keys returns 1 after connect."""
    async with db.conn.execute("PRAGMA foreign_keys") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1


@pytest.mark.asyncio
async def test_all_tables_created(db: Database) -> None:
    """All business tables exist after connect + migration."""
    expected_tables = {
        "scan_runs",
        "ticker_scores",
        "service_cache",
        "ai_theses",
    }
    async with db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ) as cursor:
        rows = await cursor.fetchall()
    table_names = {row[0] for row in rows}
    assert expected_tables <= table_names


@pytest.mark.asyncio
async def test_schema_version_tracks_migration(db: Database) -> None:
    """schema_version table exists and records version 1."""
    async with db.conn.execute("SELECT version FROM schema_version") as cursor:
        rows = await cursor.fetchall()
    versions = [row[0] for row in rows]
    assert 1 in versions


@pytest.mark.asyncio
async def test_idempotent_connect(db: Database) -> None:
    """Calling connect() on an already-connected Database doesn't re-apply migrations."""
    # Get initial migration count
    async with db.conn.execute("SELECT COUNT(*) FROM schema_version") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    initial_count = row[0]

    # Call connect again
    await db.connect()

    # Count should be the same
    async with db.conn.execute("SELECT COUNT(*) FROM schema_version") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == initial_count


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    """Calling close() twice doesn't raise."""
    database = Database(":memory:")
    await database.connect()
    await database.close()
    await database.close()  # should not raise


@pytest.mark.asyncio
async def test_operation_after_close_raises() -> None:
    """Accessing conn after close raises RuntimeError."""
    database = Database(":memory:")
    await database.connect()
    await database.close()

    with pytest.raises(RuntimeError, match="not connected"):
        _ = database.conn


@pytest.mark.asyncio
async def test_memory_database_no_file_io() -> None:
    """:memory: database works without creating files."""
    database = Database(":memory:")
    await database.connect()

    # Can execute queries
    async with database.conn.execute("SELECT 1") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1

    await database.close()


@pytest.mark.asyncio
async def test_migration_applied_at_is_iso8601(db: Database) -> None:
    """Migration applied_at is a valid ISO 8601 datetime string."""
    query = "SELECT applied_at FROM schema_version WHERE version = 1"
    async with db.conn.execute(query) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    # Should parse without error
    applied_at = datetime.fromisoformat(row[0])
    assert applied_at.tzinfo is not None


@pytest.mark.asyncio
async def test_full_lifecycle() -> None:
    """connect → verify tables → close cycle completes cleanly."""
    database = Database(":memory:")
    await database.connect()

    # Tables exist
    async with database.conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='scan_runs'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1

    await database.close()

    # After close, conn raises
    with pytest.raises(RuntimeError):
        _ = database.conn
