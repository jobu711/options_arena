"""Tests for analytics query methods on Repository.

Covers:
  - Win rate by direction (empty, all winners, all losers, mixed).
  - Score calibration buckets (default size, custom size, avg return).
  - Indicator attribution (correlation computation, quartile split).
  - Holding period (grouped results, direction filter, median).
  - Delta performance (bucketed by delta, holding_days filter).
  - Performance summary (with data, no data, lookback filter).
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
    GreeksSource,
    IndicatorSignals,
    OptionType,
    OutcomeCollectionMethod,
    PricingModel,
    RecommendedContract,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
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
        "holding_days": 5,
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
    # Save contracts one at a time to get individual IDs
    contract_ids: list[int] = []
    conn = repo._db.conn  # noqa: SLF001
    for cdata in contracts_data:
        c = make_contract(scan_run_id=scan_id, **cdata)
        await repo.save_recommended_contracts(scan_id, [c])
        async with conn.execute("SELECT MAX(id) FROM recommended_contracts") as cursor:
            row = await cursor.fetchone()
        contract_ids.append(int(row[0]))  # type: ignore[index]

    # Save outcomes referencing the actual IDs
    outcomes = []
    for odata in outcomes_data:
        idx = int(odata.pop("_contract_index", 0))  # type: ignore[arg-type]
        cid = contract_ids[idx]
        outcomes.append(make_outcome(contract_id=cid, **odata))
    if outcomes:
        await repo.save_contract_outcomes(outcomes)

    return contract_ids


# ---------------------------------------------------------------------------
# Win Rate
# ---------------------------------------------------------------------------


class TestWinRateQuery:
    """Tests for ``get_win_rate_by_direction()``."""

    @pytest.mark.critical
    @pytest.mark.asyncio
    async def test_win_rate_by_direction(self, repo: Repository, scan_id: int) -> None:
        """Verify win rate computed correctly per direction."""
        bull = SignalDirection.BULLISH
        bear = SignalDirection.BEARISH
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00"), "direction": bull},
                {"ticker": "MSFT", "strike": Decimal("400.00"), "direction": bull},
                {"ticker": "TSLA", "strike": Decimal("200.00"), "direction": bear},
            ],
            outcomes_data=[
                {"_contract_index": 0, "is_winner": True, "contract_return_pct": 10.0},
                {"_contract_index": 1, "is_winner": False, "contract_return_pct": -5.0},
                {"_contract_index": 2, "is_winner": True, "contract_return_pct": 15.0},
            ],
        )

        results = await repo.get_win_rate_by_direction()
        assert len(results) == 2

        by_dir = {r.direction: r for r in results}
        bull = by_dir[SignalDirection.BULLISH]
        assert bull.total_contracts == 2
        assert bull.winners == 1
        assert bull.losers == 1
        assert bull.win_rate == pytest.approx(0.5)

        bear = by_dir[SignalDirection.BEARISH]
        assert bear.total_contracts == 1
        assert bear.winners == 1
        assert bear.win_rate == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_win_rate_empty_no_outcomes(self, repo: Repository, scan_id: int) -> None:
        """Verify empty list when no outcomes exist."""
        results = await repo.get_win_rate_by_direction()
        assert results == []

    @pytest.mark.asyncio
    async def test_win_rate_all_winners(self, repo: Repository, scan_id: int) -> None:
        """Verify win_rate=1.0 when all contracts are winners."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00")},
                {"ticker": "MSFT", "strike": Decimal("400.00")},
            ],
            outcomes_data=[
                {"_contract_index": 0, "is_winner": True},
                {"_contract_index": 1, "is_winner": True},
            ],
        )

        results = await repo.get_win_rate_by_direction()
        assert len(results) == 1
        assert results[0].win_rate == pytest.approx(1.0)
        assert results[0].losers == 0

    @pytest.mark.asyncio
    async def test_win_rate_all_losers(self, repo: Repository, scan_id: int) -> None:
        """Verify win_rate=0.0 when all contracts are losers."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[{"ticker": "AAPL", "strike": Decimal("180.00")}],
            outcomes_data=[
                {"_contract_index": 0, "is_winner": False, "contract_return_pct": -10.0},
            ],
        )

        results = await repo.get_win_rate_by_direction()
        assert len(results) == 1
        assert results[0].win_rate == pytest.approx(0.0)
        assert results[0].winners == 0


# ---------------------------------------------------------------------------
# Score Calibration
# ---------------------------------------------------------------------------


class TestScoreCalibration:
    """Tests for ``get_score_calibration()``."""

    @pytest.mark.asyncio
    async def test_score_buckets(self, repo: Repository, scan_id: int) -> None:
        """Verify contracts bucketed correctly by composite_score."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00"), "composite_score": 25.0},
                {"ticker": "MSFT", "strike": Decimal("400.00"), "composite_score": 75.0},
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": -5.0, "is_winner": False},
                {"_contract_index": 1, "contract_return_pct": 15.0, "is_winner": True},
            ],
        )

        results = await repo.get_score_calibration(bucket_size=10.0)
        assert len(results) == 2
        # Bucket [20, 30) and [70, 80)
        low_bucket = results[0]
        assert low_bucket.score_min == pytest.approx(20.0)
        assert low_bucket.contract_count == 1

        high_bucket = results[1]
        assert high_bucket.score_min == pytest.approx(70.0)
        assert high_bucket.contract_count == 1

    @pytest.mark.asyncio
    async def test_custom_bucket_size(self, repo: Repository, scan_id: int) -> None:
        """Verify bucket_size=50 creates wider buckets."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00"), "composite_score": 25.0},
                {"ticker": "MSFT", "strike": Decimal("400.00"), "composite_score": 35.0},
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": -5.0, "is_winner": False},
                {"_contract_index": 1, "contract_return_pct": 15.0, "is_winner": True},
            ],
        )

        results = await repo.get_score_calibration(bucket_size=50.0)
        # Both 25 and 35 fall into [0, 50) bucket
        assert len(results) == 1
        assert results[0].contract_count == 2

    @pytest.mark.asyncio
    async def test_avg_return_per_bucket(self, repo: Repository, scan_id: int) -> None:
        """Verify avg_return_pct computed correctly per bucket."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00"), "composite_score": 75.0},
                {"ticker": "MSFT", "strike": Decimal("400.00"), "composite_score": 78.0},
            ],
            outcomes_data=[
                {"_contract_index": 0, "contract_return_pct": 10.0, "is_winner": True},
                {"_contract_index": 1, "contract_return_pct": 20.0, "is_winner": True},
            ],
        )

        results = await repo.get_score_calibration(bucket_size=10.0)
        assert len(results) == 1
        assert results[0].avg_return_pct == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Indicator Attribution
