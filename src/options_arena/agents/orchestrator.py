"""Orchestrator for the Options Arena AI debate system.

Coordinates bull, bear, volatility (optional), and risk agents via Groq cloud API,
accumulates token usage, and returns a ``DebateResult``. On ANY failure
(connection error, timeout, invalid LLM output, etc.), returns a data-driven
fallback — ``run_debate()`` never raises.

Architecture rules:
- Bull and bear run sequentially. Rebuttal + volatility can run in parallel.
- Every ``agent.run()`` is wrapped in ``asyncio.wait_for(timeout=...)``.
- The orchestrator does NOT fetch data — all inputs are pre-fetched by the caller.
- ``time.monotonic()`` for duration measurement, never ``time.time()``.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

import httpx
from pydantic_ai import AgentRunResult
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import (
    DebateDeps,
    DebateResult,
    compute_citation_density,
    render_context_block,
)
from options_arena.agents.bear import bear_agent
from options_arena.agents.bull import bull_agent
from options_arena.agents.model_config import build_debate_model
from options_arena.agents.risk import risk_agent
from options_arena.agents.volatility import volatility_agent
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
    VolatilityThesis,
)

logger = logging.getLogger(__name__)


class DebatePhase(StrEnum):
    """Phases of the AI debate pipeline, reported via progress callback."""

    BULL = "bull"
    BEAR = "bear"
    REBUTTAL = "rebuttal"
    VOLATILITY = "volatility"
    RISK = "risk"


type DebateProgressCallback = Callable[[DebatePhase, str, float | None], None]
"""Callback for debate progress: ``(phase, status, confidence_or_none)``."""


def should_debate(ticker_score: TickerScore, config: DebateConfig) -> bool:
    """Return False if signal is too weak for meaningful AI debate.

    Pure function — no side effects, no I/O, no logging. Score comparison
    uses ``<`` so that a score exactly at ``min_debate_score`` returns True.
    """
    if ticker_score.direction == SignalDirection.NEUTRAL:
        return False
    return ticker_score.composite_score >= config.min_debate_score


def build_market_context(
    ticker_score: TickerScore,
    quote: Quote,
    ticker_info: TickerInfo,
    contracts: list[OptionContract],
) -> MarketContext:
    """Map scan pipeline output to ``MarketContext`` for agent consumption.

    Passes ``None`` through for optional float fields so that
    ``MarketContext.completeness_ratio()`` accurately reflects data availability.
    Options-specific indicators (``iv_rank``, ``iv_percentile``,
    ``put_call_ratio``) may be ``None`` on ``TickerScore.signals``.

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
        iv_rank=signals.iv_rank,
        iv_percentile=signals.iv_percentile,
        atm_iv_30d=(
            first_contract.market_iv
            if first_contract is not None and first_contract.market_iv > 0
            else None
        ),
        rsi_14=signals.rsi if signals.rsi is not None else 50.0,
        macd_signal=macd_signal,
        put_call_ratio=signals.put_call_ratio,
        next_earnings=None,
        dte_target=dte_target,
        target_strike=target_strike,
        target_delta=target_delta,
        sector=ticker_info.sector,
        dividend_yield=ticker_info.dividend_yield,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime.now(UTC),
        # Scoring context
        composite_score=ticker_score.composite_score,
        direction_signal=ticker_score.direction,
        # Key indicators (pass through from signals — already float | None)
        adx=signals.adx,
        sma_alignment=signals.sma_alignment,
        bb_width=signals.bb_width,
        atr_pct=signals.atr_pct,
        stochastic_rsi=signals.stochastic_rsi,
        relative_volume=signals.relative_volume,
        # Greeks beyond delta (None-safe access)
        target_gamma=(
            first_contract.greeks.gamma if first_contract and first_contract.greeks else None
        ),
        target_theta=(
            first_contract.greeks.theta if first_contract and first_contract.greeks else None
        ),
        target_vega=(
            first_contract.greeks.vega if first_contract and first_contract.greeks else None
        ),
        target_rho=(
            first_contract.greeks.rho if first_contract and first_contract.greeks else None
        ),
        # Options-specific indicators
        max_pain_distance=signals.max_pain_distance,
        # Contract pricing
        contract_mid=first_contract.mid if first_contract else None,
    )


