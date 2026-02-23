"""CLI commands: scan, health, universe (refresh/list/stats).

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``. Services are created and closed within the command scope.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from options_arena.cli.app import app
from options_arena.cli.progress import RichProgressCallback, setup_sigint_handler
from options_arena.cli.rendering import DISCLAIMER, render_health_table, render_scan_table
from options_arena.data import Database, Repository
from options_arena.models.config import AppSettings
from options_arena.models.enums import ScanPreset
from options_arena.scan import CancellationToken, ScanPipeline, ScanResult
from options_arena.services.cache import ServiceCache
from options_arena.services.fred import FredService
from options_arena.services.health import HealthService
from options_arena.services.market_data import MarketDataService
from options_arena.services.options_data import OptionsDataService
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import UniverseService

logger = logging.getLogger(__name__)
console = Console()
err_console = Console(stderr=True)

# Resolve data directory from project root (src/options_arena/cli/commands.py → parents[3])
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------


@app.command()
def scan(
    preset: ScanPreset = typer.Option(  # noqa: B008
        ScanPreset.SP500, "--preset", "-p", help="Scan preset: full, sp500, etfs"
    ),
    top_n: int = typer.Option(50, "--top-n", "-n", help="Top N tickers for options analysis"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum composite score"),
    sectors: str | None = typer.Option(None, "--sectors", help="Comma-separated GICS sectors"),
) -> None:
    """Run the full scan pipeline: universe -> scoring -> options -> persist."""
    asyncio.run(_scan_async(preset, top_n, min_score, sectors))


async def _scan_async(
    preset: ScanPreset,
    top_n: int,
    min_score: float,
    sectors: str | None,
) -> None:
    """Run the scan pipeline with full service lifecycle management."""
    if sectors is not None:
        logger.warning(
            "--sectors filtering is not yet implemented; ignoring --sectors=%s", sectors
        )

    start_time = time.monotonic()

    # Config with CLI overrides
    settings = AppSettings()
    settings.scan.top_n = top_n
    settings.scan.min_score = min_score

    # Infrastructure (lightweight constructors — no I/O)
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    db = Database(_DATA_DIR / "options_arena.db")

    # Track services for cleanup — None until successfully constructed
    market_data: MarketDataService | None = None
    options_data: OptionsDataService | None = None
    fred: FredService | None = None
    universe_svc: UniverseService | None = None

    try:
        await db.connect()
        repo = Repository(db)

        # Services (DI pattern)
        market_data = MarketDataService(settings.service, cache, limiter)
        options_data = OptionsDataService(settings.service, settings.pricing, cache, limiter)
        fred = FredService(settings.service, settings.pricing, cache)
        universe_svc = UniverseService(settings.service, cache, limiter)

        # Pipeline
        pipeline = ScanPipeline(settings, market_data, options_data, fred, universe_svc, repo)

        # Cancellation token + SIGINT handler
        token = CancellationToken()
        setup_sigint_handler(token, err_console)

        # Progress bar on stderr (preserves piped stdout)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=err_console,
            transient=False,
        ) as progress:
            callback = RichProgressCallback(progress)
            result = await pipeline.run(preset, token, callback)

        # Render results
        elapsed = time.monotonic() - start_time
        _render_scan_results(result, elapsed)

    except Exception as exc:
        logger.exception("Scan pipeline failed")
        err_console.print("[red]Scan failed. Check logs/options_arena.log for details.[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        # Restore default SIGINT handler
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        # Close all services that were successfully constructed
        if market_data is not None:
            await market_data.close()
        if options_data is not None:
            await options_data.close()
        if fred is not None:
            await fred.close()
        if universe_svc is not None:
            await universe_svc.close()
        await cache.close()
        await db.close()


def _render_scan_results(result: ScanResult, elapsed: float) -> None:
    """Render scan results: table + summary + disclaimer."""
    if result.cancelled:
        err_console.print(
            f"[yellow]Scan cancelled after {result.phases_completed}/4 phases.[/yellow]"
        )

    if result.scores:
        table = render_scan_table(result)
        console.print(table)

    # Summary line
    rec_count = sum(len(contracts) for contracts in result.recommendations.values())
    console.print(
        f"\n{result.scan_run.tickers_scanned} tickers scanned, "
        f"{result.scan_run.tickers_scored} scored, "
        f"{rec_count} recommendations in {elapsed:.1f}s"
    )

    # Regulatory disclaimer (ALWAYS printed)
    console.print(f"\n{DISCLAIMER}")


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
