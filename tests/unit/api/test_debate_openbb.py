"""Tests for OpenBB enrichment in API debate background tasks."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateResult
from options_arena.api.routes.debate import _run_batch_debate_background, _run_debate_background
from options_arena.api.ws import BatchProgressBridge, DebateProgressBridge
from options_arena.models import (
    AgentResponse,
    AppSettings,
    IndicatorSignals,
    MarketContext,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
    TradeThesis,
)
from options_arena.models.enums import (
    DividendSource,
    ExerciseStyle,
    MacdSignal,
)
from options_arena.models.openbb import (
    FundamentalSnapshot,
    NewsSentimentSnapshot,
    UnusualFlowSnapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quote() -> Quote:
    """Create a realistic Quote for test fixtures."""
    return Quote(
        ticker="AAPL",
        price=Decimal("185.05"),
        bid=Decimal("185.00"),
        ask=Decimal("185.10"),
        volume=42_000_000,
        timestamp=datetime(2026, 3, 2, 15, 0, 0, tzinfo=UTC),
    )


def _make_ticker_info() -> TickerInfo:
    """Create a realistic TickerInfo for test fixtures."""
    return TickerInfo(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Information Technology",
        market_cap=2_800_000_000_000,
        current_price=Decimal("185.05"),
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("164.08"),
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
    )


def _make_ticker_score(ticker: str = "AAPL") -> TickerScore:
    """Create a TickerScore for test fixtures."""
    return TickerScore(
        ticker=ticker,
        composite_score=75.0,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.0),
        scan_run_id=1,
    )


def _make_debate_result(ticker: str = "AAPL") -> DebateResult:
    """Create a minimal DebateResult for test fixtures."""
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
    from options_arena.models.enums import SentimentLabel  # noqa: PLC0415
    from options_arena.models.openbb import NewsHeadline  # noqa: PLC0415

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


def _make_mock_request(openbb_svc: AsyncMock | None = None) -> MagicMock:
    """Create a mock Request with app.state populated."""
    request = MagicMock()
    request.app.state.openbb = openbb_svc
    request.app.state.intelligence = None
    request.app.state.financial_datasets = None
    request.app.state.debate_queues = {}
    request.app.state.batch_queues = {}
    return request


def _make_mock_openbb_service(
    fundamentals: FundamentalSnapshot | None = None,
    flow: UnusualFlowSnapshot | None = None,
    sentiment: NewsSentimentSnapshot | None = None,
) -> AsyncMock:
    """Create a mock OpenBBService with configured return values."""
    svc = AsyncMock()
    svc.fetch_fundamentals = AsyncMock(return_value=fundamentals)
    svc.fetch_unusual_flow = AsyncMock(return_value=flow)
    svc.fetch_news_sentiment = AsyncMock(return_value=sentiment)
    return svc


# ---------------------------------------------------------------------------
# Single debate tests
# ---------------------------------------------------------------------------


@patch("options_arena.api.routes.debate.run_debate", new_callable=AsyncMock)
@patch("options_arena.api.routes.debate.compute_dimensional_scores")
async def test_single_debate_fetches_enrichment(
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """Verify _run_debate_background calls OpenBB fetch methods."""
    mock_dim_scores.return_value = None
    mock_run_debate.return_value = _make_debate_result()

    fundamental = _make_fundamental()
    flow = _make_flow()
    sentiment = _make_sentiment()
    openbb_svc = _make_mock_openbb_service(fundamental, flow, sentiment)
    request = _make_mock_request(openbb_svc)

    mock_repo = AsyncMock()
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    mock_repo.save_debate = AsyncMock(return_value=1)

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=_make_quote())
    mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info())
    mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    bridge = DebateProgressBridge()

    await _run_debate_background(
        request=request,
        debate_id=1,
        ticker="AAPL",
        scan_id=None,
        settings=AppSettings(),
        repo=mock_repo,
        market_data=mock_market_data,
        options_data=mock_options_data,
        bridge=bridge,
    )

    # Verify OHLCV backfill path was exercised (scan_id=None)
    mock_market_data.fetch_ohlcv.assert_awaited_once()

    # Verify all three fetch methods were called
    openbb_svc.fetch_fundamentals.assert_awaited_once_with("AAPL")
    openbb_svc.fetch_unusual_flow.assert_awaited_once_with("AAPL")
    openbb_svc.fetch_news_sentiment.assert_awaited_once_with("AAPL")


@patch("options_arena.api.routes.debate.run_debate", new_callable=AsyncMock)
@patch("options_arena.api.routes.debate.compute_dimensional_scores")
async def test_single_debate_passes_enrichment_to_run_debate(
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """Verify enrichment kwargs passed to run_debate."""
    mock_dim_scores.return_value = None
    mock_run_debate.return_value = _make_debate_result()

    fundamental = _make_fundamental()
    flow = _make_flow()
    sentiment = _make_sentiment()
    openbb_svc = _make_mock_openbb_service(fundamental, flow, sentiment)
    request = _make_mock_request(openbb_svc)

    mock_repo = AsyncMock()
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    mock_repo.save_debate = AsyncMock(return_value=1)

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=_make_quote())
    mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info())
    mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    bridge = DebateProgressBridge()

    await _run_debate_background(
        request=request,
        debate_id=1,
        ticker="AAPL",
        scan_id=None,
        settings=AppSettings(),
        repo=mock_repo,
        market_data=mock_market_data,
        options_data=mock_options_data,
        bridge=bridge,
    )

    # Check that run_debate was called with the enrichment data
    call_kwargs = mock_run_debate.call_args.kwargs
    assert call_kwargs["fundamentals"] is fundamental
    assert call_kwargs["flow"] is flow
    assert call_kwargs["sentiment"] is sentiment


@patch("options_arena.api.routes.debate.run_debate", new_callable=AsyncMock)
@patch("options_arena.api.routes.debate.compute_dimensional_scores")
async def test_single_debate_skips_enrichment_when_openbb_none(
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """Verify no error when app.state.openbb is None."""
    mock_dim_scores.return_value = None
    mock_run_debate.return_value = _make_debate_result()

    # No OpenBB service (None)
    request = _make_mock_request(openbb_svc=None)

    mock_repo = AsyncMock()
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    mock_repo.save_debate = AsyncMock(return_value=1)

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=_make_quote())
    mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info())
    mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    bridge = DebateProgressBridge()

    await _run_debate_background(
        request=request,
        debate_id=1,
        ticker="AAPL",
        scan_id=None,
        settings=AppSettings(),
        repo=mock_repo,
        market_data=mock_market_data,
        options_data=mock_options_data,
        bridge=bridge,
    )

    # Verify run_debate was called with None for all enrichment
    call_kwargs = mock_run_debate.call_args.kwargs
    assert call_kwargs["fundamentals"] is None
    assert call_kwargs["flow"] is None
    assert call_kwargs["sentiment"] is None


# ---------------------------------------------------------------------------
# Batch debate tests
# ---------------------------------------------------------------------------


@patch("options_arena.api.routes.debate.run_debate", new_callable=AsyncMock)
@patch("options_arena.api.routes.debate.compute_dimensional_scores")
async def test_batch_debate_fetches_enrichment_per_ticker(
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """Verify batch debate fetches enrichment for each ticker."""
    mock_dim_scores.return_value = None
    mock_run_debate.side_effect = [
        _make_debate_result("AAPL"),
        _make_debate_result("MSFT"),
    ]

    openbb_svc = _make_mock_openbb_service(_make_fundamental(), _make_flow(), _make_sentiment())
    request = _make_mock_request(openbb_svc)

    scores = [_make_ticker_score("AAPL"), _make_ticker_score("MSFT")]
    mock_repo = AsyncMock()
    mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)
    mock_repo.save_debate = AsyncMock(return_value=1)

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=_make_quote())
    mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info())
    mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    bridge = BatchProgressBridge()
    lock = asyncio.Lock()
    await lock.acquire()

    await _run_batch_debate_background(
        request=request,
        batch_id=1,
        tickers=["AAPL", "MSFT"],
        scan_id=1,
        settings=AppSettings(),
        repo=mock_repo,
        market_data=mock_market_data,
        options_data=mock_options_data,
        bridge=bridge,
        lock=lock,
    )

    # Each ticker should trigger 3 fetch calls (fundamentals, flow, sentiment)
    assert openbb_svc.fetch_fundamentals.await_count == 2
    assert openbb_svc.fetch_unusual_flow.await_count == 2
    assert openbb_svc.fetch_news_sentiment.await_count == 2


@patch("options_arena.api.routes.debate.run_debate", new_callable=AsyncMock)
@patch("options_arena.api.routes.debate.compute_dimensional_scores")
async def test_enrichment_failure_does_not_crash_debate(
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """Verify debate completes when all 3 OpenBB fetches return None."""
    mock_dim_scores.return_value = None
    mock_run_debate.return_value = _make_debate_result()

    # All fetches return None (simulating unavailable OpenBB)
    openbb_svc = _make_mock_openbb_service(fundamentals=None, flow=None, sentiment=None)
    request = _make_mock_request(openbb_svc)

    mock_repo = AsyncMock()
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    mock_repo.save_debate = AsyncMock(return_value=1)

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=_make_quote())
    mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info())
    mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    bridge = DebateProgressBridge()

    await _run_debate_background(
        request=request,
        debate_id=1,
        ticker="AAPL",
        scan_id=None,
        settings=AppSettings(),
        repo=mock_repo,
        market_data=mock_market_data,
        options_data=mock_options_data,
        bridge=bridge,
    )

    # Debate still runs — run_debate was called
    mock_run_debate.assert_awaited_once()
    # All enrichment args are None
    call_kwargs = mock_run_debate.call_args.kwargs
    assert call_kwargs["fundamentals"] is None
    assert call_kwargs["flow"] is None
    assert call_kwargs["sentiment"] is None


@patch("options_arena.api.routes.debate.run_debate", new_callable=AsyncMock)
@patch("options_arena.api.routes.debate.compute_dimensional_scores")
async def test_partial_enrichment_passes_through(
    mock_dim_scores: MagicMock,
    mock_run_debate: AsyncMock,
) -> None:
    """Verify partial data passed when only some fetches succeed."""
    mock_dim_scores.return_value = None
    mock_run_debate.return_value = _make_debate_result()

    fundamental = _make_fundamental()
    # Only fundamentals available; flow and sentiment return None
    openbb_svc = _make_mock_openbb_service(fundamentals=fundamental, flow=None, sentiment=None)
    request = _make_mock_request(openbb_svc)

    mock_repo = AsyncMock()
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    mock_repo.save_debate = AsyncMock(return_value=1)

    mock_market_data = AsyncMock()
    mock_market_data.fetch_quote = AsyncMock(return_value=_make_quote())
    mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info())
    mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    bridge = DebateProgressBridge()

    await _run_debate_background(
        request=request,
        debate_id=1,
        ticker="AAPL",
        scan_id=None,
        settings=AppSettings(),
        repo=mock_repo,
        market_data=mock_market_data,
        options_data=mock_options_data,
        bridge=bridge,
    )

    # Verify partial enrichment passed through correctly
    call_kwargs = mock_run_debate.call_args.kwargs
    assert call_kwargs["fundamentals"] is fundamental
    assert call_kwargs["flow"] is None
    assert call_kwargs["sentiment"] is None
