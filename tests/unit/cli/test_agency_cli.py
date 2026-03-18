"""Tests for the ``agency`` CLI subcommand group.

Tests use ``typer.testing.CliRunner`` and mock async internals to verify
argument parsing and command registration. No actual LLM calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from pydantic_ai import models
from typer.testing import CliRunner

from options_arena.cli.app import app

# Prevent accidental real LLM API calls in tests
models.ALLOW_MODEL_REQUESTS = False

runner = CliRunner()


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


class TestAgencyCommandRegistration:
    """Verify the agency subcommand group is registered and accessible."""

    def test_agency_group_exists(self) -> None:
        """The 'agency' subcommand group is registered on the main app."""
        result = runner.invoke(app, ["agency", "--help"])
        assert result.exit_code == 0
        assert "ask" in result.output
        assert "history" in result.output

    def test_ask_command_help(self) -> None:
        """The 'agency ask' command shows expected options."""
        result = runner.invoke(app, ["agency", "ask", "--help"])
        assert result.exit_code == 0
        assert "--desk" in result.output
        assert "--ticker" in result.output

    def test_history_command_help(self) -> None:
        """The 'agency history' command shows expected options."""
        result = runner.invoke(app, ["agency", "history", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output


# ---------------------------------------------------------------------------
# agency ask
# ---------------------------------------------------------------------------


class TestAgencyAskCommand:
    """Tests for the ``agency ask`` command."""

    @patch("options_arena.cli.agency._ask_async", new_callable=AsyncMock)
    def test_ask_basic_query(self, mock_ask: AsyncMock) -> None:
        """agency ask 'question' invokes _ask_async."""
        result = runner.invoke(app, ["agency", "ask", "What is the IV for AAPL?"])
        assert result.exit_code == 0
        mock_ask.assert_awaited_once_with("What is the IV for AAPL?", None, None)

    @patch("options_arena.cli.agency._ask_async", new_callable=AsyncMock)
    def test_ask_with_desk_flag(self, mock_ask: AsyncMock) -> None:
        """agency ask --desk volatility 'question' passes desk arg."""
        result = runner.invoke(app, ["agency", "ask", "--desk", "volatility", "Check IV"])
        assert result.exit_code == 0
        mock_ask.assert_awaited_once_with("Check IV", "volatility", None)

    @patch("options_arena.cli.agency._ask_async", new_callable=AsyncMock)
    def test_ask_with_ticker_flag(self, mock_ask: AsyncMock) -> None:
        """agency ask --ticker AAPL 'question' passes ticker arg."""
        result = runner.invoke(app, ["agency", "ask", "--ticker", "AAPL", "Check IV"])
        assert result.exit_code == 0
        mock_ask.assert_awaited_once_with("Check IV", None, ["AAPL"])

    @patch("options_arena.cli.agency._ask_async", new_callable=AsyncMock)
    def test_ask_combined_flags(self, mock_ask: AsyncMock) -> None:
        """agency ask --desk risk --ticker TSLA 'question' passes both."""
        result = runner.invoke(
            app,
            ["agency", "ask", "--desk", "risk", "--ticker", "TSLA", "Check risk"],
        )
        assert result.exit_code == 0
        mock_ask.assert_awaited_once_with("Check risk", "risk", ["TSLA"])


# ---------------------------------------------------------------------------
# agency history
# ---------------------------------------------------------------------------


class TestAgencyHistoryCommand:
    """Tests for the ``agency history`` command."""

    @patch("options_arena.cli.agency._history_async", new_callable=AsyncMock)
    def test_history_default(self, mock_hist: AsyncMock) -> None:
        """agency history calls _history_async with default limit."""
        result = runner.invoke(app, ["agency", "history"])
        assert result.exit_code == 0
        mock_hist.assert_awaited_once_with(20)

    @patch("options_arena.cli.agency._history_async", new_callable=AsyncMock)
    def test_history_with_limit(self, mock_hist: AsyncMock) -> None:
        """agency history --limit 5 passes limit to _history_async."""
        result = runner.invoke(app, ["agency", "history", "--limit", "5"])
        assert result.exit_code == 0
        mock_hist.assert_awaited_once_with(5)
