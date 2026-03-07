"""Tests for OpenBB wiring in CLI debate commands."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from pydantic_ai.usage import RunUsage
from typer.testing import CliRunner

from options_arena.agents._parsing import DebateResult
from options_arena.cli.app import app
from options_arena.models import (
    AgentResponse,
    IndicatorSignals,
    MarketContext,
    SignalDirection,
    TickerScore,
    TradeThesis,
)
from options_arena.models.enums import ExerciseStyle, MacdSignal, ScanPreset, SentimentLabel
from options_arena.models.openbb import (
    FundamentalSnapshot,
    NewsHeadline,
    NewsSentimentSnapshot,
    UnusualFlowSnapshot,
)
from options_arena.models.scan import ScanRun

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(ticker: str = "AAPL", score: float = 75.0) -> TickerScore:
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
        started_at=datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 1, 10, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        tickers_scanned=500,
        tickers_scored=50,
        recommendations=5,
    )


def _make_debate_result(ticker: str = "AAPL") -> DebateResult:
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
        data_timestamp=datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC),
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


def _make_fundamental() -> FundamentalSnapshot:
    """Create a realistic FundamentalSnapshot fixture."""
    return FundamentalSnapshot(
        ticker="AAPL",
        pe_ratio=25.3,
        forward_pe=22.1,
        peg_ratio=1.8,
        price_to_book=5.2,
        debt_to_equity=0.45,
        revenue_growth=0.12,
        profit_margin=0.25,
        fetched_at=datetime(2026, 3, 2, 14, 0, 0, tzinfo=UTC),
    )


def _make_flow() -> UnusualFlowSnapshot:
    """Create a realistic UnusualFlowSnapshot fixture."""
    return UnusualFlowSnapshot(
        ticker="AAPL",
        net_call_premium=5_000_000.0,
        net_put_premium=2_000_000.0,
        call_volume=150_000,
        put_volume=80_000,
        put_call_ratio=0.53,
        fetched_at=datetime(2026, 3, 2, 14, 0, 0, tzinfo=UTC),
    )


def _make_sentiment() -> NewsSentimentSnapshot:
    """Create a realistic NewsSentimentSnapshot fixture."""
    return NewsSentimentSnapshot(
        ticker="AAPL",
        headlines=[
            NewsHeadline(
                title="Apple beats earnings expectations",
                sentiment_score=0.65,
            ),
        ],
        aggregate_sentiment=0.65,
        sentiment_label=SentimentLabel.BULLISH,
        article_count=1,
        fetched_at=datetime(2026, 3, 2, 14, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# CLI routing tests for --no-openbb
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
def test_debate_skips_openbb_when_no_openbb_flag(mock_debate_async: AsyncMock) -> None:
    """Verify --no-openbb flag passes no_openbb=True to _debate_async."""
    mock_debate_async.return_value = None
    result = runner.invoke(app, ["debate", "AAPL", "--no-openbb"])
    assert result.exit_code == 0
    mock_debate_async.assert_awaited_once()
    # Check the no_openbb keyword argument
    call_kwargs = mock_debate_async.call_args.kwargs
    assert call_kwargs["no_openbb"] is True


# ---------------------------------------------------------------------------
# _debate_async — OpenBB service creation and lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
@patch("options_arena.cli.commands.FredService")
@patch("options_arena.cli.commands.OptionsDataService")
@patch("options_arena.cli.commands.MarketDataService")
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
@patch("options_arena.cli.commands.OpenBBService")
async def test_debate_creates_openbb_service(
    mock_openbb_cls: MagicMock,
    mock_limiter_cls: MagicMock,
    mock_cache_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_options_cls: MagicMock,
    mock_fred_cls: MagicMock,
    mock_debate_single: AsyncMock,
) -> None:
    """Verify _debate_async creates OpenBBService when enabled."""
    from options_arena.cli.commands import _debate_async  # noqa: PLC0415

    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo.get_latest_scan.return_value = _make_scan_run()
    mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
    mock_repo_cls.return_value = mock_repo

    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache
    mock_market_cls.return_value = AsyncMock()
    mock_options_cls.return_value = AsyncMock()
    mock_fred_cls.return_value = AsyncMock()

    mock_openbb_svc = AsyncMock()
    mock_openbb_cls.return_value = mock_openbb_svc

    mock_debate_single.return_value = _make_debate_result()

    # no_openbb=False + config has enabled=True (default)
    await _debate_async("AAPL", history=False, fallback_only=False, no_openbb=False)

    # OpenBBService constructor should have been called
    mock_openbb_cls.assert_called_once()


@pytest.mark.asyncio
@patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
@patch("options_arena.cli.commands.FredService")
@patch("options_arena.cli.commands.OptionsDataService")
@patch("options_arena.cli.commands.MarketDataService")
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
@patch("options_arena.cli.commands.OpenBBService")
async def test_debate_skips_openbb_when_config_disabled(
    mock_openbb_cls: MagicMock,
    mock_limiter_cls: MagicMock,
    mock_cache_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_options_cls: MagicMock,
    mock_fred_cls: MagicMock,
    mock_debate_single: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify OpenBBConfig.enabled=False prevents service creation."""
    from options_arena.cli.commands import _debate_async  # noqa: PLC0415

    # Disable OpenBB via environment variable
    monkeypatch.setenv("ARENA_OPENBB__ENABLED", "false")

    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo.get_latest_scan.return_value = _make_scan_run()
    mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
    mock_repo_cls.return_value = mock_repo

    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache
    mock_market_cls.return_value = AsyncMock()
    mock_options_cls.return_value = AsyncMock()
    mock_fred_cls.return_value = AsyncMock()

    mock_debate_single.return_value = _make_debate_result()

    await _debate_async("AAPL", history=False, fallback_only=False, no_openbb=False)

    # OpenBBService should NOT be constructed since config is disabled
    mock_openbb_cls.assert_not_called()


