"""Tests for metadata index integration in the scan pipeline.

Phase 1 integration:
  - Cached metadata extends sector_map and industry_group_map beyond S&P 500.
  - S&P 500 CSV entries always take priority (never overwritten).
  - Empty metadata table is handled gracefully.
  - Metadata load failure is caught and logged, never crashes the scan.
  - Enriched map sizes are logged.

Phase 3 integration:
  - metadata write-back via upsert_ticker_metadata after fetch_ticker_info.
  - ticker_score.sector/industry_group enriched from metadata when not set.
  - Existing sector/industry_group not overwritten by Phase 3 metadata.
  - Upsert failure caught and logged, never crashes the scan.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from options_arena.models import (
    AppSettings,
    GICSIndustryGroup,
    GICSSector,
    IndicatorSignals,
    ScanPreset,
    SignalDirection,
    TickerScore,
)
from options_arena.models.enums import DividendSource, ExerciseStyle, MarketCapTier, OptionType
from options_arena.models.market_data import OHLCV, TickerInfo
from options_arena.models.metadata import TickerMetadata
from options_arena.models.options import OptionContract
from options_arena.scan.models import ScoringResult, UniverseResult
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult
from options_arena.services.options_data import ExpirationChain
from options_arena.services.universe import SP500Constituent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_bars(
    ticker: str,
    n: int = 250,
    *,
    close_price: float = 100.0,
    volume: int = 1_000_000,
) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars for a ticker."""
    bars: list[OHLCV] = []
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        bars.append(
            OHLCV(
                ticker=ticker,
                date=d,
                open=Decimal(str(close_price)),
                high=Decimal(str(close_price + 1.0)),
                low=Decimal(str(close_price - 1.0)),
                close=Decimal(str(close_price)),
                adjusted_close=Decimal(str(close_price)),
                volume=volume,
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


def _make_ticker_metadata(
    ticker: str,
    *,
    sector: GICSSector | None = None,
    industry_group: GICSIndustryGroup | None = None,
    market_cap_tier: MarketCapTier | None = None,
    company_name: str | None = None,
) -> TickerMetadata:
    """Create a TickerMetadata with sensible defaults."""
    return TickerMetadata(
        ticker=ticker,
        sector=sector,
        industry_group=industry_group,
        market_cap_tier=market_cap_tier,
        company_name=company_name or f"{ticker} Inc.",
        raw_sector="Technology" if sector else "Unknown",
        raw_industry="Software" if industry_group else "Unknown",
        last_updated=datetime.now(UTC),
    )


def _make_ticker_info(ticker: str, current_price: float = 100.0) -> TickerInfo:
    """Create a TickerInfo with sensible defaults."""
    return TickerInfo(
        ticker=ticker,
        company_name=f"{ticker} Inc.",
        sector="Technology",
        industry="Software - Application",
        dividend_yield=0.01,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal(str(current_price)),
        fifty_two_week_high=Decimal(str(current_price * 1.3)),
        fifty_two_week_low=Decimal(str(current_price * 0.7)),
    )


def _make_ticker_score(
    ticker: str,
    score: float = 75.0,
    direction: SignalDirection = SignalDirection.BULLISH,
    *,
    sector: GICSSector | None = None,
    industry_group: GICSIndustryGroup | None = None,
) -> TickerScore:
    """Create a TickerScore with sensible defaults."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=direction,
        signals=IndicatorSignals(rsi=65.0, adx=25.0),
        sector=sector,
        industry_group=industry_group,
    )


def _make_option_contract(
    ticker: str,
    expiration_offset_days: int = 45,
) -> OptionContract:
    """Create a minimal OptionContract for testing."""
    return OptionContract(
        ticker=ticker,
        option_type=OptionType.CALL,
        strike=Decimal("100"),
        expiration=date.today() + timedelta(days=expiration_offset_days),
        bid=Decimal("3.00"),
        ask=Decimal("3.50"),
        last=Decimal("3.25"),
        volume=500,
        open_interest=2000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.25,
        greeks=None,
    )


def _make_expiration_chain(
    ticker: str,
    n_contracts: int = 3,
) -> ExpirationChain:
    """Create an ExpirationChain with n_contracts."""
    expiration = date.today() + timedelta(days=45)
    contracts = [_make_option_contract(ticker) for _ in range(n_contracts)]
    return ExpirationChain(expiration=expiration, contracts=contracts)


def _make_universe_result(
    tickers: list[str],
    *,
    sector_map: dict[str, GICSSector] | None = None,
    industry_group_map: dict[str, GICSIndustryGroup] | None = None,
) -> UniverseResult:
    """Build a UniverseResult with synthetic OHLCV data."""
    ohlcv_map = {t: _make_ohlcv_bars(t) for t in tickers}
    return UniverseResult(
        tickers=tickers,
        ohlcv_map=ohlcv_map,
        sp500_sectors={},
        sector_map=sector_map or {},
        industry_group_map=industry_group_map or {},
        failed_count=0,
        filtered_count=0,
    )


def _make_scoring_result(
    tickers: list[str],
    *,
    scores: list[float] | None = None,
    sectors: dict[str, GICSSector] | None = None,
    industry_groups: dict[str, GICSIndustryGroup] | None = None,
) -> ScoringResult:
    """Build a ScoringResult with given tickers."""
    _scores = scores or [90.0 - i * 5.0 for i in range(len(tickers))]
    _sectors = sectors or {}
    _igs = industry_groups or {}
    ticker_scores = [
        _make_ticker_score(
            t,
            score=s,
            sector=_sectors.get(t),
            industry_group=_igs.get(t),
        )
        for t, s in zip(tickers, _scores, strict=True)
    ]
    raw_signals = {t: IndicatorSignals(rsi=65.0, adx=25.0) for t in tickers}
    return ScoringResult(scores=ticker_scores, raw_signals=raw_signals)


def _make_pipeline_phase1(
    *,
    optionable_tickers: list[str] | None = None,
    sp500_constituents: list[SP500Constituent] | None = None,
    batch_result: BatchOHLCVResult | None = None,
    settings: AppSettings | None = None,
    metadata_list: list[TickerMetadata] | None = None,
    metadata_raises: bool = False,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services for Phase 1 metadata tests."""
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
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)

    mock_options_data = AsyncMock()
    mock_fred = AsyncMock()
    mock_repository = AsyncMock()

    # Configure metadata loading
    if metadata_raises:
        mock_repository.get_all_ticker_metadata = AsyncMock(
            side_effect=RuntimeError("DB connection lost")
        )
    else:
        mock_repository.get_all_ticker_metadata = AsyncMock(return_value=metadata_list or [])

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


def _make_pipeline_phase3(
    *,
    settings: AppSettings | None = None,
    ticker_infos: dict[str, TickerInfo] | None = None,
    expiration_chains: dict[str, list[ExpirationChain]] | None = None,
    upsert_raises: bool = False,
    metadata_from_map: dict[str, TickerMetadata] | None = None,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services for Phase 3 metadata tests."""
    _settings = settings or AppSettings()

    mock_universe = AsyncMock()
    mock_market_data = AsyncMock()
    mock_options_data = AsyncMock()
    mock_fred = AsyncMock()
    mock_repository = AsyncMock()

    mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)

    if ticker_infos is not None:

        async def _fetch_info(ticker: str) -> TickerInfo:
            return ticker_infos[ticker]

        mock_market_data.fetch_ticker_info = AsyncMock(side_effect=_fetch_info)
    else:
        mock_market_data.fetch_ticker_info = AsyncMock(side_effect=lambda t: _make_ticker_info(t))

    if expiration_chains is not None:

        async def _fetch_chains(ticker: str) -> list[ExpirationChain]:
            return expiration_chains.get(ticker, [])

        mock_options_data.fetch_chain_all_expirations = AsyncMock(side_effect=_fetch_chains)
    else:
        mock_options_data.fetch_chain_all_expirations = AsyncMock(
            side_effect=lambda t: [_make_expiration_chain(t)]
        )

    if upsert_raises:
        mock_repository.upsert_ticker_metadata = AsyncMock(
            side_effect=RuntimeError("DB write failed")
        )
    else:
        mock_repository.upsert_ticker_metadata = AsyncMock(return_value=None)

    # Also mock get_all_ticker_metadata for Phase 1 if needed
    mock_repository.get_all_ticker_metadata = AsyncMock(return_value=[])

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
# Phase 1 — Metadata Enrichment Tests
# ---------------------------------------------------------------------------


class TestPhase1MetadataEnrichment:
    """Phase 1 metadata enrichment extends sector and industry group maps."""

    @pytest.mark.asyncio
    async def test_metadata_extends_sector_map(self) -> None:
        """Verify cached metadata adds non-S&P500 tickers to sector_map."""
        # TSLA is in optionable universe but NOT in S&P 500 constituents
        metadata = [
            _make_ticker_metadata(
                "TSLA",
                sector=GICSSector.CONSUMER_DISCRETIONARY,
                industry_group=GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
            ),
        ]
        pipeline, mocks = _make_pipeline_phase1(
            optionable_tickers=["AAPL", "TSLA"],
            sp500_constituents=[
                SP500Constituent(ticker="AAPL", sector="Information Technology", sub_industry=""),
            ],
            metadata_list=metadata,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert "TSLA" in result.sector_map
        assert result.sector_map["TSLA"] == GICSSector.CONSUMER_DISCRETIONARY

    @pytest.mark.asyncio
    async def test_sp500_csv_takes_priority(self) -> None:
        """Verify S&P500 CSV sector is NOT overwritten by metadata."""
        # AAPL in both S&P500 (Technology) and metadata (Consumer Discretionary)
        metadata = [
            _make_ticker_metadata(
                "AAPL",
                sector=GICSSector.CONSUMER_DISCRETIONARY,
            ),
        ]
        pipeline, mocks = _make_pipeline_phase1(
            optionable_tickers=["AAPL"],
            sp500_constituents=[
                SP500Constituent(ticker="AAPL", sector="Information Technology", sub_industry=""),
            ],
            metadata_list=metadata,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # S&P 500 sector should be preserved, NOT overwritten by metadata
        assert result.sector_map["AAPL"] == GICSSector.INFORMATION_TECHNOLOGY

    @pytest.mark.asyncio
    async def test_metadata_extends_industry_group_map(self) -> None:
        """Verify cached metadata adds non-S&P500 tickers to industry_group_map."""
        metadata = [
            _make_ticker_metadata(
                "TSLA",
                sector=GICSSector.CONSUMER_DISCRETIONARY,
                industry_group=GICSIndustryGroup.AUTOMOBILES_COMPONENTS,
            ),
        ]
        pipeline, mocks = _make_pipeline_phase1(
            optionable_tickers=["AAPL", "TSLA"],
            sp500_constituents=[],
            metadata_list=metadata,
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert "TSLA" in result.industry_group_map
        assert result.industry_group_map["TSLA"] == GICSIndustryGroup.AUTOMOBILES_COMPONENTS

    @pytest.mark.asyncio
    async def test_empty_metadata_table_no_error(self) -> None:
        """Verify Phase 1 handles empty ticker_metadata gracefully."""
        pipeline, mocks = _make_pipeline_phase1(
            optionable_tickers=["AAPL"],
            sp500_constituents=[],
            metadata_list=[],
        )

        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # Should complete without error — sector/industry maps stay empty
        assert result.sector_map == {}
        assert result.industry_group_map == {}

    @pytest.mark.asyncio
    async def test_metadata_load_failure_continues(self) -> None:
        """Verify Phase 1 continues if metadata load raises exception."""
        pipeline, mocks = _make_pipeline_phase1(
            optionable_tickers=["AAPL"],
            sp500_constituents=[
                SP500Constituent(ticker="AAPL", sector="Information Technology", sub_industry=""),
            ],
            metadata_raises=True,
        )

        # Should NOT raise — metadata failure is caught and logged
        result = await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        # S&P 500 data should still be intact
        assert "AAPL" in result.sector_map
        assert result.sector_map["AAPL"] == GICSSector.INFORMATION_TECHNOLOGY

    @pytest.mark.asyncio
    async def test_logs_enriched_coverage(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify metadata enrichment coverage is logged."""
        metadata = [
            _make_ticker_metadata(
                "TSLA",
                sector=GICSSector.CONSUMER_DISCRETIONARY,
            ),
        ]
        pipeline, mocks = _make_pipeline_phase1(
            optionable_tickers=["AAPL", "TSLA"],
            sp500_constituents=[
                SP500Constituent(ticker="AAPL", sector="Information Technology", sub_industry=""),
            ],
            metadata_list=metadata,
        )

        with caplog.at_level(logging.INFO, logger="options_arena.scan.pipeline"):
            await pipeline._phase_universe(ScanPreset.FULL, _noop_progress)

        assert any("Metadata enrichment" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Phase 3 — Metadata Write-Back Tests
# ---------------------------------------------------------------------------


class TestPhase3WriteBack:
    """Phase 3 metadata write-back via map_yfinance_to_metadata."""

    @pytest.mark.asyncio
    @patch("options_arena.scan.pipeline.recommend_contracts", return_value=[])
    @patch("options_arena.scan.pipeline.map_yfinance_to_metadata")
    async def test_upserts_metadata_after_fetch(
        self,
        mock_map_fn: AsyncMock,
        mock_recommend: AsyncMock,
    ) -> None:
        """Verify Phase 3 calls upsert_ticker_metadata after fetch_ticker_info."""
        meta = _make_ticker_metadata("AAPL", sector=GICSSector.INFORMATION_TECHNOLOGY)
        mock_map_fn.return_value = meta

        pipeline, mocks = _make_pipeline_phase3()
        ts = _make_ticker_score("AAPL")
        ohlcv_map = {"AAPL": _make_ohlcv_bars("AAPL")}

        await pipeline._process_ticker_options(ts, 0.045, ohlcv_map, None)

        mocks["repository"].upsert_ticker_metadata.assert_awaited_once_with(meta)

    @pytest.mark.asyncio
    @patch("options_arena.scan.pipeline.recommend_contracts", return_value=[])
    @patch("options_arena.scan.pipeline.map_yfinance_to_metadata")
    async def test_enriches_ticker_score_sector(
        self,
        mock_map_fn: AsyncMock,
        mock_recommend: AsyncMock,
    ) -> None:
        """Verify ticker_score.sector set from metadata when Phase 1 left it None."""
        meta = _make_ticker_metadata("AAPL", sector=GICSSector.INFORMATION_TECHNOLOGY)
        mock_map_fn.return_value = meta

        pipeline, mocks = _make_pipeline_phase3()
        ts = _make_ticker_score("AAPL", sector=None)
        ohlcv_map = {"AAPL": _make_ohlcv_bars("AAPL")}

        await pipeline._process_ticker_options(ts, 0.045, ohlcv_map, None)

        assert ts.sector == GICSSector.INFORMATION_TECHNOLOGY

    @pytest.mark.asyncio
    @patch("options_arena.scan.pipeline.recommend_contracts", return_value=[])
    @patch("options_arena.scan.pipeline.map_yfinance_to_metadata")
    async def test_enriches_ticker_score_industry_group(
        self,
        mock_map_fn: AsyncMock,
        mock_recommend: AsyncMock,
    ) -> None:
        """Verify ticker_score.industry_group set from metadata when Phase 1 left it None."""
        meta = _make_ticker_metadata(
            "AAPL",
            sector=GICSSector.INFORMATION_TECHNOLOGY,
            industry_group=GICSIndustryGroup.SOFTWARE_SERVICES,
        )
        mock_map_fn.return_value = meta

        pipeline, mocks = _make_pipeline_phase3()
        ts = _make_ticker_score("AAPL", industry_group=None)
        ohlcv_map = {"AAPL": _make_ohlcv_bars("AAPL")}

        await pipeline._process_ticker_options(ts, 0.045, ohlcv_map, None)

        assert ts.industry_group == GICSIndustryGroup.SOFTWARE_SERVICES

    @pytest.mark.asyncio
    @patch("options_arena.scan.pipeline.recommend_contracts", return_value=[])
    @patch("options_arena.scan.pipeline.map_yfinance_to_metadata")
    async def test_does_not_overwrite_existing_sector(
        self,
        mock_map_fn: AsyncMock,
        mock_recommend: AsyncMock,
    ) -> None:
        """Verify Phase 3 does not overwrite sector already set by Phase 1."""
        meta = _make_ticker_metadata("AAPL", sector=GICSSector.CONSUMER_DISCRETIONARY)
        mock_map_fn.return_value = meta

        pipeline, mocks = _make_pipeline_phase3()
        # Sector already set from Phase 1 (S&P 500 CSV)
        ts = _make_ticker_score("AAPL", sector=GICSSector.INFORMATION_TECHNOLOGY)
        ohlcv_map = {"AAPL": _make_ohlcv_bars("AAPL")}

        await pipeline._process_ticker_options(ts, 0.045, ohlcv_map, None)

        # Phase 1 sector should NOT be overwritten
        assert ts.sector == GICSSector.INFORMATION_TECHNOLOGY

    @pytest.mark.asyncio
    @patch("options_arena.scan.pipeline.recommend_contracts", return_value=[])
    @patch("options_arena.scan.pipeline.map_yfinance_to_metadata")
    async def test_upsert_failure_does_not_crash(
        self,
        mock_map_fn: AsyncMock,
        mock_recommend: AsyncMock,
    ) -> None:
        """Verify metadata upsert failure is caught and logged, not raised."""
        meta = _make_ticker_metadata("AAPL", sector=GICSSector.INFORMATION_TECHNOLOGY)
        mock_map_fn.return_value = meta

        pipeline, mocks = _make_pipeline_phase3(upsert_raises=True)
        ts = _make_ticker_score("AAPL")
        ohlcv_map = {"AAPL": _make_ohlcv_bars("AAPL")}

        # Should NOT raise — upsert failure is caught and logged
        result = await pipeline._process_ticker_options(ts, 0.045, ohlcv_map, None)

        # Pipeline continues — returns a valid tuple
        assert result[0] == "AAPL"
