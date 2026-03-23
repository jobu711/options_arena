"""Markdown export for debate results and recommendation results.

Pure functions that convert ``DebateResult`` and ``RecommendationResult``
into GitHub-flavored Markdown report strings. No I/O, no side effects.
"""

from __future__ import annotations

import datetime
import logging
import math
from decimal import Decimal
from typing import TYPE_CHECKING

from options_arena.models.constants import UNLIMITED_SENTINEL

if TYPE_CHECKING:
    from options_arena.agents._parsing import DebateResult
    from options_arena.models import (
        AgentResponse,
        ContrarianThesis,
        FlowThesis,
        FundamentalThesis,
        MarketContext,
        RiskAssessment,
        SpreadAnalysis,
        VolatilityThesis,
    )
    from options_arena.models.recommendation import (
        DomainAssessment,
        PositionRecommendation,
        RecommendationResult,
    )

logger = logging.getLogger(__name__)


def _render_agent_section(
    heading: str,
    response: AgentResponse,
    *,
    include_risks: bool = True,
) -> str:
    """Render a bull/bear/rebuttal agent section as Markdown.

    Args:
        heading: Section heading (e.g. "Bull Case", "Bear Case", "Bull Rebuttal").
        response: The agent's structured response.
        include_risks: Whether to render a "Risks Cited" subsection.

    Returns:
        Markdown string for the section.
    """
    lines: list[str] = [
        f"## {heading} (Confidence: {response.confidence:.0%})",
        "",
        response.argument,
        "",
    ]

    if response.key_points:
        lines.append("### Key Points")
        for point in response.key_points:
            lines.append(f"- {point}")
        lines.append("")

    if include_risks and response.risks_cited:
        lines.append("### Risks Cited")
        for risk in response.risks_cited:
            lines.append(f"- {risk}")
        lines.append("")

    return "\n".join(lines)


def _render_vol_section(vol: VolatilityThesis) -> str:
    """Render the volatility assessment section as Markdown.

    Args:
        vol: The volatility thesis from the vol agent.

    Returns:
        Markdown string for the volatility section.
    """
    lines: list[str] = [
        "## Volatility Assessment",
        "",
        (f"**IV Assessment**: {vol.iv_assessment.value} | **Confidence**: {vol.confidence:.0%}"),
        "",
        vol.strategy_rationale,
        "",
    ]

    if vol.key_vol_factors:
        lines.append("### Key Volatility Factors")
        for factor in vol.key_vol_factors:
            lines.append(f"- {factor}")
        lines.append("")

    return "\n".join(lines)


def _render_flow_section(flow: FlowThesis) -> str:
    """Render the flow analysis section as Markdown.

    Args:
        flow: The flow thesis from the flow agent.

    Returns:
        Markdown string for the flow section.
    """
    lines: list[str] = [
        f"## Flow Analysis (Confidence: {flow.confidence:.0%})",
        "",
        f"**Direction**: {flow.direction.value}",
        "",
        f"**GEX Interpretation**: {flow.gex_interpretation}",
        "",
        f"**Smart Money Signal**: {flow.smart_money_signal}",
        "",
        f"**OI Analysis**: {flow.oi_analysis}",
        "",
        f"**Volume Confirmation**: {flow.volume_confirmation}",
        "",
    ]

    if flow.key_flow_factors:
        lines.append("### Key Flow Factors")
        for factor in flow.key_flow_factors:
            lines.append(f"- {factor}")
        lines.append("")

    return "\n".join(lines)


