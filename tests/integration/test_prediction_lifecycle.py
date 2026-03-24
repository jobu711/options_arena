"""Integration tests for the full prediction lifecycle: record -> score -> attribute.

Tests exercise the complete data flow:
  1. Save a scan run and recommendation
  2. Save desk + synthesis predictions
  3. Save recommended contracts + contract outcomes
  4. Run prediction scoring
  5. Query scored predictions
  6. Compute attribution report

Uses in-memory SQLite with all migrations applied. No external API calls.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.learning.prediction_ledger import (
    compute_attribution,
    run_prediction_scoring,
    score_predictions_for_recommendation,
)
from options_arena.models.analytics import ContractOutcome, RecommendedContract
from options_arena.models.attribution import (
    AttributionReport,
    Prediction,
    PredictionSource,
)
from options_arena.models.enums import (
    ExerciseStyle,
    OptionType,
    OutcomeCollectionMethod,
    ScanPreset,
    ScanSource,
    SignalDirection,
)
from options_arena.models.scan import ScanRun

pytestmark = [pytest.mark.db, pytest.mark.integration]


# ---------------------------------------------------------------------------
# Fixtures — in-memory SQLite with all migrations
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database with all migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository backed by the in-memory database."""
    return Repository(db)


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------

_NOW = datetime.now(UTC)


def _make_scan_run() -> ScanRun:
    """Create a ScanRun for test persistence."""
    return ScanRun(
        started_at=_NOW - timedelta(minutes=10),
        completed_at=_NOW - timedelta(minutes=5),
        preset=ScanPreset.SP500,
        source=ScanSource.MANUAL,
        tickers_scanned=100,
        tickers_scored=50,
        recommendations=10,
    )


def _make_recommended_contract(
    scan_run_id: int,
    ticker: str = "AAPL",
) -> RecommendedContract:
    """Create a RecommendedContract linked to a scan run."""
    return RecommendedContract(
        scan_run_id=scan_run_id,
        ticker=ticker,
        option_type=OptionType.CALL,
        strike=Decimal("190.00"),
        bid=Decimal("4.50"),
        ask=Decimal("4.80"),
        last=Decimal("4.65"),
        expiration=date.today() + timedelta(days=45),
        volume=1500,
        open_interest=12000,
        market_iv=0.285,
        exercise_style=ExerciseStyle.AMERICAN,
        delta=0.35,
        gamma=0.025,
        theta=-0.045,
        vega=0.32,
        rho=0.08,
        entry_stock_price=Decimal("185.50"),
        entry_mid=Decimal("4.65"),
        direction=SignalDirection.BULLISH,
        composite_score=72.5,
        risk_free_rate=0.05,
        created_at=_NOW,
    )


def _make_contract_outcome(
    recommended_contract_id: int,
    stock_return_pct: float = 5.0,
) -> ContractOutcome:
    """Create a ContractOutcome with a given stock return."""
    return ContractOutcome(
        recommended_contract_id=recommended_contract_id,
        exit_stock_price=Decimal("195.00"),
        exit_contract_mid=Decimal("9.50"),
        stock_return_pct=stock_return_pct,
        contract_return_pct=102.0,
        is_winner=stock_return_pct > 0.0,
        holding_days=5,
        collection_method=OutcomeCollectionMethod.MARKET,
        collected_at=_NOW,
    )


def _make_prediction(
    recommendation_id: int,
    source: PredictionSource = PredictionSource.DESK_TREND,
    direction: SignalDirection = SignalDirection.BULLISH,
    confidence: float = 0.75,
    ticker: str = "AAPL",
    adx: float | None = 28.0,
    iv_rank: float | None = 45.0,
    atr_pct: float | None = 2.0,
    rsi: float | None = 55.0,
) -> Prediction:
    """Create a Prediction for test use."""
    return Prediction(
        recommendation_id=recommendation_id,
        ticker=ticker,
        source=source,
        predicted_direction=direction,
        confidence=confidence,
        adx=adx,
        iv_rank=iv_rank,
        atr_pct=atr_pct,
        rsi=rsi,
        created_at=_NOW,
    )


async def _setup_scan_and_recommendation(
    repo: Repository,
    ticker: str = "AAPL",
    stock_return_pct: float = 5.0,
) -> tuple[int, int, int]:
    """Set up the full chain: scan_run -> recommendation -> contract -> outcome.

    Returns (scan_run_id, recommendation_id, recommended_contract_id).
    """
    from tests.factories import make_recommendation_result

    # 1. Save a scan run
    scan_run_id = await repo.save_scan_run(_make_scan_run())

    # 2. Save a recommended contract for that scan run + ticker
    contract = _make_recommended_contract(scan_run_id, ticker=ticker)
    await repo.save_recommended_contracts(scan_run_id, [contract])

    # 3. Get the contract ID back
    contracts = await repo.get_contracts_for_scan(scan_run_id)
    assert len(contracts) >= 1
    contract_id = contracts[0].id
    assert contract_id is not None

    # 4. Save a recommendation result linked to that scan_run_id
    rec_result = make_recommendation_result(ticker=ticker)
    recommendation_id = await repo.save_recommendation(rec_result, scan_run_id=scan_run_id)

    # 5. Save a contract outcome with the given stock_return_pct
    outcome = _make_contract_outcome(contract_id, stock_return_pct=stock_return_pct)
    await repo.save_contract_outcomes([outcome])

    return scan_run_id, recommendation_id, contract_id


