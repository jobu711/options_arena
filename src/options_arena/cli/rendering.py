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
from options_arena.models import (
    ContrarianThesis,
    ExtendedTradeThesis,
    FlowThesis,
    FundamentalThesis,
    RiskAssessment,
    TradeThesis,
    VolatilityThesis,
)
from options_arena.models.health import HealthStatus
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
        f"IV Rank Interpretation: {_safe_text(thesis.iv_rank_interpretation)}",
        "",
        _safe_text(thesis.strategy_rationale),
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
            lines.append(f"  * {_safe_text(factor)}")

    # Text() defaults to no markup — prevents agent text with [brackets] from crashing Rich
    return Panel(
        Text("\n".join(lines)),
        border_style="cyan",
        title="VOLATILITY ANALYSIS",
        title_align="left",
    )


def render_flow_panel(flow: FlowThesis) -> Panel:
    """Render Flow Agent output as a bright_magenta-bordered Rich Panel.

    Uses ``Text()`` constructor (defaults to no markup) to prevent bracket
    interpretation from agent-generated content.

    Args:
        flow: FlowThesis from the Flow Agent.

    Returns:
        Rich Panel with bright_magenta border showing flow analysis.
    """
    direction_style = _DIRECTION_STYLES.get(flow.direction.value, "")
    lines: list[str] = [
        f"Direction: {flow.direction.value.upper()}",
        f"Confidence: {flow.confidence * 100:.0f}%",
        "",
        f"GEX Interpretation: {_safe_text(flow.gex_interpretation)}",
        f"Smart Money Signal: {_safe_text(flow.smart_money_signal)}",
        f"OI Analysis: {_safe_text(flow.oi_analysis)}",
        f"Volume Confirmation: {_safe_text(flow.volume_confirmation)}",
    ]

    if flow.key_flow_factors:
        lines.append("")
        lines.append("Key Flow Factors:")
        for factor in flow.key_flow_factors:
            lines.append(f"  * {_safe_text(factor)}")

    text = Text("\n".join(lines))
    if direction_style:
        direction_label = f"Direction: {flow.direction.value.upper()}"
        text.stylize(direction_style, 0, len(direction_label))

    return Panel(
        text,
        border_style="bright_magenta",
        title="FLOW ANALYSIS",
        title_align="left",
    )


def render_fundamental_panel(fund: FundamentalThesis) -> Panel:
    """Render Fundamental Agent output as a bright_cyan-bordered Rich Panel.

    Uses ``Text()`` constructor (defaults to no markup) to prevent bracket
    interpretation from agent-generated content.

    Args:
        fund: FundamentalThesis from the Fundamental Agent.

    Returns:
        Rich Panel with bright_cyan border showing fundamental analysis.
    """
    direction_style = _DIRECTION_STYLES.get(fund.direction.value, "")
    lines: list[str] = [
        f"Direction: {fund.direction.value.upper()}",
        f"Confidence: {fund.confidence * 100:.0f}%",
        "",
        f"Catalyst Impact: {fund.catalyst_impact.value.upper()}",
        f"Earnings Assessment: {_safe_text(fund.earnings_assessment)}",
        f"IV Crush Risk: {_safe_text(fund.iv_crush_risk)}",
    ]

    if fund.short_interest_analysis is not None:
        lines.append(f"Short Interest: {_safe_text(fund.short_interest_analysis)}")

    if fund.dividend_impact is not None:
        lines.append(f"Dividend Impact: {_safe_text(fund.dividend_impact)}")

    if fund.key_fundamental_factors:
        lines.append("")
        lines.append("Key Fundamental Factors:")
        for factor in fund.key_fundamental_factors:
            lines.append(f"  * {_safe_text(factor)}")

    text = Text("\n".join(lines))
    if direction_style:
        direction_label = f"Direction: {fund.direction.value.upper()}"
        text.stylize(direction_style, 0, len(direction_label))

    return Panel(
        text,
        border_style="bright_cyan",
        title="FUNDAMENTAL ANALYSIS",
        title_align="left",
    )


