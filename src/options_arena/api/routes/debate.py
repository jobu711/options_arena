"""Debate endpoints — start, list, get result, batch."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from options_arena.agents import (
    DebateResult,
    effective_batch_ticker_delay,
    extract_agent_predictions,
    run_debate,
)
from options_arena.api.app import limiter
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
    SpreadDetail,
    spread_detail_from_analysis,
)
from options_arena.api.ws import BatchProgressBridge, DebateProgressBridge
from options_arena.data import Repository
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
from options_arena.models.enums import TICKER_RE
from options_arena.models.financial_datasets import FinancialDatasetsPackage
from options_arena.models.intelligence import IntelligencePackage
from options_arena.models.openbb import (
    FundamentalSnapshot,
    NewsSentimentSnapshot,
    UnusualFlowSnapshot,
)
from options_arena.scoring import compute_dimensional_scores, normalize_single_ticker
from options_arena.services import MarketDataService, OptionsDataService
from options_arena.services.financial_datasets import FinancialDatasetsService
from options_arena.services.intelligence import IntelligenceService
from options_arena.services.openbb_service import OpenBBService

logger = logging.getLogger(__name__)

# Strong references to background tasks prevent garbage collection (AUDIT P1-1)
_background_tasks: set[asyncio.Task[None]] = set()

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
            # Compute real indicators from OHLCV so MarketContext has actual data
            # instead of an empty IndicatorSignals (which causes <40% completeness
            # and silent fallback to data-driven mode).
            from options_arena.models import IndicatorSignals, TickerScore
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

            # Determine direction from RAW indicator values — thresholds
            # (e.g. SMA_BULLISH_THRESHOLD=0.5) are calibrated for raw scale.
            adhoc_direction = determine_direction(
                adx=raw_signals.adx or 0.0,
                rsi=raw_signals.rsi or 50.0,
                sma_alignment=raw_signals.sma_alignment or 0.0,
                supertrend=raw_signals.supertrend,
                roc=raw_signals.roc,
            )

            # Single-ticker normalization: scale raw indicators to 0-100 via
            # domain bounds so composite scoring receives comparable values
            # even without a universe for percentile ranking.
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

        # Compute dimensional scores for the 6-agent protocol
        dim_scores = None
        try:
            dim_scores = compute_dimensional_scores(score_match.signals)
        except Exception:
            logger.warning("Could not compute dimensional scores for %s", ticker, exc_info=True)

        # Fetch OpenBB enrichment (never-raises — methods return None on error)
        openbb_svc: OpenBBService | None = getattr(request.app.state, "openbb", None)
        fundamentals: FundamentalSnapshot | None = None
        flow: UnusualFlowSnapshot | None = None
        sentiment: NewsSentimentSnapshot | None = None
        if openbb_svc is not None:
            _openbb_results = await asyncio.gather(
                openbb_svc.fetch_fundamentals(ticker),
                openbb_svc.fetch_unusual_flow(ticker),
                openbb_svc.fetch_news_sentiment(ticker),
                return_exceptions=True,
            )
            if not isinstance(_openbb_results[0], BaseException):
                fundamentals = _openbb_results[0]
            if not isinstance(_openbb_results[1], BaseException):
                flow = _openbb_results[1]
            if not isinstance(_openbb_results[2], BaseException):
                sentiment = _openbb_results[2]

        # Fetch intelligence data (never raises — returns None on error)
        intelligence_svc: IntelligenceService | None = getattr(
            request.app.state, "intelligence", None
        )
        intel: IntelligencePackage | None = None
        if intelligence_svc is not None:
            intel = await intelligence_svc.fetch_intelligence(ticker, float(quote.price))

        # Fetch Financial Datasets enrichment (never raises — returns None on error)
        fd_svc: FinancialDatasetsService | None = getattr(
            request.app.state, "financial_datasets", None
        )
        fd_package: FinancialDatasetsPackage | None = None
        if fd_svc is not None:
            fd_package = await fd_svc.fetch_package(ticker)

        result: DebateResult = await run_debate(
            ticker_score=score_match,
            contracts=contracts,
            quote=quote,
            ticker_info=ticker_info,
            config=settings.debate,
            repository=None,  # Route handles persistence — avoid double save
            progress=bridge,
            dimensional_scores=dim_scores,
            fundamentals=fundamentals,
            flow=flow,
            sentiment=sentiment,
            intelligence=intel,
            fd_package=fd_package,
        )

        # Persist debate to DB
        total_tokens = result.total_usage.input_tokens + result.total_usage.output_tokens
        db_debate_id = await repo.save_debate(
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
            market_context_json=result.context.model_dump_json(),
            flow_thesis=result.flow_response,
            fundamental_thesis=result.fundamental_response,
            risk_assessment=result.risk_response,
            contrarian_thesis=result.contrarian_response,
        )

        # Persist per-agent predictions for accuracy tracking (FR-8)
        predictions = extract_agent_predictions(db_debate_id, result)
        if predictions:
            await repo.save_agent_predictions(predictions)

        bridge.complete(debate_id)
    except Exception:
        logger.exception("Debate %d for %s failed", debate_id, ticker)
        bridge.error(f"Debate failed for {ticker}")
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
) -> DebateStarted:
    """Start a single-ticker debate in the background.

    No operation lock is needed here: single debates are lightweight, short-lived,
    and do not conflict with concurrent access. Only batch debates and scans
    require the mutex (AUDIT-015).

    NOTE: Provider selection (Groq vs Anthropic) is not yet exposed via the API.
    The API uses whatever ``ARENA_DEBATE__PROVIDER`` env var is set (defaults to
    Groq). To use Anthropic from the web UI, set the env var before starting the
    server. The CLI ``--provider`` flag is the only per-invocation override.
    """
    bridge = DebateProgressBridge()

    # Apply per-request debate overrides
    effective_settings = settings
    debate_overrides: dict[str, object] = {}
    if body.enable_rebuttal is not None:
        debate_overrides["enable_rebuttal"] = body.enable_rebuttal
    if body.enable_volatility_agent is not None:
        debate_overrides["enable_volatility_agent"] = body.enable_volatility_agent
    if debate_overrides:
        effective_settings = settings.model_copy(
            update={"debate": settings.debate.model_copy(update=debate_overrides)}
        )

    # Use a counter for debate IDs (initialized in lifespan)
    request.app.state.debate_counter += 1
    debate_id: int = request.app.state.debate_counter

    request.app.state.debate_queues[debate_id] = bridge.queue

    task = asyncio.create_task(
        _run_debate_background(
            request,
            debate_id,
            body.ticker.upper(),
            body.scan_id,
            effective_settings,
            repo,
            market_data,
            options_data,
            bridge,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
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
                quote = await market_data.fetch_quote(ticker)
                ticker_info = await market_data.fetch_ticker_info(ticker)

                score_match = next((s for s in all_scores if s.ticker == ticker), None)
                if score_match is None:
                    from options_arena.models import (  # noqa: PLC0415
                        IndicatorSignals,
                        TickerScore,
                    )
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

                    batch_ohlcv = await market_data.fetch_ohlcv(ticker, period="1y")
                    if batch_ohlcv:
                        batch_df = ohlcv_to_dataframe(batch_ohlcv)
                        batch_raw_signals = compute_indicators(batch_df, INDICATOR_REGISTRY)
                    else:
                        batch_raw_signals = IndicatorSignals()

                    # Determine direction from RAW indicator values — thresholds
                    # are calibrated for raw scale, not normalized 0-100.
                    batch_direction = determine_direction(
                        adx=batch_raw_signals.adx or 0.0,
                        rsi=batch_raw_signals.rsi or 50.0,
                        sma_alignment=batch_raw_signals.sma_alignment or 0.0,
                        supertrend=batch_raw_signals.supertrend,
                        roc=batch_raw_signals.roc,
                    )

                    # Single-ticker normalization for batch ad-hoc tickers
                    batch_normalized = normalize_single_ticker(batch_raw_signals)
                    logger.info("single-ticker normalization applied for %s", ticker)

                    batch_composite = calc_composite(batch_normalized)

                    score_match = TickerScore(
                        ticker=ticker,
                        composite_score=batch_composite,
                        direction=batch_direction,
                        signals=batch_normalized,
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

                # Compute dimensional scores for the 6-agent protocol
                batch_dim_scores = None
                try:
                    batch_dim_scores = compute_dimensional_scores(score_match.signals)
                except Exception:
                    logger.warning(
                        "Could not compute dimensional scores for %s", ticker, exc_info=True
                    )

                # Fetch OpenBB enrichment (never-raises — methods return None on error)
                batch_openbb: OpenBBService | None = getattr(request.app.state, "openbb", None)
                batch_fundamentals: FundamentalSnapshot | None = None
                batch_flow: UnusualFlowSnapshot | None = None
                batch_sentiment: NewsSentimentSnapshot | None = None
                if batch_openbb is not None:
                    _batch_openbb_results = await asyncio.gather(
                        batch_openbb.fetch_fundamentals(ticker),
                        batch_openbb.fetch_unusual_flow(ticker),
                        batch_openbb.fetch_news_sentiment(ticker),
                        return_exceptions=True,
                    )
                    if not isinstance(_batch_openbb_results[0], BaseException):
                        batch_fundamentals = _batch_openbb_results[0]
                    if not isinstance(_batch_openbb_results[1], BaseException):
                        batch_flow = _batch_openbb_results[1]
                    if not isinstance(_batch_openbb_results[2], BaseException):
                        batch_sentiment = _batch_openbb_results[2]

                # Fetch intelligence data (never raises — returns None on error)
                batch_intel_svc: IntelligenceService | None = getattr(
                    request.app.state, "intelligence", None
                )
                batch_intel: IntelligencePackage | None = None
                if batch_intel_svc is not None:
                    batch_intel = await batch_intel_svc.fetch_intelligence(
                        ticker, float(ticker_info.current_price)
                    )

                # Fetch Financial Datasets enrichment (never raises — returns None)
                batch_fd_svc: FinancialDatasetsService | None = getattr(
                    request.app.state, "financial_datasets", None
                )
                batch_fd_package: FinancialDatasetsPackage | None = None
                if batch_fd_svc is not None:
                    batch_fd_package = await batch_fd_svc.fetch_package(ticker)

                # Create a per-ticker agent bridge that forwards to the batch bridge
                agent_bridge = bridge.agent_bridge(ticker)

                result: DebateResult = await run_debate(
                    ticker_score=score_match,
                    contracts=contracts,
                    quote=quote,
                    ticker_info=ticker_info,
                    config=settings.debate,
                    repository=None,  # Route handles persistence — avoid double save
                    progress=agent_bridge,
                    dimensional_scores=batch_dim_scores,
                    fundamentals=batch_fundamentals,
                    flow=batch_flow,
                    sentiment=batch_sentiment,
                    intelligence=batch_intel,
                    fd_package=batch_fd_package,
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
                    market_context_json=result.context.model_dump_json(),
                    flow_thesis=result.flow_response,
                    fundamental_thesis=result.fundamental_response,
                    risk_assessment=result.risk_response,
                    contrarian_thesis=result.contrarian_response,
                )

                # Persist per-agent predictions for accuracy tracking (FR-8)
                batch_predictions = extract_agent_predictions(debate_id, result)
                if batch_predictions:
                    await repo.save_agent_predictions(batch_predictions)

                direction = result.thesis.direction
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
) -> BatchDebateStarted:
    """Start a batch debate for top N tickers from a scan."""
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
    request.app.state.batch_counter += 1
    batch_id: int = request.app.state.batch_counter

    bridge = BatchProgressBridge()
    request.app.state.batch_queues[batch_id] = bridge.queue

    task = asyncio.create_task(
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
    """List past debate summaries."""
    if ticker is not None:
        ticker_upper = ticker.upper()
        if not TICKER_RE.match(ticker_upper):
            raise HTTPException(422, f"Invalid ticker format: {ticker!r}")
        rows = await repo.get_debates_for_ticker(ticker_upper, limit=limit)
    else:
        rows = await repo.get_recent_debates(limit=limit)

    summaries: list[DebateResultSummary] = []
    for row in rows:
        # Parse verdict to extract direction + confidence
        direction = SignalDirection.NEUTRAL
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
                direction = parsed_verdict.direction
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
) -> DebateResultDetail:
    """Get full debate result by ID."""
    row = await repo.get_debate_by_id(debate_id)
    if row is None:
        raise HTTPException(404, "Debate not found")

    # Parse stored JSON into typed models
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

    # Extract OpenBB enrichment from MarketContext (already parsed by Repository)
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
        # OpenBB enrichment fields
        pe_ratio=mc.pe_ratio if mc else None,
        forward_pe=mc.forward_pe if mc else None,
        peg_ratio=mc.peg_ratio if mc else None,
        price_to_book=mc.price_to_book if mc else None,
        debt_to_equity=mc.debt_to_equity if mc else None,
        revenue_growth=mc.revenue_growth if mc else None,
        profit_margin=mc.profit_margin if mc else None,
        net_call_premium=mc.net_call_premium if mc else None,
        net_put_premium=mc.net_put_premium if mc else None,
        news_sentiment_score=mc.news_sentiment if mc else None,
        news_sentiment_label=(mc.news_sentiment_label if mc else None),
        enrichment_ratio=mc.enrichment_ratio() if mc else None,
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