def _render_fundamental_section(fund: FundamentalThesis) -> str:
    """Render the fundamental analysis section as Markdown.

    Args:
        fund: The fundamental thesis from the fundamental agent.

    Returns:
        Markdown string for the fundamental section.
    """
    lines: list[str] = [
        f"## Fundamental Analysis (Confidence: {fund.confidence:.0%})",
        "",
        f"**Direction**: {fund.direction.value}",
        "",
        f"**Catalyst Impact**: {fund.catalyst_impact.value}",
        "",
        f"**Earnings Assessment**: {fund.earnings_assessment}",
        "",
        f"**IV Crush Risk**: {fund.iv_crush_risk}",
        "",
    ]

    if fund.short_interest_analysis is not None:
        lines.append(f"**Short Interest Analysis**: {fund.short_interest_analysis}")
        lines.append("")

    if fund.dividend_impact is not None:
        lines.append(f"**Dividend Impact**: {fund.dividend_impact}")
        lines.append("")

    if fund.key_fundamental_factors:
        lines.append("### Key Fundamental Factors")
        for factor in fund.key_fundamental_factors:
            lines.append(f"- {factor}")
        lines.append("")

    return "\n".join(lines)


def _render_risk_section(risk: RiskAssessment) -> str:
    """Render the risk assessment section as Markdown.

    Args:
        risk: The expanded risk assessment from the risk agent.

    Returns:
        Markdown string for the risk assessment section.
    """
    lines: list[str] = [
        f"## Risk Assessment (Confidence: {risk.confidence:.0%})",
        "",
        f"**Risk Level**: {risk.risk_level.value}",
        "",
    ]

    if risk.pop_estimate is not None and math.isfinite(risk.pop_estimate):
        lines.append(f"**Probability of Profit**: {risk.pop_estimate:.0%}")
        lines.append("")

    lines.append(f"**Max Loss Estimate**: {risk.max_loss_estimate}")
    lines.append("")

    if risk.charm_decay_warning is not None:
        lines.append(f"**Charm Decay Warning**: {risk.charm_decay_warning}")
        lines.append("")

    if risk.key_risks:
        lines.append("### Key Risks")
        for risk_item in risk.key_risks:
            lines.append(f"- {risk_item}")
        lines.append("")

    if risk.risk_mitigants:
        lines.append("### Mitigants")
        for mitigant in risk.risk_mitigants:
            lines.append(f"- {mitigant}")
        lines.append("")

    if risk.recommended_position_size is not None:
        lines.append(f"**Position Size**: {risk.recommended_position_size}")
        lines.append("")

    return "\n".join(lines)


def _render_contrarian_section(contra: ContrarianThesis) -> str:
    """Render the contrarian challenge section as Markdown.

    Args:
        contra: The contrarian thesis from the contrarian agent.

    Returns:
        Markdown string for the contrarian challenge section.
    """
    lines: list[str] = [
        f"## Contrarian Challenge (Confidence: {contra.dissent_confidence:.0%})",
        "",
        f"**Dissent Direction**: {contra.dissent_direction.value}",
        "",
        f"**Primary Challenge**: {contra.primary_challenge}",
        "",
        f"**Consensus Weakness**: {contra.consensus_weakness}",
        "",
        f"**Alternative Scenario**: {contra.alternative_scenario}",
        "",
    ]

    if contra.overlooked_risks:
        lines.append("### Overlooked Risks")
        for risk in contra.overlooked_risks:
            lines.append(f"- {risk}")
        lines.append("")

    return "\n".join(lines)


def _render_spread_section(spread: SpreadAnalysis) -> str:
    """Render a spread strategy section as Markdown.

    Args:
        spread: The spread analysis to render.

    Returns:
        Markdown string for the spread strategy section.
    """
    lines: list[str] = [
        f"## Spread Strategy: {spread.spread.spread_type.value.upper()}",
        "",
        "| Leg | Side | Type | Strike | Expiration | Delta |",
        "|-----|------|------|--------|------------|-------|",
    ]

    for i, leg in enumerate(spread.spread.legs, 1):
        contract = leg.contract
        delta = f"{contract.greeks.delta:.3f}" if contract.greeks is not None else "--"
        lines.append(
            f"| {i} | {leg.side.value} | {contract.option_type.value} "
            f"| ${contract.strike} | {contract.expiration} | {delta} |"
        )

    max_profit_str = (
        "Unlimited" if str(spread.max_profit) == UNLIMITED_SENTINEL else f"${spread.max_profit}"
    )

    pop_str = f"{spread.pop_estimate:.1%}" if math.isfinite(spread.pop_estimate) else "N/A"
    rr_str = (
        f"{spread.risk_reward_ratio:.2f}"
        if spread.risk_reward_ratio is not None and math.isfinite(spread.risk_reward_ratio)
        else "N/A"
    )

    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Net Premium | ${spread.net_premium} |")
    lines.append(f"| Max Profit | {max_profit_str} |")
    lines.append(f"| Max Loss | ${spread.max_loss} |")
    lines.append(f"| PoP | {pop_str} |")
    lines.append(f"| Risk/Reward | {rr_str} |")
    lines.append("")

    return "\n".join(lines)