# ---------------------------------------------------------------------------


class TestIndicatorAttribution:
    """Tests for ``get_indicator_attribution()``."""

    @pytest.mark.asyncio
    async def test_correlation_computation(self, repo: Repository, scan_id: int) -> None:
        """Verify correlation between indicator values and returns."""
        # Save ticker scores with known RSI values
        scores = [
            TickerScore(
                ticker="AAPL",
                composite_score=78.0,
                direction=SignalDirection.BULLISH,
                signals=IndicatorSignals(rsi=80.0),
                scan_run_id=scan_id,
            ),
            TickerScore(
                ticker="MSFT",
                composite_score=65.0,
                direction=SignalDirection.BULLISH,
                signals=IndicatorSignals(rsi=40.0),
                scan_run_id=scan_id,
            ),
            TickerScore(
                ticker="GOOGL",
                composite_score=70.0,
                direction=SignalDirection.BULLISH,
                signals=IndicatorSignals(rsi=60.0),
                scan_run_id=scan_id,
            ),
        ]
        await repo.save_ticker_scores(scan_id, scores)

        # Save contracts + outcomes matching the tickers
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00"), "composite_score": 78.0},
                {"ticker": "MSFT", "strike": Decimal("400.00"), "composite_score": 65.0},
                {"ticker": "GOOGL", "strike": Decimal("150.00"), "composite_score": 70.0},
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "contract_return_pct": 20.0,
                    "is_winner": True,
                    "holding_days": 5,
                },
                {
                    "_contract_index": 1,
                    "contract_return_pct": -5.0,
                    "is_winner": False,
                    "holding_days": 5,
                },
                {
                    "_contract_index": 2,
                    "contract_return_pct": 10.0,
                    "is_winner": True,
                    "holding_days": 5,
                },
            ],
        )

        results = await repo.get_indicator_attribution("rsi", holding_days=5)
        assert len(results) == 1
        r = results[0]
        assert r.indicator_name == "rsi"
        assert r.holding_days == 5
        assert r.sample_size == 3
        # High RSI (80) -> 20% return; Low RSI (40) -> -5%: positive correlation
        assert r.correlation > 0.0

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_empty(self, repo: Repository, scan_id: int) -> None:
        """Verify empty list when fewer than 3 data points."""
        results = await repo.get_indicator_attribution("rsi", holding_days=5)
        assert results == []


