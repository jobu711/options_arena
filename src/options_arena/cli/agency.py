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