def _render_market_snapshot(ctx: MarketContext) -> str:
    """Render a Market Snapshot section from the persisted MarketContext.

    Args:
        ctx: The MarketContext snapshot from the debate result.

    Returns:
        Markdown string for the Market Snapshot section.
    """
    lines: list[str] = [
        "## Market Snapshot",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Price | ${ctx.current_price} |",
        f"| 52W High | ${ctx.price_52w_high} |",
        f"| 52W Low | ${ctx.price_52w_low} |",
        f"| Target Strike | ${ctx.target_strike} |",
        f"| DTE | {ctx.dte_target} |",
        f"| Target Delta | {ctx.target_delta:.2f} |",
        f"| Sector | {ctx.sector} |",
        f"| Dividend Yield | {ctx.dividend_yield:.2%} |",
    ]

    if ctx.iv_rank is not None and math.isfinite(ctx.iv_rank):
        lines.append(f"| IV Rank | {ctx.iv_rank:.1f} |")
    if ctx.iv_percentile is not None and math.isfinite(ctx.iv_percentile):
        lines.append(f"| IV Percentile | {ctx.iv_percentile:.1f} |")
    if ctx.contract_mid is not None:
        lines.append(f"| Contract Mid | ${ctx.contract_mid} |")

    lines.append("")
    return "\n".join(lines)


