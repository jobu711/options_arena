"""Tests for prediction-derived accuracy in weight_tuner.py.

Verifies the mapping from PredictionAccuracy to AgentAccuracyReport, the
render_tuned_weights() function, and the prediction-first / legacy-fallback
behaviour in auto_tune_weights().
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock

import pytest

from options_arena.learning.weight_tuner import (
    AGENT_VOTE_WEIGHTS,
    _prediction_accuracy_to_agent_report,
    auto_tune_weights,
    render_tuned_weights,
)
from options_arena.models import AgentAccuracyReport, AgentWeightsComparison
from options_arena.models.attribution import PredictionAccuracy, PredictionSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pred(
    source: PredictionSource,
    accuracy: float = 0.70,
    total: int = 50,
    correct: int | None = None,
    sample_sufficient: bool = True,
) -> PredictionAccuracy:
    """Shorthand for creating a PredictionAccuracy."""
    if correct is None:
        correct = int(total * accuracy)
    return PredictionAccuracy(
        source=source,
        total=total,
        correct=correct,
        accuracy=accuracy,
        sample_sufficient=sample_sufficient,
    )


def _legacy_report(
    name: str,
    brier: float = 0.20,
    sample_size: int = 50,
) -> AgentAccuracyReport:
    """Shorthand for creating a legacy AgentAccuracyReport."""
    return AgentAccuracyReport(
        agent_name=name,
        direction_hit_rate=0.7,
        mean_confidence=0.65,
        brier_score=brier,
        sample_size=sample_size,
    )


# ---------------------------------------------------------------------------
# TestPredictionAccuracyToAgentReport
# ---------------------------------------------------------------------------


class TestPredictionAccuracyToAgentReport:
    """Tests for _prediction_accuracy_to_agent_report helper."""

    def test_desk_trend_mapping(self) -> None:
        """DESK_TREND maps to agent_name='trend' with accuracy as hit_rate."""
        acc = _pred(PredictionSource.DESK_TREND, accuracy=0.75, total=40)
        report = _prediction_accuracy_to_agent_report(acc)

        assert report.agent_name == "trend"
        assert report.direction_hit_rate == pytest.approx(0.75)
        assert report.mean_confidence == pytest.approx(0.75)
        assert report.brier_score == pytest.approx(0.25)
        assert report.sample_size == 40

    def test_strips_desk_prefix(self) -> None:
        """'desk_volatility' becomes 'volatility'."""
        acc = _pred(PredictionSource.DESK_VOLATILITY, accuracy=0.60, total=30)
        report = _prediction_accuracy_to_agent_report(acc)
        assert report.agent_name == "volatility"

    def test_desk_flow_mapping(self) -> None:
        """DESK_FLOW maps correctly."""
        acc = _pred(PredictionSource.DESK_FLOW, accuracy=0.80, total=60)
        report = _prediction_accuracy_to_agent_report(acc)
        assert report.agent_name == "flow"
        assert report.direction_hit_rate == pytest.approx(0.80)
        assert report.brier_score == pytest.approx(0.20)

    def test_desk_fundamental_mapping(self) -> None:
        """DESK_FUNDAMENTAL maps correctly."""
        acc = _pred(PredictionSource.DESK_FUNDAMENTAL, accuracy=0.55, total=20)
        report = _prediction_accuracy_to_agent_report(acc)
        assert report.agent_name == "fundamental"

    def test_desk_contrarian_mapping(self) -> None:
        """DESK_CONTRARIAN maps correctly."""
        acc = _pred(PredictionSource.DESK_CONTRARIAN, accuracy=0.50, total=15)
        report = _prediction_accuracy_to_agent_report(acc)
        assert report.agent_name == "contrarian"

    def test_desk_risk_mapping(self) -> None:
        """DESK_RISK maps to 'risk'."""
        acc = _pred(PredictionSource.DESK_RISK, accuracy=0.65, total=25)
        report = _prediction_accuracy_to_agent_report(acc)
        assert report.agent_name == "risk"

    def test_brier_score_boundary_perfect(self) -> None:
        """Perfect accuracy (1.0) yields brier_score of 0.0."""
        acc = _pred(PredictionSource.DESK_TREND, accuracy=1.0, total=50, correct=50)
        report = _prediction_accuracy_to_agent_report(acc)
        assert report.brier_score == pytest.approx(0.0)

    def test_brier_score_boundary_zero(self) -> None:
        """Zero accuracy yields brier_score of 1.0."""
        acc = _pred(PredictionSource.DESK_TREND, accuracy=0.0, total=50, correct=0)
        report = _prediction_accuracy_to_agent_report(acc)
        assert report.brier_score == pytest.approx(1.0)

    def test_all_fields_finite(self) -> None:
        """All numeric fields in the report are finite."""
        acc = _pred(PredictionSource.DESK_FLOW, accuracy=0.72, total=35)
        report = _prediction_accuracy_to_agent_report(acc)
        assert math.isfinite(report.direction_hit_rate)
        assert math.isfinite(report.mean_confidence)
        assert math.isfinite(report.brier_score)


# ---------------------------------------------------------------------------
# TestRenderTunedWeights
# ---------------------------------------------------------------------------


class TestRenderTunedWeights:
    """Tests for render_tuned_weights function."""

    def test_renders_all_agents(self) -> None:
        """All 6 desk weights rendered in sorted order."""
        text = render_tuned_weights(AGENT_VOTE_WEIGHTS)
        assert "trend" in text
        assert "volatility" in text
        assert "flow" in text
        assert "fundamental" in text
        assert "contrarian" in text
        assert "risk" in text

    def test_format(self) -> None:
        """Each line has 'agent: weight' format with 2 decimal places."""
        weights = {"flow": 0.20, "trend": 0.25}
        text = render_tuned_weights(weights)
        lines = text.split("\n")
        # First line is header
        assert "auto-tuned" in lines[0].lower()
        # Remaining lines are agent entries (sorted: flow, trend)
        assert "  flow: 0.20" in lines[1]
        assert "  trend: 0.25" in lines[2]

    def test_sorted_output(self) -> None:
        """Agents are sorted alphabetically."""
        weights = {"volatility": 0.20, "contrarian": 0.05, "flow": 0.20}
        text = render_tuned_weights(weights)
        lines = text.split("\n")
        agent_lines = lines[1:]  # skip header
        agents = [line.strip().split(":")[0] for line in agent_lines if line.strip()]
        assert agents == sorted(agents)

    def test_empty_weights(self) -> None:
        """Empty weights returns empty string."""
        assert render_tuned_weights({}) == ""

    def test_header_present(self) -> None:
        """Header line describes the weights."""
        text = render_tuned_weights({"trend": 0.25})
        first_line = text.split("\n")[0]
        assert "desk vote weights" in first_line.lower()


# ---------------------------------------------------------------------------
# TestAutoTuneWithPredictions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAutoTuneWithPredictions:
    """Tests for prediction-first / legacy-fallback in auto_tune_weights."""

    async def test_uses_predictions_when_available(self) -> None:
        """Predictions with sufficient samples are used as data source."""
        desk_preds = [
            _pred(PredictionSource.DESK_TREND, accuracy=0.75, total=50),
            _pred(PredictionSource.DESK_VOLATILITY, accuracy=0.70, total=40),
            _pred(PredictionSource.DESK_FLOW, accuracy=0.65, total=35),
            _pred(PredictionSource.DESK_FUNDAMENTAL, accuracy=0.60, total=30),
            _pred(PredictionSource.DESK_CONTRARIAN, accuracy=0.55, total=25),
            _pred(PredictionSource.DESK_RISK, accuracy=0.50, total=20),
        ]

        repo = AsyncMock()
        repo.get_prediction_accuracy = AsyncMock(return_value=desk_preds)
        repo.get_agent_accuracy = AsyncMock(return_value=[])
        repo.save_auto_tune_weights = AsyncMock()

        result = await auto_tune_weights(repo, window_days=90)

        assert len(result) > 0
        assert all(isinstance(r, AgentWeightsComparison) for r in result)
        # Should NOT have called legacy accuracy
        repo.get_agent_accuracy.assert_not_awaited()
        repo.save_auto_tune_weights.assert_awaited_once()

    async def test_falls_back_to_legacy(self) -> None:
        """No predictions causes fallback to legacy agent_predictions."""
        repo = AsyncMock()
        repo.get_prediction_accuracy = AsyncMock(return_value=[])
        repo.get_agent_accuracy = AsyncMock(
            return_value=[
                _legacy_report("trend", brier=0.15),
                _legacy_report("volatility", brier=0.20),
            ]
        )
        repo.save_auto_tune_weights = AsyncMock()

        result = await auto_tune_weights(repo, window_days=90)

        assert len(result) > 0
        repo.get_agent_accuracy.assert_awaited_once()

    async def test_insufficient_samples_falls_back(self) -> None:
        """Predictions with sample_sufficient=False fall back to legacy."""
        desk_preds = [
            _pred(
                PredictionSource.DESK_TREND,
                accuracy=0.75,
                total=5,
                correct=3,
                sample_sufficient=False,
            ),
            _pred(
                PredictionSource.DESK_VOLATILITY,
                accuracy=0.70,
                total=50,
                sample_sufficient=True,
            ),
        ]

        repo = AsyncMock()
        repo.get_prediction_accuracy = AsyncMock(return_value=desk_preds)
        repo.get_agent_accuracy = AsyncMock(return_value=[_legacy_report("trend", brier=0.15)])
        repo.save_auto_tune_weights = AsyncMock()

        await auto_tune_weights(repo, window_days=90)

        # Should have fallen back to legacy because not all desk sources are sufficient
        repo.get_agent_accuracy.assert_awaited_once()

    async def test_only_non_desk_predictions_falls_back(self) -> None:
        """Non-desk predictions (SCAN_DIRECTION, SYNTHESIS) do not satisfy desk requirement."""
        preds = [
            _pred(PredictionSource.SCAN_DIRECTION, accuracy=0.80, total=100),
            _pred(PredictionSource.SYNTHESIS, accuracy=0.70, total=80),
        ]

        repo = AsyncMock()
        repo.get_prediction_accuracy = AsyncMock(return_value=preds)
        repo.get_agent_accuracy = AsyncMock(return_value=[_legacy_report("trend", brier=0.15)])
        repo.save_auto_tune_weights = AsyncMock()

        await auto_tune_weights(repo, window_days=90)

        # No desk predictions, so should fall back to legacy
        repo.get_agent_accuracy.assert_awaited_once()

    async def test_prediction_error_falls_back(self) -> None:
        """Exception from get_prediction_accuracy falls back to legacy gracefully."""
        repo = AsyncMock()
        repo.get_prediction_accuracy = AsyncMock(side_effect=RuntimeError("DB error"))
        repo.get_agent_accuracy = AsyncMock(return_value=[_legacy_report("trend", brier=0.15)])
        repo.save_auto_tune_weights = AsyncMock()

        result = await auto_tune_weights(repo, window_days=90)

        assert len(result) > 0
        repo.get_agent_accuracy.assert_awaited_once()

    async def test_empty_predictions_and_empty_legacy(self) -> None:
        """Both sources empty returns empty list without crashing."""
        repo = AsyncMock()
        repo.get_prediction_accuracy = AsyncMock(return_value=[])
        repo.get_agent_accuracy = AsyncMock(return_value=[])

        result = await auto_tune_weights(repo, window_days=90)

        assert result == []

    async def test_dry_run_skips_persist_with_predictions(self) -> None:
        """dry_run=True with prediction data skips persistence."""
        desk_preds = [
            _pred(PredictionSource.DESK_TREND, accuracy=0.75, total=50),
            _pred(PredictionSource.DESK_VOLATILITY, accuracy=0.70, total=40),
            _pred(PredictionSource.DESK_FLOW, accuracy=0.65, total=35),
            _pred(PredictionSource.DESK_FUNDAMENTAL, accuracy=0.60, total=30),
            _pred(PredictionSource.DESK_CONTRARIAN, accuracy=0.55, total=25),
            _pred(PredictionSource.DESK_RISK, accuracy=0.50, total=20),
        ]

        repo = AsyncMock()
        repo.get_prediction_accuracy = AsyncMock(return_value=desk_preds)
        repo.get_agent_accuracy = AsyncMock(return_value=[])
        repo.save_auto_tune_weights = AsyncMock()

        result = await auto_tune_weights(repo, window_days=90, dry_run=True)

        assert len(result) > 0
        repo.save_auto_tune_weights.assert_not_awaited()