def render_risk_panel(risk: RiskAssessment) -> Panel:
    """Render Risk Agent output as a bright_blue-bordered Rich Panel.

    Uses ``Text()`` constructor (defaults to no markup) to prevent bracket
    interpretation from agent-generated content.

    Args:
        risk: RiskAssessment from the Risk Agent.

    Returns:
        Rich Panel with bright_blue border showing risk assessment.
    """
    lines: list[str] = [
        f"Risk Level: {risk.risk_level.value.upper()}",
        f"Confidence: {risk.confidence * 100:.0f}%",
    ]

    if risk.pop_estimate is not None and math.isfinite(risk.pop_estimate):
        lines.append(f"Probability of Profit: {risk.pop_estimate * 100:.0f}%")

    lines.append(f"Max Loss Estimate: {_safe_text(risk.max_loss_estimate)}")

    if risk.charm_decay_warning is not None:
        lines.append(f"Charm Decay Warning: {_safe_text(risk.charm_decay_warning)}")

    if risk.spread_quality_assessment is not None:
        lines.append(f"Spread Quality: {_safe_text(risk.spread_quality_assessment)}")

    if risk.key_risks:
        lines.append("")
        lines.append("Key Risks:")
        for r in risk.key_risks:
            lines.append(f"  * {_safe_text(r)}")

    if risk.risk_mitigants:
        lines.append("")
        lines.append("Risk Mitigants:")
        for m in risk.risk_mitigants:
            lines.append(f"  * {_safe_text(m)}")

    if risk.recommended_position_size is not None:
        lines.append("")
        lines.append(f"Recommended Position Size: {_safe_text(risk.recommended_position_size)}")

    return Panel(
        Text("\n".join(lines)),
        border_style="bright_blue",
        title="RISK ASSESSMENT",
        title_align="left",
    )


def render_contrarian_panel(contra: ContrarianThesis) -> Panel:
    """Render Contrarian Agent output as a yellow-bordered Rich Panel.

    Uses ``Text()`` constructor (defaults to no markup) to prevent bracket
    interpretation from agent-generated content.

    Args:
        contra: ContrarianThesis from the Contrarian Agent.

    Returns:
        Rich Panel with yellow border showing contrarian analysis.
    """
    direction_style = _DIRECTION_STYLES.get(contra.dissent_direction.value, "")
    lines: list[str] = [
        f"Dissent Direction: {contra.dissent_direction.value.upper()}",
        f"Dissent Confidence: {contra.dissent_confidence * 100:.0f}%",
        "",
        f"Primary Challenge: {_safe_text(contra.primary_challenge)}",
        f"Consensus Weakness: {_safe_text(contra.consensus_weakness)}",
        "",
        f"Alternative Scenario: {_safe_text(contra.alternative_scenario)}",
    ]

    if contra.overlooked_risks:
        lines.append("")
        lines.append("Overlooked Risks:")
        for risk in contra.overlooked_risks:
            lines.append(f"  * {_safe_text(risk)}")

    text = Text("\n".join(lines))
    if direction_style:
        direction_label = f"Dissent Direction: {contra.dissent_direction.value.upper()}"
        text.stylize(direction_style, 0, len(direction_label))

    return Panel(
        text,
        border_style="yellow",
        title="CONTRARIAN ANALYSIS",
        title_align="left",
    )


