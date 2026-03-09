"""Tests for agent calibration CLI commands.

Covers: agent-accuracy, calibration, agent-weights subcommands.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from options_arena.cli import app
from options_arena.models import (
    AgentAccuracyReport,
    AgentCalibrationData,
    AgentWeightsComparison,
    CalibrationBucket,
)

runner = CliRunner()


def _mock_db() -> AsyncMock:
    """Create a mock Database that does nothing on connect/close."""
    db = AsyncMock()
    db.connect = AsyncMock()
    db.close = AsyncMock()
    return db


class TestAgentAccuracyCLI:
    """Tests for outcomes agent-accuracy command."""

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_basic_output(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify Rich table renders with mock data."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_agent_accuracy = AsyncMock(
            return_value=[
                AgentAccuracyReport(
                    agent_name="trend",
                    direction_hit_rate=0.75,
                    mean_confidence=0.70,
                    brier_score=0.18,
                    sample_size=50,
                ),
            ]
        )
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "agent-accuracy"])
        assert result.exit_code == 0
        assert "trend" in result.output
        assert "75.0%" in result.output

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_window_flag(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify --window passes to repository."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_agent_accuracy = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "agent-accuracy", "--window", "30"])
        assert result.exit_code == 0
        mock_repo.get_agent_accuracy.assert_called_once_with(30)

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_no_data_message(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify informative message when no accuracy data."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_agent_accuracy = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "agent-accuracy"])
        assert result.exit_code == 0
        assert "No agent accuracy data" in result.output


class TestCalibrationCLI:
    """Tests for outcomes calibration command."""

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_aggregate_view(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify calibration table with all agents."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_agent_calibration = AsyncMock(
            return_value=AgentCalibrationData(
                agent_name=None,
                buckets=[
                    CalibrationBucket(
                        bucket_label="0.6-0.8",
                        bucket_low=0.6,
                        bucket_high=0.8,
                        mean_confidence=0.7,
                        actual_hit_rate=0.65,
                        count=20,
                    ),
                ],
                sample_size=20,
            )
        )
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "calibration"])
        assert result.exit_code == 0
        assert "All Agents" in result.output

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_agent_filter(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify --agent filters to single agent."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_agent_calibration = AsyncMock(
            return_value=AgentCalibrationData(
                agent_name="trend",
                buckets=[],
                sample_size=0,
            )
        )
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "calibration", "--agent", "trend"])
        assert result.exit_code == 0
        mock_repo.get_agent_calibration.assert_called_once_with("trend")

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_no_data_message(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify informative message when no calibration data."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_agent_calibration = AsyncMock(
            return_value=AgentCalibrationData(
                agent_name=None,
                buckets=[],
                sample_size=0,
            )
        )
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "calibration"])
        assert result.exit_code == 0
        assert "No calibration data" in result.output


class TestAgentWeightsCLI:
    """Tests for outcomes agent-weights command."""

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_basic_output(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify weights comparison table renders."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_latest_auto_tune_weights = AsyncMock(
            return_value=[
                AgentWeightsComparison(
                    agent_name="trend",
                    manual_weight=0.25,
                    auto_weight=0.22,
                    brier_score=0.18,
                    sample_size=50,
                ),
            ]
        )
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "agent-weights"])
        assert result.exit_code == 0
        assert "trend" in result.output

    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_no_auto_weights(self, mock_db_cls: AsyncMock, mock_repo_cls: AsyncMock) -> None:
        """Verify message when auto-tune not run yet."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_latest_auto_tune_weights = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["outcomes", "agent-weights"])
        assert result.exit_code == 0
        assert "No auto-tune weights" in result.output
