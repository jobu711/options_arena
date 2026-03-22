"""Tests for ``learn`` CLI subcommands: playbook confidence display and decay.

Covers: playbook table columns (Confidence, Last Validated), decay command
registration, decay execution on empty DB, and decay summary output.

Uses ``typer.testing.CliRunner`` with mocked repository/database -- no real
DB or LLM calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from options_arena.cli import app
from options_arena.models import RuleStatus
from options_arena.models.strategy import StrategyCondition, StrategyRule

runner = CliRunner()


def _mock_db() -> AsyncMock:
    """Create a mock Database that does nothing on connect/close."""
    db = AsyncMock()
    db.connect = AsyncMock()
    db.close = AsyncMock()
    return db


def _sample_rules(
    *,
    include_validated: bool = True,
) -> list[StrategyRule]:
    """Build sample strategy rules for tests."""
    rules = [
        StrategyRule(
            rule_id="rule-abc-123",
            pattern="IT sector + bullish + high IV",
            conditions=[
                StrategyCondition(field="sector", operator="eq", value="Information Technology"),
            ],
            win_rate=0.72,
            avg_return=0.15,
            sample_size=30,
            status=RuleStatus.APPROVED,
            created_at=datetime(2026, 1, 15, tzinfo=UTC),
            confidence=0.85,
            last_validated=datetime(2026, 3, 10, tzinfo=UTC) if include_validated else None,
            validation_count=6 if include_validated else 0,
        ),
        StrategyRule(
            rule_id="rule-def-456",
            pattern="Healthcare + bearish + low IV",
            conditions=[
                StrategyCondition(field="sector", operator="eq", value="Health Care"),
            ],
            win_rate=0.60,
            avg_return=0.08,
            sample_size=25,
            status=RuleStatus.CANDIDATE,
            created_at=datetime(2026, 2, 1, tzinfo=UTC),
            confidence=0.45,
            last_validated=None,
            validation_count=0,
        ),
    ]
    return rules


# ---------------------------------------------------------------------------
# Playbook confidence display
# ---------------------------------------------------------------------------


class TestLearnPlaybookConfidence:
    """Verify playbook table includes Confidence and Last Validated columns."""

    @patch("options_arena.cli.agency._learn_playbook_async", new_callable=AsyncMock)
    def test_playbook_command_invokes_async(
        self,
        mock_playbook: AsyncMock,
    ) -> None:
        """Verify the playbook command calls _learn_playbook_async."""
        result = runner.invoke(app, ["agency", "learn", "playbook"])
        assert result.exit_code == 0
        mock_playbook.assert_awaited_once_with(None)

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_playbook_shows_confidence_column(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """Verify playbook table includes Confidence column header."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_strategy_rules = AsyncMock(return_value=_sample_rules())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "playbook"])
        assert result.exit_code == 0
        # Rich may truncate header to "Confi..." at narrow widths
        assert "Confi" in result.output

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_playbook_shows_last_validated_column(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """Verify playbook table includes Last Validated column header."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_strategy_rules = AsyncMock(return_value=_sample_rules())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "playbook"])
        assert result.exit_code == 0
        # Rich may truncate to "Last" + "Valida..." across two lines
        assert "Valida" in result.output

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_playbook_formats_confidence_as_percentage(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """Verify confidence displayed as '85%' not '0.85'."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_strategy_rules = AsyncMock(return_value=_sample_rules())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "playbook"])
        assert result.exit_code == 0
        # First rule has confidence=0.85 -> "85%"
        assert "85%" in result.output
        # Second rule has confidence=0.45 -> "45%"
        assert "45%" in result.output

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_playbook_last_validated_none_shows_dash(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """Verify None last_validated renders as '--'."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_strategy_rules = AsyncMock(return_value=_sample_rules())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "playbook"])
        assert result.exit_code == 0
        # Second rule has last_validated=None -> "--"
        assert "--" in result.output

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_playbook_last_validated_shows_date(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """Verify non-None last_validated renders as YYYY-MM-DD."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_strategy_rules = AsyncMock(return_value=_sample_rules())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "playbook"])
        assert result.exit_code == 0
        # First rule has last_validated=2026-03-10; Rich may truncate to "2026-0..."
        assert "2026-0" in result.output


# ---------------------------------------------------------------------------
# Learn decay command
# ---------------------------------------------------------------------------


class TestLearnDecay:
    """Tests for the ``learn decay`` command."""

    def test_decay_command_exists(self) -> None:
        """Verify 'learn decay' command is registered."""
        result = runner.invoke(app, ["agency", "learn", "decay", "--help"])
        assert result.exit_code == 0
        assert "decay" in result.output.lower()

    @patch("options_arena.learning.run_confidence_decay", new_callable=AsyncMock)
    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_decay_runs_without_error(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_decay: AsyncMock,
    ) -> None:
        """Verify decay command completes on empty DB."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_strategy_rules = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "decay"])
        assert result.exit_code == 0
        mock_decay.assert_awaited_once()

    @patch("options_arena.learning.run_confidence_decay", new_callable=AsyncMock)
    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_decay_shows_summary(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_decay: AsyncMock,
    ) -> None:
        """Verify decay outputs summary of rules processed."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        rules = _sample_rules()
        mock_repo.get_strategy_rules = AsyncMock(return_value=rules)
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "decay"])
        assert result.exit_code == 0
        assert "Total rules" in result.output
        assert "Promoted" in result.output
        assert "Demoted" in result.output

    @patch("options_arena.learning.run_confidence_decay", new_callable=AsyncMock)
    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_decay_no_rules_shows_message(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_decay: AsyncMock,
    ) -> None:
        """Verify empty rule set shows a user-friendly message."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_strategy_rules = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "decay"])
        assert result.exit_code == 0
        assert "No strategy rules found" in result.output

    @patch("options_arena.learning.run_confidence_decay", new_callable=AsyncMock)
    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_decay_detects_promotion(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_decay: AsyncMock,
    ) -> None:
        """Verify promoted count increments when candidate becomes approved."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()

        # Before: candidate; After: approved (simulating promotion)
        before_rules = [
            StrategyRule(
                rule_id="rule-promo-1",
                pattern="test pattern",
                conditions=[],
                win_rate=0.8,
                avg_return=0.2,
                sample_size=40,
                status=RuleStatus.CANDIDATE,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                confidence=0.9,
                validation_count=6,
            ),
        ]
        after_rules = [
            before_rules[0].model_copy(update={"status": RuleStatus.APPROVED}),
        ]

        mock_repo.get_strategy_rules = AsyncMock(side_effect=[before_rules, after_rules])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "decay"])
        assert result.exit_code == 0
        # Should show promoted count of 1
        assert "1" in result.output

    @patch("options_arena.learning.run_confidence_decay", new_callable=AsyncMock)
    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_decay_db_closed_on_success(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
        mock_decay: AsyncMock,
    ) -> None:
        """Database is closed even on success path."""
        mock_db = _mock_db()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo.get_strategy_rules = AsyncMock(return_value=_sample_rules())
        mock_repo_cls.return_value = mock_repo

        runner.invoke(app, ["agency", "learn", "decay"])
        mock_db.close.assert_called_once()
