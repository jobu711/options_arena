"""Tests for score history — models, repository methods, and API endpoints.

Covers:
  - HistoryPoint and TrendingTicker model validation
  - Repository.get_score_history() and Repository.get_trending_tickers()
  - API endpoints GET /api/ticker/{ticker}/history and GET /api/ticker/trending
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    HistoryPoint,
    IndicatorSignals,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
    TrendingTicker,
)

# ---------------------------------------------------------------------------
# Fixtures (database)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_scan_run(**overrides: object) -> ScanRun:
    """Build a ScanRun with sensible defaults."""
    defaults: dict[str, object] = {
        "started_at": datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 1, 15, 10, 35, 0, tzinfo=UTC),
        "preset": ScanPreset.SP500,
        "tickers_scanned": 500,
        "tickers_scored": 450,
        "recommendations": 8,
    }
    defaults.update(overrides)
    return ScanRun(**defaults)  # type: ignore[arg-type]


def make_ticker_score(**overrides: object) -> TickerScore:
    """Build a TickerScore with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "composite_score": 78.5,
        "direction": SignalDirection.BULLISH,
        "signals": IndicatorSignals(rsi=65.2, adx=28.4, bb_width=42.1),
    }
    defaults.update(overrides)
    return TickerScore(**defaults)  # type: ignore[arg-type]


# ===========================================================================
# Model validation tests
# ===========================================================================


class TestHistoryPointModel:
    """Validation tests for the HistoryPoint model."""

    def test_valid_construction(self) -> None:
        """HistoryPoint constructs with valid data."""
        hp = HistoryPoint(
            scan_id=1,
            scan_date=datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
            composite_score=78.5,
            direction="bullish",
            preset="sp500",
        )
        assert hp.scan_id == 1
        assert hp.composite_score == pytest.approx(78.5)
        assert hp.direction == "bullish"
        assert hp.preset == "sp500"

    def test_frozen(self) -> None:
        """HistoryPoint is immutable."""
        hp = HistoryPoint(
            scan_id=1,
            scan_date=datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
            composite_score=78.5,
            direction="bullish",
            preset="sp500",
        )
        with pytest.raises(Exception):  # noqa: B017
            hp.scan_id = 2  # type: ignore[misc]

    def test_rejects_naive_datetime(self) -> None:
        """HistoryPoint rejects naive (non-UTC) scan_date."""
        with pytest.raises(ValueError, match="UTC"):
            HistoryPoint(
                scan_id=1,
                scan_date=datetime(2026, 1, 15, 10, 30, 0),
                composite_score=78.5,
                direction="bullish",
                preset="sp500",
            )

    def test_rejects_non_utc_datetime(self) -> None:
        """HistoryPoint rejects non-UTC timezone."""
        from datetime import timezone  # noqa: PLC0415

        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValueError, match="UTC"):
            HistoryPoint(
                scan_id=1,
                scan_date=datetime(2026, 1, 15, 10, 30, 0, tzinfo=est),
                composite_score=78.5,
                direction="bullish",
                preset="sp500",
            )

    def test_rejects_nan_composite_score(self) -> None:
        """HistoryPoint rejects NaN composite_score."""
        with pytest.raises(ValueError, match="finite"):
            HistoryPoint(
                scan_id=1,
                scan_date=datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
                composite_score=float("nan"),
                direction="bullish",
                preset="sp500",
            )

    def test_rejects_inf_composite_score(self) -> None:
        """HistoryPoint rejects infinite composite_score."""
        with pytest.raises(ValueError, match="finite"):
            HistoryPoint(
                scan_id=1,
                scan_date=datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
                composite_score=float("inf"),
                direction="bullish",
                preset="sp500",
            )

    def test_json_roundtrip(self) -> None:
        """HistoryPoint survives JSON serialization round-trip."""
        hp = HistoryPoint(
            scan_id=1,
            scan_date=datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
            composite_score=78.5,
            direction="bullish",
            preset="sp500",
        )
        loaded = HistoryPoint.model_validate_json(hp.model_dump_json())
        assert loaded == hp


