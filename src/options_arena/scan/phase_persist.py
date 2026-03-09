"""Phase 4: Persist — save scan results to the database and assemble final ScanResult.

Extracted from ``ScanPipeline._phase_persist()`` as a standalone async function.
All service and data dependencies are passed as explicit parameters.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from options_arena.data import Repository
from options_arena.models import (
    NormalizationStats,
    RecommendedContract,
    ScanPreset,
    ScanRun,
    ScanSource,
    SignalDirection,
    TickerScore,
)
from options_arena.scan.models import (
    OptionsResult,
    ScanResult,
    ScoringResult,
    UniverseResult,
)
from options_arena.scan.progress import ProgressCallback, ScanPhase

logger = logging.getLogger(__name__)


async def run_persist_phase(
    *,
    started_at: datetime,
    preset: ScanPreset,
    source: ScanSource,
    universe_result: UniverseResult,
    scoring_result: ScoringResult,
    options_result: OptionsResult,
    progress: ProgressCallback,
    repository: Repository,
) -> ScanResult:
    """Phase 4: Persist scan results to database and assemble final ScanResult.

    Steps:
        1. Build ``ScanRun`` with UTC timestamps.
        2. Save scan run to get DB-assigned ID.
        3. Update each ``TickerScore.scan_run_id``.
        4. Batch-insert ticker scores.
        5. Build and persist ``RecommendedContract`` list.
        6. Persist normalization stats with real scan_run_id.
        7. Atomic commit — all writes succeed or fail together.
        8. Report progress.
        9. Return final ``ScanResult``.

    Args:
        started_at: Pipeline start time (UTC).
        preset: Scan preset used for this run.
        source: How the scan was triggered (CLI, API, etc.).
        universe_result: Phase 1 output with tickers and OHLCV data.
        scoring_result: Phase 2 output with scored tickers and raw signals.
        options_result: Phase 3 output with recommended contracts and risk-free rate.
        progress: Callback for reporting per-phase progress.
        repository: Data layer for persistence.

    Returns:
        ``ScanResult`` with all 4 phases completed and DB-assigned scan ID.
    """
    # Step 1: Build ScanRun
    recommendation_count = sum(
        len(contracts) for contracts in options_result.recommendations.values()
    )
    scan_run = ScanRun(
        started_at=started_at,
        completed_at=datetime.now(UTC),
        preset=preset,
        source=source,
        tickers_scanned=len(universe_result.tickers),
        tickers_scored=len(scoring_result.scores),
        recommendations=recommendation_count,
    )

    # Step 2: Save scan run → get DB-assigned ID
    # All Phase 4 saves use commit=False for atomic persistence;
    # a single commit() at the end ensures all-or-nothing semantics.
    scan_id: int = await repository.save_scan_run(scan_run, commit=False)
    logger.info("Persisted scan run id=%d", scan_id)

    # Step 3: Update scan_run_id on each TickerScore
    for ts in scoring_result.scores:
        ts.scan_run_id = scan_id

    # Step 4: Batch-insert ticker scores
    await repository.save_ticker_scores(scan_id, scoring_result.scores, commit=False)
    logger.info(
        "Persisted %d ticker scores for scan %d",
        len(scoring_result.scores),
        scan_id,
    )

    # Step 5: Build and persist RecommendedContract list
    now_utc = datetime.now(UTC)
    score_map: dict[str, TickerScore] = {ts.ticker: ts for ts in scoring_result.scores}
    recommended_contracts: list[RecommendedContract] = []
    for ticker, contracts in options_result.recommendations.items():
        entry_price = options_result.entry_prices.get(ticker)
        matched_score: TickerScore | None = score_map.get(ticker)
        for contract in contracts:
            entry_mid = contract.mid
            recommended_contracts.append(
                RecommendedContract(
                    scan_run_id=scan_id,
                    ticker=contract.ticker,
                    option_type=contract.option_type,
                    strike=contract.strike,
                    expiration=contract.expiration,
                    bid=contract.bid,
                    ask=contract.ask,
                    last=contract.last,
                    volume=contract.volume,
                    open_interest=contract.open_interest,
                    market_iv=contract.market_iv,
                    exercise_style=contract.exercise_style,
                    delta=(contract.greeks.delta if contract.greeks is not None else None),
                    gamma=(contract.greeks.gamma if contract.greeks is not None else None),
                    theta=(contract.greeks.theta if contract.greeks is not None else None),
                    vega=(contract.greeks.vega if contract.greeks is not None else None),
                    rho=(contract.greeks.rho if contract.greeks is not None else None),
                    pricing_model=(
                        contract.greeks.pricing_model if contract.greeks is not None else None
                    ),
                    greeks_source=contract.greeks_source,
                    entry_stock_price=entry_price,
                    entry_mid=entry_mid,
                    direction=(
                        matched_score.direction
                        if matched_score is not None
                        else SignalDirection.NEUTRAL
                    ),
                    composite_score=(
                        matched_score.composite_score if matched_score is not None else 0.0
                    ),
                    risk_free_rate=options_result.risk_free_rate,
                    created_at=now_utc,
                )
            )

    if recommended_contracts:
        await repository.save_recommended_contracts(scan_id, recommended_contracts, commit=False)
        logger.info(
            "Persisted %d recommended contracts for scan %d",
            len(recommended_contracts),
            scan_id,
        )

    # Step 6: Persist normalization stats with real scan_run_id
    # NormalizationStats is frozen, so rebuild with the correct scan_run_id.
    if scoring_result.normalization_stats:
        real_stats = [
            NormalizationStats(
                scan_run_id=scan_id,
                indicator_name=s.indicator_name,
                ticker_count=s.ticker_count,
                min_value=s.min_value,
                max_value=s.max_value,
                median_value=s.median_value,
                mean_value=s.mean_value,
                std_dev=s.std_dev,
                p25=s.p25,
                p75=s.p75,
                created_at=s.created_at,
            )
            for s in scoring_result.normalization_stats
        ]
        await repository.save_normalization_stats(scan_id, real_stats, commit=False)
        logger.info(
            "Persisted %d normalization stats for scan %d",
            len(real_stats),
            scan_id,
        )

    # Step 7: Atomic commit — all Phase 4 writes succeed or fail together
    await repository.commit()

    # Step 8: Report progress
    progress(ScanPhase.PERSIST, 1, 1)

    # Step 9: Return final ScanResult
    # ScanRun is frozen — reconstruct with ID populated
    final_scan_run = ScanRun(
        id=scan_id,
        started_at=scan_run.started_at,
        completed_at=scan_run.completed_at,
        preset=scan_run.preset,
        source=scan_run.source,
        tickers_scanned=scan_run.tickers_scanned,
        tickers_scored=scan_run.tickers_scored,
        recommendations=scan_run.recommendations,
    )

    return ScanResult(
        scan_run=final_scan_run,
        scores=scoring_result.scores,
        recommendations=options_result.recommendations,
        risk_free_rate=options_result.risk_free_rate,
        earnings_dates=options_result.earnings_dates,
        phases_completed=4,
    )