# ---------------------------------------------------------------------------
# Holding Period
# ---------------------------------------------------------------------------


class TestHoldingPeriod:
    """Tests for ``get_optimal_holding_period()``."""

    @pytest.mark.asyncio
    async def test_holding_period_results(self, repo: Repository, scan_id: int) -> None:
        """Verify results grouped by holding_days."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[{"ticker": "AAPL", "strike": Decimal("180.00")}],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "holding_days": 5,
                    "contract_return_pct": 10.0,
                    "is_winner": True,
                },
                {
                    "_contract_index": 0,
                    "holding_days": 10,
                    "contract_return_pct": 25.0,
                    "is_winner": True,
                    "exit_date": date(2026, 3, 11),
                },
            ],
        )

        results = await repo.get_optimal_holding_period()
        assert len(results) == 2
        by_hd = {r.holding_days: r for r in results}
        assert 5 in by_hd
        assert 10 in by_hd
        assert by_hd[5].avg_return_pct == pytest.approx(10.0)
        assert by_hd[10].avg_return_pct == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_direction_filter(self, repo: Repository, scan_id: int) -> None:
        """Verify optional direction filter works."""
        bull = SignalDirection.BULLISH
        bear = SignalDirection.BEARISH
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00"), "direction": bull},
                {"ticker": "MSFT", "strike": Decimal("400.00"), "direction": bear},
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "holding_days": 5,
                    "contract_return_pct": 10.0,
                    "is_winner": True,
                },
                {
                    "_contract_index": 1,
                    "holding_days": 5,
                    "contract_return_pct": -3.0,
                    "is_winner": False,
                },
            ],
        )

        results = await repo.get_optimal_holding_period(direction=SignalDirection.BULLISH)
        assert len(results) == 1
        assert results[0].direction is SignalDirection.BULLISH
        assert results[0].avg_return_pct == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Delta Performance
# ---------------------------------------------------------------------------


class TestDeltaPerformance:
    """Tests for ``get_delta_performance()``."""

    @pytest.mark.asyncio
    async def test_delta_buckets(self, repo: Repository, scan_id: int) -> None:
        """Verify contracts bucketed by delta value."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00"), "delta": 0.25},
                {"ticker": "MSFT", "strike": Decimal("400.00"), "delta": 0.45},
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "holding_days": 5,
                    "contract_return_pct": 15.0,
                    "is_winner": True,
                },
                {
                    "_contract_index": 1,
                    "holding_days": 5,
                    "contract_return_pct": 8.0,
                    "is_winner": True,
                },
            ],
        )

        results = await repo.get_delta_performance(bucket_size=0.1, holding_days=5)
        assert len(results) == 2
        # Delta 0.25 -> bucket [0.2, 0.3); Delta 0.45 -> bucket [0.4, 0.5)
        assert results[0].delta_min == pytest.approx(0.2)
        assert results[1].delta_min == pytest.approx(0.4)

    @pytest.mark.asyncio
    async def test_holding_days_filter(self, repo: Repository, scan_id: int) -> None:
        """Verify results filtered by holding_days."""
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[{"ticker": "AAPL", "strike": Decimal("180.00"), "delta": 0.35}],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "holding_days": 5,
                    "contract_return_pct": 10.0,
                    "is_winner": True,
                },
                {
                    "_contract_index": 0,
                    "holding_days": 10,
                    "contract_return_pct": 25.0,
                    "is_winner": True,
                    "exit_date": date(2026, 3, 11),
                },
            ],
        )

        # Only holding_days=5
        results = await repo.get_delta_performance(holding_days=5)
        assert len(results) == 1
        assert results[0].avg_return_pct == pytest.approx(10.0)

        # Only holding_days=10
        results10 = await repo.get_delta_performance(holding_days=10)
        assert len(results10) == 1
        assert results10[0].avg_return_pct == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Performance Summary
