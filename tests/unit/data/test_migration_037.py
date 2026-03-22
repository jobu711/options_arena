"""Tests for migration 037 — recommendation_results table.

Tests verify:
  - Migration 037 runs cleanly on top of existing schema
  - recommendation_results table created with correct columns
  - Indexes on ticker and created_at columns
  - agent_predictions has recommendation_protocol column
  - Existing agent_predictions rows get 'debate_v1' default
  - Basic INSERT/SELECT on recommendation_results works
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from options_arena.data.database import Database

pytestmark = pytest.mark.db


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database with all migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


def _insert_prerequisite_rows() -> str:
    """SQL to insert prerequisite rows for foreign key constraints.

    Returns a multi-statement SQL string that creates a scan_run so the
    recommendation_results FK on scan_run_id is satisfied.
    """
    return (
        "INSERT INTO scan_runs "
        "(started_at, preset, tickers_scanned, tickers_scored, recommendations) "
        "VALUES ('2026-03-22T00:00:00+00:00', 'sp500', 100, 50, 5);"
    )


def _insert_agent_prediction_prerequisites() -> str:
    """SQL to insert prerequisite rows needed for agent_predictions FK constraints.

    Creates a scan_run and an ai_theses row so agent_predictions debate_id FK is satisfied.
    """
    return (
        "INSERT INTO scan_runs "
        "(started_at, preset, tickers_scanned, tickers_scored, recommendations) "
        "VALUES ('2026-03-22T00:00:00+00:00', 'sp500', 100, 50, 5);"
        "INSERT INTO ai_theses "
        "(scan_run_id, ticker, created_at) "
        "VALUES (1, 'AAPL', '2026-03-22T00:00:00+00:00');"
    )


@pytest.mark.asyncio
async def test_migration_applies_cleanly(db: Database) -> None:
    """Verify migration 037 applies on top of existing schema."""
    # db fixture already ran all migrations via connect().
    # Check that schema_version includes migration 37.
    async with db.conn.execute(
        "SELECT version FROM schema_version WHERE version = ?", (37,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None, "Migration 037 not recorded in schema_version"
    assert row[0] == 37


@pytest.mark.asyncio
async def test_recommendation_results_table_exists(db: Database) -> None:
    """Verify recommendation_results table is created with correct columns."""
    expected_columns = {
        "id": "INTEGER",
        "ticker": "TEXT",
        "scan_run_id": "INTEGER",
        "direction": "TEXT",
        "confidence": "REAL",
        "recommended_contract": "TEXT",
        "entry_price": "TEXT",
        "entry_criteria": "TEXT",
        "exit_criteria": "TEXT",
        "stop_loss": "TEXT",
        "take_profit": "TEXT",
        "position_size_pct": "REAL",
        "risk_reward_ratio": "REAL",
        "recommended_strategy": "TEXT",
        "summary": "TEXT",
        "key_factors_json": "TEXT",
        "risk_assessment": "TEXT",
        "agent_agreement_score": "REAL",
        "dissenting_desks_json": "TEXT",
        "assessments_json": "TEXT",
        "total_input_tokens": "INTEGER",
        "total_output_tokens": "INTEGER",
        "duration_ms": "INTEGER",
        "is_fallback": "INTEGER",
        "citation_density": "REAL",
        "position_rationale": "TEXT",
        "strategy_rationale": "TEXT",
        "max_loss_estimate": "TEXT",
        "model_used": "TEXT",
        "created_at": "TEXT",
    }
    async with db.conn.execute("PRAGMA table_info(recommendation_results)") as cursor:
        rows = await cursor.fetchall()
    # PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk
    columns = {row[1]: row[2] for row in rows}
    assert columns == expected_columns


@pytest.mark.asyncio
async def test_recommendation_results_indexes_exist(db: Database) -> None:
    """Verify indexes on ticker and created_at exist."""
    async with db.conn.execute("PRAGMA index_list(recommendation_results)") as cursor:
        rows = await cursor.fetchall()
    index_names = {row[1] for row in rows}
    assert "idx_recommendation_results_ticker" in index_names
    assert "idx_recommendation_results_created_at" in index_names


@pytest.mark.asyncio
async def test_agent_predictions_has_protocol_column(db: Database) -> None:
    """Verify agent_predictions has recommendation_protocol column."""
    async with db.conn.execute("PRAGMA table_info(agent_predictions)") as cursor:
        rows = await cursor.fetchall()
    column_names = {row[1] for row in rows}
    assert "recommendation_protocol" in column_names

    # Verify column type and default
    protocol_col = next(row for row in rows if row[1] == "recommendation_protocol")
    assert protocol_col[2] == "TEXT"  # type
    assert protocol_col[4] == "'debate_v1'"  # default value


@pytest.mark.asyncio
async def test_existing_predictions_backfilled(db: Database) -> None:
    """Verify existing agent_predictions get 'debate_v1' as default."""
    # Insert prerequisite rows (scan_run + ai_theses for FK)
    await db.conn.executescript(_insert_agent_prediction_prerequisites())

    # Insert a prediction row — should get 'debate_v1' as the default
    await db.conn.execute(
        "INSERT INTO agent_predictions "
        "(debate_id, agent_name, confidence, created_at) "
        "VALUES (?, ?, ?, ?)",
        (1, "trend", 0.8, "2026-03-22T00:00:00+00:00"),
    )
    await db.conn.commit()

    # Verify the recommendation_protocol column has the default value
    async with db.conn.execute(
        "SELECT recommendation_protocol FROM agent_predictions WHERE id = 1"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "debate_v1"


@pytest.mark.asyncio
async def test_recommendation_results_insert_and_read(db: Database) -> None:
    """Verify basic INSERT/SELECT on recommendation_results."""
    # Insert prerequisite scan_run for FK
    await db.conn.executescript(_insert_prerequisite_rows())

    key_factors = json.dumps(["Strong momentum", "High IV rank"])
    dissenting_desks = json.dumps(["contrarian"])
    assessments = json.dumps([{"desk": "trend", "direction": "bullish", "confidence": 0.85}])

    await db.conn.execute(
        "INSERT INTO recommendation_results "
        "(ticker, scan_run_id, direction, confidence, recommended_contract, "
        "entry_price, entry_criteria, exit_criteria, stop_loss, take_profit, "
        "position_size_pct, risk_reward_ratio, recommended_strategy, summary, "
        "key_factors_json, risk_assessment, agent_agreement_score, "
        "dissenting_desks_json, assessments_json, total_input_tokens, "
        "total_output_tokens, duration_ms, is_fallback, citation_density, "
        "model_used, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "AAPL",
            1,
            "bullish",
            0.82,
            "AAPL 190C 2026-04-18",
            "5.25",
            "Break above 188 resistance",
            "Close below 185 support",
            "3.50",
            "8.00",
            0.05,
            2.2,
            "long_call",
            "Strong bullish setup with momentum confirmation",
            key_factors,
            "Moderate risk — earnings in 14 days",
            0.83,
            dissenting_desks,
            assessments,
            1500,
            800,
            4200,
            0,
            0.65,
            "llama-3.3-70b-versatile",
            "2026-03-22T14:00:00+00:00",
        ),
    )
    await db.conn.commit()

    # Read back and verify
    async with db.conn.execute(
        "SELECT * FROM recommendation_results WHERE ticker = ?", ("AAPL",)
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    # Use positional access — row[0] is id, row[1] is ticker, etc.
    db.conn.row_factory = None  # ensure tuple access
    async with db.conn.execute(
        "SELECT ticker, direction, confidence, recommended_contract, "
        "entry_price, stop_loss, take_profit, position_size_pct, "
        "risk_reward_ratio, duration_ms, is_fallback, citation_density, "
        "model_used FROM recommendation_results WHERE id = 1"
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == "AAPL"
    assert row[1] == "bullish"
    assert row[2] == pytest.approx(0.82)
    assert row[3] == "AAPL 190C 2026-04-18"
    assert row[4] == "5.25"
    assert row[5] == "3.50"
    assert row[6] == "8.00"
    assert row[7] == pytest.approx(0.05)
    assert row[8] == pytest.approx(2.2)
    assert row[9] == 4200
    assert row[10] == 0
    assert row[11] == pytest.approx(0.65)
    assert row[12] == "llama-3.3-70b-versatile"


@pytest.mark.asyncio
async def test_recommendation_results_nullable_scan_run_id(db: Database) -> None:
    """Verify scan_run_id can be NULL (recommendation without a scan)."""
    key_factors = json.dumps(["Factor 1"])
    assessments = json.dumps([])

    await db.conn.execute(
        "INSERT INTO recommendation_results "
        "(ticker, scan_run_id, direction, confidence, recommended_contract, "
        "entry_price, entry_criteria, exit_criteria, "
        "position_size_pct, risk_reward_ratio, summary, "
        "key_factors_json, risk_assessment, assessments_json, "
        "duration_ms, model_used, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "TSLA",
            None,  # NULL scan_run_id
            "bearish",
            0.6,
            "TSLA 200P 2026-05-16",
            "8.50",
            "Break below 205",
            "Close above 210",
            0.03,
            1.8,
            "Bearish divergence on TSLA",
            key_factors,
            "High risk",
            assessments,
            3000,
            "llama-3.3-70b-versatile",
            "2026-03-22T15:00:00+00:00",
        ),
    )
    await db.conn.commit()

    async with db.conn.execute(
        "SELECT scan_run_id FROM recommendation_results WHERE ticker = ?", ("TSLA",)
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] is None  # scan_run_id should be NULL


@pytest.mark.asyncio
async def test_recommendation_results_defaults(db: Database) -> None:
    """Verify default values for is_fallback, citation_density, token counts, dissenting_desks."""
    key_factors = json.dumps(["Factor 1"])
    assessments = json.dumps([])

    # Insert without specifying columns that have defaults
    await db.conn.execute(
        "INSERT INTO recommendation_results "
        "(ticker, direction, confidence, recommended_contract, "
        "entry_price, entry_criteria, exit_criteria, "
        "position_size_pct, risk_reward_ratio, summary, "
        "key_factors_json, risk_assessment, assessments_json, "
        "duration_ms, model_used, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "MSFT",
            "bullish",
            0.7,
            "MSFT 400C 2026-04-18",
            "6.00",
            "Entry criteria",
            "Exit criteria",
            0.04,
            1.5,
            "Summary text",
            key_factors,
            "Risk assessment text",
            assessments,
            2500,
            "llama-3.3-70b-versatile",
            "2026-03-22T16:00:00+00:00",
        ),
    )
    await db.conn.commit()

    async with db.conn.execute(
        "SELECT is_fallback, citation_density, total_input_tokens, "
        "total_output_tokens, dissenting_desks_json "
        "FROM recommendation_results WHERE ticker = ?",
        ("MSFT",),
    ) as cursor:
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == 0  # is_fallback default
    assert row[1] == pytest.approx(0.0)  # citation_density default
    assert row[2] == 0  # total_input_tokens default
    assert row[3] == 0  # total_output_tokens default
    assert row[4] == "[]"  # dissenting_desks_json default
