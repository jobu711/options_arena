"""Tests for watchlist API routes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.models import Watchlist, WatchlistTicker

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_repo_watchlist(mock_repo: MagicMock) -> MagicMock:
    """Extend mock_repo with watchlist method stubs."""
    mock_repo.create_watchlist = AsyncMock(
        return_value=Watchlist(
            id=1, name="Test", created_at=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
        )
    )
    mock_repo.delete_watchlist = AsyncMock(return_value=None)
    mock_repo.get_watchlists = AsyncMock(return_value=[])
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=None)
    mock_repo.get_watchlist_by_name = AsyncMock(return_value=None)
    mock_repo.add_ticker_to_watchlist = AsyncMock(return_value=None)
    mock_repo.remove_ticker_from_watchlist = AsyncMock(return_value=None)
    mock_repo.get_tickers_for_watchlist = AsyncMock(return_value=[])
    mock_repo.get_last_debate_dates = AsyncMock(return_value={})
    return mock_repo


# ---------------------------------------------------------------------------
# POST /api/watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_watchlist_success(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """POST /api/watchlist creates a watchlist and returns 201."""
    response = await client.post("/api/watchlist", json={"name": "My Picks"})
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Test"
    mock_repo_watchlist.create_watchlist.assert_awaited_once_with("My Picks")


@pytest.mark.asyncio
async def test_create_watchlist_duplicate_409(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """POST /api/watchlist returns 409 on duplicate name."""
    mock_repo_watchlist.create_watchlist.side_effect = sqlite3.IntegrityError(
        "UNIQUE constraint failed"
    )
    response = await client.post("/api/watchlist", json={"name": "Existing"})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_watchlist_missing_name(client: AsyncClient) -> None:
    """POST /api/watchlist returns 422 if name is missing."""
    response = await client.post("/api/watchlist", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/watchlist/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_watchlist_success(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """DELETE /api/watchlist/{id} deletes and returns 204."""
    mock_repo_watchlist.get_watchlist_by_id.return_value = Watchlist(
        id=1, name="Test", created_at=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
    )
    response = await client.delete("/api/watchlist/1")
    assert response.status_code == 204
    mock_repo_watchlist.delete_watchlist.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_delete_watchlist_not_found(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """DELETE /api/watchlist/{id} returns 404 if not found."""
    mock_repo_watchlist.get_watchlist_by_id.return_value = None
    response = await client.delete("/api/watchlist/999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_watchlists_empty(client: AsyncClient, mock_repo_watchlist: MagicMock) -> None:
    """GET /api/watchlist returns empty list when no watchlists exist."""
    response = await client.get("/api/watchlist")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_watchlists_with_data(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """GET /api/watchlist returns all watchlists."""
    mock_repo_watchlist.get_watchlists.return_value = [
        Watchlist(id=1, name="Alpha", created_at=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)),
        Watchlist(id=2, name="Beta", created_at=datetime(2026, 2, 27, 13, 0, 0, tzinfo=UTC)),
    ]
    response = await client.get("/api/watchlist")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Alpha"
    assert data[1]["name"] == "Beta"


# ---------------------------------------------------------------------------
# GET /api/watchlist/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watchlist_detail_not_found(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """GET /api/watchlist/{id} returns 404 if not found."""
    response = await client.get("/api/watchlist/999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_watchlist_detail_empty_tickers(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """GET /api/watchlist/{id} returns watchlist with empty tickers list."""
    mock_repo_watchlist.get_watchlist_by_id.return_value = Watchlist(
        id=1, name="Empty", created_at=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
    )
    response = await client.get("/api/watchlist/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Empty"
    assert data["tickers"] == []


@pytest.mark.asyncio
async def test_get_watchlist_detail_with_tickers(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """GET /api/watchlist/{id} returns enriched ticker data."""
    ts = datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
    mock_repo_watchlist.get_watchlist_by_id.return_value = Watchlist(
        id=1, name="Tech", created_at=ts
    )
    mock_repo_watchlist.get_tickers_for_watchlist.return_value = [
        WatchlistTicker(id=1, watchlist_id=1, ticker="AAPL", added_at=ts),
    ]
    # No latest scan
    mock_repo_watchlist.get_latest_scan.return_value = None

    response = await client.get("/api/watchlist/1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["tickers"]) == 1
    assert data["tickers"][0]["ticker"] == "AAPL"
    assert data["tickers"][0]["composite_score"] is None


# ---------------------------------------------------------------------------
# POST /api/watchlist/{id}/tickers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_ticker_success(client: AsyncClient, mock_repo_watchlist: MagicMock) -> None:
    """POST /api/watchlist/{id}/tickers adds a ticker and returns 201."""
    mock_repo_watchlist.get_watchlist_by_id.return_value = Watchlist(
        id=1, name="Test", created_at=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
    )
    response = await client.post("/api/watchlist/1/tickers", json={"ticker": "AAPL"})
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "added"
    assert data["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_add_ticker_watchlist_not_found(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """POST /api/watchlist/{id}/tickers returns 404 if watchlist not found."""
    mock_repo_watchlist.get_watchlist_by_id.return_value = None
    response = await client.post("/api/watchlist/999/tickers", json={"ticker": "AAPL"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_ticker_duplicate_409(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """POST /api/watchlist/{id}/tickers returns 409 on duplicate."""
    mock_repo_watchlist.get_watchlist_by_id.return_value = Watchlist(
        id=1, name="Test", created_at=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
    )
    mock_repo_watchlist.add_ticker_to_watchlist.side_effect = sqlite3.IntegrityError(
        "UNIQUE constraint failed"
    )
    response = await client.post("/api/watchlist/1/tickers", json={"ticker": "AAPL"})
    assert response.status_code == 409
    assert "already in watchlist" in response.json()["detail"]


@pytest.mark.asyncio
async def test_add_ticker_missing_body(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """POST /api/watchlist/{id}/tickers returns 422 if ticker is missing."""
    mock_repo_watchlist.get_watchlist_by_id.return_value = Watchlist(
        id=1, name="Test", created_at=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
    )
    response = await client.post("/api/watchlist/1/tickers", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/watchlist/{id}/tickers/{ticker}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_ticker_success(client: AsyncClient, mock_repo_watchlist: MagicMock) -> None:
    """DELETE /api/watchlist/{id}/tickers/{ticker} removes and returns 204."""
    mock_repo_watchlist.get_watchlist_by_id.return_value = Watchlist(
        id=1, name="Test", created_at=datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
    )
    response = await client.delete("/api/watchlist/1/tickers/AAPL")
    assert response.status_code == 204
    mock_repo_watchlist.remove_ticker_from_watchlist.assert_awaited_once_with(1, "AAPL")


@pytest.mark.asyncio
async def test_remove_ticker_watchlist_not_found(
    client: AsyncClient, mock_repo_watchlist: MagicMock
) -> None:
    """DELETE /api/watchlist/{id}/tickers/{ticker} returns 404 if watchlist not found."""
    mock_repo_watchlist.get_watchlist_by_id.return_value = None
    response = await client.delete("/api/watchlist/999/tickers/AAPL")
    assert response.status_code == 404
