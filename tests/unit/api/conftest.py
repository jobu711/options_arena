"""Shared fixtures for API tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from options_arena.api.app import create_app
from options_arena.api.deps import (
    get_fred,
    get_market_data,
    get_operation_lock,
    get_options_data,
    get_repo,
    get_settings,
    get_universe,
)
from options_arena.models.config import AppSettings


@pytest.fixture()
def mock_repo() -> MagicMock:
    """Mock Repository with async method stubs."""
    repo = MagicMock()
    repo.get_recent_scans = AsyncMock(return_value=[])
    repo.get_latest_scan = AsyncMock(return_value=None)
    repo.get_scan_by_id = AsyncMock(return_value=None)
    repo.get_scores_for_scan = AsyncMock(return_value=[])
    repo.save_scan_run = AsyncMock(return_value=1)
    repo.save_ticker_scores = AsyncMock(return_value=None)
    repo.get_debate_by_id = AsyncMock(return_value=None)
    repo.get_debates_for_ticker = AsyncMock(return_value=[])
    repo.get_recent_debates = AsyncMock(return_value=[])
    repo.save_debate = AsyncMock(return_value=1)
    repo.get_last_debate_dates = AsyncMock(return_value={})
    return repo


@pytest.fixture()
def mock_market_data() -> MagicMock:
    """Mock MarketDataService."""
    return MagicMock()


@pytest.fixture()
def mock_options_data() -> MagicMock:
    """Mock OptionsDataService."""
    return MagicMock()


@pytest.fixture()
def mock_fred() -> MagicMock:
    """Mock FredService."""
    return MagicMock()


@pytest.fixture()
def mock_universe() -> MagicMock:
    """Mock UniverseService."""
    svc = MagicMock()
    svc.fetch_optionable_tickers = AsyncMock(return_value=["AAPL", "MSFT", "GOOGL"])
    svc.fetch_sp500_constituents = AsyncMock(return_value=[])
    return svc


@pytest.fixture()
def test_app(
    mock_repo: MagicMock,
    mock_market_data: MagicMock,
    mock_options_data: MagicMock,
    mock_fred: MagicMock,
    mock_universe: MagicMock,
) -> create_app:
    """Create a test FastAPI app with dependency overrides (no lifespan)."""
    import asyncio  # noqa: PLC0415

    app = create_app()
    app.dependency_overrides[get_repo] = lambda: mock_repo
    app.dependency_overrides[get_market_data] = lambda: mock_market_data
    app.dependency_overrides[get_options_data] = lambda: mock_options_data
    app.dependency_overrides[get_fred] = lambda: mock_fred
    app.dependency_overrides[get_universe] = lambda: mock_universe
    app.dependency_overrides[get_settings] = lambda: AppSettings()
    app.dependency_overrides[get_operation_lock] = lambda: asyncio.Lock()
    return app


@pytest.fixture()
async def client(test_app: create_app) -> AsyncClient:  # type: ignore[type-arg]
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=test_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac  # type: ignore[misc]
