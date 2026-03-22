"""CLI eval subcommand group: run agent evaluations and view results.

Each command is a sync Typer function wrapping an async internal function
via ``asyncio.run()``. Services are created and closed within the command scope.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from options_arena.cli.app import app

logger = logging.getLogger(__name__)
console = Console()
err_console = Console(stderr=True)

# Resolve data directory from project root (src/options_arena/cli/eval.py -> parents[3])
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"

eval_app = typer.Typer(
    help="Agent evaluation harness -- run evals, view reports, manage baselines.",
    no_args_is_help=True,
)
app.add_typer(eval_app, name="eval")


@eval_app.command("check")
def check(
    desk: Annotated[
        str | None,
        typer.Option("--desk", "-d", help="Filter evals by target desk type"),
    ] = None,
) -> None:
    """Run all eval definitions and report pass@k metrics."""
    asyncio.run(_check_async(desk))


@eval_app.command("report")
def report() -> None:
    """Show the latest eval report with pass@k, regressions, and verdict."""
    asyncio.run(_report_async())


@eval_app.command("list")
def list_evals() -> None:
    """List all eval definitions with their status."""
    asyncio.run(_list_async())


# ---------------------------------------------------------------------------
# Async internals
# ---------------------------------------------------------------------------


async def _check_async(desk_name: str | None) -> None:
    """Run eval check and display results."""
    from options_arena.data import Database, Repository  # noqa: PLC0415
    from options_arena.evals import run_eval_check  # noqa: PLC0415
    from options_arena.models.config import AppSettings  # noqa: PLC0415
    from options_arena.models.enums import DeskType  # noqa: PLC0415

    settings = AppSettings()
    db = Database(_DATA_DIR / "options_arena.db")
    await db.connect()
    repo = Repository(db)

    try:
        desk_filter: DeskType | None = None
        if desk_name is not None:
            try:
                desk_filter = DeskType(desk_name.lower())
            except ValueError:
                err_console.print(f"[red]Unknown desk: {desk_name}[/]")
                raise typer.Exit(code=1) from None

        report = await run_eval_check(repo, settings.eval, desk_filter=desk_filter)

        # Display results table
        table = Table(title="Eval Check Results")
        table.add_column("Eval", style="bold white", no_wrap=True)
        table.add_column("Passed", justify="center")
        table.add_column("Successes", justify="right")
        table.add_column("Attempts", justify="right")
        table.add_column("Duration", justify="right")

        for run in report.runs:
            passed_style = "bold green" if run.passed else "bold red"
            status = Text("PASS" if run.passed else "FAIL", style=passed_style)
            table.add_row(
                run.eval_name,
                status,
                str(run.successes),
                str(run.attempts),
                f"{run.duration_ms}ms",
            )

        console.print(table)

        # Summary
        verdict_style = {
            "ship": "bold green",
            "needs_work": "bold yellow",
            "blocked": "bold red",
        }
        console.print(
            f"\npass@1: {report.pass_at_1:.1%}  "
            f"pass@3: {report.pass_at_3:.1%}  "
            f"Verdict: ",
            end="",
        )
        console.print(
            report.verdict.value.upper(),
            style=verdict_style.get(report.verdict.value, ""),
        )

        if report.regressions:
            console.print(
                f"\n[bold red]Regressions:[/] {', '.join(report.regressions)}"
            )

    finally:
        await db.close()


async def _report_async() -> None:
    """Display the latest eval runs."""
    from options_arena.data import Database, Repository  # noqa: PLC0415

    db = Database(_DATA_DIR / "options_arena.db")
    await db.connect()
    repo = Repository(db)

    try:
        runs = await repo.get_latest_eval_runs()
        if not runs:
            console.print("[yellow]No eval runs found. Run 'eval check' first.[/]")
            return

        table = Table(title="Latest Eval Results")
        table.add_column("Eval", style="bold white", no_wrap=True)
        table.add_column("Passed", justify="center")
        table.add_column("Successes", justify="right")
        table.add_column("Attempts", justify="right")
        table.add_column("Model", justify="center")
        table.add_column("Duration", justify="right")
        table.add_column("Timestamp", justify="right")

        for run in runs:
            passed_style = "bold green" if run.passed else "bold red"
            status = Text("PASS" if run.passed else "FAIL", style=passed_style)
            table.add_row(
                run.eval_name,
                status,
                str(run.successes),
                str(run.attempts),
                run.model_used,
                f"{run.duration_ms}ms",
                run.timestamp.strftime("%Y-%m-%d %H:%M"),
            )

        console.print(table)

        # Summary stats
        passed_count = sum(1 for r in runs if r.passed)
        total = len(runs)
        pass_rate = passed_count / total if total > 0 else 0.0
        console.print(f"\n{passed_count}/{total} evals passing ({pass_rate:.0%})")

    finally:
        await db.close()


async def _list_async() -> None:
    """List all eval definitions."""
    from options_arena.data import Database, Repository  # noqa: PLC0415

    db = Database(_DATA_DIR / "options_arena.db")
    await db.connect()
    repo = Repository(db)

    try:
        definitions = await repo.get_eval_definitions()
        if not definitions:
            console.print("[yellow]No eval definitions found.[/]")
            return

        table = Table(title="Eval Definitions")
        table.add_column("Name", style="bold white", no_wrap=True)
        table.add_column("Type", justify="center")
        table.add_column("Desk", justify="center")
        table.add_column("Grader", justify="center")
        table.add_column("Direction", justify="center")
        table.add_column("Confidence", justify="center")

        for defn in definitions:
            desk = defn.target_desk.value if defn.target_desk else "synthesis"
            direction = defn.expected_direction.value if defn.expected_direction else "--"
            conf_range = "--"
            has_bounds = (
                defn.expected_confidence_min is not None
                or defn.expected_confidence_max is not None
            )
            if has_bounds:
                c_min = defn.expected_confidence_min
                c_max = defn.expected_confidence_max
                lo = f"{c_min:.1f}" if c_min is not None else "0.0"
                hi = f"{c_max:.1f}" if c_max is not None else "1.0"
                conf_range = f"[{lo}, {hi}]"

            table.add_row(
                defn.name,
                defn.eval_type.value,
                desk,
                defn.grader_type.value,
                direction,
                conf_range,
            )

        console.print(table)
        console.print(f"\n{len(definitions)} eval definitions")

    finally:
        await db.close()
