"""Tests for CLI commands: scan, health, universe (refresh/list/stats).

All tests mock at the service level to avoid real API calls.
Typer CliRunner captures output and exit codes for assertion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from options_arena.cli.app import app
from options_arena.models.health import HealthStatus
from options_arena.services.universe import SP500Constituent

runner = CliRunner()


def _make_health_status(
    name: str,
    *,
    available: bool = True,
    latency_ms: float | None = 50.0,
    error: str | None = None,
) -> HealthStatus:
    """Create a HealthStatus for testing."""
    return HealthStatus(
        service_name=name,
        available=available,
        latency_ms=latency_ms,
        error=error,
        checked_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands._scan_async", new_callable=AsyncMock)
def test_scan_command_default_args(mock_scan_async: AsyncMock) -> None:
    """Scan command with defaults invokes _scan_async with SP500 preset."""
    mock_scan_async.return_value = None

    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 0
    mock_scan_async.assert_awaited_once()
    args = mock_scan_async.call_args
    # Default preset is SP500, top_n=50, min_score=0.0, sectors=None
    assert args[0][0].value == "sp500"
    assert args[0][1] == 50
    assert args[0][2] == 0.0
    assert args[0][3] is None


def test_scan_invalid_preset_rejected() -> None:
    """Scan rejects an invalid preset value."""
    result = runner.invoke(app, ["scan", "--preset", "invalid"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# health command
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands.HealthService")
def test_health_exit_code_all_up(mock_cls: AsyncMock) -> None:
    """Exit code 0 when all services are UP."""
    mock_svc = AsyncMock()
    mock_svc.check_all.return_value = [
        _make_health_status("yfinance"),
        _make_health_status("fred"),
        _make_health_status("groq"),
        _make_health_status("cboe"),
    ]
    mock_cls.return_value = mock_svc

    result = runner.invoke(app, ["health"])
    assert result.exit_code == 0
    mock_svc.close.assert_awaited_once()


@patch("options_arena.cli.commands.HealthService")
def test_health_exit_code_some_down(mock_cls: AsyncMock) -> None:
    """Exit code 1 when at least one service is DOWN."""
    mock_svc = AsyncMock()
    mock_svc.check_all.return_value = [
        _make_health_status("yfinance"),
        _make_health_status("fred", available=False, error="timeout"),
        _make_health_status("groq"),
        _make_health_status("cboe"),
    ]
    mock_cls.return_value = mock_svc

    result = runner.invoke(app, ["health"])
    assert result.exit_code == 1
    mock_svc.close.assert_awaited_once()


@patch("options_arena.cli.commands.HealthService")
def test_health_output_contains_service_names(mock_cls: AsyncMock) -> None:
    """Health output includes service names from the status list."""
    mock_svc = AsyncMock()
    mock_svc.check_all.return_value = [
        _make_health_status("yfinance"),
        _make_health_status("fred"),
    ]
    mock_cls.return_value = mock_svc

    result = runner.invoke(app, ["health"])
    assert "yfinance" in result.output
    assert "fred" in result.output


# ---------------------------------------------------------------------------
# universe stats command
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands.UniverseService")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
def test_universe_stats_produces_output(
    mock_limiter_cls: AsyncMock,
    mock_cache_cls: AsyncMock,
    mock_svc_cls: AsyncMock,
) -> None:
    """universe stats prints optionable count and S&P 500 count."""
    mock_svc = AsyncMock()
    mock_svc.fetch_optionable_tickers.return_value = ["AAPL", "MSFT", "GOOG"]
    mock_svc.fetch_sp500_constituents.return_value = [
        SP500Constituent(ticker="AAPL", sector="Information Technology"),
        SP500Constituent(ticker="MSFT", sector="Information Technology"),
        SP500Constituent(ticker="JNJ", sector="Health Care"),
    ]
    mock_svc_cls.return_value = mock_svc
    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache

    result = runner.invoke(app, ["universe", "stats"])
    assert result.exit_code == 0
    assert "3" in result.output  # 3 optionable tickers
    assert "S&P 500" in result.output or "S&P" in result.output
    mock_svc.close.assert_awaited_once()
    mock_cache.close.assert_awaited_once()
