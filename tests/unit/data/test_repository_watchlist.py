"""Tests for Repository — watchlist CRUD operations."""

import sqlite3
from datetime import datetime

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
async def test_create_watchlist_returns_watchlist(repo: Repository) -> None:
    """create_watchlist returns a Watchlist with DB-assigned ID."""
    wl = await repo.create_watchlist("My Picks")
    assert isinstance(wl, Watchlist)
    assert isinstance(wl.id, int)
    assert wl.id > 0
    assert wl.name == "My Picks"
    assert isinstance(wl.created_at, datetime)
    assert wl.created_at.tzinfo is not None


@pytest.mark.asyncio
async def test_create_watchlist_unique_name(repo: Repository) -> None:
    """Duplicate watchlist name raises IntegrityError."""
    await repo.create_watchlist("Favorites")
    with pytest.raises(sqlite3.IntegrityError):
        await repo.create_watchlist("Favorites")


@pytest.mark.asyncio
async def test_create_watchlist_different_names(repo: Repository) -> None:
    """Different names create distinct watchlists."""
    wl1 = await repo.create_watchlist("Alpha")
    wl2 = await repo.create_watchlist("Beta")
    assert wl1.id != wl2.id
    assert wl1.name == "Alpha"
    assert wl2.name == "Beta"


# ---------------------------------------------------------------------------
# get_watchlists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watchlists_empty(repo: Repository) -> None:
    """get_watchlists returns empty list when no watchlists exist."""
    result = await repo.get_watchlists()
    assert result == []


@pytest.mark.asyncio
async def test_get_watchlists_ordered_by_name(repo: Repository) -> None:
    """get_watchlists returns watchlists ordered by name ascending."""
    await repo.create_watchlist("Zebra")
    await repo.create_watchlist("Alpha")
    await repo.create_watchlist("Mango")

    result = await repo.get_watchlists()
    names = [wl.name for wl in result]
    assert names == ["Alpha", "Mango", "Zebra"]


@pytest.mark.asyncio
async def test_get_watchlists_returns_typed_models(repo: Repository) -> None:
    """get_watchlists returns list of Watchlist Pydantic models."""
    await repo.create_watchlist("Test")
    result = await repo.get_watchlists()
    assert len(result) == 1
    assert isinstance(result[0], Watchlist)


# ---------------------------------------------------------------------------
# get_watchlist_by_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watchlist_by_id_found(repo: Repository) -> None:
    """get_watchlist_by_id returns the watchlist when it exists."""
    wl = await repo.create_watchlist("Found Me")
    result = await repo.get_watchlist_by_id(wl.id)
    assert result is not None
    assert result.id == wl.id
    assert result.name == "Found Me"


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
    """get_watchlist_by_name returns the watchlist when name matches."""
    wl = await repo.create_watchlist("By Name")
    result = await repo.get_watchlist_by_name("By Name")
    assert result is not None
    assert result.id == wl.id


