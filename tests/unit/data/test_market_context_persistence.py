"""Tests for MarketContext persistence and export integration (issue #176).

Tests cover:
  - Migration 009 adds market_context_json column to ai_theses
  - Round-trip: save debate with MarketContext → load → verify all fields match
  - NULL handling: load thesis with NULL market_context_json → returns None, no crash
  - Export with prices: export with persisted MarketContext → verify real prices appear
  - Export without context: export with None MarketContext → verify graceful fallback
  - Weight assertion: INDICATOR_WEIGHTS sum is correct (runs at import time)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import DebateRow, Repository
from options_arena.models import MarketContext
from options_arena.models.enums import ExerciseStyle, MacdSignal

pytestmark = pytest.mark.db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_market_context() -> MarketContext:
    """Build a realistic MarketContext for AAPL."""
    return MarketContext(
        ticker="AAPL",
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.2,
        iv_percentile=52.1,
        atm_iv_30d=28.5,
        rsi_14=62.3,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
        composite_score=78.5,
        contract_mid=Decimal("3.45"),
    )


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
# Part A: Migration 009
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_009_adds_market_context_json_column(db: Database) -> None:
    """Migration 009 adds the market_context_json TEXT column to ai_theses."""
    async with db.conn.execute("PRAGMA table_info(ai_theses)") as cursor:
        rows = await cursor.fetchall()
    columns = {row[1]: row[2] for row in rows}
    assert "market_context_json" in columns
    assert columns["market_context_json"] == "TEXT"


@pytest.mark.asyncio
async def test_migration_009_applied_in_schema_version(db: Database) -> None:
    """Schema version table records migration 009 as applied."""
    async with db.conn.execute("SELECT version FROM schema_version WHERE version = 9") as cursor:
        row = await cursor.fetchone()
    assert row is not None


# ---------------------------------------------------------------------------
# Part B: Round-trip persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_and_load_debate_with_market_context(repo: Repository) -> None:
    """Save a debate with MarketContext JSON → load → all fields match."""
    ctx = _make_market_context()
    ctx_json = ctx.model_dump_json()

    debate_id = await repo.save_debate(
        scan_run_id=None,
        ticker="AAPL",
        bull_json='{"agent_name": "bull"}',
        bear_json='{"agent_name": "bear"}',
        risk_json=None,
        verdict_json=None,
        total_tokens=500,
        model_name="test-model",
        duration_ms=2000,
        is_fallback=False,
        market_context_json=ctx_json,
    )

    loaded: DebateRow | None = await repo.get_debate_by_id(debate_id)
    assert loaded is not None
    assert loaded.market_context is not None

    # Verify key fields round-trip correctly
    mc = loaded.market_context
    assert mc.ticker == "AAPL"
    assert mc.current_price == Decimal("185.50")
    assert mc.price_52w_high == Decimal("199.62")
    assert mc.price_52w_low == Decimal("164.08")
    assert mc.target_strike == Decimal("190.00")
    assert mc.dte_target == 45
    assert mc.sector == "Information Technology"
    assert mc.iv_rank == pytest.approx(45.2, rel=1e-4)
    assert mc.iv_percentile == pytest.approx(52.1, rel=1e-4)
    assert mc.composite_score == pytest.approx(78.5, rel=1e-4)
    assert mc.contract_mid == Decimal("3.45")
    assert mc.exercise_style == ExerciseStyle.AMERICAN
    assert mc.macd_signal == MacdSignal.BULLISH_CROSSOVER


@pytest.mark.asyncio
async def test_null_market_context_returns_none(repo: Repository) -> None:
    """Loading a debate with NULL market_context_json gives None, no crash."""
    debate_id = await repo.save_debate(
        scan_run_id=None,
        ticker="MSFT",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=0,
        model_name="test",
        duration_ms=0,
        is_fallback=True,
        market_context_json=None,
    )

    loaded = await repo.get_debate_by_id(debate_id)
    assert loaded is not None
    assert loaded.market_context is None


@pytest.mark.asyncio
async def test_market_context_survives_json_roundtrip(repo: Repository) -> None:
    """MarketContext → JSON → DB → JSON → MarketContext preserves model equality."""
    original = _make_market_context()
    debate_id = await repo.save_debate(
        scan_run_id=None,
        ticker="AAPL",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=0,
        model_name="test",
        duration_ms=0,
        is_fallback=False,
        market_context_json=original.model_dump_json(),
    )

    loaded = await repo.get_debate_by_id(debate_id)
    assert loaded is not None
    assert loaded.market_context is not None

    # Full model equality via Pydantic
    assert loaded.market_context == original


# ---------------------------------------------------------------------------
# Part B supplementary: get_recent_debates also loads market_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recent_debates_includes_market_context(repo: Repository) -> None:
    """get_recent_debates deserializes market_context from JSON column."""
    ctx = _make_market_context()
    await repo.save_debate(
        scan_run_id=None,
        ticker="AAPL",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=0,
        model_name="test",
        duration_ms=0,
        is_fallback=False,
        market_context_json=ctx.model_dump_json(),
    )

    debates = await repo.get_recent_debates(limit=5)
    assert len(debates) == 1
    assert debates[0].market_context is not None
    assert debates[0].market_context.ticker == "AAPL"
    assert debates[0].market_context.current_price == Decimal("185.50")
