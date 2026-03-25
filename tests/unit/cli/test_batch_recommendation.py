"""Tests for batch recommendation CLI feature.

Tests cover batch iteration with run_recommendation, per-ticker error isolation,
provider flag forwarding, and batch summary rendering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.usage import RunUsage
from rich.table import Table
from typer.testing import CliRunner

from options_arena.cli.app import app
from options_arena.cli.rendering import render_recommendation_batch_summary
from options_arena.models.enums import (
    DeskType,
    ExerciseStyle,
    MacdSignal,
    ScanPreset,
    SignalDirection,
)
from options_arena.models.recommendation import (
    PositionRecommendation,
    RecommendationResult,
    TrendAssessment,
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
        started_at=datetime(2026, 3, 22, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 22, 10, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        tickers_scanned=500,
        tickers_scored=50,
        recommendations=5,
    )


def _make_market_context(ticker: str = "AAPL") -> object:
    """Create a minimal MarketContext for RecommendationResult."""
    from options_arena.models.analysis import MarketContext

    return MarketContext(
        ticker=ticker,
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("200.00"),
        price_52w_low=Decimal("140.00"),
        iv_rank=45.0,
        iv_percentile=50.0,
        atm_iv_30d=0.28,
        rsi_14=55.0,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 3, 22, 14, 30, 0, tzinfo=UTC),
    )


def _make_recommendation_result(
    ticker: str = "AAPL",
    *,
    is_fallback: bool = False,
) -> RecommendationResult:
    """Create a minimal RecommendationResult for testing."""
    trend = TrendAssessment(
        desk=DeskType.TREND,
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        summary="Strong uptrend.",
        key_factors=["RSI trending up"],
        risks=["Earnings next week"],
        contracts_referenced=[f"{ticker} 190C 2026-04-18"],
        tools_used=["fetch_quote"],
        model_used="test",
    )
    rec = PositionRecommendation(
        ticker=ticker,
        direction=SignalDirection.BULLISH,
        confidence=0.70,
        recommended_contract=f"{ticker} 190C 2026-04-18",
        entry_price=Decimal("5.25"),
        entry_criteria="Enter on pullback.",
        exit_criteria="Exit at 50% profit.",
        stop_loss=Decimal("3.50"),
        take_profit=Decimal("7.80"),
        position_size_pct=0.05,
        position_rationale="Conservative.",
        risk_reward_ratio=2.3,
        max_loss_estimate="$175 per contract",
        strategy_rationale="Directional call.",
        summary="Bullish momentum.",
        key_factors=["RSI at 65"],
        risk_assessment="Moderate risk.",
        model_used="test",
    )
    return RecommendationResult(
        context=_make_market_context(ticker),
        assessments=[trend],
        recommendation=rec,
        total_usage=RunUsage(),
        duration_ms=2500,
        is_fallback=is_fallback,
    )


# ---------------------------------------------------------------------------
# CLI Routing Tests
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands._validate_provider_config")
@patch("options_arena.cli.commands._batch_async", new_callable=AsyncMock)
def test_batch_flag_invokes_batch_async(mock_batch: AsyncMock, _mock_validate: MagicMock) -> None:
    """--batch without ticker invokes _batch_async."""
    mock_batch.return_value = None
    result = runner.invoke(app, ["debate", "--batch"])
    assert result.exit_code == 0
    mock_batch.assert_awaited_once()


@patch("options_arena.cli.commands._validate_provider_config")
@patch("options_arena.cli.commands._batch_async", new_callable=AsyncMock)
def test_batch_provider_flag_forwarded(mock_batch: AsyncMock, _mock_validate: MagicMock) -> None:
    """--provider anthropic is forwarded to _batch_async."""
    mock_batch.return_value = None
    result = runner.invoke(app, ["debate", "--batch", "--provider", "anthropic"])
    assert result.exit_code == 0
    mock_batch.assert_awaited_once()
    kwargs = mock_batch.call_args[1]
    assert kwargs.get("provider").value == "anthropic"


@patch("options_arena.cli.commands._validate_provider_config")
@patch("options_arena.cli.commands._batch_async", new_callable=AsyncMock)
def test_batch_limit_forwarded(mock_batch: AsyncMock, _mock_validate: MagicMock) -> None:
    """--batch-limit 3 is forwarded to _batch_async."""
    mock_batch.return_value = None
    result = runner.invoke(app, ["debate", "--batch", "--batch-limit", "3"])
    assert result.exit_code == 0
    mock_batch.assert_awaited_once()
    assert mock_batch.call_args[0][0] == 3


# ---------------------------------------------------------------------------
# Batch Orchestration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_iterates_tickers_with_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify batch iterates tickers calling _recommendation_single."""
    import options_arena.cli.commands as cmd_mod

    monkeypatch.setenv("ARENA_DEBATE__BATCH_TICKER_DELAY", "0")

    mock_rec_single = AsyncMock()
    result_aapl = _make_recommendation_result("AAPL")
    result_msft = _make_recommendation_result("MSFT")
    mock_rec_single.side_effect = [result_aapl, result_msft]
    monkeypatch.setattr(cmd_mod, "_recommendation_single", mock_rec_single)

    mock_db = AsyncMock()
    monkeypatch.setattr(cmd_mod, "Database", MagicMock(return_value=mock_db))

    mock_repo = MagicMock()
    mock_repo.get_latest_scan = AsyncMock(return_value=_make_scan_run())
    mock_repo.get_scores_for_scan = AsyncMock(
        return_value=[
            _make_ticker_score("AAPL", 80.0),
            _make_ticker_score("MSFT", 75.0),
        ]
    )
    mock_repo.get_spread_for_ticker = AsyncMock(return_value=None)
    monkeypatch.setattr(cmd_mod, "Repository", MagicMock(return_value=mock_repo))

    # Service mocks must return AsyncMock instances so .close() can be awaited
    mock_cache = MagicMock()
    mock_cache.close = AsyncMock()
    monkeypatch.setattr(cmd_mod, "ServiceCache", MagicMock(return_value=mock_cache))
    monkeypatch.setattr(cmd_mod, "RateLimiter", MagicMock())
    monkeypatch.setattr(cmd_mod, "MarketDataService", MagicMock(return_value=AsyncMock()))
    monkeypatch.setattr(cmd_mod, "OptionsDataService", MagicMock(return_value=AsyncMock()))
    monkeypatch.setattr(cmd_mod, "FredService", MagicMock(return_value=AsyncMock()))

    await cmd_mod._batch_async(2, False)

    assert mock_rec_single.call_count == 2
    tickers_called = [call.args[0].ticker for call in mock_rec_single.call_args_list]
    assert "AAPL" in tickers_called
    assert "MSFT" in tickers_called