# ---------------------------------------------------------------------------
# TestPredictionLifecycle
# ---------------------------------------------------------------------------


@pytest.mark.critical
@pytest.mark.asyncio
class TestPredictionLifecycle:
    """Full lifecycle tests: save -> score -> query -> attribute."""

    async def test_full_lifecycle(self, repo: Repository) -> None:
        """Full loop: save -> predict -> collect outcome -> score -> attribute."""
        _scan_run_id, rec_id, _contract_id = await _setup_scan_and_recommendation(
            repo, ticker="AAPL", stock_return_pct=5.0
        )

        # Save 6 desk + 1 synthesis predictions (all bullish)
        desk_sources = [
            PredictionSource.DESK_TREND,
            PredictionSource.DESK_VOLATILITY,
            PredictionSource.DESK_FLOW,
            PredictionSource.DESK_FUNDAMENTAL,
            PredictionSource.DESK_RISK,
            PredictionSource.DESK_CONTRARIAN,
        ]
        predictions = [
            _make_prediction(rec_id, source=src, direction=SignalDirection.BULLISH)
            for src in desk_sources
        ]
        predictions.append(
            _make_prediction(
                rec_id,
                source=PredictionSource.SYNTHESIS,
                direction=SignalDirection.BULLISH,
            )
        )
        ids = await repo.save_predictions_batch(predictions)
        assert len(ids) == 7

        # Score predictions for this recommendation
        scored_count = await score_predictions_for_recommendation(repo, rec_id)
        assert scored_count == 7

        # Query predictions back and verify was_correct is set
        all_preds = await repo.get_predictions(window_days=90)
        assert len(all_preds) == 7
        for p in all_preds:
            assert p.was_correct is True  # stock_return_pct=5.0, bullish -> correct

        # Compute attribution
        report = compute_attribution(all_preds)
        assert isinstance(report, AttributionReport)
        assert report.total_recommendations == 1
        assert report.total_outcomes == 7

        # Every source should show 100% accuracy (all bullish + positive return)
        assert len(report.source_accuracy) == 7
        for sa in report.source_accuracy:
            assert sa.accuracy == pytest.approx(1.0)
            assert sa.total == 1
            assert sa.correct == 1

    async def test_cold_start_no_data(self, repo: Repository) -> None:
        """Zero data -> empty report, no crash."""
        await run_prediction_scoring(repo)  # no crash
        predictions = await repo.get_predictions(90)
        assert predictions == []
        report = compute_attribution(predictions)
        assert report.source_accuracy == []
        assert report.condition_accuracy == []
        assert report.total_recommendations == 0
        assert report.total_outcomes == 0

    async def test_idempotent_scoring(self, repo: Repository) -> None:
        """Scoring predictions twice produces same results."""
        _scan_run_id, rec_id, _contract_id = await _setup_scan_and_recommendation(
            repo, ticker="AAPL", stock_return_pct=3.0
        )

        predictions = [
            _make_prediction(rec_id, source=PredictionSource.DESK_TREND),
            _make_prediction(rec_id, source=PredictionSource.SYNTHESIS),
        ]
        await repo.save_predictions_batch(predictions)

        # Score once
        count1 = await score_predictions_for_recommendation(repo, rec_id)
        assert count1 == 2

        preds_after_first = await repo.get_predictions(90)
        first_scores = [(p.source, p.was_correct) for p in preds_after_first]

        # Score again — should find 0 unscored (already scored)
        count2 = await score_predictions_for_recommendation(repo, rec_id)
        assert count2 == 0

        preds_after_second = await repo.get_predictions(90)
        second_scores = [(p.source, p.was_correct) for p in preds_after_second]

        # Same results
        assert sorted(first_scores) == sorted(second_scores)

    async def test_mixed_outcomes(self, repo: Repository) -> None:
        """Some correct, some incorrect -> accurate percentages."""
        _scan_run_id, rec_id, _contract_id = await _setup_scan_and_recommendation(
            repo,
            ticker="AAPL",
            stock_return_pct=5.0,  # positive return
        )

        # 3 bullish (will be correct) + 3 bearish (will be incorrect)
        predictions = [
            _make_prediction(
                rec_id,
                source=PredictionSource.DESK_TREND,
                direction=SignalDirection.BULLISH,
            ),
            _make_prediction(
                rec_id,
                source=PredictionSource.DESK_VOLATILITY,
                direction=SignalDirection.BULLISH,
            ),
            _make_prediction(
                rec_id,
                source=PredictionSource.SYNTHESIS,
                direction=SignalDirection.BULLISH,
            ),
            _make_prediction(
                rec_id,
                source=PredictionSource.DESK_FLOW,
                direction=SignalDirection.BEARISH,
            ),
            _make_prediction(
                rec_id,
                source=PredictionSource.DESK_FUNDAMENTAL,
                direction=SignalDirection.BEARISH,
            ),
            _make_prediction(
                rec_id,
                source=PredictionSource.DESK_RISK,
                direction=SignalDirection.BEARISH,
            ),
        ]
        await repo.save_predictions_batch(predictions)

        scored = await score_predictions_for_recommendation(repo, rec_id)
        assert scored == 6

        all_preds = await repo.get_predictions(90)
        assert len(all_preds) == 6

        bullish_preds = [p for p in all_preds if p.predicted_direction is SignalDirection.BULLISH]
        bearish_preds = [p for p in all_preds if p.predicted_direction is SignalDirection.BEARISH]

        for p in bullish_preds:
            assert p.was_correct is True
        for p in bearish_preds:
            assert p.was_correct is False

        # Attribution report
        report = compute_attribution(all_preds)
        assert report.total_outcomes == 6

        # Check individual source accuracy
        for sa in report.source_accuracy:
            if sa.source in {
                PredictionSource.DESK_TREND,
                PredictionSource.DESK_VOLATILITY,
                PredictionSource.SYNTHESIS,
            }:
                assert sa.accuracy == pytest.approx(1.0)
            else:
                assert sa.accuracy == pytest.approx(0.0)

    async def test_neutral_predictions_always_incorrect(self, repo: Repository) -> None:
        """NEUTRAL direction predictions are always scored as incorrect."""
        _scan_run_id, rec_id, _contract_id = await _setup_scan_and_recommendation(
            repo, ticker="AAPL", stock_return_pct=5.0
        )

        predictions = [
            _make_prediction(
                rec_id,
                source=PredictionSource.DESK_TREND,
                direction=SignalDirection.NEUTRAL,
            ),
        ]
        await repo.save_predictions_batch(predictions)

        scored = await score_predictions_for_recommendation(repo, rec_id)
        assert scored == 1

        all_preds = await repo.get_predictions(90)
        assert len(all_preds) == 1
        assert all_preds[0].was_correct is False

    async def test_no_outcomes_leaves_predictions_unscored(self, repo: Repository) -> None:
        """Predictions without outcomes remain unscored (was_correct=None)."""
        from tests.factories import make_recommendation_result

        # Create scan_run and recommendation but NO contract outcomes
        scan_run_id = await repo.save_scan_run(_make_scan_run())
        contract = _make_recommended_contract(scan_run_id)
        await repo.save_recommended_contracts(scan_run_id, [contract])

        rec_result = make_recommendation_result(ticker="AAPL")
        rec_id = await repo.save_recommendation(rec_result, scan_run_id=scan_run_id)

        # Save predictions
        predictions = [_make_prediction(rec_id, source=PredictionSource.DESK_TREND)]
        await repo.save_predictions_batch(predictions)

        # Score — no outcomes, so 0 scored
        scored = await score_predictions_for_recommendation(repo, rec_id)
        assert scored == 0

        # Predictions remain unscored
        all_preds = await repo.get_predictions(90)
        assert len(all_preds) == 1
        assert all_preds[0].was_correct is None


