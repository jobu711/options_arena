"""Recommendation orchestrator — run_recommendation() 4-phase pipeline.

Coordinates six desk recommendation agents in parallel, feeds their assessments
into the synthesis agent, and persists the result.  Follows the same never-raises
contract as ``run_debate()``.

Protocol flow:
  Phase 0 (setup):  Build MarketContext, check should_recommend, build deps
  Phase 1 (parallel): 6 desk recommendation agents via asyncio.gather
  Phase 2 (synthesis): synthesis agent weighs assessments → PositionRecommendation
  Phase 3 (persist):  Save RecommendationResult + AgentPrediction list

Architecture rules:
- Every ``agent.run()`` is wrapped in ``asyncio.wait_for(timeout=...)``.
- The orchestrator does NOT fetch data — all inputs are pre-fetched by the caller.
- ``time.monotonic()`` for duration measurement, never ``time.time()``.
- ``run_recommendation()`` never raises — any exception returns a valid fallback.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from options_arena.agents._context import (
    _build_model_settings,
    build_market_context,
    should_recommend,
)
from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._parsing import compute_citation_density, render_context_block
from options_arena.agents.contrarian_desk import run_contrarian_desk_recommendation
from options_arena.agents.flow_desk import run_flow_desk_recommendation
from options_arena.agents.fundamental_desk import run_fundamental_desk_recommendation
from options_arena.agents.model_config import build_debate_model
from options_arena.agents.risk_desk import run_risk_desk_recommendation
from options_arena.agents.synthesis_agent import SynthesisDeps, run_synthesis
from options_arena.agents.trend_desk import run_trend_desk_recommendation
from options_arena.agents.volatility_desk import run_vol_desk_recommendation
from options_arena.data.repository import Repository
from options_arena.models import (
    AgencyConfig,
    AgentPrediction,
    AppSettings,
    DeskType,
    MarketContext,
    OptionContract,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
)
from options_arena.models.enums import RuleStatus
from options_arena.models.options import SpreadAnalysis
from options_arena.models.recommendation import (
    AnyAssessment,
    ContrarianAssessment,
    DomainAssessment,
    FlowAssessment,
    FundamentalAssessment,
    PositionRecommendation,
    RecommendationResult,
    RiskDeskAssessment,
    TrendAssessment,
    VolatilityAssessment,
)
from options_arena.services.fred import FredService
from options_arena.services.market_data import MarketDataService
from options_arena.services.options_data import OptionsDataService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public type alias
# ---------------------------------------------------------------------------

RecommendationProgressCallback = Callable[[str, int, int], None]
"""Callback signature: (phase_name, current_step, total_steps)."""


class _DeskRunner(Protocol):
    """Protocol for desk recommendation runner functions."""

    def __call__(
        self,
        deps: DeskDeps,
        *,
        model: Model | None,
        model_settings: ModelSettings | None,
        config: AgencyConfig | None,
    ) -> Coroutine[Any, Any, DomainAssessment]: ...


# ---------------------------------------------------------------------------
# Fallback builders
# ---------------------------------------------------------------------------

_DESK_ASSESSMENT_MAP: dict[DeskType, type[DomainAssessment]] = {
    DeskType.TREND: TrendAssessment,
    DeskType.VOLATILITY: VolatilityAssessment,
    DeskType.FLOW: FlowAssessment,
    DeskType.FUNDAMENTAL: FundamentalAssessment,
    DeskType.RISK: RiskDeskAssessment,
    DeskType.CONTRARIAN: ContrarianAssessment,
}


def _build_fallback_assessment(desk_type: DeskType, ticker: str) -> DomainAssessment:
    """Build a desk-specific fallback ``DomainAssessment`` with correct subclass type.

    Each ``DeskType`` maps to its concrete subclass so that the discriminated
    union (``AnyAssessment``) round-trips correctly.
    """
    direction = SignalDirection.NEUTRAL
    confidence = 0.2
    summary = f"{desk_type.value.title()} assessment unavailable for {ticker}"
    key_factors = ["Assessment unavailable — agent failed"]
    risks = [f"Unable to analyze {desk_type.value}"]
    contracts_referenced: list[str] = []
    tools_used: list[str] = []
    model_used = "data-driven-fallback"

    match desk_type:
        case DeskType.TREND:
            return TrendAssessment(
                direction=direction,
                confidence=confidence,
                summary=summary,
                key_factors=key_factors,
                risks=risks,
                contracts_referenced=contracts_referenced,
                tools_used=tools_used,
                model_used=model_used,
                trend_strength=None,
                momentum_signal=None,
            )
        case DeskType.VOLATILITY:
            return VolatilityAssessment(
                direction=direction,
                confidence=confidence,
                summary=summary,
                key_factors=key_factors,
                risks=risks,
                contracts_referenced=contracts_referenced,
                tools_used=tools_used,
                model_used=model_used,
                iv_regime=None,
                vol_skew_assessment=None,
                term_structure_shape=None,
            )
        case DeskType.FLOW:
            return FlowAssessment(
                direction=direction,
                confidence=confidence,
                summary=summary,
                key_factors=key_factors,
                risks=risks,
                contracts_referenced=contracts_referenced,
                tools_used=tools_used,
                model_used=model_used,
                flow_bias=None,
                unusual_activity_noted=False,
            )
        case DeskType.FUNDAMENTAL:
            return FundamentalAssessment(
                direction=direction,
                confidence=confidence,
                summary=summary,
                key_factors=key_factors,
                risks=risks,
                contracts_referenced=contracts_referenced,
                tools_used=tools_used,
                model_used=model_used,
                valuation_signal=None,
                catalyst_timeline=None,
            )
        case DeskType.RISK:
            return RiskDeskAssessment(
                direction=direction,
                confidence=confidence,
                summary=summary,
                key_factors=key_factors,
                risks=risks,
                contracts_referenced=contracts_referenced,
                tools_used=tools_used,
                model_used=model_used,
                max_position_pct=0.02,
                hedging_suggestion="Review required",
                portfolio_correlation_note=None,
            )
        case DeskType.CONTRARIAN:
            return ContrarianAssessment(
                direction=direction,
                confidence=confidence,
                summary=summary,
                key_factors=key_factors,
                risks=risks,
                contracts_referenced=contracts_referenced,
                tools_used=tools_used,
                model_used=model_used,
                consensus_challenged=None,
                contrarian_thesis=None,
            )
        case _:
            # RESEARCH or unknown — shouldn't happen in recommendation pipeline
            return TrendAssessment(
                direction=direction,
                confidence=confidence,
                summary=summary,
                key_factors=key_factors,
                risks=risks,
                contracts_referenced=contracts_referenced,
                tools_used=tools_used,
                model_used=model_used,
                trend_strength=None,
                momentum_signal=None,
            )


def _build_fallback_recommendation(
    context: MarketContext,
    ticker: str,
) -> PositionRecommendation:
    """Build a conservative fallback ``PositionRecommendation`` for total failure."""
    return PositionRecommendation(
        ticker=ticker,
        direction=SignalDirection.NEUTRAL,
        confidence=0.2,
        recommended_contract=f"{ticker} ATM (recommendation pipeline failed)",
        entry_price=context.current_price,
        entry_criteria="N/A — data-driven fallback, manual review required",
        exit_criteria="N/A — data-driven fallback, manual review required",
        stop_loss=None,
        take_profit=None,
        position_size_pct=0.02,
        position_rationale="Minimum position size due to pipeline failure",
        risk_reward_ratio=1.0,
        max_loss_estimate="Unable to estimate — recommendation pipeline failed",
        recommended_strategy=None,
        strategy_rationale="No strategy recommended — pipeline failed",
        summary=(
            f"Data-driven fallback for {ticker}. "
            f"Recommendation pipeline was unavailable. Exercise additional caution."
        ),
        key_factors=["Pipeline failure — all assessments are fallbacks"],
        risk_assessment="High risk — AI recommendation unavailable, manual review required",
        agent_agreement_score=None,
        dissenting_desks=[],
        model_used="data-driven-fallback",
    )


def _build_fallback_recommendation_result(
    context: MarketContext,
    ticker: str,
    duration_ms: int = 0,
) -> RecommendationResult:
    """Build full ``RecommendationResult`` for total pipeline failure."""
    desk_types = [
        DeskType.TREND,
        DeskType.VOLATILITY,
        DeskType.FLOW,
        DeskType.FUNDAMENTAL,
        DeskType.RISK,
        DeskType.CONTRARIAN,
    ]
    # Each _build_fallback_assessment returns a concrete subclass that is a
    # valid AnyAssessment member.  The cast is safe because every DeskType maps
    # to its correct subclass in the match statement.
    raw_assessments = [_build_fallback_assessment(dt, ticker) for dt in desk_types]
    assessments: list[AnyAssessment] = raw_assessments  # type: ignore[assignment]
    recommendation = _build_fallback_recommendation(context, ticker)

    return RecommendationResult(
        context=context,
        assessments=assessments,
        recommendation=recommendation,
        total_usage=RunUsage(),
        duration_ms=duration_ms,
        is_fallback=True,
        citation_density=0.0,
    )


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

# Ordered list of (DeskType, runner coroutine factory) tuples.
_DESK_RUNNERS: list[tuple[DeskType, _DeskRunner]] = [
    (DeskType.TREND, run_trend_desk_recommendation),
    (DeskType.VOLATILITY, run_vol_desk_recommendation),
    (DeskType.FLOW, run_flow_desk_recommendation),
    (DeskType.FUNDAMENTAL, run_fundamental_desk_recommendation),
    (DeskType.RISK, run_risk_desk_recommendation),
    (DeskType.CONTRARIAN, run_contrarian_desk_recommendation),
]


async def run_recommendation(
    ticker: str,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    quote: Quote,
    ticker_info: TickerInfo,
    settings: AppSettings,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    fred: FredService | None = None,
    scan_run_id: int | None = None,
    spread_analysis: SpreadAnalysis | None = None,  # noqa: ARG001
    progress_callback: RecommendationProgressCallback | None = None,
) -> RecommendationResult:
    """Run the 4-phase recommendation pipeline — never raises.

    Parameters
    ----------
    ticker
        Symbol to analyze (e.g. ``"AAPL"``).
    ticker_score
        Scored ticker from the scan pipeline.
    contracts
        Recommended option contracts (may be empty).
    quote
        Current price snapshot.
    ticker_info
        Fundamental data (sector, dividend, 52-week range).
    settings
        Application settings (debate config, agency config).
    repo
        Database repository for persistence and learned patterns.
    market_data
        Market data service (passed to DeskDeps for tool use).
    options_data
        Options data service (passed to DeskDeps for tool use).
    fred
        FRED service (optional).
    scan_run_id
        Scan run ID for persistence linkage.
    spread_analysis
        Optional spread analysis (reserved for future use).
    progress_callback
        Optional callback for phase progress reporting.

    Returns
    -------
    RecommendationResult
        The complete recommendation, or a data-driven fallback on any error.
    """
    t0 = time.monotonic()

    try:
        return await _run_recommendation_pipeline(
            ticker=ticker,
            ticker_score=ticker_score,
            contracts=contracts,
            quote=quote,
            ticker_info=ticker_info,
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
            scan_run_id=scan_run_id,
            progress_callback=progress_callback,
            t0=t0,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "Recommendation pipeline failed for %s: %s (%s) — returning fallback",
            ticker,
            exc,
            type(exc).__name__,
        )
        # Build a minimal MarketContext for the fallback
        try:
            context = build_market_context(ticker_score, quote, ticker_info, contracts)
        except Exception:
            # Even context building failed — build a truly minimal fallback
            context = _build_emergency_context(ticker, quote)
        return _build_fallback_recommendation_result(context, ticker, duration_ms)


async def _run_recommendation_pipeline(
    *,
    ticker: str,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    quote: Quote,
    ticker_info: TickerInfo,
    settings: AppSettings,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    fred: FredService | None,
    scan_run_id: int | None,
    progress_callback: RecommendationProgressCallback | None,
    t0: float,
) -> RecommendationResult:
    """Inner pipeline — may raise; caller catches and returns fallback."""
    config = settings.debate
    agency_config = settings.agency

    # ------------------------------------------------------------------
    # Phase 0: Build context
    # ------------------------------------------------------------------
    if progress_callback is not None:
        progress_callback("context", 0, 4)

    context = build_market_context(ticker_score, quote, ticker_info, contracts)

    if not should_recommend(ticker_score, config):
        logger.info(
            "Skipping recommendation for %s — score %.1f below threshold or NEUTRAL direction",
            ticker,
            ticker_score.composite_score,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        return _build_fallback_recommendation_result(context, ticker, duration_ms)

    # Build LLM model + settings
    model = build_debate_model(config)
    model_settings = _build_model_settings(config)

    # Fetch learned patterns (never-raises)
    learned_patterns = ""
    try:
        from options_arena.learning.strategy_book import render_learned_patterns

        approved_rules = await repo.get_strategy_rules(status=RuleStatus.APPROVED)
        learned_patterns = render_learned_patterns(approved_rules)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, ImportError):
        logger.warning("Failed to fetch learned patterns — proceeding without them")

    # Build DeskDeps for all desk agents
    desk_deps = DeskDeps(
        query=f"Produce a structured assessment for {ticker}.",
        ticker=ticker,
        market_data=market_data,
        options_data=options_data,
        repo=repo,
        fred=fred,
        learned_patterns=learned_patterns,
        ticker_score=ticker_score,
        contracts=list(contracts),
        market_context=context,
    )

    # ------------------------------------------------------------------
    # Phase 1: Parallel desk recommendations
    # ------------------------------------------------------------------
    if progress_callback is not None:
        progress_callback("desks", 1, 4)

    semaphore = asyncio.Semaphore(agency_config.desk_parallelism)

    async def _run_desk(
        desk_type: DeskType,
        runner: _DeskRunner,
    ) -> DomainAssessment:
        """Run a single desk under the semaphore — never raises."""
        async with semaphore:
            try:
                result = await runner(
                    desk_deps,
                    model=model,
                    model_settings=model_settings,
                    config=agency_config,
                )
                if isinstance(result, BaseException):
                    logger.warning(
                        "Desk %s returned exception: %s",
                        desk_type.value,
                        result,
                    )
                    return _build_fallback_assessment(desk_type, ticker)
                return result
            except Exception as exc:
                logger.warning(
                    "Desk %s failed: %s (%s)",
                    desk_type.value,
                    exc,
                    type(exc).__name__,
                )
                return _build_fallback_assessment(desk_type, ticker)

    tasks = [_run_desk(dt, runner) for dt, runner in _DESK_RUNNERS]
    desk_results: list[DomainAssessment] = await asyncio.gather(*tasks)

    # Cast to AnyAssessment list for RecommendationResult
    assessments: list[AnyAssessment] = list(desk_results)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Phase 2: Synthesis
    # ------------------------------------------------------------------
    if progress_callback is not None:
        progress_callback("synthesis", 2, 4)

    synthesis_deps = SynthesisDeps(
        context=context,
        assessments=list(desk_results),
        contracts=list(contracts),
        ticker_score=ticker_score,
        learned_patterns=learned_patterns,
    )

    recommendation = await run_synthesis(
        deps=synthesis_deps,
        model=model,
        model_settings=model_settings,
        timeout=agency_config.agent_timeout * 2,  # synthesis gets extra time
    )

    # Compute citation density
    context_block = render_context_block(context)
    citation_density = compute_citation_density(context_block, recommendation.summary)

    # Determine if this is a fallback result
    is_fallback = recommendation.model_used == "data-driven-fallback"

    duration_ms = int((time.monotonic() - t0) * 1000)

    result = RecommendationResult(
        context=context,
        assessments=assessments,
        recommendation=recommendation,
        total_usage=RunUsage(),
        duration_ms=duration_ms,
        is_fallback=is_fallback,
        citation_density=citation_density,
    )

    # ------------------------------------------------------------------
    # Phase 3: Persist
    # ------------------------------------------------------------------
    if progress_callback is not None:
        progress_callback("persist", 3, 4)

    await _persist_recommendation(result, repo, scan_run_id, assessments, ticker)

    return result


async def _persist_recommendation(
    result: RecommendationResult,
    repo: Repository,
    scan_run_id: int | None,
    assessments: list[AnyAssessment],
    ticker: str,
) -> None:
    """Persist recommendation result and agent predictions — never raises."""
    try:
        rec_id = await repo.save_recommendation(result, scan_run_id)
        logger.info("Saved recommendation id=%d for %s", rec_id, ticker)
    except Exception as exc:
        logger.warning(
            "Failed to save recommendation for %s: %s (%s)",
            ticker,
            exc,
            type(exc).__name__,
        )
        return

    # Extract and save agent predictions
    try:
        now = datetime.now(UTC)
        predictions: list[AgentPrediction] = []
        for assessment in assessments:
            if isinstance(assessment, DomainAssessment):
                predictions.append(
                    AgentPrediction(
                        debate_id=rec_id,
                        recommended_contract_id=None,
                        agent_name=assessment.desk.value,
                        direction=assessment.direction,
                        confidence=assessment.confidence,
                        created_at=now,
                    )
                )
        if predictions:
            await repo.save_agent_predictions(predictions)
            logger.debug(
                "Saved %d agent predictions for recommendation %d",
                len(predictions),
                rec_id,
            )
    except Exception as exc:
        logger.warning(
            "Failed to save agent predictions for %s: %s (%s)",
            ticker,
            exc,
            type(exc).__name__,
        )


def _build_emergency_context(ticker: str, quote: Quote) -> MarketContext:
    """Build the most minimal MarketContext possible for emergency fallback.

    Used when even ``build_market_context()`` fails.
    """
    from options_arena.models import ExerciseStyle, MacdSignal

    return MarketContext(
        ticker=ticker,
        current_price=quote.price,
        price_52w_high=quote.price,
        price_52w_low=quote.price,
        rsi_14=50.0,
        macd_signal=MacdSignal.NEUTRAL,
        next_earnings=None,
        dte_target=45,
        target_strike=quote.price,
        target_delta=0.35,
        sector="Unknown",
        dividend_yield=0.0,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime.now(UTC),
    )
