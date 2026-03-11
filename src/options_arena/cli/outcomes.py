"""CLI outcomes subcommand group: collect and summarize contract outcomes.

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``. Services are created and closed within the command scope.
"""

from __future__ import annotations

import asyncio
import logging
import math
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from options_arena.agents import auto_tune_weights
from options_arena.cli.app import app
from options_arena.data import Database, Repository
from options_arena.models.config import AppSettings
from options_arena.services.cache import ServiceCache
from options_arena.services.market_data import MarketDataService
from options_arena.services.options_data import OptionsDataService
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
    options_data: OptionsDataService | None = None

    try:
        await db.connect()
        repo = Repository(db)

        market_data = MarketDataService(settings.service, cache, limiter)
        opts_filters = settings.scan.filters.options
        options_data = OptionsDataService(settings.service, opts_filters, cache, limiter)
        collector = OutcomeCollector(settings.analytics, repo, market_data, options_data)

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
        if options_data is not None:
            await options_data.close()
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


# ---------------------------------------------------------------------------
# Agent calibration commands
# ---------------------------------------------------------------------------


@outcomes_app.command("agent-accuracy")
def agent_accuracy_cmd(
    window: int | None = typer.Option(  # noqa: B008
        None, "--window", help="Rolling window in days"
    ),
) -> None:
    """Show per-agent direction accuracy and Brier scores."""
    asyncio.run(_agent_accuracy_async(window))


async def _agent_accuracy_async(window: int | None) -> None:
    """Display agent accuracy table."""
    settings = AppSettings()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    try:
        await db.connect()
        repo = Repository(db)
        results = await repo.get_agent_accuracy(window)

        if not results:
            console.print("[yellow]No agent accuracy data available (need 10+ outcomes).[/yellow]")
            return

        table = Table(title="Agent Accuracy")
        table.add_column("Agent", style="cyan")
        table.add_column("Hit Rate", justify="right")
        table.add_column("Confidence", justify="right")
        table.add_column("Brier", justify="right")
        table.add_column("Samples", justify="right", style="dim")
        for r in results:
            table.add_row(
                r.agent_name,
                f"{r.direction_hit_rate:.1%}" if math.isfinite(r.direction_hit_rate) else "--",
                f"{r.mean_confidence:.1%}" if math.isfinite(r.mean_confidence) else "--",
                f"{r.brier_score:.3f}" if math.isfinite(r.brier_score) else "--",
                str(r.sample_size),
            )
        console.print(table)
    except Exception as exc:
        logger.exception("Agent accuracy display failed")
        err_console.print(
            "[red]Agent accuracy failed. Check logs/options_arena.log for details.[/red]"
        )
        raise typer.Exit(code=1) from exc
    finally:
        await db.close()


@outcomes_app.command("calibration")
def calibration_cmd(
    agent: str | None = typer.Option(  # noqa: B008
        None, "--agent", help="Filter to a specific agent"
    ),
) -> None:
    """Show confidence calibration buckets."""
    asyncio.run(_calibration_async(agent))


async def _calibration_async(agent: str | None) -> None:
    """Display calibration table."""
    settings = AppSettings()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    try:
        await db.connect()
        repo = Repository(db)
        data = await repo.get_agent_calibration(agent)

        title = f"Calibration: {data.agent_name}" if data.agent_name else "Calibration: All Agents"
        if data.sample_size == 0:
            console.print(f"[yellow]No calibration data available for {title}.[/yellow]")
            return

        table = Table(title=title)
        table.add_column("Bucket", style="cyan")
        table.add_column("Predicted", justify="right")
        table.add_column("Actual", justify="right")
        table.add_column("Count", justify="right", style="dim")
        for b in data.buckets:
            table.add_row(
                b.bucket_label,
                (f"{b.mean_confidence:.1%}" if math.isfinite(b.mean_confidence) else "--"),
                f"{b.actual_hit_rate:.1%}" if math.isfinite(b.actual_hit_rate) else "--",
                str(b.count),
            )
        console.print(table)
        console.print(f"\nTotal samples: {data.sample_size}")
    except Exception as exc:
        logger.exception("Calibration display failed")
        err_console.print(
            "[red]Calibration failed. Check logs/options_arena.log for details.[/red]"
        )
        raise typer.Exit(code=1) from exc
    finally:
        await db.close()


