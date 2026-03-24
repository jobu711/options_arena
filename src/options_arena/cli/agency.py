"""CLI agency subcommand group: submit desk queries and view history.

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``. Services are created and closed within the command scope.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from options_arena.cli.app import app

logger = logging.getLogger(__name__)
console = Console()
err_console = Console(stderr=True)

# Resolve data directory from project root (src/options_arena/cli/agency.py -> parents[3])
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"

agency_app = typer.Typer(
    help="AI agency desk system -- ask questions, view history.",
    no_args_is_help=True,
)
app.add_typer(agency_app, name="agency")


@agency_app.command("ask")
def ask(
    query: Annotated[str, typer.Argument(help="Natural language question")],
    desk: Annotated[str | None, typer.Option("--desk", "-d", help="Target desk type")] = None,
    ticker: Annotated[
        list[str] | None,
        typer.Option("--ticker", "-t", help="Ticker symbol (repeatable)"),
    ] = None,
) -> None:
    """Submit a query to the AI agency desk system."""
    asyncio.run(_ask_async(query, desk, ticker))


@agency_app.command("history")
def history(
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of queries")] = 20,
) -> None:
    """Show recent agency queries."""
    asyncio.run(_history_async(limit))


async def _ask_async(
    query: str,
    desk_str: str | None,
    tickers: list[str] | None,
) -> None:
    """Execute an agency query with full service lifecycle management."""
    from options_arena.agents import run_agency_query  # noqa: PLC0415
    from options_arena.agents.model_config import build_debate_model  # noqa: PLC0415
    from options_arena.data import Database, Repository  # noqa: PLC0415
    from options_arena.models import (  # noqa: PLC0415
        AgencyQuery,
        AppSettings,
        DeskType,
    )
    from options_arena.services.cache import ServiceCache  # noqa: PLC0415
    from options_arena.services.fred import FredService  # noqa: PLC0415
    from options_arena.services.market_data import MarketDataService  # noqa: PLC0415
    from options_arena.services.options_data import OptionsDataService  # noqa: PLC0415
    from options_arena.services.rate_limiter import RateLimiter  # noqa: PLC0415

    settings = AppSettings()

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = ServiceCache(settings.service)
    limiter = RateLimiter(
        settings.service.rate_limit_rps, settings.service.max_concurrent_requests
    )
    db = Database(_DATA_DIR / "options_arena.db")

    market_data: MarketDataService | None = None
    options_data: OptionsDataService | None = None
    fred: FredService | None = None

    try:
        await db.connect()
        repo = Repository(db)

        market_data = MarketDataService(settings.service, cache, limiter)
        options_data = OptionsDataService(
            settings.service,
            settings.scan.filters.options,
            cache,
            limiter,
            openbb_config=settings.openbb,
        )
        fred = FredService(settings.service, settings.pricing, cache)

        # Resolve desk override
        desk_override: DeskType | None = None
        if desk_str is not None:
            try:
                desk_override = DeskType(desk_str.lower())
            except ValueError:
                valid = ", ".join(d.value for d in DeskType)
                err_console.print(f"[red]Unknown desk: {desk_str!r}. Valid: {valid}[/red]")
                raise typer.Exit(code=1)  # noqa: B904

        # Build LLM model
        try:
            model = build_debate_model(settings.debate)
        except ValueError:
            err_console.print(
                "[yellow]No LLM API key configured. "
                "Set GROQ_API_KEY or ANTHROPIC_API_KEY.[/yellow]"
            )
            model = None

        query_id = str(uuid.uuid4())

        agency_query = AgencyQuery(
            query_id=query_id,
            query_text=query,
            created_at=datetime.now(UTC),
            desk_override=desk_override,
        )

        err_console.print("[cyan]Submitting query to agency...[/cyan]")

        response = await run_agency_query(
            agency_query,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
            repo=repo,
            model=model,
            config=settings.agency,
            tickers_override=tickers,
        )

        # Render response first so user sees answer even if persistence fails
        _render_agency_response(response)

        # Persist
        desk_csv: str | None = None
        if response.intent.desks:
            desk_csv = ",".join(d.value for d in response.intent.desks)

        await repo.save_agency_query(
            query_id=response.query_id,
            query_text=response.query_text,
            desk=desk_csv,
            tickers=response.intent.tickers,
            intent_json=response.intent.model_dump_json(),
            response_json=response.model_dump_json(),
            confidence=response.confidence,
        )

    finally:
        if fred is not None:
            await fred.close()
        if options_data is not None:
            await options_data.close()
        if market_data is not None:
            await market_data.close()
        await cache.close()
        await db.close()


async def _history_async(limit: int) -> None:
    """List recent agency queries."""
    from options_arena.data import Database, Repository  # noqa: PLC0415

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(_DATA_DIR / "options_arena.db")

    try:
        await db.connect()
        repo = Repository(db)

        rows = await repo.list_agency_queries(limit=limit)

        if not rows:
            console.print("No agency queries found.")
            return

        table = Table(title="Recent Agency Queries")
        table.add_column("Query ID", style="dim", no_wrap=True)
        table.add_column("Query", max_width=40)
        table.add_column("Desk", justify="center")
        table.add_column("Confidence", justify="right")
        table.add_column("Time", justify="right")

        for row in rows:
            table.add_row(
                row.query_id[:8],
                _truncate(row.query_text, 40),
                row.desk or "--",
                f"{row.confidence:.0%}",
                row.created_at[:19],
            )

        console.print(table)

    finally:
        await db.close()


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _render_agency_response(response: object) -> None:
    """Render an AgencyResponse to the console.

    Uses ``object`` type annotation to avoid circular import at module level.
    The actual type is ``AgencyResponse``.
    """
    # Import here to get access to the typed model attributes
    from options_arena.models import AgencyResponse  # noqa: PLC0415

    assert isinstance(response, AgencyResponse)

    # Desk responses
    for desk_resp in response.desk_responses:
        title = f"[bold]{desk_resp.desk.value.upper()} DESK[/bold]"
        tools = ", ".join(desk_resp.tools_used) if desk_resp.tools_used else "none"
        conf = f"{desk_resp.confidence:.0%}"
        body = f"{desk_resp.response}\n\n[dim]Tools: {tools} | Confidence: {conf}[/dim]"
        console.print(Panel(body, title=title, border_style="cyan"))

    # Synthesis
    if response.synthesis:
        console.print(
            Panel(
                response.synthesis,
                title="[bold]Synthesis[/bold]",
                border_style="green",
            )
        )

    # Overall confidence
    console.print(f"\nOverall confidence: {response.confidence:.0%}")


# ---------------------------------------------------------------------------
# Learn subcommand group
# ---------------------------------------------------------------------------

learn_app = typer.Typer(
    help="Self-improvement learning system -- weight tuning, mining, and playbook.",
    no_args_is_help=True,
)
agency_app.add_typer(learn_app, name="learn")


@learn_app.command("status")
def learn_status() -> None:
    """Show learning system status: last tune timestamps and sample counts."""
    asyncio.run(_learn_status_async())


async def _learn_status_async() -> None:
    """Display learning system status."""
    from options_arena.data import Database, Repository
    from options_arena.models import WeightType

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(str(_DATA_DIR / "options_arena.db"))
    try:
        await db.connect()
        repo = Repository(db)

        vote_history = await repo.get_weight_history(limit=1, weight_type=WeightType.VOTE)
        indicator_history = await repo.get_weight_history(
            limit=1, weight_type=WeightType.INDICATOR
        )

        table = Table(title="Learning System Status")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        last_vote = vote_history[0].computed_at.isoformat() if vote_history else "Never"
        last_ind = indicator_history[0].computed_at.isoformat() if indicator_history else "Never"
        vote_agents = len(vote_history[0].weights) if vote_history else 0
        ind_count = len(indicator_history[0].weights) if indicator_history else 0
        accuracy = (
            f"{indicator_history[0].accuracy_at_time:.1%}"
            if indicator_history and indicator_history[0].accuracy_at_time is not None
            else "--"
        )

        table.add_row("Last vote tune", last_vote)
        table.add_row("Vote agents tracked", str(vote_agents))
        table.add_row("Last indicator tune", last_ind)
        table.add_row("Indicators tuned", str(ind_count))
        table.add_row("Accuracy at last tune", accuracy)

        console.print(table)
    finally:
        await db.close()


@learn_app.command("weights")
def learn_weights(
    window: int = typer.Option(90, "--window", help="Lookback window in days", min=1),
    apply: bool = typer.Option(  # noqa: FBT001
        False, "--apply", help="Persist tuned weights (read-only by default)"
    ),
) -> None:
    """Compute indicator weight tuning and show comparison table."""
    asyncio.run(_learn_weights_async(window, dry_run=not apply))


async def _learn_weights_async(window: int, dry_run: bool) -> None:
    """Run indicator weight tuning and display results."""
    import math

    from options_arena.data import Database, Repository
    from options_arena.learning import auto_tune_indicator_weights

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(str(_DATA_DIR / "options_arena.db"))
    try:
        await db.connect()
        repo = Repository(db)

        results = await auto_tune_indicator_weights(repo, window_days=window, dry_run=dry_run)

        if not results:
            console.print(
                "[yellow]Indicator tuning produced no results. "
                "Check logs — may need 50+ scored outcomes or an error occurred.[/yellow]"
            )
            return

        table = Table(
            title=f"Indicator Weight Tuning (window={window}d{', read-only' if dry_run else ''})"
        )
        table.add_column("Indicator", style="bold")
        table.add_column("Static", justify="right")
        table.add_column("Tuned", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("Pearson r", justify="right")
        table.add_column("Samples", justify="right")

        for r in sorted(results, key=lambda x: x.tuned_weight, reverse=True):
            delta = r.tuned_weight - r.static_weight
            delta_str = f"{delta:+.4f}"
            pearson_str = (
                f"{r.pearson_r:.3f}"
                if r.pearson_r is not None and math.isfinite(r.pearson_r)
                else "--"
            )
            table.add_row(
                r.indicator_name,
                f"{r.static_weight:.4f}",
                f"{r.tuned_weight:.4f}",
                delta_str,
                pearson_str,
                str(r.sample_count),
            )

        console.print(table)
        total = sum(r.tuned_weight for r in results)
        console.print(f"\nTotal weight sum: {total:.6f}")
    finally:
        await db.close()


@learn_app.command("mine")
def learn_mine() -> None:
    """Mine historical outcomes for strategy patterns."""
    asyncio.run(_learn_mine_async())


async def _learn_mine_async() -> None:
    """Run strategy mining and display generated rules."""
    from options_arena.data import Database, Repository
    from options_arena.learning import run_strategy_mining

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(str(_DATA_DIR / "options_arena.db"))
    try:
        await db.connect()
        repo = Repository(db)

        rules = await run_strategy_mining(repo)

        if not rules:
            console.print(
                "[yellow]No significant patterns found. "
                "Need 100+ outcomes with sufficient dimensional variety.[/yellow]"
            )
            return

        table = Table(title=f"Strategy Mining Results ({len(rules)} rules generated)")
        table.add_column("Rule ID", style="bold", max_width=30)
        table.add_column("Pattern", max_width=50)
        table.add_column("Win Rate", justify="right")
        table.add_column("Avg Return", justify="right")
        table.add_column("Samples", justify="right")
        table.add_column("Status", justify="center")

        for r in rules:
            table.add_row(
                r.rule_id[:28],
                r.pattern,
                f"{r.win_rate:.1%}",
                f"{r.avg_return:+.1%}",
                str(r.sample_size),
                r.status.value,
            )

        console.print(table)
        console.print(
            "\nRules saved as candidates. "
            "Use [bold]learn playbook[/bold] to view and approve/reject."
        )
    finally:
        await db.close()


@learn_app.command("playbook")
def learn_playbook(
    status: str | None = typer.Option(
        None, "--status", help="Filter by status: candidate, approved, rejected"
    ),
) -> None:
    """List strategy rules in the playbook."""
    asyncio.run(_learn_playbook_async(status))


async def _learn_playbook_async(status_filter: str | None) -> None:
    """Display strategy playbook."""
    from options_arena.data import Database, Repository
    from options_arena.models import RuleStatus

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(str(_DATA_DIR / "options_arena.db"))
    try:
        await db.connect()
        repo = Repository(db)

        rule_status: RuleStatus | None = None
        if status_filter is not None:
            try:
                rule_status = RuleStatus(status_filter)
            except ValueError:
                err_console.print(
                    f"[red]Invalid status: {status_filter}. "
                    f"Use: candidate, approved, rejected[/red]"
                )
                raise typer.Exit(code=1) from None

        rules = await repo.get_strategy_rules(status=rule_status)

        if not rules:
            console.print("[yellow]No strategy rules found.[/yellow]")
            return

        title = "Strategy Playbook"
        if rule_status:
            title += f" (status={rule_status.value})"

        table = Table(title=title)
        table.add_column("Rule ID", style="bold", max_width=30)
        table.add_column("Pattern", max_width=50)
        table.add_column("Win Rate", justify="right")
        table.add_column("Avg Return", justify="right")
        table.add_column("Samples", justify="right")
        table.add_column("Confidence", justify="right")
        table.add_column("Last Validated", justify="right")
        table.add_column("Status", justify="center")

        status_styles = {
            "candidate": "yellow",
            "approved": "green",
            "rejected": "red",
        }

        for r in rules:
            style = status_styles.get(r.status.value, "")
            last_validated_str = (
                r.last_validated.strftime("%Y-%m-%d") if r.last_validated else "--"
            )
            table.add_row(
                r.rule_id[:28],
                r.pattern,
                f"{r.win_rate:.1%}",
                f"{r.avg_return:+.1%}",
                str(r.sample_size),
                f"{r.confidence:.0%}",
                last_validated_str,
                f"[{style}]{r.status.value}[/{style}]",
            )

        console.print(table)
        console.print(f"\nTotal rules: {len(rules)}")
    finally:
        await db.close()


@learn_app.command("attribution")
def learn_attribution(
    window_days: int = typer.Option(90, min=7, max=365, help="Lookback window in days"),
    source: str | None = typer.Option(None, help="Filter to single source"),
) -> None:
    """Show prediction accuracy by source and market condition."""
    from options_arena.models.attribution import PredictionSource  # noqa: PLC0415

    source_enum: PredictionSource | None = None
    if source is not None:
        try:
            source_enum = PredictionSource(source)
        except ValueError:
            valid = ", ".join(s.value for s in PredictionSource)
            err_console.print(f"[red]Unknown source: {source!r}. Valid: {valid}[/red]")
            raise typer.Exit(code=1) from None

    asyncio.run(_run_attribution(window_days, source_enum))


async def _run_attribution(
    window_days: int,
    source: object,
) -> None:
    """Fetch predictions and display attribution report.

    Parameters
    ----------
    window_days
        Number of days to look back.
    source
        Optional ``PredictionSource`` filter (typed as ``object`` to avoid
        top-level import).
    """
    from options_arena.data import Database, Repository  # noqa: PLC0415
    from options_arena.learning.prediction_ledger import compute_attribution  # noqa: PLC0415
    from options_arena.models.attribution import PredictionSource  # noqa: PLC0415

    source_typed: PredictionSource | None = None
    if source is not None:
        assert isinstance(source, PredictionSource)
        source_typed = source

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(str(_DATA_DIR / "options_arena.db"))
    try:
        await db.connect()
        repo = Repository(db)

        predictions = await repo.get_predictions(window_days, source_typed)
        report = compute_attribution(predictions)

        if not report.source_accuracy:
            console.print(f"No scored predictions found in the last {window_days} days.")
            return

        # Source accuracy table
        table = Table(title=f"Prediction Attribution (last {window_days} days)")
        table.add_column("Source", style="bold")
        table.add_column("Total", justify="right")
        table.add_column("Correct", justify="right")
        table.add_column("Accuracy", justify="right")
        table.add_column("Sufficient", justify="center")

        for acc in report.source_accuracy:
            table.add_row(
                acc.source.value,
                str(acc.total),
                str(acc.correct),
                f"{acc.accuracy:.1%}",
                "yes" if acc.sample_sufficient else "no",
            )

        console.print(table)
        console.print(
            f"\nTotal recommendations: {report.total_recommendations}"
            f"  |  Total outcomes: {report.total_outcomes}"
        )

        # Condition accuracy table (if any rows exist)
        if report.condition_accuracy:
            cond_table = Table(title="Condition Breakdown")
            cond_table.add_column("Source", style="bold")
            cond_table.add_column("Condition")
            cond_table.add_column("Accuracy", justify="right")
            cond_table.add_column("Samples", justify="right")

            for ca in report.condition_accuracy:
                cond_table.add_row(
                    ca.source.value,
                    ca.condition,
                    f"{ca.accuracy:.1%}",
                    str(ca.total),
                )

            console.print(cond_table)
    finally:
        await db.close()


@learn_app.command("decay")
def learn_decay() -> None:
    """Apply confidence decay and auto-promote/demote strategy rules."""
    asyncio.run(_learn_decay_async())


async def _learn_decay_async() -> None:
    """Run confidence decay pipeline and display summary."""
    from options_arena.data import Database, Repository
    from options_arena.learning import run_confidence_decay
    from options_arena.models import RuleStatus

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = Database(str(_DATA_DIR / "options_arena.db"))
    try:
        await db.connect()
        repo = Repository(db)

        # Snapshot rule statuses before decay
        rules_before = await repo.get_strategy_rules()
        statuses_before: dict[str, str] = {r.rule_id: r.status.value for r in rules_before}

        await run_confidence_decay(repo)

        # Fetch rules after decay to compute summary
        rules_after = await repo.get_strategy_rules()

        if not rules_after:
            console.print("[yellow]No strategy rules found.[/yellow]")
            return

        promoted = sum(
            1
            for r in rules_after
            if r.status == RuleStatus.APPROVED
            and statuses_before.get(r.rule_id) == RuleStatus.CANDIDATE.value
        )
        demoted = sum(
            1
            for r in rules_after
            if r.status == RuleStatus.REJECTED
            and statuses_before.get(r.rule_id)
            in {
                RuleStatus.CANDIDATE.value,
                RuleStatus.APPROVED.value,
            }
        )

        table = Table(title="Confidence Decay Summary")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Total rules", str(len(rules_after)))
        table.add_row("Promoted to approved", str(promoted))
        table.add_row("Demoted to rejected", str(demoted))

        console.print(table)
    finally:
        await db.close()
