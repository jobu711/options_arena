"""Tests for industry group filtering and enrichment in the scan pipeline.

Covers:
  - Phase 1 builds industry_group_map from sector_map via SECTOR_TO_INDUSTRY_GROUPS.
  - Phase 1 filters tickers when ScanConfig.industry_groups is non-empty.
  - Phase 1 passes all tickers when ScanConfig.industry_groups is empty.
  - Phase 2 enriches TickerScore.industry_group from industry_group_map.
  - Combined sector + industry group filter (AND logic).
  - Existing sector filtering still works (regression).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from options_arena.models import (
    AppSettings,
    GICSIndustryGroup,
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
# Phase 1: industry_group_map construction
# ---------------------------------------------------------------------------


class TestIndustryGroupMapConstruction:
    """Phase 1 builds industry_group_map from sector_map via SECTOR_TO_INDUSTRY_GROUPS."""

    async def test_single_group_sector_inferred(self) -> None:
        """Sectors with exactly 1 industry group produce a map entry."""
        # Materials has exactly 1 group: MATERIALS
        # Utilities has exactly 1 group: UTILITIES
        sp500 = [
            SP500Constituent(ticker="FCX", sector="Materials"),
            SP500Constituent(ticker="NEE", sector="Utilities"),
        ]
        tickers = ["FCX", "NEE"]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.industry_group_map["FCX"] == GICSIndustryGroup.MATERIALS
        assert result.industry_group_map["NEE"] == GICSIndustryGroup.UTILITIES

    async def test_multi_group_sector_with_sub_industry_inferred(self) -> None:
        """Sectors with multiple groups ARE inferred when sub_industry is present."""
        # IT has 3 groups, but sub_industry disambiguates
        sp500 = [
            SP500Constituent(
                ticker="AAPL",
                sector="Information Technology",
                sub_industry="Technology Hardware Storage & Peripherals",
            ),
        ]
        tickers = ["AAPL"]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.industry_group_map["AAPL"] == GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT

    async def test_multi_group_sector_without_sub_industry_not_inferred(self) -> None:
        """Sectors with multiple groups are NOT inferred without sub_industry."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
        ]
        tickers = ["AAPL"]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # AAPL should NOT be in industry_group_map because IT has multiple groups
        # and no sub_industry is available
        assert "AAPL" not in result.industry_group_map

    async def test_empty_sp500_yields_empty_map(self) -> None:
        """No SP500 constituents yields empty industry_group_map."""
        pipeline, _ = _make_pipeline(
            optionable_tickers=["AAPL"],
            sp500_constituents=[],
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.industry_group_map == {}


# ---------------------------------------------------------------------------
# Phase 1: industry group filter
# ---------------------------------------------------------------------------


class TestPhase1IndustryGroupFilter:
    """ScanConfig.industry_groups filters universe to matching industry groups."""

    async def test_industry_group_filter_narrows_tickers(self) -> None:
        """When industry_groups is non-empty, only matching tickers pass."""
        # Utilities -> single group -> UTILITIES
        # Materials -> single group -> MATERIALS
        sp500 = [
            SP500Constituent(ticker="NEE", sector="Utilities"),
            SP500Constituent(ticker="FCX", sector="Materials"),
        ]
        tickers = ["NEE", "FCX"]

        settings = AppSettings()
        settings.scan.industry_groups = [GICSIndustryGroup.UTILITIES]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["NEE"]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.tickers == ["NEE"]

    async def test_industry_group_filter_empty_passes_all(self) -> None:
        """When industry_groups is empty, all tickers pass."""
        sp500 = [
            SP500Constituent(ticker="NEE", sector="Utilities"),
            SP500Constituent(ticker="FCX", sector="Materials"),
        ]
        tickers = ["NEE", "FCX"]

        settings = AppSettings()
        assert settings.scan.industry_groups == []

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(tickers),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert set(result.tickers) == {"NEE", "FCX"}

    async def test_industry_group_filter_no_matches_empty_result(self) -> None:
        """When no tickers match the configured industry groups, result is empty."""
        sp500 = [
            SP500Constituent(ticker="NEE", sector="Utilities"),
        ]
        tickers = ["NEE"]

        settings = AppSettings()
        settings.scan.industry_groups = [GICSIndustryGroup.BANKS]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result([]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert result.tickers == []

    async def test_industry_group_filter_logs_count(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Industry group filter logs before/after count at INFO level."""
        sp500 = [
            SP500Constituent(ticker="NEE", sector="Utilities"),
            SP500Constituent(ticker="FCX", sector="Materials"),
        ]
        tickers = ["NEE", "FCX"]

        settings = AppSettings()
        settings.scan.industry_groups = [GICSIndustryGroup.UTILITIES]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["NEE"]),
            settings=settings,
        )

        with caplog.at_level(logging.INFO, logger="options_arena.scan.pipeline"):
            await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("Industry group filter" in msg and "2 -> 1" in msg for msg in info_messages)


# ---------------------------------------------------------------------------
# Combined sector + industry group filter
# ---------------------------------------------------------------------------


class TestCombinedFilters:
    """Sector and industry group filters apply together (AND logic)."""

    async def test_sector_and_industry_group_both_applied(self) -> None:
        """Both sector and industry group filters narrow the universe."""
        sp500 = [
            SP500Constituent(ticker="NEE", sector="Utilities"),
            SP500Constituent(ticker="FCX", sector="Materials"),
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
        ]
        tickers = ["NEE", "FCX", "AAPL"]

        settings = AppSettings()
        # Sector filter: only Utilities and Materials
        settings.scan.sectors = [GICSSector.UTILITIES, GICSSector.MATERIALS]
        # Industry group filter: only UTILITIES
        settings.scan.industry_groups = [GICSIndustryGroup.UTILITIES]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["NEE"]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # AAPL removed by sector filter, FCX removed by industry group filter
        assert result.tickers == ["NEE"]


# ---------------------------------------------------------------------------
# Phase 2: industry_group enrichment
# ---------------------------------------------------------------------------


class TestPhase2IndustryGroupEnrichment:
    """Phase 2 sets TickerScore.industry_group from industry_group_map."""

    async def test_ticker_score_industry_group_set(self) -> None:
        """TickerScore.industry_group is set for tickers in industry_group_map."""
        # Utilities -> single group -> UTILITIES
        sp500 = [
            SP500Constituent(ticker="NEE", sector="Utilities"),
        ]
        tickers = ["NEE"]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
        )

        universe_result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)
        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        for ts in scoring_result.scores:
            assert ts.industry_group == GICSIndustryGroup.UTILITIES.value

    async def test_ticker_score_industry_group_from_sub_industry(self) -> None:
        """TickerScore.industry_group is set from sub_industry data."""
        sp500 = [
            SP500Constituent(
                ticker="AAPL",
                sector="Information Technology",
                sub_industry="Technology Hardware Storage & Peripherals",
            ),
        ]
        tickers = ["AAPL"]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
        )

        universe_result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)
        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        for ts in scoring_result.scores:
            assert ts.industry_group == GICSIndustryGroup.TECHNOLOGY_HARDWARE_EQUIPMENT.value

    async def test_ticker_score_industry_group_none_when_not_in_map(self) -> None:
        """TickerScore.industry_group remains None when not in industry_group_map."""
        # IT has multiple groups -> not inferred, no sub_industry
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
        ]
        tickers = ["AAPL"]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
        )

        universe_result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)
        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        for ts in scoring_result.scores:
            assert ts.industry_group is None


# ---------------------------------------------------------------------------
# Regression: sector filtering still works
# ---------------------------------------------------------------------------


class TestSectorFilterRegression:
    """Existing sector filtering continues to work with industry group changes."""

    async def test_sector_filter_still_reduces_universe(self) -> None:
        """Sector filter (without industry group filter) works unchanged."""
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
            batch_result=_make_batch_result(["AAPL"]),
            settings=settings,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert set(result.tickers) == {"AAPL"}

    async def test_sector_enrichment_still_works(self) -> None:
        """Phase 2 sector enrichment on TickerScore is not broken."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
        ]
        tickers = ["AAPL"]

        pipeline, _ = _make_pipeline(
            optionable_tickers=tickers,
            sp500_constituents=sp500,
        )

        universe_result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)
        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        for ts in scoring_result.scores:
            assert ts.sector is GICSSector.INFORMATION_TECHNOLOGY
