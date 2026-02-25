"""Tests for batch debate CLI feature.

Tests cover CLI routing (CliRunner + mocks), batch orchestration logic
(pytest-asyncio + mocked services), and the batch summary rendering function.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from pydantic_ai.usage import RunUsage
from rich.table import Table
from typer.testing import CliRunner

from options_arena.agents._parsing import DebateResult
from options_arena.cli.app import app
from options_arena.cli.rendering import render_batch_summary_table
from options_arena.models import (
    AgentResponse,
    MarketContext,
    TradeThesis,
)
from options_arena.models.enums import (
    ExerciseStyle,
    MacdSignal,
    ScanPreset,
    SignalDirection,
)
from options_arena.models.scan import IndicatorSignals, ScanRun, TickerScore

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(ticker: str, score: float = 75.0) -> TickerScore:
    """Create a TickerScore for testing."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.0),
        scan_run_id=1,
    )


def _make_scan_run() -> ScanRun:
    """Create a ScanRun for testing."""
    return ScanRun(
        id=1,
        started_at=datetime(2026, 2, 25, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 2, 25, 10, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        tickers_scanned=500,
        tickers_scored=50,
        recommendations=5,
    )


def _make_debate_result(ticker: str) -> DebateResult:
    """Create a minimal DebateResult for testing."""
    bull = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI at 65 indicates bullish momentum.",
        key_points=["RSI trending up"],
        risks_cited=["Earnings next week"],
        contracts_referenced=[f"{ticker} $190 CALL"],
        model_used="test",
    )
    bear = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="IV is elevated, limiting upside.",
        key_points=["IV elevated"],
        risks_cited=["Potential reversal"],
        contracts_referenced=[f"{ticker} $190 CALL"],
        model_used="test",
    )
    thesis = TradeThesis(
        ticker=ticker,
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["Momentum"],
        risk_assessment="Moderate risk.",
        recommended_strategy=None,
    )
    ctx = MarketContext(
        ticker=ticker,
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.2,
        iv_percentile=52.1,
        atm_iv_30d=28.5,
        rsi_14=62.3,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 2, 25, 14, 30, 0, tzinfo=UTC),
    )
    return DebateResult(
        context=ctx,
        bull_response=bull,
        bear_response=bear,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=1500,
        is_fallback=False,
    )


# ---------------------------------------------------------------------------
# CLI Routing Tests
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands._batch_async", new_callable=AsyncMock)
def test_batch_flag_without_ticker(mock_batch: AsyncMock) -> None:
    """--batch without ticker invokes _batch_async."""
    mock_batch.return_value = None
    result = runner.invoke(app, ["debate", "--batch"])
    assert result.exit_code == 0
    mock_batch.assert_awaited_once()


@patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
def test_single_ticker_without_batch(mock_debate: AsyncMock) -> None:
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
@patch("options_arena.cli.commands.FredService")
@patch("options_arena.cli.commands.OptionsDataService")
@patch("options_arena.cli.commands.MarketDataService")
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
@patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
async def test_batch_all_succeed(
    mock_debate_single: AsyncMock,
    mock_limiter_cls: MagicMock,
    mock_cache_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_options_cls: MagicMock,
    mock_fred_cls: MagicMock,
) -> None:
    """All tickers in batch succeed -- results list has all entries."""
    from options_arena.cli.commands import _batch_async

    # Mock DB + repo
    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo.get_latest_scan.return_value = _make_scan_run()
    mock_repo.get_scores_for_scan.return_value = [
        _make_ticker_score("AAPL", 90.0),
        _make_ticker_score("MSFT", 80.0),
        _make_ticker_score("GOOG", 70.0),
    ]
    mock_repo_cls.return_value = mock_repo

    # Mock services (return AsyncMock so .close() is awaitable)
    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache
    mock_market_cls.return_value = AsyncMock()
    mock_options_cls.return_value = AsyncMock()
    mock_fred_cls.return_value = AsyncMock()

    # _debate_single returns a DebateResult for each call
    mock_debate_single.side_effect = [
        _make_debate_result("AAPL"),
        _make_debate_result("MSFT"),
        _make_debate_result("GOOG"),
    ]

    await _batch_async(batch_limit=3, fallback_only=False)

    assert mock_debate_single.await_count == 3


