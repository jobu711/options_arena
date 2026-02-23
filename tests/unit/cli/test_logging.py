"""Tests for CLI logging configuration (configure_logging)."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import patch

from rich.logging import RichHandler

from options_arena.cli.app import configure_logging


def _clear_root_handlers() -> None:
    """Remove all handlers from root logger to prevent test pollution."""
    root = logging.getLogger()
    root.handlers.clear()


def test_configure_logging_creates_two_handlers(tmp_path: Path) -> None:
    """Verify dual-handler setup: RichHandler + RotatingFileHandler on root."""
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
            assert "RotatingFileHandler" in handler_types
        finally:
            _clear_root_handlers()


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
            _clear_root_handlers()


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
            _clear_root_handlers()


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
            _clear_root_handlers()


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
            _clear_root_handlers()


def test_file_handler_always_debug(tmp_path: Path) -> None:
    """File handler level is DEBUG regardless of verbose flag."""
    with (
        patch("options_arena.cli.app.LOG_DIR", tmp_path),
        patch("options_arena.cli.app.LOG_FILE", tmp_path / "options_arena.log"),
    ):
        try:
            configure_logging(verbose=False)
            root = logging.getLogger()
            file_handlers = [h for h in root.handlers if isinstance(h, RotatingFileHandler)]
            assert len(file_handlers) == 1
            assert file_handlers[0].level == logging.DEBUG
        finally:
            _clear_root_handlers()


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
            _clear_root_handlers()
