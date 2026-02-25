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
        f"IV RANK: {ctx.iv_rank:.1f}",
        f"IV PERCENTILE: {ctx.iv_percentile:.1f}",
        f"ATM IV 30D: {ctx.atm_iv_30d:.1f}",
        f"PUT/CALL RATIO: {ctx.put_call_ratio:.2f}",
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
