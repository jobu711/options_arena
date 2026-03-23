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

from options_arena.data.repository import DebateRow
from options_arena.models import (
    ExtendedTradeThesis,
    TradeThesis,
)
from options_arena.models.health import HealthStatus
from options_arena.models.recommendation import (
    DomainAssessment,
    PositionRecommendation,
    RecommendationResult,
)
from options_arena.scan.models import ScanResult

logger = logging.getLogger(__name__)

# Windows cp1252 console cannot render many Unicode chars (√, →, etc.)
# Replace common math/symbol chars with ASCII equivalents.
_UNICODE_REPLACEMENTS: dict[str, str] = {
    "\u221a": "sqrt",  # √
    "\u2192": "->",  # →
    "\u2190": "<-",  # ←
    "\u2264": "<=",  # ≤
    "\u2265": ">=",  # ≥
    "\u2260": "!=",  # ≠
    "\u00b1": "+/-",  # ±
    "\u2014": "--",  # —
    "\u2013": "-",  # –
    "\u2018": "'",  # '
    "\u2019": "'",  # '
    "\u201c": '"',  # "
    "\u201d": '"',  # "
    "\u2026": "...",  # …
    "\u03c3": "sigma",  # σ
    "\u0394": "delta",  # Δ
}


def _safe_text(text: str) -> str:
    """Replace Unicode chars that cp1252 cannot encode with ASCII equivalents."""
    for char, replacement in _UNICODE_REPLACEMENTS.items():
        text = text.replace(char, replacement)
    # Fallback: replace any remaining non-cp1252 chars
    return text.encode("cp1252", errors="replace").decode("cp1252")


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
                # Try ExtendedTradeThesis first (6-agent protocol), fall back to TradeThesis
                parsed_thesis: TradeThesis
                try:
                    parsed_thesis = ExtendedTradeThesis.model_validate_json(debate.verdict_json)
                except ValidationError:
                    parsed_thesis = TradeThesis.model_validate_json(debate.verdict_json)
                direction_style = _DIRECTION_STYLES.get(parsed_thesis.direction.value, "")
                direction_text = Text(parsed_thesis.direction.value.upper(), style=direction_style)
                confidence_str = f"{parsed_thesis.confidence * 100:.0f}%"
                # Truncate summary to ~60 chars
                summary_raw = parsed_thesis.summary
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


# ---------------------------------------------------------------------------
# Recommendation rendering (unified agent system)
# ---------------------------------------------------------------------------


