"""Tests for the serve CLI command."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from options_arena.cli import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from Rich/Typer output."""
    return _ANSI_RE.sub("", text)


def test_serve_command_exists() -> None:
    """The serve command is accessible via the Typer app."""
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "Start the FastAPI web server" in output


def test_serve_help_shows_options() -> None:
    """serve --help lists all options."""
    result = runner.invoke(app, ["serve", "--help"])
    output = _strip_ansi(result.output)
    assert "--host" in output
    assert "--port" in output
    assert "--no-open" in output
    assert "--reload" in output


@patch("uvicorn.run")
def test_serve_calls_uvicorn_with_defaults(mock_run: MagicMock) -> None:
    """serve invokes uvicorn.run with factory pattern."""
    result = runner.invoke(app, ["serve", "--no-open"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        "options_arena.api.app:create_app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        factory=True,
    )


@patch("uvicorn.run")
def test_serve_custom_host_port(mock_run: MagicMock) -> None:
    """serve passes custom host and port to uvicorn."""
    result = runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "3000", "--no-open"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        "options_arena.api.app:create_app",
        host="127.0.0.1",
        port=3000,
        reload=False,
        factory=True,
    )


@patch("uvicorn.run")
def test_serve_rejects_non_loopback_host(mock_run: MagicMock) -> None:
    """serve rejects non-loopback hosts like 0.0.0.0."""
    result = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--no-open"])
    assert result.exit_code == 1
    mock_run.assert_not_called()


@patch("uvicorn.run")
def test_serve_reload_flag(mock_run: MagicMock) -> None:
    """serve --reload passes reload=True to uvicorn."""
    result = runner.invoke(app, ["serve", "--no-open", "--reload"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        "options_arena.api.app:create_app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        factory=True,
    )


@patch("uvicorn.run")
@patch("threading.Thread")
def test_serve_opens_browser_by_default(mock_thread: MagicMock, mock_run: MagicMock) -> None:
    """serve starts a background thread to open browser unless --no-open is set."""
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 0
    mock_thread.assert_called_once()
    mock_thread.return_value.start.assert_called_once()
    mock_run.assert_called_once()


@patch("uvicorn.run")
@patch("webbrowser.open")
def test_serve_no_open_skips_browser(mock_browser: MagicMock, mock_run: MagicMock) -> None:
    """serve --no-open does not open browser."""
    result = runner.invoke(app, ["serve", "--no-open"])
    assert result.exit_code == 0
    mock_browser.assert_not_called()
    mock_run.assert_called_once()
