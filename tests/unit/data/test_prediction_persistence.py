"""Tests for prediction persistence — LearningMixin prediction CRUD."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from options_arena.data import Database, Repository
from options_arena.models.attribution import (
    Prediction,
    PredictionAccuracy,
    PredictionSource,
)
from tests.factories import make_prediction

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)
_LATER = datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC)
_OLD = datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def db() -> Database:  # type: ignore[misc]
    database = Database(":memory:")
    await database.connect()

    conn = database.conn

    # Pre-create stub rows for FK validity
    await conn.execute(
        "INSERT INTO scan_runs (id, started_at, preset, source, "
        "tickers_scanned, tickers_scored, recommendations) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, _NOW.isoformat(), "sp500", "manual", 500, 450, 50),
    )
    await conn.execute(
        "INSERT INTO scan_runs (id, started_at, preset, source, "
        "tickers_scanned, tickers_scored, recommendations) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (2, _NOW.isoformat(), "sp500", "manual", 500, 450, 50),
    )
    await conn.execute(
        "INSERT INTO recommendation_results "
        "(id, ticker, direction, confidence, recommended_contract, "
        "entry_price, entry_criteria, exit_criteria, position_size_pct, "
        "risk_reward_ratio, summary, key_factors_json, risk_assessment, "
        "assessments_json, duration_ms, model_used, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            "AAPL",
            "bullish",
            0.75,
            "AAPL 190C 2026-04-18",
            "5.25",
            "entry",
            "exit",
            0.05,
            2.0,
            "Test summary",
            "[]",
            "Low risk",
            "[]",
            2500,
            "test",
            _NOW.isoformat(),
        ),
    )
    await conn.execute(
        "INSERT INTO recommendation_results "
        "(id, ticker, direction, confidence, recommended_contract, "
        "entry_price, entry_criteria, exit_criteria, position_size_pct, "
        "risk_reward_ratio, summary, key_factors_json, risk_assessment, "
        "assessments_json, duration_ms, model_used, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            2,
            "MSFT",
            "bearish",
            0.60,
            "MSFT 380P 2026-04-18",
            "4.00",
            "entry",
            "exit",
            0.05,
            1.5,
            "Test summary",
            "[]",
            "Moderate risk",
            "[]",
            2500,
            "test",
            _NOW.isoformat(),
        ),
    )
    await conn.commit()

    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    return Repository(db)


def _make_pred(**overrides: object) -> Prediction:
    """Test-local helper that delegates to the shared factory with local defaults."""
    defaults: dict[str, object] = {
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return make_prediction(**defaults)


# ---------------------------------------------------------------------------
# Save prediction
# ---------------------------------------------------------------------------


class TestSavePrediction:
    @pytest.mark.asyncio
    async def test_save_single(self, repo: Repository) -> None:
        """Verify saving a single prediction returns a valid row ID."""
        p = _make_pred(recommendation_id=1)
        row_id = await repo.save_prediction(p)
        assert row_id > 0

    @pytest.mark.asyncio
    async def test_save_with_recommendation_id(self, repo: Repository) -> None:
        """Verify prediction with recommendation_id persists and round-trips."""
        p = _make_pred(recommendation_id=1, scan_run_id=None)
        row_id = await repo.save_prediction(p)

        predictions = await repo.get_predictions(window_days=30)
        assert len(predictions) == 1
        assert predictions[0].id == row_id
        assert predictions[0].recommendation_id == 1
        assert predictions[0].scan_run_id is None

    @pytest.mark.asyncio
    async def test_save_with_scan_run_id(self, repo: Repository) -> None:
        """Verify prediction with scan_run_id persists and round-trips."""
        p = _make_pred(
            recommendation_id=None,
            scan_run_id=1,
            source=PredictionSource.SCAN_DIRECTION,
        )
        row_id = await repo.save_prediction(p)

        predictions = await repo.get_predictions(window_days=30)
        assert len(predictions) == 1
        assert predictions[0].id == row_id
        assert predictions[0].scan_run_id == 1
        assert predictions[0].recommendation_id is None

    @pytest.mark.asyncio
    async def test_save_none_context(self, repo: Repository) -> None:
        """Verify context fields (adx, iv_rank, atr_pct, rsi) can all be None."""
        p = _make_pred(recommendation_id=1, adx=None, iv_rank=None, atr_pct=None, rsi=None)
        await repo.save_prediction(p)

        predictions = await repo.get_predictions(window_days=30)
        assert predictions[0].adx is None
        assert predictions[0].iv_rank is None
        assert predictions[0].atr_pct is None
        assert predictions[0].rsi is None

    @pytest.mark.asyncio
    async def test_save_with_context(self, repo: Repository) -> None:
        """Verify context fields round-trip correctly."""
        p = _make_pred(
            recommendation_id=1,
            adx=30.5,
            iv_rank=45.0,
            atr_pct=2.5,
            rsi=55.0,
        )
        await repo.save_prediction(p)

        predictions = await repo.get_predictions(window_days=30)
        assert predictions[0].adx == pytest.approx(30.5, rel=1e-4)
        assert predictions[0].iv_rank == pytest.approx(45.0, rel=1e-4)
        assert predictions[0].atr_pct == pytest.approx(2.5, rel=1e-4)
        assert predictions[0].rsi == pytest.approx(55.0, rel=1e-4)

    @pytest.mark.asyncio
    async def test_duplicate_raises_integrity_error(self, repo: Repository) -> None:
        """Verify UNIQUE(recommendation_id, source) constraint raises IntegrityError."""
        p1 = _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND)
        p2 = _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND)
        await repo.save_prediction(p1)
        with pytest.raises(sqlite3.IntegrityError):
            await repo.save_prediction(p2)


# ---------------------------------------------------------------------------
# Save predictions batch
# ---------------------------------------------------------------------------


class TestSavePredictionsBatch:
    @pytest.mark.asyncio
    async def test_batch_multiple(self, repo: Repository) -> None:
        """Verify batch saving returns correct number of IDs."""
        predictions = [
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND),
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_VOLATILITY),
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_FLOW),
        ]
        ids = await repo.save_predictions_batch(predictions)
        assert len(ids) == 3
        assert all(i > 0 for i in ids)
        assert len(set(ids)) == 3  # all unique

    @pytest.mark.asyncio
    async def test_empty_batch(self, repo: Repository) -> None:
        """Verify empty batch returns empty list."""
        ids = await repo.save_predictions_batch([])
        assert ids == []

    @pytest.mark.asyncio
    async def test_batch_atomicity(self, repo: Repository) -> None:
        """Verify batch uses single commit (commit=True)."""
        predictions = [
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND),
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_VOLATILITY),
        ]
        ids = await repo.save_predictions_batch(predictions)
        assert len(ids) == 2

        # Verify both are retrievable
        stored = await repo.get_predictions(window_days=30)
        assert len(stored) == 2


# ---------------------------------------------------------------------------
# Score predictions
# ---------------------------------------------------------------------------


class TestScorePredictions:
    @pytest.mark.asyncio
    async def test_score_by_recommendation_id(self, repo: Repository) -> None:
        """Verify scoring predictions by recommendation_id sets was_correct."""
        predictions = [
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND),
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_VOLATILITY),
        ]
        await repo.save_predictions_batch(predictions)

        count = await repo.score_predictions(recommendation_id=1, was_correct=True)
        assert count == 2

        stored = await repo.get_predictions(window_days=30)
        assert all(p.was_correct is True for p in stored)

    @pytest.mark.asyncio
    async def test_returns_count(self, repo: Repository) -> None:
        """Verify score_predictions returns the number of rows updated."""
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND)
        )
        count = await repo.score_predictions(recommendation_id=1, was_correct=False)
        assert count == 1

    @pytest.mark.asyncio
    async def test_nonexistent_returns_zero(self, repo: Repository) -> None:
        """Verify scoring a nonexistent recommendation_id returns 0."""
        count = await repo.score_predictions(recommendation_id=9999, was_correct=True)
        assert count == 0

    @pytest.mark.asyncio
    async def test_idempotent(self, repo: Repository) -> None:
        """Verify scoring the same recommendation twice is idempotent."""
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND)
        )
        await repo.score_predictions(recommendation_id=1, was_correct=True)
        count = await repo.score_predictions(recommendation_id=1, was_correct=False)
        assert count == 1

        stored = await repo.get_predictions(window_days=30)
        assert stored[0].was_correct is False


# ---------------------------------------------------------------------------
# Score scan predictions
# ---------------------------------------------------------------------------


class TestScoreScanPredictions:
    @pytest.mark.asyncio
    async def test_score_scan(self, repo: Repository) -> None:
        """Verify scoring scan predictions by scan_run_id + ticker."""
        p = _make_pred(
            recommendation_id=None,
            scan_run_id=1,
            ticker="AAPL",
            source=PredictionSource.SCAN_DIRECTION,
        )
        await repo.save_prediction(p)

        count = await repo.score_scan_predictions(scan_run_id=1, ticker="AAPL", was_correct=True)
        assert count == 1

        stored = await repo.get_predictions(window_days=30)
        assert stored[0].was_correct is True

    @pytest.mark.asyncio
    async def test_only_matching_ticker(self, repo: Repository) -> None:
        """Verify only matching ticker is scored, not other tickers in same scan."""
        p_aapl = _make_pred(
            recommendation_id=None,
            scan_run_id=1,
            ticker="AAPL",
            source=PredictionSource.SCAN_DIRECTION,
        )
        p_msft = _make_pred(
            recommendation_id=None,
            scan_run_id=2,
            ticker="MSFT",
            source=PredictionSource.SCAN_DIRECTION,
        )
        await repo.save_prediction(p_aapl)
        await repo.save_prediction(p_msft)

        count = await repo.score_scan_predictions(scan_run_id=1, ticker="AAPL", was_correct=True)
        assert count == 1

        stored = await repo.get_predictions(window_days=30)
        aapl_pred = next(p for p in stored if p.ticker == "AAPL")
        msft_pred = next(p for p in stored if p.ticker == "MSFT")
        assert aapl_pred.was_correct is True
        assert msft_pred.was_correct is None


# ---------------------------------------------------------------------------
# Get predictions
# ---------------------------------------------------------------------------


class TestGetPredictions:
    @pytest.mark.asyncio
    async def test_within_window(self, repo: Repository) -> None:
        """Verify predictions within the window are returned."""
        await repo.save_prediction(_make_pred(recommendation_id=1))

        predictions = await repo.get_predictions(window_days=30)
        assert len(predictions) == 1
        assert isinstance(predictions[0], Prediction)

    @pytest.mark.asyncio
    async def test_filter_by_source(self, repo: Repository) -> None:
        """Verify source filter works correctly."""
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND)
        )
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_VOLATILITY)
        )

        trend_only = await repo.get_predictions(window_days=30, source=PredictionSource.DESK_TREND)
        assert len(trend_only) == 1
        assert trend_only[0].source == PredictionSource.DESK_TREND

    @pytest.mark.asyncio
    async def test_excludes_old(self, repo: Repository) -> None:
        """Verify predictions older than the window are excluded."""
        await repo.save_prediction(_make_pred(recommendation_id=1, created_at=_OLD))

        predictions = await repo.get_predictions(window_days=7)
        assert len(predictions) == 0

    @pytest.mark.asyncio
    async def test_returns_prediction_models(self, repo: Repository) -> None:
        """Verify returned items are Prediction model instances."""
        await repo.save_prediction(_make_pred(recommendation_id=1, adx=25.0, rsi=55.0))

        predictions = await repo.get_predictions(window_days=30)
        assert len(predictions) == 1
        p = predictions[0]
        assert isinstance(p, Prediction)
        assert p.ticker == "AAPL"
        assert p.adx == pytest.approx(25.0, rel=1e-4)
        assert p.rsi == pytest.approx(55.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Get prediction accuracy
# ---------------------------------------------------------------------------


class TestGetPredictionAccuracy:
    @pytest.mark.asyncio
    async def test_accuracy_computation(self, repo: Repository) -> None:
        """Verify accuracy is computed correctly."""
        # Save 3 predictions, score 2 correct and 1 incorrect
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND)
        )
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_VOLATILITY)
        )
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_FLOW)
        )

        # Score trend and vol as correct, flow as incorrect
        conn = repo._db.conn
        await conn.execute(
            "UPDATE predictions SET was_correct = 1 WHERE source = ?",
            (PredictionSource.DESK_TREND.value,),
        )
        await conn.execute(
            "UPDATE predictions SET was_correct = 1 WHERE source = ?",
            (PredictionSource.DESK_VOLATILITY.value,),
        )
        await conn.execute(
            "UPDATE predictions SET was_correct = 0 WHERE source = ?",
            (PredictionSource.DESK_FLOW.value,),
        )
        await conn.commit()

        results = await repo.get_prediction_accuracy(window_days=30)
        assert len(results) == 3
        assert all(isinstance(r, PredictionAccuracy) for r in results)

        # Each source has 1 prediction, so each has accuracy 1.0 or 0.0
        by_source = {r.source: r for r in results}
        assert by_source[PredictionSource.DESK_TREND].accuracy == pytest.approx(1.0, abs=0.01)
        assert by_source[PredictionSource.DESK_FLOW].accuracy == pytest.approx(0.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_excludes_unscored(self, repo: Repository) -> None:
        """Verify unscored predictions (was_correct IS NULL) are excluded."""
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND)
        )

        results = await repo.get_prediction_accuracy(window_days=30)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_groups_by_source(self, repo: Repository) -> None:
        """Verify accuracy is grouped by source."""
        # 2 trend predictions (both correct), 1 vol prediction (incorrect)
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_TREND)
        )
        await repo.save_prediction(
            _make_pred(recommendation_id=2, source=PredictionSource.DESK_TREND, ticker="MSFT")
        )
        await repo.save_prediction(
            _make_pred(recommendation_id=1, source=PredictionSource.DESK_VOLATILITY)
        )

        await repo.score_predictions(recommendation_id=1, was_correct=True)
        await repo.score_predictions(recommendation_id=2, was_correct=True)

        results = await repo.get_prediction_accuracy(window_days=30)
        by_source = {r.source: r for r in results}

        assert by_source[PredictionSource.DESK_TREND].total == 2
        assert by_source[PredictionSource.DESK_TREND].correct == 2
        assert by_source[PredictionSource.DESK_TREND].accuracy == pytest.approx(1.0, abs=0.01)

        assert by_source[PredictionSource.DESK_VOLATILITY].total == 1
        assert by_source[PredictionSource.DESK_VOLATILITY].correct == 1

    @pytest.mark.asyncio
    async def test_sample_sufficient_flag(self, repo: Repository) -> None:
        """Verify sample_sufficient is True when total >= 10."""
        # Save 10 predictions with same source, all correct
        for i in range(10):
            # Use scan_run_id for uniqueness (since UNIQUE is on scan_run_id, ticker, source)
            conn = repo._db.conn
            await conn.execute(
                "INSERT INTO scan_runs (id, started_at, preset, source, "
                "tickers_scanned, tickers_scored, recommendations) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (100 + i, _NOW.isoformat(), "sp500", "manual", 500, 450, 50),
            )
            await conn.commit()

            p = _make_pred(
                recommendation_id=None,
                scan_run_id=100 + i,
                source=PredictionSource.SCAN_DIRECTION,
                ticker=f"T{i:03d}",
            )
            await repo.save_prediction(p)

        # Score all as correct
        conn = repo._db.conn
        await conn.execute(
            "UPDATE predictions SET was_correct = 1 WHERE source = ?",
            (PredictionSource.SCAN_DIRECTION.value,),
        )
        await conn.commit()

        results = await repo.get_prediction_accuracy(window_days=30)
        scan_acc = next(r for r in results if r.source == PredictionSource.SCAN_DIRECTION)
        assert scan_acc.total == 10
        assert scan_acc.sample_sufficient is True

    @pytest.mark.asyncio
    async def test_empty_data(self, repo: Repository) -> None:
        """Verify empty database returns empty accuracy list."""
        results = await repo.get_prediction_accuracy(window_days=30)
        assert results == []


# ---------------------------------------------------------------------------
# Full lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.critical
@pytest.mark.db
@pytest.mark.asyncio
class TestPredictionLifecycle:
    async def test_save_score_query_accuracy(self, repo: Repository) -> None:
        """Full lifecycle: save 7 predictions, score, query, verify accuracy."""
        # Save 7 predictions: 4 from rec_id=1, 3 from rec_id=2
        rec1_preds = [
            _make_pred(
                recommendation_id=1,
                source=PredictionSource.DESK_TREND,
                confidence=0.80,
                adx=30.0,
            ),
            _make_pred(
                recommendation_id=1,
                source=PredictionSource.DESK_VOLATILITY,
                confidence=0.65,
                iv_rank=45.0,
            ),
            _make_pred(
                recommendation_id=1,
                source=PredictionSource.DESK_FLOW,
                confidence=0.70,
            ),
            _make_pred(
                recommendation_id=1,
                source=PredictionSource.SYNTHESIS,
                confidence=0.75,
            ),
        ]
        rec2_preds = [
            _make_pred(
                recommendation_id=2,
                source=PredictionSource.DESK_TREND,
                confidence=0.60,
                ticker="MSFT",
            ),
            _make_pred(
                recommendation_id=2,
                source=PredictionSource.DESK_RISK,
                confidence=0.55,
                ticker="MSFT",
            ),
            _make_pred(
                recommendation_id=2,
                source=PredictionSource.SYNTHESIS,
                confidence=0.50,
                ticker="MSFT",
            ),
        ]
        all_preds = rec1_preds + rec2_preds
        ids = await repo.save_predictions_batch(all_preds)
        assert len(ids) == 7

        # Score rec_id=1 as correct, rec_id=2 as incorrect
        count1 = await repo.score_predictions(recommendation_id=1, was_correct=True)
        assert count1 == 4
        count2 = await repo.score_predictions(recommendation_id=2, was_correct=False)
        assert count2 == 3

        # Query all predictions
        predictions = await repo.get_predictions(window_days=30)
        assert len(predictions) == 7

        # Verify scoring
        rec1_stored = [p for p in predictions if p.recommendation_id == 1]
        rec2_stored = [p for p in predictions if p.recommendation_id == 2]
        assert all(p.was_correct is True for p in rec1_stored)
        assert all(p.was_correct is False for p in rec2_stored)

        # Verify accuracy
        accuracy_results = await repo.get_prediction_accuracy(window_days=30)
        assert len(accuracy_results) > 0

        # DESK_TREND: 1 correct (rec1) + 1 incorrect (rec2) = 50% accuracy
        by_source = {r.source: r for r in accuracy_results}
        trend_acc = by_source[PredictionSource.DESK_TREND]
        assert trend_acc.total == 2
        assert trend_acc.correct == 1
        assert trend_acc.accuracy == pytest.approx(0.5, abs=0.01)
        assert trend_acc.sample_sufficient is False  # only 2 samples

        # SYNTHESIS: 1 correct (rec1) + 1 incorrect (rec2) = 50% accuracy
        synth_acc = by_source[PredictionSource.SYNTHESIS]
        assert synth_acc.total == 2
        assert synth_acc.correct == 1
        assert synth_acc.accuracy == pytest.approx(0.5, abs=0.01)

        # DESK_VOLATILITY: 1 correct only = 100% accuracy
        vol_acc = by_source[PredictionSource.DESK_VOLATILITY]
        assert vol_acc.total == 1
        assert vol_acc.correct == 1
        assert vol_acc.accuracy == pytest.approx(1.0, abs=0.01)

        # Verify context fields survived
        trend_pred = next(
            p
            for p in predictions
            if p.recommendation_id == 1 and p.source == PredictionSource.DESK_TREND
        )
        assert trend_pred.adx == pytest.approx(30.0, rel=1e-4)
