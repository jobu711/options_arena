"""Tests for AnalyticsMixin.get_risk_adjusted_metrics()."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio

from options_arena.data import Database, Repository
from options_arena.models import (
    ExerciseStyle,
    OutcomeCollectionMethod,
    SignalDirection,
)
from options_arena.models.analytics import RiskAdjustedMetrics


@pytest_asyncio.fixture
async def db() -> Database:  # type: ignore[misc]
    """Fresh in-memory database with migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository backed by in-memory database."""
    return Repository(db)


async def _insert_contract_and_outcome(
    repo: Repository,
    *,
    return_pct: float,
    holding_days: int,
    collected_at: datetime | None = None,
) -> None:
    """Helper to insert a recommended contract and its outcome."""
    unique_id = uuid4().hex[:8]

    db = repo._db  # noqa: SLF001
    conn = db.conn

    # Insert a scan run first
    await conn.execute(
        "INSERT OR IGNORE INTO scan_runs "
        "(id, started_at, completed_at, preset, tickers_scanned, tickers_scored, recommendations) "
        "VALUES (1, ?, ?, 'sp500', 100, 90, 5)",
        (
            datetime.now(UTC).isoformat(),
            datetime.now(UTC).isoformat(),
        ),
    )
    await conn.commit()

    # Vary strike to avoid UNIQUE constraint violation
    strike = Decimal("185.00") + Decimal(str(int(unique_id, 16) % 10000))

    # Insert a recommended contract
    cursor = await conn.execute(
        "INSERT INTO recommended_contracts "
        "(scan_run_id, ticker, option_type, strike, bid, ask, last, expiration, "
        " volume, open_interest, market_iv, exercise_style, "
        " entry_mid, direction, composite_score, risk_free_rate, created_at) "
        "VALUES (1, 'AAPL', 'call', ?, '2.50', '3.00', '2.75', '2026-04-18', "
        " 1000, 5000, 0.25, ?, "
        " '2.75', ?, 75.0, 0.05, ?)",
        (
            str(strike),
            ExerciseStyle.AMERICAN.value,
            SignalDirection.BULLISH.value,
            datetime.now(UTC).isoformat(),
        ),
    )
    await conn.commit()
    contract_id = cursor.lastrowid

    # Insert an outcome
    if collected_at is None:
        collected_at = datetime.now(UTC)

    await conn.execute(
        "INSERT INTO contract_outcomes "
        "(recommended_contract_id, contract_return_pct, holding_days, "
        " collection_method, collected_at, is_winner) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            contract_id,
            return_pct,
            holding_days,
            OutcomeCollectionMethod.MARKET.value,
            collected_at.isoformat(),
            return_pct > 0,
        ),
    )
    await conn.commit()


class TestRiskMetricsQuery:
    """Tests for AnalyticsMixin.get_risk_adjusted_metrics()."""

    @pytest.mark.asyncio
    async def test_returns_typed_model(self, repo: Repository) -> None:
        """Query returns RiskAdjustedMetrics, not dict."""
        result = await repo.get_risk_adjusted_metrics()
        assert isinstance(result, RiskAdjustedMetrics)

    @pytest.mark.asyncio
    async def test_empty_outcomes_returns_zero_trades(self, repo: Repository) -> None:
        """No outcomes in lookback window -> total_trades=0, all ratios None."""
        result = await repo.get_risk_adjusted_metrics()
        assert result.total_trades == 0
        assert result.sharpe_ratio is None
        assert result.sortino_ratio is None
        assert result.max_drawdown_pct is None
        assert result.annualized_return_pct is None

    @pytest.mark.asyncio
    async def test_default_lookback_is_365(self, repo: Repository) -> None:
        """Default lookback_days parameter is 365."""
        result = await repo.get_risk_adjusted_metrics()
        assert result.lookback_days == 365

    @pytest.mark.asyncio
    async def test_custom_lookback_days(self, repo: Repository) -> None:
        """Custom lookback_days is reflected in result."""
        result = await repo.get_risk_adjusted_metrics(lookback_days=90)
        assert result.lookback_days == 90

    @pytest.mark.asyncio
    async def test_with_outcome_data(self, repo: Repository) -> None:
        """With outcome data, total_trades reflects the count."""
        for i in range(5):
            return_pct = 5.0 if i % 2 == 0 else -3.0
            await _insert_contract_and_outcome(
                repo,
                return_pct=return_pct,
                holding_days=5,
            )

        result = await repo.get_risk_adjusted_metrics()
        assert result.total_trades == 5
        # Not enough trades for Sharpe/Sortino (need 30)
        assert result.sharpe_ratio is None
        assert result.sortino_ratio is None
        # But max drawdown should be computed
        assert result.max_drawdown_pct is not None

    @pytest.mark.asyncio
    async def test_lookback_filters_old_data(self, repo: Repository) -> None:
        """Outcomes outside the lookback window are excluded."""
        old_date = datetime.now(UTC) - timedelta(days=400)
        await _insert_contract_and_outcome(
            repo,
            return_pct=5.0,
            holding_days=5,
            collected_at=old_date,
        )

        # Default 365-day lookback should exclude the 400-day-old outcome
        result = await repo.get_risk_adjusted_metrics(lookback_days=365)
        assert result.total_trades == 0

    @pytest.mark.asyncio
    async def test_risk_free_rate_passed_through(self, repo: Repository) -> None:
        """Risk-free rate from parameter flows to result."""
        result = await repo.get_risk_adjusted_metrics(risk_free_rate=0.03)
        assert result.risk_free_rate == pytest.approx(0.03)
