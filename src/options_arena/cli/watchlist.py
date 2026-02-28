"""CLI watchlist subcommands: list, create, delete, add, remove.

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``.  Uses Rich Tables for output formatting.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from options_arena.cli.app import app
from options_arena.data import Database, Repository
from options_arena.models import Watchlist
from options_arena.models.config import AppSettings

logger = logging.getLogger(__name__)
console = Console()
err_console = Console(stderr=True)

# Resolve data directory from project root (src/options_arena/cli/watchlist.py -> parents[3])
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"

watchlist_app = typer.Typer(
    help="Manage user-defined watchlists.",
    no_args_is_help=True,
)
app.add_typer(watchlist_app, name="watchlist")


async def _get_db_and_repo() -> tuple[Database, Repository]:
    """Create and connect a Database + Repository for watchlist operations."""
    settings = AppSettings()
    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    await db.connect()
    return db, Repository(db)


@watchlist_app.command("list")
def list_watchlists() -> None:
    """Show all watchlists."""
    asyncio.run(_list_async())


async def _list_async() -> None:
    """Fetch and display all watchlists."""
    db, repo = await _get_db_and_repo()
    try:
        watchlists = await repo.get_watchlists()
        if not watchlists:
            console.print(
                "[yellow]No watchlists found. "
                "Create one with: options-arena watchlist create NAME[/yellow]"
            )
            return

        table = Table(title="Watchlists")
        table.add_column("ID", justify="right", style="dim")
        table.add_column("Name", style="bold white")
        table.add_column("Tickers", justify="right", style="cyan")
        table.add_column("Created", style="dim")

        for wl in watchlists:
            tickers = await repo.get_tickers_for_watchlist(wl.id)
            table.add_row(
                str(wl.id),
                wl.name,
                str(len(tickers)),
                wl.created_at.strftime("%Y-%m-%d %H:%M"),
            )

        console.print(table)
    finally:
        await db.close()


@watchlist_app.command()
def create(
    name: str = typer.Argument(help="Watchlist name"),
) -> None:
    """Create a new watchlist."""
    asyncio.run(_create_async(name))


async def _create_async(name: str) -> None:
    """Create a watchlist and display confirmation."""
    db, repo = await _get_db_and_repo()
    try:
        try:
            watchlist = await repo.create_watchlist(name)
            console.print(
                f"[green]Created watchlist '{watchlist.name}' (id={watchlist.id})[/green]"
            )
        except sqlite3.IntegrityError:
            err_console.print(f"[red]Watchlist '{name}' already exists.[/red]")
            raise typer.Exit(code=1)  # noqa: B904
    finally:
        await db.close()


@watchlist_app.command()
def delete(
    name_or_id: str = typer.Argument(help="Watchlist name or numeric ID"),
) -> None:
    """Delete a watchlist by name or ID."""
    asyncio.run(_delete_async(name_or_id))


async def _delete_async(name_or_id: str) -> None:
    """Delete a watchlist by name or numeric ID."""
    db, repo = await _get_db_and_repo()
    try:
        watchlist = await _resolve_watchlist(repo, name_or_id)
        if watchlist is None:
            err_console.print(f"[red]Watchlist '{name_or_id}' not found.[/red]")
            raise typer.Exit(code=1)
        await repo.delete_watchlist(watchlist.id)
        console.print(f"[green]Deleted watchlist '{watchlist.name}' (id={watchlist.id})[/green]")
    finally:
        await db.close()


@watchlist_app.command()
def add(
    ticker: str = typer.Argument(help="Ticker symbol to add"),
    name: str = typer.Option(..., "--name", "-n", help="Watchlist name or ID"),
) -> None:
    """Add a ticker to a watchlist."""
    asyncio.run(_add_async(ticker.upper(), name))


async def _add_async(ticker: str, name_or_id: str) -> None:
    """Add a ticker to the specified watchlist."""
    db, repo = await _get_db_and_repo()
    try:
        watchlist = await _resolve_watchlist(repo, name_or_id)
        if watchlist is None:
            err_console.print(f"[red]Watchlist '{name_or_id}' not found.[/red]")
            raise typer.Exit(code=1)
        try:
            await repo.add_ticker_to_watchlist(watchlist.id, ticker)
            console.print(f"[green]Added {ticker} to '{watchlist.name}'[/green]")
        except sqlite3.IntegrityError:
            err_console.print(f"[red]{ticker} is already in '{watchlist.name}'.[/red]")
            raise typer.Exit(code=1)  # noqa: B904
    finally:
        await db.close()


@watchlist_app.command()
def remove(
    ticker: str = typer.Argument(help="Ticker symbol to remove"),
    name: str = typer.Option(..., "--name", "-n", help="Watchlist name or ID"),
) -> None:
    """Remove a ticker from a watchlist."""
    asyncio.run(_remove_async(ticker.upper(), name))


async def _remove_async(ticker: str, name_or_id: str) -> None:
    """Remove a ticker from the specified watchlist."""
    db, repo = await _get_db_and_repo()
    try:
        watchlist = await _resolve_watchlist(repo, name_or_id)
        if watchlist is None:
            err_console.print(f"[red]Watchlist '{name_or_id}' not found.[/red]")
            raise typer.Exit(code=1)
        await repo.remove_ticker_from_watchlist(watchlist.id, ticker)
        console.print(f"[green]Removed {ticker} from '{watchlist.name}'[/green]")
    finally:
        await db.close()


async def _resolve_watchlist(repo: Repository, name_or_id: str) -> Watchlist | None:
    """Resolve a watchlist by numeric ID or by name."""
    # Try as numeric ID first
    try:
        wl_id = int(name_or_id)
        return await repo.get_watchlist_by_id(wl_id)
    except ValueError:
        pass
    # Fall back to name lookup
    return await repo.get_watchlist_by_name(name_or_id)