@pytest.mark.asyncio
@patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
@patch("options_arena.cli.commands.FredService")
@patch("options_arena.cli.commands.OptionsDataService")
@patch("options_arena.cli.commands.MarketDataService")
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
@patch("options_arena.cli.commands.OpenBBService")
async def test_debate_closes_openbb_in_finally(
    mock_openbb_cls: MagicMock,
    mock_limiter_cls: MagicMock,
    mock_cache_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_options_cls: MagicMock,
    mock_fred_cls: MagicMock,
    mock_debate_single: AsyncMock,
) -> None:
    """Verify close() called even on exception."""
    from options_arena.cli.commands import _debate_async  # noqa: PLC0415

    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo.get_latest_scan.return_value = _make_scan_run()
    mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
    mock_repo_cls.return_value = mock_repo

    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache
    mock_market_cls.return_value = AsyncMock()
    mock_options_cls.return_value = AsyncMock()
    mock_fred_cls.return_value = AsyncMock()

    mock_openbb_svc = AsyncMock()
    mock_openbb_cls.return_value = mock_openbb_svc

    # Simulate _debate_single raising an exception
    mock_debate_single.side_effect = RuntimeError("LLM connection refused")

    with pytest.raises(typer.Exit):
        await _debate_async("AAPL", history=False, fallback_only=False, no_openbb=False)

    # close() should still have been called despite the exception
    mock_openbb_svc.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# _debate_single — OpenBB enrichment fetch and passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("options_arena.agents.run_debate", new_callable=AsyncMock)
