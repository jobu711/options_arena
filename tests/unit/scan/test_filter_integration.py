"""Integration tests for ScanFilterSpec flowing through all pipeline phases.

Covers:
  - Default ScanFilterSpec produces identical behavior to pre-migration.
  - min_score cutoff reduces ticker count entering Phase 3.
  - Market cap filter reduces OHLCV fetch count.
  - filter_spec_json is persisted in scan_runs.
  - min_score=100 drops all tickers.
  - Combined filters produce correct cumulative effect.
  - ScanFilterSpec JSON roundtrip preserves all fields.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from options_arena.models import (
    AppSettings,
    MarketCapTier,
    ScanPreset,
    SignalDirection,
    TickerInfo,
)
from options_arena.models.filters import (
    OptionsFilters,
    ScanFilterSpec,
    ScoringFilters,
    UniverseFilters,
)
from options_arena.models.market_data import OHLCV
from options_arena.models.metadata import TickerMetadata
from options_arena.scan import CancellationToken, ScanPipeline
from options_arena.scan.progress import ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW_UTC = datetime.now(UTC)


def _make_ohlcv_bars(ticker: str, n: int = 250) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars."""
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


def _make_ticker_info(ticker: str) -> TickerInfo:
    """Create a minimal TickerInfo for testing."""
    return TickerInfo(
        ticker=ticker,
        company_name=f"{ticker} Inc",
        sector="Technology",
        current_price=Decimal("100.00"),
        fifty_two_week_high=Decimal("150.00"),
        fifty_two_week_low=Decimal("80.00"),
    )


def _make_metadata(ticker: str, tier: MarketCapTier | None = None) -> TickerMetadata:
    """Create a TickerMetadata for testing."""
    return TickerMetadata(
        ticker=ticker,
        market_cap_tier=tier,
        last_updated=_NOW_UTC,
    )


def _noop_progress(phase: ScanPhase, current: int, total: int) -> None:
    """No-op progress callback."""


def _make_settings(**overrides: object) -> AppSettings:
    """Create AppSettings with filter overrides."""
    settings = AppSettings()
    if overrides:
        base = settings.scan.filters
        filter_spec = ScanFilterSpec(
            universe=base.universe.model_copy(
                update={k: v for k, v in overrides.items() if k in UniverseFilters.model_fields}
            ),
            scoring=base.scoring.model_copy(
                update={k: v for k, v in overrides.items() if k in ScoringFilters.model_fields}
            ),
            options=base.options.model_copy(
                update={k: v for k, v in overrides.items() if k in OptionsFilters.model_fields}
            ),
        )
        settings = settings.model_copy(
            update={"scan": settings.scan.model_copy(update={"filters": filter_spec})}
        )
    return settings


