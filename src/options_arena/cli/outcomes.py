"""CLI outcomes subcommand group: collect and summarize contract outcomes.

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``. Services are created and closed within the command scope.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from options_arena.cli.app import app
from options_arena.data import Database, Repository
from options_arena.models.config import AppSettings
from options_arena.services.cache import ServiceCache
from options_arena.services.market_data import MarketDataService
from options_arena.services.outcome_collector import OutcomeCollector
from options_arena.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)
console = Console()
err_console = Console(stderr=True)

# Resolve data directory from project root (src/options_arena/cli/outcomes.py -> parents[3])
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"

outcomes_app = typer.Typer(
    help="Outcome tracking and collection.",
    no_args_is_help=True,
)
app.add_typer(outcomes_app, name="outcomes")


@outcomes_app.command("collect")
def outcomes_collect(
    holding_days: int | None = typer.Option(  # noqa: B008
        None, "--holding-days", help="Specific holding period in days"
    ),
) -> None:
    """Collect outcomes for recommended contracts."""
    asyncio.run(_outcomes_collect_async(holding_days))


async def _outcomes_collect_async(holding_days: int | None) -> None:
    """Collect outcomes with full service lifecycle management."""
    settings = AppSettings()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )

    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    market_data: MarketDataService | None = None

    try:
        await db.connect()
        repo = Repository(db)

        market_data = MarketDataService(settings.service, cache, limiter)
        collector = OutcomeCollector(settings.analytics, repo, market_data)

        if holding_days is not None:
            err_console.print(f"[cyan]Collecting outcomes for {holding_days}-day period...[/cyan]")
        else:
            periods_str = ", ".join(str(p) for p in settings.analytics.holding_periods)
            err_console.print(f"[cyan]Collecting outcomes for periods: {periods_str}...[/cyan]")

        outcomes = await collector.collect_outcomes(holding_days)

        if not outcomes:
            console.print("[yellow]No new outcomes to collect.[/yellow]")
            return

        # Display summary
        table = Table(title="Collected Outcomes")
        table.add_column("Ticker", style="bold white", no_wrap=True)
        table.add_column("Period", justify="right", style="cyan")
        table.add_column("Method", justify="center")
        table.add_column("Stock Return", justify="right")
        table.add_column("Contract Return", justify="right")
        table.add_column("Winner", justify="center")

        for outcome in outcomes:
            # Resolve ticker from contract_id
            ticker = "?"
            try:
                conn = repo._db.conn  # noqa: SLF001
                async with conn.execute(
                    "SELECT ticker FROM recommended_contracts WHERE id = ?",
                    (outcome.recommended_contract_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                if row:
                    ticker = str(row["ticker"])
            except Exception:
                pass

            stock_ret = (
                f"{outcome.stock_return_pct:+.1f}%"
                if outcome.stock_return_pct is not None
                else "--"
            )
            contract_ret = (
                f"{outcome.contract_return_pct:+.1f}%"
                if outcome.contract_return_pct is not None
                else "--"
            )
            winner = (
                "[green]YES[/green]"
                if outcome.is_winner is True
                else "[red]NO[/red]"
                if outcome.is_winner is False
                else "--"
            )
            table.add_row(
                ticker,
                str(outcome.holding_days or "--"),
                outcome.collection_method.value,
                stock_ret,
                contract_ret,
                winner,
            )

        console.print(table)
        console.print(f"\n[dim]{len(outcomes)} outcomes collected.[/dim]")

    except Exception as exc:
        logger.exception("Outcome collection failed")
        err_console.print(
            "[red]Collection failed. Check logs/options_arena.log for details.[/red]"
        )
        raise typer.Exit(code=1) from exc
    finally:
        if market_data is not None:
            await market_data.close()
        await cache.close()
        await db.close()


@outcomes_app.command("summary")
def outcomes_summary(
    lookback_days: int = typer.Option(30, "--lookback-days", help="Number of days to look back"),
) -> None:
    """Show performance summary."""
    asyncio.run(_outcomes_summary_async(lookback_days))


async def _outcomes_summary_async(lookback_days: int) -> None:
    """Get and display performance summary with full service lifecycle management."""
    settings = AppSettings()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )

    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    market_data: MarketDataService | None = None

    try:
        await db.connect()
        repo = Repository(db)

        market_data = MarketDataService(settings.service, cache, limiter)
        collector = OutcomeCollector(settings.analytics, repo, market_data)

        summary = await collector.get_summary(lookback_days)

        # Display summary
        console.print(f"\n[bold]Performance Summary ({lookback_days}-day lookback)[/bold]\n")

        table = Table(show_header=False, padding=(0, 2))
        table.add_column("Metric", style="bold white")
        table.add_column("Value", justify="right", style="cyan")

        table.add_row("Total contracts", str(summary.total_contracts))
        table.add_row("With outcomes", str(summary.total_with_outcomes))
        table.add_row(
            "Overall win rate",
            f"{summary.overall_win_rate * 100:.1f}%"
            if summary.overall_win_rate is not None
            else "--",
        )
        table.add_row(
            "Avg stock return",
            f"{summary.avg_stock_return_pct:+.2f}%"
            if summary.avg_stock_return_pct is not None
            else "--",
        )
        table.add_row(
            "Avg contract return",
            f"{summary.avg_contract_return_pct:+.2f}%"
            if summary.avg_contract_return_pct is not None
            else "--",
        )
        table.add_row(
            "Best direction",
            summary.best_direction.value.upper() if summary.best_direction is not None else "--",
        )
        table.add_row(
            "Best holding period",
            f"T+{summary.best_holding_days}" if summary.best_holding_days is not None else "--",
        )

        console.print(table)

    except Exception as exc:
        logger.exception("Summary generation failed")
        err_console.print("[red]Summary failed. Check logs/options_arena.log for details.[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        if market_data is not None:
            await market_data.close()
        await cache.close()
        await db.close()