class TestTrendingTickerModel:
    """Validation tests for the TrendingTicker model."""

    def test_valid_construction(self) -> None:
        """TrendingTicker constructs with valid data."""
        tt = TrendingTicker(
            ticker="AAPL",
            direction="bullish",
            consecutive_scans=5,
            latest_score=82.3,
            score_change=4.1,
        )
        assert tt.ticker == "AAPL"
        assert tt.consecutive_scans == 5
        assert tt.latest_score == pytest.approx(82.3)
        assert tt.score_change == pytest.approx(4.1)

    def test_frozen(self) -> None:
        """TrendingTicker is immutable."""
        tt = TrendingTicker(
            ticker="AAPL",
            direction="bullish",
            consecutive_scans=5,
            latest_score=82.3,
            score_change=4.1,
        )
        with pytest.raises(Exception):  # noqa: B017
            tt.ticker = "MSFT"  # type: ignore[misc]

    def test_rejects_nan_latest_score(self) -> None:
        """TrendingTicker rejects NaN latest_score."""
        with pytest.raises(ValueError, match="finite"):
            TrendingTicker(
                ticker="AAPL",
                direction="bullish",
                consecutive_scans=5,
                latest_score=float("nan"),
                score_change=0.0,
            )

    def test_rejects_inf_score_change(self) -> None:
        """TrendingTicker rejects infinite score_change."""
        with pytest.raises(ValueError, match="finite"):
            TrendingTicker(
                ticker="AAPL",
                direction="bullish",
                consecutive_scans=5,
                latest_score=82.3,
                score_change=float("inf"),
            )

    def test_negative_score_change_allowed(self) -> None:
        """Negative score_change is valid (score decreased within streak)."""
        tt = TrendingTicker(
            ticker="AAPL",
            direction="bullish",
            consecutive_scans=3,
            latest_score=70.0,
            score_change=-5.2,
        )
        assert tt.score_change == pytest.approx(-5.2)

    def test_zero_consecutive_scans_raises(self) -> None:
        """TrendingTicker rejects consecutive_scans = 0."""
        with pytest.raises(ValueError, match="consecutive_scans"):
            TrendingTicker(
                ticker="AAPL",
                direction="bullish",
                consecutive_scans=0,
                latest_score=82.3,
                score_change=4.1,
            )

    def test_negative_consecutive_scans_raises(self) -> None:
        """TrendingTicker rejects negative consecutive_scans."""
        with pytest.raises(ValueError, match="consecutive_scans"):
            TrendingTicker(
                ticker="AAPL",
                direction="bullish",
                consecutive_scans=-1,
                latest_score=82.3,
                score_change=4.1,
            )

    def test_json_roundtrip(self) -> None:
        """TrendingTicker survives JSON serialization round-trip."""
        tt = TrendingTicker(
            ticker="AAPL",
            direction="bullish",
            consecutive_scans=5,
            latest_score=82.3,
            score_change=4.1,
        )
        loaded = TrendingTicker.model_validate_json(tt.model_dump_json())
        assert loaded == tt


# ===========================================================================
# Repository tests — get_score_history
# ===========================================================================