@pytest.mark.asyncio
async def test_batch_error_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify one ticker failure does not crash the batch."""
    import options_arena.cli.commands as cmd_mod

    monkeypatch.setenv("ARENA_DEBATE__BATCH_TICKER_DELAY", "0")

    mock_rec_single = AsyncMock()
    result_msft = _make_recommendation_result("MSFT")
    mock_rec_single.side_effect = [
        RuntimeError("AAPL data fetch failed"),
        result_msft,
    ]
    monkeypatch.setattr(cmd_mod, "_recommendation_single", mock_rec_single)

    mock_db = AsyncMock()
    monkeypatch.setattr(cmd_mod, "Database", MagicMock(return_value=mock_db))

    mock_repo = MagicMock()
    mock_repo.get_latest_scan = AsyncMock(return_value=_make_scan_run())
    mock_repo.get_scores_for_scan = AsyncMock(
        return_value=[
            _make_ticker_score("AAPL", 80.0),
            _make_ticker_score("MSFT", 75.0),
        ]
    )
    mock_repo.get_spread_for_ticker = AsyncMock(return_value=None)
    monkeypatch.setattr(cmd_mod, "Repository", MagicMock(return_value=mock_repo))

    mock_cache = MagicMock()
    mock_cache.close = AsyncMock()
    monkeypatch.setattr(cmd_mod, "ServiceCache", MagicMock(return_value=mock_cache))
    monkeypatch.setattr(cmd_mod, "RateLimiter", MagicMock())
    monkeypatch.setattr(cmd_mod, "MarketDataService", MagicMock(return_value=AsyncMock()))
    monkeypatch.setattr(cmd_mod, "OptionsDataService", MagicMock(return_value=AsyncMock()))
    monkeypatch.setattr(cmd_mod, "FredService", MagicMock(return_value=AsyncMock()))

    # Should not raise despite first ticker failure
    await cmd_mod._batch_async(2, False)
    assert mock_rec_single.call_count == 2


# ---------------------------------------------------------------------------
# Batch Summary Rendering Tests
# ---------------------------------------------------------------------------


def test_render_recommendation_batch_summary_success() -> None:
    """Verify batch summary table renders recommendation details."""
    results: list[tuple[str, RecommendationResult | None, str | None]] = [
        ("AAPL", _make_recommendation_result("AAPL"), None),
        ("MSFT", _make_recommendation_result("MSFT"), None),
    ]
    table = render_recommendation_batch_summary(results)
    assert isinstance(table, Table)
    assert table.row_count == 2


def test_render_recommendation_batch_summary_with_failure() -> None:
    """Verify batch summary table handles failures gracefully."""
    results: list[tuple[str, RecommendationResult | None, str | None]] = [
        ("AAPL", _make_recommendation_result("AAPL"), None),
        ("MSFT", None, "Connection timeout"),
    ]
    table = render_recommendation_batch_summary(results)
    assert isinstance(table, Table)
    assert table.row_count == 2


def test_render_recommendation_batch_summary_all_failures() -> None:
    """Verify batch summary table handles all-failure case."""
    results: list[tuple[str, RecommendationResult | None, str | None]] = [
        ("AAPL", None, "Error 1"),
        ("MSFT", None, "Error 2"),
    ]
    table = render_recommendation_batch_summary(results)
    assert isinstance(table, Table)
    assert table.row_count == 2