# ---------------------------------------------------------------------------
# TestPredictionPerformance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPredictionPerformance:
    """Performance tests for attribution computation."""

    async def test_attribution_under_2_seconds(self) -> None:
        """1,000 predictions -> attribution computed in < 2 seconds."""
        from tests.factories import make_prediction

        predictions = [
            make_prediction(
                was_correct=(i % 2 == 0),
                source=PredictionSource.DESK_TREND
                if i % 3 == 0
                else PredictionSource.DESK_VOLATILITY
                if i % 3 == 1
                else PredictionSource.SYNTHESIS,
                adx=25.0 + (i % 50),
                iv_rank=10.0 + (i % 80),
                atr_pct=1.0 + (i % 30) * 0.1,
                rsi=20.0 + (i % 60),
            )
            for i in range(1000)
        ]

        start = time.monotonic()
        report = compute_attribution(predictions)
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"Attribution took {elapsed:.2f}s, expected < 2.0s"
        assert isinstance(report, AttributionReport)
        assert report.total_outcomes == 1000
        assert len(report.source_accuracy) == 3


# ---------------------------------------------------------------------------
# TestPredictionResilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPredictionResilience:
    """Resilience tests: never-raises contract, failure isolation."""

    async def test_scoring_never_raises(self, repo: Repository) -> None:
        """DB error during scoring -> logged, not raised."""
        # Replace the internal connection with a mock that raises on execute
        mock_conn = AsyncMock()
        mock_conn.execute.side_effect = RuntimeError("DB connection lost")

        original_conn = repo._db._conn  # noqa: SLF001
        repo._db._conn = mock_conn  # noqa: SLF001
        try:
            # run_prediction_scoring has the never-raises contract
            await run_prediction_scoring(repo)  # should NOT raise
        finally:
            repo._db._conn = original_conn  # noqa: SLF001

    async def test_recording_failure_non_blocking(self, repo: Repository) -> None:
        """save_predictions_batch failure -> raises but doesn't corrupt DB state."""

        # First verify DB is healthy
        preds_before = await repo.get_predictions(90)
        assert preds_before == []

        # Attempt to create a prediction with invalid confidence -> validation error
        with pytest.raises(ValueError, match="confidence"):
            Prediction(
                recommendation_id=9999,
                ticker="AAPL",
                source=PredictionSource.DESK_TREND,
                predicted_direction=SignalDirection.BULLISH,
                confidence=-0.5,  # invalid
                created_at=_NOW,
            )

        # DB still works after the failed attempt
        preds_after = await repo.get_predictions(90)
        assert preds_after == []

    async def test_all_desks_wrong_zero_accuracy(self, repo: Repository) -> None:
        """All desks wrong -> 0% accuracy correctly computed."""
        _scan_run_id, rec_id, _contract_id = await _setup_scan_and_recommendation(
            repo,
            ticker="AAPL",
            stock_return_pct=-5.0,  # negative return
        )

        # All bullish predictions -> stock went down -> all incorrect
        desk_sources = [
            PredictionSource.DESK_TREND,
            PredictionSource.DESK_VOLATILITY,
            PredictionSource.DESK_FLOW,
            PredictionSource.DESK_FUNDAMENTAL,
            PredictionSource.DESK_RISK,
            PredictionSource.DESK_CONTRARIAN,
        ]
        predictions = [
            _make_prediction(rec_id, source=src, direction=SignalDirection.BULLISH)
            for src in desk_sources
        ]
        await repo.save_predictions_batch(predictions)

        scored = await score_predictions_for_recommendation(repo, rec_id)
        assert scored == 6

        all_preds = await repo.get_predictions(90)
        for p in all_preds:
            assert p.was_correct is False

        report = compute_attribution(all_preds)
        for sa in report.source_accuracy:
            assert sa.accuracy == pytest.approx(0.0)
            assert sa.correct == 0

    async def test_all_desks_right_full_accuracy(self, repo: Repository) -> None:
        """All desks right -> 100% accuracy correctly computed."""
        _scan_run_id, rec_id, _contract_id = await _setup_scan_and_recommendation(
            repo,
            ticker="AAPL",
            stock_return_pct=8.0,  # positive return
        )

        # All bullish predictions -> stock went up -> all correct
        desk_sources = [
            PredictionSource.DESK_TREND,
            PredictionSource.DESK_VOLATILITY,
            PredictionSource.DESK_FLOW,
            PredictionSource.DESK_FUNDAMENTAL,
            PredictionSource.DESK_RISK,
            PredictionSource.DESK_CONTRARIAN,
            PredictionSource.SYNTHESIS,
        ]
        predictions = [
            _make_prediction(rec_id, source=src, direction=SignalDirection.BULLISH)
            for src in desk_sources
        ]
        await repo.save_predictions_batch(predictions)

        scored = await score_predictions_for_recommendation(repo, rec_id)
        assert scored == 7

        all_preds = await repo.get_predictions(90)
        for p in all_preds:
            assert p.was_correct is True

        report = compute_attribution(all_preds)
        for sa in report.source_accuracy:
            assert sa.accuracy == pytest.approx(1.0)
            assert sa.total == 1
            assert sa.correct == 1

    async def test_bearish_prediction_negative_return_correct(self, repo: Repository) -> None:
        """Bearish prediction with negative stock return is scored as correct."""
        _scan_run_id, rec_id, _contract_id = await _setup_scan_and_recommendation(
            repo, ticker="AAPL", stock_return_pct=-3.0
        )

        predictions = [
            _make_prediction(
                rec_id,
                source=PredictionSource.DESK_CONTRARIAN,
                direction=SignalDirection.BEARISH,
            ),
        ]
        await repo.save_predictions_batch(predictions)

        scored = await score_predictions_for_recommendation(repo, rec_id)
        assert scored == 1

        all_preds = await repo.get_predictions(90)
        assert len(all_preds) == 1
        assert all_preds[0].was_correct is True
