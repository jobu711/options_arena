"""Internal dataclasses and utilities for the debate system.

DebateDeps and DebateResult are @dataclass (not Pydantic) because RunUsage
is a plain dataclass — not Pydantic-serializable.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass

from pydantic_ai.usage import RunUsage

from options_arena.models import (
    AgentResponse,
    MarketContext,
    OptionContract,
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


# VERSION: v2.0
PROMPT_RULES_APPENDIX = """Confidence calibration (MUST follow these guidelines):
- 0.0-0.2: Extremely weak case, minimal data support
- 0.2-0.4: Weak case, some data but significant contradictions
- 0.4-0.6: Moderate case, mixed signals in the data
- 0.6-0.8: Strong case, most indicators confirm thesis
- 0.8-1.0: Very strong case, overwhelming data support

Data anchors:
- If COMPOSITE SCORE < 40: your confidence MUST NOT exceed 0.5
- If COMPOSITE SCORE > 70 and direction matches: confidence MUST be at least 0.4
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


@dataclass
class DebateResult:
    """Complete debate output returned by run_debate().

    Uses @dataclass because RunUsage is a plain dataclass, not Pydantic-serializable.
    Pydantic sub-models (AgentResponse, TradeThesis) are serialized individually for
    persistence.
    """

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


def _render_optional(label: str, value: float | None, fmt: str = ".1f") -> str | None:
    """Render a labeled value if non-None and finite, else None."""
    if value is not None and math.isfinite(value):
        return f"{label}: {value:{fmt}}"
    return None


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

    # Options-specific fields — omit when unavailable (0.0 = not computed)
    if ctx.iv_rank > 0.0:
        lines.append(f"IV RANK: {ctx.iv_rank:.1f}")
    if ctx.iv_percentile > 0.0:
        lines.append(f"IV PERCENTILE: {ctx.iv_percentile:.1f}")
    if ctx.put_call_ratio > 0.0:
        lines.append(f"PUT/CALL RATIO: {ctx.put_call_ratio:.2f}")

    # ATM IV 30D — only render when available (derived from first contract)
    if ctx.atm_iv_30d > 0.0:
        lines.append(f"ATM IV 30D: {ctx.atm_iv_30d:.1f}")

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
    combined = " ".join(texts).upper()
    cited = sum(1 for label in labels if label in combined)
    return cited / len(labels)
