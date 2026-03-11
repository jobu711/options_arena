"""Tests for Phase 1 market cap pre-filter optimization.

Covers:
  - Market cap tiers filter tickers before OHLCV fetch.
  - Empty market_cap_tiers list skips filter.
  - Tickers without metadata are kept (not penalized).
  - Empty metadata cache skips filter with warning.
  - Multiple tiers are accepted.
  - Filter runs before OHLCV batch fetch.
  - Logging includes before/after counts.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from options_arena.models import (
    MarketCapTier,
    ScanPreset,
)
from options_arena.models.filters import UniverseFilters
from options_arena.models.market_data import OHLCV
from options_arena.models.metadata import TickerMetadata
from options_arena.scan.phase_universe import run_universe_phase
from options_arena.scan.progress import ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW_UTC = datetime.now(UTC)


def _make_metadata(ticker: str, tier: MarketCapTier | None = None) -> TickerMetadata:
    """Create a TickerMetadata with given market cap tier."""
    return TickerMetadata(
        ticker=ticker,
        market_cap_tier=tier,
        last_updated=_NOW_UTC,
    )


def _make_ohlcv_bars(ticker: str, n: int = 250) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars."""
    from datetime import date

    bars: list[OHLCV] = []
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        close = 100.0 + (i % 10) - 5
        bars.append(
            OHLCV(
                ticker=ticker,
                date=d,
                open=Decimal(str(round(close - 0.5, 2))),
                high=Decimal(str(round(close + 1.0, 2))),
                low=Decimal(str(round(close - 1.0, 2))),
                close=Decimal(str(round(close, 2))),
                adjusted_close=Decimal(str(round(close, 2))),
                volume=1_000_000,
            )
        )
    return bars


def _noop_progress(phase: ScanPhase, current: int, total: int) -> None:
    """No-op progress callback."""


