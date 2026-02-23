"""CLI commands: health, universe (refresh/list/stats).

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``. Services are created and closed within the command scope.
"""

from __future__ import annotations

import asyncio
import logging

import typer
from rich.console import Console

from options_arena.cli.app import app
from options_arena.cli.rendering import render_health_table
from options_arena.models.config import AppSettings
from options_arena.models.enums import ScanPreset
from options_arena.services.cache import ServiceCache
from options_arena.services.health import HealthService
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import UniverseService

logger = logging.getLogger(__name__)
console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# health command
# ---------------------------------------------------------------------------


@app.command()
def health() -> None:
    """Check external service availability."""
    asyncio.run(_health_async())


async def _health_async() -> None:
    """Run all health checks and render results."""
    settings = AppSettings()
    svc = HealthService(settings.service)
    try:
        statuses = await svc.check_all()
        table = render_health_table(statuses)
        console.print(table)
        all_up = all(s.available for s in statuses)
        if not all_up:
            raise typer.Exit(code=1)
    finally:
        await svc.close()


# ---------------------------------------------------------------------------
# universe subcommands
# ---------------------------------------------------------------------------

universe_app = typer.Typer(
    help="Manage the optionable ticker universe.",
    no_args_is_help=True,
)
app.add_typer(universe_app, name="universe")


@universe_app.command()
def refresh() -> None:
    """Force re-fetch CBOE universe and S&P 500 constituents."""
    asyncio.run(_refresh_async())


async def _refresh_async() -> None:
    """Fetch universe data from all sources and report counts."""
    settings = AppSettings()
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    svc = UniverseService(settings.service, cache, limiter)
    try:
        tickers = await svc.fetch_optionable_tickers()
        sp500 = await svc.fetch_sp500_constituents()
        console.print(
            f"[green]Universe refreshed:[/green] {len(tickers)} optionable tickers, "
            f"{len(sp500)} S&P 500 constituents"
        )
    finally:
        await svc.close()
        await cache.close()


@universe_app.command("list")
def list_tickers(
    sector: str | None = typer.Option(None, "--sector", help="Filter by GICS sector"),
    preset: ScanPreset = typer.Option(  # noqa: B008
        ScanPreset.SP500, "--preset", help="Scan preset"
    ),
) -> None:
    """Display tickers matching filters."""
    asyncio.run(_list_async(sector, preset))


async def _list_async(sector: str | None, preset: ScanPreset) -> None:
    """List tickers for the given preset, optionally filtered by sector."""
    settings = AppSettings()
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    svc = UniverseService(settings.service, cache, limiter)
    try:
        if preset == ScanPreset.SP500:
            constituents = await svc.fetch_sp500_constituents()
            tickers_with_sector = [(c.ticker, c.sector) for c in constituents]
            if sector:
                sectors = [s.strip() for s in sector.split(",")]
                tickers_with_sector = [(t, s) for t, s in tickers_with_sector if s in sectors]
            console.print(
                f"[bold]{len(tickers_with_sector)} tickers[/bold] (preset={preset.value})"
            )
            for ticker, sec in sorted(tickers_with_sector):
                console.print(f"  {ticker:<8} {sec}")
        else:
            tickers = await svc.fetch_optionable_tickers()
            console.print(
                f"[bold]{len(tickers)} optionable tickers[/bold] (preset={preset.value})"
            )
            for i in range(0, len(tickers), 8):
                row = tickers[i : i + 8]
                console.print("  " + "  ".join(f"{t:<8}" for t in row))
    finally:
        await svc.close()
        await cache.close()


@universe_app.command()
def stats() -> None:
    """Show universe size, sector breakdown, S&P 500 count."""
    asyncio.run(_stats_async())


async def _stats_async() -> None:
    """Compute and display universe statistics with sector breakdown."""
    settings = AppSettings()
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    svc = UniverseService(settings.service, cache, limiter)
    try:
        tickers = await svc.fetch_optionable_tickers()
        sp500 = await svc.fetch_sp500_constituents()

        console.print("[bold]Universe Statistics[/bold]")
        console.print(f"  Optionable tickers: {len(tickers)}")
        console.print(f"  S&P 500 constituents: {len(sp500)}")

        # Sector breakdown
        sectors: dict[str, int] = {}
        for c in sp500:
            sectors[c.sector] = sectors.get(c.sector, 0) + 1

        if sectors:
            console.print("\n[bold]S&P 500 Sector Breakdown[/bold]")
            for sec, count in sorted(sectors.items(), key=lambda x: -x[1]):
                console.print(f"  {sec:<35} {count:>3}")
    finally:
        await svc.close()
        await cache.close()
