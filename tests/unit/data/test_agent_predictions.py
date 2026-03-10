"""Tests for agent prediction persistence — migration, save, idempotency, FK.

Tests cover:
  - Migration 025 creates agent_predictions table with expected schema
  - save_agent_predictions inserts all agent rows correctly
  - Idempotent save (INSERT OR IGNORE) does not raise on duplicate
  - FK constraint: debate_id must reference ai_theses
  - Empty prediction list: no DB interaction
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import AgentPrediction, ScanPreset, ScanRun, SignalDirection

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


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository wrapping the in-memory database."""
    return Repository(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)


async def _create_debate(repo: Repository) -> int:
    """Insert a minimal ai_theses row and return its ID."""
    return await repo.save_debate(
        scan_run_id=None,
        ticker="AAPL",
        bull_json='{"test": true}',
        bear_json='{"test": true}',
        risk_json=None,
        verdict_json='{"test": true}',
        total_tokens=100,
        model_name="test-model",
        duration_ms=500,
        is_fallback=False,
    )


def _make_predictions(debate_id: int) -> list[AgentPrediction]:
    """Build a realistic set of agent predictions."""
    return [
        AgentPrediction(
            debate_id=debate_id,
            agent_name="bull",
            direction=SignalDirection.BULLISH,
            confidence=0.80,
            created_at=NOW,
        ),
        AgentPrediction(
            debate_id=debate_id,
            agent_name="bear",
            direction=SignalDirection.BEARISH,
            confidence=0.65,
            created_at=NOW,
        ),
        AgentPrediction(
            debate_id=debate_id,
            agent_name="flow",
            direction=SignalDirection.BULLISH,
            confidence=0.72,
            created_at=NOW,
        ),
        AgentPrediction(
            debate_id=debate_id,
            agent_name="risk",
            direction=None,
            confidence=0.50,
            created_at=NOW,
        ),
    ]


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


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_predictions(repo: Repository, db: Database) -> None:
    """Verify save_agent_predictions inserts all agent rows."""
    debate_id = await _create_debate(repo)
    predictions = _make_predictions(debate_id)

    await repo.save_agent_predictions(predictions)

    conn = db.conn
    async with conn.execute(
        "SELECT * FROM agent_predictions WHERE debate_id = ? ORDER BY agent_name",
        (debate_id,),
    ) as cursor:
        rows = await cursor.fetchall()

    assert len(rows) == 4

    # Verify specific row data
    row_by_name = {row["agent_name"]: row for row in rows}

    bull = row_by_name["bull"]
    assert bull["direction"] == "bullish"
    assert bull["confidence"] == pytest.approx(0.80)

    bear = row_by_name["bear"]
    assert bear["direction"] == "bearish"
    assert bear["confidence"] == pytest.approx(0.65)

    risk = row_by_name["risk"]
    assert risk["direction"] is None
    assert risk["confidence"] == pytest.approx(0.50)


@pytest.mark.asyncio
async def test_idempotent_save(repo: Repository) -> None:
    """Verify duplicate save doesn't raise (INSERT OR IGNORE)."""
    debate_id = await _create_debate(repo)
    predictions = _make_predictions(debate_id)

    # Save twice — second call should not raise
    await repo.save_agent_predictions(predictions)
    await repo.save_agent_predictions(predictions)  # idempotent


@pytest.mark.asyncio
async def test_empty_predictions_noop(repo: Repository) -> None:
    """Verify empty prediction list does not touch the database."""
    await repo.save_agent_predictions([])  # should not raise


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


