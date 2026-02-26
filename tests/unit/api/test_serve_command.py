"""Tests for the serve CLI command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from options_arena.cli import app

runner = CliRunner()


def test_serve_command_exists() -> None:
    """The serve command is accessible via the Typer app."""
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "Start the FastAPI web server" in result.output


def test_serve_help_shows_options() -> None:
    """serve --help lists all options."""
    result = runner.invoke(app, ["serve", "--help"])
    assert "--host" in result.output
    assert "--port" in result.output
    assert "--no-open" in result.output
    assert "--reload" in result.output


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
    result = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--port", "3000", "--no-open"])
    assert result.exit_code == 0
    mock_run.assert_called_once_with(
        "options_arena.api.app:create_app",
        host="0.0.0.0",
        port=3000,
        reload=False,
        factory=True,
    )


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
@patch("webbrowser.open")
def test_serve_opens_browser_by_default(mock_browser: MagicMock, mock_run: MagicMock) -> None:
    """serve opens browser unless --no-open is set."""
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 0
    mock_browser.assert_called_once_with("http://127.0.0.1:8000")
    mock_run.assert_called_once()


@patch("uvicorn.run")
@patch("webbrowser.open")
def test_serve_no_open_skips_browser(mock_browser: MagicMock, mock_run: MagicMock) -> None:
    """serve --no-open does not open browser."""
    result = runner.invoke(app, ["serve", "--no-open"])
    assert result.exit_code == 0
    mock_browser.assert_not_called()
    mock_run.assert_called_once()