# ---------------------------------------------------------------------------


class TestPerformanceSummary:
    """Tests for ``get_performance_summary()``."""

    @pytest.mark.asyncio
    async def test_summary_with_data(self, repo: Repository, scan_id: int) -> None:
        """Verify summary computes correct aggregates."""
        bull = SignalDirection.BULLISH
        bear = SignalDirection.BEARISH
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {"ticker": "AAPL", "strike": Decimal("180.00"), "direction": bull},
                {"ticker": "MSFT", "strike": Decimal("400.00"), "direction": bear},
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "is_winner": True,
                    "contract_return_pct": 20.0,
                    "stock_return_pct": 3.0,
                    "holding_days": 5,
                },
                {
                    "_contract_index": 1,
                    "is_winner": False,
                    "contract_return_pct": -10.0,
                    "stock_return_pct": -2.0,
                    "holding_days": 5,
                },
            ],
        )

        summary = await repo.get_performance_summary(lookback_days=30)
        assert summary.total_contracts == 2
        assert summary.total_with_outcomes == 2
        assert summary.overall_win_rate == pytest.approx(0.5)
        assert summary.avg_stock_return_pct == pytest.approx(0.5)
        assert summary.avg_contract_return_pct == pytest.approx(5.0)
        assert summary.best_direction is not None
        assert summary.best_holding_days == 5

    @pytest.mark.asyncio
    async def test_summary_no_data(self, repo: Repository, scan_id: int) -> None:
        """Verify summary with zero contracts returns None optional fields."""
        summary = await repo.get_performance_summary(lookback_days=30)
        assert summary.total_contracts == 0
        assert summary.total_with_outcomes == 0
        assert summary.overall_win_rate is None
        assert summary.avg_stock_return_pct is None
        assert summary.avg_contract_return_pct is None
        assert summary.best_direction is None
        assert summary.best_holding_days is None

    @pytest.mark.asyncio
    async def test_lookback_days_filter(self, repo: Repository, scan_id: int) -> None:
        """Verify lookback_days limits to recent contracts only.

        Create a contract with created_at far in the past, verify it is excluded
        from a narrow lookback window.
        """
        old_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        await _seed_contracts_and_outcomes(
            repo,
            scan_id,
            contracts_data=[
                {
                    "ticker": "AAPL",
                    "strike": Decimal("180.00"),
                    "created_at": old_time,
                },
            ],
            outcomes_data=[
                {
                    "_contract_index": 0,
                    "is_winner": True,
                    "contract_return_pct": 50.0,
                    "stock_return_pct": 10.0,
                    "holding_days": 5,
                },
            ],
        )

        # Lookback 1 day: old contract should be excluded
        summary = await repo.get_performance_summary(lookback_days=1)
        assert summary.total_contracts == 0
        assert summary.total_with_outcomes == 0