@pytest.mark.asyncio
async def test_get_watchlist_by_name_not_found(repo: Repository) -> None:
    """get_watchlist_by_name returns None for unknown name."""
    result = await repo.get_watchlist_by_name("Nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# delete_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_watchlist_removes_it(repo: Repository) -> None:
    """delete_watchlist removes the watchlist from the database."""
    wl = await repo.create_watchlist("Delete Me")
    await repo.delete_watchlist(wl.id)
    result = await repo.get_watchlist_by_id(wl.id)
    assert result is None


@pytest.mark.asyncio
async def test_delete_watchlist_removes_tickers(repo: Repository) -> None:
    """delete_watchlist also removes associated tickers."""
    wl = await repo.create_watchlist("With Tickers")
    await repo.add_ticker_to_watchlist(wl.id, "AAPL")
    await repo.add_ticker_to_watchlist(wl.id, "MSFT")

    await repo.delete_watchlist(wl.id)

    tickers = await repo.get_tickers_for_watchlist(wl.id)
    assert tickers == []


@pytest.mark.asyncio
async def test_delete_watchlist_nonexistent_is_noop(repo: Repository) -> None:
    """delete_watchlist silently succeeds for nonexistent ID."""
    await repo.delete_watchlist(999)  # Should not raise


# ---------------------------------------------------------------------------
# add_ticker_to_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_ticker_to_watchlist(repo: Repository) -> None:
    """add_ticker_to_watchlist adds a ticker."""
    wl = await repo.create_watchlist("Watchlist")
    await repo.add_ticker_to_watchlist(wl.id, "AAPL")

    tickers = await repo.get_tickers_for_watchlist(wl.id)
    assert len(tickers) == 1
    assert tickers[0].ticker == "AAPL"


@pytest.mark.asyncio
async def test_add_ticker_uppercase(repo: Repository) -> None:
    """add_ticker_to_watchlist uppercases the ticker."""
    wl = await repo.create_watchlist("Upper")
    await repo.add_ticker_to_watchlist(wl.id, "aapl")

    tickers = await repo.get_tickers_for_watchlist(wl.id)
    assert len(tickers) == 1
    assert tickers[0].ticker == "AAPL"


@pytest.mark.asyncio
async def test_add_duplicate_ticker_raises(repo: Repository) -> None:
    """Adding the same ticker twice raises IntegrityError."""
    wl = await repo.create_watchlist("Dups")
    await repo.add_ticker_to_watchlist(wl.id, "AAPL")
    with pytest.raises(sqlite3.IntegrityError):
        await repo.add_ticker_to_watchlist(wl.id, "AAPL")


@pytest.mark.asyncio
async def test_add_multiple_tickers(repo: Repository) -> None:
    """Multiple distinct tickers can be added."""
    wl = await repo.create_watchlist("Multi")
    await repo.add_ticker_to_watchlist(wl.id, "AAPL")
    await repo.add_ticker_to_watchlist(wl.id, "MSFT")
    await repo.add_ticker_to_watchlist(wl.id, "GOOGL")

    tickers = await repo.get_tickers_for_watchlist(wl.id)
    assert len(tickers) == 3
    ticker_names = {t.ticker for t in tickers}
    assert ticker_names == {"AAPL", "MSFT", "GOOGL"}


@pytest.mark.asyncio
async def test_same_ticker_different_watchlists(repo: Repository) -> None:
    """Same ticker can belong to different watchlists."""
    wl1 = await repo.create_watchlist("WL1")
    wl2 = await repo.create_watchlist("WL2")
    await repo.add_ticker_to_watchlist(wl1.id, "AAPL")
    await repo.add_ticker_to_watchlist(wl2.id, "AAPL")

    t1 = await repo.get_tickers_for_watchlist(wl1.id)
    t2 = await repo.get_tickers_for_watchlist(wl2.id)
    assert len(t1) == 1
    assert len(t2) == 1
    assert t1[0].ticker == "AAPL"
    assert t2[0].ticker == "AAPL"


# ---------------------------------------------------------------------------
# remove_ticker_from_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_ticker_from_watchlist(repo: Repository) -> None:
    """remove_ticker_from_watchlist removes the ticker."""
    wl = await repo.create_watchlist("Remove")
    await repo.add_ticker_to_watchlist(wl.id, "AAPL")
    await repo.add_ticker_to_watchlist(wl.id, "MSFT")

    await repo.remove_ticker_from_watchlist(wl.id, "AAPL")

    tickers = await repo.get_tickers_for_watchlist(wl.id)
    assert len(tickers) == 1
    assert tickers[0].ticker == "MSFT"


@pytest.mark.asyncio
async def test_remove_nonexistent_ticker_is_noop(repo: Repository) -> None:
    """Removing a ticker not in the watchlist is a no-op."""
    wl = await repo.create_watchlist("Noop")
    await repo.remove_ticker_from_watchlist(wl.id, "AAPL")  # Should not raise


@pytest.mark.asyncio
async def test_remove_ticker_uppercase(repo: Repository) -> None:
    """remove_ticker_from_watchlist uppercases the ticker for matching."""
    wl = await repo.create_watchlist("CaseSensitive")
    await repo.add_ticker_to_watchlist(wl.id, "AAPL")
    await repo.remove_ticker_from_watchlist(wl.id, "aapl")

    tickers = await repo.get_tickers_for_watchlist(wl.id)
    assert tickers == []


# ---------------------------------------------------------------------------
# get_tickers_for_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_tickers_empty_watchlist(repo: Repository) -> None:
    """get_tickers_for_watchlist returns empty list for empty watchlist."""
    wl = await repo.create_watchlist("Empty")
    result = await repo.get_tickers_for_watchlist(wl.id)
    assert result == []


@pytest.mark.asyncio
async def test_get_tickers_nonexistent_watchlist(repo: Repository) -> None:
    """get_tickers_for_watchlist returns empty list for nonexistent watchlist."""
    result = await repo.get_tickers_for_watchlist(999)
    assert result == []


@pytest.mark.asyncio
async def test_get_tickers_ordered_by_ticker(repo: Repository) -> None:
    """get_tickers_for_watchlist returns tickers ordered alphabetically."""
    wl = await repo.create_watchlist("Ordered")
    await repo.add_ticker_to_watchlist(wl.id, "MSFT")
    await repo.add_ticker_to_watchlist(wl.id, "AAPL")
    await repo.add_ticker_to_watchlist(wl.id, "GOOGL")

    tickers = await repo.get_tickers_for_watchlist(wl.id)
    names = [t.ticker for t in tickers]
    assert names == ["AAPL", "GOOGL", "MSFT"]


@pytest.mark.asyncio
async def test_get_tickers_returns_typed_models(repo: Repository) -> None:
    """get_tickers_for_watchlist returns WatchlistTicker Pydantic models."""
    wl = await repo.create_watchlist("Typed")
    await repo.add_ticker_to_watchlist(wl.id, "AAPL")

    tickers = await repo.get_tickers_for_watchlist(wl.id)
    assert len(tickers) == 1
    t = tickers[0]
    assert isinstance(t, WatchlistTicker)
    assert isinstance(t.id, int)
    assert isinstance(t.watchlist_id, int)
    assert isinstance(t.ticker, str)
    assert isinstance(t.added_at, datetime)
    assert t.added_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Watchlist model round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchlist_created_at_utc(repo: Repository) -> None:
    """Watchlist.created_at is UTC-aware."""
    wl = await repo.create_watchlist("UTC Test")
    assert wl.created_at.tzinfo is not None
    from datetime import timedelta

    assert wl.created_at.utcoffset() == timedelta(0)


@pytest.mark.asyncio
async def test_watchlist_ticker_added_at_utc(repo: Repository) -> None:
    """WatchlistTicker.added_at is UTC-aware."""
    wl = await repo.create_watchlist("UTC Ticker Test")
    await repo.add_ticker_to_watchlist(wl.id, "AAPL")

    tickers = await repo.get_tickers_for_watchlist(wl.id)
    assert len(tickers) == 1
    from datetime import timedelta

    assert tickers[0].added_at.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# Isolation: tickers from watchlist A don't appear in watchlist B
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tickers_isolated_per_watchlist(repo: Repository) -> None:
    """Tickers from watchlist A don't appear when querying watchlist B."""
    wl_a = await repo.create_watchlist("WL-A")
    wl_b = await repo.create_watchlist("WL-B")

    await repo.add_ticker_to_watchlist(wl_a.id, "AAPL")
    await repo.add_ticker_to_watchlist(wl_b.id, "MSFT")

    tickers_a = await repo.get_tickers_for_watchlist(wl_a.id)
    tickers_b = await repo.get_tickers_for_watchlist(wl_b.id)

    assert len(tickers_a) == 1
    assert tickers_a[0].ticker == "AAPL"
    assert len(tickers_b) == 1
    assert tickers_b[0].ticker == "MSFT"
