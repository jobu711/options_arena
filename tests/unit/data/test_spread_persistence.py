"""Tests for spread recommendation persistence.

Covers:
  - Save and retrieve spread recommendations.
  - All legs persisted with correct data.
  - Decimal precision preserved in database.
  - Migration 033 creates the expected tables.
  - get_spread_for_ticker returns None when no spread saved.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    ScanPreset,
    ScanRun,
    ScanSource,
)
from options_arena.models.enums import (
    ExerciseStyle,
    OptionType,
    PositionSide,
    SpreadType,
    VolRegime,
)
from options_arena.models.options import (
    OptionContract,
    OptionSpread,
    SpreadAnalysis,
    SpreadLeg,
)
from tests.factories import make_spread_analysis

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
    """Repository backed by in-memory database."""
    return Repository(db)


@pytest_asyncio.fixture
async def scan_run_id(repo: Repository) -> int:
    """Create a scan run and return its ID (needed as FK for spreads)."""
    scan_run = ScanRun(
        started_at=datetime(2026, 3, 15, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 15, 10, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        source=ScanSource.MANUAL,
        tickers_scanned=500,
        tickers_scored=450,
        recommendations=10,
    )
    return await repo.save_scan_run(scan_run)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_spread_with_known_decimals() -> SpreadAnalysis:
    """Create a SpreadAnalysis with specific Decimal values for precision testing."""
    long_contract = OptionContract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("150.00"),
        expiration=date.today() + timedelta(days=45),
        bid=Decimal("5.10"),
        ask=Decimal("5.30"),
        last=Decimal("5.20"),
        volume=200,
        open_interest=1000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.28,
    )
    short_contract = OptionContract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("155.00"),
        expiration=date.today() + timedelta(days=45),
        bid=Decimal("3.10"),
        ask=Decimal("3.30"),
        last=Decimal("3.20"),
        volume=150,
        open_interest=800,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.26,
    )
    long_leg = SpreadLeg(contract=long_contract, side=PositionSide.LONG, quantity=1)
    short_leg = SpreadLeg(contract=short_contract, side=PositionSide.SHORT, quantity=1)

    spread = OptionSpread(
        spread_type=SpreadType.VERTICAL,
        legs=[long_leg, short_leg],
        ticker="AAPL",
    )

    return SpreadAnalysis(
        spread=spread,
        net_premium=Decimal("1.95"),
        max_profit=Decimal("3.05"),
        max_loss=Decimal("1.95"),
        breakevens=[Decimal("151.95")],
        risk_reward_ratio=1.564,
        pop_estimate=0.52,
        strategy_rationale="Bull call debit spread: 150/155 (bullish bias, low IV regime)",
        iv_regime=VolRegime.LOW,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSpreadPersistence:
    """Tests for spread recommendation persistence in SQLite."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_spread(
        self,
        repo: Repository,
        scan_run_id: int,
    ) -> None:
        """Verify round-trip: save -> retrieve returns equivalent SpreadAnalysis."""
        original = _make_spread_with_known_decimals()
        spread_id = await repo.save_spread_recommendation(scan_run_id, "AAPL", original)
        assert spread_id > 0

        retrieved = await repo.get_spread_for_ticker(scan_run_id, "AAPL")
        assert retrieved is not None
        assert retrieved.spread.spread_type == original.spread.spread_type
        assert retrieved.net_premium == original.net_premium
        assert retrieved.max_profit == original.max_profit
        assert retrieved.max_loss == original.max_loss
        assert retrieved.pop_estimate == pytest.approx(original.pop_estimate, abs=0.01)
        assert retrieved.strategy_rationale == original.strategy_rationale
        assert retrieved.iv_regime == original.iv_regime

    @pytest.mark.asyncio
    async def test_spread_legs_persisted(
        self,
        repo: Repository,
        scan_run_id: int,
    ) -> None:
        """Verify all legs saved with correct strikes, sides, quantities."""
        original = _make_spread_with_known_decimals()
        await repo.save_spread_recommendation(scan_run_id, "AAPL", original)

        retrieved = await repo.get_spread_for_ticker(scan_run_id, "AAPL")
        assert retrieved is not None
        assert len(retrieved.spread.legs) == 2

        long_leg = retrieved.spread.legs[0]
        assert long_leg.side == PositionSide.LONG
        assert long_leg.contract.strike == Decimal("150.00")
        assert long_leg.contract.option_type == OptionType.CALL
        assert long_leg.quantity == 1

        short_leg = retrieved.spread.legs[1]
        assert short_leg.side == PositionSide.SHORT
        assert short_leg.contract.strike == Decimal("155.00")
        assert short_leg.contract.option_type == OptionType.CALL
        assert short_leg.quantity == 1

    @pytest.mark.asyncio
    async def test_decimal_precision_in_db(
        self,
        repo: Repository,
        scan_run_id: int,
    ) -> None:
        """Verify Decimal values stored as strings, restored without precision loss."""
        original = _make_spread_with_known_decimals()
        await repo.save_spread_recommendation(scan_run_id, "AAPL", original)

        retrieved = await repo.get_spread_for_ticker(scan_run_id, "AAPL")
        assert retrieved is not None

        # Decimal fields must round-trip exactly
        assert retrieved.net_premium == Decimal("1.95")
        assert retrieved.max_profit == Decimal("3.05")
        assert retrieved.max_loss == Decimal("1.95")

        # Leg strike prices must round-trip
        assert retrieved.spread.legs[0].contract.strike == Decimal("150.00")
        assert retrieved.spread.legs[1].contract.strike == Decimal("155.00")

        # Leg bid/ask must round-trip
        assert retrieved.spread.legs[0].contract.bid == Decimal("5.10")
        assert retrieved.spread.legs[0].contract.ask == Decimal("5.30")

    @pytest.mark.asyncio
    async def test_migration_033_applies(self, db: Database) -> None:
        """Verify migration creates both tables with correct schema."""
        conn = db.conn
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN "
            "('spread_recommendations', 'spread_legs') ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
        table_names = {row[0] for row in rows}
        assert "spread_recommendations" in table_names
        assert "spread_legs" in table_names

    @pytest.mark.asyncio
    async def test_no_spread_returns_none(
        self,
        repo: Repository,
        scan_run_id: int,
    ) -> None:
        """Verify get_spread_for_ticker returns None when no spread saved."""
        result = await repo.get_spread_for_ticker(scan_run_id, "AAPL")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_spread_recommendations_empty(
        self,
        repo: Repository,
        scan_run_id: int,
    ) -> None:
        """Verify get_spread_recommendations returns empty list when none saved."""
        results = await repo.get_spread_recommendations(scan_run_id)
        assert results == []

    @pytest.mark.asyncio
    async def test_get_spread_recommendations_multiple(
        self,
        repo: Repository,
        scan_run_id: int,
    ) -> None:
        """Verify multiple spreads retrieved for same scan run."""
        spread1 = _make_spread_with_known_decimals()
        spread2 = make_spread_analysis(
            strategy_rationale="Bear put debit spread",
            iv_regime=VolRegime.ELEVATED,
        )

        await repo.save_spread_recommendation(scan_run_id, "AAPL", spread1)
        await repo.save_spread_recommendation(scan_run_id, "MSFT", spread2)

        results = await repo.get_spread_recommendations(scan_run_id)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_spread_with_none_iv_regime(
        self,
        repo: Repository,
        scan_run_id: int,
    ) -> None:
        """Verify spread with iv_regime=None persists and retrieves correctly."""
        spread = make_spread_analysis(iv_regime=None)
        await repo.save_spread_recommendation(scan_run_id, "AAPL", spread)

        retrieved = await repo.get_spread_for_ticker(scan_run_id, "AAPL")
        assert retrieved is not None
        assert retrieved.iv_regime is None

    @pytest.mark.asyncio
    async def test_atomic_commit_false(
        self,
        repo: Repository,
        scan_run_id: int,
    ) -> None:
        """Verify commit=False does not auto-commit (data visible after explicit commit)."""
        spread = _make_spread_with_known_decimals()
        await repo.save_spread_recommendation(scan_run_id, "AAPL", spread, commit=False)
        # Data should be visible within the same connection (before commit)
        retrieved = await repo.get_spread_for_ticker(scan_run_id, "AAPL")
        assert retrieved is not None