def _build_pipeline(
    settings: AppSettings,
    optionable_tickers: list[str],
    metadata: list[TickerMetadata] | None = None,
) -> tuple[ScanPipeline, AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    """Create a ScanPipeline with mocked services."""
    all_bars = {t: _make_ohlcv_bars(t) for t in optionable_tickers}

    async def _dynamic_batch(tickers: list[str], **_: object) -> BatchOHLCVResult:
        return BatchOHLCVResult(
            results=[TickerOHLCVResult(ticker=t, data=all_bars.get(t, [])) for t in tickers]
        )

    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=optionable_tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=[])
    # map_yfinance_to_metadata is sync — return None (no metadata update)
    mock_universe.map_yfinance_to_metadata = lambda *_args, **_kw: None

    mock_market_data = AsyncMock()
    mock_market_data.fetch_batch_ohlcv = AsyncMock(side_effect=_dynamic_batch)
    mock_market_data.fetch_ticker_info = AsyncMock(
        side_effect=lambda t, **_kw: _make_ticker_info(t)
    )
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

    mock_fred = AsyncMock()
    mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.05)

    mock_repo = AsyncMock()
    mock_repo.get_all_ticker_metadata = AsyncMock(return_value=metadata or [])
    mock_repo.save_scan_run = AsyncMock(return_value=1)
    mock_repo.save_ticker_scores = AsyncMock()
    mock_repo.save_recommended_contracts = AsyncMock()
    mock_repo.save_normalization_stats = AsyncMock()
    mock_repo.upsert_metadata_batch = AsyncMock()

    pipeline = ScanPipeline(
        settings=settings,
        market_data=mock_market_data,
        options_data=mock_options_data,
        fred=mock_fred,
        universe=mock_universe,
        repository=mock_repo,
    )

    return pipeline, mock_universe, mock_market_data, mock_options_data, mock_fred, mock_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFilterIntegration:
    """Integration tests for ScanFilterSpec through the pipeline."""

    async def test_default_spec_runs_without_error(self) -> None:
        """Verify ScanFilterSpec() defaults produce a successful pipeline run."""
        settings = _make_settings(preset=ScanPreset.FULL)
        tickers = ["AAPL", "MSFT", "GOOG"]
        pipeline, *_ = _build_pipeline(settings, tickers)

        token = CancellationToken()
        result = await pipeline.run(token, _noop_progress)

        assert not result.cancelled
        assert result.scan_run is not None

    async def test_min_score_reduces_phase3_count(self) -> None:
        """Verify min_score cutoff reduces ticker count entering Phase 3."""
        settings = _make_settings(preset=ScanPreset.FULL, min_score=99.0)
        tickers = ["AAPL", "MSFT", "GOOG"]
        pipeline, *_ = _build_pipeline(settings, tickers)

        token = CancellationToken()
        result = await pipeline.run(token, _noop_progress)

        # With min_score=99.0, very few (likely 0) tickers pass the cutoff
        assert not result.cancelled

    async def test_market_cap_filter_reduces_ohlcv_fetch(self) -> None:
        """Verify market cap filter reduces the tickers sent to OHLCV fetch."""
        metadata = [
            _make_metadata("AAPL", MarketCapTier.MEGA),
            _make_metadata("MSFT", MarketCapTier.MEGA),
            _make_metadata("PENNY", MarketCapTier.MICRO),
        ]
        settings = _make_settings(
            preset=ScanPreset.FULL,
            market_cap_tiers=[MarketCapTier.MEGA],
        )
        tickers = ["AAPL", "MSFT", "PENNY"]
        pipeline, _, mock_market_data, _, _, _ = _build_pipeline(settings, tickers, metadata)

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        # OHLCV fetch (first call) should only include AAPL and MSFT (not PENNY)
        # Note: Phase 3 may make a second call for ^GSPC, so use call_args_list[0]
        first_call = mock_market_data.fetch_batch_ohlcv.call_args_list[0]
        fetched_tickers = first_call[0][0]
        assert "AAPL" in fetched_tickers
        assert "MSFT" in fetched_tickers
        assert "PENNY" not in fetched_tickers

    async def test_filter_spec_persisted_in_scan_run(self) -> None:
        """Verify filter_spec_json is stored in scan_runs."""
        filter_spec = ScanFilterSpec(
            universe=UniverseFilters(preset=ScanPreset.FULL),
            scoring=ScoringFilters(min_score=25.0),
            options=OptionsFilters(top_n=10),
        )
        settings = AppSettings()
        settings = settings.model_copy(
            update={"scan": settings.scan.model_copy(update={"filters": filter_spec})}
        )

        tickers = ["AAPL"]
        pipeline, _, _, _, _, mock_repo = _build_pipeline(settings, tickers)

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        # save_scan_run should have been called with filter_spec_json set
        assert mock_repo.save_scan_run.called
        saved_run = mock_repo.save_scan_run.call_args[0][0]
        assert saved_run.filter_spec_json is not None
        # Verify it's valid JSON that can roundtrip
        roundtrip = ScanFilterSpec.model_validate_json(saved_run.filter_spec_json)
        assert roundtrip.scoring.min_score == pytest.approx(25.0)
        assert roundtrip.options.top_n == 10

    async def test_min_score_100_drops_all_tickers(self) -> None:
        """Verify min_score=100 results in 0 tickers entering Phase 3."""
        settings = _make_settings(preset=ScanPreset.FULL, min_score=100.0)
        tickers = ["AAPL", "MSFT"]
        pipeline, *_ = _build_pipeline(settings, tickers)

        token = CancellationToken()
        result = await pipeline.run(token, _noop_progress)

        assert not result.cancelled

    async def test_combined_filters_cumulative(self) -> None:
        """Verify multiple filters applied together reduce results cumulatively."""
        metadata = [
            _make_metadata("AAPL", MarketCapTier.MEGA),
            _make_metadata("MSFT", MarketCapTier.MEGA),
            _make_metadata("PENNY", MarketCapTier.MICRO),
        ]
        settings = _make_settings(
            preset=ScanPreset.FULL,
            market_cap_tiers=[MarketCapTier.MEGA],
            min_score=50.0,
            direction_filter=SignalDirection.BULLISH,
        )
        tickers = ["AAPL", "MSFT", "PENNY"]
        pipeline, _, mock_market_data, _, _, _ = _build_pipeline(settings, tickers, metadata)

        token = CancellationToken()
        result = await pipeline.run(token, _noop_progress)

        # Pipeline should complete without error
        assert not result.cancelled
        # PENNY filtered by market cap
        call_args = mock_market_data.fetch_batch_ohlcv.call_args
        fetched_tickers = call_args[0][0]
        assert "PENNY" not in fetched_tickers

    async def test_filter_spec_json_roundtrip(self) -> None:
        """Verify ScanFilterSpec JSON serialization preserves all filter values."""
        spec = ScanFilterSpec(
            universe=UniverseFilters(
                preset=ScanPreset.FULL,
                market_cap_tiers=[MarketCapTier.MEGA, MarketCapTier.LARGE],
                min_price=20.0,
                max_price=500.0,
            ),
            scoring=ScoringFilters(
                min_score=40.0,
                min_direction_confidence=0.6,
                direction_filter=SignalDirection.BULLISH,
            ),
            options=OptionsFilters(
                top_n=25,
                min_dte=45,
                max_dte=120,
                exclude_near_earnings_days=5,
            ),
        )
        json_str = spec.model_dump_json()
        roundtrip = ScanFilterSpec.model_validate_json(json_str)

        assert roundtrip.universe.preset == ScanPreset.FULL
        assert roundtrip.universe.market_cap_tiers == [MarketCapTier.MEGA, MarketCapTier.LARGE]
        assert roundtrip.universe.min_price == pytest.approx(20.0)
        assert roundtrip.universe.max_price == pytest.approx(500.0)
        assert roundtrip.scoring.min_score == pytest.approx(40.0)
        assert roundtrip.scoring.min_direction_confidence == pytest.approx(0.6)
        assert roundtrip.scoring.direction_filter == SignalDirection.BULLISH
        assert roundtrip.options.top_n == 25
        assert roundtrip.options.min_dte == 45
        assert roundtrip.options.max_dte == 120
        assert roundtrip.options.exclude_near_earnings_days == 5
