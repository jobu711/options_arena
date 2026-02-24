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