class TestGetScoreHistory:
    """Tests for Repository.get_score_history()."""

    @pytest.mark.asyncio
    async def test_empty_history(self, repo: Repository) -> None:
        """get_score_history returns empty list for unknown ticker."""
        result = await repo.get_score_history("UNKNOWN")
        assert result == []

    @pytest.mark.asyncio
    async def test_single_scan_history(self, repo: Repository) -> None:
        """get_score_history returns single entry for ticker in one scan."""
        scan_id = await repo.save_scan_run(make_scan_run())
        await repo.save_ticker_scores(scan_id, [make_ticker_score(ticker="AAPL")])

        history = await repo.get_score_history("AAPL")
        assert len(history) == 1
        assert history[0].scan_id == scan_id
        assert history[0].composite_score == pytest.approx(78.5)
        assert history[0].direction == "bullish"
        assert history[0].preset == "sp500"

    @pytest.mark.asyncio
    async def test_multiple_scans_newest_first(self, repo: Repository) -> None:
        """get_score_history returns entries in descending scan date order."""
        base_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
        scan_ids = []
        for i in range(3):
            scan_id = await repo.save_scan_run(
                make_scan_run(started_at=base_time + timedelta(days=i))
            )
            scan_ids.append(scan_id)
            await repo.save_ticker_scores(
                scan_id,
                [make_ticker_score(ticker="AAPL", composite_score=70.0 + i)],
            )

        history = await repo.get_score_history("AAPL")
        assert len(history) == 3
        # Newest first: scan_ids[2] should be first
        assert history[0].scan_id == scan_ids[2]
        assert history[0].composite_score == pytest.approx(72.0)
        assert history[2].scan_id == scan_ids[0]
        assert history[2].composite_score == pytest.approx(70.0)

    @pytest.mark.asyncio
    async def test_respects_limit(self, repo: Repository) -> None:
        """get_score_history respects limit parameter."""
        base_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
        for i in range(5):
            scan_id = await repo.save_scan_run(
                make_scan_run(started_at=base_time + timedelta(days=i))
            )
            await repo.save_ticker_scores(
                scan_id,
                [make_ticker_score(ticker="AAPL", composite_score=70.0 + i)],
            )

        history = await repo.get_score_history("AAPL", limit=3)
        assert len(history) == 3

    @pytest.mark.asyncio
    async def test_case_insensitive_ticker(self, repo: Repository) -> None:
        """get_score_history normalizes ticker to uppercase."""
        scan_id = await repo.save_scan_run(make_scan_run())
        await repo.save_ticker_scores(scan_id, [make_ticker_score(ticker="AAPL")])

        history = await repo.get_score_history("aapl")
        assert len(history) == 1
        assert history[0].composite_score == pytest.approx(78.5)

    @pytest.mark.asyncio
    async def test_returns_typed_history_points(self, repo: Repository) -> None:
        """get_score_history returns HistoryPoint instances."""
        scan_id = await repo.save_scan_run(make_scan_run())
        await repo.save_ticker_scores(scan_id, [make_ticker_score(ticker="MSFT")])

        history = await repo.get_score_history("MSFT")
        assert len(history) == 1
        assert isinstance(history[0], HistoryPoint)
        assert history[0].scan_date.tzinfo is not None


# ===========================================================================
# Repository tests — get_trending_tickers
# ===========================================================================


