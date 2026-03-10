"""Tests for backtesting analytics query methods on Repository.

Covers:
  - Equity curve (empty, single day, multi-day, direction filter, period filter).
  - Drawdown series (empty, at peak, below peak).
  - Win rate by sector (empty, multiple sectors).
  - Win rate by DTE bucket (empty, multiple buckets).
  - Win rate by IV rank bucket (empty, multiple buckets).
  - Greeks decomposition (empty, calls, puts, direction groupby, sector groupby).
  - Holding period comparison (empty, multiple periods, Sharpe-like ratio).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    ContractOutcome,
    ExerciseStyle,
    GreeksGroupBy,
    GreeksSource,
    OptionType,
    OutcomeCollectionMethod,
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


def make_contract(scan_run_id: int, **overrides: object) -> RecommendedContract:
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


def make_outcome(contract_id: int, **overrides: object) -> ContractOutcome:
    """Build a ContractOutcome with sensible defaults."""
    defaults: dict[str, object] = {
        "recommended_contract_id": contract_id,
        "exit_stock_price": Decimal("190.00"),
        "exit_contract_mid": Decimal("6.50"),
        "exit_date": date(2026, 3, 6),
        "stock_return_pct": 4.22,
        "contract_return_pct": 20.37,
        "is_winner": True,
        "holding_days": 20,
        "dte_at_exit": 40,
        "collection_method": OutcomeCollectionMethod.MARKET,
        "collected_at": datetime(2026, 3, 6, 16, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return ContractOutcome(**defaults)  # type: ignore[arg-type]


async def _seed_contracts_and_outcomes(
    repo: Repository,
    scan_id: int,
    contracts_data: list[dict[str, object]],
    outcomes_data: list[dict[str, object]],
) -> list[int]:
    """Seed contracts and outcomes, returning the contract DB ids."""
    contract_ids: list[int] = []
    conn = repo._db.conn  # noqa: SLF001
    for cdata in contracts_data:
        c = make_contract(scan_run_id=scan_id, **cdata)
        await repo.save_recommended_contracts(scan_id, [c])
        async with conn.execute("SELECT MAX(id) FROM recommended_contracts") as cursor:
            row = await cursor.fetchone()
        contract_ids.append(int(row[0]))  # type: ignore[index]

    outcomes = []
    for odata in outcomes_data:
        idx = int(odata.pop("_contract_index", 0))  # type: ignore[arg-type]
        cid = contract_ids[idx]
        outcomes.append(make_outcome(contract_id=cid, **odata))
    if outcomes:
        await repo.save_contract_outcomes(outcomes)

    return contract_ids


async def _seed_ticker_metadata(repo: Repository, ticker: str, sector: str) -> None:
    """Insert a row into ticker_metadata for sector-based queries."""
    conn = repo._db.conn  # noqa: SLF001
    await conn.execute(
        "INSERT OR REPLACE INTO ticker_metadata "
        "(ticker, sector, industry_group, market_cap_tier, company_name, "
        "raw_sector, raw_industry, last_updated) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ticker,
            sector,
            "Software",
            "large",
            f"{ticker} Inc.",
            sector,
            "Software",
            datetime.now(UTC).isoformat(),
        ),
    )
    await conn.commit()


# ---------------------------------------------------------------------------
# Equity Curve
# ---------------------------------------------------------------------------


class TestEquityCurve:
    """Tests for ``get_equity_curve()``."""

    @pytest.mark.asyncio
    async def test_empty_db(self, repo: Repository) -> None:
        """Empty database returns empty list."""
        results = await repo.get_equity_curve()
        assert results == []

    @pytest.mark.asyncio
    async def test_single_day(self, repo: Repository, scan_id: int) -> None:
        """Single contract produces one equity curve point."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[{"ticker": "AAPL"}],
            outcomes_data=[{"_contract_index": 0, "contract_return_pct": 10.0}],
        )
        results = await repo.get_equity_curve()
        assert len(results) == 1
        assert results[0].cumulative_return_pct == pytest.approx(10.0, rel=1e-4)
        assert results[0].trade_count == 1

    @pytest.mark.asyncio
    async def test_multi_day_cumulative(self, repo: Repository, scan_id: int) -> None:
        """Multiple dates produce cumulative returns."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "created_at": datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "created_at": datetime(2026, 3, 2, 10, 0, 0, tzinfo=UTC),
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0},
                {"_contract_index": 1, "contract_return_pct": -5.0},
            ],
        )
        results = await repo.get_equity_curve()
        assert len(results) == 2
        # Day 1: single trade +10% → factor = 1.10 → cum = 10.0%
        assert results[0].cumulative_return_pct == pytest.approx(10.0, rel=1e-4)
        assert results[0].trade_count == 1
        # Day 2: single trade -5% → factor = 1.10 * 0.95 = 1.045 → cum = 4.5%
        assert results[1].cumulative_return_pct == pytest.approx(4.5, rel=1e-4)
        assert results[1].trade_count == 2

    @pytest.mark.asyncio
    async def test_direction_filter(self, repo: Repository, scan_id: int) -> None:
        """Direction filter limits results to matching contracts."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "direction": SignalDirection.BULLISH,
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "direction": SignalDirection.BEARISH,
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0},
                {"_contract_index": 1, "contract_return_pct": -5.0},
            ],
        )
        results = await repo.get_equity_curve(direction="bullish")
        assert len(results) == 1
        assert results[0].cumulative_return_pct == pytest.approx(10.0, rel=1e-4)

    @pytest.mark.asyncio
    async def test_same_day_multiple_trades(self, repo: Repository, scan_id: int) -> None:
        """Multiple trades on same day are aggregated into one point."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "created_at": datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "created_at": datetime(2026, 3, 1, 11, 0, 0, tzinfo=UTC),
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0},
                {"_contract_index": 1, "contract_return_pct": 5.0},
            ],
        )
        results = await repo.get_equity_curve()
        assert len(results) == 1
        # Same-day trades averaged: (10 + 5) / 2 = 7.5% → factor = 1.075 → cum = 7.5%
        assert results[0].cumulative_return_pct == pytest.approx(7.5, rel=1e-4)
        assert results[0].trade_count == 2


# ---------------------------------------------------------------------------
# Drawdown Series
# ---------------------------------------------------------------------------


class TestDrawdownSeries:
    """Tests for ``get_drawdown_series()``."""

    @pytest.mark.asyncio
    async def test_empty_db(self, repo: Repository) -> None:
        """Empty database returns empty list."""
        results = await repo.get_drawdown_series()
        assert results == []

    @pytest.mark.asyncio
    async def test_monotonically_increasing(self, repo: Repository, scan_id: int) -> None:
        """When equity only goes up, drawdown is always 0."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "created_at": datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "created_at": datetime(2026, 3, 2, 10, 0, 0, tzinfo=UTC),
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0},
                {"_contract_index": 1, "contract_return_pct": 5.0},
            ],
        )
        results = await repo.get_drawdown_series()
        assert len(results) == 2
        for pt in results:
            assert pt.drawdown_pct == pytest.approx(0.0, abs=1e-8)

    @pytest.mark.asyncio
    async def test_drawdown_after_peak(self, repo: Repository, scan_id: int) -> None:
        """Drawdown computed correctly after equity drops from peak."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "created_at": datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "created_at": datetime(2026, 3, 2, 10, 0, 0, tzinfo=UTC),
                },
                {
                    "ticker": "TSLA",
                    "strike": Decimal("200.00"),
                    "created_at": datetime(2026, 3, 3, 10, 0, 0, tzinfo=UTC),
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 20.0},
                {"_contract_index": 1, "contract_return_pct": -15.0},
                {"_contract_index": 2, "contract_return_pct": 3.0},
            ],
        )
        results = await repo.get_drawdown_series()
        assert len(results) == 3

        # Geometric compounding:
        # Day 1: factor=1.20, cum=20.0, peak=20.0, dd=0
        assert results[0].drawdown_pct == pytest.approx(0.0, abs=1e-8)
        assert results[0].peak_value == pytest.approx(20.0, rel=1e-4)

        # Day 2: factor=1.20*0.85=1.02, cum=2.0, peak=20.0
        # dd = (2.0 - 20.0) / 20.0 * 100 = -90.0
        assert results[1].drawdown_pct == pytest.approx(-90.0, rel=1e-4)
        assert results[1].peak_value == pytest.approx(20.0, rel=1e-4)

        # Day 3: factor=1.02*1.03=1.0506, cum=5.06, peak=20.0
        # dd = (5.06 - 20.0) / 20.0 * 100 = -74.7
        assert results[2].drawdown_pct == pytest.approx(-74.7, rel=1e-2)
        assert results[2].peak_value == pytest.approx(20.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Win Rate by Sector
# ---------------------------------------------------------------------------


class TestWinRateBySector:
    """Tests for ``get_win_rate_by_sector()``."""

    @pytest.mark.asyncio
    async def test_empty_db(self, repo: Repository) -> None:
        """Empty database returns empty list."""
        results = await repo.get_win_rate_by_sector()
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_sectors(self, repo: Repository, scan_id: int) -> None:
        """Win rate computed correctly per sector."""
        # Seed metadata
        await _seed_ticker_metadata(repo, "AAPL", "Information Technology")
        await _seed_ticker_metadata(repo, "JPM", "Financials")

        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00")},
                {"ticker": "AAPL", "strike": Decimal("185.00")},
                {"ticker": "JPM", "strike": Decimal("200.00")},
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "contract_return_pct": 10.0,
                    "holding_days": 20,
                    "is_winner": True,
                },
                {
                    "_contract_index": 1,
                    "contract_return_pct": -5.0,
                    "holding_days": 20,
                    "is_winner": False,
                },
                {
                    "_contract_index": 2,
                    "contract_return_pct": 15.0,
                    "holding_days": 20,
                    "is_winner": True,
                },
            ],
        )

        results = await repo.get_win_rate_by_sector(holding_days=20)
        assert len(results) == 2

        by_sector = {r.sector: r for r in results}

        tech = by_sector["Information Technology"]
        assert tech.total == 2
        assert tech.win_rate_pct == pytest.approx(50.0, rel=1e-4)
        assert tech.avg_return_pct == pytest.approx(2.5, rel=1e-4)

        fin = by_sector["Financials"]
        assert fin.total == 1
        assert fin.win_rate_pct == pytest.approx(100.0, rel=1e-4)
        assert fin.avg_return_pct == pytest.approx(15.0, rel=1e-4)

    @pytest.mark.asyncio
    async def test_no_metadata(self, repo: Repository, scan_id: int) -> None:
        """Contracts without ticker_metadata are excluded."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[{"ticker": "AAPL"}],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 20},
            ],
        )
        results = await repo.get_win_rate_by_sector(holding_days=20)
        assert results == []

    @pytest.mark.asyncio
    async def test_wrong_holding_days(self, repo: Repository, scan_id: int) -> None:
        """Outcomes with different holding_days are excluded."""
        await _seed_ticker_metadata(repo, "AAPL", "Information Technology")
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[{"ticker": "AAPL"}],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 5},
            ],
        )
        results = await repo.get_win_rate_by_sector(holding_days=20)
        assert results == []


