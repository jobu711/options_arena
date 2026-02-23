"""Tests for RichProgressCallback — protocol compliance and Rich Progress delegation."""

from __future__ import annotations

from unittest.mock import MagicMock

from options_arena.cli.progress import RichProgressCallback
from options_arena.scan.progress import ProgressCallback, ScanPhase


def test_rich_progress_callback_protocol_compliance() -> None:
    """RichProgressCallback satisfies the runtime-checkable ProgressCallback protocol."""
    mock_progress = MagicMock()
    callback = RichProgressCallback(mock_progress)
    assert isinstance(callback, ProgressCallback)


def test_new_phase_creates_task() -> None:
    """Calling with a new phase calls progress.add_task() with the phase description."""
    mock_progress = MagicMock()
    mock_progress.add_task.return_value = 0
    callback = RichProgressCallback(mock_progress)

    callback(ScanPhase.UNIVERSE, current=0, total=100)

    mock_progress.add_task.assert_called_once()
    call_args = mock_progress.add_task.call_args
    assert "Fetching universe" in call_args[0][0]
    mock_progress.update.assert_called_once_with(0, completed=0, total=100)


def test_existing_phase_updates_task() -> None:
    """Calling the same phase twice does not create a second task — only updates."""
    mock_progress = MagicMock()
    mock_progress.add_task.return_value = 42
    callback = RichProgressCallback(mock_progress)

    callback(ScanPhase.SCORING, current=0, total=50)
    callback(ScanPhase.SCORING, current=25, total=50)

    # add_task called exactly once (first call only)
    assert mock_progress.add_task.call_count == 1
    # update called twice (once per __call__)
    assert mock_progress.update.call_count == 2
    mock_progress.update.assert_called_with(42, completed=25, total=50)
