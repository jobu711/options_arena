"""Tests for watchlist API routes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

from options_arena.models import Watchlist, WatchlistTicker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_watchlist(wl_id: int = 1) -> Watchlist:
    return Watchlist(
        id=wl_id,
        name="My Watchlist",
        description="Test description",
        created_at=datetime(2026, 2, 27, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 2, 27, 10, 0, 0, tzinfo=UTC),
    )


def _make_watchlist_ticker(ticker: str = "AAPL", wl_id: int = 1) -> WatchlistTicker:
    return WatchlistTicker(
        id=1,
        watchlist_id=wl_id,
        ticker=ticker,
        added_at=datetime(2026, 2, 27, 10, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# POST /api/watchlists — create
# ---------------------------------------------------------------------------


async def test_create_watchlist_201(client: AsyncClient, mock_repo: MagicMock) -> None:
    """POST /api/watchlists with valid name returns 201 with watchlist data."""
    mock_repo.create_watchlist = AsyncMock(return_value=1)
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=_make_watchlist())

    response = await client.post("/api/watchlists", json={"name": "My Watchlist"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Watchlist"
    assert data["id"] == 1


async def test_create_watchlist_duplicate_409(client: AsyncClient, mock_repo: MagicMock) -> None:
    """POST /api/watchlists with duplicate name returns 409."""
    mock_repo.create_watchlist = AsyncMock(
        side_effect=sqlite3.IntegrityError("UNIQUE constraint failed")
    )

    response = await client.post("/api/watchlists", json={"name": "Duplicate"})
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/watchlists — list
# ---------------------------------------------------------------------------


async def test_list_watchlists_empty(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/watchlists returns 200 with empty list when no watchlists."""
    mock_repo.get_all_watchlists = AsyncMock(return_value=[])

    response = await client.get("/api/watchlists")
    assert response.status_code == 200
    assert response.json() == []


async def test_list_watchlists_returns_data(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/watchlists returns list of watchlists."""
    mock_repo.get_all_watchlists = AsyncMock(return_value=[_make_watchlist(1), _make_watchlist(2)])

    response = await client.get("/api/watchlists")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


# ---------------------------------------------------------------------------
# GET /api/watchlists/{id} — detail
# ---------------------------------------------------------------------------


async def test_get_watchlist_detail_200(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/watchlists/1 returns 200 with watchlist detail including tickers."""
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=_make_watchlist())
    mock_repo.get_tickers_for_watchlist = AsyncMock(
        return_value=[_make_watchlist_ticker("AAPL"), _make_watchlist_ticker("MSFT")]
    )

    response = await client.get("/api/watchlists/1")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "My Watchlist"
    assert len(data["tickers"]) == 2
    assert data["tickers"][0]["ticker"] == "AAPL"


async def test_get_watchlist_not_found_404(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/watchlists/999 returns 404 when not found."""
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=None)

    response = await client.get("/api/watchlists/999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/watchlists/{id} — update
# ---------------------------------------------------------------------------


async def test_update_watchlist_200(client: AsyncClient, mock_repo: MagicMock) -> None:
    """PUT /api/watchlists/1 returns 200 with updated watchlist."""
    original = _make_watchlist()
    updated = Watchlist(
        id=1,
        name="Updated Name",
        description="Updated desc",
        created_at=datetime(2026, 2, 27, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 2, 27, 11, 0, 0, tzinfo=UTC),
    )
    # First call returns original (existence check), second returns updated
    mock_repo.get_watchlist_by_id = AsyncMock(side_effect=[original, updated])
    mock_repo.update_watchlist = AsyncMock(return_value=None)

    response = await client.put(
        "/api/watchlists/1",
        json={"name": "Updated Name", "description": "Updated desc"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"


# ---------------------------------------------------------------------------
# DELETE /api/watchlists/{id} — delete
# ---------------------------------------------------------------------------


async def test_delete_watchlist_204(client: AsyncClient, mock_repo: MagicMock) -> None:
    """DELETE /api/watchlists/1 returns 204."""
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=_make_watchlist())
    mock_repo.delete_watchlist = AsyncMock(return_value=None)

    response = await client.delete("/api/watchlists/1")
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# POST /api/watchlists/{id}/tickers — add ticker
# ---------------------------------------------------------------------------


async def test_add_ticker_201(client: AsyncClient, mock_repo: MagicMock) -> None:
    """POST /api/watchlists/1/tickers returns 201 with new ticker."""
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=_make_watchlist())
    mock_repo.add_ticker_to_watchlist = AsyncMock(return_value=None)
    mock_repo.get_tickers_for_watchlist = AsyncMock(return_value=[_make_watchlist_ticker("AAPL")])

    response = await client.post("/api/watchlists/1/tickers", json={"ticker": "AAPL"})
    assert response.status_code == 201
    data = response.json()
    assert data["ticker"] == "AAPL"


async def test_add_ticker_duplicate_409(client: AsyncClient, mock_repo: MagicMock) -> None:
    """POST /api/watchlists/1/tickers with duplicate ticker returns 409."""
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=_make_watchlist())
    mock_repo.add_ticker_to_watchlist = AsyncMock(
        side_effect=sqlite3.IntegrityError("UNIQUE constraint failed")
    )

    response = await client.post("/api/watchlists/1/tickers", json={"ticker": "AAPL"})
    assert response.status_code == 409
    assert "already in watchlist" in response.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /api/watchlists/{id}/tickers/{ticker} — remove ticker
# ---------------------------------------------------------------------------


async def test_remove_ticker_204(client: AsyncClient, mock_repo: MagicMock) -> None:
    """DELETE /api/watchlists/1/tickers/AAPL returns 204."""
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=_make_watchlist())
    mock_repo.remove_ticker_from_watchlist = AsyncMock(return_value=None)

    response = await client.delete("/api/watchlists/1/tickers/AAPL")
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# Ticker operations on missing watchlist
# ---------------------------------------------------------------------------


async def test_watchlist_not_found_for_ticker_ops_404(
    client: AsyncClient, mock_repo: MagicMock
) -> None:
    """Ticker operations on nonexistent watchlist return 404."""
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=None)

    # Add ticker to missing watchlist
    add_resp = await client.post("/api/watchlists/999/tickers", json={"ticker": "AAPL"})
    assert add_resp.status_code == 404

    # Remove ticker from missing watchlist
    remove_resp = await client.delete("/api/watchlists/999/tickers/AAPL")
    assert remove_resp.status_code == 404
