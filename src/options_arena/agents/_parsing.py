"""Internal dataclasses and utilities for the debate system.

DebateDeps is a @dataclass (PydanticAI convention for agent deps).
DebateResult is a Pydantic BaseModel — enables FastAPI auto-serialization.
RunUsage is a plain dataclass but Pydantic v2-compatible (uses Field annotations).
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, ConfigDict
from pydantic_ai.usage import RunUsage

from options_arena.models import (
    AgentResponse,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    MarketContext,
    OptionContract,
    RiskAssessment,
    TickerScore,
    TradeThesis,
    VolatilityThesis,
)

logger = logging.getLogger(__name__)

# Regex patterns for stripping <think> tags from LLM output.
# Models like Llama sometimes emit reasoning traces wrapped in <think>...</think>
# that should not appear in user-facing text.
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_TAG_RE = re.compile(r"</?think>")

# Regime label lookup tables for human-readable rendering
_VOL_REGIME_LABELS: dict[float, str] = {0.0: "NORMAL", 1.0: "ELEVATED", 2.0: "CRISIS"}
_MARKET_REGIME_LABELS: dict[float, str] = {
    0.0: "CRISIS",
    1.0: "VOLATILE",
    2.0: "TRENDING",
    3.0: "MEAN_REVERTING",
}


def strip_think_tags(text: str) -> str:
    """Remove ``<think>...</think>`` blocks and any stray open/close tags.

    Returns the cleaned text with leading/trailing whitespace stripped.
    If stripping produces an empty string, returns the original text and logs
    a warning — empty output is less useful than output with think-tag remnants.
    """
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = _THINK_TAG_RE.sub("", cleaned)
    cleaned = cleaned.strip()
    if not cleaned and text.strip():
        logger.warning("strip_think_tags produced empty string, keeping original text")
        return text.strip()
    return cleaned


# VERSION: v3.0
PROMPT_RULES_APPENDIX = """Confidence calibration (MUST follow these guidelines):
- 0.0-0.2: Extremely weak case, minimal data support
- 0.2-0.4: Weak case, some data but significant contradictions
- 0.4-0.6: Moderate case, mixed signals in the data
- 0.6-0.8: Strong case, most indicators confirm thesis
- 0.8-1.0: Very strong case, overwhelming data support

Domain-specific calibration:
- Base your confidence on domain-specific indicators in your context
- Indicators outside your domain are intentionally excluded — focus on YOUR data
- It's OK to disagree with other agents — independent judgment is valued
- If RSI contradicts your thesis direction: reduce confidence by at least 0.1

Data citation rules (MANDATORY):
- When referencing data, use the EXACT label and value from the context block.
- WRONG: "The RSI is showing strength" or "momentum is bullish"
- RIGHT: "RSI(14): 65.3 is above the 50 midpoint, confirming bullish momentum"
- WRONG: "Volatility is elevated"
- RIGHT: "IV RANK: 85.0 places current IV in the top 15% of its 52-week range"
- Every claim MUST cite at least one specific number from the context.
- IV RANK ≠ IV PERCENTILE. Rank = position in 52-week range. Percentile = % of days IV was lower.