def _log_completeness_breakdown(context: MarketContext, ratio: float) -> None:
    """Log which MarketContext fields are populated vs missing for diagnostics."""
    field_checks: list[tuple[str, float | None]] = [
        ("iv_rank", context.iv_rank),
        ("iv_percentile", context.iv_percentile),
        ("atm_iv_30d", context.atm_iv_30d),
        ("put_call_ratio", context.put_call_ratio),
        ("max_pain_distance", context.max_pain_distance),
        ("adx", context.adx),
        ("sma_alignment", context.sma_alignment),
        ("bb_width", context.bb_width),
        ("atr_pct", context.atr_pct),
        ("stochastic_rsi", context.stochastic_rsi),
        ("relative_volume", context.relative_volume),
    ]
    if context.contract_mid is not None:
        field_checks.extend(
            [
                ("target_gamma", context.target_gamma),
                ("target_theta", context.target_theta),
                ("target_vega", context.target_vega),
                ("target_rho", context.target_rho),
            ]
        )

    populated = [name for name, val in field_checks if val is not None]
    missing = [name for name, val in field_checks if val is None]

    logger.info(
        "MarketContext completeness for %s: %.0f%% (%d/%d) — populated=[%s], missing=[%s]",
        context.ticker,
        ratio * 100,
        len(populated),
        len(field_checks),
        ", ".join(populated),
        ", ".join(missing),
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
    progress: DebateProgressCallback | None = None,
) -> DebateResult:
    """Run AI debate on a ticker. On ANY failure, returns data-driven fallback -- never raises.

    Agents run sequentially:
    1. Bull agent argues the bullish case.
    2. Bear agent receives the bull's argument and counters it.
    3. Volatility agent (optional, config-gated) assesses IV mispricing.
    4. Risk agent weighs arguments (and vol context when present) and produces a ``TradeThesis``.

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
        Debate configuration (model, timeouts).
    repository
        Optional persistence layer. If provided, debate results are saved.
    progress
        Optional callback for real-time progress reporting. Called with
        ``(phase, status, confidence)`` on agent start/complete.

    Returns
    -------
    DebateResult
        Complete debate output. ``is_fallback=True`` if AI debate failed.
    """
    start_time = time.monotonic()
    context = build_market_context(ticker_score, quote, ticker_info, contracts)

    completeness = context.completeness_ratio()

    # Log completeness breakdown for diagnostics
    _log_completeness_breakdown(context, completeness)

    if not should_debate(ticker_score, config):
        logger.info("Skipping debate for %s: signal too weak", ticker_score.ticker)
        result = _build_screening_fallback(context, ticker_score, contracts, config, start_time)
    elif completeness < 0.4:
        logger.warning(
            "MarketContext completeness %.0f%% < 40%% for %s — using data-driven fallback",
            completeness * 100,
            context.ticker,
        )
        result = _build_fallback_result(context, ticker_score, contracts, config, start_time)
    else:
        if completeness < 0.6:
            logger.warning(
                "MarketContext completeness %.0f%% < 60%% for %s — proceeding with caution",
                completeness * 100,
                context.ticker,
            )
        try:
            result = await asyncio.wait_for(
                _run_agents(context, ticker_score, contracts, config, start_time, progress),
                timeout=config.max_total_duration,
            )
        except httpx.ConnectError as e:
            logger.warning(
                "LLM provider not reachable for %s (%s: %s), using data-driven fallback",
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


def _notify(
    progress: DebateProgressCallback | None,
    phase: DebatePhase,
    status: str,
    confidence: float | None = None,
) -> None:
    """Call progress callback if set. Never raises."""
    if progress is not None:
        try:
            progress(phase, status, confidence)
        except Exception:
            logger.debug("Progress callback error (ignored)", exc_info=True)


async def _run_agents(
    context: MarketContext,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    config: DebateConfig,
    start_time: float,
    progress: DebateProgressCallback | None = None,
) -> DebateResult:
    """Run the sequential agent pipeline (bull -> bear -> [volatility] -> risk).

    Raises on any agent failure — the caller (``run_debate``) catches and falls back.
    """
    model = build_debate_model(config)
    settings = ModelSettings(temperature=config.temperature)
    per_agent_timeout = config.agent_timeout
    context_text = render_context_block(context)

    # --- Bull agent ---
    logger.info("Running bull agent for %s", context.ticker)
    _notify(progress, DebatePhase.BULL, "started")
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
            model_settings=settings,
        ),
        timeout=per_agent_timeout,
    )
    bull_output: AgentResponse = bull_result.output
    logger.info(
        "Bull agent complete for %s: confidence=%.2f",
        context.ticker,
        bull_output.confidence,
    )
    _notify(progress, DebatePhase.BULL, "completed", bull_output.confidence)

    # --- Bear agent ---
    logger.info("Running bear agent for %s", context.ticker)
    _notify(progress, DebatePhase.BEAR, "started")
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
            model_settings=settings,
        ),
        timeout=per_agent_timeout,
    )
    bear_output: AgentResponse = bear_result.output
    logger.info(
        "Bear agent complete for %s: confidence=%.2f",
        context.ticker,
        bear_output.confidence,
    )
    _notify(progress, DebatePhase.BEAR, "completed", bear_output.confidence)

    # --- Rebuttal + Volatility (parallel when both enabled, sequential otherwise) ---
    rebuttal_result: AgentRunResult[AgentResponse] | None = None
    rebuttal_output: AgentResponse | None = None
    vol_result: AgentRunResult[VolatilityThesis] | None = None
    vol_output: VolatilityThesis | None = None

    if config.enable_rebuttal and config.enable_volatility_agent:
        # Run both in parallel — they have no dependency on each other
        logger.info("Running rebuttal + volatility in parallel for %s", context.ticker)
        _notify(progress, DebatePhase.REBUTTAL, "started")
        _notify(progress, DebatePhase.VOLATILITY, "started")
        rebuttal_coro = _run_rebuttal(
            context,
            ticker_score,
            contracts,
            bear_output,
            model,
            settings,
            per_agent_timeout,
            context_text,
        )
        vol_coro = _run_volatility(
            context,
            ticker_score,
            contracts,
            bull_output,
            bear_output,
            model,
            settings,
            per_agent_timeout,
            context_text,
        )
        parallel_results = await asyncio.gather(
            rebuttal_coro,
            vol_coro,
            return_exceptions=True,
        )
        # Handle rebuttal result
        if isinstance(parallel_results[0], BaseException):
            logger.warning(
                "Rebuttal failed for %s: %s",
                context.ticker,
                parallel_results[0],
            )
            _notify(progress, DebatePhase.REBUTTAL, "failed")
        else:
            rebuttal_result, rebuttal_output = parallel_results[0]
            _notify(
                progress,
                DebatePhase.REBUTTAL,
                "completed",
                rebuttal_output.confidence,
            )
        # Handle volatility result
        if isinstance(parallel_results[1], BaseException):
            logger.warning(
                "Volatility agent failed for %s: %s",
                context.ticker,
                parallel_results[1],
            )
            _notify(progress, DebatePhase.VOLATILITY, "failed")
        else:
            vol_result, vol_output = parallel_results[1]
            _notify(
                progress,
                DebatePhase.VOLATILITY,
                "completed",
                vol_output.confidence,
            )
    else:
        if config.enable_rebuttal:
            _notify(progress, DebatePhase.REBUTTAL, "started")
            rebuttal_result, rebuttal_output = await _run_rebuttal(
                context,
                ticker_score,
                contracts,
                bear_output,
                model,
                settings,
                per_agent_timeout,
                context_text,
            )
            _notify(
                progress,
                DebatePhase.REBUTTAL,
                "completed",
                rebuttal_output.confidence,
            )
        if config.enable_volatility_agent:
            _notify(progress, DebatePhase.VOLATILITY, "started")
            vol_result, vol_output = await _run_volatility(
                context,
                ticker_score,
                contracts,
                bull_output,
                bear_output,
                model,
                settings,
                per_agent_timeout,
                context_text,
            )
            _notify(
                progress,
                DebatePhase.VOLATILITY,
                "completed",
                vol_output.confidence,
            )

    # --- Risk agent (always last — depends on all prior outputs) ---
    logger.info("Running risk agent for %s", context.ticker)
    _notify(progress, DebatePhase.RISK, "started")
    risk_deps = DebateDeps(
        context=context,
        ticker_score=ticker_score,
        contracts=contracts,
        bull_response=bull_output,
        bear_response=bear_output,
        bull_rebuttal=rebuttal_output,
        vol_response=vol_output,
    )
    risk_result = await asyncio.wait_for(
        risk_agent.run(
            f"Adjudicate the debate for {context.ticker} and produce a trade thesis.\n\n"
            f"{context_text}",
            model=model,
            deps=risk_deps,
            model_settings=settings,
        ),
        timeout=per_agent_timeout,
    )
    thesis: TradeThesis = risk_result.output
    logger.info(
        "Risk agent complete for %s: direction=%s, confidence=%.2f",
        context.ticker,
        thesis.direction.value,
        thesis.confidence,
    )
    _notify(progress, DebatePhase.RISK, "completed", thesis.confidence)

    # Accumulate usage across all agents
    total_usage = bull_result.usage() + bear_result.usage() + risk_result.usage()
    if rebuttal_result is not None:
        total_usage = total_usage + rebuttal_result.usage()
    if vol_result is not None:
        total_usage = total_usage + vol_result.usage()
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # Citation density scoring
    agent_texts = [
        bull_output.argument,
        bear_output.argument,
        thesis.summary,
        thesis.risk_assessment,
    ]
    if rebuttal_output is not None:
        agent_texts.append(rebuttal_output.argument)
    density = compute_citation_density(context_text, *agent_texts)

    logger.info(
        "Debate complete for %s in %dms (tokens: in=%d, out=%d, citation=%.2f)",
        context.ticker,
        elapsed_ms,
        total_usage.input_tokens,
        total_usage.output_tokens,
        density,
    )

    return DebateResult(
        context=context,
        bull_response=bull_output,
        bear_response=bear_output,
        thesis=thesis,
        total_usage=total_usage,
        duration_ms=elapsed_ms,
        is_fallback=False,
        bull_rebuttal=rebuttal_output,
        vol_response=vol_output,
        citation_density=density,
    )