def render_recommendation(
    console: Console,
    result: RecommendationResult,
) -> None:
    """Render a recommendation result as Rich panels for the unified agent pipeline.

    Layout: Fallback warning (if applicable) -> 6 domain assessment panels ->
    Position recommendation table.

    Agent text is rendered with ``markup=False`` to prevent Rich from interpreting
    ``[brackets]`` (e.g., ``[RSI]``, ``[AAPL]``) as style tags.

    Args:
        console: Rich Console instance for stdout output.
        result: Complete recommendation output from ``run_recommendation()``.
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
                title="FALLBACK",
            )
        )
        console.print()

    # --- Domain assessment panels ---
    if result.assessments:
        for assessment in result.assessments:
            _render_assessment_panel(console, assessment)
    else:
        console.print(
            Panel(
                Text("No assessments available.", style="dim"),
                border_style="dim",
                title="ASSESSMENTS",
            )
        )
        console.print()

    # --- Position recommendation ---
    rec = result.recommendation
    _render_position_recommendation(console, rec)


def _render_assessment_panel(
    console: Console,
    assessment: DomainAssessment,
) -> None:
    """Render a single domain assessment as a Rich Panel.

    Args:
        console: Rich Console instance for stdout output.
        assessment: A concrete DomainAssessment subclass instance.
    """
    desk_name = assessment.desk.value.upper()
    direction = assessment.direction.value.upper()
    direction_style = _DIRECTION_STYLES.get(assessment.direction.value, "")
    confidence_str = (
        f"{assessment.confidence * 100:.0f}%" if math.isfinite(assessment.confidence) else "--"
    )

    lines: list[str] = [
        f"Direction: {direction}  |  Confidence: {confidence_str}",
        "",
        _safe_text(assessment.summary),
    ]

    if assessment.key_factors:
        lines.append("")
        lines.append("Key Factors:")
        for factor in assessment.key_factors:
            lines.append(f"  - {_safe_text(factor)}")

    if assessment.risks:
        lines.append("")
        lines.append("Risks:")
        for risk in assessment.risks:
            lines.append(f"  - {_safe_text(risk)}")

    body = Text("\n".join(lines))
    # Color the direction portion on the first line
    if direction_style:
        direction_label = f"Direction: {direction}"
        body.stylize(direction_style, 0, len(direction_label))

    border_style = _DIRECTION_STYLES.get(assessment.direction.value, "dim")
    console.print(
        Panel(
            body,
            border_style=border_style,
            title=f"{desk_name} ASSESSMENT",
            title_align="left",
        )
    )
    console.print()


def _render_position_recommendation(
    console: Console,
    rec: PositionRecommendation,
) -> None:
    """Render the position recommendation as a Rich Table + summary panel.

    Args:
        console: Rich Console instance for stdout output.
        rec: The position recommendation from synthesis.
    """
    direction = rec.direction.value.upper()
    direction_style = _DIRECTION_STYLES.get(rec.direction.value, "bold white")
    confidence_str = f"{rec.confidence * 100:.0f}%" if math.isfinite(rec.confidence) else "--"
    strategy_str = (
        rec.recommended_strategy.value.upper()
        if rec.recommended_strategy is not None
        else "SINGLE LEG"
    )

    # Contract + position details table
    table = Table(title="Position Recommendation", show_header=True)
    table.add_column("Detail", style="bold white", no_wrap=True)
    table.add_column("Value", justify="right")

    table.add_row("Ticker", rec.ticker)
    table.add_row("Contract", _safe_text(rec.recommended_contract))
    table.add_row("Direction", Text(direction, style=direction_style))
    table.add_row("Confidence", confidence_str)
    table.add_row("Entry Price", f"${rec.entry_price:.2f}")

    if rec.stop_loss is not None:
        table.add_row("Stop Loss", f"${rec.stop_loss:.2f}")
    if rec.take_profit is not None:
        table.add_row("Take Profit", f"${rec.take_profit:.2f}")

    table.add_row("Position Size", f"{rec.position_size_pct:.0%}")
    rr_str = f"{rec.risk_reward_ratio:.2f}" if math.isfinite(rec.risk_reward_ratio) else "--"
    table.add_row("Risk/Reward", rr_str)
    table.add_row("Max Loss", _safe_text(rec.max_loss_estimate))
    table.add_row("Strategy", strategy_str)
    console.print(table)
    console.print()

    # Strategy rationale panel
    rationale_lines: list[str] = [
        _safe_text(rec.strategy_rationale),
        "",
        f"Entry: {_safe_text(rec.entry_criteria)}",
        f"Exit: {_safe_text(rec.exit_criteria)}",
    ]

    if rec.key_factors:
        rationale_lines.append("")
        rationale_lines.append("Key Factors:")
        for factor in rec.key_factors:
            rationale_lines.append(f"  - {_safe_text(factor)}")

    rationale_lines.append("")
    rationale_lines.append(f"Risk Assessment: {_safe_text(rec.risk_assessment)}")

    if rec.agent_agreement_score is not None and math.isfinite(rec.agent_agreement_score):
        rationale_lines.append(f"Agent Agreement: {rec.agent_agreement_score:.0%}")

    if rec.dissenting_desks:
        desk_names = ", ".join(d.value.title() for d in rec.dissenting_desks)
        rationale_lines.append(f"Dissenting Desks: {desk_names}")

    console.print(
        Panel(
            Text("\n".join(rationale_lines)),
            border_style=direction_style,
            title="RATIONALE",
            title_align="left",
        )
    )


def render_recommendation_batch_summary(
    results: list[tuple[str, RecommendationResult | None, str | None]],
) -> Table:
    """Render batch recommendation results as a compact summary table.

    Args:
        results: List of (ticker, recommendation_result_or_none, error_or_none) tuples.

    Returns:
        Rich Table with one row per ticker.
    """
    table = Table(title="Batch Recommendation Summary")
    table.add_column("Ticker", style="bold white", no_wrap=True)
    table.add_column("Direction", justify="center")
    table.add_column("Confidence", justify="right")
    table.add_column("Contract", justify="center")
    table.add_column("Fallback", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Status", justify="center")

    for ticker, result, error in results:
        if result is not None:
            rec = result.recommendation
            direction_style = _DIRECTION_STYLES.get(rec.direction.value, "")
            direction_text: Text | str = Text(rec.direction.value.upper(), style=direction_style)
            conf_str = f"{rec.confidence * 100:.0f}%" if math.isfinite(rec.confidence) else "--"
            contract_str = rec.recommended_contract[:25] if rec.recommended_contract else "--"
            fallback: Text | str = (
                Text("Yes", style="yellow") if result.is_fallback else Text("No", style="dim")
            )
            duration = f"{result.duration_ms / 1000:.1f}s"
            status: Text | str = Text("OK", style="bold green")
        else:
            direction_text = "--"
            conf_str = "--"
            contract_str = "--"
            fallback = "--"
            duration = "--"
            err_msg = (error or "Unknown error")[:40]
            status = Text(f"FAIL: {err_msg}", style="bold red")

        table.add_row(ticker, direction_text, conf_str, contract_str, fallback, duration, status)

    return table