Greeks (when present):
- DELTA: directional exposure [-1,1]. Call>0 bullish, put<0 bearish.
- GAMMA: price-move sensitivity. Higher = more risk/reward near expiry.
- THETA: daily time decay. Negative = long position cost.
- VEGA: IV sensitivity. Positive vega profits from IV expansion."""


def build_cleaned_agent_response(output: AgentResponse) -> AgentResponse:
    """Strip ``<think>`` tags from all text fields of an ``AgentResponse``.

    Returns the original instance unchanged if no ``<think>`` tags are found.
    Constructs a new frozen instance with cleaned text fields otherwise.
    """
    fields = [
        output.argument,
        *output.key_points,
        *output.risks_cited,
        *output.contracts_referenced,
    ]
    if not any("<think>" in v or "</think>" in v for v in fields):
        return output
    return AgentResponse(
        agent_name=output.agent_name,
        direction=output.direction,
        confidence=output.confidence,
        argument=strip_think_tags(output.argument),
        key_points=[strip_think_tags(p) for p in output.key_points],
        risks_cited=[strip_think_tags(r) for r in output.risks_cited],
        contracts_referenced=[strip_think_tags(c) for c in output.contracts_referenced],
        model_used=output.model_used,
    )


def build_cleaned_trade_thesis(output: TradeThesis) -> TradeThesis:
    """Strip ``<think>`` tags from all text fields of a ``TradeThesis``.

    Returns the original instance unchanged if no ``<think>`` tags are found.
    Constructs a new frozen instance with cleaned text fields otherwise.
    """
    fields = [output.summary, output.risk_assessment, *output.key_factors]
    if not any("<think>" in v or "</think>" in v for v in fields):
        return output
    return TradeThesis(
        ticker=output.ticker,
        direction=output.direction,
        confidence=output.confidence,
        summary=strip_think_tags(output.summary),
        bull_score=output.bull_score,
        bear_score=output.bear_score,
        key_factors=[strip_think_tags(f) for f in output.key_factors],
        risk_assessment=strip_think_tags(output.risk_assessment),
        recommended_strategy=output.recommended_strategy,
    )


def build_cleaned_volatility_thesis(output: VolatilityThesis) -> VolatilityThesis:
    """Strip ``<think>`` tags from all text fields of a ``VolatilityThesis``.

    Returns the original instance unchanged if no ``<think>`` tags are found.
    Constructs a new frozen instance with cleaned text fields otherwise.
    """
    fields = [
        output.iv_rank_interpretation,
        output.strategy_rationale,
        *output.suggested_strikes,
        *output.key_vol_factors,
        output.model_used,
    ]
    if not any("<think>" in v or "</think>" in v for v in fields):
        return output
    return VolatilityThesis(
        iv_assessment=output.iv_assessment,
        iv_rank_interpretation=strip_think_tags(output.iv_rank_interpretation),
        confidence=output.confidence,
        recommended_strategy=output.recommended_strategy,
        strategy_rationale=strip_think_tags(output.strategy_rationale),
        target_iv_entry=output.target_iv_entry,
        target_iv_exit=output.target_iv_exit,
        suggested_strikes=[strip_think_tags(s) for s in output.suggested_strikes],
        key_vol_factors=[strip_think_tags(f) for f in output.key_vol_factors],
        model_used=strip_think_tags(output.model_used),
        direction=output.direction,
    )


def build_cleaned_flow_thesis(output: FlowThesis) -> FlowThesis:
    """Strip ``<think>`` tags from all text fields of a ``FlowThesis``.

    Returns the original instance unchanged if no ``<think>`` tags are found.
    Constructs a new frozen instance with cleaned text fields otherwise.
    """
    fields = [
        output.gex_interpretation,
        output.smart_money_signal,
        output.oi_analysis,
        output.volume_confirmation,
        *output.key_flow_factors,
        output.model_used,
    ]
    if not any("<think>" in v or "</think>" in v for v in fields):
        return output
    return FlowThesis(
        direction=output.direction,
        confidence=output.confidence,
        gex_interpretation=strip_think_tags(output.gex_interpretation),
        smart_money_signal=strip_think_tags(output.smart_money_signal),
        oi_analysis=strip_think_tags(output.oi_analysis),
        volume_confirmation=strip_think_tags(output.volume_confirmation),
        key_flow_factors=[strip_think_tags(f) for f in output.key_flow_factors],
        model_used=strip_think_tags(output.model_used),
    )


def build_cleaned_contrarian_thesis(output: ContrarianThesis) -> ContrarianThesis:
    """Strip ``<think>`` tags from all text fields of a ``ContrarianThesis``.

    Returns the original instance unchanged if no ``<think>`` tags are found.
    Constructs a new frozen instance with cleaned text fields otherwise.
    """
    fields = [
        output.primary_challenge,
        output.consensus_weakness,
        output.alternative_scenario,
        *output.overlooked_risks,
        output.model_used,
    ]
    if not any("<think>" in v or "</think>" in v for v in fields):
        return output
    return ContrarianThesis(
        dissent_direction=output.dissent_direction,
        dissent_confidence=output.dissent_confidence,
        primary_challenge=strip_think_tags(output.primary_challenge),
        overlooked_risks=[strip_think_tags(r) for r in output.overlooked_risks],
        consensus_weakness=strip_think_tags(output.consensus_weakness),
        alternative_scenario=strip_think_tags(output.alternative_scenario),
        model_used=strip_think_tags(output.model_used),
    )


def build_cleaned_risk_assessment(output: RiskAssessment) -> RiskAssessment:
    """Strip ``<think>`` tags from all text fields of a ``RiskAssessment``.

    Returns the original instance unchanged if no ``<think>`` tags are found.
    Constructs a new frozen instance with cleaned text fields otherwise.
    """
    fields = [
        output.max_loss_estimate,
        *output.key_risks,
        *output.risk_mitigants,
        output.model_used,
    ]
    optional_str_fields = [
        output.charm_decay_warning,
        output.spread_quality_assessment,
        output.recommended_position_size,
    ]
    all_text = [*fields, *(f for f in optional_str_fields if f is not None)]
    if not any("<think>" in v or "</think>" in v for v in all_text):
        return output
    return RiskAssessment(
        risk_level=output.risk_level,
        confidence=output.confidence,
        pop_estimate=output.pop_estimate,
        max_loss_estimate=strip_think_tags(output.max_loss_estimate),
        charm_decay_warning=(
            strip_think_tags(output.charm_decay_warning)
            if output.charm_decay_warning is not None
            else None
        ),
        spread_quality_assessment=(
            strip_think_tags(output.spread_quality_assessment)
            if output.spread_quality_assessment is not None
            else None
        ),
        key_risks=[strip_think_tags(r) for r in output.key_risks],
        risk_mitigants=[strip_think_tags(m) for m in output.risk_mitigants],
        recommended_position_size=(
            strip_think_tags(output.recommended_position_size)
            if output.recommended_position_size is not None
            else None
        ),
        model_used=strip_think_tags(output.model_used),
    )


def build_cleaned_fundamental_thesis(output: FundamentalThesis) -> FundamentalThesis:
    """Strip ``<think>`` tags from all text fields of a ``FundamentalThesis``.

    Returns the original instance unchanged if no ``<think>`` tags are found.
    Constructs a new frozen instance with cleaned text fields otherwise.
    """
    fields = [
        output.earnings_assessment,
        output.iv_crush_risk,
        *output.key_fundamental_factors,
        output.model_used,
    ]
    optional_str_fields = [output.short_interest_analysis, output.dividend_impact]
    all_text = [*fields, *(f for f in optional_str_fields if f is not None)]
    if not any("<think>" in v or "</think>" in v for v in all_text):
        return output
    return FundamentalThesis(
        direction=output.direction,
        confidence=output.confidence,
        catalyst_impact=output.catalyst_impact,
        earnings_assessment=strip_think_tags(output.earnings_assessment),
        iv_crush_risk=strip_think_tags(output.iv_crush_risk),
        short_interest_analysis=(
            strip_think_tags(output.short_interest_analysis)
            if output.short_interest_analysis is not None
            else None
        ),
        dividend_impact=(
            strip_think_tags(output.dividend_impact)
            if output.dividend_impact is not None
            else None
        ),
        key_fundamental_factors=[strip_think_tags(f) for f in output.key_fundamental_factors],
        model_used=strip_think_tags(output.model_used),
    )


@dataclass
class DebateDeps:
    """Injected into every agent via RunContext[DebateDeps].

    The orchestrator builds this with pre-fetched data. Agents never fetch data.
    """

    context: MarketContext
    ticker_score: TickerScore
    contracts: list[OptionContract]
    opponent_argument: str | None = None  # For bear (receives bull's text)
    bear_counter_argument: str | None = None  # For bull rebuttal (bear's key_points as text)
    bull_response: AgentResponse | None = None  # For risk agent
    bear_response: AgentResponse | None = None  # For risk agent
    bull_rebuttal: AgentResponse | None = None  # For risk agent (bull's rebuttal)
    vol_response: VolatilityThesis | None = None  # For risk agent (vol context)
    # --- 6-agent protocol fields (v2) ---
    trend_response: AgentResponse | None = None  # Phase 1 trend output
    volatility_thesis: VolatilityThesis | None = None  # Phase 1 vol output
    flow_thesis: FlowThesis | None = None  # Phase 1 flow output
    fundamental_thesis: FundamentalThesis | None = None  # Phase 1 fundamental output
    risk_assessment: RiskAssessment | None = None  # Phase 2 risk output
    all_prior_outputs: str | None = None  # Formatted text for contrarian (Phase 3)


class DebateResult(BaseModel):
    """Complete debate output returned by run_debate().

    Pydantic BaseModel with ``frozen=True`` for immutability. Enables FastAPI
    auto-serialization via ``model_dump_json()``. RunUsage is a plain dataclass
    but Pydantic v2-compatible (uses ``Field`` annotations internally).
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    context: MarketContext
    bull_response: AgentResponse
    bear_response: AgentResponse
    thesis: TradeThesis
    total_usage: RunUsage
    duration_ms: int
    is_fallback: bool
    bull_rebuttal: AgentResponse | None = None  # None when rebuttal disabled/skipped
    vol_response: VolatilityThesis | None = None  # None when vol agent disabled/skipped
    citation_density: float = 0.0  # fraction of context labels cited in agent text
    # --- v2 agent outputs (6-agent protocol) ---
    flow_response: FlowThesis | None = None
    fundamental_response: FundamentalThesis | None = None
    risk_v2_response: RiskAssessment | None = None
    contrarian_response: ContrarianThesis | None = None
    debate_protocol: str = "v2"


