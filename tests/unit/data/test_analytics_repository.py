"""Tests for analytics persistence — RecommendedContract.

Covers:
  - RecommendedContract save/get roundtrip with all fields intact.
  - Decimal precision preserved through TEXT storage.
  - Optional Greeks (None) stored as NULL and reconstructed as None.
  - Enum reconstruction (OptionType, ExerciseStyle, SignalDirection).
  - UNIQUE constraint enforcement on (scan_run_id, ticker, option_type, strike, expiration).
  - Batch insert of multiple contracts.
  - Empty scan returns empty list.
  - Ticker-filtered contract query.
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
    ExerciseStyle,
    GreeksSource,
    OptionType,
    PricingModel,
    RecommendedContract,
    ScanPreset,
    ScanRun,
    SignalDirection,
)

pytestmark = pytest.mark.db

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_recommended_contract(scan_run_id: int = 1, **overrides: object) -> RecommendedContract:
    """Build a RecommendedContract with sensible defaults."""
    defaults: dict[str, object] = {
        "scan_run_id": scan_run_id,
        "ticker": "AAPL",
        "option_type": OptionType.CALL,
        "strike": Decimal("185.50"),
        "expiration": date(2026, 4, 15),
        "bid": Decimal("5.20"),
        "ask": Decimal("5.60"),
        "last": Decimal("5.40"),
        "volume": 1200,
        "open_interest": 5000,
        "market_iv": 0.32,
        "exercise_style": ExerciseStyle.AMERICAN,
        "delta": 0.45,
        "gamma": 0.03,
        "theta": -0.12,
        "vega": 0.15,
        "rho": 0.02,
        "pricing_model": PricingModel.BAW,
        "greeks_source": GreeksSource.COMPUTED,
        "entry_stock_price": Decimal("182.30"),
        "entry_mid": Decimal("5.40"),
        "direction": SignalDirection.BULLISH,
        "composite_score": 78.5,
        "risk_free_rate": 0.045,
        "created_at": datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return RecommendedContract(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RecommendedContract persistence
# ---------------------------------------------------------------------------


class TestRecommendedContractPersistence:
    """Tests for recommended contract save/get operations."""

    @pytest.mark.asyncio
    async def test_save_and_get_contracts_roundtrip(self, repo: Repository, scan_id: int) -> None:
        """Verify contracts survive save -> get with all fields intact."""
        contract = make_recommended_contract(scan_run_id=scan_id)
        await repo.save_recommended_contracts(scan_id, [contract])

        loaded = await repo.get_contracts_for_scan(scan_id)
        assert len(loaded) == 1
        c = loaded[0]
        assert c.id is not None
        assert c.scan_run_id == scan_id
        assert c.ticker == "AAPL"
        assert c.option_type is OptionType.CALL
        assert c.strike == Decimal("185.50")
        assert c.expiration == date(2026, 4, 15)
        assert c.bid == Decimal("5.20")
        assert c.ask == Decimal("5.60")
        assert c.last == Decimal("5.40")
        assert c.volume == 1200
        assert c.open_interest == 5000
        assert c.market_iv == pytest.approx(0.32)
        assert c.exercise_style is ExerciseStyle.AMERICAN
        assert c.delta == pytest.approx(0.45)
        assert c.gamma == pytest.approx(0.03)
        assert c.theta == pytest.approx(-0.12)
        assert c.vega == pytest.approx(0.15)
        assert c.rho == pytest.approx(0.02)
        assert c.pricing_model is PricingModel.BAW
        assert c.greeks_source is GreeksSource.COMPUTED
        assert c.entry_stock_price == Decimal("182.30")
        assert c.entry_mid == Decimal("5.40")
        assert c.direction is SignalDirection.BULLISH
        assert c.composite_score == pytest.approx(78.5)
        assert c.risk_free_rate == pytest.approx(0.045)
        assert c.created_at == datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_decimal_precision_survives_roundtrip(
        self, repo: Repository, scan_id: int
    ) -> None:
        """Verify Decimal('185.50') stored as TEXT roundtrips exactly."""
        contract = make_recommended_contract(
            scan_run_id=scan_id,
            strike=Decimal("185.50"),
            bid=Decimal("0.01"),
            ask=Decimal("99999.99"),
            entry_stock_price=Decimal("1234.5678"),
            entry_mid=Decimal("50000.005"),
        )
        await repo.save_recommended_contracts(scan_id, [contract])

        loaded = await repo.get_contracts_for_scan(scan_id)
        assert len(loaded) == 1
        c = loaded[0]
        assert c.strike == Decimal("185.50")
        assert c.bid == Decimal("0.01")
        assert c.ask == Decimal("99999.99")
        assert c.entry_stock_price == Decimal("1234.5678")
        assert c.entry_mid == Decimal("50000.005")

    @pytest.mark.asyncio
    async def test_optional_greeks_none_roundtrip(self, repo: Repository, scan_id: int) -> None:
        """Verify None Greeks stored as NULL and reconstructed as None."""
        contract = make_recommended_contract(
            scan_run_id=scan_id,
            delta=None,
            gamma=None,
            theta=None,
            vega=None,
            rho=None,
            pricing_model=None,
            greeks_source=None,
            last=None,
        )
        await repo.save_recommended_contracts(scan_id, [contract])

        loaded = await repo.get_contracts_for_scan(scan_id)
        assert len(loaded) == 1
        c = loaded[0]
        assert c.delta is None
        assert c.gamma is None
        assert c.theta is None
        assert c.vega is None
        assert c.rho is None
        assert c.pricing_model is None
        assert c.greeks_source is None
        assert c.last is None

    @pytest.mark.asyncio
    async def test_null_entry_stock_price_roundtrip(self, repo: Repository, scan_id: int) -> None:
        """Verify None entry_stock_price stored as NULL and reconstructed as None."""
        contract = make_recommended_contract(
            scan_run_id=scan_id,
            entry_stock_price=None,
        )
        await repo.save_recommended_contracts(scan_id, [contract])

        loaded = await repo.get_contracts_for_scan(scan_id)
        assert len(loaded) == 1
        assert loaded[0].entry_stock_price is None

    @pytest.mark.asyncio
    async def test_get_contracts_for_ticker(self, repo: Repository, scan_id: int) -> None:
        """Verify ticker-filtered query returns correct contracts."""
        aapl = make_recommended_contract(scan_run_id=scan_id, ticker="AAPL")
        msft = make_recommended_contract(
            scan_run_id=scan_id,
            ticker="MSFT",
            strike=Decimal("400.00"),
        )
        await repo.save_recommended_contracts(scan_id, [aapl, msft])

        loaded = await repo.get_contracts_for_ticker("AAPL")
        assert len(loaded) == 1
        assert loaded[0].ticker == "AAPL"

        loaded_msft = await repo.get_contracts_for_ticker("MSFT")
        assert len(loaded_msft) == 1
        assert loaded_msft[0].ticker == "MSFT"

    @pytest.mark.asyncio
    async def test_get_contracts_empty_scan(self, repo: Repository, scan_id: int) -> None:
        """Verify empty list returned for scan with no contracts."""
        loaded = await repo.get_contracts_for_scan(scan_id)
        assert loaded == []

    @pytest.mark.asyncio
    async def test_enum_reconstruction(self, repo: Repository, scan_id: int) -> None:
        """Verify OptionType, ExerciseStyle, SignalDirection roundtrip as enums."""
        contract = make_recommended_contract(
            scan_run_id=scan_id,
            option_type=OptionType.PUT,
            exercise_style=ExerciseStyle.EUROPEAN,
            direction=SignalDirection.BEARISH,
        )
        await repo.save_recommended_contracts(scan_id, [contract])

        loaded = await repo.get_contracts_for_scan(scan_id)
        assert len(loaded) == 1
        c = loaded[0]
        assert isinstance(c.option_type, OptionType)
        assert c.option_type is OptionType.PUT
        assert isinstance(c.exercise_style, ExerciseStyle)
        assert c.exercise_style is ExerciseStyle.EUROPEAN
        assert isinstance(c.direction, SignalDirection)
        assert c.direction is SignalDirection.BEARISH

    @pytest.mark.asyncio
    async def test_unique_constraint_rejects_duplicates(
        self, repo: Repository, scan_id: int
    ) -> None:
        """Verify UNIQUE(scan_run_id, ticker, option_type, strike, expiration) enforced."""
        contract = make_recommended_contract(scan_run_id=scan_id)
        await repo.save_recommended_contracts(scan_id, [contract])

        with pytest.raises(sqlite3.IntegrityError):
            await repo.save_recommended_contracts(scan_id, [contract])

    @pytest.mark.asyncio
    async def test_batch_insert_multiple_contracts(self, repo: Repository, scan_id: int) -> None:
        """Verify executemany saves multiple contracts in one call."""
        contracts = [
            make_recommended_contract(
                scan_run_id=scan_id,
                ticker="AAPL",
                strike=Decimal("180.00"),
            ),
            make_recommended_contract(
                scan_run_id=scan_id,
                ticker="AAPL",
                strike=Decimal("190.00"),
            ),
            make_recommended_contract(
                scan_run_id=scan_id,
                ticker="MSFT",
                strike=Decimal("400.00"),
            ),
        ]
        await repo.save_recommended_contracts(scan_id, contracts)

        loaded = await repo.get_contracts_for_scan(scan_id)
        assert len(loaded) == 3
        tickers = {c.ticker for c in loaded}
        assert tickers == {"AAPL", "MSFT"}