def export_debate_markdown(
    result: DebateResult,
    spread: SpreadAnalysis | None = None,
) -> str:
    """Convert a debate result into a Markdown report string.

    This is a pure function with no side effects. The caller is responsible
    for writing the returned string to a file or displaying it.

    Args:
        result: Complete debate output from ``run_debate()``.
        spread: Optional spread analysis to include in the report.

    Returns:
        A GitHub-flavored Markdown string containing the full report
        with header, market snapshot, agent sections, and verdict.
    """
    now_utc = datetime.datetime.now(datetime.UTC)
    date_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    duration_s = result.duration_ms / 1000
    model_name = result.bull_response.model_used
    fallback_str = "Yes" if result.is_fallback else "No"

    sections: list[str] = []

    # --- Header ---
    header_lines: list[str] = [
        f"# Options Arena Debate Report: {result.context.ticker}",
        "",
        (f"**Date**: {date_str} | **Duration**: {duration_s:.1f}s | **Model**: {model_name}"),
        f"**Fallback**: {fallback_str}",
        "",
    ]
    sections.append("\n".join(header_lines))

    # --- Market Snapshot (uses persisted MarketContext for real prices) ---
    if result.context is not None:
        sections.append(_render_market_snapshot(result.context))

    # 6-agent layout: Trend -> Flow -> Fundamental -> Volatility
    #                  -> Risk Assessment -> Contrarian Challenge -> Verdict
    sections.append(
        _render_agent_section("Trend Analysis", result.bull_response),
    )

    if result.flow_response is not None:
        sections.append(_render_flow_section(result.flow_response))

    if result.fundamental_response is not None:
        sections.append(_render_fundamental_section(result.fundamental_response))

    if result.vol_response is not None:
        sections.append(_render_vol_section(result.vol_response))

    if result.risk_response is not None:
        sections.append(_render_risk_section(result.risk_response))

    if result.contrarian_response is not None:
        sections.append(_render_contrarian_section(result.contrarian_response))

    # --- Spread Strategy (#521) ---
    if spread is not None:
        sections.append(_render_spread_section(spread))

    # --- Verdict ---
    thesis = result.thesis
    strategy_str = thesis.recommended_strategy.value if thesis.recommended_strategy else "None"
    verdict_lines: list[str] = [
        "## Verdict",
        "",
        (f"**Direction**: {thesis.direction.value} | **Confidence**: {thesis.confidence:.0%}"),
        f"**Strategy**: {strategy_str}",
    ]

    # Extended fields from 6-agent protocol
    from options_arena.models import ExtendedTradeThesis  # noqa: PLC0415

    if isinstance(thesis, ExtendedTradeThesis):
        if thesis.agent_agreement_score is not None and math.isfinite(
            thesis.agent_agreement_score
        ):
            verdict_lines.append(f"**Agent Agreement**: {thesis.agent_agreement_score:.0%}")
        if thesis.dissenting_agents:
            verdict_lines.append(f"**Dissenting**: {', '.join(thesis.dissenting_agents)}")

    verdict_lines.extend(
        [
            "",
            thesis.summary,
            "",
            "### Risk Assessment",
            "",
            thesis.risk_assessment,
        ]
    )

    # Extended: contrarian challenge section
    if isinstance(thesis, ExtendedTradeThesis) and thesis.contrarian_dissent:
        verdict_lines.extend(["", "### Contrarian Challenge", "", thesis.contrarian_dissent])

    # Extended: dimensional scores table
    if isinstance(thesis, ExtendedTradeThesis) and thesis.dimensional_scores is not None:
        dim = thesis.dimensional_scores
        dim_entries: list[tuple[str, float | None]] = [
            ("Trend", dim.trend),
            ("IV/Vol", dim.iv_vol),
            ("HV/Vol", dim.hv_vol),
            ("Flow", dim.flow),
            ("Microstructure", dim.microstructure),
            ("Fundamental", dim.fundamental),
            ("Regime", dim.regime),
            ("Risk", dim.risk),
        ]
        populated = [(name, val) for name, val in dim_entries if val is not None]
        if populated:
            verdict_lines.extend(["", "### Dimensional Scores", ""])
            verdict_lines.append("| Family | Score |")
            verdict_lines.append("|--------|-------|")
            for name, val in populated:
                val_str = f"{val:.1f}" if math.isfinite(val) else "--"
                verdict_lines.append(f"| {name} | {val_str} |")

    verdict_lines.append("")
    sections.append("\n".join(verdict_lines))

    return "\n".join(sections)


def _format_decimal(value: Decimal) -> str:
    """Format a Decimal to 2 decimal places without float conversion.

    Args:
        value: The Decimal value to format.

    Returns:
        String with 2 decimal places.
    """
    return f"{value:.2f}"


