"""Smoke tests for the watchlist CLI subcommand group."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from options_arena.cli import app

runner = CliRunner()


def test_watchlist_no_args_shows_help() -> None:
    """Running 'watchlist' with no args shows help text (exit code 0 or 2)."""
    result = runner.invoke(app, ["watchlist"])
    # Typer with no_args_is_help=True may exit 0 or 2 depending on version
    assert result.exit_code in (0, 2)
    assert "Manage user-defined watchlists" in result.output


def test_watchlist_list_empty() -> None:
    """'watchlist list' shows message when no watchlists exist."""
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()

    mock_repo = MagicMock()
    mock_repo.get_watchlists = AsyncMock(return_value=[])

    with (
        patch("options_arena.cli.watchlist.Database", return_value=mock_db),
        patch("options_arena.cli.watchlist.Repository", return_value=mock_repo),
    ):
        result = runner.invoke(app, ["watchlist", "list"])
    assert result.exit_code == 0
    assert "No watchlists found" in result.output


def test_watchlist_create_success() -> None:
    """'watchlist create' shows confirmation on success."""
    from datetime import UTC, datetime

    from options_arena.models import Watchlist

    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()

    mock_repo = MagicMock()
    mock_repo.create_watchlist = AsyncMock(
        return_value=Watchlist(id=1, name="Tech", created_at=datetime(2026, 2, 27, tzinfo=UTC))
    )

    with (
        patch("options_arena.cli.watchlist.Database", return_value=mock_db),
        patch("options_arena.cli.watchlist.Repository", return_value=mock_repo),
    ):
        result = runner.invoke(app, ["watchlist", "create", "Tech"])
    assert result.exit_code == 0
    assert "Created watchlist" in result.output
    assert "Tech" in result.output


def test_watchlist_create_duplicate() -> None:
    """'watchlist create' with duplicate name shows error."""
    import sqlite3

    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()

    mock_repo = MagicMock()
    mock_repo.create_watchlist = AsyncMock(side_effect=sqlite3.IntegrityError())

    with (
        patch("options_arena.cli.watchlist.Database", return_value=mock_db),
        patch("options_arena.cli.watchlist.Repository", return_value=mock_repo),
    ):
        result = runner.invoke(app, ["watchlist", "create", "Existing"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_watchlist_delete_not_found() -> None:
    """'watchlist delete' shows error when not found."""
    mock_db = MagicMock()
    mock_db.connect = AsyncMock()
    mock_db.close = AsyncMock()

    mock_repo = MagicMock()
    mock_repo.get_watchlist_by_id = AsyncMock(return_value=None)
    mock_repo.get_watchlist_by_name = AsyncMock(return_value=None)

    with (
        patch("options_arena.cli.watchlist.Database", return_value=mock_db),
        patch("options_arena.cli.watchlist.Repository", return_value=mock_repo),
    ):
        result = runner.invoke(app, ["watchlist", "delete", "nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.output