@patch("options_arena.scoring.compute_dimensional_scores")
@patch("options_arena.cli.commands.recommend_contracts")
@patch("options_arena.cli.commands.compute_indicators")
@patch("options_arena.cli.commands.ohlcv_to_dataframe")
async def test_debate_single_fetches_enrichment(
    mock_ohlcv_to_df: MagicMock,
    mock_compute_ind: MagicMock,
    mock_recommend: MagicMock,
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """Verify _debate_single fetches OpenBB data via asyncio.gather."""
    from options_arena.cli.commands import _debate_single  # noqa: PLC0415
    from options_arena.models.config import AppSettings  # noqa: PLC0415

    mock_ohlcv_to_df.return_value = MagicMock()
    mock_compute_ind.return_value = IndicatorSignals(rsi=65.0)
    mock_recommend.return_value = []
    mock_dim_scores.return_value = None
    mock_run_debate.return_value = _make_debate_result()

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=MagicMock())
    mock_market_data.fetch_ticker_info = AsyncMock(
        return_value=MagicMock(current_price=Decimal("185.00"), dividend_yield=0.005)
    )
    mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    mock_fred = AsyncMock()
    mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

    mock_repo = AsyncMock()

    # Create mock OpenBB service with enrichment data
    mock_openbb = AsyncMock()
    fundamental = _make_fundamental()
    flow = _make_flow()
    sentiment = _make_sentiment()
    mock_openbb.fetch_fundamentals = AsyncMock(return_value=fundamental)
    mock_openbb.fetch_unusual_flow = AsyncMock(return_value=flow)
    mock_openbb.fetch_news_sentiment = AsyncMock(return_value=sentiment)

    await _debate_single(
        ticker_score=_make_ticker_score(),
        settings=AppSettings(),
        market_data=mock_market_data,
        options_data=mock_options_data,
        fred=mock_fred,
        repo=mock_repo,
        openbb_svc=mock_openbb,
    )

    # Verify all three fetch methods were called
    mock_openbb.fetch_fundamentals.assert_awaited_once_with("AAPL")
    mock_openbb.fetch_unusual_flow.assert_awaited_once_with("AAPL")
    mock_openbb.fetch_news_sentiment.assert_awaited_once_with("AAPL")


@pytest.mark.asyncio
@patch("options_arena.agents.run_debate", new_callable=AsyncMock)
@patch("options_arena.scoring.compute_dimensional_scores")
@patch("options_arena.cli.commands.recommend_contracts")
@patch("options_arena.cli.commands.compute_indicators")
@patch("options_arena.cli.commands.ohlcv_to_dataframe")
async def test_debate_single_passes_enrichment_to_run_debate(
    mock_ohlcv_to_df: MagicMock,
    mock_compute_ind: MagicMock,
    mock_recommend: MagicMock,
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """Verify enrichment kwargs passed to run_debate."""
    from options_arena.cli.commands import _debate_single  # noqa: PLC0415
    from options_arena.models.config import AppSettings  # noqa: PLC0415

    mock_ohlcv_to_df.return_value = MagicMock()
    mock_compute_ind.return_value = IndicatorSignals(rsi=65.0)
    mock_recommend.return_value = []
    mock_dim_scores.return_value = None
    mock_run_debate.return_value = _make_debate_result()

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=MagicMock())
    mock_market_data.fetch_ticker_info = AsyncMock(
        return_value=MagicMock(current_price=Decimal("185.00"), dividend_yield=0.005)
    )
    mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    mock_fred = AsyncMock()
    mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

    mock_repo = AsyncMock()

    fundamental = _make_fundamental()
    flow = _make_flow()
    sentiment = _make_sentiment()

    mock_openbb = AsyncMock()
    mock_openbb.fetch_fundamentals = AsyncMock(return_value=fundamental)
    mock_openbb.fetch_unusual_flow = AsyncMock(return_value=flow)
    mock_openbb.fetch_news_sentiment = AsyncMock(return_value=sentiment)

    await _debate_single(
        ticker_score=_make_ticker_score(),
        settings=AppSettings(),
        market_data=mock_market_data,
        options_data=mock_options_data,
        fred=mock_fred,
        repo=mock_repo,
        openbb_svc=mock_openbb,
    )

    # Verify run_debate received the enrichment data
    call_kwargs = mock_run_debate.call_args.kwargs
    assert call_kwargs["fundamentals"] is fundamental
    assert call_kwargs["flow"] is flow
    assert call_kwargs["sentiment"] is sentiment


