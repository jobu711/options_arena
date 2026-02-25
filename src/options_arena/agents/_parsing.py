"""Internal dataclasses and utilities for the debate system.

DebateDeps and DebateResult are @dataclass (not Pydantic) because RunUsage
is a plain dataclass — not Pydantic-serializable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from pydantic_ai.usage import RunUsage

from options_arena.models import (
    AgentResponse,
    MarketContext,
    OptionContract,
    TickerScore,
    TradeThesis,
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
PROMPT_RULES_APPENDIX = """
Confidence calibration (MUST follow these guidelines):
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
- Every claim MUST cite at least one specific number from the context."""


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


@dataclass
class DebateDeps:
    """Injected into every agent via RunContext[DebateDeps].

    The orchestrator builds this with pre-fetched data. Agents never fetch data.
    """

    context: MarketContext
    ticker_score: TickerScore
    contracts: list[OptionContract]
    opponent_argument: str | None = None  # For bear (receives bull's text)
    bull_response: AgentResponse | None = None  # For risk agent
    bear_response: AgentResponse | None = None  # For risk agent


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


def render_context_block(ctx: MarketContext) -> str:
    """Render MarketContext as flat key-value text for agent consumption.

    Agents parse flat text better than JSON. Each line is a labeled value
    that agents can reference in their arguments.
    """
    return (
        f"TICKER: {ctx.ticker}\n"
        f"PRICE: ${ctx.current_price}\n"
        f"52W HIGH: ${ctx.price_52w_high}\n"
        f"52W LOW: ${ctx.price_52w_low}\n"
        f"RSI(14): {ctx.rsi_14:.1f}\n"
        f"MACD: {ctx.macd_signal.value}\n"
        f"IV RANK: {ctx.iv_rank:.1f}\n"
        f"IV PERCENTILE: {ctx.iv_percentile:.1f}\n"
        f"ATM IV 30D: {ctx.atm_iv_30d:.1f}\n"
        f"PUT/CALL RATIO: {ctx.put_call_ratio:.2f}\n"
        f"SECTOR: {ctx.sector}\n"
        f"TARGET STRIKE: ${ctx.target_strike}\n"
        f"TARGET DELTA: {ctx.target_delta:.2f}\n"
        f"DTE: {ctx.dte_target}\n"
        f"DIV YIELD: {ctx.dividend_yield:.2%}\n"
        f"EXERCISE: {ctx.exercise_style.value}"
    )
