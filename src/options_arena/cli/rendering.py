"""Pure rendering functions for CLI output.

All functions produce Rich renderables (Table, Text, Panel) from typed models.
No I/O, no service calls -- pure data-to-display transformation.
"""

from __future__ import annotations

import logging
import math

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from options_arena.agents._parsing import DebateResult
from options_arena.data.repository import DebateRow
from options_arena.models import TradeThesis, VolatilityThesis
from options_arena.models.health import HealthStatus
from options_arena.scan.models import ScanResult

logger = logging.getLogger(__name__)

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


# ---------------------------------------------------------------------------
# Debate rendering
# ---------------------------------------------------------------------------

# Direction color mapping (trading convention) — shared across debate panels
_DIRECTION_STYLES: dict[str, str] = {
    "bullish": "bold green",
    "bearish": "bold red",
    "neutral": "bold yellow",
}


def render_volatility_panel(thesis: VolatilityThesis) -> Panel:
    """Render Volatility Agent output as a cyan-bordered Rich Panel.

    Uses ``Text()`` constructor (defaults to no markup) to prevent bracket
    interpretation from agent-generated content.

    Args:
        thesis: VolatilityThesis from the Volatility Agent.

    Returns:
        Rich Panel with cyan border showing IV assessment and strategy.
    """
    lines: list[str] = [
        f"IV Assessment: {thesis.iv_assessment.upper()}",
        f"Confidence: {thesis.confidence * 100:.0f}%",
        f"IV Rank Interpretation: {thesis.iv_rank_interpretation}",
        "",
        thesis.strategy_rationale,
    ]

    if thesis.recommended_strategy is not None:
        lines.append("")
        lines.append(f"Recommended Strategy: {thesis.recommended_strategy.value.upper()}")

    if thesis.target_iv_entry is not None or thesis.target_iv_exit is not None:
        lines.append("")
        if thesis.target_iv_entry is not None:
            lines.append(f"Target IV Entry: {thesis.target_iv_entry:.1f}")
        if thesis.target_iv_exit is not None:
            lines.append(f"Target IV Exit: {thesis.target_iv_exit:.1f}")

    if thesis.suggested_strikes:
        lines.append("")
        lines.append(f"Suggested Strikes: {', '.join(thesis.suggested_strikes)}")

    if thesis.key_vol_factors:
        lines.append("")
        lines.append("Key Volatility Factors:")
        for factor in thesis.key_vol_factors:
            lines.append(f"  * {factor}")

    # Text() defaults to no markup — prevents agent text with [brackets] from crashing Rich
    return Panel(
        Text("\n".join(lines)),
        border_style="cyan",
        title="VOLATILITY ANALYSIS",
        title_align="left",
    )


def render_debate_panels(console: Console, result: DebateResult) -> None:
    """Render debate result as Rich panels: Bull (green), Bear (red), Verdict (blue).

    Agent argument text is rendered with ``markup=False`` to prevent Rich from
    interpreting ``[brackets]`` (e.g., ``[RSI]``, ``[AAPL]``) as style tags.

    Args:
        console: Rich Console instance for stdout output.
        result: Complete debate output from ``run_debate()``.
    """
    # Fallback warning banner
    if result.is_fallback:
        console.print(
            Panel(
                Text(
                    "Data-driven analysis -- AI unavailable. Exercise additional caution.",
                    style="bold yellow",
                ),
                border_style="yellow",
                title="WARNING",
            )
        )
        console.print()

    # --- Bull panel ---
    bull = result.bull_response
    bull_body = _build_agent_panel_text(
        direction=bull.direction.value.upper(),
        confidence=bull.confidence,
        argument=bull.argument,
        key_points=bull.key_points,
        risks=bull.risks_cited,
    )
    console.print(
        Panel(
            bull_body,
            border_style="green",
            title="BULL",
            title_align="left",
        )
    )
    console.print()

    # --- Bear panel ---
    bear = result.bear_response
    bear_body = _build_agent_panel_text(
        direction=bear.direction.value.upper(),
        confidence=bear.confidence,
        argument=bear.argument,
        key_points=bear.key_points,
        risks=bear.risks_cited,
    )
    console.print(
        Panel(
            bear_body,
            border_style="red",
            title="BEAR",
            title_align="left",
        )
    )
    console.print()

    # --- Verdict panel ---
    thesis = result.thesis
    verdict_body = _build_verdict_panel_text(thesis)
    console.print(
        Panel(
            verdict_body,
            border_style="blue",
            title=f"VERDICT: {thesis.ticker}",
            title_align="left",
        )
    )