@pytest.mark.asyncio
@patch("options_arena.agents.run_debate", new_callable=AsyncMock)
@patch("options_arena.scoring.compute_dimensional_scores")
@patch("options_arena.cli.commands.recommend_contracts")
@patch("options_arena.cli.commands.compute_indicators")
@patch("options_arena.cli.commands.ohlcv_to_dataframe")
async def test_debate_single_no_enrichment_when_service_none(
    mock_ohlcv_to_df: MagicMock,
    mock_compute_ind: MagicMock,
    mock_recommend: MagicMock,
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """Verify all enrichment is None when openbb_svc is None."""
    from options_arena.cli.commands import _debate_single  # noqa: PLC0415
    from options_arena.models.config import AppSettings  # noqa: PLC0415

    mock_ohlcv_to_df.return_value = MagicMock()
    mock_compute_ind.return_value = IndicatorSignals(rsi=65.0)
    mock_recommend.return_value = []
    mock_dim_scores.return_value = None
    mock_run_debate.return_value = _make_debate_result()

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=MagicMock())
    mock_market_data.fetch_ticker_info = AsyncMock(
        return_value=MagicMock(current_price=Decimal("185.00"), dividend_yield=0.005)
    )
    mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    mock_fred = AsyncMock()
    mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

    mock_repo = AsyncMock()

    # No OpenBB service — all enrichment should be None
    await _debate_single(
        ticker_score=_make_ticker_score(),
        settings=AppSettings(),
        market_data=mock_market_data,
        options_data=mock_options_data,
        fred=mock_fred,
        repo=mock_repo,
        openbb_svc=None,
    )

    call_kwargs = mock_run_debate.call_args.kwargs
    assert call_kwargs["fundamentals"] is None
    assert call_kwargs["flow"] is None
    assert call_kwargs["sentiment"] is None


# ---------------------------------------------------------------------------
# _batch_async — OpenBB service creation for batch mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("options_arena.cli.commands._debate_single", new_callable=AsyncMock)
@patch("options_arena.cli.commands.FredService")
@patch("options_arena.cli.commands.OptionsDataService")
@patch("options_arena.cli.commands.MarketDataService")
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
@patch("options_arena.cli.commands.ServiceCache")
@patch("options_arena.cli.commands.RateLimiter")
@patch("options_arena.cli.commands.OpenBBService")
async def test_batch_creates_openbb_service(
    mock_openbb_cls: MagicMock,
    mock_limiter_cls: MagicMock,
    mock_cache_cls: MagicMock,
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_options_cls: MagicMock,
    mock_fred_cls: MagicMock,
    mock_debate_single: AsyncMock,
) -> None:
    """Verify _batch_async creates OpenBBService when enabled."""
    from options_arena.cli.commands import _batch_async  # noqa: PLC0415

    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo.get_latest_scan.return_value = _make_scan_run()
    mock_repo.get_scores_for_scan.return_value = [_make_ticker_score()]
    mock_repo_cls.return_value = mock_repo

    mock_cache = AsyncMock()
    mock_cache_cls.return_value = mock_cache
    mock_market_cls.return_value = AsyncMock()
    mock_options_cls.return_value = AsyncMock()
    mock_fred_cls.return_value = AsyncMock()

    mock_openbb_svc = AsyncMock()
    mock_openbb_cls.return_value = mock_openbb_svc

    mock_debate_single.return_value = _make_debate_result()

    # no_openbb=False + config.openbb.enabled=True (default)
    await _batch_async(batch_limit=1, fallback_only=False, no_openbb=False)

    # OpenBBService should have been constructed
    mock_openbb_cls.assert_called_once()
    # And closed in finally block
    mock_openbb_svc.close.assert_awaited_once()
