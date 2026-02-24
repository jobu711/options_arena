"""Orchestrator for the Options Arena AI debate system.

Coordinates bull, bear, and risk agents sequentially, accumulates token usage,
and returns a ``DebateResult``. On ANY failure (connection error, timeout, invalid
LLM output, etc.), returns a data-driven fallback — ``run_debate()`` never raises.

Architecture rules:
- Agents run SEQUENTIALLY (bull -> bear -> risk). Ollama is single-threaded.
- Every ``agent.run()`` is wrapped in ``asyncio.wait_for(timeout=...)``.
- The orchestrator does NOT fetch data — all inputs are pre-fetched by the caller.
- ``time.monotonic()`` for duration measurement, never ``time.time()``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

import httpx
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateDeps, DebateResult, render_context_block
from options_arena.agents.bear import bear_agent
from options_arena.agents.bull import bull_agent
from options_arena.agents.model_config import build_ollama_model
from options_arena.agents.risk import risk_agent
from options_arena.data.repository import Repository
from options_arena.models import (
    AgentResponse,
    DebateConfig,
    ExerciseStyle,
    MacdSignal,
    MarketContext,
    OptionContract,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
    TradeThesis,
)

logger = logging.getLogger(__name__)


def build_market_context(
    ticker_score: TickerScore,
    quote: Quote,
    ticker_info: TickerInfo,
    contracts: list[OptionContract],
) -> MarketContext:
    """Map scan pipeline output to ``MarketContext`` for agent consumption.

    Uses safe defaults for ``None`` values — ``MarketContext`` requires all float
    fields to be actual floats. Options-specific indicators (``iv_rank``,
    ``iv_percentile``, ``put_call_ratio``) may be ``None`` on ``TickerScore.signals``.

    Parameters
    ----------
    ticker_score
        Scored ticker from the scan pipeline with indicator signals.
    quote
        Real-time price snapshot.
    ticker_info
        Fundamental data including dividend yield and 52-week range.
    contracts
        Recommended option contracts (may be empty).

    Returns
    -------
    MarketContext
        Flat snapshot of ticker state for agent consumption.
    """
    signals = ticker_score.signals

    # Derive MACD signal from direction heuristic — no raw MACD data in scan signals
    macd_signal = _derive_macd_signal(ticker_score.direction)

    # Contract-derived fields with safe defaults
    first_contract = contracts[0] if contracts else None
    dte_target = first_contract.dte if first_contract is not None else 45
    target_strike = first_contract.strike if first_contract is not None else quote.price
    target_delta: float
    if first_contract is not None and first_contract.greeks is not None:
        target_delta = first_contract.greeks.delta
    else:
        target_delta = 0.35

    return MarketContext(
        ticker=ticker_score.ticker,
        current_price=quote.price,
        price_52w_high=ticker_info.fifty_two_week_high,
        price_52w_low=ticker_info.fifty_two_week_low,
        iv_rank=signals.iv_rank if signals.iv_rank is not None else 0.0,
        iv_percentile=signals.iv_percentile if signals.iv_percentile is not None else 0.0,
        atm_iv_30d=0.0,  # Not available in scan data
        rsi_14=signals.rsi if signals.rsi is not None else 50.0,
        macd_signal=macd_signal,
        put_call_ratio=(signals.put_call_ratio if signals.put_call_ratio is not None else 0.0),
        next_earnings=None,
        dte_target=dte_target,
        target_strike=target_strike,
        target_delta=target_delta,
        sector=ticker_info.sector,
        dividend_yield=ticker_info.dividend_yield,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime.now(UTC),
    )


def _derive_macd_signal(direction: SignalDirection) -> MacdSignal:
    """Derive a MACD signal from the scan pipeline direction.

    The scan pipeline does not produce a raw MACD crossover signal.
    We approximate from the overall direction classification.
    """
    if direction == SignalDirection.BULLISH:
        return MacdSignal.BULLISH_CROSSOVER
    if direction == SignalDirection.BEARISH:
        return MacdSignal.BEARISH_CROSSOVER
    return MacdSignal.NEUTRAL


async def run_debate(
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    quote: Quote,
    ticker_info: TickerInfo,
    config: DebateConfig,
    repository: Repository | None = None,
) -> DebateResult:
    """Run AI debate on a ticker. On ANY failure, returns data-driven fallback -- never raises.

    Three agents run sequentially:
    1. Bull agent argues the bullish case.
    2. Bear agent receives the bull's argument and counters it.
    3. Risk agent weighs both arguments and produces a ``TradeThesis``.

    Parameters
    ----------
    ticker_score
        Scored ticker from the scan pipeline.
    contracts
        Recommended option contracts for this ticker.
    quote
        Real-time price snapshot.
    ticker_info
        Fundamental data (sector, dividend yield, 52-week range).
    config
        Debate configuration (Ollama host, model, timeouts).
    repository
        Optional persistence layer. If provided, debate results are saved.

    Returns
    -------
    DebateResult
        Complete debate output. ``is_fallback=True`` if AI debate failed.
    """
    start_time = time.monotonic()
    context = build_market_context(ticker_score, quote, ticker_info, contracts)

    try:
        result = await asyncio.wait_for(
            _run_agents(context, ticker_score, contracts, config, start_time),
            timeout=config.max_total_duration,
        )
    except httpx.ConnectError as e:
        logger.warning(
            "Ollama not reachable for %s (%s: %s), using data-driven fallback",
            context.ticker,
            type(e).__name__,
            e,
        )
        result = _build_fallback_result(context, ticker_score, contracts, config, start_time)
    except TimeoutError as e:
        logger.warning(
            "Debate timed out for %s (%s: %s), using data-driven fallback",
            context.ticker,
            type(e).__name__,
            e,
        )
        result = _build_fallback_result(context, ticker_score, contracts, config, start_time)
    except UnexpectedModelBehavior as e:
        logger.warning(
            "LLM returned invalid output for %s after retries (%s: %s), "
            "using data-driven fallback",
            context.ticker,
            type(e).__name__,
            e,
        )
        result = _build_fallback_result(context, ticker_score, contracts, config, start_time)
    except Exception as e:
        logger.warning(
            "Debate failed for %s (%s: %s), using data-driven fallback",
            context.ticker,
            type(e).__name__,
            e,
        )
        result = _build_fallback_result(context, ticker_score, contracts, config, start_time)

    # Persist result (never crash on persistence failure)
    if repository is not None:
        await _persist_result(result, ticker_score, config, repository)

    return result


async def _run_agents(
    context: MarketContext,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    config: DebateConfig,
    start_time: float,
) -> DebateResult:
    """Run all three agents sequentially and return a DebateResult.

    Raises on any agent failure — the caller (``run_debate``) catches and falls back.
    """
    model = build_ollama_model(config)
    context_text = render_context_block(context)

    # --- Bull agent ---
    logger.info("Running bull agent for %s", context.ticker)
    bull_deps = DebateDeps(
        context=context,
        ticker_score=ticker_score,
        contracts=contracts,
    )
    bull_result = await asyncio.wait_for(
        bull_agent.run(
            f"Analyze {context.ticker} for a bullish options position.\n\n{context_text}",
            model=model,
            deps=bull_deps,
        ),
        timeout=config.ollama_timeout,
    )
    bull_output: AgentResponse = bull_result.output
    logger.info(
        "Bull agent complete for %s: confidence=%.2f",
        context.ticker,
        bull_output.confidence,
    )

    # --- Bear agent ---
    logger.info("Running bear agent for %s", context.ticker)
    bear_deps = DebateDeps(
        context=context,
        ticker_score=ticker_score,
        contracts=contracts,
        opponent_argument=bull_output.argument,
    )
    bear_result = await asyncio.wait_for(
        bear_agent.run(
            f"Counter the bullish case for {context.ticker}.\n\n{context_text}",
            model=model,
            deps=bear_deps,
        ),
        timeout=config.ollama_timeout,
    )
    bear_output: AgentResponse = bear_result.output
    logger.info(
        "Bear agent complete for %s: confidence=%.2f",
        context.ticker,
        bear_output.confidence,
    )

    # --- Risk agent ---
    logger.info("Running risk agent for %s", context.ticker)
    risk_deps = DebateDeps(
        context=context,
        ticker_score=ticker_score,
        contracts=contracts,
        bull_response=bull_output,
        bear_response=bear_output,
    )
    risk_result = await asyncio.wait_for(
        risk_agent.run(
            f"Adjudicate the debate for {context.ticker} and produce a trade thesis.\n\n"
            f"{context_text}",
            model=model,
            deps=risk_deps,
        ),
        timeout=config.ollama_timeout,
    )
    thesis: TradeThesis = risk_result.output
    logger.info(
        "Risk agent complete for %s: direction=%s, confidence=%.2f",
        context.ticker,
        thesis.direction.value,
        thesis.confidence,
    )

    # Accumulate usage across all three agents
    total_usage = bull_result.usage() + bear_result.usage() + risk_result.usage()
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    logger.info(
        "Debate complete for %s in %dms (tokens: in=%d, out=%d)",
        context.ticker,
        elapsed_ms,
        total_usage.input_tokens,
        total_usage.output_tokens,
    )

    return DebateResult(
        context=context,
        bull_response=bull_output,
        bear_response=bear_output,
        thesis=thesis,
        total_usage=total_usage,
        duration_ms=elapsed_ms,
        is_fallback=False,
    )


def _build_fallback_result(
    context: MarketContext,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    config: DebateConfig,
    start_time: float,
) -> DebateResult:
    """Build a data-driven fallback result when AI debate fails.

    Synthesizes ``AgentResponse`` for bull and bear from quantitative data,
    and a ``TradeThesis`` from the composite score and direction.
    """
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # Gather top non-None indicator signals for key_points
    key_points = _extract_top_signals(ticker_score)

    # Contract descriptions for contracts_referenced
    contract_refs = _format_contract_refs(contracts)

    # --- Bull fallback ---
    bull_confidence = min(ticker_score.composite_score / 100.0 * 0.3, 0.3)
    bull_response = AgentResponse(
        agent_name="bull",
        direction=ticker_score.direction,
        confidence=bull_confidence,
        argument=(
            f"Data-driven analysis for {context.ticker}. "
            f"Composite score: {ticker_score.composite_score:.1f}/100. "
            f"Signal direction: {ticker_score.direction.value}. "
            f"RSI: {context.rsi_14:.1f}."
        ),
        key_points=key_points[:3] if key_points else ["Composite score available"],
        risks_cited=["AI analysis unavailable -- limited qualitative assessment"],
        contracts_referenced=contract_refs[:3],
        model_used="data-driven-fallback",
    )

    # --- Bear fallback ---
    bear_direction = _opposite_direction(ticker_score.direction)
    bear_confidence = min((100.0 - ticker_score.composite_score) / 100.0 * 0.3, 0.3)
    bear_response = AgentResponse(
        agent_name="bear",
        direction=bear_direction,
        confidence=bear_confidence,
        argument=(
            f"Data-driven bearish assessment for {context.ticker}. "
            f"Composite score: {ticker_score.composite_score:.1f}/100. "
            f"Inverse signal strength: {100.0 - ticker_score.composite_score:.1f}/100."
        ),
        key_points=key_points[:3] if key_points else ["Inverse composite score available"],
        risks_cited=["AI analysis unavailable -- limited qualitative assessment"],
        contracts_referenced=contract_refs[:3],
        model_used="data-driven-fallback",
    )

    # --- Thesis fallback ---
    thesis = TradeThesis(
        ticker=context.ticker,
        direction=ticker_score.direction,
        confidence=config.fallback_confidence,
        summary=(
            f"Data-driven analysis (AI unavailable). Based on composite score "
            f"{ticker_score.composite_score:.1f}/100, {ticker_score.direction.value} signal."
        ),
        bull_score=ticker_score.composite_score / 10.0,
        bear_score=(100.0 - ticker_score.composite_score) / 10.0,
        key_factors=key_points[:5] if key_points else ["Composite score only"],
        risk_assessment=(
            "Limited analysis -- AI debate unavailable. Exercise additional caution."
        ),
        recommended_strategy=None,
    )

    logger.info(
        "Data-driven fallback for %s: direction=%s, confidence=%.2f, duration=%dms",
        context.ticker,
        thesis.direction.value,
        thesis.confidence,
        elapsed_ms,
    )

    return DebateResult(
        context=context,
        bull_response=bull_response,
        bear_response=bear_response,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=elapsed_ms,
        is_fallback=True,
    )


def _extract_top_signals(ticker_score: TickerScore) -> list[str]:
    """Extract the top non-None indicator signals as human-readable strings."""
    signals = ticker_score.signals
    items: list[str] = []

    # Map field names to readable labels
    signal_labels: list[tuple[str, str]] = [
        ("rsi", "RSI"),
        ("adx", "ADX"),
        ("sma_alignment", "SMA Alignment"),
        ("bb_width", "Bollinger Band Width"),
        ("atr_pct", "ATR %"),
        ("obv", "OBV"),
        ("relative_volume", "Relative Volume"),
        ("stochastic_rsi", "Stochastic RSI"),
        ("supertrend", "SuperTrend"),
        ("roc", "Rate of Change"),
        ("keltner_width", "Keltner Width"),
        ("vwap_deviation", "VWAP Deviation"),
        ("iv_rank", "IV Rank"),
        ("iv_percentile", "IV Percentile"),
        ("put_call_ratio", "Put/Call Ratio"),
        ("williams_r", "Williams %R"),
        ("ad", "Accumulation/Distribution"),
        ("max_pain_distance", "Max Pain Distance"),
    ]

    for field_name, label in signal_labels:
        value = getattr(signals, field_name, None)
        if value is not None:
            items.append(f"{label}: {value:.1f}")
        if len(items) >= 5:
            break

    return items


def _format_contract_refs(contracts: list[OptionContract]) -> list[str]:
    """Format option contracts as human-readable reference strings."""
    refs: list[str] = []
    for contract in contracts[:3]:
        strike_str = f"${contract.strike}"
        type_str = contract.option_type.value.upper()
        expiry_str = contract.expiration.isoformat()
        refs.append(f"{contract.ticker} {strike_str} {type_str} {expiry_str}")
    return refs


def _opposite_direction(direction: SignalDirection) -> SignalDirection:
    """Return the opposite direction, or NEUTRAL if NEUTRAL."""
    if direction == SignalDirection.BULLISH:
        return SignalDirection.BEARISH
    if direction == SignalDirection.BEARISH:
        return SignalDirection.BULLISH
    return SignalDirection.NEUTRAL


async def _persist_result(
    result: DebateResult,
    ticker_score: TickerScore,
    config: DebateConfig,
    repository: Repository,
) -> None:
    """Persist debate result to the database. Never raises -- logs on failure."""
    try:
        total_tokens = result.total_usage.input_tokens + result.total_usage.output_tokens
        await repository.save_debate(
            scan_run_id=ticker_score.scan_run_id or 0,
            ticker=result.context.ticker,
            bull_json=result.bull_response.model_dump_json(),
            bear_json=result.bear_response.model_dump_json(),
            risk_json=None,  # Risk output is TradeThesis, stored in verdict_json
            verdict_json=result.thesis.model_dump_json(),
            total_tokens=total_tokens,
            model_name=config.ollama_model,
            duration_ms=result.duration_ms,
            is_fallback=result.is_fallback,
        )
        logger.debug(
            "Persisted debate for %s (tokens=%d, fallback=%s)",
            result.context.ticker,
            total_tokens,
            result.is_fallback,
        )
    except Exception:
        logger.warning(
            "Failed to persist debate result for %s",
            result.context.ticker,
            exc_info=True,
        )
