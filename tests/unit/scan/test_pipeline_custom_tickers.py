"""Tests for ScanPipeline Phase 1 custom tickers branch (#244).

Covers:
  - Custom tickers are used when provided (bypass preset filters).
  - Non-optionable custom tickers are excluded (intersection).
  - Preset/sector/industry filters are bypassed with custom tickers.
  - Empty custom_tickers falls back to normal preset behavior (regression).
  - All custom tickers non-optionable → 0 valid tickers.
  - OHLCV fetch and min_bars filter still apply to custom tickers.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from options_arena.models import AppSettings, GICSSector, ScanPreset
from options_arena.models.market_data import OHLCV
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult
from options_arena.services.universe import SP500Constituent

# ---------------------------------------------------------------------------
# Helpers (adapted from test_pipeline_phase1.py)
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


def _make_batch_result(
    tickers: list[str],
    bars_per_ticker: int = 250,
) -> BatchOHLCVResult:
    """Build a BatchOHLCVResult with synthetic data for the given tickers."""
    results: list[TickerOHLCVResult] = []
    for ticker in tickers:
        results.append(
            TickerOHLCVResult(ticker=ticker, data=_make_ohlcv_bars(ticker, bars_per_ticker))
        )
    return BatchOHLCVResult(results=results)


def _make_pipeline(
    *,
    optionable_tickers: list[str] | None = None,
    sp500_constituents: list[SP500Constituent] | None = None,
    batch_result: BatchOHLCVResult | None = None,
    settings: AppSettings | None = None,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services."""
    _settings = settings or AppSettings()
    tickers = optionable_tickers if optionable_tickers is not None else ["AAPL", "MSFT", "GOOG"]

    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=sp500_constituents or [])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=[])

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
    """No-op progress callback for tests that don't inspect progress."""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineCustomTickers:
    """Phase 1 custom tickers branch tests."""

    async def test_custom_tickers_used_when_set(self) -> None:
        """Pipeline scans only custom tickers when provided."""
        optionable = ["AAPL", "MSFT", "GOOG", "AMZN", "TSLA"]
        settings = AppSettings()
        settings.scan = settings.scan.model_copy(update={"custom_tickers": ["AAPL", "MSFT"]})

        pipeline, mocks = _make_pipeline(
            optionable_tickers=optionable,
            batch_result=_make_batch_result(["AAPL", "MSFT"]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # Only custom tickers appear in the result
        assert set(result.ohlcv_map.keys()) == {"AAPL", "MSFT"}

    async def test_custom_tickers_intersect_optionable(self) -> None:
        """Non-optionable custom tickers are excluded."""
        optionable = ["AAPL", "MSFT"]
        settings = AppSettings()
        settings.scan = settings.scan.model_copy(
            update={"custom_tickers": ["AAPL", "FAKE1", "FAKE2"]}
        )

        pipeline, mocks = _make_pipeline(
            optionable_tickers=optionable,
            batch_result=_make_batch_result(["AAPL"]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # Only AAPL is optionable and fetched
        assert "AAPL" in result.ohlcv_map
        assert "FAKE1" not in result.ohlcv_map
        assert "FAKE2" not in result.ohlcv_map

    async def test_custom_tickers_bypass_preset_filter(self) -> None:
        """Preset filter is skipped when custom tickers provided."""
        sp500 = [
            SP500Constituent(ticker="AAPL", company_name="Apple", sector="Technology"),
        ]
        optionable = ["AAPL", "MSFT", "GOOG"]
        settings = AppSettings()
        # MSFT is not in SP500 but should still be scanned via custom_tickers
        settings.scan = settings.scan.model_copy(update={"custom_tickers": ["MSFT"]})

        pipeline, mocks = _make_pipeline(
            optionable_tickers=optionable,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["MSFT"]),
            settings=settings,
        )

        # Using SP500 preset — normally MSFT wouldn't be in the result since
        # it's not in sp500_constituents. But custom_tickers bypasses preset.
        result = await pipeline._phase_universe(ScanPreset.SP500, _noop_progress)

        assert "MSFT" in result.ohlcv_map

    async def test_custom_tickers_bypass_sector_filter(self) -> None:
        """Sector filter is skipped when custom tickers provided."""
        optionable = ["AAPL", "MSFT", "XOM"]
        settings = AppSettings()
        settings.scan = settings.scan.model_copy(
            update={
                "custom_tickers": ["AAPL", "XOM"],
                "sectors": [GICSSector.ENERGY],  # would normally filter to XOM only
            }
        )

        pipeline, mocks = _make_pipeline(
            optionable_tickers=optionable,
            batch_result=_make_batch_result(["AAPL", "XOM"]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # Both AAPL and XOM should be present — sector filter bypassed
        assert "AAPL" in result.ohlcv_map
        assert "XOM" in result.ohlcv_map

    async def test_empty_custom_tickers_uses_preset(self) -> None:
        """Empty custom_tickers falls back to normal preset behavior (regression)."""
        sp500 = [
            SP500Constituent(ticker="AAPL", company_name="Apple", sector="Technology"),
        ]
        optionable = ["AAPL", "MSFT", "GOOG"]
        settings = AppSettings()
        # custom_tickers is default empty — should use SP500 preset filter
        assert settings.scan.custom_tickers == []

        pipeline, mocks = _make_pipeline(
            optionable_tickers=optionable,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["AAPL"]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.SP500, _noop_progress)

        # Only AAPL is in SP500
        assert "AAPL" in result.ohlcv_map
        assert "MSFT" not in result.ohlcv_map

    async def test_all_custom_tickers_non_optionable(self) -> None:
        """All non-optionable → 0 valid tickers → pipeline runs with empty OHLCV map."""
        optionable = ["AAPL", "MSFT"]
        settings = AppSettings()
        settings.scan = settings.scan.model_copy(update={"custom_tickers": ["FAKE1", "FAKE2"]})

        pipeline, mocks = _make_pipeline(
            optionable_tickers=optionable,
            batch_result=BatchOHLCVResult(results=[]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.ohlcv_map == {}

    async def test_ohlcv_min_bars_still_applies(self) -> None:
        """OHLCV min_bars filter still applies to custom tickers."""
        optionable = ["AAPL", "MSFT"]
        settings = AppSettings()
        settings.scan = settings.scan.model_copy(update={"custom_tickers": ["AAPL", "MSFT"]})
        settings.scan.ohlcv_min_bars = 200

        # AAPL has 250 bars (passes), MSFT has 100 bars (filtered)
        batch = BatchOHLCVResult(
            results=[
                TickerOHLCVResult(ticker="AAPL", data=_make_ohlcv_bars("AAPL", 250)),
                TickerOHLCVResult(ticker="MSFT", data=_make_ohlcv_bars("MSFT", 100)),
            ]
        )

        pipeline, mocks = _make_pipeline(
            optionable_tickers=optionable,
            batch_result=batch,
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert "AAPL" in result.ohlcv_map
        assert "MSFT" not in result.ohlcv_map
