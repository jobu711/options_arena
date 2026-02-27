"""Tests for pipeline watchlist mode.

Covers:
  - Watchlist tickers bypass universe service fetch.
  - Watchlist tickers still trigger OHLCV fetch.
  - Normal path (no watchlist) still uses universe service.
  - Empty watchlist list passes through pipeline.
  - Watchlist mode preserves the scan preset in ScanRun.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from options_arena.models import AppSettings, ScanPreset
from options_arena.models.market_data import OHLCV
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import CancellationToken, ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_bars(ticker: str, n: int = 250) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars for a ticker."""
    bars: list[OHLCV] = []
    base_price = 100.0
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        close = base_price + (i % 10) - 5
        bars.append(
            OHLCV(
                ticker=ticker,
                date=d,
                open=Decimal(str(round(close - 0.5, 2))),
                high=Decimal(str(round(close + 1.0, 2))),
                low=Decimal(str(round(close - 1.0, 2))),
                close=Decimal(str(round(close, 2))),
                adjusted_close=Decimal(str(round(close, 2))),
                volume=1_000_000 + i * 1000,
            )
        )
    return bars


def _make_batch_result(tickers: list[str], bars_per_ticker: int = 250) -> BatchOHLCVResult:
    """Build a BatchOHLCVResult with synthetic data."""
    results: list[TickerOHLCVResult] = []
    for ticker in tickers:
        results.append(
            TickerOHLCVResult(ticker=ticker, data=_make_ohlcv_bars(ticker, bars_per_ticker))
        )
    return BatchOHLCVResult(results=results)


def _make_pipeline(
    *,
    optionable_tickers: list[str] | None = None,
    batch_result: BatchOHLCVResult | None = None,
    settings: AppSettings | None = None,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services."""
    _settings = settings or AppSettings()
    tickers = optionable_tickers if optionable_tickers is not None else ["AAPL", "MSFT", "GOOG"]

    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])

    mock_market_data = AsyncMock()
    mock_market_data.fetch_batch_ohlcv = AsyncMock(
        return_value=batch_result or _make_batch_result(tickers)
    )

    mock_options_data = AsyncMock()
    mock_fred = AsyncMock()
    mock_repository = AsyncMock()

    pipeline = ScanPipeline(
        settings=_settings,
        market_data=mock_market_data,
        options_data=mock_options_data,
        fred=mock_fred,
        universe=mock_universe,
        repository=mock_repository,
    )

    mocks = {
        "universe": mock_universe,
        "market_data": mock_market_data,
        "options_data": mock_options_data,
        "fred": mock_fred,
        "repository": mock_repository,
    }

    return pipeline, mocks


def _noop_progress(phase: ScanPhase, current: int, total: int) -> None:
    """No-op progress callback."""


# ---------------------------------------------------------------------------
# Watchlist mode tests
# ---------------------------------------------------------------------------


class TestPipelineWatchlistMode:
    """Pipeline watchlist mode bypasses universe fetch."""

    async def test_run_with_watchlist_tickers_skips_universe_fetch(self) -> None:
        """When watchlist_tickers is provided, universe service methods are NOT called."""
        watchlist_tickers = ["AAPL", "TSLA"]
        batch = _make_batch_result(watchlist_tickers)
        pipeline, mocks = _make_pipeline(
            optionable_tickers=["AAPL", "MSFT", "GOOG"],
            batch_result=batch,
        )

        result = await pipeline._phase_universe(
            ScanPreset.SP500, _noop_progress, watchlist_tickers=watchlist_tickers
        )

        # Universe service should NOT have been called
        mocks["universe"].fetch_optionable_tickers.assert_not_awaited()
        mocks["universe"].fetch_sp500_constituents.assert_not_awaited()

        # But tickers should be the watchlist tickers
        assert result.tickers == watchlist_tickers

    async def test_run_with_watchlist_tickers_fetches_ohlcv(self) -> None:
        """When watchlist_tickers is provided, market_data.fetch_batch_ohlcv IS called."""
        watchlist_tickers = ["NVDA", "AMD"]
        batch = _make_batch_result(watchlist_tickers)
        pipeline, mocks = _make_pipeline(batch_result=batch)

        await pipeline._phase_universe(
            ScanPreset.SP500, _noop_progress, watchlist_tickers=watchlist_tickers
        )

        mocks["market_data"].fetch_batch_ohlcv.assert_awaited_once_with(
            watchlist_tickers, period="1y"
        )

    async def test_run_without_watchlist_uses_universe(self) -> None:
        """Normal path (watchlist_tickers=None) fetches from universe service."""
        pipeline, mocks = _make_pipeline(optionable_tickers=["AAPL", "MSFT"])

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        mocks["universe"].fetch_optionable_tickers.assert_awaited_once()
        assert result.tickers == ["AAPL", "MSFT"]

    async def test_watchlist_mode_empty_list(self) -> None:
        """Empty watchlist ticker list still goes through pipeline without error."""
        batch = BatchOHLCVResult(results=[])
        pipeline, mocks = _make_pipeline(batch_result=batch)

        result = await pipeline._phase_universe(
            ScanPreset.SP500, _noop_progress, watchlist_tickers=[]
        )

        # Universe service should NOT have been called
        mocks["universe"].fetch_optionable_tickers.assert_not_awaited()

        assert result.tickers == []
        assert result.ohlcv_map == {}
        assert result.sp500_sectors == {}

    async def test_watchlist_mode_preserves_preset(self) -> None:
        """Watchlist mode still records the preset in the pipeline result.

        The preset flows through to ScanRun in Phase 4. Here we verify it
        is passed correctly to _phase_universe and the result tracks the
        ticker list from the watchlist.
        """
        watchlist_tickers = ["AAPL"]
        batch = _make_batch_result(watchlist_tickers)
        pipeline, mocks = _make_pipeline(batch_result=batch)

        # Cancel after Phase 1 so we can inspect the partial result
        token = CancellationToken()
        token.cancel()

        result = await pipeline.run(
            ScanPreset.SP500, token, _noop_progress, watchlist_tickers=watchlist_tickers
        )

        # The scan_run preset should be SP500 even in watchlist mode
        assert result.scan_run.preset == ScanPreset.SP500
        assert result.scan_run.tickers_scanned == 1
