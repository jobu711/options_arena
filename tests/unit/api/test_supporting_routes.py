"""Tests for supporting page routes — health, universe, config."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from options_arena.models import HealthStatus


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
    """GET /api/universe returns universe stats."""
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["AAPL", "MSFT", "GOOGL"])
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=["AAPL", "MSFT"])
    response = await client.get("/api/universe")
    assert response.status_code == 200
    data = response.json()
    assert data["optionable_count"] == 3
    assert data["sp500_count"] == 2


async def test_universe_refresh(client: AsyncClient, mock_universe: MagicMock) -> None:
    """POST /api/universe/refresh returns updated stats."""
    mock_universe.fetch_optionable_tickers = AsyncMock(
        return_value=["AAPL", "MSFT", "GOOGL", "TSLA"]
    )
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=["AAPL", "MSFT"])
    response = await client.post("/api/universe/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["optionable_count"] == 4


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
