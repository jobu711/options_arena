"""Tests for batch debate CLI feature.

Tests cover CLI routing (CliRunner + mocks) and batch orchestration logic
(pytest-asyncio + mocked services).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from options_arena.cli.app import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# CLI Routing Tests
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands._validate_provider_config")
@patch("options_arena.cli.commands._batch_async", new_callable=AsyncMock)
def test_batch_flag_without_ticker(mock_batch: AsyncMock, _mock_validate: MagicMock) -> None:
    """--batch without ticker invokes _batch_async."""
    mock_batch.return_value = None
    result = runner.invoke(app, ["debate", "--batch"])
    assert result.exit_code == 0
    mock_batch.assert_awaited_once()


@patch("options_arena.cli.commands._validate_provider_config")
@patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
def test_single_ticker_without_batch(mock_debate: AsyncMock, _mock_validate: MagicMock) -> None:
    """debate AAPL without --batch invokes _debate_async (existing behavior)."""
    mock_debate.return_value = None
    result = runner.invoke(app, ["debate", "AAPL"])
    assert result.exit_code == 0
    mock_debate.assert_awaited_once()
    # First positional arg is the ticker, uppercased
    assert mock_debate.call_args[0][0] == "AAPL"


def test_batch_with_ticker_is_error() -> None:
    """debate AAPL --batch is a validation error (exit code 1)."""
    result = runner.invoke(app, ["debate", "AAPL", "--batch"])
    assert result.exit_code == 1


def test_no_ticker_no_batch_is_error() -> None:
    """debate alone (no ticker, no --batch) is a validation error (exit code 1)."""
    result = runner.invoke(app, ["debate"])
    assert result.exit_code == 1


def test_batch_with_history_is_error() -> None:
    """debate --batch --history is a validation error (exit code 1)."""
    result = runner.invoke(app, ["debate", "--batch", "--history"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Batch Orchestration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
async def test_batch_no_scan_data(
    mock_limiter_cls: MagicMock,
    mock_cache_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
) -> None:
    """No scan data in DB produces an error (exit code 1 via typer.Exit)."""
    from options_arena.cli.commands import _batch_async

    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo.get_latest_scan.return_value = None
    mock_repo_cls.return_value = mock_repo

    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache

    with pytest.raises(typer.Exit) as exc_info:
        await _batch_async(batch_limit=5, fallback_only=False)
    assert exc_info.value.exit_code == 1