async def _run_rebuttal(
    context: MarketContext,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    bear_output: AgentResponse,
    model: Model,
    settings: ModelSettings,
    timeout: float,
    context_text: str,
) -> tuple[AgentRunResult[AgentResponse], AgentResponse]:
    """Run bull rebuttal agent. Returns (run_result, output) tuple."""
    logger.info("Running bull rebuttal for %s", context.ticker)
    bear_key_points = (
        "\n".join(f"- {p}" for p in bear_output.key_points)
        if bear_output.key_points
        else f"- {bear_output.argument}"
    )
    rebuttal_deps = DebateDeps(
        context=context,
        ticker_score=ticker_score,
        contracts=contracts,
        bear_counter_argument=bear_key_points,
    )
    result = await asyncio.wait_for(
        bull_agent.run(
            f"Rebut the bear's counterarguments for {context.ticker}.\n\n{context_text}",
            model=model,
            deps=rebuttal_deps,
            model_settings=settings,
        ),
        timeout=timeout,
    )
    output: AgentResponse = result.output
    logger.info(
        "Bull rebuttal complete for %s: confidence=%.2f",
        context.ticker,
        output.confidence,
    )
    return result, output


async def _run_volatility(
    context: MarketContext,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    bull_output: AgentResponse,
    bear_output: AgentResponse,
    model: Model,
    settings: ModelSettings,
    timeout: float,
    context_text: str,
) -> tuple[AgentRunResult[VolatilityThesis], VolatilityThesis]:
    """Run volatility agent. Returns (run_result, output) tuple."""
    logger.info("Running volatility agent for %s", context.ticker)
    vol_deps = DebateDeps(
        context=context,
        ticker_score=ticker_score,
        contracts=contracts,
        bull_response=bull_output,
        bear_response=bear_output,
    )
    result = await asyncio.wait_for(
        volatility_agent.run(
            f"Assess implied volatility for {context.ticker}.\n\n{context_text}",
            model=model,
            deps=vol_deps,
            model_settings=settings,
        ),
        timeout=timeout,
    )
    output: VolatilityThesis = result.output
    logger.info(
        "Volatility agent complete for %s: iv_assessment=%s, confidence=%.2f",
        context.ticker,
        output.iv_assessment,
        output.confidence,
    )
    return result, output


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
    cap = config.fallback_confidence
    bull_confidence = min(ticker_score.composite_score / 100.0 * cap, cap)
    bull_response = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
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
    bear_confidence = min((100.0 - ticker_score.composite_score) / 100.0 * cap, cap)
    bear_response = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
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
        bull_rebuttal=None,
        vol_response=None,
    )