def _make_mocks(
    optionable_tickers: list[str],
    metadata: list[TickerMetadata] | None = None,
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """Create mocked services for run_universe_phase."""
    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=optionable_tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=[])

    # Pre-build bars for all tickers; side_effect filters to requested tickers
    all_bars: dict[str, list[OHLCV]] = {t: _make_ohlcv_bars(t) for t in optionable_tickers}

    async def _dynamic_batch(tickers: list[str], **_: object) -> BatchOHLCVResult:
        return BatchOHLCVResult(
            results=[
                TickerOHLCVResult(ticker=t, data=all_bars.get(t, []))
                for t in tickers
            ]
        )

    mock_market_data = AsyncMock()
    mock_market_data.fetch_batch_ohlcv = AsyncMock(side_effect=_dynamic_batch)

    mock_repository = AsyncMock()
    mock_repository.get_all_ticker_metadata = AsyncMock(return_value=metadata or [])

    return mock_universe, mock_market_data, mock_repository


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMarketCapPreFilter:
    """Phase 1 market cap pre-filter tests."""

    async def test_filters_by_market_cap_tiers(self) -> None:
        """Verify tickers outside allowed tiers are excluded."""
        metadata = [
            _make_metadata("AAPL", MarketCapTier.MEGA),
            _make_metadata("MSFT", MarketCapTier.MEGA),
            _make_metadata("XYZ", MarketCapTier.MICRO),
        ]
        tickers = ["AAPL", "MSFT", "XYZ"]
        mock_universe, mock_market_data, mock_repo = _make_mocks(tickers, metadata)

        result = await run_universe_phase(
            _noop_progress,
            universe=mock_universe,
            market_data=mock_market_data,
            repository=mock_repo,
            universe_filters=UniverseFilters(
                preset=ScanPreset.FULL,
                market_cap_tiers=[MarketCapTier.MEGA],
            ),
        )

        # XYZ (micro) should be filtered, AAPL and MSFT (mega) kept
        assert "AAPL" in result.ohlcv_map
        assert "MSFT" in result.ohlcv_map
        assert "XYZ" not in result.ohlcv_map

    async def test_empty_tiers_no_filtering(self) -> None:
        """Verify empty market_cap_tiers list skips filter."""
        metadata = [
            _make_metadata("AAPL", MarketCapTier.MEGA),
            _make_metadata("XYZ", MarketCapTier.MICRO),
        ]
        tickers = ["AAPL", "XYZ"]
        mock_universe, mock_market_data, mock_repo = _make_mocks(tickers, metadata)

        result = await run_universe_phase(
            _noop_progress,
            universe=mock_universe,
            market_data=mock_market_data,
            repository=mock_repo,
            universe_filters=UniverseFilters(
                preset=ScanPreset.FULL,
                market_cap_tiers=[],
            ),
        )

        # No filtering — both tickers present
        assert "AAPL" in result.ohlcv_map
        assert "XYZ" in result.ohlcv_map

    async def test_missing_metadata_keeps_ticker(self) -> None:
        """Verify tickers without metadata are not penalized."""
        metadata = [
            _make_metadata("AAPL", MarketCapTier.MEGA),
            # MSFT has no metadata entry
        ]
        tickers = ["AAPL", "MSFT"]
        mock_universe, mock_market_data, mock_repo = _make_mocks(tickers, metadata)

        result = await run_universe_phase(
            _noop_progress,
            universe=mock_universe,
            market_data=mock_market_data,
            repository=mock_repo,
            universe_filters=UniverseFilters(
                preset=ScanPreset.FULL,
                market_cap_tiers=[MarketCapTier.MEGA],
            ),
        )

        # MSFT kept (no metadata = not penalized)
        assert "AAPL" in result.ohlcv_map
        assert "MSFT" in result.ohlcv_map

    async def test_empty_metadata_cache_skips_filter(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify graceful degradation when metadata cache is empty."""
        tickers = ["AAPL", "MSFT"]
        mock_universe, mock_market_data, mock_repo = _make_mocks(tickers, [])

        with caplog.at_level(logging.WARNING, logger="options_arena.scan.pipeline"):
            result = await run_universe_phase(
                _noop_progress,
                universe=mock_universe,
                market_data=mock_market_data,
                repository=mock_repo,
                universe_filters=UniverseFilters(
                    preset=ScanPreset.FULL,
                    market_cap_tiers=[MarketCapTier.MEGA],
                ),
            )

        # Both tickers kept (filter skipped)
        assert "AAPL" in result.ohlcv_map
        assert "MSFT" in result.ohlcv_map
        assert any("metadata cache is empty" in r.message for r in caplog.records)

    async def test_multiple_tiers(self) -> None:
        """Verify [mega, large] keeps both mega and large cap tickers."""
        metadata = [
            _make_metadata("AAPL", MarketCapTier.MEGA),
            _make_metadata("MSFT", MarketCapTier.LARGE),
            _make_metadata("XYZ", MarketCapTier.MICRO),
        ]
        tickers = ["AAPL", "MSFT", "XYZ"]
        mock_universe, mock_market_data, mock_repo = _make_mocks(tickers, metadata)

        result = await run_universe_phase(
            _noop_progress,
            universe=mock_universe,
            market_data=mock_market_data,
            repository=mock_repo,
            universe_filters=UniverseFilters(
                preset=ScanPreset.FULL,
                market_cap_tiers=[MarketCapTier.MEGA, MarketCapTier.LARGE],
            ),
        )

        assert "AAPL" in result.ohlcv_map
        assert "MSFT" in result.ohlcv_map
        assert "XYZ" not in result.ohlcv_map

    async def test_filter_before_ohlcv_fetch(self) -> None:
        """Verify market cap filter runs before OHLCV batch fetch."""
        metadata = [
            _make_metadata("AAPL", MarketCapTier.MEGA),
            _make_metadata("XYZ", MarketCapTier.MICRO),
        ]
        tickers = ["AAPL", "XYZ"]
        mock_universe, mock_market_data, mock_repo = _make_mocks(tickers, metadata)

        await run_universe_phase(
            _noop_progress,
            universe=mock_universe,
            market_data=mock_market_data,
            repository=mock_repo,
            universe_filters=UniverseFilters(
                preset=ScanPreset.FULL,
                market_cap_tiers=[MarketCapTier.MEGA],
            ),
        )

        # fetch_batch_ohlcv should be called with filtered tickers (only AAPL)
        call_args = mock_market_data.fetch_batch_ohlcv.call_args
        fetched_tickers = call_args[0][0]  # first positional arg
        assert "AAPL" in fetched_tickers
        assert "XYZ" not in fetched_tickers

    async def test_logging_counts(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify before/after ticker counts are logged."""
        metadata = [
            _make_metadata("AAPL", MarketCapTier.MEGA),
            _make_metadata("XYZ", MarketCapTier.MICRO),
        ]
        tickers = ["AAPL", "XYZ"]
        mock_universe, mock_market_data, mock_repo = _make_mocks(tickers, metadata)

        with caplog.at_level(logging.INFO, logger="options_arena.scan.pipeline"):
            await run_universe_phase(
                _noop_progress,
                universe=mock_universe,
                market_data=mock_market_data,
                repository=mock_repo,
                universe_filters=UniverseFilters(
                    preset=ScanPreset.FULL,
                    market_cap_tiers=[MarketCapTier.MEGA],
                ),
            )

        assert any("Market cap filter" in r.message for r in caplog.records)