class TestGetTrendingTickers:
    """Tests for Repository.get_trending_tickers()."""

    @pytest.mark.asyncio
    async def test_no_scans(self, repo: Repository) -> None:
        """get_trending_tickers returns empty list when no scans exist."""
        result = await repo.get_trending_tickers("bullish")
        assert result == []

    @pytest.mark.asyncio
    async def test_no_matching_direction(self, repo: Repository) -> None:
        """get_trending_tickers returns empty when no tickers match direction."""
        scan_id = await repo.save_scan_run(make_scan_run())
        await repo.save_ticker_scores(
            scan_id,
            [make_ticker_score(ticker="AAPL", direction=SignalDirection.BEARISH)],
        )

        result = await repo.get_trending_tickers("bullish")
        assert result == []

    @pytest.mark.asyncio
    async def test_single_scan_below_min_scans(self, repo: Repository) -> None:
        """Ticker in only 1 scan does not meet min_scans=3 threshold."""
        scan_id = await repo.save_scan_run(make_scan_run())
        await repo.save_ticker_scores(
            scan_id,
            [make_ticker_score(ticker="AAPL", direction=SignalDirection.BULLISH)],
        )

        result = await repo.get_trending_tickers("bullish", min_scans=3)
        assert result == []

    @pytest.mark.asyncio
    async def test_consistent_direction_qualifies(self, repo: Repository) -> None:
        """Ticker with consistent bullish direction across 3 scans qualifies."""
        base_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
        for i in range(3):
            scan_id = await repo.save_scan_run(
                make_scan_run(started_at=base_time + timedelta(days=i))
            )
            await repo.save_ticker_scores(
                scan_id,
                [
                    make_ticker_score(
                        ticker="AAPL",
                        composite_score=70.0 + i,
                        direction=SignalDirection.BULLISH,
                    )
                ],
            )

        result = await repo.get_trending_tickers("bullish", min_scans=3)
        assert len(result) == 1
        assert result[0].ticker == "AAPL"
        assert result[0].consecutive_scans == 3
        assert result[0].direction == "bullish"

    @pytest.mark.asyncio
    async def test_broken_streak_excluded(self, repo: Repository) -> None:
        """Ticker with a broken streak does not meet min_scans threshold.

        Scans (oldest to newest): bullish, bearish, bullish.
        From most recent: bullish(1) then bearish breaks the streak -> consecutive=1.
        With min_scans=2, this ticker should be excluded.
        """
        base_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
        directions = [SignalDirection.BULLISH, SignalDirection.BEARISH, SignalDirection.BULLISH]
        for i, direction in enumerate(directions):
            scan_id = await repo.save_scan_run(
                make_scan_run(started_at=base_time + timedelta(days=i))
            )
            await repo.save_ticker_scores(
                scan_id,
                [make_ticker_score(ticker="AAPL", direction=direction)],
            )

        result = await repo.get_trending_tickers("bullish", min_scans=2)
        assert result == []

    @pytest.mark.asyncio
    async def test_score_change_computed(self, repo: Repository) -> None:
        """score_change is latest_score - oldest_score_in_streak."""
        base_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
        scores = [70.0, 74.0, 80.0]
        for i, score in enumerate(scores):
            scan_id = await repo.save_scan_run(
                make_scan_run(started_at=base_time + timedelta(days=i))
            )
            await repo.save_ticker_scores(
                scan_id,
                [
                    make_ticker_score(
                        ticker="AAPL",
                        composite_score=score,
                        direction=SignalDirection.BULLISH,
                    )
                ],
            )

        result = await repo.get_trending_tickers("bullish", min_scans=3)
        assert len(result) == 1
        # latest=80.0, oldest in streak=70.0 -> change=10.0
        assert result[0].latest_score == pytest.approx(80.0)
        assert result[0].score_change == pytest.approx(10.0)

    @pytest.mark.asyncio
    async def test_sorted_by_consecutive_scans(self, repo: Repository) -> None:
        """Trending tickers sorted by consecutive_scans descending."""
        base_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
        # Create 4 scans
        for i in range(4):
            scan_id = await repo.save_scan_run(
                make_scan_run(started_at=base_time + timedelta(days=i))
            )
            # AAPL is bullish in all 4 scans
            await repo.save_ticker_scores(
                scan_id,
                [
                    make_ticker_score(
                        ticker="AAPL",
                        composite_score=70.0 + i,
                        direction=SignalDirection.BULLISH,
                    ),
                ],
            )
            # MSFT is bullish only in last 2 scans
            if i < 2:
                await repo.save_ticker_scores(
                    scan_id,
                    [
                        make_ticker_score(
                            ticker="MSFT",
                            composite_score=60.0 + i,
                            direction=SignalDirection.BEARISH,
                        )
                    ],
                )
            else:
                await repo.save_ticker_scores(
                    scan_id,
                    [
                        make_ticker_score(
                            ticker="MSFT",
                            composite_score=60.0 + i,
                            direction=SignalDirection.BULLISH,
                        )
                    ],
                )

        result = await repo.get_trending_tickers("bullish", min_scans=2)
        assert len(result) == 2
        assert result[0].ticker == "AAPL"
        assert result[0].consecutive_scans == 4
        assert result[1].ticker == "MSFT"
        assert result[1].consecutive_scans == 2

    @pytest.mark.asyncio
    async def test_returns_typed_trending_tickers(self, repo: Repository) -> None:
        """get_trending_tickers returns TrendingTicker instances."""
        base_time = datetime(2026, 1, 10, 10, 0, 0, tzinfo=UTC)
        for i in range(3):
            scan_id = await repo.save_scan_run(
                make_scan_run(started_at=base_time + timedelta(days=i))
            )
            await repo.save_ticker_scores(
                scan_id,
                [
                    make_ticker_score(
                        ticker="AAPL",
                        direction=SignalDirection.BULLISH,
                    )
                ],
            )

        result = await repo.get_trending_tickers("bullish", min_scans=3)
        assert len(result) == 1
        assert isinstance(result[0], TrendingTicker)