def _render_desk_specific_fields(assessment: DomainAssessment) -> list[str]:
    """Render desk-specific fields for a domain assessment as markdown lines.

    Inspects the concrete subclass type and renders any populated optional fields
    that are unique to that desk.

    Args:
        assessment: A concrete DomainAssessment subclass instance.

    Returns:
        List of markdown lines for desk-specific fields (may be empty).
    """
    from options_arena.models.recommendation import (  # noqa: PLC0415
        ContrarianAssessment,
        FlowAssessment,
        FundamentalAssessment,
        RiskDeskAssessment,
        TrendAssessment,
        VolatilityAssessment,
    )

    lines: list[str] = []

    if isinstance(assessment, TrendAssessment):
        if assessment.trend_strength is not None and math.isfinite(assessment.trend_strength):
            lines.append(f"**Trend Strength**: {assessment.trend_strength:.2f}")
            lines.append("")
        if assessment.momentum_signal is not None:
            lines.append(f"**Momentum Signal**: {assessment.momentum_signal}")
            lines.append("")

    elif isinstance(assessment, VolatilityAssessment):
        if assessment.iv_regime is not None:
            lines.append(f"**IV Regime**: {assessment.iv_regime.value}")
            lines.append("")
        if assessment.vol_skew_assessment is not None:
            lines.append(f"**Vol Skew**: {assessment.vol_skew_assessment}")
            lines.append("")
        if assessment.term_structure_shape is not None:
            lines.append(f"**Term Structure**: {assessment.term_structure_shape.value}")
            lines.append("")

    elif isinstance(assessment, FlowAssessment):
        if assessment.flow_bias is not None:
            lines.append(f"**Flow Bias**: {assessment.flow_bias}")
            lines.append("")
        if assessment.unusual_activity_noted:
            lines.append("**Unusual Activity**: Yes")
            lines.append("")

    elif isinstance(assessment, FundamentalAssessment):
        if assessment.valuation_signal is not None:
            lines.append(f"**Valuation Signal**: {assessment.valuation_signal.value}")
            lines.append("")
        if assessment.catalyst_timeline is not None:
            lines.append(f"**Catalyst Timeline**: {assessment.catalyst_timeline}")
            lines.append("")

    elif isinstance(assessment, RiskDeskAssessment):
        if assessment.max_position_pct is not None and math.isfinite(assessment.max_position_pct):
            lines.append(f"**Max Position**: {assessment.max_position_pct:.0%}")
            lines.append("")
        if assessment.hedging_suggestion is not None:
            lines.append(f"**Hedging Suggestion**: {assessment.hedging_suggestion}")
            lines.append("")
        if assessment.portfolio_correlation_note is not None:
            lines.append(f"**Portfolio Correlation**: {assessment.portfolio_correlation_note}")
            lines.append("")

    elif isinstance(assessment, ContrarianAssessment):
        if assessment.consensus_challenged is not None:
            lines.append(f"**Consensus Challenged**: {assessment.consensus_challenged}")
            lines.append("")
        if assessment.contrarian_thesis is not None:
            lines.append(f"**Contrarian Thesis**: {assessment.contrarian_thesis}")
            lines.append("")

    return lines


def _render_assessment_section(assessment: DomainAssessment) -> str:
    """Render a single domain assessment as a Markdown section.

    Args:
        assessment: A concrete DomainAssessment subclass instance.

    Returns:
        Markdown string for the assessment section.
    """
    desk_name = assessment.desk.value.title()
    lines: list[str] = [
        f"### {desk_name} (Confidence: {assessment.confidence:.0%})",
        "",
        f"**Direction**: {assessment.direction.value.title()}",
        "",
        assessment.summary,
        "",
    ]

    # Desk-specific fields
    desk_lines = _render_desk_specific_fields(assessment)
    if desk_lines:
        lines.extend(desk_lines)

    # Key factors
    if assessment.key_factors:
        lines.append("**Key Factors**")
        for factor in assessment.key_factors:
            lines.append(f"- {factor}")
        lines.append("")

    # Risks
    if assessment.risks:
        lines.append("**Risks**")
        for risk in assessment.risks:
            lines.append(f"- {risk}")
        lines.append("")

    return "\n".join(lines)