@outcomes_app.command("agent-weights")
def agent_weights_cmd() -> None:
    """Show manual vs auto-tuned weight comparison."""
    asyncio.run(_agent_weights_async())


async def _agent_weights_async() -> None:
    """Display weight comparison table."""
    settings = AppSettings()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    try:
        await db.connect()
        repo = Repository(db)
        results = await repo.get_latest_auto_tune_weights()

        if not results:
            console.print("[yellow]No auto-tune weights available. Run auto-tune first.[/yellow]")
            return

        table = Table(title="Agent Weights Comparison")
        table.add_column("Agent", style="cyan")
        table.add_column("Manual", justify="right")
        table.add_column("Auto-Tuned", justify="right")
        table.add_column("Brier", justify="right")
        table.add_column("Samples", justify="right", style="dim")
        for r in results:
            brier_str = (
                f"{r.brier_score:.3f}"
                if r.brier_score is not None and math.isfinite(r.brier_score)
                else "--"
            )
            table.add_row(
                r.agent_name,
                f"{r.manual_weight:.3f}",
                f"{r.auto_weight:.3f}",
                brier_str,
                str(r.sample_size),
            )
        console.print(table)
    except Exception as exc:
        logger.exception("Agent weights display failed")
        err_console.print(
            "[red]Agent weights failed. Check logs/options_arena.log for details.[/red]"
        )
        raise typer.Exit(code=1) from exc
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Auto-tune command
# ---------------------------------------------------------------------------


@outcomes_app.command("auto-tune")
def auto_tune_cmd(
    dry_run: bool = typer.Option(  # noqa: FBT001
        False, "--dry-run", help="Show weights without persisting"
    ),
    window: int = typer.Option(90, "--window", help="Lookback window in days", min=1, max=365),
) -> None:
    """Compute auto-tuned agent vote weights from outcome accuracy data."""
    asyncio.run(_auto_tune_async(dry_run, window))