# ===========================================================================
# API endpoint tests
# ===========================================================================


@pytest.fixture()
def mock_repo() -> MagicMock:
    """Mock Repository with async method stubs for API tests."""
    repo = MagicMock()
    repo.get_score_history = AsyncMock(return_value=[])
    repo.get_trending_tickers = AsyncMock(return_value=[])
    return repo


@pytest.fixture()
def test_app(mock_repo: MagicMock) -> object:
    """Create test FastAPI app with dependency overrides."""
    import asyncio  # noqa: PLC0415

    from options_arena.api.app import create_app  # noqa: PLC0415
    from options_arena.api.deps import (  # noqa: PLC0415
        get_fred,
        get_market_data,
        get_operation_lock,
        get_options_data,
        get_repo,
        get_settings,
        get_universe,
    )
    from options_arena.models.config import AppSettings  # noqa: PLC0415

    app = create_app()
    app.dependency_overrides[get_repo] = lambda: mock_repo
    app.dependency_overrides[get_market_data] = lambda: MagicMock()
    app.dependency_overrides[get_options_data] = lambda: MagicMock()
    app.dependency_overrides[get_fred] = lambda: MagicMock()
    app.dependency_overrides[get_universe] = lambda: MagicMock()
    app.dependency_overrides[get_settings] = lambda: AppSettings()
    app.dependency_overrides[get_operation_lock] = lambda: asyncio.Lock()
    return app


@pytest_asyncio.fixture
async def client(test_app: object) -> AsyncClient:
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=test_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac  # type: ignore[misc]


class TestTickerHistoryEndpoint:
    """Tests for GET /api/ticker/{ticker}/history."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Returns empty list when no history exists."""
        response = await client.get("/api/ticker/AAPL/history")
        assert response.status_code == 200
        assert response.json() == []
        mock_repo.get_score_history.assert_called_once_with("AAPL", limit=20)

    @pytest.mark.asyncio
    async def test_returns_history_points(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Returns HistoryPoint data when history exists."""
        mock_repo.get_score_history.return_value = [
            HistoryPoint(
                scan_id=1,
                scan_date=datetime(2026, 1, 15, 10, 30, 0, tzinfo=UTC),
                composite_score=78.5,
                direction="bullish",
                preset="sp500",
            )
        ]
        response = await client.get("/api/ticker/AAPL/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["scan_id"] == 1
        assert data[0]["composite_score"] == pytest.approx(78.5)

    @pytest.mark.asyncio
    async def test_custom_limit(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Respects custom limit query parameter."""
        response = await client.get("/api/ticker/AAPL/history?limit=5")
        assert response.status_code == 200
        mock_repo.get_score_history.assert_called_once_with("AAPL", limit=5)


class TestTrendingEndpoint:
    """Tests for GET /api/ticker/trending."""

    @pytest.mark.asyncio
    async def test_returns_empty_list(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Returns empty list when no trending tickers exist."""
        response = await client.get("/api/ticker/trending")
        assert response.status_code == 200
        assert response.json() == []
        mock_repo.get_trending_tickers.assert_called_once_with("bullish", min_scans=3)

    @pytest.mark.asyncio
    async def test_returns_trending_tickers(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Returns TrendingTicker data when trending tickers exist."""
        mock_repo.get_trending_tickers.return_value = [
            TrendingTicker(
                ticker="AAPL",
                direction="bullish",
                consecutive_scans=5,
                latest_score=82.3,
                score_change=4.1,
            )
        ]
        response = await client.get("/api/ticker/trending?direction=bullish")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"
        assert data[0]["consecutive_scans"] == 5

    @pytest.mark.asyncio
    async def test_custom_parameters(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Respects custom direction and min_scans parameters."""
        response = await client.get("/api/ticker/trending?direction=bearish&min_scans=5")
        assert response.status_code == 200
        mock_repo.get_trending_tickers.assert_called_once_with("bearish", min_scans=5)
