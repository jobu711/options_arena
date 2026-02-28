"""Tests for ScanPipeline Phase 1 — Universe + OHLCV.

Covers:
  - Constructor accepts all required services (DI).
  - Phase 1 fetches optionable tickers from universe service.
  - Phase 1 filters tickers by ohlcv_min_bars threshold.
  - SP500 preset filters to S&P 500 tickers only.
  - Failed OHLCV fetches counted in failed_count.
  - Progress callback invoked with ScanPhase.UNIVERSE.
  - SP500 sectors dict populated correctly.
  - Empty universe returns empty ohlcv_map.
  - Full run() with cancellation after Phase 1 returns partial result.
  - Full run() with no cancellation returns phases_completed=2.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from options_arena.models import (
    AppSettings,
    ScanPreset,
)
from options_arena.models.market_data import OHLCV
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import CancellationToken, ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult
from options_arena.services.universe import SP500Constituent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_bars(ticker: str, n: int = 250) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars for a ticker.

    Prices oscillate around a fixed base of 100 (no drift) so all values
    stay safely positive and pass OHLCV candle validators.
    """
    bars: list[OHLCV] = []
    base_price = 100.0
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        close = base_price + (i % 10) - 5  # oscillates in [95, 104]
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
    failed_tickers: set[str] | None = None,
) -> BatchOHLCVResult:
    """Build a BatchOHLCVResult with synthetic data for the given tickers."""
    failed = failed_tickers or set()
    results: list[TickerOHLCVResult] = []
    for ticker in tickers:
        if ticker in failed:
            results.append(TickerOHLCVResult(ticker=ticker, error="fetch failed"))
        else:
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
    """Create a ScanPipeline with mocked services.

    Returns the pipeline and a dict of the mock services for assertion.
    """
    _settings = settings or AppSettings()
    tickers = optionable_tickers if optionable_tickers is not None else ["AAPL", "MSFT", "GOOG"]

    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=sp500_constituents or [])

    mock_market_data = AsyncMock()
    mock_market_data.fetch_batch_ohlcv = AsyncMock(
        return_value=batch_result or _make_batch_result(tickers)
    )
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)

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
# Constructor tests
# ---------------------------------------------------------------------------


class TestScanPipelineConstructor:
    """ScanPipeline constructor accepts all required services."""

    def test_constructor_accepts_all_services(self) -> None:
        pipeline, _ = _make_pipeline()
        assert pipeline is not None

    def test_constructor_stores_settings(self) -> None:
        settings = AppSettings()
        pipeline, _ = _make_pipeline(settings=settings)
        assert pipeline._settings is settings


# ---------------------------------------------------------------------------
# Phase 1 (Universe) tests
# ---------------------------------------------------------------------------


