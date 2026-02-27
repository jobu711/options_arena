"""Tests for Repository — watchlist CRUD methods."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import Watchlist, WatchlistTicker

# ---------------------------------------------------------------------------
# Fixtures
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
# create_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_watchlist_returns_positive_id(repo: Repository) -> None:
    """create_watchlist returns integer ID > 0."""
    row_id = await repo.create_watchlist("My Watchlist")
    assert isinstance(row_id, int)
    assert row_id > 0


@pytest.mark.asyncio
async def test_create_watchlist_with_description(repo: Repository) -> None:
    """create_watchlist stores description when provided."""
    row_id = await repo.create_watchlist("Tech Stocks", description="FAANG and friends")
    wl = await repo.get_watchlist_by_id(row_id)
    assert wl is not None
    assert wl.description == "FAANG and friends"


@pytest.mark.asyncio
async def test_create_watchlist_duplicate_name_raises(repo: Repository) -> None:
    """Duplicate watchlist name raises IntegrityError."""
    await repo.create_watchlist("Unique Name")
    with pytest.raises(sqlite3.IntegrityError):
        await repo.create_watchlist("Unique Name")


# ---------------------------------------------------------------------------
# get_watchlist_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watchlist_by_id_found(repo: Repository) -> None:
    """get_watchlist_by_id returns Watchlist with correct fields."""
    row_id = await repo.create_watchlist("My WL", description="A test")
    wl = await repo.get_watchlist_by_id(row_id)
    assert wl is not None
    assert isinstance(wl, Watchlist)
    assert wl.id == row_id
    assert wl.name == "My WL"
    assert wl.description == "A test"
    assert isinstance(wl.created_at, datetime)
    assert wl.created_at.tzinfo is not None


@pytest.mark.asyncio
async def test_get_watchlist_by_id_not_found(repo: Repository) -> None:
    """get_watchlist_by_id returns None for nonexistent ID."""
    result = await repo.get_watchlist_by_id(999)
    assert result is None


# ---------------------------------------------------------------------------
# get_watchlist_by_name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watchlist_by_name_found(repo: Repository) -> None:
    """get_watchlist_by_name returns Watchlist when name exists."""
    await repo.create_watchlist("Sector Play")
    wl = await repo.get_watchlist_by_name("Sector Play")
    assert wl is not None
    assert isinstance(wl, Watchlist)
    assert wl.name == "Sector Play"


@pytest.mark.asyncio
async def test_get_watchlist_by_name_not_found(repo: Repository) -> None:
    """get_watchlist_by_name returns None for nonexistent name."""
    result = await repo.get_watchlist_by_name("No Such Watchlist")
    assert result is None


# ---------------------------------------------------------------------------
# get_all_watchlists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_watchlists_empty(repo: Repository) -> None:
    """get_all_watchlists returns empty list when no watchlists exist."""
    result = await repo.get_all_watchlists()
    assert result == []


@pytest.mark.asyncio
async def test_get_all_watchlists_multiple(repo: Repository) -> None:
    """get_all_watchlists returns all watchlists sorted by name ascending."""
    await repo.create_watchlist("Zebra")
    await repo.create_watchlist("Alpha")
    await repo.create_watchlist("Middle")

    result = await repo.get_all_watchlists()
    assert len(result) == 3
    names = [wl.name for wl in result]
    assert names == ["Alpha", "Middle", "Zebra"]


# ---------------------------------------------------------------------------
# add / remove tickers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_ticker_to_watchlist(repo: Repository) -> None:
    """Ticker is retrievable after being added to watchlist."""
    wl_id = await repo.create_watchlist("Test WL")
    await repo.add_ticker_to_watchlist(wl_id, "AAPL")

    tickers = await repo.get_tickers_for_watchlist(wl_id)
    assert len(tickers) == 1
    assert tickers[0].ticker == "AAPL"
    assert tickers[0].watchlist_id == wl_id


@pytest.mark.asyncio
async def test_add_duplicate_ticker_raises(repo: Repository) -> None:
    """Duplicate (watchlist_id, ticker) raises IntegrityError."""
    wl_id = await repo.create_watchlist("Dupes WL")
    await repo.add_ticker_to_watchlist(wl_id, "MSFT")
    with pytest.raises(sqlite3.IntegrityError):
        await repo.add_ticker_to_watchlist(wl_id, "MSFT")


@pytest.mark.asyncio
async def test_remove_ticker_from_watchlist(repo: Repository) -> None:
    """Ticker is gone after removal from watchlist."""
    wl_id = await repo.create_watchlist("Remove WL")
    await repo.add_ticker_to_watchlist(wl_id, "AAPL")
    await repo.add_ticker_to_watchlist(wl_id, "MSFT")

    await repo.remove_ticker_from_watchlist(wl_id, "AAPL")

    tickers = await repo.get_tickers_for_watchlist(wl_id)
    assert len(tickers) == 1
    assert tickers[0].ticker == "MSFT"


# ---------------------------------------------------------------------------
# get_tickers_for_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tickers_empty_watchlist(repo: Repository) -> None:
    """get_tickers_for_watchlist returns empty list for watchlist with no tickers."""
    wl_id = await repo.create_watchlist("Empty WL")
    result = await repo.get_tickers_for_watchlist(wl_id)
    assert result == []


@pytest.mark.asyncio
async def test_get_tickers_returns_typed_models(repo: Repository) -> None:
    """get_tickers_for_watchlist returns list[WatchlistTicker] with correct types."""
    wl_id = await repo.create_watchlist("Typed WL")
    await repo.add_ticker_to_watchlist(wl_id, "AAPL")
    await repo.add_ticker_to_watchlist(wl_id, "GOOG")

    tickers = await repo.get_tickers_for_watchlist(wl_id)
    assert len(tickers) == 2
    for t in tickers:
        assert isinstance(t, WatchlistTicker)
        assert isinstance(t.id, int)
        assert isinstance(t.watchlist_id, int)
        assert isinstance(t.ticker, str)
        assert isinstance(t.added_at, datetime)
        assert t.added_at.tzinfo is not None


# ---------------------------------------------------------------------------
# update_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_watchlist_name(repo: Repository) -> None:
    """update_watchlist changes the name."""
    wl_id = await repo.create_watchlist("Old Name")
    await repo.update_watchlist(wl_id, name="New Name")

    wl = await repo.get_watchlist_by_id(wl_id)
    assert wl is not None
    assert wl.name == "New Name"


@pytest.mark.asyncio
async def test_update_watchlist_description(repo: Repository) -> None:
    """update_watchlist changes the description."""
    wl_id = await repo.create_watchlist("Desc WL", description="Old desc")
    await repo.update_watchlist(wl_id, description="New desc")

    wl = await repo.get_watchlist_by_id(wl_id)
    assert wl is not None
    assert wl.description == "New desc"


# ---------------------------------------------------------------------------
# delete_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_watchlist_cascades_tickers(repo: Repository) -> None:
    """Deleting a watchlist also removes its tickers."""
    wl_id = await repo.create_watchlist("Doomed WL")
    await repo.add_ticker_to_watchlist(wl_id, "AAPL")
    await repo.add_ticker_to_watchlist(wl_id, "MSFT")

    await repo.delete_watchlist(wl_id)

    # Watchlist gone
    assert await repo.get_watchlist_by_id(wl_id) is None
    # Tickers also gone
    tickers = await repo.get_tickers_for_watchlist(wl_id)
    assert tickers == []


@pytest.mark.asyncio
async def test_delete_watchlist_not_found(repo: Repository) -> None:
    """Deleting a nonexistent watchlist does not raise (idempotent)."""
    # Should not raise any exception
    await repo.delete_watchlist(99999)