def _render_optional(label: str, value: float | None, fmt: str = ".1f") -> str | None:
    """Render a labeled value if non-None and finite, else None."""
    if value is not None and math.isfinite(value):
        return f"{label}: {value:{fmt}}"
    return None


def _render_regime_label(label: str, value: float | None, labels: dict[float, str]) -> str | None:
    """Render a regime field as a human-readable label, with numeric fallback."""
    if value is None or not math.isfinite(value):
        return None
    name = labels.get(value, f"{value:.0f}")
    return f"{label}: {name}"


def _format_dollars(value: float) -> str:
    """Format a dollar amount as $X.XB or $X.XM, with sign for negatives."""
    abs_val = abs(value)
    if abs_val >= 1e9:
        return f"${value / 1e9:.1f}B"
    if abs_val >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def _render_identity_block(ctx: MarketContext) -> list[str]:
    """Shared identity fields for all domain-specific renderers.

    Returns a list of lines containing TICKER, PRICE, 52W HIGH/LOW, SECTOR,
    DTE, TARGET STRIKE, TARGET DELTA, EXERCISE, DIV YIELD, and an earnings
    warning when next earnings is within 7 days.

    These fields are domain-neutral — every agent needs them regardless of
    its analytical specialization.
    """
    lines: list[str] = [
        f"TICKER: {ctx.ticker}",
        f"PRICE: ${ctx.current_price}",
        f"52W HIGH: ${ctx.price_52w_high}",
        f"52W LOW: ${ctx.price_52w_low}",
        f"SECTOR: {ctx.sector}",
        f"DTE: {ctx.dte_target}",
        f"TARGET STRIKE: ${ctx.target_strike}",
        f"TARGET DELTA: {ctx.target_delta:.2f}",
        f"EXERCISE: {ctx.exercise_style.value}",
        f"DIV YIELD: {ctx.dividend_yield:.2%}",
    ]

    # Earnings warning — appended when next earnings is within 7 days
    if ctx.next_earnings is not None:
        days_to_earnings = (ctx.next_earnings - date.today()).days
        if days_to_earnings >= 0:
            lines.append(f"NEXT EARNINGS: {ctx.next_earnings.isoformat()} ({days_to_earnings}d)")
            if days_to_earnings <= 7:
                lines.append(
                    f"WARNING: Earnings in {days_to_earnings} days. "
                    "IV crush risk is elevated. Factor this into your analysis."
                )

    return lines