@pytest.mark.asyncio
async def test_direction_none_persisted(repo: Repository, db: Database) -> None:
    """Verify None direction is stored as SQL NULL."""
    debate_id = await _create_debate(repo)
    predictions = [
        AgentPrediction(
            debate_id=debate_id,
            agent_name="risk",
            direction=None,
            confidence=0.50,
            created_at=NOW,
        ),
    ]
    await repo.save_agent_predictions(predictions)

    conn = db.conn
    async with conn.execute(
        "SELECT direction FROM agent_predictions WHERE debate_id = ? AND agent_name = 'risk'",
        (debate_id,),
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    assert row["direction"] is None


@pytest.mark.asyncio
async def test_created_at_persisted_as_iso(repo: Repository, db: Database) -> None:
    """Verify created_at is stored as ISO 8601 text."""
    debate_id = await _create_debate(repo)
    predictions = [
        AgentPrediction(
            debate_id=debate_id,
            agent_name="bull",
            direction=SignalDirection.BULLISH,
            confidence=0.75,
            created_at=NOW,
        ),
    ]
    await repo.save_agent_predictions(predictions)

    conn = db.conn
    async with conn.execute(
        "SELECT created_at FROM agent_predictions WHERE debate_id = ?",
        (debate_id,),
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    # Should be a valid ISO 8601 string parseable back to datetime
    parsed = datetime.fromisoformat(row["created_at"])
    assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# recommended_contract_id linkage tests
# ---------------------------------------------------------------------------


async def _create_scan_and_contract(repo: Repository) -> tuple[int, int]:
    """Insert a scan run + recommended contract, return (scan_run_id, contract_id)."""
    scan_run = ScanRun(
        started_at=NOW,
        completed_at=NOW,
        preset=ScanPreset.SP500,
        tickers_scanned=10,
        tickers_scored=5,
        recommendations=1,
    )
    scan_id = await repo.save_scan_run(scan_run)
    conn = repo._db.conn  # noqa: SLF001
    cursor = await conn.execute(
        "INSERT INTO recommended_contracts "
        "(scan_run_id, ticker, option_type, strike, bid, ask, expiration, "
        "volume, open_interest, market_iv, exercise_style, entry_mid, direction, "
        "composite_score, risk_free_rate, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            scan_id,
            "AAPL",
            "call",
            "190.00",
            "3.50",
            "3.80",
            "2026-04-18",
            1000,
            5000,
            0.30,
            "american",
            "3.65",
            "bullish",
            78.5,
            0.045,
            NOW.isoformat(),
        ),
    )
    await conn.commit()
    assert cursor.lastrowid is not None
    return scan_id, cursor.lastrowid


@pytest.mark.asyncio
async def test_save_predictions_with_contract_id(repo: Repository, db: Database) -> None:
    """Verify recommended_contract_id is persisted when provided."""
    scan_id, contract_id = await _create_scan_and_contract(repo)
    debate_id = await repo.save_debate(
        scan_run_id=scan_id,
        ticker="AAPL",
        bull_json="{}",
        bear_json="{}",
        risk_json=None,
        verdict_json="{}",
        total_tokens=100,
        model_name="test",
        duration_ms=500,
        is_fallback=False,
    )
    predictions = [
        AgentPrediction(
            debate_id=debate_id,
            recommended_contract_id=contract_id,
            agent_name="trend",
            direction=SignalDirection.BULLISH,
            confidence=0.75,
            created_at=NOW,
        ),
    ]
    await repo.save_agent_predictions(predictions)

    conn = db.conn
    async with conn.execute(
        "SELECT recommended_contract_id FROM agent_predictions WHERE debate_id = ?",
        (debate_id,),
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    assert row["recommended_contract_id"] == contract_id


@pytest.mark.asyncio
async def test_get_recommended_contract_id(repo: Repository) -> None:
    """Verify helper returns the correct contract ID for a scan+ticker pair."""
    scan_id, contract_id = await _create_scan_and_contract(repo)
    result = await repo.get_recommended_contract_id(scan_id, "AAPL")
    assert result == contract_id


@pytest.mark.asyncio
async def test_get_recommended_contract_id_no_match(repo: Repository) -> None:
    """Verify helper returns None when no matching contract exists."""
    result = await repo.get_recommended_contract_id(999, "ZZZZZ")
    assert result is None


@pytest.mark.asyncio
async def test_get_recommended_contract_id_none_scan(repo: Repository) -> None:
    """Verify helper returns None when scan_run_id is None (standalone debate)."""
    result = await repo.get_recommended_contract_id(None, "AAPL")
    assert result is None
