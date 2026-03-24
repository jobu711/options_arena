"""Tests for orchestrator prediction persistence (#768).

Verifies:
- DeskType -> PredictionSource mapping for all 6 desks
- _build_desk_predictions() creates one Prediction per desk with context
- _persist_recommendation() persists desk + synthesis + scan predictions
- Never-raises: recording failures don't crash the recommendation pipeline
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from options_arena.agents.recommendation_orchestrator import (
    _build_desk_predictions,
    _desk_type_to_prediction_source,
    _persist_recommendation,
)
from options_arena.models.attribution import PredictionSource
from options_arena.models.enums import DeskType, SignalDirection
from options_arena.models.recommendation import AnyAssessment
from tests.factories import (
    make_domain_assessment,
    make_market_context,
    make_prediction,
    make_recommendation_result,
)

# ---------------------------------------------------------------------------
# TestDeskTypeToPredictionSource
# ---------------------------------------------------------------------------


class TestDeskTypeToPredictionSource:
    """Verify DeskType -> PredictionSource mapping for all 6 desks."""

    @pytest.mark.parametrize(
        ("desk", "expected"),
        [
            (DeskType.TREND, PredictionSource.DESK_TREND),
            (DeskType.VOLATILITY, PredictionSource.DESK_VOLATILITY),
            (DeskType.FLOW, PredictionSource.DESK_FLOW),
            (DeskType.FUNDAMENTAL, PredictionSource.DESK_FUNDAMENTAL),
            (DeskType.RISK, PredictionSource.DESK_RISK),
            (DeskType.CONTRARIAN, PredictionSource.DESK_CONTRARIAN),
        ],
    )
    def test_mapping(self, desk: DeskType, expected: PredictionSource) -> None:
        assert _desk_type_to_prediction_source(desk) == expected

    def test_research_desk_raises(self) -> None:
        """RESEARCH desk is not mapped — raises ValueError."""
        with pytest.raises(ValueError, match="No prediction source mapping"):
            _desk_type_to_prediction_source(DeskType.RESEARCH)


# ---------------------------------------------------------------------------
# TestBuildDeskPredictions
# ---------------------------------------------------------------------------


class TestBuildDeskPredictions:
    """Verify _build_desk_predictions() creates correct Prediction objects."""

    def test_creates_one_per_desk(self) -> None:
        """6 desk results produce 6 predictions."""
        desks = [
            DeskType.TREND,
            DeskType.VOLATILITY,
            DeskType.FLOW,
            DeskType.FUNDAMENTAL,
            DeskType.RISK,
            DeskType.CONTRARIAN,
        ]
        desk_results = [make_domain_assessment(d) for d in desks]
        context = make_market_context(adx=65.0, iv_rank=42.0, atr_pct=3.5)

        predictions = _build_desk_predictions(
            desk_results,
            rec_id=1,
            ticker="AAPL",
            context=context,
        )

        assert len(predictions) == 6
        sources = {p.source for p in predictions}
        expected_sources = {
            PredictionSource.DESK_TREND,
            PredictionSource.DESK_VOLATILITY,
            PredictionSource.DESK_FLOW,
            PredictionSource.DESK_FUNDAMENTAL,
            PredictionSource.DESK_RISK,
            PredictionSource.DESK_CONTRARIAN,
        }
        assert sources == expected_sources

    def test_context_from_market_context(self) -> None:
        """Prediction context fields match MarketContext values."""
        context = make_market_context(adx=72.0, iv_rank=38.5, atr_pct=4.2)
        desk_results = [make_domain_assessment(DeskType.TREND)]

        predictions = _build_desk_predictions(
            desk_results,
            rec_id=1,
            ticker="AAPL",
            context=context,
        )

        assert len(predictions) == 1
        p = predictions[0]
        assert p.adx == pytest.approx(72.0)
        assert p.iv_rank == pytest.approx(38.5)
        assert p.atr_pct == pytest.approx(4.2)
        assert p.rsi == pytest.approx(context.rsi_14)

    def test_context_none_fields(self) -> None:
        """Prediction created with None context when MarketContext fields are None."""
        context = make_market_context(adx=None, iv_rank=None, atr_pct=None)
        desk_results = [make_domain_assessment(DeskType.FLOW)]

        predictions = _build_desk_predictions(
            desk_results,
            rec_id=1,
            ticker="AAPL",
            context=context,
        )

        assert len(predictions) == 1
        p = predictions[0]
        assert p.adx is None
        assert p.iv_rank is None
        assert p.atr_pct is None

    def test_skips_failed_desks(self) -> None:
        """Empty desk_results produces empty predictions list."""
        context = make_market_context()
        predictions = _build_desk_predictions([], rec_id=1, ticker="AAPL", context=context)
        assert predictions == []

    def test_fallback_assessment_included(self) -> None:
        """Fallback assessments (low confidence) are still recorded as predictions."""
        context = make_market_context()
        # Fallback assessments have confidence=0.2
        fallback = make_domain_assessment(DeskType.TREND, confidence=0.2)

        predictions = _build_desk_predictions([fallback], rec_id=1, ticker="AAPL", context=context)

        assert len(predictions) == 1
        assert predictions[0].confidence == pytest.approx(0.2)
        assert predictions[0].source == PredictionSource.DESK_TREND

    def test_prediction_fields(self) -> None:
        """Prediction captures recommendation_id, ticker, direction, confidence."""
        context = make_market_context()
        assessment = make_domain_assessment(
            DeskType.VOLATILITY,
            direction=SignalDirection.BEARISH,
            confidence=0.65,
        )

        predictions = _build_desk_predictions(
            [assessment], rec_id=42, ticker="MSFT", context=context
        )

        assert len(predictions) == 1
        p = predictions[0]
        assert p.recommendation_id == 42
        assert p.ticker == "MSFT"
        assert p.source == PredictionSource.DESK_VOLATILITY
        assert p.predicted_direction == SignalDirection.BEARISH
        assert p.confidence == pytest.approx(0.65)
        assert p.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# TestOrchestratorPredictionPersistence
# ---------------------------------------------------------------------------


class TestOrchestratorPredictionPersistence:
    """Verify _persist_recommendation() persists predictions correctly."""

    @pytest.mark.asyncio
    async def test_predictions_persisted_after_recommendation(self) -> None:
        """save_predictions_batch called with desk + synthesis predictions."""
        rec_result = make_recommendation_result(ticker="AAPL")
        desk_results = [
            make_domain_assessment(DeskType.TREND),
            make_domain_assessment(DeskType.VOLATILITY),
        ]

        repo = AsyncMock()
        repo.save_recommendation = AsyncMock(return_value=10)
        repo.save_predictions_batch = AsyncMock(return_value=[1, 2, 3])

        assessments: list[AnyAssessment] = []  # unused in new impl

        await _persist_recommendation(
            rec_result,
            repo,
            scan_run_id=5,
            assessments=assessments,
            ticker="AAPL",
            desk_results=desk_results,
        )

        repo.save_predictions_batch.assert_called_once()
        predictions = repo.save_predictions_batch.call_args[0][0]

        # 2 desk + 1 synthesis = 3
        assert len(predictions) == 3

        sources = {p.source for p in predictions}
        assert PredictionSource.DESK_TREND in sources
        assert PredictionSource.DESK_VOLATILITY in sources
        assert PredictionSource.SYNTHESIS in sources

        # All predictions have recommendation_id from save_recommendation
        for p in predictions:
            assert p.recommendation_id == 10
            assert p.ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_synthesis_prediction_direction(self) -> None:
        """Synthesis prediction captures recommendation direction and confidence."""
        rec_result = make_recommendation_result(ticker="TSLA")

        repo = AsyncMock()
        repo.save_recommendation = AsyncMock(return_value=20)
        repo.save_predictions_batch = AsyncMock(return_value=[1])

        await _persist_recommendation(
            rec_result,
            repo,
            scan_run_id=None,
            assessments=[],
            ticker="TSLA",
        )

        repo.save_predictions_batch.assert_called_once()
        predictions = repo.save_predictions_batch.call_args[0][0]

        # Only synthesis (no desk_results passed)
        assert len(predictions) == 1
        synth = predictions[0]
        assert synth.source == PredictionSource.SYNTHESIS
        assert synth.predicted_direction == rec_result.recommendation.direction
        assert synth.confidence == pytest.approx(float(rec_result.recommendation.confidence))

    @pytest.mark.asyncio
    async def test_scan_predictions_get_real_scan_run_id(self) -> None:
        """Placeholder scan_run_id=0 replaced with actual scan_run_id."""
        rec_result = make_recommendation_result(ticker="AAPL")

        # Create scan predictions with placeholder scan_run_id=0
        scan_pred = make_prediction(
            scan_run_id=0,
            recommendation_id=None,
            ticker="AAPL",
            source=PredictionSource.SCAN_DIRECTION,
        )

        repo = AsyncMock()
        repo.save_recommendation = AsyncMock(return_value=15)
        repo.save_predictions_batch = AsyncMock(return_value=[1, 2])

        await _persist_recommendation(
            rec_result,
            repo,
            scan_run_id=7,
            assessments=[],
            ticker="AAPL",
            scan_predictions=[scan_pred],
        )

        repo.save_predictions_batch.assert_called_once()
        predictions = repo.save_predictions_batch.call_args[0][0]

        # 1 synthesis + 1 scan = 2
        assert len(predictions) == 2

        scan_predictions = [p for p in predictions if p.source == PredictionSource.SCAN_DIRECTION]
        assert len(scan_predictions) == 1
        assert scan_predictions[0].scan_run_id == 7
        assert scan_predictions[0].recommendation_id == 15

    @pytest.mark.asyncio
    async def test_scan_predictions_skipped_without_scan_run_id(self) -> None:
        """Scan predictions NOT persisted if scan_run_id is None."""
        rec_result = make_recommendation_result(ticker="AAPL")
        scan_pred = make_prediction(
            scan_run_id=0,
            recommendation_id=None,
            ticker="AAPL",
            source=PredictionSource.SCAN_DIRECTION,
        )

        repo = AsyncMock()
        repo.save_recommendation = AsyncMock(return_value=10)
        repo.save_predictions_batch = AsyncMock(return_value=[1])

        await _persist_recommendation(
            rec_result,
            repo,
            scan_run_id=None,
            assessments=[],
            ticker="AAPL",
            scan_predictions=[scan_pred],
        )

        repo.save_predictions_batch.assert_called_once()
        predictions = repo.save_predictions_batch.call_args[0][0]

        # Only synthesis — scan predictions skipped because scan_run_id=None
        assert len(predictions) == 1
        assert predictions[0].source == PredictionSource.SYNTHESIS

    @pytest.mark.asyncio
    async def test_recording_failure_doesnt_crash(self) -> None:
        """Exception in save_predictions_batch is logged, recommendation still returned."""
        rec_result = make_recommendation_result(ticker="AAPL")
        desk_results = [make_domain_assessment(DeskType.TREND)]

        repo = AsyncMock()
        repo.save_recommendation = AsyncMock(return_value=10)
        repo.save_predictions_batch = AsyncMock(side_effect=RuntimeError("DB write failed"))

        # Should NOT raise — never-raises contract
        await _persist_recommendation(
            rec_result,
            repo,
            scan_run_id=5,
            assessments=[],
            ticker="AAPL",
            desk_results=desk_results,
        )

        # save_predictions_batch was attempted
        repo.save_predictions_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_recommendation_failure_skips_predictions(self) -> None:
        """If save_recommendation fails, predictions are not attempted."""
        rec_result = make_recommendation_result(ticker="AAPL")
        desk_results = [make_domain_assessment(DeskType.TREND)]

        repo = AsyncMock()
        repo.save_recommendation = AsyncMock(side_effect=RuntimeError("DB write failed"))
        repo.save_predictions_batch = AsyncMock()

        await _persist_recommendation(
            rec_result,
            repo,
            scan_run_id=5,
            assessments=[],
            ticker="AAPL",
            desk_results=desk_results,
        )

        repo.save_predictions_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_desks_failed_still_records_synthesis(self) -> None:
        """When all desks fail (empty desk_results), synthesis prediction still recorded."""
        rec_result = make_recommendation_result(ticker="AAPL")

        repo = AsyncMock()
        repo.save_recommendation = AsyncMock(return_value=10)
        repo.save_predictions_batch = AsyncMock(return_value=[1])

        await _persist_recommendation(
            rec_result,
            repo,
            scan_run_id=5,
            assessments=[],
            ticker="AAPL",
            desk_results=[],
        )

        repo.save_predictions_batch.assert_called_once()
        predictions = repo.save_predictions_batch.call_args[0][0]

        # Only synthesis — no desk predictions
        assert len(predictions) == 1
        assert predictions[0].source == PredictionSource.SYNTHESIS

    @pytest.mark.asyncio
    async def test_full_pipeline_desk_plus_synthesis_plus_scan(self) -> None:
        """Full scenario: 6 desks + 1 synthesis + 2 scan = 9 predictions."""
        rec_result = make_recommendation_result(ticker="AAPL")
        desks = [
            DeskType.TREND,
            DeskType.VOLATILITY,
            DeskType.FLOW,
            DeskType.FUNDAMENTAL,
            DeskType.RISK,
            DeskType.CONTRARIAN,
        ]
        desk_results = [make_domain_assessment(d) for d in desks]

        scan_preds = [
            make_prediction(
                scan_run_id=0,
                recommendation_id=None,
                ticker="AAPL",
                source=PredictionSource.SCAN_DIRECTION,
            ),
            make_prediction(
                scan_run_id=0,
                recommendation_id=None,
                ticker="AAPL",
                source=PredictionSource.SCAN_DIRECTION,
            ),
        ]

        repo = AsyncMock()
        repo.save_recommendation = AsyncMock(return_value=100)
        repo.save_predictions_batch = AsyncMock(return_value=list(range(1, 10)))

        await _persist_recommendation(
            rec_result,
            repo,
            scan_run_id=50,
            assessments=[],
            ticker="AAPL",
            desk_results=desk_results,
            scan_predictions=scan_preds,
        )

        repo.save_predictions_batch.assert_called_once()
        predictions = repo.save_predictions_batch.call_args[0][0]

        # 6 desk + 1 synthesis + 2 scan = 9
        assert len(predictions) == 9

        desk_sources = {p.source for p in predictions if p.source.value.startswith("desk_")}
        assert len(desk_sources) == 6

        synthesis_preds = [p for p in predictions if p.source == PredictionSource.SYNTHESIS]
        assert len(synthesis_preds) == 1

        scan_direction_preds = [
            p for p in predictions if p.source == PredictionSource.SCAN_DIRECTION
        ]
        assert len(scan_direction_preds) == 2
        for sp in scan_direction_preds:
            assert sp.scan_run_id == 50
            assert sp.recommendation_id == 100
