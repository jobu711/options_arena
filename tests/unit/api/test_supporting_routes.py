"""Tests for supporting page routes — health, universe, config."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from options_arena.models import HealthStatus
from options_arena.services.universe import SP500Constituent


async def test_health_check(client: AsyncClient) -> None:
    """GET /api/health returns ok."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("options_arena.api.routes.health.HealthService")
async def test_health_services(mock_cls: MagicMock, client: AsyncClient) -> None:
    """GET /api/health/services returns service statuses."""
    mock_instance = MagicMock()
    mock_instance.check_all = AsyncMock(
        return_value=[
            HealthStatus(
                service_name="groq",
                available=True,
                latency_ms=50.0,
                checked_at=datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC),
            ),
            HealthStatus(
                service_name="yfinance",
                available=False,
                latency_ms=100.0,
                error="timeout",
                checked_at=datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC),
            ),
        ]
    )
    mock_instance.close = AsyncMock()
    mock_cls.return_value = mock_instance

    response = await client.get("/api/health/services")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["service_name"] == "groq"
    assert data[0]["available"] is True
    assert data[1]["available"] is False


async def test_universe_stats(client: AsyncClient, mock_universe: MagicMock) -> None:
    """GET /api/universe returns universe stats with etf_count."""
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["AAPL", "MSFT", "GOOGL"])
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=["AAPL", "MSFT"])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=["SPY", "QQQ"])
    response = await client.get("/api/universe")
    assert response.status_code == 200
    data = response.json()
    assert data["optionable_count"] == 3
    assert data["sp500_count"] == 2
    assert data["etf_count"] == 2


async def test_universe_refresh(client: AsyncClient, mock_universe: MagicMock) -> None:
    """POST /api/universe/refresh returns updated stats with etf_count."""
    mock_universe.fetch_optionable_tickers = AsyncMock(
        return_value=["AAPL", "MSFT", "GOOGL", "TSLA"]
    )
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=["AAPL", "MSFT"])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=["SPY"])
    response = await client.post("/api/universe/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["optionable_count"] == 4
    assert data["etf_count"] == 1


async def test_universe_sectors(client: AsyncClient, mock_universe: MagicMock) -> None:
    """GET /api/universe/sectors returns hierarchical GICS sectors with ticker counts."""
    mock_universe.fetch_sp500_constituents = AsyncMock(
        return_value=[
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="MSFT", sector="Information Technology"),
            SP500Constituent(ticker="GOOGL", sector="Communication Services"),
            SP500Constituent(ticker="XOM", sector="Energy"),
        ]
    )
    response = await client.get("/api/universe/sectors")
    assert response.status_code == 200
    data = response.json()

    # Should return all 11 GICS sectors (hierarchical response)
    assert len(data) == 11

    # Verify sorted alphabetically
    names = [s["name"] for s in data]
    assert names == sorted(names)

    # Each sector has industry_groups array
    for item in data:
        assert "industry_groups" in item
        assert isinstance(item["industry_groups"], list)

    # Verify counts for sectors with data
    sector_map = {s["name"]: s["ticker_count"] for s in data}
    assert sector_map["Information Technology"] == 2
    assert sector_map["Communication Services"] == 1
    assert sector_map["Energy"] == 1

    # Sectors without data have zero count
    assert sector_map["Health Care"] == 0


async def test_universe_sectors_empty(client: AsyncClient, mock_universe: MagicMock) -> None:
    """GET /api/universe/sectors returns all 11 sectors with zero counts when no S&P 500 data."""
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])
    response = await client.get("/api/universe/sectors")
    assert response.status_code == 200
    data = response.json()
    # Hierarchical response always returns all 11 GICS sectors
    assert len(data) == 11
    # All ticker counts should be zero
    for item in data:
        assert item["ticker_count"] == 0
        assert isinstance(item["industry_groups"], list)


async def test_universe_sectors_all_eleven(client: AsyncClient, mock_universe: MagicMock) -> None:
    """GET /api/universe/sectors returns all 11 GICS sectors when all present."""
    all_sectors = [
        "Communication Services",
        "Consumer Discretionary",
        "Consumer Staples",
        "Energy",
        "Financials",
        "Health Care",
        "Industrials",
        "Information Technology",
        "Materials",
        "Real Estate",
        "Utilities",
    ]
    constituents = [
        SP500Constituent(ticker=f"T{i}", sector=sector) for i, sector in enumerate(all_sectors)
    ]
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=constituents)
    response = await client.get("/api/universe/sectors")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 11


async def test_config_endpoint(client: AsyncClient) -> None:
    """GET /api/config returns safe config values."""
    response = await client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "groq_api_key_set" in data
    assert "enable_rebuttal" in data
    assert "enable_volatility_agent" in data
    assert "agent_timeout" in data
    assert data["scan_preset_default"] == "sp500"


async def test_config_hides_api_key(client: AsyncClient) -> None:
    """GET /api/config never exposes the actual API key."""
    response = await client.get("/api/config")
    data = response.json()
    # Should only have a boolean, never the actual key
    assert isinstance(data["groq_api_key_set"], bool)
    assert "api_key" not in data
