"""Tests for ticker-specific API routes — info, history, trending."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from options_arena.models import TickerInfo
from options_arena.models.enums import DividendSource, MarketCapTier
from options_arena.utils import DataSourceUnavailableError, TickerNotFoundError


def _make_ticker_info(ticker: str = "AAPL") -> TickerInfo:
    """Build a realistic TickerInfo fixture."""
    return TickerInfo(
        ticker=ticker,
        company_name="Apple Inc.",
        sector="Information Technology",
        market_cap=3_000_000_000_000,
        market_cap_tier=MarketCapTier.MEGA,
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal("185.50"),
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("124.17"),
    )


async def test_ticker_info_success(client: AsyncClient, mock_market_data: MagicMock) -> None:
    """GET /api/ticker/{ticker}/info returns TickerInfo with company_name."""
    mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info())

    response = await client.get("/api/ticker/AAPL/info")

    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["company_name"] == "Apple Inc."
    assert data["sector"] == "Information Technology"
    assert data["market_cap"] == 3_000_000_000_000
    assert data["current_price"] == "185.50"


async def test_ticker_info_not_found(client: AsyncClient, mock_market_data: MagicMock) -> None:
    """GET /api/ticker/{ticker}/info returns 404 for unknown ticker."""
    mock_market_data.fetch_ticker_info = AsyncMock(side_effect=TickerNotFoundError("BADTK"))

    response = await client.get("/api/ticker/BADTK/info")

    assert response.status_code == 404
    assert "BADTK" in response.json()["detail"]


async def test_ticker_info_data_source_unavailable(
    client: AsyncClient, mock_market_data: MagicMock
) -> None:
    """GET /api/ticker/{ticker}/info returns 503 when data source is down."""
    mock_market_data.fetch_ticker_info = AsyncMock(
        side_effect=DataSourceUnavailableError("Yahoo Finance unavailable")
    )

    response = await client.get("/api/ticker/AAPL/info")

    assert response.status_code == 503


async def test_ticker_info_invalid_ticker_pattern(client: AsyncClient) -> None:
    """GET /api/ticker/{ticker}/info rejects invalid ticker patterns."""
    response = await client.get("/api/ticker/aapl/info")

    assert response.status_code == 422
