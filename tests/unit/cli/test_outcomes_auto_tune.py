"""Tests for outcomes auto-tune CLI subcommand.

Covers: default invocation, --dry-run, --window, empty results, exit codes,
and error handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from options_arena.cli import app
from options_arena.models import AgentWeightsComparison

runner = CliRunner()


def _mock_db() -> AsyncMock:
    """Create a mock Database that does nothing on connect/close."""
    db = AsyncMock()
    db.connect = AsyncMock()
    db.close = AsyncMock()
    return db


def _sample_results() -> list[AgentWeightsComparison]:
    """Build sample auto-tune results for tests."""
    return [
        AgentWeightsComparison(
            agent_name="trend",
            manual_weight=0.250,
            auto_weight=0.284,
            brier_score=0.180,
            sample_size=50,
        ),
        AgentWeightsComparison(
            agent_name="volatility",
            manual_weight=0.200,
            auto_weight=0.172,
            brier_score=0.220,
            sample_size=45,
        ),
        AgentWeightsComparison(
            agent_name="flow",
            manual_weight=0.150,
            auto_weight=0.150,
            brier_score=None,
            sample_size=8,
        ),
    ]


class TestAutoTuneCLI:
    """Tests for outcomes auto-tune command."""

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_default(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """Command runs with defaults, renders table with agent data."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.return_value = _sample_results()

        result = runner.invoke(app, ["outcomes", "auto-tune"])
        assert result.exit_code == 0
        assert "trend" in result.output
        assert "volatility" in result.output
        assert "0.284" in result.output
        assert "0.180" in result.output
        assert "Weights saved" in result.output
        # Verify called with defaults
        mock_auto_tune.assert_called_once_with(mock_repo, window_days=90, dry_run=False)

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_dry_run(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """--dry-run shows table without persisting."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.return_value = _sample_results()

        result = runner.invoke(app, ["outcomes", "auto-tune", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Weights not saved" in result.output
        assert "Weights saved. Next debate" not in result.output
        mock_auto_tune.assert_called_once_with(mock_repo, window_days=90, dry_run=True)

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_custom_window(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """--window parameter forwarded to auto_tune_weights."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.return_value = _sample_results()

        result = runner.invoke(app, ["outcomes", "auto-tune", "--window", "30"])
        assert result.exit_code == 0
        mock_auto_tune.assert_called_once_with(mock_repo, window_days=30, dry_run=False)

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_no_data(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """Graceful handling when no outcome data available."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.return_value = []

        result = runner.invoke(app, ["outcomes", "auto-tune"])
        assert result.exit_code == 0
        assert "No outcome data available for auto-tuning" in result.output

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_exit_code_zero(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """Success exit code on normal operation."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.return_value = _sample_results()

        result = runner.invoke(app, ["outcomes", "auto-tune"])
        assert result.exit_code == 0

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_error_handling(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """Exit code 1 on exception."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.side_effect = RuntimeError("DB connection lost")

        result = runner.invoke(app, ["outcomes", "auto-tune"])
        assert result.exit_code == 1

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_delta_formatting(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """Verify delta column shows positive, negative, and zero values."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.return_value = _sample_results()

        result = runner.invoke(app, ["outcomes", "auto-tune"])
        assert result.exit_code == 0
        # trend: 0.284 - 0.250 = +0.034
        assert "+0.034" in result.output
        # volatility: 0.172 - 0.200 = -0.028
        assert "-0.028" in result.output
        # flow: 0.150 - 0.150 = +0.000
        assert "+0.000" in result.output

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_brier_none_shows_dash(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """Brier column shows '--' when value is None."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.return_value = [
            AgentWeightsComparison(
                agent_name="flow",
                manual_weight=0.150,
                auto_weight=0.150,
                brier_score=None,
                sample_size=5,
            ),
        ]

        result = runner.invoke(app, ["outcomes", "auto-tune"])
        assert result.exit_code == 0
        assert "--" in result.output

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_db_closed_on_success(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """Database is closed even on success path."""
        mock_db = _mock_db()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.return_value = _sample_results()

        runner.invoke(app, ["outcomes", "auto-tune"])
        mock_db.close.assert_called_once()

    @patch("options_arena.cli.outcomes.auto_tune_weights", new_callable=AsyncMock)
    @patch("options_arena.cli.outcomes.Repository")
    @patch("options_arena.cli.outcomes.Database")
    def test_auto_tune_db_closed_on_error(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_auto_tune: AsyncMock,
    ) -> None:
        """Database is closed even on error path."""
        mock_db = _mock_db()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_auto_tune.side_effect = RuntimeError("fail")

        runner.invoke(app, ["outcomes", "auto-tune"])
        mock_db.close.assert_called_once()
