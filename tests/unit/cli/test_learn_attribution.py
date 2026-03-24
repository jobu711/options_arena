"""Tests for ``learn attribution`` CLI command.

Covers: command registration, Rich table output with source accuracy rows,
empty data message, and --source filter forwarding.

Uses ``typer.testing.CliRunner`` with mocked repository/database -- no real
DB or LLM calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from options_arena.cli import app
from options_arena.models.attribution import (
    Prediction,
    PredictionSource,
)
from options_arena.models.enums import SignalDirection

runner = CliRunner()


def _mock_db() -> AsyncMock:
    """Create a mock Database that does nothing on connect/close."""
    db = AsyncMock()
    db.connect = AsyncMock()
    db.close = AsyncMock()
    return db


def _sample_predictions(
    *,
    sources: list[PredictionSource] | None = None,
) -> list[Prediction]:
    """Build sample scored predictions for tests."""
    if sources is None:
        sources = [PredictionSource.DESK_TREND, PredictionSource.SYNTHESIS]

    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)
    result: list[Prediction] = []
    for idx, src in enumerate(sources):
        result.append(
            Prediction(
                id=idx + 1,
                recommendation_id=1,
                ticker="AAPL",
                source=src,
                predicted_direction=SignalDirection.BULLISH,
                confidence=0.8,
                adx=25.0,
                iv_rank=45.0,
                atr_pct=2.0,
                rsi=55.0,
                was_correct=idx % 2 == 0,
                created_at=now,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLearnAttribution:
    """Tests for the ``learn attribution`` CLI command."""

    def test_command_exists(self) -> None:
        """Verify 'learn attribution' command is registered."""
        result = runner.invoke(app, ["agency", "learn", "attribution", "--help"])
        assert result.exit_code == 0
        assert "attribution" in result.output.lower()

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_displays_source_accuracy(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """Rich table shows per-source accuracy rows."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_predictions = AsyncMock(return_value=_sample_predictions())
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "attribution"])
        assert result.exit_code == 0
        # Table title
        assert "Attribution" in result.output
        # Source names should appear
        assert "desk_trend" in result.output
        assert "synthesis" in result.output

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_empty_data_message(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """No predictions produces 'No scored predictions' message."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_predictions = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "attribution"])
        assert result.exit_code == 0
        assert "No scored predictions" in result.output

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_source_filter(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """--source desk_trend filters to single source."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        filtered = _sample_predictions(sources=[PredictionSource.DESK_TREND])
        mock_repo.get_predictions = AsyncMock(return_value=filtered)
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "attribution", "--source", "desk_trend"])
        assert result.exit_code == 0
        assert "desk_trend" in result.output
        # Verify get_predictions was called with the source filter
        mock_repo.get_predictions.assert_awaited_once_with(90, PredictionSource.DESK_TREND)

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_invalid_source_exits_with_error(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """Invalid --source value exits with code 1."""
        result = runner.invoke(app, ["agency", "learn", "attribution", "--source", "nonexistent"])
        assert result.exit_code == 1

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_custom_window_days(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """--window-days is forwarded to get_predictions."""
        mock_db_cls.return_value = _mock_db()
        mock_repo = AsyncMock()
        mock_repo.get_predictions = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        result = runner.invoke(app, ["agency", "learn", "attribution", "--window-days", "30"])
        assert result.exit_code == 0
        mock_repo.get_predictions.assert_awaited_once_with(30, None)

    @patch("options_arena.data.Repository")
    @patch("options_arena.data.Database")
    def test_db_closed_on_success(
        self,
        mock_db_cls: AsyncMock,
        mock_repo_cls: AsyncMock,
    ) -> None:
        """Database is closed even on success path."""
        mock_db = _mock_db()
        mock_db_cls.return_value = mock_db
        mock_repo = AsyncMock()
        mock_repo.get_predictions = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        runner.invoke(app, ["agency", "learn", "attribution"])
        mock_db.close.assert_called_once()
