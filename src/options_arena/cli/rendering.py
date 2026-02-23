"""Pure rendering functions for CLI output.

All functions produce Rich renderables (Table, Text, Panel) from typed models.
No I/O, no service calls -- pure data-to-display transformation.
"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

from options_arena.models.health import HealthStatus

DISCLAIMER = (
    "[dim]This tool is for educational and informational purposes only. "
    "It does not constitute financial advice. Options trading involves "
    "substantial risk of loss. Past performance does not guarantee future results.[/dim]"
)


def render_health_table(statuses: list[HealthStatus]) -> Table:
    """Render health check results as a Rich table.

    Args:
        statuses: List of HealthStatus from HealthService.check_all().

    Returns:
        Rich Table with service name, status, latency, and error columns.
    """
    table = Table(title="Service Health")
    table.add_column("Service", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Latency", justify="right")
    table.add_column("Error")

    for s in statuses:
        status_text = (
            Text("UP", style="bold green") if s.available else Text("DOWN", style="bold red")
        )
        latency = f"{s.latency_ms:.0f}ms" if s.latency_ms is not None else "--"
        table.add_row(s.service_name, status_text, latency, s.error or "")

    return table
