"""Tests for sector hierarchy endpoint and industry group score filtering (#230)."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from options_arena.api.app import create_app, limiter
from options_arena.api.deps import (
    get_repo,
    get_settings,
    get_universe,
)
from options_arena.models.config import AppSettings
from options_arena.models.enums import SignalDirection
from options_arena.models.scan import IndicatorSignals, TickerScore
from options_arena.services.universe import SP500Constituent


@pytest.fixture(autouse=True)
def _restore_limiter_state() -> Generator[None]:
    """Restore limiter state after each test to prevent cross-test leakage."""
    previous = limiter.enabled
    yield
    limiter.enabled = previous


def _make_constituents() -> list[SP500Constituent]:
    """Build a small set of S&P 500 constituents for testing."""
    return [
        SP500Constituent(ticker="AAPL", sector="Information Technology"),
        SP500Constituent(ticker="MSFT", sector="Information Technology"),
        SP500Constituent(ticker="GOOGL", sector="Communication Services"),
        SP500Constituent(ticker="XOM", sector="Energy"),
        SP500Constituent(ticker="CVX", sector="Energy"),
        SP500Constituent(ticker="NEM", sector="Materials"),
    ]


def _make_score(
    ticker: str,
    *,
    score: float = 50.0,
    industry_group: str | None = None,
) -> TickerScore:
    """Build a minimal TickerScore for filtering tests."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(),
        industry_group=industry_group,
    )


@pytest.fixture()
def hierarchy_app() -> create_app:
    """Create a test app with mocked universe service for hierarchy endpoint."""
    import asyncio  # noqa: PLC0415

    app = create_app()
    limiter.enabled = False

    mock_universe = MagicMock()
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=_make_constituents())
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["AAPL", "MSFT"])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=[])

    mock_repo = MagicMock()
    mock_repo.get_scan_by_id = AsyncMock(return_value=None)
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])

    app.dependency_overrides[get_universe] = lambda: mock_universe
    app.dependency_overrides[get_repo] = lambda: mock_repo
    app.dependency_overrides[get_settings] = lambda: AppSettings()

    # Initialize app.state attributes
    app.state.cache = MagicMock()
    app.state.limiter = MagicMock()
    app.state.scan_counter = 0
    app.state.active_scans = {}
    app.state.scan_queues = {}
    app.state.debate_counter = 0
    app.state.debate_queues = {}
    app.state.batch_counter = 0
    app.state.batch_queues = {}
    app.state.operation_lock = asyncio.Lock()

    return app


