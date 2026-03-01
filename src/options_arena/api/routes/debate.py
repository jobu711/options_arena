"""Debate endpoints — start, list, get result, batch."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from options_arena.agents import DebateResult, run_debate_v2
from options_arena.api.deps import (
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
)
from options_arena.api.ws import BatchProgressBridge, DebateProgressBridge
from options_arena.data import Repository
from options_arena.models import AgentResponse, AppSettings, ExtendedTradeThesis, TradeThesis
from options_arena.scoring import compute_dimensional_scores
from options_arena.services import MarketDataService, OptionsDataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["debate"])


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------


async def _run_debate_background(
    request: Request,
    debate_id: int,
    ticker: str,
    scan_id: int | None,
    settings: AppSettings,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    bridge: DebateProgressBridge,
) -> None:
    """Run the debate orchestrator as a background task."""
    try:
        # Fetch data for the ticker
        quote = await market_data.fetch_quote(ticker)
        ticker_info = await market_data.fetch_ticker_info(ticker)

        # Get contracts (from scan results if scan_id provided, else fetch fresh)
        contracts = []
        if scan_id is not None:
            all_scores = await repo.get_scores_for_scan(scan_id)
            score_match = next((s for s in all_scores if s.ticker == ticker), None)
        else:
            score_match = None

        if score_match is None:
            # Create a minimal TickerScore for the debate
            from options_arena.models import IndicatorSignals, SignalDirection, TickerScore

            score_match = TickerScore(
                ticker=ticker,
                composite_score=50.0,
                direction=SignalDirection.NEUTRAL,
                signals=IndicatorSignals(),
            )

        # Fetch fresh option chains
        chain_results = await options_data.fetch_chain_all_expirations(ticker)
        for chain in chain_results:
            contracts.extend(chain.contracts)

        # Enrich with options-specific indicators from the full chain
        if contracts:
            from options_arena.scan.indicators import (  # noqa: PLC0415
                compute_options_indicators,
            )

            spot = float(ticker_info.current_price)
            options_signals = compute_options_indicators(contracts, spot)
            if options_signals.put_call_ratio is not None:
                score_match.signals.put_call_ratio = options_signals.put_call_ratio
            if options_signals.max_pain_distance is not None:
                score_match.signals.max_pain_distance = options_signals.max_pain_distance

        # Compute dimensional scores for the v2 protocol
        dim_scores = None
        try:
            dim_scores = compute_dimensional_scores(score_match.signals)
        except Exception:
            logger.debug("Could not compute dimensional scores for %s", ticker, exc_info=True)

        result: DebateResult = await run_debate_v2(
            ticker_score=score_match,
            contracts=contracts,
            quote=quote,
            ticker_info=ticker_info,
            config=settings.debate,
            repository=None,  # Route handles persistence — avoid double save
            progress=bridge,
            dimensional_scores=dim_scores,
        )

        # Persist debate to DB
        total_tokens = result.total_usage.input_tokens + result.total_usage.output_tokens
        await repo.save_debate(
            scan_run_id=scan_id,
            ticker=ticker,
            bull_json=result.bull_response.model_dump_json(),
            bear_json=result.bear_response.model_dump_json(),
            risk_json=result.thesis.model_dump_json(),
            verdict_json=result.thesis.model_dump_json(),
            total_tokens=total_tokens,
            model_name=(
                settings.debate.model if not result.is_fallback else "data-driven-fallback"
            ),
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
        )

        bridge.complete(debate_id)
    except Exception:
        logger.exception("Debate %d for %s failed", debate_id, ticker)
        bridge.error(f"Debate failed for {ticker}")
        bridge.complete(debate_id)
    finally:
        # Clean up
        debate_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
            request.app.state, "debate_queues", {}
        )
        debate_queues.pop(debate_id, None)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@router.post("/debate", status_code=202)
async def start_debate(
    request: Request,
    body: DebateRequest,
    settings: AppSettings = Depends(get_settings),
    repo: Repository = Depends(get_repo),
    market_data: MarketDataService = Depends(get_market_data),
    options_data: OptionsDataService = Depends(get_options_data),
) -> DebateStarted:
    """Start a single-ticker debate in the background."""
    bridge = DebateProgressBridge()

    # Use a counter for debate IDs since we don't pre-persist
    if not hasattr(request.app.state, "debate_counter"):
        request.app.state.debate_counter = 0
    request.app.state.debate_counter += 1
    debate_id: int = request.app.state.debate_counter

    if not hasattr(request.app.state, "debate_queues"):
        request.app.state.debate_queues = {}

    request.app.state.debate_queues[debate_id] = bridge.queue

    asyncio.create_task(
        _run_debate_background(
            request,
            debate_id,
            body.ticker.upper(),
            body.scan_id,
            settings,
            repo,
            market_data,
            options_data,
            bridge,
        )
    )
    return DebateStarted(debate_id=debate_id)


# ---------------------------------------------------------------------------
# Batch debate
# ---------------------------------------------------------------------------


async def _run_batch_debate_background(
    request: Request,
    batch_id: int,
    tickers: list[str],
    scan_id: int,
    settings: AppSettings,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    bridge: BatchProgressBridge,
    lock: asyncio.Lock,
) -> None:
    """Run sequential debates for a batch of tickers.

    The lock is already acquired by the caller — this task releases it on completion.
    """
    results: list[BatchTickerResult] = []
    try:
        all_scores = await repo.get_scores_for_scan(scan_id)
        for idx, ticker in enumerate(tickers):
            bridge.batch_progress(ticker, idx + 1, len(tickers), "started")
            try:
                quote = await market_data.fetch_quote(ticker)
                ticker_info = await market_data.fetch_ticker_info(ticker)

                score_match = next((s for s in all_scores if s.ticker == ticker), None)
                if score_match is None:
                    from options_arena.models import (  # noqa: PLC0415
                        IndicatorSignals,
                        SignalDirection,
                        TickerScore,
                    )

                    score_match = TickerScore(
                        ticker=ticker,
                        composite_score=50.0,
                        direction=SignalDirection.NEUTRAL,
                        signals=IndicatorSignals(),
                    )

                contracts = []
                chain_results = await options_data.fetch_chain_all_expirations(ticker)
                for chain in chain_results:
                    contracts.extend(chain.contracts)

                # Enrich with options-specific indicators from the full chain
                if contracts:
                    from options_arena.scan.indicators import (  # noqa: PLC0415
                        compute_options_indicators,
                    )

                    batch_spot = float(ticker_info.current_price)
                    options_signals = compute_options_indicators(contracts, batch_spot)
                    if options_signals.put_call_ratio is not None:
                        score_match.signals.put_call_ratio = options_signals.put_call_ratio
                    if options_signals.max_pain_distance is not None:
                        score_match.signals.max_pain_distance = options_signals.max_pain_distance

                # Compute dimensional scores for the v2 protocol
                batch_dim_scores = None
                try:
                    batch_dim_scores = compute_dimensional_scores(score_match.signals)
                except Exception:
                    logger.debug(
                        "Could not compute dimensional scores for %s", ticker, exc_info=True
                    )

                # Create a per-ticker agent bridge that forwards to the batch bridge
                agent_bridge = bridge.agent_bridge(ticker)

                result: DebateResult = await run_debate_v2(
                    ticker_score=score_match,
                    contracts=contracts,
                    quote=quote,
                    ticker_info=ticker_info,
                    config=settings.debate,
                    repository=None,  # Route handles persistence — avoid double save
                    progress=agent_bridge,
                    dimensional_scores=batch_dim_scores,
                )

                total_tokens = result.total_usage.input_tokens + result.total_usage.output_tokens
                debate_id = await repo.save_debate(
                    scan_run_id=scan_id,
                    ticker=ticker,
                    bull_json=result.bull_response.model_dump_json(),
                    bear_json=result.bear_response.model_dump_json(),
                    risk_json=result.thesis.model_dump_json(),
                    verdict_json=result.thesis.model_dump_json(),
                    total_tokens=total_tokens,
                    model_name=(
                        settings.debate.model if not result.is_fallback else "data-driven-fallback"
                    ),
                    duration_ms=result.duration_ms,
                    is_fallback=result.is_fallback,
                    vol_json=(
                        result.vol_response.model_dump_json()
                        if result.vol_response is not None
                        else None
                    ),
                    rebuttal_json=(
                        result.bull_rebuttal.model_dump_json()
                        if result.bull_rebuttal is not None
                        else None
                    ),
                )

                direction = result.thesis.direction.value
                confidence = result.thesis.confidence
                results.append(
                    BatchTickerResult(
                        ticker=ticker,
                        debate_id=debate_id,
                        direction=direction,
                        confidence=confidence,
                    )
                )
                bridge.batch_progress(ticker, idx + 1, len(tickers), "completed")

            except Exception:
                logger.exception("Batch debate failed for %s", ticker)
                results.append(
                    BatchTickerResult(ticker=ticker, error=f"Debate failed for {ticker}")
                )
                bridge.batch_progress(ticker, idx + 1, len(tickers), "failed")

        bridge.batch_complete(results)
    except Exception:
        logger.exception("Batch %d failed unexpectedly", batch_id)
        bridge.error(f"Batch debate {batch_id} failed")
        bridge.batch_complete(results)
    finally:
        lock.release()
        batch_queues: dict[int, asyncio.Queue[dict[str, object]]] = getattr(
            request.app.state, "batch_queues", {}
        )
        batch_queues.pop(batch_id, None)


@router.post("/debate/batch", status_code=202)
async def start_batch_debate(
    request: Request,
    body: BatchDebateRequest,
    lock: asyncio.Lock = Depends(get_operation_lock),
    settings: AppSettings = Depends(get_settings),
    repo: Repository = Depends(get_repo),
    market_data: MarketDataService = Depends(get_market_data),
    options_data: OptionsDataService = Depends(get_options_data),
) -> BatchDebateStarted:
    """Start a batch debate for top N tickers from a scan."""
    if lock.locked():
        raise HTTPException(409, "Another operation is in progress")

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

    # Acquire the lock atomically before creating the background task
    if lock.locked():
        raise HTTPException(409, "Another operation is in progress")
    await lock.acquire()

    # Allocate batch ID
    if not hasattr(request.app.state, "batch_counter"):
        request.app.state.batch_counter = 0
    request.app.state.batch_counter += 1
    batch_id: int = request.app.state.batch_counter

    if not hasattr(request.app.state, "batch_queues"):
        request.app.state.batch_queues = {}

    bridge = BatchProgressBridge()
    request.app.state.batch_queues[batch_id] = bridge.queue

    asyncio.create_task(
        _run_batch_debate_background(
            request,
            batch_id,
            tickers,
            body.scan_id,
            settings,
            repo,
            market_data,
            options_data,
            bridge,
            lock,
        )
    )

    return BatchDebateStarted(batch_id=batch_id, tickers=tickers)


@router.get("/debate")
async def list_debates(
    repo: Repository = Depends(get_repo),
    ticker: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> list[DebateResultSummary]:
    """List past debate summaries."""
    if ticker is not None:
        rows = await repo.get_debates_for_ticker(ticker.upper(), limit=limit)
    else:
        rows = await repo.get_recent_debates(limit=limit)

    summaries: list[DebateResultSummary] = []
    for row in rows:
        # Parse verdict to extract direction + confidence
        direction = "neutral"
        confidence = 0.0
        if row.verdict_json is not None:
            from pydantic import ValidationError as PydanticValidationError  # noqa: PLC0415

            try:
                # Try ExtendedTradeThesis first, fall back to TradeThesis
                parsed_verdict: TradeThesis
                try:
                    parsed_verdict = ExtendedTradeThesis.model_validate_json(row.verdict_json)
                except PydanticValidationError:
                    parsed_verdict = TradeThesis.model_validate_json(row.verdict_json)
                direction = parsed_verdict.direction.value
                confidence = parsed_verdict.confidence
            except PydanticValidationError:
                logger.warning("Failed to parse verdict JSON for debate %d", row.id, exc_info=True)

        summaries.append(
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
    return summaries


@router.get("/debate/{debate_id}")
async def get_debate(
    debate_id: int,
    repo: Repository = Depends(get_repo),
) -> DebateResultDetail:
    """Get full debate result by ID."""
    row = await repo.get_debate_by_id(debate_id)
    if row is None:
        raise HTTPException(404, "Debate not found")

    # Parse stored JSON into typed models
    bull = AgentResponse.model_validate_json(row.bull_json) if row.bull_json else None
    bear = AgentResponse.model_validate_json(row.bear_json) if row.bear_json else None

    # Try ExtendedTradeThesis first (v2 protocol), fall back to TradeThesis
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
    )