# ---------------------------------------------------------------------------
# Win Rate by DTE Bucket
# ---------------------------------------------------------------------------


class TestWinRateByDTEBucket:
    """Tests for ``get_win_rate_by_dte_bucket()``."""

    @pytest.mark.asyncio
    async def test_empty_db(self, repo: Repository) -> None:
        """Empty database returns empty list."""
        results = await repo.get_win_rate_by_dte_bucket()
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_buckets(self, repo: Repository, scan_id: int) -> None:
        """Contracts placed into correct DTE buckets."""
        # DTE = julianday(expiration) - julianday(created_at)
        # Contract 1: 2026-04-15 - 2026-03-01T10:00 ~ 44.58 days -> 30-60 bucket
        # Contract 2: 2026-03-11 - 2026-03-01T10:00 ~ 9.58 days -> 7-14 bucket
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "expiration": date(2026, 4, 15),
                    "created_at": datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "expiration": date(2026, 3, 11),
                    "created_at": datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 20},
                {"_contract_index": 1, "contract_return_pct": -5.0, "holding_days": 20},
            ],
        )

        results = await repo.get_win_rate_by_dte_bucket(holding_days=20)
        assert len(results) == 2

        by_min = {r.dte_min: r for r in results}

        # 7-14 bucket (~9.58 DTE)
        short = by_min[7]
        assert short.dte_max == 14
        assert short.total == 1
        assert short.avg_return_pct == pytest.approx(-5.0, rel=1e-4)

        # 30-60 bucket (~44.58 DTE)
        mid = by_min[30]
        assert mid.dte_max == 60
        assert mid.total == 1
        assert mid.avg_return_pct == pytest.approx(10.0, rel=1e-4)

    @pytest.mark.asyncio
    async def test_wrong_holding_days(self, repo: Repository, scan_id: int) -> None:
        """Outcomes with different holding_days are excluded."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[{"ticker": "AAPL"}],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 5},
            ],
        )
        results = await repo.get_win_rate_by_dte_bucket(holding_days=20)
        assert results == []


# ---------------------------------------------------------------------------
# Win Rate by IV Rank
# ---------------------------------------------------------------------------


class TestWinRateByIVRank:
    """Tests for ``get_win_rate_by_iv_rank()``."""

    @pytest.mark.asyncio
    async def test_empty_db(self, repo: Repository) -> None:
        """Empty database returns empty list."""
        results = await repo.get_win_rate_by_iv_rank()
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_iv_buckets(self, repo: Repository, scan_id: int) -> None:
        """Contracts bucketed correctly by IV."""
        # market_iv=0.15 -> 15% -> 0-25 bucket
        # market_iv=0.55 -> 55% -> 50-75 bucket
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "market_iv": 0.15,
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "market_iv": 0.55,
                },
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "contract_return_pct": 10.0,
                    "holding_days": 20,
                    "is_winner": True,
                },
                {
                    "_contract_index": 1,
                    "contract_return_pct": -3.0,
                    "holding_days": 20,
                    "is_winner": False,
                },
            ],
        )

        results = await repo.get_win_rate_by_iv_rank(holding_days=20)
        assert len(results) == 2

        by_iv_min = {r.iv_min: r for r in results}

        low_iv = by_iv_min[0.0]
        assert low_iv.iv_max == pytest.approx(25.0)
        assert low_iv.total == 1
        assert low_iv.win_rate_pct == pytest.approx(100.0, rel=1e-4)

        mid_iv = by_iv_min[50.0]
        assert mid_iv.iv_max == pytest.approx(75.0)
        assert mid_iv.total == 1
        assert mid_iv.win_rate_pct == pytest.approx(0.0, abs=1e-4)

    @pytest.mark.asyncio
    async def test_wrong_holding_days(self, repo: Repository, scan_id: int) -> None:
        """Outcomes with different holding_days are excluded."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[{"ticker": "AAPL"}],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 5},
            ],
        )
        results = await repo.get_win_rate_by_iv_rank(holding_days=20)
        assert results == []