def render_debate_panels(console: Console, result: DebateResult) -> None:
    """Render debate result as Rich panels for the 6-agent protocol.

    Agent argument text is rendered with ``markup=False`` to prevent Rich from
    interpreting ``[brackets]`` (e.g., ``[RSI]``, ``[AAPL]``) as style tags.

    Layout: Trend -> Flow -> Fundamental -> Volatility -> Risk -> Contrarian -> Verdict.

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

    # --- Trend panel (uses bull_response with TREND ANALYSIS title) ---
    trend = result.bull_response
    trend_body = _build_agent_panel_text(
        direction=trend.direction.value.upper(),
        confidence=trend.confidence,
        argument=trend.argument,
        key_points=trend.key_points,
        risks=trend.risks_cited,
    )
    console.print(
        Panel(
            trend_body,
            border_style="green",
            title="TREND ANALYSIS",
            title_align="left",
        )
    )
    console.print()

    # --- Flow panel (optional) ---
    if result.flow_response is not None:
        console.print(render_flow_panel(result.flow_response))
        console.print()

    # --- Fundamental panel (optional) ---
    if result.fundamental_response is not None:
        console.print(render_fundamental_panel(result.fundamental_response))
        console.print()

    # --- Volatility panel (optional) ---
    if result.vol_response is not None:
        console.print(render_volatility_panel(result.vol_response))
        console.print()

    # --- Risk panel (optional) ---
    if result.risk_response is not None:
        console.print(render_risk_panel(result.risk_response))
        console.print()

    # --- Contrarian panel (optional) ---
    if result.contrarian_response is not None:
        console.print(render_contrarian_panel(result.contrarian_response))
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
        _safe_text(argument),
    ]

    if key_points:
        lines.append("")
        lines.append("Key Points:")
        for point in key_points:
            lines.append(f"  * {_safe_text(point)}")

    if risks:
        lines.append("")
        lines.append("Risks:")
        for risk in risks:
            lines.append(f"  * {_safe_text(risk)}")

    # markup=False prevents [RSI], [AAPL], etc. from being parsed as Rich tags
    return Text("\n".join(lines))


def _build_verdict_panel_text(thesis: TradeThesis) -> Text:
    """Build Rich Text for the verdict panel.

    Detects ``ExtendedTradeThesis`` to render additional DSE fields:
    agent agreement, dissenting agents, contrarian challenge, and dimensional scores.

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
    ]

    # Extended fields from 6-agent protocol
    if isinstance(thesis, ExtendedTradeThesis):
        if thesis.agent_agreement_score is not None and math.isfinite(
            thesis.agent_agreement_score
        ):
            agents_total = thesis.agents_completed if thesis.agents_completed > 0 else 6
            agreeing = round(thesis.agent_agreement_score * agents_total)
            lines.append(
                f"Agreement: {thesis.agent_agreement_score:.0%} ({agreeing}/{agents_total} agents)"
            )
        if thesis.dissenting_agents:
            lines.append(f"Dissenting: {', '.join(thesis.dissenting_agents)}")

    lines.append("")
    lines.append(_safe_text(thesis.summary))

    if thesis.key_factors:
        lines.append("")
        lines.append("Key Factors:")
        for factor in thesis.key_factors:
            lines.append(f"  * {_safe_text(factor)}")

    lines.append("")
    lines.append("Risk Assessment:")
    lines.append(f"  {_safe_text(thesis.risk_assessment)}")

    if thesis.recommended_strategy is not None:
        lines.append("")
        lines.append(f"Recommended Strategy: {thesis.recommended_strategy.value.upper()}")

    # Extended: contrarian challenge section
    if isinstance(thesis, ExtendedTradeThesis) and thesis.contrarian_dissent:
        lines.append("")
        lines.append("Contrarian Challenge:")
        lines.append(f"  {_safe_text(thesis.contrarian_dissent)}")

    # Extended: dimensional scores mini-table
    if isinstance(thesis, ExtendedTradeThesis) and thesis.dimensional_scores is not None:
        dim = thesis.dimensional_scores
        dim_entries: list[tuple[str, float | None]] = [
            ("Trend", dim.trend),
            ("IV/Vol", dim.iv_vol),
            ("HV/Vol", dim.hv_vol),
            ("Flow", dim.flow),
            ("Micro", dim.microstructure),
            ("Fund", dim.fundamental),
            ("Regime", dim.regime),
            ("Risk", dim.risk),
        ]
        # Only render if at least one score is populated
        populated = [(name, val) for name, val in dim_entries if val is not None]
        if populated:
            lines.append("")
            lines.append("Dimensional Scores:")
            for name, val in populated:
                val_str = f"{val:.1f}" if math.isfinite(val) else "--"
                lines.append(f"  {name:<8} {val_str}")

    # Build text without markup to avoid bracket interpretation
    text = Text("\n".join(lines))

    # Apply direction color to the first line only
    if direction_style:
        direction_label = f"Direction: {thesis.direction.value.upper()}"
        text.stylize(direction_style, 0, len(direction_label))

    return text


def render_batch_summary_table(
    results: list[tuple[str, DebateResult | None, str | None]],
) -> Table:
    """Render batch debate results as a compact summary table.

    Args:
        results: List of (ticker, debate_result_or_none, error_or_none) tuples.

    Returns:
        Rich Table with one row per ticker.
    """
    table = Table(title="Batch Debate Summary")
    table.add_column("Ticker", style="bold white", no_wrap=True)
    table.add_column("Direction", justify="center")
    table.add_column("Confidence", justify="right")
    table.add_column("Strategy", justify="center")
    table.add_column("Fallback", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Status", justify="center")

    for ticker, result, error in results:
        if result is not None:
            thesis = result.thesis
            direction_style = _DIRECTION_STYLES.get(thesis.direction.value, "")
            direction_text: Text | str = Text(
                thesis.direction.value.upper(), style=direction_style
            )
            conf_str = (
                f"{thesis.confidence * 100:.0f}%" if math.isfinite(thesis.confidence) else "--"
            )
            strategy: str = (
                thesis.recommended_strategy.value.upper()
                if thesis.recommended_strategy is not None
                else "--"
            )
            fallback: Text | str = (
                Text("Yes", style="yellow") if result.is_fallback else Text("No", style="dim")
            )
            duration = f"{result.duration_ms / 1000:.1f}s"
            status: Text | str = Text("OK", style="bold green")
        else:
            direction_text = "--"
            conf_str = "--"
            strategy = "--"
            fallback = "--"
            duration = "--"
            # Truncate error to ~40 chars
            err_msg = (error or "Unknown error")[:40]
            status = Text(f"FAIL: {err_msg}", style="bold red")

        table.add_row(ticker, direction_text, conf_str, strategy, fallback, duration, status)

    return table


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