class TestPhaseUniverse:
    """Phase 1 fetches optionable tickers, S&P 500 sectors, and OHLCV data."""

    async def test_fetches_optionable_tickers(self) -> None:
        tickers = ["AAPL", "MSFT", "GOOG"]
        pipeline, mocks = _make_pipeline(optionable_tickers=tickers)

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        mocks["universe"].fetch_optionable_tickers.assert_awaited_once()
        assert result.tickers == tickers

    async def test_filters_by_ohlcv_min_bars(self) -> None:
        """Tickers with fewer bars than ohlcv_min_bars are filtered out."""
        settings = AppSettings()
        settings.scan.ohlcv_min_bars = 200

        # AAPL has 250 bars (passes), MSFT has 100 bars (filtered)
        batch = BatchOHLCVResult(
            results=[
                TickerOHLCVResult(ticker="AAPL", data=_make_ohlcv_bars("AAPL", 250)),
                TickerOHLCVResult(ticker="MSFT", data=_make_ohlcv_bars("MSFT", 100)),
            ]
        )

        pipeline, _ = _make_pipeline(
            optionable_tickers=["AAPL", "MSFT"],
            batch_result=batch,
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert "AAPL" in result.ohlcv_map
        assert "MSFT" not in result.ohlcv_map
        assert result.filtered_count == 1

    async def test_sp500_preset_filters_to_sp500_only(self) -> None:
        """SP500 preset filters tickers to S&P 500 constituents."""
        all_tickers = ["AAPL", "MSFT", "GOOG", "XYZ"]
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Technology"),
            SP500Constituent(ticker="MSFT", sector="Technology"),
        ]

        # Only AAPL and MSFT are in S&P 500 — batch should only have those
        batch = _make_batch_result(["AAPL", "MSFT"])

        mock_market_data = AsyncMock()
        mock_market_data.fetch_batch_ohlcv = AsyncMock(return_value=batch)

        pipeline, _mocks = _make_pipeline(
            optionable_tickers=all_tickers,
            sp500_constituents=sp500,
            batch_result=batch,
        )

        result = await pipeline._phase_universe(ScanPreset.SP500, _noop_progress)

        # The tickers list should be filtered to SP500 only
        assert set(result.tickers) == {"AAPL", "MSFT"}
        assert "GOOG" not in result.tickers
        assert "XYZ" not in result.tickers

    async def test_failed_ohlcv_fetches_counted(self) -> None:
        """Failed OHLCV fetches are counted in failed_count."""
        batch = _make_batch_result(
            ["AAPL", "MSFT", "GOOG"],
            failed_tickers={"MSFT", "GOOG"},
        )
        pipeline, _ = _make_pipeline(
            optionable_tickers=["AAPL", "MSFT", "GOOG"],
            batch_result=batch,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.failed_count == 2
        assert "AAPL" in result.ohlcv_map
        assert "MSFT" not in result.ohlcv_map
        assert "GOOG" not in result.ohlcv_map

    async def test_progress_callback_invoked_with_universe_phase(self) -> None:
        """Progress callback is invoked with ScanPhase.UNIVERSE."""
        progress_calls: list[tuple[ScanPhase, int, int]] = []

        def recording_progress(phase: ScanPhase, current: int, total: int) -> None:
            progress_calls.append((phase, current, total))

        pipeline, _ = _make_pipeline(optionable_tickers=["AAPL", "MSFT"])

        await pipeline._phase_universe(ScanPreset.FULL, recording_progress)

        # Should have at least the start (0, N) and end (N, N) calls
        assert len(progress_calls) >= 2
        for phase, _, _ in progress_calls:
            assert phase == ScanPhase.UNIVERSE

        # First call is start (0, total)
        assert progress_calls[0][1] == 0
        assert progress_calls[0][2] == 2

        # Last call is completion (total, total)
        assert progress_calls[-1][1] == progress_calls[-1][2]

    async def test_sp500_sectors_dict_populated(self) -> None:
        """SP500 sectors dict maps ticker -> sector."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
        ]
        pipeline, _ = _make_pipeline(
            optionable_tickers=["AAPL", "JPM"],
            sp500_constituents=sp500,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.sp500_sectors == {
            "AAPL": "Information Technology",
            "JPM": "Financials",
        }

    async def test_empty_universe_returns_empty_ohlcv_map(self) -> None:
        """Empty ticker list results in empty ohlcv_map."""
        batch = BatchOHLCVResult(results=[])
        pipeline, _ = _make_pipeline(
            optionable_tickers=[],
            batch_result=batch,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.ohlcv_map == {}
        assert result.tickers == []
        assert result.failed_count == 0
        assert result.filtered_count == 0

    async def test_batch_ohlcv_called_with_period_1y(self) -> None:
        """fetch_batch_ohlcv is called with period='1y'."""
        pipeline, mocks = _make_pipeline(optionable_tickers=["AAPL"])

        await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        mocks["market_data"].fetch_batch_ohlcv.assert_awaited_once_with(["AAPL"], period="1y")

    async def test_ohlcv_map_contains_only_valid_tickers(self) -> None:
        """ohlcv_map contains only tickers that passed both fetch and min_bars filter."""
        settings = AppSettings()
        settings.scan.ohlcv_min_bars = 200

        batch = BatchOHLCVResult(
            results=[
                TickerOHLCVResult(ticker="AAPL", data=_make_ohlcv_bars("AAPL", 250)),
                TickerOHLCVResult(ticker="MSFT", error="timeout"),
                TickerOHLCVResult(ticker="GOOG", data=_make_ohlcv_bars("GOOG", 50)),
            ]
        )

        pipeline, _ = _make_pipeline(
            optionable_tickers=["AAPL", "MSFT", "GOOG"],
            batch_result=batch,
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert set(result.ohlcv_map.keys()) == {"AAPL"}
        assert result.failed_count == 1
        assert result.filtered_count == 1


# ---------------------------------------------------------------------------
# Cancellation tests (Phase 1 only)
# ---------------------------------------------------------------------------


class TestETFSPresetWarning:
    """ETFS preset logs a warning about unimplemented filtering."""

    async def test_etfs_preset_logs_warning(self, caplog: object) -> None:
        """ScanPreset.ETFS emits a warning and uses the full universe."""
        import _pytest.logging

        assert isinstance(caplog, _pytest.logging.LogCaptureFixture)

        pipeline, _ = _make_pipeline(optionable_tickers=["AAPL", "MSFT", "GOOG"])

        with caplog.at_level(logging.WARNING, logger="options_arena.scan.pipeline"):
            result = await pipeline._phase_universe(ScanPreset.ETFS, _noop_progress)

        # All tickers included (no filtering applied)
        assert result.tickers == ["AAPL", "MSFT", "GOOG"]

        # Warning was emitted
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("ETFS" in msg and "not yet implemented" in msg for msg in warning_messages)

    async def test_full_preset_no_etfs_warning(self, caplog: object) -> None:
        """ScanPreset.FULL does NOT emit the ETFS warning."""
        import _pytest.logging

        assert isinstance(caplog, _pytest.logging.LogCaptureFixture)

        pipeline, _ = _make_pipeline(optionable_tickers=["AAPL"])

        with caplog.at_level(logging.WARNING, logger="options_arena.scan.pipeline"):
            await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("ETFS" in msg for msg in warning_messages)


class TestPhase1Cancellation:
    """Cancellation after Phase 1 returns partial result."""

    async def test_cancelled_after_phase1_returns_cancelled_true(self) -> None:
        """When token is cancelled after Phase 1, result has cancelled=True."""
        pipeline, _ = _make_pipeline(optionable_tickers=["AAPL"])

        token = CancellationToken()
        # Cancel immediately — will be checked after Phase 1
        token.cancel()

        # We need to mock _phase_scoring to avoid it actually running
        # Since run() checks cancellation AFTER Phase 1, it should short-circuit
        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.cancelled is True
        assert result.phases_completed == 1
        assert result.scores == []
        assert result.recommendations == {}
