"""Tests for sector filtering and enrichment in the scan pipeline.

Covers:
  - sector_map construction from SP500 constituents via SECTOR_ALIASES.
  - Sector filter (ScanConfig.sectors) reduces universe to matching sectors (OR logic).
  - Empty ScanConfig.sectors means no filtering (all tickers pass).
  - sector_map propagated on UniverseResult for downstream phases.
  - Phase 2 sets TickerScore.sector from sector_map.
  - Phase 3 sets TickerScore.company_name from TickerInfo.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from options_arena.models import (
    AppSettings,
    GICSSector,
    ScanPreset,
)
from options_arena.models.market_data import OHLCV
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult
from options_arena.services.universe import SP500Constituent

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
# sector_map construction tests
# ---------------------------------------------------------------------------


class TestSectorMapConstruction:
    """sector_map is built from SP500 constituents via SECTOR_ALIASES."""

    async def test_sector_map_built_from_constituents(self) -> None:
        """sector_map maps tickers to GICSSector enums."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
            SP500Constituent(ticker="JNJ", sector="Health Care"),
        ]
        pipeline, _ = _make_pipeline(
            optionable_tickers=["AAPL", "JPM", "JNJ"],
            sp500_constituents=sp500,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.sector_map["AAPL"] is GICSSector.INFORMATION_TECHNOLOGY
        assert result.sector_map["JPM"] is GICSSector.FINANCIALS
        assert result.sector_map["JNJ"] is GICSSector.HEALTH_CARE

    async def test_sector_map_handles_all_11_gics_sectors(self) -> None:
        """All 11 GICS sectors can be mapped from their canonical names."""
        sectors = [
            ("A", "Communication Services"),
            ("B", "Consumer Discretionary"),
            ("C", "Consumer Staples"),
            ("D", "Energy"),
            ("E", "Financials"),
            ("F", "Health Care"),
            ("G", "Industrials"),
            ("H", "Information Technology"),
            ("I", "Materials"),
            ("J", "Real Estate"),
            ("K", "Utilities"),
        ]
        sp500 = [SP500Constituent(ticker=t, sector=s) for t, s in sectors]
        tickers = [t for t, _ in sectors]
        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert len(result.sector_map) == 11

    async def test_sector_map_skips_unknown_sectors(self) -> None:
        """Unknown sector strings are skipped (not added to sector_map)."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="XYZ", sector="Unknown Sector"),
        ]
        pipeline, _ = _make_pipeline(
            optionable_tickers=["AAPL", "XYZ"],
            sp500_constituents=sp500,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert "AAPL" in result.sector_map
        assert "XYZ" not in result.sector_map

    async def test_sector_map_empty_when_no_sp500(self) -> None:
        """sector_map is empty when there are no SP500 constituents."""
        pipeline, _ = _make_pipeline(
            optionable_tickers=["AAPL"],
            sp500_constituents=[],
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.sector_map == {}


# ---------------------------------------------------------------------------
# Sector filter tests
# ---------------------------------------------------------------------------


class TestSectorFilter:
    """ScanConfig.sectors filters universe to matching sectors only."""

    async def test_sector_filter_reduces_universe(self) -> None:
        """When sectors is non-empty, only tickers in those sectors pass."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="MSFT", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
            SP500Constituent(ticker="GS", sector="Financials"),
        ]
        tickers = ["AAPL", "MSFT", "JPM", "GS"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY]

        # After sector filtering, only AAPL and MSFT are passed to fetch_batch_ohlcv.
        # The mock returns data matching the filtered set.
        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["AAPL", "MSFT"]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # Only tech tickers should remain
        assert set(result.tickers) == {"AAPL", "MSFT"}
        # Both should be in ohlcv_map (they have enough bars)
        assert "AAPL" in result.ohlcv_map
        assert "MSFT" in result.ohlcv_map

    async def test_sector_filter_or_logic_multiple_sectors(self) -> None:
        """Multiple sectors use OR logic (include tickers matching any)."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
            SP500Constituent(ticker="XOM", sector="Energy"),
        ]
        tickers = ["AAPL", "JPM", "XOM"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY, GICSSector.ENERGY]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(tickers),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert set(result.tickers) == {"AAPL", "XOM"}

    async def test_empty_sectors_config_no_filtering(self) -> None:
        """When ScanConfig.sectors is empty, all tickers pass."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
        ]
        tickers = ["AAPL", "JPM"]

        settings = AppSettings()
        assert settings.scan.sectors == []

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(tickers),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # No filtering applied — all tickers remain
        assert set(result.tickers) == {"AAPL", "JPM"}

    async def test_sector_filter_removes_non_sp500_tickers(self) -> None:
        """Tickers not in sector_map are removed when sector filter is active."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
        ]
        # XYZ is not in SP500, so it has no sector
        tickers = ["AAPL", "XYZ"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(tickers),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.tickers == ["AAPL"]

    async def test_sector_filter_with_sp500_preset(self) -> None:
        """Sector filter works in combination with SP500 preset."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
        ]
        # Extra non-SP500 ticker
        tickers = ["AAPL", "JPM", "XYZ"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["AAPL", "JPM"]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.SP500, _noop_progress)

        # SP500 filter removes XYZ, sector filter removes JPM
        assert result.tickers == ["AAPL"]

    async def test_sector_filter_logs_count_info(self, caplog: pytest.LogCaptureFixture) -> None:
        """Sector filter logs before/after count at INFO level."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
        ]
        tickers = ["AAPL", "JPM"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(tickers),
            settings=settings,
        )

        with caplog.at_level(logging.INFO, logger="options_arena.scan.pipeline"):
            await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("Sector filter" in msg and "2 -> 1" in msg for msg in info_messages)


# ---------------------------------------------------------------------------
# Phase 2 sector enrichment tests
# ---------------------------------------------------------------------------


class TestPhase2SectorEnrichment:
    """Phase 2 sets TickerScore.sector from universe_result.sector_map."""

    async def test_ticker_score_sector_set_from_sector_map(self) -> None:
        """TickerScore.sector is set for tickers present in sector_map."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="MSFT", sector="Information Technology"),
        ]
        tickers = ["AAPL", "MSFT"]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(tickers),
        )

        universe_result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)
        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        for ts in scoring_result.scores:
            assert ts.sector is GICSSector.INFORMATION_TECHNOLOGY

    async def test_ticker_score_sector_none_when_not_in_map(self) -> None:
        """TickerScore.sector remains None for tickers not in sector_map."""
        # No SP500 constituents — sector_map is empty
        pipeline, _ = _make_pipeline(
            optionable_tickers=["AAPL"],
            sp500_constituents=[],
        )

        universe_result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)
        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        for ts in scoring_result.scores:
            assert ts.sector is None