@pytest.fixture()
async def hierarchy_client(hierarchy_app: create_app) -> AsyncClient:  # type: ignore[type-arg]
    """Async HTTP client for hierarchy tests."""
    transport = ASGITransport(app=hierarchy_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac  # type: ignore[misc]


class TestSectorsHierarchyEndpoint:
    """Tests for GET /api/universe/sectors returning hierarchical data."""

    @pytest.mark.asyncio()
    async def test_returns_nested_structure(self, hierarchy_client: AsyncClient) -> None:
        """Verify sectors contain industry_groups array."""
        response = await hierarchy_client.get("/api/universe/sectors")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 11  # All 11 GICS sectors

        # Each entry should have name, ticker_count, industry_groups
        for item in data:
            assert "name" in item
            assert "ticker_count" in item
            assert "industry_groups" in item
            assert isinstance(item["industry_groups"], list)

    @pytest.mark.asyncio()
    async def test_sector_counts_are_accurate(self, hierarchy_client: AsyncClient) -> None:
        """Verify ticker_count reflects actual data."""
        response = await hierarchy_client.get("/api/universe/sectors")
        data = response.json()

        # Find Energy sector — should have 2 tickers (XOM, CVX)
        energy = next(s for s in data if s["name"] == "Energy")
        assert energy["ticker_count"] == 2

        # Materials should have 1 ticker (NEM)
        materials = next(s for s in data if s["name"] == "Materials")
        assert materials["ticker_count"] == 1

    @pytest.mark.asyncio()
    async def test_single_group_sector_has_count(self, hierarchy_client: AsyncClient) -> None:
        """Verify single-group sectors inherit the full sector count."""
        response = await hierarchy_client.get("/api/universe/sectors")
        data = response.json()

        # Materials has one industry group: Materials
        materials = next(s for s in data if s["name"] == "Materials")
        assert len(materials["industry_groups"]) == 1
        assert materials["industry_groups"][0]["name"] == "Materials"
        assert materials["industry_groups"][0]["ticker_count"] == 1

    @pytest.mark.asyncio()
    async def test_multi_group_sector_groups_listed(self, hierarchy_client: AsyncClient) -> None:
        """Verify multi-group sectors list all child industry groups."""
        response = await hierarchy_client.get("/api/universe/sectors")
        data = response.json()

        # Information Technology has 3 industry groups
        it = next(s for s in data if s["name"] == "Information Technology")
        assert len(it["industry_groups"]) == 3
        ig_names = {ig["name"] for ig in it["industry_groups"]}
        assert "Semiconductors & Semiconductor Equipment" in ig_names
        assert "Software & Services" in ig_names
        assert "Technology Hardware & Equipment" in ig_names

    @pytest.mark.asyncio()
    async def test_empty_sector_has_zero_count(self, hierarchy_client: AsyncClient) -> None:
        """Verify sectors not in test data have zero ticker_count."""
        response = await hierarchy_client.get("/api/universe/sectors")
        data = response.json()

        # Health Care is not in our test data
        hc = next(s for s in data if s["name"] == "Health Care")
        assert hc["ticker_count"] == 0


class TestScoreFilteringByIndustryGroup:
    """Tests for industry_groups query param on GET /api/scan/{id}/scores."""

    @pytest.fixture()
    def score_app(self) -> create_app:
        """Create test app with scores that have industry_group set."""
        import asyncio  # noqa: PLC0415

        app = create_app()
        limiter.enabled = False

        scores = [
            _make_score("AAPL", score=80.0, industry_group="Software & Services"),
            _make_score(
                "NVDA",
                score=75.0,
                industry_group="Semiconductors & Semiconductor Equipment",
            ),
            _make_score("XOM", score=60.0, industry_group="Oil Gas & Consumable Fuels"),
            _make_score("JPM", score=55.0, industry_group="Banks"),
        ]

        mock_scan = MagicMock()
        mock_scan.id = 1

        mock_repo = MagicMock()
        mock_repo.get_scan_by_id = AsyncMock(return_value=mock_scan)
        mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)

        app.dependency_overrides[get_repo] = lambda: mock_repo
        app.dependency_overrides[get_settings] = lambda: AppSettings()

        app.state.cache = MagicMock()
        app.state.limiter = MagicMock()
        app.state.scan_counter = 0
        app.state.active_scans = {}
        app.state.scan_queues = {}
        app.state.debate_counter = 0
        app.state.debate_queues = {}
        app.state.batch_counter = 0
        app.state.batch_queues = {}
        app.state.operation_lock = asyncio.Lock()

        return app

    @pytest.mark.asyncio()
    async def test_filter_by_single_industry_group(self, score_app: create_app) -> None:
        """Verify filtering by a single industry group returns matching tickers."""
        transport = ASGITransport(app=score_app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/scan/1/scores?industry_groups=Banks")
            assert response.status_code == 200
            data = response.json()
            tickers = [item["ticker"] for item in data["items"]]
            assert tickers == ["JPM"]

    @pytest.mark.asyncio()
    async def test_filter_by_multiple_industry_groups(self, score_app: create_app) -> None:
        """Verify comma-separated groups filter with OR logic."""
        transport = ASGITransport(app=score_app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get(
                "/api/scan/1/scores?industry_groups=Banks,Software %26 Services"
            )
            assert response.status_code == 200
            data = response.json()
            tickers = {item["ticker"] for item in data["items"]}
            assert "JPM" in tickers
            assert "AAPL" in tickers
            assert len(tickers) == 2

    @pytest.mark.asyncio()
    async def test_no_filter_returns_all(self, score_app: create_app) -> None:
        """Verify no industry_groups param returns all scores."""
        transport = ASGITransport(app=score_app)  # type: ignore[arg-type]
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/scan/1/scores")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 4
