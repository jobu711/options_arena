"""Debate endpoints — start, list, get result, batch.

Issue #670: Rewrites background tasks to use ``run_recommendation()`` instead of
``run_debate()``.  The ``GET /api/debate/{id}`` endpoint performs dual-table lookup:
recommendation_results first (new data), then ai_theses (old data).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from options_arena.agents import run_recommendation
from options_arena.agents._context import effective_batch_ticker_delay
from options_arena.api.app import limiter
from options_arena.api.deps import (
    get_fred,
    get_market_data,
    get_operation_lock,
    get_options_data,
    get_repo,
    get_settings,
)
from options_arena.api.schemas import (
    BatchDebateRequest,
    BatchDebateStarted,
    BatchTickerResult,
    DebateRequest,
    DebateResultDetail,
    DebateResultSummary,
    DebateStarted,
    DeskAssessmentBrief,
    PositionRecommendationResponse,
    RecommendationResponse,
    SpreadDetail,
    spread_detail_from_analysis,
)
from options_arena.api.ws import BatchProgressBridge, RecommendationProgressBridge
from options_arena.data import Repository
from options_arena.data._recommendation import RecommendationRow
from options_arena.models import (
    AgentResponse,
    AppSettings,
    ContrarianThesis,
    ExtendedTradeThesis,
    FlowThesis,
    FundamentalThesis,
    RiskAssessment,
    SignalDirection,
    TradeThesis,
)
from options_arena.models.analysis import ScanEnrichment
from options_arena.models.config import RoutingConfig
from options_arena.models.enums import TICKER_RE
from options_arena.models.market_data import Quote, TickerInfo
from options_arena.models.options import OptionContract
from options_arena.models.scan import TickerScore
from options_arena.scoring import normalize_single_ticker
from options_arena.services import MarketDataService, OptionsDataService
from options_arena.services.fred import FredService

logger = logging.getLogger(__name__)

# Strong references to background tasks prevent garbage collection (AUDIT P1-1)
_background_tasks: set[asyncio.Task[None]] = set()

router = APIRouter(prefix="/api", tags=["debate"])


# ---------------------------------------------------------------------------
# Routing overlay resolution
# ---------------------------------------------------------------------------


def _resolve_routing_overlay(request: Request, settings: AppSettings) -> AppSettings:
    """Apply runtime routing override if one is active on ``app.state``.

    Returns a modified ``AppSettings`` copy with the overridden debate routing
    config, or the original settings unchanged if no override is set.
    """
    routing_override: RoutingConfig | None = getattr(request.app.state, "routing_override", None)
    if routing_override is not None:
        debate_copy = settings.debate.model_copy(update={"routing": routing_override})
        return settings.model_copy(update={"debate": debate_copy})
    return settings


# ---------------------------------------------------------------------------
# Helpers: prepare ticker data for run_recommendation()
# ---------------------------------------------------------------------------


async def _prepare_ticker_data(
    ticker: str,
    scan_id: int | None,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
) -> tuple[TickerScore, Quote, TickerInfo, list[OptionContract]]:
    """Fetch and prepare all data needed for ``run_recommendation()``.

    Returns (ticker_score, quote, ticker_info, contracts).
    """
    from options_arena.models import IndicatorSignals  # noqa: PLC0415

    quote: Quote = await market_data.fetch_quote(ticker)
    ticker_info: TickerInfo = await market_data.fetch_ticker_info(ticker)

    # Get score from scan results if available, else compute fresh
    score_match: TickerScore | None = None
    if scan_id is not None:
        all_scores = await repo.get_scores_for_scan(scan_id)
        score_match = next((s for s in all_scores if s.ticker == ticker), None)

    if score_match is None:
        from options_arena.scan.indicators import (  # noqa: PLC0415
            INDICATOR_REGISTRY,
            compute_indicators,
            ohlcv_to_dataframe,
        )
        from options_arena.scoring import (  # noqa: PLC0415
            composite_score as calc_composite,
        )
        from options_arena.scoring import (
            determine_direction,
        )

        ohlcv_list = await market_data.fetch_ohlcv(ticker, period="1y")
        if ohlcv_list:
            df = ohlcv_to_dataframe(ohlcv_list)
            raw_signals = compute_indicators(df, INDICATOR_REGISTRY)
        else:
            raw_signals = IndicatorSignals()

        adhoc_direction = determine_direction(
            adx=raw_signals.adx or 0.0,
            rsi=raw_signals.rsi or 50.0,
            sma_alignment=raw_signals.sma_alignment or 0.0,
            supertrend=raw_signals.supertrend,
            roc=raw_signals.roc,
        )

        normalized_signals = normalize_single_ticker(raw_signals)
        logger.info("single-ticker normalization applied for %s", ticker)

        adhoc_composite = calc_composite(normalized_signals)

        score_match = TickerScore(
            ticker=ticker,
            composite_score=adhoc_composite,
            direction=adhoc_direction,
            signals=normalized_signals,
        )

    # Fetch fresh option chains
    contracts: list[OptionContract] = []
    chain_results = await options_data.fetch_chain_all_expirations(ticker)
    for chain in chain_results:
        contracts.extend(chain.contracts)

    # Enrich with options-specific indicators from the full chain.
    # Defensive copy avoids mutating shared objects from concurrent tasks.
    if contracts:
        from options_arena.scan.indicators import (  # noqa: PLC0415
            compute_options_indicators,
        )

        score_match = score_match.model_copy(deep=True)
        spot = float(ticker_info.current_price)
        options_signals = compute_options_indicators(contracts, spot)
        if options_signals.put_call_ratio is not None:
            score_match.signals.put_call_ratio = options_signals.put_call_ratio
        if options_signals.max_pain_distance is not None:
            score_match.signals.max_pain_distance = options_signals.max_pain_distance

    return score_match, quote, ticker_info, contracts


# ---------------------------------------------------------------------------
# Recommendation row -> API response conversion
# ---------------------------------------------------------------------------


def _recommendation_row_to_response(
    row: RecommendationRow,
    recommendation_protocol: str,
) -> RecommendationResponse:
    """Convert a ``RecommendationRow`` to a ``RecommendationResponse`` schema."""
    # Parse assessments JSON
    assessments: list[DeskAssessmentBrief] = []
    try:
        assessment_dicts = json.loads(row.assessments_json)
        for ad in assessment_dicts:
            try:
                raw_conf = float(ad.get("confidence", 0.0))
                conf = raw_conf if math.isfinite(raw_conf) else 0.0
                assessments.append(
                    DeskAssessmentBrief(
                        desk=str(ad.get("desk", "unknown")),
                        direction=str(ad.get("direction", "neutral")),
                        confidence=conf,
                        summary=str(ad.get("summary", "")),
                        key_findings=list(ad.get("key_factors", [])),
                    )
                )
            except (TypeError, ValueError):
                logger.warning("Skipping malformed assessment in recommendation %d", row.id)
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("Failed to parse assessments JSON for recommendation %d", row.id)

    # Build recommendation response
    rec_response = PositionRecommendationResponse(
        ticker=row.ticker,
        recommended_contract=row.recommended_contract,
        entry_price=row.entry_price,
        stop_loss=row.stop_loss,
        take_profit=row.take_profit,
        position_size_pct=row.position_size_pct,
        risk_reward_ratio=row.risk_reward_ratio,
        direction=row.direction,
        confidence=row.confidence,
        strategy=row.recommended_strategy,
        strategy_rationale=row.strategy_rationale,
        rationale=row.position_rationale,
    )

    # Parse created_at datetime — add UTC if naive (legacy data defense)
    created_at = datetime.fromisoformat(row.created_at)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    return RecommendationResponse(
        id=row.id,
        ticker=row.ticker,
        assessments=assessments,
        recommendation=rec_response,
        is_fallback=row.is_fallback,
        recommendation_protocol=recommendation_protocol,
        duration_ms=row.duration_ms,
        total_tokens=row.total_input_tokens + row.total_output_tokens,
        citation_density=row.citation_density,
        model_used=row.model_used,
        created_at=created_at,
        scan_run_id=row.scan_run_id,
    )


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_recommendation_background(
    request: Request,
    debate_id: int,
    ticker: str,
    scan_id: int | None,
    settings: AppSettings,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    fred: FredService | None,
    bridge: RecommendationProgressBridge,
) -> None:
    """Run the recommendation orchestrator as a background task."""
    try:
        score_match, quote, ticker_info, contracts = await _prepare_ticker_data(
            ticker, scan_id, repo, market_data, options_data
        )

        result = await run_recommendation(
            ticker=ticker,
            ticker_score=score_match,
            contracts=contracts,
            quote=quote,
            ticker_info=ticker_info,
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
            scan_run_id=scan_id,
            enrichment=None,
            progress_callback=bridge,
        )

        # run_recommendation() handles its own persistence via _persist_recommendation.
        # Log completion.
        logger.info(
            "Recommendation for %s completed (fallback=%s, duration=%dms)",
            ticker,
            result.is_fallback,
            result.duration_ms,
        )

        bridge.complete(debate_id)
    except Exception:
        logger.exception("Recommendation %d for %s failed", debate_id, ticker)
        bridge.error(f"Recommendation failed for {ticker}")
        bridge.complete(debate_id)
    finally:
        # Clean up (initialized in lifespan)
        request.app.state.debate_queues.pop(debate_id, None)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.post("/debate", status_code=202)
@limiter.limit("5/minute")
async def start_debate(
    request: Request,
    body: DebateRequest,
    settings: AppSettings = Depends(get_settings),
    repo: Repository = Depends(get_repo),
    market_data: MarketDataService = Depends(get_market_data),
    options_data: OptionsDataService = Depends(get_options_data),
    fred: FredService = Depends(get_fred),
) -> DebateStarted:
    """Start a single-ticker recommendation in the background.

    No operation lock is needed here: single recommendations are lightweight,
    short-lived, and do not conflict with concurrent access. Only batch
    recommendations and scans require the mutex (AUDIT-015).

    NOTE: Provider selection (Groq vs Anthropic) is not yet exposed via the API.
    The API uses whatever ``ARENA_DEBATE__PROVIDER`` env var is set (defaults to
    Groq). To use Anthropic from the web UI, set the env var before starting the
    server. The CLI ``--provider`` flag is the only per-invocation override.
    """
    # Resolve routing overlay — apply runtime override if active
    effective_settings = _resolve_routing_overlay(request, settings)

    bridge = RecommendationProgressBridge()

    # Use a counter for debate IDs (initialized in lifespan)
    debate_id: int = next(request.app.state.debate_counter)

    request.app.state.debate_queues[debate_id] = bridge.queue

    task = asyncio.create_task(
        _run_recommendation_background(
            request,
            debate_id,
            body.ticker.upper(),
            body.scan_id,
            effective_settings,
            repo,
            market_data,
            options_data,
            fred,
            bridge,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return DebateStarted(debate_id=debate_id)


# ---------------------------------------------------------------------------
# Batch recommendation
# ---------------------------------------------------------------------------


async def _run_batch_recommendation_background(
    request: Request,
    batch_id: int,
    tickers: list[str],
    scan_id: int,
    settings: AppSettings,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    fred: FredService | None,
    bridge: BatchProgressBridge,
    lock: asyncio.Lock,
) -> None:
    """Run sequential recommendations for a batch of tickers.

    The lock is already acquired by the caller — this task releases it on completion.
    """
    results: list[BatchTickerResult] = []
    try:
        batch_delay = effective_batch_ticker_delay(settings.debate)
        for idx, ticker in enumerate(tickers):
            if idx > 0 and batch_delay > 0:
                logger.debug(
                    "Batch inter-ticker delay: %.1fs before %s (%d/%d)",
                    batch_delay,
                    ticker,
                    idx + 1,
                    len(tickers),
                )
                await asyncio.sleep(batch_delay)
            bridge.batch_progress(ticker, idx + 1, len(tickers), "started")
            try:
                score_match, quote, ticker_info, contracts = await _prepare_ticker_data(
                    ticker, scan_id, repo, market_data, options_data
                )

                # Build ScanEnrichment from persisted scan data
                spread = await repo.get_spread_for_ticker(scan_id, ticker)
                enrichment = ScanEnrichment(spread_analysis=spread)

                result = await run_recommendation(
                    ticker=ticker,
                    ticker_score=score_match,
                    contracts=contracts,
                    quote=quote,
                    ticker_info=ticker_info,
                    settings=settings,
                    repo=repo,
                    market_data=market_data,
                    options_data=options_data,
                    fred=fred,
                    scan_run_id=scan_id,
                    enrichment=enrichment,
                )

                # run_recommendation() handles persistence internally.
                # Get the latest recommendation ID for linking.
                recent = await repo.get_recommendations_for_ticker(ticker, limit=1)
                rec_id = recent[0].id if recent else None

                direction = result.recommendation.direction
                confidence = result.recommendation.confidence
                results.append(
                    BatchTickerResult(
                        ticker=ticker,
                        debate_id=rec_id,
                        direction=direction,
                        confidence=confidence,
                    )
                )
                bridge.batch_progress(ticker, idx + 1, len(tickers), "completed")

            except Exception:
                logger.exception("Batch recommendation failed for %s", ticker)
                results.append(
                    BatchTickerResult(ticker=ticker, error=f"Recommendation failed for {ticker}")
                )
                bridge.batch_progress(ticker, idx + 1, len(tickers), "failed")

        bridge.batch_complete(results)
    except Exception:
        logger.exception("Batch %d failed unexpectedly", batch_id)
        bridge.error(f"Batch recommendation {batch_id} failed")
        bridge.batch_complete(results)
    finally:
        lock.release()
        # Clean up (initialized in lifespan)
        request.app.state.batch_queues.pop(batch_id, None)


@router.post("/debate/batch", status_code=202)
@limiter.limit("5/minute")
async def start_batch_debate(
    request: Request,
    body: BatchDebateRequest,
    lock: asyncio.Lock = Depends(get_operation_lock),
    settings: AppSettings = Depends(get_settings),
    repo: Repository = Depends(get_repo),
    market_data: MarketDataService = Depends(get_market_data),
    options_data: OptionsDataService = Depends(get_options_data),
    fred: FredService = Depends(get_fred),
) -> BatchDebateStarted:
    """Start a batch recommendation for top N tickers from a scan."""
    # Resolve routing overlay — apply runtime override if active
    effective_settings = _resolve_routing_overlay(request, settings)

    # Determine tickers to debate (before acquiring lock — these are read-only ops)
    if body.tickers is not None:
        tickers = [t.upper() for t in body.tickers]
    else:
        all_scores = await repo.get_scores_for_scan(body.scan_id)
        if not all_scores:
            raise HTTPException(404, "Scan not found or has no scores")
        all_scores.sort(key=lambda s: s.composite_score, reverse=True)
        tickers = [s.ticker for s in all_scores[: body.limit]]

    if not tickers:
        raise HTTPException(422, "No tickers to debate")

    # Atomic try-acquire: eliminates TOCTOU race between lock.locked() and acquire()
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(409, "Another operation is in progress") from None

    # Allocate batch ID (initialized in lifespan)
    batch_id: int = next(request.app.state.batch_counter)

    bridge = BatchProgressBridge()
    request.app.state.batch_queues[batch_id] = bridge.queue

    # Guard create_task — if it fails, release lock to avoid permanent hold.
    try:
        task = asyncio.create_task(
            _run_batch_recommendation_background(
                request,
                batch_id,
                tickers,
                body.scan_id,
                effective_settings,
                repo,
                market_data,
                options_data,
                fred,
                bridge,
                lock,
            )
        )
    except BaseException:
        lock.release()
        raise
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return BatchDebateStarted(batch_id=batch_id, tickers=tickers)


@router.get("/debate")
@limiter.limit("60/minute")
async def list_debates(
    request: Request,
    repo: Repository = Depends(get_repo),
    ticker: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> list[DebateResultSummary]:
    """List past debate summaries.

    Returns summaries from both recommendation_results and ai_theses tables,
    merged and sorted by creation time (newest first).
    """
    # Gather recommendation summaries
    rec_summaries: list[DebateResultSummary] = []
    try:
        if ticker is not None:
            ticker_upper = ticker.upper()
            if not TICKER_RE.match(ticker_upper):
                raise HTTPException(422, "Invalid ticker format")
            rec_rows = await repo.get_recommendations_for_ticker(ticker_upper, limit=limit)
        else:
            rec_rows = await repo.get_recent_recommendations(limit=limit)

        for rr in rec_rows:
            created_at = datetime.fromisoformat(rr.created_at)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            direction = SignalDirection(rr.direction) if rr.direction else SignalDirection.NEUTRAL
            rec_summaries.append(
                DebateResultSummary(
                    id=rr.id,
                    ticker=rr.ticker,
                    direction=direction,
                    confidence=rr.confidence,
                    is_fallback=rr.is_fallback,
                    model_name=rr.model_used,
                    duration_ms=rr.duration_ms,
                    created_at=created_at,
                )
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning("Failed to fetch recommendation summaries", exc_info=True)

    # Gather old debate summaries
    debate_summaries: list[DebateResultSummary] = []
    try:
        if ticker is not None:
            ticker_upper = ticker.upper()
            if not TICKER_RE.match(ticker_upper):
                raise HTTPException(422, "Invalid ticker format")
            rows = await repo.get_debates_for_ticker(ticker_upper, limit=limit)
        else:
            rows = await repo.get_recent_debates(limit=limit)

        for row in rows:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0
            if row.verdict_json is not None:
                from pydantic import ValidationError as PydanticValidationError  # noqa: PLC0415

                try:
                    parsed_verdict: TradeThesis
                    try:
                        parsed_verdict = ExtendedTradeThesis.model_validate_json(row.verdict_json)
                    except PydanticValidationError:
                        parsed_verdict = TradeThesis.model_validate_json(row.verdict_json)
                    direction = parsed_verdict.direction
                    confidence = parsed_verdict.confidence
                except PydanticValidationError:
                    logger.warning(
                        "Failed to parse verdict JSON for debate %d", row.id, exc_info=True
                    )

            debate_summaries.append(
                DebateResultSummary(
                    id=row.id,
                    ticker=row.ticker,
                    direction=direction,
                    confidence=confidence,
                    is_fallback=row.is_fallback,
                    model_name=row.model_name,
                    duration_ms=row.duration_ms,
                    created_at=row.created_at,
                )
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning("Failed to fetch debate summaries", exc_info=True)

    # Merge and sort by creation time (newest first), cap at limit
    all_summaries = rec_summaries + debate_summaries
    all_summaries.sort(key=lambda s: s.created_at, reverse=True)
    return all_summaries[:limit]


def _parse_agent_json[T: BaseModel](
    model_cls: type[T],
    raw_json: str | None,
    field_name: str,
    debate_id: int,
) -> T | None:
    """Parse agent JSON with graceful degradation.

    Returns ``None`` and logs a warning if the stored JSON is malformed,
    matching the export route's ``contextlib.suppress`` pattern.
    """
    if not raw_json:
        return None
    try:
        return model_cls.model_validate_json(raw_json)
    except (ValueError, TypeError):
        logger.warning("Malformed %s for debate %d", field_name, debate_id, exc_info=True)
        return None


@router.get("/debate/{debate_id}")
@limiter.limit("60/minute")
async def get_debate(
    request: Request,
    debate_id: int,
    repo: Repository = Depends(get_repo),
    settings: AppSettings = Depends(get_settings),
) -> RecommendationResponse | DebateResultDetail:
    """Get full debate/recommendation result by ID.

    Dual-table lookup: checks recommendation_results first (new data),
    then falls back to ai_theses (old data). Returns 404 if both miss.
    """
    # First: try recommendation_results table (new data)
    rec_row = await repo.get_recommendation_by_id(debate_id)
    if rec_row is not None:
        return _recommendation_row_to_response(rec_row, settings.debate.recommendation_protocol)

    # Second: try ai_theses table (old data — backward compat)
    row = await repo.get_debate_by_id(debate_id)
    if row is None:
        raise HTTPException(404, "Debate not found")

    # Parse stored JSON into typed models (old debate format)
    bull = AgentResponse.model_validate_json(row.bull_json) if row.bull_json else None
    bear = AgentResponse.model_validate_json(row.bear_json) if row.bear_json else None

    # Try ExtendedTradeThesis first (6-agent protocol), fall back to TradeThesis
    thesis: TradeThesis | None = None
    contrarian_dissent: str | None = None
    agent_agreement_score: float | None = None
    dissenting_agents: list[str] = []
    agents_completed: int | None = None
    if row.verdict_json:
        from pydantic import ValidationError as PydanticValidationError  # noqa: PLC0415

        try:
            ext_thesis = ExtendedTradeThesis.model_validate_json(row.verdict_json)
            thesis = ext_thesis
            contrarian_dissent = ext_thesis.contrarian_dissent
            agent_agreement_score = ext_thesis.agent_agreement_score
            dissenting_agents = list(ext_thesis.dissenting_agents)
            agents_completed = ext_thesis.agents_completed
        except PydanticValidationError:
            try:
                thesis = TradeThesis.model_validate_json(row.verdict_json)
            except PydanticValidationError:
                logger.warning(
                    "Failed to parse verdict JSON for debate %d",
                    debate_id,
                    exc_info=True,
                )

    mc = row.market_context

    # Fetch spread data if debate is linked to a scan (#521)
    spread_detail: SpreadDetail | None = None
    if row.scan_run_id is not None:
        try:
            spread_analysis = await repo.get_spread_for_ticker(row.scan_run_id, row.ticker)
            if spread_analysis is not None:
                spread_detail = spread_detail_from_analysis(spread_analysis)
        except Exception:
            logger.warning(
                "Failed to fetch spread for debate %d ticker %s",
                debate_id,
                row.ticker,
                exc_info=True,
            )

    return DebateResultDetail(
        id=row.id,
        ticker=row.ticker,
        is_fallback=row.is_fallback,
        model_name=row.model_name,
        duration_ms=row.duration_ms,
        total_tokens=row.total_tokens,
        created_at=row.created_at,
        debate_mode=row.debate_mode,
        citation_density=row.citation_density,
        bull_response=bull,
        bear_response=bear,
        thesis=thesis,
        vol_response=row.vol_json,
        bull_rebuttal=row.rebuttal_json,
        contrarian_dissent=contrarian_dissent,
        agent_agreement_score=agent_agreement_score,
        dissenting_agents=dissenting_agents,
        agents_completed=agents_completed,
        # Agent structured outputs — graceful degradation for malformed JSON
        flow_response=_parse_agent_json(FlowThesis, row.flow_json, "flow_json", debate_id),
        fundamental_response=_parse_agent_json(
            FundamentalThesis, row.fundamental_json, "fundamental_json", debate_id
        ),
        risk_response=_parse_agent_json(
            RiskAssessment, row.risk_assessment_json, "risk_assessment_json", debate_id
        ),
        contrarian_response=_parse_agent_json(
            ContrarianThesis, row.contrarian_json, "contrarian_json", debate_id
        ),
        scan_run_id=row.scan_run_id,
        # Native Quant: HV & vol surface metrics
        hv_yang_zhang=mc.hv_yang_zhang if mc else None,
        skew_25d=mc.skew_25d if mc else None,
        smile_curvature=mc.smile_curvature if mc else None,
        prob_above_current=mc.prob_above_current if mc else None,
        # Native Quant: second-order Greeks on target contract
        target_vanna=mc.target_vanna if mc else None,
        target_charm=mc.target_charm if mc else None,
        target_vomma=mc.target_vomma if mc else None,
        # Spread strategy (#521)
        spread=spread_detail,
    )
