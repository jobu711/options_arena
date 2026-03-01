"""Tests for CLI logging configuration (configure_logging).

Validates dual-handler setup: RichHandler for console + QueueHandler for
file rotation on a background thread via QueueListener.
"""

import logging
import sys
from logging.handlers import QueueHandler
from pathlib import Path
from unittest.mock import patch

from rich.logging import RichHandler

from options_arena.cli.app import configure_logging


def _get_app_module() -> object:
    """Get the cli.app module (not the Typer app object) from sys.modules."""
    return sys.modules["options_arena.cli.app"]


def _cleanup() -> None:
    """Remove all handlers from root logger and stop queue listener."""
    mod = _get_app_module()
    listener = getattr(mod, "_queue_listener", None)
    if listener is not None:
        listener.stop()
        mod._queue_listener = None
    root = logging.getLogger()
    for h in root.handlers[:]:
        h.close()
    root.handlers.clear()


def test_configure_logging_creates_two_handlers(tmp_path: Path) -> None:
    """Verify dual-handler setup: RichHandler + QueueHandler on root."""
    with (
        patch("options_arena.cli.app.LOG_DIR", tmp_path),
        patch("options_arena.cli.app.LOG_FILE", tmp_path / "options_arena.log"),
    ):
        try:
            configure_logging(verbose=False)
            root = logging.getLogger()
            assert len(root.handlers) == 2
            handler_types = {type(h).__name__ for h in root.handlers}
            assert "RichHandler" in handler_types
            assert "QueueHandler" in handler_types
        finally:
            _cleanup()


def test_noisy_loggers_suppressed(tmp_path: Path) -> None:
    """All 4 noisy loggers set to WARNING or above."""
    with (
        patch("options_arena.cli.app.LOG_DIR", tmp_path),
        patch("options_arena.cli.app.LOG_FILE", tmp_path / "options_arena.log"),
    ):
        try:
            configure_logging()
            for name in ("aiosqlite", "httpx", "httpcore", "yfinance"):
                assert logging.getLogger(name).level >= logging.WARNING
        finally:
            _cleanup()


def test_verbose_lowers_console_handler(tmp_path: Path) -> None:
    """When verbose=True the console (Rich) handler level is DEBUG."""
    with (
        patch("options_arena.cli.app.LOG_DIR", tmp_path),
        patch("options_arena.cli.app.LOG_FILE", tmp_path / "options_arena.log"),
    ):
        try:
            configure_logging(verbose=True)
            root = logging.getLogger()
            rich_handlers = [h for h in root.handlers if isinstance(h, RichHandler)]
            assert len(rich_handlers) == 1
            assert rich_handlers[0].level == logging.DEBUG
        finally:
            _cleanup()


def test_log_directory_created(tmp_path: Path) -> None:
    """Verify the log directory is created if it does not exist."""
    log_dir = tmp_path / "custom_logs"
    with (
        patch("options_arena.cli.app.LOG_DIR", log_dir),
        patch("options_arena.cli.app.LOG_FILE", log_dir / "options_arena.log"),
    ):
        try:
            assert not log_dir.exists()
            configure_logging(verbose=False)
            assert log_dir.exists()
        finally:
            _cleanup()


def test_handlers_cleared_on_reentry(tmp_path: Path) -> None:
    """Calling configure_logging twice does not duplicate handlers."""
    with (
        patch("options_arena.cli.app.LOG_DIR", tmp_path),
        patch("options_arena.cli.app.LOG_FILE", tmp_path / "options_arena.log"),
    ):
        try:
            configure_logging(verbose=False)
            configure_logging(verbose=True)
            root = logging.getLogger()
            assert len(root.handlers) == 2
            # Second call should have set Rich handler to DEBUG
            rich_handlers = [h for h in root.handlers if isinstance(h, RichHandler)]
            assert rich_handlers[0].level == logging.DEBUG
        finally:
            _cleanup()


def test_queue_handler_level_is_debug(tmp_path: Path) -> None:
    """QueueHandler level is DEBUG so all records reach the file via QueueListener."""
    with (
        patch("options_arena.cli.app.LOG_DIR", tmp_path),
        patch("options_arena.cli.app.LOG_FILE", tmp_path / "options_arena.log"),
    ):
        try:
            configure_logging(verbose=False)
            root = logging.getLogger()
            queue_handlers = [h for h in root.handlers if isinstance(h, QueueHandler)]
            assert len(queue_handlers) == 1
            assert queue_handlers[0].level == logging.DEBUG
        finally:
            _cleanup()


def test_queue_listener_started(tmp_path: Path) -> None:
    """QueueListener is started after configure_logging and can be stopped."""
    with (
        patch("options_arena.cli.app.LOG_DIR", tmp_path),
        patch("options_arena.cli.app.LOG_FILE", tmp_path / "options_arena.log"),
    ):
        try:
            configure_logging(verbose=False)
            mod = _get_app_module()
            assert getattr(mod, "_queue_listener", None) is not None
        finally:
            _cleanup()


def test_root_logger_level_is_debug(tmp_path: Path) -> None:
    """Root logger is set to DEBUG so both handlers can filter independently."""
    with (
        patch("options_arena.cli.app.LOG_DIR", tmp_path),
        patch("options_arena.cli.app.LOG_FILE", tmp_path / "options_arena.log"),
    ):
        try:
            configure_logging(verbose=False)
            root = logging.getLogger()
            assert root.level == logging.DEBUG
        finally:
            _cleanup()
