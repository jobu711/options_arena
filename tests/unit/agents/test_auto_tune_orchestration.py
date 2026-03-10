"""Tests for auto_tune_weights() orchestration function.

Covers: full flow with mocked repo, dry_run skips persist, comparison list
shape, manual weight sourcing, Brier score matching, empty accuracy,
window_days forwarding to both accuracy and save.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from options_arena.agents.orchestrator import (
    AGENT_VOTE_WEIGHTS,
    auto_tune_weights,
)
from options_arena.models import AgentAccuracyReport, AgentWeightsComparison


def _report(
    name: str,
    brier: float = 0.20,
    sample_size: int = 50,
) -> AgentAccuracyReport:
    """Shorthand for creating an AgentAccuracyReport."""
    return AgentAccuracyReport(
        agent_name=name,
        direction_hit_rate=0.7,
        mean_confidence=0.65,
        brier_score=brier,
        sample_size=sample_size,
    )


def _mock_repo(
    accuracy: list[AgentAccuracyReport] | None = None,
) -> AsyncMock:
    """Build a mock Repository with get_agent_accuracy and save_auto_tune_weights."""
    repo = AsyncMock()
    repo.get_agent_accuracy = AsyncMock(return_value=accuracy if accuracy is not None else [])
    repo.save_auto_tune_weights = AsyncMock(return_value=None)
    return repo


class TestAutoTuneWeights:
    """Tests for auto_tune_weights() orchestration."""

    @pytest.mark.asyncio
    async def test_computes_and_persists(self) -> None:
        """Full flow: accuracy -> weights -> comparisons -> save called."""
        reports = [
            _report("trend", brier=0.15),
            _report("volatility", brier=0.20),
            _report("flow", brier=0.25),
            _report("fundamental", brier=0.30),
            _report("contrarian", brier=0.40),
        ]
        repo = _mock_repo(reports)

        result = await auto_tune_weights(repo, window_days=90, dry_run=False)

        assert len(result) > 0
        repo.get_agent_accuracy.assert_awaited_once_with(window_days=90)
        repo.save_auto_tune_weights.assert_awaited_once()
        # Verify the save call received the comparisons and window_days
        save_args = repo.save_auto_tune_weights.call_args
        assert save_args[1]["window_days"] == 90
        assert save_args[0][0] == result

    @pytest.mark.asyncio
    async def test_dry_run_skips_persist(self) -> None:
        """Verify save is NOT called when dry_run=True."""
        reports = [
            _report("trend", brier=0.15),
            _report("volatility", brier=0.20),
        ]
        repo = _mock_repo(reports)

        result = await auto_tune_weights(repo, window_days=60, dry_run=True)

        assert len(result) > 0
        repo.get_agent_accuracy.assert_awaited_once()
        repo.save_auto_tune_weights.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_comparison_list(self) -> None:
        """Verify return type is list[AgentWeightsComparison]."""
        reports = [
            _report("trend", brier=0.15),
            _report("volatility", brier=0.20),
            _report("flow", brier=0.25),
            _report("fundamental", brier=0.30),
            _report("contrarian", brier=0.40),
        ]
        repo = _mock_repo(reports)

        result = await auto_tune_weights(repo, window_days=90, dry_run=True)

        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, AgentWeightsComparison)

    @pytest.mark.asyncio
    async def test_manual_weights_from_constants(self) -> None:
        """Verify manual_weight comes from AGENT_VOTE_WEIGHTS for each agent."""
        reports = [
            _report("trend", brier=0.15),
            _report("volatility", brier=0.20),
            _report("flow", brier=0.25),
            _report("fundamental", brier=0.30),
            _report("contrarian", brier=0.40),
        ]
        repo = _mock_repo(reports)

        result = await auto_tune_weights(repo, window_days=90, dry_run=True)

        for comp in result:
            expected_manual = AGENT_VOTE_WEIGHTS.get(comp.agent_name, 0.0)
            assert comp.manual_weight == pytest.approx(expected_manual)

    @pytest.mark.asyncio
    async def test_brier_score_matched_by_agent_name(self) -> None:
        """Verify each comparison has the correct Brier score from accuracy."""
        reports = [
            _report("trend", brier=0.15),
            _report("volatility", brier=0.20),
            _report("flow", brier=0.25),
            _report("fundamental", brier=0.30),
            _report("contrarian", brier=0.40),
        ]
        repo = _mock_repo(reports)

        result = await auto_tune_weights(repo, window_days=90, dry_run=True)

        accuracy_map = {r.agent_name: r.brier_score for r in reports}
        for comp in result:
            if comp.agent_name in accuracy_map:
                assert comp.brier_score == pytest.approx(accuracy_map[comp.agent_name])
            else:
                # Agents not in accuracy (e.g., risk) should have None brier
                assert comp.brier_score is None

    @pytest.mark.asyncio
    async def test_empty_accuracy_returns_empty(self) -> None:
        """Empty accuracy data returns empty list — no snapshot persisted."""
        repo = _mock_repo([])

        result = await auto_tune_weights(repo, window_days=90, dry_run=True)

        assert result == []

    @pytest.mark.asyncio
    async def test_window_days_passed_to_accuracy(self) -> None:
        """Verify window_days is forwarded to get_agent_accuracy."""
        repo = _mock_repo([])

        await auto_tune_weights(repo, window_days=180, dry_run=True)

        repo.get_agent_accuracy.assert_awaited_once_with(window_days=180)

    @pytest.mark.asyncio
    async def test_window_days_passed_to_save(self) -> None:
        """Verify window_days is forwarded to save_auto_tune_weights."""
        reports = [_report("trend", brier=0.15)]
        repo = _mock_repo(reports)

        await auto_tune_weights(repo, window_days=120, dry_run=False)

        save_args = repo.save_auto_tune_weights.call_args
        assert save_args[1]["window_days"] == 120
