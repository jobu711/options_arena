"""Tests for watchlist CLI subcommands.

All tests mock at the Database and Repository level to avoid real I/O.
Typer CliRunner captures output and exit codes for assertion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from options_arena.cli.app import app
from options_arena.models import Watchlist, WatchlistTicker

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_watchlist(
    wl_id: int = 1,
    name: str = "Test WL",
    description: str | None = None,
) -> Watchlist:
    return Watchlist(
        id=wl_id,
        name=name,
        description=description,
        created_at=datetime(2026, 2, 27, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 2, 27, 10, 0, 0, tzinfo=UTC),
    )


def _make_ticker(ticker: str = "AAPL", wl_id: int = 1) -> WatchlistTicker:
    return WatchlistTicker(
        id=1,
        watchlist_id=wl_id,
        ticker=ticker,
        added_at=datetime(2026, 2, 27, 10, 0, 0, tzinfo=UTC),
    )


def _setup_mocks(
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
) -> tuple[MagicMock, MagicMock]:
    """Set up Database and Repository mock instances and return them."""
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = MagicMock()
    mock_repo_cls.return_value = mock_repo

    return mock_db, mock_repo


# ---------------------------------------------------------------------------
# watchlist wl-create
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
def test_watchlist_create(mock_db_cls: MagicMock, mock_repo_cls: MagicMock) -> None:
    """watchlist wl-create creates a new watchlist."""
    _mock_db, mock_repo = _setup_mocks(mock_db_cls, mock_repo_cls)
    mock_repo.create_watchlist = AsyncMock(return_value=1)

    result = runner.invoke(app, ["watchlist", "wl-create", "My Picks"])
    assert result.exit_code == 0
    assert "Created" in result.output


@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
def test_watchlist_create_duplicate(
    mock_db_cls: MagicMock, mock_repo_cls: MagicMock
) -> None:
    """watchlist wl-create with duplicate name exits with code 1."""
    _mock_db, mock_repo = _setup_mocks(mock_db_cls, mock_repo_cls)
    mock_repo.create_watchlist = AsyncMock(
        side_effect=Exception("UNIQUE constraint failed")
    )

    result = runner.invoke(app, ["watchlist", "wl-create", "Existing"])
    assert result.exit_code == 1
    assert "already exists" in result.output


# ---------------------------------------------------------------------------
# watchlist list
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
def test_watchlist_list_empty(mock_db_cls: MagicMock, mock_repo_cls: MagicMock) -> None:
    """watchlist list with no watchlists shows 'No watchlists'."""
    _mock_db, mock_repo = _setup_mocks(mock_db_cls, mock_repo_cls)
    mock_repo.get_all_watchlists = AsyncMock(return_value=[])

    result = runner.invoke(app, ["watchlist", "list"])
    assert result.exit_code == 0
    assert "No watchlists" in result.output


@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
def test_watchlist_list_with_data(
    mock_db_cls: MagicMock, mock_repo_cls: MagicMock
) -> None:
    """watchlist list with data renders a table with watchlist names."""
    _mock_db, mock_repo = _setup_mocks(mock_db_cls, mock_repo_cls)
    mock_repo.get_all_watchlists = AsyncMock(
        return_value=[_make_watchlist(1, "Tech"), _make_watchlist(2, "Value")]
    )

    result = runner.invoke(app, ["watchlist", "list"])
    assert result.exit_code == 0
    assert "Tech" in result.output
    assert "Value" in result.output


# ---------------------------------------------------------------------------
# watchlist wl-show
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
def test_watchlist_show(mock_db_cls: MagicMock, mock_repo_cls: MagicMock) -> None:
    """watchlist wl-show displays watchlist with tickers."""
    _mock_db, mock_repo = _setup_mocks(mock_db_cls, mock_repo_cls)
    mock_repo.get_watchlist_by_name = AsyncMock(return_value=_make_watchlist(1, "My WL"))
    mock_repo.get_tickers_for_watchlist = AsyncMock(
        return_value=[_make_ticker("AAPL"), _make_ticker("MSFT")]
    )

    result = runner.invoke(app, ["watchlist", "wl-show", "My WL"])
    assert result.exit_code == 0
    assert "My WL" in result.output
    assert "AAPL" in result.output
    assert "MSFT" in result.output


@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
def test_watchlist_show_not_found(
    mock_db_cls: MagicMock, mock_repo_cls: MagicMock
) -> None:
    """watchlist wl-show with unknown name exits with code 1."""
    _mock_db, mock_repo = _setup_mocks(mock_db_cls, mock_repo_cls)
    mock_repo.get_watchlist_by_name = AsyncMock(return_value=None)

    result = runner.invoke(app, ["watchlist", "wl-show", "Nope"])
    assert result.exit_code == 1
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# watchlist wl-add
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
def test_watchlist_add(mock_db_cls: MagicMock, mock_repo_cls: MagicMock) -> None:
    """watchlist wl-add adds tickers to watchlist."""
    _mock_db, mock_repo = _setup_mocks(mock_db_cls, mock_repo_cls)
    mock_repo.get_watchlist_by_name = AsyncMock(return_value=_make_watchlist(1, "Test"))
    mock_repo.add_ticker_to_watchlist = AsyncMock(return_value=None)

    result = runner.invoke(app, ["watchlist", "wl-add", "Test", "AAPL", "MSFT"])
    assert result.exit_code == 0
    assert "Added" in result.output


# ---------------------------------------------------------------------------
# watchlist wl-delete
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
def test_watchlist_delete(mock_db_cls: MagicMock, mock_repo_cls: MagicMock) -> None:
    """watchlist wl-delete removes the watchlist."""
    _mock_db, mock_repo = _setup_mocks(mock_db_cls, mock_repo_cls)
    mock_repo.get_watchlist_by_name = AsyncMock(return_value=_make_watchlist(1, "Doomed"))
    mock_repo.delete_watchlist = AsyncMock(return_value=None)

    result = runner.invoke(app, ["watchlist", "wl-delete", "Doomed"])
    assert result.exit_code == 0
    assert "Deleted" in result.output
