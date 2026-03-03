"""Tests for outcome repository methods.

Covers:
  - ContractOutcome save/get roundtrip with all fields intact.
  - Decimal precision preserved through TEXT storage.
  - get_contracts_needing_outcomes returns contracts without outcomes.
  - Contracts with existing outcomes for the period are excluded.
  - has_outcome returns True for existing outcome.
  - has_outcome returns False for missing outcome.
  - Multiple outcomes per contract (T+1, T+5, T+10, T+20).
  - UNIQUE(recommended_contract_id, exit_date) enforced.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    ContractOutcome,
    ExerciseStyle,
    OptionType,
    OutcomeCollectionMethod,
    RecommendedContract,
    ScanPreset,
    ScanRun,
    SignalDirection,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database for each test."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository backed by the in-memory database."""
    return Repository(db)


@pytest_asyncio.fixture
async def scan_id(repo: Repository) -> int:
    """Pre-created scan run for foreign key references."""
    scan = ScanRun(
        started_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        tickers_scanned=500,
        tickers_scored=450,
        recommendations=5,
    )
    return await repo.save_scan_run(scan)


@pytest_asyncio.fixture
async def contract_id(repo: Repository, scan_id: int) -> int:
    """Pre-created recommended contract for foreign key references.

    Returns the DB-assigned contract ID.
    """
    contract = RecommendedContract(
        scan_run_id=scan_id,
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("185.50"),
        expiration=date(2026, 4, 15),
        bid=Decimal("5.20"),
        ask=Decimal("5.60"),
        volume=1200,
        open_interest=5000,
        market_iv=0.32,
        exercise_style=ExerciseStyle.AMERICAN,
        entry_stock_price=Decimal("182.30"),
        entry_mid=Decimal("5.40"),
        direction=SignalDirection.BULLISH,
        composite_score=78.5,
        risk_free_rate=0.045,
        created_at=datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC),
    )
    await repo.save_recommended_contracts(scan_id, [contract])
    contracts = await repo.get_contracts_for_scan(scan_id)
    assert len(contracts) == 1
    assert contracts[0].id is not None
    return contracts[0].id  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_outcome(contract_id: int, **overrides: object) -> ContractOutcome:
    """Build a ContractOutcome with sensible defaults."""
    defaults: dict[str, object] = {
        "recommended_contract_id": contract_id,
        "exit_stock_price": Decimal("190.50"),
        "exit_contract_mid": Decimal("7.30"),
        "exit_contract_bid": Decimal("7.10"),
        "exit_contract_ask": Decimal("7.50"),
        "exit_date": date(2026, 3, 11),
        "stock_return_pct": 4.50,
        "contract_return_pct": 35.19,
        "is_winner": True,
        "holding_days": 10,
        "dte_at_exit": 35,
        "collection_method": OutcomeCollectionMethod.MARKET,
        "collected_at": datetime(2026, 3, 11, 16, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return ContractOutcome(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Save and get roundtrip
# ---------------------------------------------------------------------------


class TestOutcomeRoundtrip:
    """Tests for outcome save/get operations."""

    @pytest.mark.asyncio
    async def test_save_and_get_outcomes_roundtrip(
        self, repo: Repository, contract_id: int
    ) -> None:
        """Verify outcomes survive save -> get roundtrip."""
        outcome = make_outcome(contract_id)
        await repo.save_contract_outcomes([outcome])

        loaded = await repo.get_outcomes_for_contract(contract_id)
        assert len(loaded) == 1
        o = loaded[0]
        assert o.id is not None
        assert o.recommended_contract_id == contract_id
        assert o.exit_stock_price == Decimal("190.50")
        assert o.exit_contract_mid == Decimal("7.30")
        assert o.exit_contract_bid == Decimal("7.10")
        assert o.exit_contract_ask == Decimal("7.50")
        assert o.exit_date == date(2026, 3, 11)
        assert o.stock_return_pct == pytest.approx(4.50)
        assert o.contract_return_pct == pytest.approx(35.19)
        assert o.is_winner is True
        assert o.holding_days == 10
        assert o.dte_at_exit == 35
        assert o.collection_method is OutcomeCollectionMethod.MARKET
        assert o.collected_at == datetime(2026, 3, 11, 16, 0, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_decimal_precision_roundtrip(self, repo: Repository, contract_id: int) -> None:
        """Verify Decimal exit prices roundtrip correctly."""
        outcome = make_outcome(
            contract_id,
            exit_stock_price=Decimal("1234.5678"),
            exit_contract_mid=Decimal("99999.99"),
            exit_contract_bid=Decimal("0.01"),
            exit_contract_ask=Decimal("50000.005"),
        )
        await repo.save_contract_outcomes([outcome])

        loaded = await repo.get_outcomes_for_contract(contract_id)
        assert len(loaded) == 1
        o = loaded[0]
        assert o.exit_stock_price == Decimal("1234.5678")
        assert o.exit_contract_mid == Decimal("99999.99")
        assert o.exit_contract_bid == Decimal("0.01")
        assert o.exit_contract_ask == Decimal("50000.005")


# ---------------------------------------------------------------------------
# Contracts needing outcomes
# ---------------------------------------------------------------------------


class TestContractsNeedingOutcomes:
    """Tests for get_contracts_needing_outcomes."""

    @pytest.mark.asyncio
    async def test_get_contracts_needing_outcomes(
        self, repo: Repository, scan_id: int, contract_id: int
    ) -> None:
        """Verify query returns contracts without outcomes for given period."""
        # Contract was created on 2026-03-01
        lookback_date = date(2026, 3, 1)
        contracts = await repo.get_contracts_needing_outcomes(10, lookback_date)
        assert len(contracts) == 1
        assert contracts[0].id == contract_id

    @pytest.mark.asyncio
    async def test_contracts_with_existing_outcome_excluded(
        self, repo: Repository, scan_id: int, contract_id: int
    ) -> None:
        """Verify contracts already having outcome for period are excluded."""
        # Save an outcome with holding_days=10
        outcome = make_outcome(contract_id, holding_days=10)
        await repo.save_contract_outcomes([outcome])

        lookback_date = date(2026, 3, 1)
        contracts = await repo.get_contracts_needing_outcomes(10, lookback_date)
        assert len(contracts) == 0

        # But a different holding period should still need collection
        contracts_5 = await repo.get_contracts_needing_outcomes(5, lookback_date)
        assert len(contracts_5) == 1


# ---------------------------------------------------------------------------
# has_outcome
# ---------------------------------------------------------------------------


class TestHasOutcome:
    """Tests for has_outcome."""

    @pytest.mark.asyncio
    async def test_has_outcome_true(self, repo: Repository, contract_id: int) -> None:
        """Verify has_outcome returns True for existing outcome."""
        outcome = make_outcome(contract_id, exit_date=date(2026, 3, 11))
        await repo.save_contract_outcomes([outcome])

        result = await repo.has_outcome(contract_id, date(2026, 3, 11))
        assert result is True

    @pytest.mark.asyncio
    async def test_has_outcome_false(self, repo: Repository, contract_id: int) -> None:
        """Verify has_outcome returns False for missing outcome."""
        result = await repo.has_outcome(contract_id, date(2026, 3, 11))
        assert result is False


# ---------------------------------------------------------------------------
# Multiple outcomes per contract
# ---------------------------------------------------------------------------


class TestMultipleOutcomes:
    """Tests for multiple holding period outcomes."""

    @pytest.mark.asyncio
    async def test_multiple_outcomes_per_contract(
        self, repo: Repository, contract_id: int
    ) -> None:
        """Verify T+1, T+5, T+10, T+20 outcomes all saved for same contract."""
        outcomes = [
            make_outcome(
                contract_id,
                holding_days=1,
                exit_date=date(2026, 3, 2),
                stock_return_pct=0.5,
                contract_return_pct=2.0,
            ),
            make_outcome(
                contract_id,
                holding_days=5,
                exit_date=date(2026, 3, 6),
                stock_return_pct=2.1,
                contract_return_pct=10.5,
            ),
            make_outcome(
                contract_id,
                holding_days=10,
                exit_date=date(2026, 3, 11),
                stock_return_pct=4.5,
                contract_return_pct=35.2,
            ),
            make_outcome(
                contract_id,
                holding_days=20,
                exit_date=date(2026, 3, 21),
                stock_return_pct=8.0,
                contract_return_pct=55.0,
            ),
        ]
        await repo.save_contract_outcomes(outcomes)

        loaded = await repo.get_outcomes_for_contract(contract_id)
        assert len(loaded) == 4
        # Verify they're ordered by holding_days ASC
        holding_days_list = [o.holding_days for o in loaded]
        assert holding_days_list == [1, 5, 10, 20]


# ---------------------------------------------------------------------------
# Unique constraint
# ---------------------------------------------------------------------------


class TestUniqueConstraint:
    """Tests for UNIQUE(recommended_contract_id, holding_days) enforcement."""

    @pytest.mark.asyncio
    async def test_unique_constraint(self, repo: Repository, contract_id: int) -> None:
        """Verify UNIQUE(recommended_contract_id, holding_days) enforced."""
        outcome = make_outcome(contract_id, exit_date=date(2026, 3, 11))
        await repo.save_contract_outcomes([outcome])

        # Attempting to save again with same contract_id + holding_days should fail
        duplicate = make_outcome(contract_id, exit_date=date(2026, 3, 12))
        with pytest.raises(sqlite3.IntegrityError):
            await repo.save_contract_outcomes([duplicate])