def _render_recommendation_section(rec: PositionRecommendation) -> str:
    """Render the position recommendation as a Markdown section.

    Decimal fields are formatted with 2 decimal places using f-string formatting
    on the Decimal value directly -- never converted to float.

    Args:
        rec: The position recommendation from synthesis.

    Returns:
        Markdown string for the recommendation section.
    """
    strategy_str = rec.recommended_strategy.value if rec.recommended_strategy else "None"

    lines: list[str] = [
        "## Position Recommendation",
        "",
        f"**Ticker**: {rec.ticker} | **Direction**: {rec.direction.value.title()} "
        f"| **Confidence**: {rec.confidence:.0%}",
        "",
        f"**Contract**: {rec.recommended_contract}",
        "",
        "| Detail | Value |",
        "|--------|-------|",
        f"| Entry Price | ${_format_decimal(rec.entry_price)} |",
    ]

    if rec.stop_loss is not None:
        lines.append(f"| Stop Loss | ${_format_decimal(rec.stop_loss)} |")
    if rec.take_profit is not None:
        lines.append(f"| Take Profit | ${_format_decimal(rec.take_profit)} |")

    lines.append(f"| Position Size | {rec.position_size_pct:.0%} |")
    lines.append(f"| Risk/Reward | {rec.risk_reward_ratio:.2f} |")
    lines.append(f"| Strategy | {strategy_str} |")
    lines.append("")

    lines.append(f"**Entry Criteria**: {rec.entry_criteria}")
    lines.append("")
    lines.append(f"**Exit Criteria**: {rec.exit_criteria}")
    lines.append("")
    lines.append(f"**Max Loss Estimate**: {rec.max_loss_estimate}")
    lines.append("")
    lines.append(f"**Position Rationale**: {rec.position_rationale}")
    lines.append("")
    lines.append(f"**Strategy Rationale**: {rec.strategy_rationale}")
    lines.append("")

    if rec.agent_agreement_score is not None and math.isfinite(rec.agent_agreement_score):
        lines.append(f"**Agent Agreement**: {rec.agent_agreement_score:.0%}")
        lines.append("")

    if rec.dissenting_desks:
        desk_names = ", ".join(d.value.title() for d in rec.dissenting_desks)
        lines.append(f"**Dissenting Desks**: {desk_names}")
        lines.append("")

    # Summary and risk
    lines.append("### Summary")
    lines.append("")
    lines.append(rec.summary)
    lines.append("")

    if rec.key_factors:
        lines.append("### Key Factors")
        for factor in rec.key_factors:
            lines.append(f"- {factor}")
        lines.append("")

    lines.append("### Risk Assessment")
    lines.append("")
    lines.append(rec.risk_assessment)
    lines.append("")

    return "\n".join(lines)


def export_recommendation_markdown(result: RecommendationResult) -> str:
    """Convert a recommendation result into a Markdown report string.

    This is a pure function with no side effects. The caller is responsible
    for writing the returned string to a file or displaying it.

    Args:
        result: Complete recommendation output from the unified agent pipeline.

    Returns:
        A GitHub-flavored Markdown string containing the full report
        with header, recommendation, and domain assessment sections.
    """
    now_utc = datetime.datetime.now(datetime.UTC)
    date_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")
    duration_s = result.duration_ms / 1000
    model_name = result.recommendation.model_used
    ticker = result.recommendation.ticker
    fallback_str = "Yes" if result.is_fallback else "No"

    sections: list[str] = []

    # --- Header ---
    header_lines: list[str] = [
        f"# Options Arena Recommendation Report: {ticker}",
        "",
        f"**Date**: {date_str} | **Duration**: {duration_s:.1f}s | **Model**: {model_name}",
        f"**Fallback**: {fallback_str}",
    ]

    if result.is_fallback:
        header_lines.append("")
        header_lines.append(
            "> **Data-Driven Fallback** -- AI agents were unavailable; "
            "this recommendation is based on quantitative data only."
        )

    header_lines.append("")
    sections.append("\n".join(header_lines))

    # --- Market Snapshot ---
    sections.append(_render_market_snapshot(result.context))

    # --- Position Recommendation ---
    sections.append(_render_recommendation_section(result.recommendation))

    # --- Domain Assessments ---
    if result.assessments:
        assessment_lines: list[str] = ["## Domain Assessments", ""]
        sections.append("\n".join(assessment_lines))

        for assessment in result.assessments:
            sections.append(_render_assessment_section(assessment))
    else:
        sections.append("## Domain Assessments\n\nNo assessments available.\n")

    return "\n".join(sections)
