"""Pure rendering functions for CLI output.

All functions produce Rich renderables (Table, Text, Panel) from typed models.
No I/O, no service calls -- pure data-to-display transformation.
"""

from __future__ import annotations

import math

from rich.table import Table
from rich.text import Text

from options_arena.models.health import HealthStatus
from options_arena.scan.models import ScanResult

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


def render_scan_table(result: ScanResult) -> Table:
    """Render scan results as a Rich table with trading-convention styling.

    Financial formatting:
    - Green for BULLISH, red for BEARISH, yellow for NEUTRAL
    - Scores: 1 decimal, Greeks: 4 decimals, prices: 2 decimals
    - Right-align numeric columns

    Args:
        result: ScanResult from the pipeline.

    Returns:
        Rich Table with scan results.
    """
    table = Table(title=f"Scan Results -- {result.scan_run.preset.upper()}")

    table.add_column("Ticker", style="bold white", no_wrap=True)
    table.add_column("Score", justify="right", style="cyan")
    table.add_column("Direction", justify="center")
    table.add_column("Type", justify="center")
    table.add_column("Strike", justify="right")
    table.add_column("Exp", justify="right")
    table.add_column("DTE", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("IV", justify="right")
    table.add_column("Bid/Ask", justify="right")

    # Direction color mapping (trading convention)
    direction_styles: dict[str, str] = {
        "bullish": "bold green",
        "bearish": "bold red",
        "neutral": "bold yellow",
    }

    for score in result.scores:
        contracts = result.recommendations.get(score.ticker, [])
        direction_style = direction_styles.get(score.direction.value, "")
        direction_text = Text(score.direction.value.upper(), style=direction_style)

        if contracts:
            contract = contracts[0]  # Primary recommendation
            greeks = contract.greeks
            delta_str = f"{greeks.delta:.4f}" if greeks else "--"
            iv_str = (
                f"{contract.market_iv * 100:.1f}%" if math.isfinite(contract.market_iv) else "--"
            )
            table.add_row(
                score.ticker,
                f"{score.composite_score:.1f}",
                direction_text,
                contract.option_type.value.upper(),
                f"${contract.strike:.2f}",
                str(contract.expiration),
                str(contract.dte),
                delta_str,
                iv_str,
                f"${contract.bid:.2f}/${contract.ask:.2f}",
            )
        else:
            table.add_row(
                score.ticker,
                f"{score.composite_score:.1f}",
                direction_text,
                "--",
                "--",
                "--",
                "--",
                "--",
                "--",
                "--",
            )

    return table