async def _auto_tune_async(dry_run: bool, window: int) -> None:
    """Run auto-tune and display results as a Rich table."""
    settings = AppSettings()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    try:
        await db.connect()
        repo = Repository(db)

        results = await auto_tune_weights(repo, window_days=window, dry_run=dry_run)

        if not results:
            console.print("[yellow]No outcome data available for auto-tuning.[/yellow]")
            return

        table = Table(title="Agent Vote Weights \u2014 Auto-Tune Results")
        table.add_column("Agent", style="cyan")
        table.add_column("Manual", justify="right")
        table.add_column("Tuned", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("Brier", justify="right")
        table.add_column("Samples", justify="right", style="dim")

        for r in results:
            delta = r.auto_weight - r.manual_weight
            if delta > 0:
                delta_str = f"[green]+{delta:.3f}[/green]"
            elif delta < 0:
                delta_str = f"[red]{delta:.3f}[/red]"
            else:
                delta_str = f"[dim]{delta:+.3f}[/dim]"

            brier_str = (
                f"{r.brier_score:.3f}"
                if r.brier_score is not None and math.isfinite(r.brier_score)
                else "--"
            )

            table.add_row(
                r.agent_name,
                f"{r.manual_weight:.3f}",
                f"{r.auto_weight:.3f}",
                delta_str,
                brier_str,
                str(r.sample_size),
            )

        console.print(table)

        if dry_run:
            console.print("\n[yellow][DRY RUN] Weights not saved.[/yellow]")
        else:
            console.print(
                "\n[green]Weights saved.[/green] "
                "Set [bold]ARENA_DEBATE__AUTO_TUNE_WEIGHTS=true[/bold] to use in debates."
            )

    except Exception as exc:
        logger.exception("Auto-tune failed")
        err_console.print("[red]Auto-tune failed. Check logs/options_arena.log for details.[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Backtesting commands
# ---------------------------------------------------------------------------


@outcomes_app.command("backtest")
def backtest(
    holding_days: Annotated[int, typer.Option(help="Filter by holding period")] = 20,
) -> None:
    """Show backtesting performance summary."""
    asyncio.run(_backtest_async(holding_days))


async def _backtest_async(holding_days: int) -> None:
    """Display backtesting performance summary by holding period and direction."""
    settings = AppSettings()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    try:
        await db.connect()
        repo = Repository(db)

        comparisons = await repo.get_holding_period_comparison()

        if not comparisons:
            console.print("[yellow]No outcome data found. Run 'outcomes collect' first.[/yellow]")
            return

        # Filter by holding_days
        filtered = [c for c in comparisons if c.holding_days == holding_days]

        if not filtered:
            unique_periods = sorted({c.holding_days for c in comparisons})
            periods_str = ", ".join(str(p) for p in unique_periods)
            console.print(
                f"[yellow]No data for {holding_days}-day holding period. "
                f"Available periods: {periods_str}[/yellow]"
            )
            return

        # Summary stats from equity curve and drawdowns
        equity_curve = await repo.get_equity_curve()
        drawdown_series = await repo.get_drawdown_series()

        table = Table(title=f"Backtesting Summary (T+{holding_days})")
        table.add_column("Direction", style="cyan")
        table.add_column("Trades", justify="right")
        table.add_column("Win Rate %", justify="right")
        table.add_column("Avg Return %", justify="right")
        table.add_column("Median Return %", justify="right")
        table.add_column("Sharpe", justify="right")
        table.add_column("Max Loss %", justify="right")

        for c in filtered:
            win_rate_str = f"{c.win_rate * 100:.1f}" if math.isfinite(c.win_rate) else "--"
            avg_ret_str = f"{c.avg_return:+.2f}" if math.isfinite(c.avg_return) else "--"
            med_ret_str = f"{c.median_return:+.2f}" if math.isfinite(c.median_return) else "--"
            sharpe_str = f"{c.sharpe_like:.2f}" if math.isfinite(c.sharpe_like) else "--"
            max_loss_str = f"{c.max_loss:+.2f}" if math.isfinite(c.max_loss) else "--"

            table.add_row(
                c.direction.upper(),
                str(c.count),
                win_rate_str,
                avg_ret_str,
                med_ret_str,
                sharpe_str,
                max_loss_str,
            )

        console.print(table)

        # Print equity curve summary if available
        if equity_curve:
            latest = equity_curve[-1]
            console.print(
                f"\n[dim]Equity curve: {latest.cumulative_return_pct:+.2f}% cumulative "
                f"over {latest.trade_count} trades[/dim]"
            )

        if drawdown_series:
            max_dd = min(d.drawdown_pct for d in drawdown_series)
            if math.isfinite(max_dd):
                console.print(f"[dim]Max drawdown: {max_dd:+.2f}%[/dim]")

    except Exception as exc:
        logger.exception("Backtest display failed")
        err_console.print("[red]Backtest failed. Check logs/options_arena.log for details.[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        await db.close()


@outcomes_app.command(name="equity-curve")
def equity_curve(
    direction: Annotated[
        str | None, typer.Option(help="Filter by direction (bullish/bearish)")
    ] = None,
    period: Annotated[int | None, typer.Option(help="Lookback period in days")] = None,
) -> None:
    """Show cumulative equity curve."""
    asyncio.run(_equity_curve_async(direction, period))


async def _equity_curve_async(direction: str | None, period: int | None) -> None:
    """Display equity curve as a Rich table."""
    settings = AppSettings()
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    if settings.data.db_path:
        db_path = Path(settings.data.db_path)
    else:
        db_path = _DATA_DIR / "options_arena.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)

    try:
        await db.connect()
        repo = Repository(db)

        points = await repo.get_equity_curve(direction=direction, period_days=period)

        if not points:
            msg = "No equity curve data found."
            if direction or period:
                msg += " Try adjusting filters or run 'outcomes collect' first."
            else:
                msg += " Run 'outcomes collect' first."
            console.print(f"[yellow]{msg}[/yellow]")
            return

        title = "Equity Curve"
        if direction:
            title += f" ({direction.upper()})"
        if period:
            title += f" (last {period} days)"

        table = Table(title=title)
        table.add_column("Date", style="cyan")
        table.add_column("Cumulative Return %", justify="right")
        table.add_column("Trades", justify="right", style="dim")

        for pt in points:
            cum_ret_str = (
                f"{pt.cumulative_return_pct:+.2f}"
                if math.isfinite(pt.cumulative_return_pct)
                else "--"
            )
            table.add_row(
                str(pt.date),
                cum_ret_str,
                str(pt.trade_count),
            )

        console.print(table)

    except Exception as exc:
        logger.exception("Equity curve display failed")
        err_console.print(
            "[red]Equity curve failed. Check logs/options_arena.log for details.[/red]"
        )
        raise typer.Exit(code=1) from exc
    finally:
        await db.close()