# ---------------------------------------------------------------------------
# Greeks Decomposition
# ---------------------------------------------------------------------------


class TestGreeksDecomposition:
    """Tests for ``get_greeks_decomposition()``."""

    @pytest.mark.asyncio
    async def test_empty_db(self, repo: Repository) -> None:
        """Empty database returns empty list."""
        results = await repo.get_greeks_decomposition()
        assert results == []

    @pytest.mark.asyncio
    async def test_call_decomposition(self, repo: Repository, scan_id: int) -> None:
        """Call delta P&L = stock_return * delta."""
        # delta=0.5, stock_return=10%, contract_return=25%
        # delta_pnl = 10 * 0.5 = 5
        # residual = 25 - 5 = 20
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "option_type": OptionType.CALL,
                    "delta": 0.50,
                    "direction": SignalDirection.BULLISH,
                },
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "stock_return_pct": 10.0,
                    "contract_return_pct": 25.0,
                    "holding_days": 20,
                },
            ],
        )

        results = await repo.get_greeks_decomposition(holding_days=20)
        assert len(results) == 1
        r = results[0]
        assert r.group_key == "bullish"
        assert r.delta_pnl == pytest.approx(5.0, rel=1e-4)
        assert r.residual_pnl == pytest.approx(20.0, rel=1e-4)
        assert r.total_pnl == pytest.approx(25.0, rel=1e-4)
        assert r.count == 1

    @pytest.mark.asyncio
    async def test_put_decomposition_negates_delta(self, repo: Repository, scan_id: int) -> None:
        """Put delta P&L = stock_return * (-delta)."""
        # delta=-0.40, stock_return=-5%, contract_return=15%
        # delta_pnl = -5 * -(-0.40) = -5 * 0.40 = -2.0
        # residual = 15 - (-2) = 17
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "option_type": OptionType.PUT,
                    "delta": -0.40,
                    "direction": SignalDirection.BEARISH,
                },
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "stock_return_pct": -5.0,
                    "contract_return_pct": 15.0,
                    "holding_days": 20,
                },
            ],
        )

        results = await repo.get_greeks_decomposition(holding_days=20)
        assert len(results) == 1
        r = results[0]
        assert r.group_key == "bearish"
        # For puts, delta_pnl = stock_return * (-delta) = -5.0 * (0.40) = -2.0
        assert r.delta_pnl == pytest.approx(-2.0, rel=1e-4)
        assert r.residual_pnl == pytest.approx(17.0, rel=1e-4)
        assert r.total_pnl == pytest.approx(15.0, rel=1e-4)

    @pytest.mark.asyncio
    async def test_groupby_sector(self, repo: Repository, scan_id: int) -> None:
        """Grouping by sector uses ticker_metadata join."""
        await _seed_ticker_metadata(repo, "AAPL", "Information Technology")

        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "option_type": OptionType.CALL,
                    "delta": 0.50,
                },
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "stock_return_pct": 10.0,
                    "contract_return_pct": 25.0,
                    "holding_days": 20,
                },
            ],
        )

        results = await repo.get_greeks_decomposition(holding_days=20, groupby=GreeksGroupBy.SECTOR)
        assert len(results) == 1
        assert results[0].group_key == "Information Technology"

    @pytest.mark.asyncio
    async def test_groupby_sector_no_metadata(self, repo: Repository, scan_id: int) -> None:
        """Sector groupby with no metadata returns empty."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "option_type": OptionType.CALL,
                    "delta": 0.50,
                },
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "stock_return_pct": 10.0,
                    "contract_return_pct": 25.0,
                    "holding_days": 20,
                },
            ],
        )
        results = await repo.get_greeks_decomposition(holding_days=20, groupby=GreeksGroupBy.SECTOR)
        assert results == []

    @pytest.mark.asyncio
    async def test_multiple_directions(self, repo: Repository, scan_id: int) -> None:
        """Multiple direction groups are returned."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "option_type": OptionType.CALL,
                    "delta": 0.50,
                    "direction": SignalDirection.BULLISH,
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "option_type": OptionType.PUT,
                    "delta": -0.40,
                    "direction": SignalDirection.BEARISH,
                },
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "stock_return_pct": 5.0,
                    "contract_return_pct": 12.0,
                    "holding_days": 20,
                },
                {
                    "_contract_index": 1,
                    "stock_return_pct": -3.0,
                    "contract_return_pct": 8.0,
                    "holding_days": 20,
                },
            ],
        )

        results = await repo.get_greeks_decomposition(holding_days=20)
        assert len(results) == 2
        by_key = {r.group_key: r for r in results}
        assert "bullish" in by_key
        assert "bearish" in by_key

    @pytest.mark.asyncio
    async def test_no_delta_excluded(self, repo: Repository, scan_id: int) -> None:
        """Contracts without delta are excluded."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "delta": None,
                },
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "stock_return_pct": 5.0,
                    "contract_return_pct": 12.0,
                    "holding_days": 20,
                },
            ],
        )
        results = await repo.get_greeks_decomposition(holding_days=20)
        assert results == []


# ---------------------------------------------------------------------------
# Holding Period Comparison
# ---------------------------------------------------------------------------


class TestHoldingPeriodComparison:
    """Tests for ``get_holding_period_comparison()``."""

    @pytest.mark.asyncio
    async def test_empty_db(self, repo: Repository) -> None:
        """Empty database returns empty list."""
        results = await repo.get_holding_period_comparison()
        assert results == []

    @pytest.mark.asyncio
    async def test_single_group(self, repo: Repository, scan_id: int) -> None:
        """Single group computes avg, median, win rate, max loss, Sharpe."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "direction": SignalDirection.BULLISH,
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "direction": SignalDirection.BULLISH,
                },
                {
                    "ticker": "TSLA",
                    "strike": Decimal("200.00"),
                    "direction": SignalDirection.BULLISH,
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 5},
                {"_contract_index": 1, "contract_return_pct": -5.0, "holding_days": 5},
                {"_contract_index": 2, "contract_return_pct": 20.0, "holding_days": 5},
            ],
        )

        results = await repo.get_holding_period_comparison()
        assert len(results) == 1

        r = results[0]
        assert r.holding_days == 5
        assert r.direction == "bullish"
        assert r.count == 3

        # avg = (10 + -5 + 20) / 3 = 8.333...
        assert r.avg_return == pytest.approx(25.0 / 3.0, rel=1e-4)
        # median of [10, -5, 20] sorted = [-5, 10, 20] -> 10
        assert r.median_return == pytest.approx(10.0, rel=1e-4)
        # win rate: 2 winners / 3 = 0.6667
        assert r.win_rate == pytest.approx(2.0 / 3.0, rel=1e-4)
        # max loss = min(-5, 10, 20) = -5
        assert r.max_loss == pytest.approx(-5.0, rel=1e-4)
        # Sharpe-like: mean / stdev
        import statistics as stats_mod

        mean = 25.0 / 3.0
        std = stats_mod.stdev([10.0, -5.0, 20.0])
        assert r.sharpe_like == pytest.approx(mean / std, rel=1e-4)

    @pytest.mark.asyncio
    async def test_multiple_holding_periods(self, repo: Repository, scan_id: int) -> None:
        """Different holding periods produce separate groups."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "direction": SignalDirection.BULLISH,
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "direction": SignalDirection.BULLISH,
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 5},
                {"_contract_index": 1, "contract_return_pct": 20.0, "holding_days": 20},
            ],
        )

        results = await repo.get_holding_period_comparison()
        assert len(results) == 2
        holding_days_set = {r.holding_days for r in results}
        assert holding_days_set == {5, 20}

    @pytest.mark.asyncio
    async def test_single_observation_sharpe_zero(self, repo: Repository, scan_id: int) -> None:
        """Single observation produces Sharpe-like of 0.0."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "direction": SignalDirection.BULLISH},
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 5},
            ],
        )

        results = await repo.get_holding_period_comparison()
        assert len(results) == 1
        assert results[0].sharpe_like == pytest.approx(0.0, abs=1e-8)

    @pytest.mark.asyncio
    async def test_all_same_returns_sharpe_zero(self, repo: Repository, scan_id: int) -> None:
        """Identical returns produce stdev=0, Sharpe-like=0.0."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "direction": SignalDirection.BULLISH,
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "direction": SignalDirection.BULLISH,
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 5},
                {"_contract_index": 1, "contract_return_pct": 10.0, "holding_days": 5},
            ],
        )

        results = await repo.get_holding_period_comparison()
        assert len(results) == 1
        assert results[0].sharpe_like == pytest.approx(0.0, abs=1e-8)

    @pytest.mark.asyncio
    async def test_mixed_directions(self, repo: Repository, scan_id: int) -> None:
        """Different directions produce separate groups."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "direction": SignalDirection.BULLISH,
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "direction": SignalDirection.BEARISH,
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "holding_days": 5},
                {"_contract_index": 1, "contract_return_pct": -5.0, "holding_days": 5},
            ],
        )

        results = await repo.get_holding_period_comparison()
        assert len(results) == 2
        directions = {r.direction for r in results}
        assert directions == {"bullish", "bearish"}

    @pytest.mark.asyncio
    async def test_all_losers(self, repo: Repository, scan_id: int) -> None:
        """All-negative returns yield win_rate=0 and negative max_loss."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "direction": SignalDirection.BULLISH,
                },
                {
                    "ticker": "MSFT",
                    "strike": Decimal("400.00"),
                    "direction": SignalDirection.BULLISH,
                },
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": -10.0, "holding_days": 5},
                {"_contract_index": 1, "contract_return_pct": -20.0, "holding_days": 5},
            ],
        )

        results = await repo.get_holding_period_comparison()
        assert len(results) == 1
        r = results[0]
        assert r.win_rate == pytest.approx(0.0, abs=1e-8)
        assert r.max_loss == pytest.approx(-20.0, rel=1e-4)