def _build_screening_fallback(
    context: MarketContext,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    config: DebateConfig,
    start_time: float,
) -> DebateResult:
    """Build fallback for tickers that fail pre-debate screening.

    Wraps ``_build_fallback_result()`` with a screening-specific thesis summary
    indicating the debate was skipped due to weak signal.
    """
    result = _build_fallback_result(context, ticker_score, contracts, config, start_time)
    screening_summary = (
        f"Signal too weak for meaningful debate "
        f"(composite: {ticker_score.composite_score:.1f}/100, "
        f"direction: {ticker_score.direction.value})."
    )
    # Override thesis with screening-specific summary and no strategy recommendation
    screening_thesis = TradeThesis(
        ticker=result.thesis.ticker,
        direction=result.thesis.direction,
        confidence=result.thesis.confidence,
        summary=screening_summary,
        bull_score=result.thesis.bull_score,
        bear_score=result.thesis.bear_score,
        key_factors=result.thesis.key_factors,
        risk_assessment=result.thesis.risk_assessment,
        recommended_strategy=None,
    )
    return DebateResult(
        context=result.context,
        bull_response=result.bull_response,
        bear_response=result.bear_response,
        thesis=screening_thesis,
        total_usage=result.total_usage,
        duration_ms=result.duration_ms,
        is_fallback=True,
        bull_rebuttal=None,
        vol_response=None,
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
        if value is not None and math.isfinite(value):
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
        model_name = config.model

        # Compute debate_mode for A/B logging
        if result.is_fallback:
            debate_mode = "fallback"
        elif config.enable_rebuttal and config.enable_volatility_agent:
            debate_mode = "full"
        elif config.enable_rebuttal:
            debate_mode = "rebuttal-only"
        elif config.enable_volatility_agent:
            debate_mode = "vol-only"
        else:
            debate_mode = "base"

        await repository.save_debate(
            scan_run_id=ticker_score.scan_run_id,
            ticker=result.context.ticker,
            bull_json=result.bull_response.model_dump_json(),
            bear_json=result.bear_response.model_dump_json(),
            risk_json=None,  # Risk output is TradeThesis, stored in verdict_json
            verdict_json=result.thesis.model_dump_json(),
            total_tokens=total_tokens,
            model_name=model_name,
            duration_ms=result.duration_ms,
            is_fallback=result.is_fallback,
            vol_json=(
                result.vol_response.model_dump_json() if result.vol_response is not None else None
            ),
            rebuttal_json=(
                result.bull_rebuttal.model_dump_json()
                if result.bull_rebuttal is not None
                else None
            ),
            debate_mode=debate_mode,
            citation_density=result.citation_density,
        )
        logger.debug(
            "Persisted debate for %s (tokens=%d, fallback=%s, mode=%s)",
            result.context.ticker,
            total_tokens,
            result.is_fallback,
            debate_mode,
        )
    except Exception:
        logger.warning(
            "Failed to persist debate result for %s",
            result.context.ticker,
            exc_info=True,
        )
