"""Tests for agent_predictions table schema — migration and constraints.

Tests cover:
  - Migration 025 creates agent_predictions table with expected schema
  - UNIQUE(debate_id, agent_name) constraint enforced
  - FK constraint: debate_id must reference ai_theses
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data.database import Database

pytestmark = pytest.mark.db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database with all migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_creates_table(db: Database) -> None:
    """Verify migration 025 creates agent_predictions table with expected columns."""
    conn = db.conn
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_predictions'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None, "agent_predictions table should exist after migration"


@pytest.mark.asyncio
async def test_migration_creates_indexes(db: Database) -> None:
    """Verify migration 025 creates the expected indexes."""
    conn = db.conn
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_ap_%'"
    ) as cursor:
        rows = await cursor.fetchall()
    index_names = {row["name"] for row in rows}
    assert "idx_ap_debate" in index_names
    assert "idx_ap_contract" in index_names


@pytest.mark.asyncio
async def test_table_has_unique_constraint(db: Database) -> None:
    """Verify UNIQUE(debate_id, agent_name) constraint exists."""
    conn = db.conn
    # Insert a debate first (FK requirement)
    debate_id = 1
    await conn.execute(
        "INSERT INTO ai_theses (ticker, bull_json, bear_json, verdict_json, "
        "total_tokens, model_name, duration_ms, is_fallback, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("AAPL", "{}", "{}", "{}", 0, "test", 0, 0, NOW.isoformat()),
    )
    await conn.commit()

    # Insert first prediction
    await conn.execute(
        "INSERT INTO agent_predictions (debate_id, agent_name, confidence, created_at) "
        "VALUES (?, ?, ?, ?)",
        (debate_id, "bull", 0.8, NOW.isoformat()),
    )
    await conn.commit()

    # Duplicate should fail on strict INSERT
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO agent_predictions (debate_id, agent_name, confidence, created_at) "
            "VALUES (?, ?, ?, ?)",
            (debate_id, "bull", 0.9, NOW.isoformat()),
        )
    await conn.rollback()


@pytest.mark.asyncio
async def test_fk_constraint(db: Database) -> None:
    """Verify debate_id references ai_theses — invalid FK should fail."""
    conn = db.conn
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO agent_predictions (debate_id, agent_name, confidence, created_at) "
            "VALUES (?, ?, ?, ?)",
            (99999, "bull", 0.8, NOW.isoformat()),
        )
    await conn.rollback()
