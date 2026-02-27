"""Tests for GET /api/debate/trend/{ticker} endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.models import DebateTrendPoint, SignalDirection


def _make_trend_point(
    ticker: str = "AAPL",
    direction: SignalDirection = SignalDirection.BULLISH,
    confidence: float = 0.72,
    is_fallback: bool = False,
) -> DebateTrendPoint:
    """Build a sample DebateTrendPoint for tests."""
    return DebateTrendPoint(
        ticker=ticker,
        direction=direction,
        confidence=confidence,
        is_fallback=is_fallback,
        created_at=datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC),
    )


async def test_debate_trend_success(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate/trend/AAPL returns 200 with trend data."""
    point = _make_trend_point()
    mock_repo.get_debate_trend_for_ticker = AsyncMock(return_value=[point])

    response = await client.get("/api/debate/trend/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert len(data["points"]) == 1
    assert data["points"][0]["direction"] == "bullish"
    assert data["points"][0]["confidence"] == pytest.approx(0.72)


async def test_debate_trend_empty_404(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/debate/trend/AAPL returns 404 when no trend data exists."""
    mock_repo.get_debate_trend_for_ticker = AsyncMock(return_value=[])

    response = await client.get("/api/debate/trend/AAPL")
    assert response.status_code == 404


async def test_debate_trend_with_limit(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Verify limit param is passed through to repository."""
    mock_repo.get_debate_trend_for_ticker = AsyncMock(return_value=[_make_trend_point()])

    response = await client.get("/api/debate/trend/AAPL?limit=5")
    assert response.status_code == 200
    mock_repo.get_debate_trend_for_ticker.assert_called_once_with("AAPL", limit=5)


async def test_debate_trend_uppercase(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Ticker lowercased in request is uppercased in response."""
    mock_repo.get_debate_trend_for_ticker = AsyncMock(return_value=[_make_trend_point()])

    response = await client.get("/api/debate/trend/aapl")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    mock_repo.get_debate_trend_for_ticker.assert_called_once_with("AAPL", limit=20)


async def test_debate_trend_response_shape(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Verify response has ticker and points fields with correct shapes."""
    points = [
        _make_trend_point(confidence=0.60),
        _make_trend_point(confidence=0.75),
    ]
    mock_repo.get_debate_trend_for_ticker = AsyncMock(return_value=points)

    response = await client.get("/api/debate/trend/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert "ticker" in data
    assert "points" in data
    assert isinstance(data["points"], list)
    assert len(data["points"]) == 2
    for pt in data["points"]:
        assert "ticker" in pt
        assert "direction" in pt
        assert "confidence" in pt
        assert "is_fallback" in pt
        assert "created_at" in pt


async def test_debate_trend_default_limit(client: AsyncClient, mock_repo: MagicMock) -> None:
    """No limit param uses default 20."""
    mock_repo.get_debate_trend_for_ticker = AsyncMock(return_value=[_make_trend_point()])

    response = await client.get("/api/debate/trend/AAPL")
    assert response.status_code == 200
    mock_repo.get_debate_trend_for_ticker.assert_called_once_with("AAPL", limit=20)