def render_trend_context(ctx: MarketContext) -> str:
    """Render domain-specific context for the Trend agent.

    Includes the shared identity block plus trend-specific indicators:
    RSI(14), MACD, ADX, SMA ALIGNMENT, STOCHASTIC RSI, REL VOLUME,
    RSI DIVERGENCE, and dim_trend.

    Excludes COMPOSITE SCORE, DIRECTION, and DIRECTION CONFIDENCE —
    these are scan conclusions that cause agent correlation.
    """
    lines = _render_identity_block(ctx)

    lines.append("")
    lines.append("## Trend Indicators")

    # RSI is always present (has default 50.0)
    lines.append(f"RSI(14): {ctx.rsi_14:.1f}")

    # MACD is always present (required MacdSignal enum)
    lines.append(f"MACD: {ctx.macd_signal.value}")

    # Optional trend indicators
    for label, value in [
        ("ADX", ctx.adx),
        ("SMA ALIGNMENT", ctx.sma_alignment),
        ("STOCHASTIC RSI", ctx.stochastic_rsi),
        ("REL VOLUME", ctx.relative_volume),
        ("RSI DIVERGENCE", ctx.rsi_divergence),
    ]:
        rendered = _render_optional(label, value)
        if rendered is not None:
            lines.append(rendered)

    # Dimensional score
    dim_rendered = _render_optional("TREND", ctx.dim_trend, ".1f")
    if dim_rendered is not None:
        lines.append("")
        lines.append("## Signal Dimension")
        lines.append(dim_rendered)

    return "\n".join(lines)


def render_volatility_context(ctx: MarketContext) -> str:
    """Render domain-specific context for the Volatility agent.

    Includes the shared identity block plus volatility-specific indicators:
    IV RANK, IV PERCENTILE, ATM IV 30D, BB WIDTH, ATR%, VOL REGIME,
    IV-HV SPREAD, SKEW RATIO, VIX TERM STRUCTURE, EXPECTED MOVE,
    EXPECTED MOVE RATIO, VEGA, VOMMA, dim_iv_vol, dim_hv_vol.

    Excludes COMPOSITE SCORE, DIRECTION, and DIRECTION CONFIDENCE.
    """
    lines = _render_identity_block(ctx)

    lines.append("")
    lines.append("## Volatility Indicators")

    for label, value, fmt in [
        ("IV RANK", ctx.iv_rank, ".1f"),
        ("IV PERCENTILE", ctx.iv_percentile, ".1f"),
        ("ATM IV 30D", ctx.atm_iv_30d, ".1f"),
        ("BB WIDTH", ctx.bb_width, ".1f"),
        ("ATR %", ctx.atr_pct, ".1f"),
    ]:
        rendered = _render_optional(label, value, fmt)
        if rendered is not None:
            lines.append(rendered)

    # Volatility regime
    vol_regime_rendered = _render_regime_label("VOL REGIME", ctx.vol_regime, _VOL_REGIME_LABELS)
    if vol_regime_rendered is not None:
        lines.append(vol_regime_rendered)

    for label, value, fmt in [
        ("IV-HV SPREAD", ctx.iv_hv_spread, ".2f"),
        ("SKEW RATIO", ctx.skew_ratio, ".2f"),
        ("VIX TERM STRUCTURE", ctx.vix_term_structure, ".2f"),
        ("EXPECTED MOVE ($)", ctx.expected_move, ",.2f"),
        ("EXPECTED MOVE RATIO", ctx.expected_move_ratio, ".2f"),
    ]:
        rendered = _render_optional(label, value, fmt)
        if rendered is not None:
            lines.append(rendered)

    # Volatility-relevant Greeks
    for label, value, fmt in [
        ("VEGA", ctx.target_vega, ".4f"),
        ("VOMMA", ctx.target_vomma, ".6f"),
    ]:
        rendered = _render_optional(label, value, fmt)
        if rendered is not None:
            lines.append(rendered)

    # Dimensional scores
    dim_lines: list[str] = []
    for label, value in [
        ("IV VOLATILITY", ctx.dim_iv_vol),
        ("HV VOLATILITY", ctx.dim_hv_vol),
    ]:
        rendered = _render_optional(label, value, ".1f")
        if rendered is not None:
            dim_lines.append(rendered)
    if dim_lines:
        lines.append("")
        lines.append("## Signal Dimensions")
        lines.extend(dim_lines)

    return "\n".join(lines)


def render_flow_context(ctx: MarketContext) -> str:
    """Render domain-specific context for the Flow agent.

    Includes the shared identity block plus flow-specific indicators:
    PUT/CALL RATIO, MAX PAIN DISTANCE %, GEX, UNUSUAL ACTIVITY SCORE,
    NET CALL PREMIUM, NET PUT PREMIUM, OPTIONS PUT/CALL RATIO,
    REL VOLUME, dim_flow, dim_microstructure.

    Excludes COMPOSITE SCORE, DIRECTION, and DIRECTION CONFIDENCE.
    """
    lines = _render_identity_block(ctx)

    lines.append("")
    lines.append("## Flow Indicators")

    for label, value, fmt in [
        ("PUT/CALL RATIO", ctx.put_call_ratio, ".2f"),
        ("MAX PAIN DISTANCE %", ctx.max_pain_distance, ".1f"),
        ("GEX", ctx.gex, ",.0f"),
        ("UNUSUAL ACTIVITY SCORE", ctx.unusual_activity_score, ".1f"),
        ("NET CALL PREMIUM ($)", ctx.net_call_premium, ",.0f"),
        ("NET PUT PREMIUM ($)", ctx.net_put_premium, ",.0f"),
        ("OPTIONS PUT/CALL RATIO", ctx.options_put_call_ratio, ".2f"),
    ]:
        rendered = _render_optional(label, value, fmt)
        if rendered is not None:
            lines.append(rendered)

    # REL VOLUME is shared with trend but relevant to flow analysis
    rel_vol = _render_optional("REL VOLUME", ctx.relative_volume)
    if rel_vol is not None:
        lines.append(rel_vol)

    # Dimensional scores
    dim_lines: list[str] = []
    for label, value in [
        ("FLOW", ctx.dim_flow),
        ("MICROSTRUCTURE", ctx.dim_microstructure),
    ]:
        rendered = _render_optional(label, value, ".1f")
        if rendered is not None:
            dim_lines.append(rendered)
    if dim_lines:
        lines.append("")
        lines.append("## Signal Dimensions")
        lines.extend(dim_lines)

    return "\n".join(lines)