def _build_agent_panel_text(
    *,
    direction: str,
    confidence: float,
    argument: str,
    key_points: list[str],
    risks: list[str],
) -> Text:
    """Build Rich Text for a bull or bear panel.

    Uses ``markup=False`` on the Text to prevent bracket interpretation.
    """
    lines: list[str] = [
        f"Direction: {direction}",
        f"Confidence: {confidence * 100:.0f}%",
        "",
        argument,
    ]

    if key_points:
        lines.append("")
        lines.append("Key Points:")
        for point in key_points:
            lines.append(f"  * {point}")

    if risks:
        lines.append("")
        lines.append("Risks:")
        for risk in risks:
            lines.append(f"  * {risk}")

    # markup=False prevents [RSI], [AAPL], etc. from being parsed as Rich tags
    return Text("\n".join(lines))


def _build_verdict_panel_text(thesis: TradeThesis) -> Text:
    """Build Rich Text for the verdict panel.

    Uses ``markup=False`` on the Text to prevent bracket interpretation.
    """
    direction_style = _DIRECTION_STYLES.get(thesis.direction.value, "")
    bull_str = f"{thesis.bull_score:.1f}" if math.isfinite(thesis.bull_score) else "--"
    bear_str = f"{thesis.bear_score:.1f}" if math.isfinite(thesis.bear_score) else "--"
    conf_str = f"{thesis.confidence * 100:.0f}%" if math.isfinite(thesis.confidence) else "--"
    lines: list[str] = [
        f"Direction: {thesis.direction.value.upper()}",
        f"Confidence: {conf_str}",
        f"Bull Score: {bull_str} / Bear Score: {bear_str}",
        "",
        thesis.summary,
    ]

    if thesis.key_factors:
        lines.append("")
        lines.append("Key Factors:")
        for factor in thesis.key_factors:
            lines.append(f"  * {factor}")

    lines.append("")
    lines.append("Risk Assessment:")
    lines.append(f"  {thesis.risk_assessment}")

    if thesis.recommended_strategy is not None:
        lines.append("")
        lines.append(f"Recommended Strategy: {thesis.recommended_strategy.value.upper()}")

    # Build text without markup to avoid bracket interpretation
    text = Text("\n".join(lines))

    # Apply direction color to the first line only
    if direction_style:
        direction_label = f"Direction: {thesis.direction.value.upper()}"
        text.stylize(direction_style, 0, len(direction_label))

    return text


def render_debate_history(debates: list[DebateRow], ticker: str) -> Table:
    """Render past debates as a Rich table.

    Parses ``DebateRow.verdict_json`` into ``TradeThesis`` to extract direction
    and confidence. Handles parse errors gracefully with ``--`` placeholders.

    Args:
        debates: List of DebateRow from ``Repository.get_debates_for_ticker()``.
        ticker: Ticker symbol for table title.

    Returns:
        Rich Table with debate history.
    """
    table = Table(title=f"Debate History -- {ticker}")
    table.add_column("Date", style="dim")
    table.add_column("Direction", justify="center")
    table.add_column("Confidence", justify="right")
    table.add_column("Fallback", justify="center")
    table.add_column("Summary")

    for debate in debates:
        # Parse verdict JSON to extract direction and confidence
        direction_text: Text | str = "--"
        confidence_str = "--"
        summary_str = "--"

        if debate.verdict_json is not None:
            try:
                thesis = TradeThesis.model_validate_json(debate.verdict_json)
                direction_style = _DIRECTION_STYLES.get(thesis.direction.value, "")
                direction_text = Text(thesis.direction.value.upper(), style=direction_style)
                confidence_str = f"{thesis.confidence * 100:.0f}%"
                # Truncate summary to ~60 chars
                summary_raw = thesis.summary
                summary_str = summary_raw[:57] + "..." if len(summary_raw) > 60 else summary_raw
            except ValidationError:
                logger.debug(
                    "Failed to parse verdict_json for debate id=%d", debate.id, exc_info=True
                )

        fallback_text = (
            Text("Yes", style="yellow") if debate.is_fallback else Text("No", style="dim")
        )

        date_str = debate.created_at.strftime("%Y-%m-%d %H:%M:%S")

        table.add_row(
            date_str,
            direction_text,
            confidence_str,
            fallback_text,
            summary_str,
        )

    return table