@pytest.mark.asyncio
@patch("options_arena.cli.commands.FredService")
@patch("options_arena.cli.commands.OptionsDataService")
@patch("options_arena.cli.commands.MarketDataService")
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
@patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
async def test_batch_one_failure(
    mock_debate_single: AsyncMock,
    mock_limiter_cls: MagicMock,
    mock_cache_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_options_cls: MagicMock,
    mock_fred_cls: MagicMock,
) -> None:
    """One ticker fails, other two succeed -- error isolation works."""
    from options_arena.cli.commands import _batch_async

    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo.get_latest_scan.return_value = _make_scan_run()
    mock_repo.get_scores_for_scan.return_value = [
        _make_ticker_score("AAPL", 90.0),
        _make_ticker_score("MSFT", 80.0),
        _make_ticker_score("GOOG", 70.0),
    ]
    mock_repo_cls.return_value = mock_repo

    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache
    mock_market_cls.return_value = AsyncMock()
    mock_options_cls.return_value = AsyncMock()
    mock_fred_cls.return_value = AsyncMock()

    # Second ticker fails, others succeed
    mock_debate_single.side_effect = [
        _make_debate_result("AAPL"),
        RuntimeError("LLM provider connection refused"),
        _make_debate_result("GOOG"),
    ]

    await _batch_async(batch_limit=3, fallback_only=False)

    # All three were attempted despite the middle failure
    assert mock_debate_single.await_count == 3


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


@pytest.mark.asyncio
@patch("options_arena.cli.commands.FredService")
@patch("options_arena.cli.commands.OptionsDataService")
@patch("options_arena.cli.commands.MarketDataService")
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
@patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
async def test_batch_limit_caps_tickers(
    mock_debate_single: AsyncMock,
    mock_limiter_cls: MagicMock,
    mock_cache_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_options_cls: MagicMock,
    mock_fred_cls: MagicMock,
) -> None:
    """--batch-limit 2 limits to 2 tickers even when more are scored."""
    from options_arena.cli.commands import _batch_async

    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo.get_latest_scan.return_value = _make_scan_run()
    mock_repo.get_scores_for_scan.return_value = [
        _make_ticker_score("AAPL", 95.0),
        _make_ticker_score("MSFT", 85.0),
        _make_ticker_score("GOOG", 75.0),
        _make_ticker_score("AMZN", 65.0),
        _make_ticker_score("META", 55.0),
    ]
    mock_repo_cls.return_value = mock_repo

    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache
    mock_market_cls.return_value = AsyncMock()
    mock_options_cls.return_value = AsyncMock()
    mock_fred_cls.return_value = AsyncMock()

    mock_debate_single.side_effect = [
        _make_debate_result("AAPL"),
        _make_debate_result("MSFT"),
    ]

    await _batch_async(batch_limit=2, fallback_only=False)

    # Only 2 debates run despite 5 scored tickers
    assert mock_debate_single.await_count == 2


@pytest.mark.asyncio
@patch("options_arena.cli.commands.FredService")
@patch("options_arena.cli.commands.OptionsDataService")
@patch("options_arena.cli.commands.MarketDataService")
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
@patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
async def test_batch_service_lifecycle(
    mock_debate_single: AsyncMock,
    mock_limiter_cls: MagicMock,
    mock_cache_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_options_cls: MagicMock,
    mock_fred_cls: MagicMock,
) -> None:
    """Services created once and closed once, not per-ticker."""
    from options_arena.cli.commands import _batch_async

    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo.get_latest_scan.return_value = _make_scan_run()
    mock_repo.get_scores_for_scan.return_value = [
        _make_ticker_score("AAPL", 90.0),
        _make_ticker_score("MSFT", 80.0),
    ]
    mock_repo_cls.return_value = mock_repo

    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache

    mock_market = AsyncMock()
    mock_market_cls.return_value = mock_market
    mock_options = AsyncMock()
    mock_options_cls.return_value = mock_options
    mock_fred = AsyncMock()
    mock_fred_cls.return_value = mock_fred

    mock_debate_single.side_effect = [
        _make_debate_result("AAPL"),
        _make_debate_result("MSFT"),
    ]

    await _batch_async(batch_limit=2, fallback_only=False)

    # Each service created exactly once (constructor called once)
    mock_market_cls.assert_called_once()
    mock_options_cls.assert_called_once()
    mock_fred_cls.assert_called_once()

    # Each service closed exactly once (not per-ticker)
    mock_market.close.assert_awaited_once()
    mock_options.close.assert_awaited_once()
    mock_fred.close.assert_awaited_once()
    mock_cache.close.assert_awaited_once()
    mock_db.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Rendering Test
# ---------------------------------------------------------------------------


def test_render_batch_summary_table_success_and_failure() -> None:
    """Table renders both successful and failed debates with correct structure."""
    results: list[tuple[str, DebateResult | None, str | None]] = [
        ("AAPL", _make_debate_result("AAPL"), None),
        ("MSFT", None, "Connection refused"),
        ("GOOG", _make_debate_result("GOOG"), None),
    ]

    table = render_batch_summary_table(results)

    assert isinstance(table, Table)
    assert table.row_count == 3
    assert table.title == "Batch Debate Summary"

    # Verify column count (7 columns)
    assert len(table.columns) == 7
    column_names = [col.header for col in table.columns]
    assert column_names == [
        "Ticker",
        "Direction",
        "Confidence",
        "Strategy",
        "Fallback",
        "Duration",
        "Status",
    ]