def render_fundamental_context(ctx: MarketContext) -> str:
    """Render domain-specific context for the Fundamental agent.

    Includes the shared identity block plus fundamental-specific indicators:
    P/E, FORWARD P/E, PEG, P/B, DEBT/EQUITY, REVENUE GROWTH, PROFIT MARGIN,
    SHORT RATIO, SHORT % OF FLOAT, analyst intelligence, insider activity,
    institutional ownership, news sentiment, dim_fundamental.

    Excludes COMPOSITE SCORE, DIRECTION, and DIRECTION CONFIDENCE.
    """
    lines = _render_identity_block(ctx)

    # --- Fundamental Profile ---
    fundamental_lines: list[str] = []
    for label, value, fmt in [
        ("P/E", ctx.pe_ratio, ".1f"),
        ("FORWARD P/E", ctx.forward_pe, ".1f"),
        ("PEG", ctx.peg_ratio, ".2f"),
        ("P/B", ctx.price_to_book, ".2f"),
        ("DEBT/EQUITY", ctx.debt_to_equity, ".2f"),
        ("REVENUE GROWTH", ctx.revenue_growth, ".1%"),
        ("PROFIT MARGIN", ctx.profit_margin, ".1%"),
        ("SHORT RATIO", ctx.short_ratio, ".2f"),
        ("SHORT % OF FLOAT", ctx.short_pct_of_float, ".1%"),
    ]:
        rendered = _render_optional(label, value, fmt)
        if rendered is not None:
            fundamental_lines.append(rendered)
    if fundamental_lines:
        lines.append("")
        lines.append("## Fundamental Profile")
        lines.extend(fundamental_lines)

    # --- Income Statement (TTM) — Financial Datasets enrichment ---
    income_lines: list[str] = []
    if ctx.fd_revenue is not None:
        income_lines.append(f"Revenue: {_format_dollars(ctx.fd_revenue)}")
    if ctx.fd_net_income is not None:
        income_lines.append(f"Net Income: {_format_dollars(ctx.fd_net_income)}")
    if ctx.fd_operating_income is not None:
        income_lines.append(f"Operating Income: {_format_dollars(ctx.fd_operating_income)}")
    if ctx.fd_eps_diluted is not None:
        income_lines.append(f"EPS (Diluted): ${ctx.fd_eps_diluted:.2f}")
    if ctx.fd_gross_margin is not None:
        income_lines.append(f"Gross Margin: {ctx.fd_gross_margin * 100:.1f}%")
    if ctx.fd_operating_margin is not None:
        income_lines.append(f"Operating Margin: {ctx.fd_operating_margin * 100:.1f}%")
    if ctx.fd_net_margin is not None:
        income_lines.append(f"Net Margin: {ctx.fd_net_margin * 100:.1f}%")
    if income_lines:
        lines.append("")
        lines.append("## Income Statement (TTM)")
        lines.extend(income_lines)

    # --- Balance Sheet — Financial Datasets enrichment ---
    balance_lines: list[str] = []
    if ctx.fd_total_debt is not None:
        balance_lines.append(f"Total Debt: {_format_dollars(ctx.fd_total_debt)}")
    if ctx.fd_total_cash is not None:
        balance_lines.append(f"Total Cash: {_format_dollars(ctx.fd_total_cash)}")
    if ctx.fd_total_assets is not None:
        balance_lines.append(f"Total Assets: {_format_dollars(ctx.fd_total_assets)}")
    if ctx.fd_current_ratio is not None:
        balance_lines.append(f"Current Ratio: {ctx.fd_current_ratio:.1f}x")
    if balance_lines:
        lines.append("")
        lines.append("## Balance Sheet")
        lines.extend(balance_lines)

    # --- Growth & Valuation — Financial Datasets enrichment ---
    growth_lines: list[str] = []
    if ctx.fd_revenue_growth is not None:
        growth_lines.append(f"Revenue Growth: {ctx.fd_revenue_growth * 100:.1f}%")
    if ctx.fd_earnings_growth is not None:
        growth_lines.append(f"Earnings Growth: {ctx.fd_earnings_growth * 100:.1f}%")
    if ctx.fd_ev_to_ebitda is not None:
        growth_lines.append(f"EV/EBITDA: {ctx.fd_ev_to_ebitda:.1f}x")
    if ctx.fd_free_cash_flow_yield is not None:
        growth_lines.append(f"FCF Yield: {ctx.fd_free_cash_flow_yield * 100:.1f}%")
    if growth_lines:
        lines.append("")
        lines.append("## Growth & Valuation")
        lines.extend(growth_lines)

    # --- Analyst Intelligence ---
    analyst_lines: list[str | None] = [
        _render_optional("ANALYST TARGET MEAN", ctx.analyst_target_mean, ",.2f"),
        _render_optional("ANALYST CONSENSUS", ctx.analyst_consensus_score, "+.2f"),
    ]
    if ctx.analyst_target_upside_pct is not None and math.isfinite(ctx.analyst_target_upside_pct):
        analyst_lines.insert(1, f"ANALYST TARGET UPSIDE: {ctx.analyst_target_upside_pct:+.1%}")
    if ctx.analyst_upgrades_30d is not None or ctx.analyst_downgrades_30d is not None:
        up = ctx.analyst_upgrades_30d if ctx.analyst_upgrades_30d is not None else 0
        down = ctx.analyst_downgrades_30d if ctx.analyst_downgrades_30d is not None else 0
        analyst_lines.append(f"UPGRADES/DOWNGRADES (30D): {up}/{down}")
    filtered_analyst = [ln for ln in analyst_lines if ln is not None]
    if filtered_analyst:
        lines.append("")
        lines.append("## Analyst Intelligence")
        lines.extend(filtered_analyst)

    # --- Insider Activity ---
    insider_lines: list[str | None] = []
    if ctx.insider_net_buys_90d is not None:
        insider_lines.append(f"INSIDER NET BUYS (90D): {ctx.insider_net_buys_90d:+d}")
    insider_lines.append(_render_optional("INSIDER BUY RATIO", ctx.insider_buy_ratio, ".2f"))
    filtered_insider = [ln for ln in insider_lines if ln is not None]
    if filtered_insider:
        lines.append("")
        lines.append("## Insider Activity")
        lines.extend(filtered_insider)

    # --- Institutional Ownership ---
    if ctx.institutional_pct is not None and math.isfinite(ctx.institutional_pct):
        lines.append("")
        lines.append("## Institutional Ownership")
        lines.append(f"INSTITUTIONAL OWNERSHIP: {ctx.institutional_pct:.1%}")

    # --- News Sentiment ---
    if ctx.news_sentiment is not None and math.isfinite(ctx.news_sentiment):
        lines.append("")
        lines.append("## News Sentiment")
        label = ctx.news_sentiment_label or "neutral"
        lines.append(f"AGGREGATE: {label.title()} ({ctx.news_sentiment:+.2f})")
        if ctx.recent_headlines:
            for headline in ctx.recent_headlines[:5]:
                lines.append(f'- "{headline}"')

    # Dimensional score
    dim_rendered = _render_optional("FUNDAMENTAL", ctx.dim_fundamental, ".1f")
    if dim_rendered is not None:
        lines.append("")
        lines.append("## Signal Dimension")
        lines.append(dim_rendered)

    return "\n".join(lines)


def render_context_block(ctx: MarketContext) -> str:
    """Render MarketContext as flat key-value text for agent consumption.

    Agents parse flat text better than JSON. Each line is a labeled value
    that agents can reference in their arguments. Optional fields (indicators,
    Greeks, contract mid) are omitted when None or non-finite.
    """
    # Static block — always present
    lines: list[str] = [
        f"TICKER: {ctx.ticker}",
        f"PRICE: ${ctx.current_price}",
        f"52W HIGH: ${ctx.price_52w_high}",
        f"52W LOW: ${ctx.price_52w_low}",
        f"RSI(14): {ctx.rsi_14:.1f}",
        f"MACD: {ctx.macd_signal.value}",
        f"SECTOR: {ctx.sector}",
        f"TARGET STRIKE: ${ctx.target_strike}",
        f"TARGET DELTA: {ctx.target_delta:.2f}",
        f"DTE: {ctx.dte_target}",
        f"DIV YIELD: {ctx.dividend_yield:.2%}",
        f"EXERCISE: {ctx.exercise_style.value}",
        # Scoring context — always present (have defaults)
        f"COMPOSITE SCORE: {ctx.composite_score:.1f}",
        f"DIRECTION: {ctx.direction_signal.value}",
    ]

    # Options-specific fields — omit when None or non-finite
    for label, value, fmt in [
        ("IV RANK", ctx.iv_rank, ".1f"),
        ("IV PERCENTILE", ctx.iv_percentile, ".1f"),
        ("PUT/CALL RATIO", ctx.put_call_ratio, ".2f"),
        ("MAX PAIN DISTANCE %", ctx.max_pain_distance, ".1f"),
        ("ATM IV 30D", ctx.atm_iv_30d, ".1f"),
    ]:
        rendered = _render_optional(label, value, fmt)
        if rendered is not None:
            lines.append(rendered)

    # Optional indicators — omit when None or non-finite
    for label, value in [
        ("ADX", ctx.adx),
        ("SMA ALIGNMENT", ctx.sma_alignment),
        ("BB WIDTH", ctx.bb_width),
        ("ATR %", ctx.atr_pct),
        ("STOCHASTIC RSI", ctx.stochastic_rsi),
        ("REL VOLUME", ctx.relative_volume),
    ]:
        rendered = _render_optional(label, value)
        if rendered is not None:
            lines.append(rendered)

    # Optional Greeks — omit when None or non-finite
    for label, value, fmt in [
        ("GAMMA", ctx.target_gamma, ".4f"),
        ("THETA", ctx.target_theta, ".4f"),
        ("VEGA", ctx.target_vega, ".4f"),
        ("RHO", ctx.target_rho, ".4f"),
    ]:
        rendered = _render_optional(label, value, fmt)
        if rendered is not None:
            lines.append(rendered)

    # Optional contract mid — Decimal, not float
    if ctx.contract_mid is not None:
        lines.append(f"CONTRACT MID: ${ctx.contract_mid}")

    # --- Fundamental Profile (OpenBB enrichment) ---
    fundamental_lines = [
        _render_optional("P/E", ctx.pe_ratio, ".1f"),
        _render_optional("FORWARD P/E", ctx.forward_pe, ".1f"),
        _render_optional("PEG", ctx.peg_ratio, ".2f"),
        _render_optional("P/B", ctx.price_to_book, ".2f"),
        _render_optional("DEBT/EQUITY", ctx.debt_to_equity, ".2f"),
        _render_optional("REVENUE GROWTH", ctx.revenue_growth, ".1%"),
        _render_optional("PROFIT MARGIN", ctx.profit_margin, ".1%"),
        _render_optional("SHORT RATIO", ctx.short_ratio, ".2f"),
        _render_optional("SHORT % OF FLOAT", ctx.short_pct_of_float, ".1%"),
    ]
    filtered_fund = [ln for ln in fundamental_lines if ln is not None]
    if filtered_fund:
        lines.append("")
        lines.append("## Fundamental Profile")
        lines.extend(filtered_fund)

    # --- Income Statement (TTM) — Financial Datasets enrichment ---
    fd_income_lines: list[str] = []
    if ctx.fd_revenue is not None:
        fd_income_lines.append(f"Revenue: {_format_dollars(ctx.fd_revenue)}")
    if ctx.fd_net_income is not None:
        fd_income_lines.append(f"Net Income: {_format_dollars(ctx.fd_net_income)}")
    if ctx.fd_operating_income is not None:
        fd_income_lines.append(f"Operating Income: {_format_dollars(ctx.fd_operating_income)}")
    if ctx.fd_eps_diluted is not None:
        fd_income_lines.append(f"EPS (Diluted): ${ctx.fd_eps_diluted:.2f}")
    if ctx.fd_gross_margin is not None:
        fd_income_lines.append(f"Gross Margin: {ctx.fd_gross_margin * 100:.1f}%")
    if ctx.fd_operating_margin is not None:
        fd_income_lines.append(f"Operating Margin: {ctx.fd_operating_margin * 100:.1f}%")
    if ctx.fd_net_margin is not None:
        fd_income_lines.append(f"Net Margin: {ctx.fd_net_margin * 100:.1f}%")
    if fd_income_lines:
        lines.append("")
        lines.append("## Income Statement (TTM)")
        lines.extend(fd_income_lines)

    # --- Balance Sheet — Financial Datasets enrichment ---
    fd_balance_lines: list[str] = []
    if ctx.fd_total_debt is not None:
        fd_balance_lines.append(f"Total Debt: {_format_dollars(ctx.fd_total_debt)}")
    if ctx.fd_total_cash is not None:
        fd_balance_lines.append(f"Total Cash: {_format_dollars(ctx.fd_total_cash)}")
    if ctx.fd_total_assets is not None:
        fd_balance_lines.append(f"Total Assets: {_format_dollars(ctx.fd_total_assets)}")
    if ctx.fd_current_ratio is not None:
        fd_balance_lines.append(f"Current Ratio: {ctx.fd_current_ratio:.1f}x")
    if fd_balance_lines:
        lines.append("")
        lines.append("## Balance Sheet")
        lines.extend(fd_balance_lines)

    # --- Growth & Valuation — Financial Datasets enrichment ---
    fd_growth_lines: list[str] = []
    if ctx.fd_revenue_growth is not None:
        fd_growth_lines.append(f"Revenue Growth: {ctx.fd_revenue_growth * 100:.1f}%")
    if ctx.fd_earnings_growth is not None:
        fd_growth_lines.append(f"Earnings Growth: {ctx.fd_earnings_growth * 100:.1f}%")
    if ctx.fd_ev_to_ebitda is not None:
        fd_growth_lines.append(f"EV/EBITDA: {ctx.fd_ev_to_ebitda:.1f}x")
    if ctx.fd_free_cash_flow_yield is not None:
        fd_growth_lines.append(f"FCF Yield: {ctx.fd_free_cash_flow_yield * 100:.1f}%")
    if fd_growth_lines:
        lines.append("")
        lines.append("## Growth & Valuation")
        lines.extend(fd_growth_lines)

    # --- Unusual Options Flow (OpenBB enrichment) ---
    flow_lines = [
        _render_optional("NET CALL PREMIUM ($)", ctx.net_call_premium, ",.0f"),
        _render_optional("NET PUT PREMIUM ($)", ctx.net_put_premium, ",.0f"),
        _render_optional("OPTIONS PUT/CALL RATIO", ctx.options_put_call_ratio, ".2f"),
    ]
    filtered_flow = [ln for ln in flow_lines if ln is not None]
    if filtered_flow:
        lines.append("")
        lines.append("## Unusual Options Flow")
        lines.extend(filtered_flow)

    # --- News Sentiment (OpenBB enrichment) ---
    if ctx.news_sentiment is not None and math.isfinite(ctx.news_sentiment):
        lines.append("")
        lines.append("## News Sentiment")
        label = ctx.news_sentiment_label or "neutral"
        lines.append(f"AGGREGATE: {label.title()} ({ctx.news_sentiment:+.2f})")
        if ctx.recent_headlines:
            for headline in ctx.recent_headlines[:5]:
                lines.append(f'- "{headline}"')

    # --- Arena Recon: Analyst Intelligence ---
    analyst_lines: list[str | None] = [
        _render_optional("ANALYST TARGET MEAN", ctx.analyst_target_mean, ",.2f"),
        # target_upside_pct inserted below if non-None
        _render_optional("ANALYST CONSENSUS", ctx.analyst_consensus_score, "+.2f"),
    ]
    # Add target upside specially formatted as percentage
    if ctx.analyst_target_upside_pct is not None and math.isfinite(ctx.analyst_target_upside_pct):
        analyst_lines.insert(1, f"ANALYST TARGET UPSIDE: {ctx.analyst_target_upside_pct:+.1%}")
    # Add upgrades/downgrades (int fields, not using _render_optional)
    if ctx.analyst_upgrades_30d is not None or ctx.analyst_downgrades_30d is not None:
        up = ctx.analyst_upgrades_30d if ctx.analyst_upgrades_30d is not None else 0
        down = ctx.analyst_downgrades_30d if ctx.analyst_downgrades_30d is not None else 0
        analyst_lines.append(f"UPGRADES/DOWNGRADES (30D): {up}/{down}")
    filtered_analyst = [ln for ln in analyst_lines if ln is not None]
    if filtered_analyst:
        lines.append("")
        lines.append("## Analyst Intelligence")
        lines.extend(filtered_analyst)

    # --- Arena Recon: Insider Activity ---
    insider_lines: list[str | None] = []
    if ctx.insider_net_buys_90d is not None:
        insider_lines.append(f"INSIDER NET BUYS (90D): {ctx.insider_net_buys_90d:+d}")
    insider_lines.append(_render_optional("INSIDER BUY RATIO", ctx.insider_buy_ratio, ".2f"))
    filtered_insider = [ln for ln in insider_lines if ln is not None]
    if filtered_insider:
        lines.append("")
        lines.append("## Insider Activity")
        lines.extend(filtered_insider)

    # --- Arena Recon: Institutional Ownership ---
    if ctx.institutional_pct is not None and math.isfinite(ctx.institutional_pct):
        lines.append("")
        lines.append("## Institutional Ownership")
        lines.append(f"INSTITUTIONAL OWNERSHIP: {ctx.institutional_pct:.1%}")

    # --- DSE: Signal Dimensions ---
    dim_lines = [
        _render_optional("TREND", ctx.dim_trend, ".1f"),
        _render_optional("IV VOLATILITY", ctx.dim_iv_vol, ".1f"),
        _render_optional("HV VOLATILITY", ctx.dim_hv_vol, ".1f"),
        _render_optional("FLOW", ctx.dim_flow, ".1f"),
        _render_optional("MICROSTRUCTURE", ctx.dim_microstructure, ".1f"),
        _render_optional("FUNDAMENTAL", ctx.dim_fundamental, ".1f"),
        _render_optional("REGIME", ctx.dim_regime, ".1f"),
        _render_optional("RISK", ctx.dim_risk, ".1f"),
        _render_optional("DIRECTION CONFIDENCE", ctx.direction_confidence, ".2f"),
    ]
    filtered_dim = [ln for ln in dim_lines if ln is not None]
    if filtered_dim:
        lines.append("")
        lines.append("## Signal Dimensions (0-100)")
        lines.extend(filtered_dim)

    # --- DSE: Volatility Regime ---
    vol_regime_lines = [
        _render_regime_label("VOL REGIME", ctx.vol_regime, _VOL_REGIME_LABELS),
        _render_optional("IV-HV SPREAD", ctx.iv_hv_spread, ".2f"),
        _render_optional("SKEW RATIO", ctx.skew_ratio, ".2f"),
        _render_optional("VIX TERM STRUCTURE", ctx.vix_term_structure, ".2f"),
        _render_optional("EXPECTED MOVE ($)", ctx.expected_move, ",.2f"),
        _render_optional("EXPECTED MOVE RATIO", ctx.expected_move_ratio, ".2f"),
    ]
    filtered_vol = [ln for ln in vol_regime_lines if ln is not None]
    if filtered_vol:
        lines.append("")
        lines.append("## Volatility Regime")
        lines.extend(filtered_vol)

    # --- DSE: Market & Flow Signals ---
    market_lines = [
        _render_regime_label("MARKET REGIME", ctx.market_regime, _MARKET_REGIME_LABELS),
        _render_optional("GEX", ctx.gex, ",.0f"),
        _render_optional("UNUSUAL ACTIVITY SCORE", ctx.unusual_activity_score, ".1f"),
        _render_optional("RSI DIVERGENCE", ctx.rsi_divergence, ".2f"),
    ]
    filtered_market = [ln for ln in market_lines if ln is not None]
    if filtered_market:
        lines.append("")
        lines.append("## Market & Flow Signals")
        lines.extend(filtered_market)

    # --- DSE: Second-Order Greeks ---
    greeks2_lines = [
        _render_optional("VANNA", ctx.target_vanna, ".6f"),
        _render_optional("CHARM", ctx.target_charm, ".6f"),
        _render_optional("VOMMA", ctx.target_vomma, ".6f"),
    ]
    filtered_greeks2 = [ln for ln in greeks2_lines if ln is not None]
    if filtered_greeks2:
        lines.append("")
        lines.append("## Second-Order Greeks")
        lines.extend(filtered_greeks2)

    # Earnings warning — appended when next earnings is within 7 days
    if ctx.next_earnings is not None:
        days_to_earnings = (ctx.next_earnings - date.today()).days
        if days_to_earnings >= 0:
            lines.append(f"NEXT EARNINGS: {ctx.next_earnings.isoformat()} ({days_to_earnings}d)")
            if days_to_earnings <= 7:
                lines.append(
                    f"WARNING: Earnings in {days_to_earnings} days. "
                    "IV crush risk is elevated. Factor this into your analysis."
                )

    # Data-availability note when no enrichment data is present
    if ctx.enrichment_ratio() == 0.0:
        lines.append("")
        lines.append(
            "Note: Enrichment data not available for this ticker. "
            "Analysis based on scan-derived indicators."
        )

    return "\n".join(lines)


# Regex to extract "LABEL:" patterns from context block (uppercase labels before colon)
_CONTEXT_LABEL_RE = re.compile(r"^([A-Z][A-Z0-9 /()%]+):", re.MULTILINE)


def compute_citation_density(context_block: str, *texts: str) -> float:
    """Compute fraction of context labels referenced in agent output text.

    Extracts ``LABEL:`` patterns from the context block (e.g., ``RSI(14):``,
    ``IV RANK:``) and counts how many appear in the combined agent text.
    Returns a float in [0.0, 1.0].
    """
    labels = _CONTEXT_LABEL_RE.findall(context_block)
    if not labels:
        return 0.0
    combined = " ".join(texts)
    cited = sum(
        1
        for label in labels
        if re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", combined, re.IGNORECASE)
    )
    return cited / len(labels)
