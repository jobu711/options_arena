"""Integration tests for sector filtering, ETF preset, and enriched scan results.

Cross-module integration tests verifying full pipeline data flow for:
  - Sector filtering (single, multiple, OR logic) through all 4 phases.
  - Sector filter composing with SP500 preset through full pipeline.
  - ETFS preset returns only ETF tickers through full pipeline.
  - TickerScore.sector and company_name enrichment after full pipeline run.
  - Pipeline -> persist -> repository retrieve round-trip with sector/company_name.
  - Empty sector filter (no filtering) through full pipeline.

All external services are mocked. No real API calls.

Issue: #164
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from options_arena.models import (
    AppSettings,
    GICSSector,
    IndicatorSignals,
    OptionContract,
    ScanPreset,
    SignalDirection,
    TickerScore,
)
from options_arena.models.enums import DividendSource, ExerciseStyle, OptionType
from options_arena.models.market_data import OHLCV, TickerInfo
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import CancellationToken, ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult
from options_arena.services.options_data import ExpirationChain
from options_arena.services.universe import SP500Constituent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _noop_progress(phase: ScanPhase, current: int, total: int) -> None:
    """No-op progress callback for tests that don't inspect progress."""


def _make_ohlcv_bars(
    ticker: str,
    n: int = 300,
    *,
    close_price: float = 150.0,
    volume: int = 1_000_000,
) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars for a ticker.

    Uses 300 bars by default to exceed warmup of all indicators.
    Uses close=150, volume=1M by default for avg dollar volume of $150M
    (passes the default $10M liquidity pre-filter).
    """
    bars: list[OHLCV] = []
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        offset = (i % 10) - 5
        close = close_price + offset
        bars.append(
            OHLCV(
                ticker=ticker,
                date=d,
                open=Decimal(str(round(close - 0.5, 2))),
                high=Decimal(str(round(close + 1.0, 2))),
                low=Decimal(str(round(close - 1.0, 2))),
                close=Decimal(str(round(close, 2))),
                adjusted_close=Decimal(str(round(close, 2))),
                volume=volume,
            )
        )
    return bars


def _make_batch_result(
    tickers: list[str],
    bars: int = 300,
    *,
    close_price: float = 150.0,
    volume: int = 1_000_000,
    failed_tickers: set[str] | None = None,
) -> BatchOHLCVResult:
    """Build a BatchOHLCVResult with synthetic data."""
    failed = failed_tickers or set()
    results: list[TickerOHLCVResult] = []
    for ticker in tickers:
        if ticker in failed:
            results.append(TickerOHLCVResult(ticker=ticker, error="fetch failed"))
        else:
            results.append(
                TickerOHLCVResult(
                    ticker=ticker,
                    data=_make_ohlcv_bars(ticker, bars, close_price=close_price, volume=volume),
                )
            )
    return BatchOHLCVResult(results=results)


def _make_ticker_info(ticker: str, current_price: float = 150.0) -> TickerInfo:
    """Create a TickerInfo with sensible defaults."""
    return TickerInfo(
        ticker=ticker,
        company_name=f"{ticker} Inc.",
        sector="Technology",
        dividend_yield=0.01,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal(str(current_price)),
        fifty_two_week_high=Decimal(str(current_price * 1.3)),
        fifty_two_week_low=Decimal(str(current_price * 0.7)),
    )


def _make_option_contract(
    ticker: str,
    expiration_offset_days: int = 45,
) -> OptionContract:
    """Create a minimal OptionContract for testing."""
    return OptionContract(
        ticker=ticker,
        option_type=OptionType.CALL,
        strike=Decimal("150"),
        expiration=date.today() + timedelta(days=expiration_offset_days),
        bid=Decimal("5.00"),
        ask=Decimal("5.50"),
        last=Decimal("5.25"),
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


# ---------------------------------------------------------------------------
# Pipeline factory
# ---------------------------------------------------------------------------


def _make_full_pipeline(
    *,
    tickers: list[str] | None = None,
    sp500_constituents: list[SP500Constituent] | None = None,
    etf_tickers: list[str] | None = None,
    batch_result: BatchOHLCVResult | None = None,
    settings: AppSettings | None = None,
    fred_rate: float = 0.045,
    save_scan_run_return: int = 42,
    ticker_info_factory: object | None = None,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a fully-mocked ScanPipeline for integration tests.

    Mocks all 5 injected services with sensible defaults that pass all filters.
    """
    _tickers = tickers if tickers is not None else ["AAPL", "MSFT", "GOOG"]

    if settings is not None:
        _settings = settings
    else:
        _settings = AppSettings()
        # Relax filters so tickers pass by default
        _settings.scan.min_dollar_volume = 1.0
        _settings.scan.min_price = 1.0

    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=_tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(
        return_value=sp500_constituents
        or [SP500Constituent(ticker=t, sector="Technology") for t in _tickers]
    )
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=etf_tickers or [])

    mock_market_data = AsyncMock()
    mock_market_data.fetch_batch_ohlcv = AsyncMock(
        return_value=batch_result or _make_batch_result(_tickers)
    )
    if ticker_info_factory is not None:
        mock_market_data.fetch_ticker_info = AsyncMock(side_effect=ticker_info_factory)
    else:
        mock_market_data.fetch_ticker_info = AsyncMock(side_effect=lambda t: _make_ticker_info(t))
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)

    mock_options_data = AsyncMock()
    mock_options_data.fetch_chain_all_expirations = AsyncMock(
        side_effect=lambda t: [_make_expiration_chain(t)]
    )

    mock_fred = AsyncMock()
    mock_fred.fetch_risk_free_rate = AsyncMock(return_value=fred_rate)

    mock_repository = AsyncMock()
    mock_repository.save_scan_run = AsyncMock(return_value=save_scan_run_return)
    mock_repository.save_ticker_scores = AsyncMock(return_value=None)

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


# ---------------------------------------------------------------------------
# Test 1: Full pipeline with single sector filter
# ---------------------------------------------------------------------------


class TestFullPipelineSectorFilter:
    """Full pipeline end-to-end with sector filtering enabled."""

    async def test_single_sector_filter_only_matching_tickers_in_results(self) -> None:
        """Scan with sectors=[IT] -- only IT tickers appear in final results."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="MSFT", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
            SP500Constituent(ticker="XOM", sector="Energy"),
        ]
        all_tickers = ["AAPL", "MSFT", "JPM", "XOM"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY]
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        # Only provide OHLCV for filtered tickers since pipeline will only
        # request data for tickers that survive the sector filter.
        pipeline, _ = _make_full_pipeline(
            tickers=all_tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["AAPL", "MSFT"]),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("X")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.phases_completed == 4
        assert result.cancelled is False
        result_tickers = {ts.ticker for ts in result.scores}
        assert result_tickers == {"AAPL", "MSFT"}
        # No financial or energy tickers should be in results
        assert "JPM" not in result_tickers
        assert "XOM" not in result_tickers

    async def test_multiple_sectors_or_logic(self) -> None:
        """Scan with sectors=[IT, Energy] -- OR logic includes both."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
            SP500Constituent(ticker="XOM", sector="Energy"),
        ]
        all_tickers = ["AAPL", "JPM", "XOM"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY, GICSSector.ENERGY]
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=all_tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["AAPL", "XOM"]),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("X")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        result_tickers = {ts.ticker for ts in result.scores}
        assert "AAPL" in result_tickers
        assert "XOM" in result_tickers
        assert "JPM" not in result_tickers

    async def test_empty_sectors_no_filtering(self) -> None:
        """Scan with sectors=[] -- all tickers pass through (no filtering)."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
        ]
        all_tickers = ["AAPL", "JPM"]

        settings = AppSettings()
        assert settings.scan.sectors == []
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=all_tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(all_tickers),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        result_tickers = {ts.ticker for ts in result.scores}
        assert result_tickers == {"AAPL", "JPM"}

    async def test_sector_filter_with_sp500_preset_composes(self) -> None:
        """SP500 preset + sector filter composes: both constraints apply."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
        ]
        # Add a non-SP500 ticker to optionable universe
        all_tickers = ["AAPL", "JPM", "XYZ"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY]
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=all_tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["AAPL"]),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.SP500, token, _noop_progress)

        # SP500 preset removes XYZ, sector filter removes JPM -> only AAPL
        result_tickers = {ts.ticker for ts in result.scores}
        assert result_tickers == {"AAPL"}


# ---------------------------------------------------------------------------
# Test 2: Full pipeline with ETFS preset
# ---------------------------------------------------------------------------


class TestFullPipelineETFSPreset:
    """Full pipeline end-to-end with ETFS preset."""

    async def test_etfs_preset_returns_only_etf_tickers(self) -> None:
        """ETFS preset filters to only ETF tickers from UniverseService."""
        all_tickers = ["AAPL", "MSFT", "SPY", "QQQ", "IWM"]
        etf_tickers = ["SPY", "QQQ", "IWM"]

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, mocks = _make_full_pipeline(
            tickers=all_tickers,
            etf_tickers=etf_tickers,
            batch_result=_make_batch_result(etf_tickers),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.ETFS, token, _noop_progress)

        assert result.phases_completed == 4
        assert result.cancelled is False
        result_tickers = {ts.ticker for ts in result.scores}
        # Only ETF tickers should be in results
        assert result_tickers == {"SPY", "QQQ", "IWM"}
        # AAPL and MSFT should not appear
        assert "AAPL" not in result_tickers
        assert "MSFT" not in result_tickers
        # fetch_etf_tickers should have been called
        mocks["universe"].fetch_etf_tickers.assert_awaited_once()

    async def test_etfs_preset_with_empty_etf_list(self) -> None:
        """ETFS preset with no ETFs produces empty results."""
        all_tickers = ["AAPL", "MSFT"]

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=all_tickers,
            etf_tickers=[],  # No ETFs detected
            batch_result=BatchOHLCVResult(results=[]),
            settings=settings,
        )
        token = CancellationToken()

        result = await pipeline.run(ScanPreset.ETFS, token, _noop_progress)

        assert result.phases_completed == 4
        assert result.scores == []
        assert result.recommendations == {}


# ---------------------------------------------------------------------------
# Test 3: Enrichment — sector and company_name populated
# ---------------------------------------------------------------------------


class TestEnrichmentSectorAndCompanyName:
    """Verify sector and company_name enrichment through full pipeline phases."""

    async def test_sector_populated_from_phase2(self) -> None:
        """TickerScore.sector is set from sector_map in Phase 2."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
        ]
        tickers = ["AAPL", "JPM"]

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(tickers),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("X")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        by_ticker = {ts.ticker: ts for ts in result.scores}
        assert by_ticker["AAPL"].sector is GICSSector.INFORMATION_TECHNOLOGY
        assert by_ticker["JPM"].sector is GICSSector.FINANCIALS

    async def test_company_name_populated_from_phase3(self) -> None:
        """TickerScore.company_name is set from TickerInfo in Phase 3."""
        tickers = ["AAPL", "MSFT"]

        # Custom ticker_info factory that returns specific company names
        def custom_ticker_info(t: str) -> TickerInfo:
            names = {"AAPL": "Apple Inc.", "MSFT": "Microsoft Corporation"}
            return TickerInfo(
                ticker=t,
                company_name=names.get(t, f"{t} Inc."),
                sector="Technology",
                dividend_yield=0.01,
                dividend_source=DividendSource.FORWARD,
                current_price=Decimal("150.0"),
                fifty_two_week_high=Decimal("195.0"),
                fifty_two_week_low=Decimal("105.0"),
            )

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=tickers,
            batch_result=_make_batch_result(tickers),
            settings=settings,
            ticker_info_factory=custom_ticker_info,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("X")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        by_ticker = {ts.ticker: ts for ts in result.scores}
        assert by_ticker["AAPL"].company_name == "Apple Inc."
        assert by_ticker["MSFT"].company_name == "Microsoft Corporation"

    async def test_sector_enriched_for_non_sp500_ticker_via_metadata(self) -> None:
        """Non-S&P 500 tickers get sector from Phase 3 metadata write-back.

        Since the metadata index integration, Phase 3 calls
        ``map_yfinance_to_metadata()`` and enriches ``ticker_score.sector``
        from the yfinance ``TickerInfo.sector`` when Phase 1 left it ``None``.
        """
        # Only AAPL is in SP500, XYZ is not
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
        ]
        tickers = ["AAPL", "XYZ"]

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(tickers),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("X")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        by_ticker = {ts.ticker: ts for ts in result.scores}
        assert by_ticker["AAPL"].sector is GICSSector.INFORMATION_TECHNOLOGY
        # XYZ gets sector from Phase 3 metadata write-back (TickerInfo.sector="Technology")
        assert by_ticker["XYZ"].sector is GICSSector.INFORMATION_TECHNOLOGY

    async def test_sector_and_company_name_both_enriched(self) -> None:
        """Both sector (Phase 2) and company_name (Phase 3) are enriched on same ticker."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
        ]

        def custom_ticker_info(t: str) -> TickerInfo:
            return TickerInfo(
                ticker=t,
                company_name="Apple Inc.",
                sector="Technology",
                dividend_yield=0.01,
                dividend_source=DividendSource.FORWARD,
                current_price=Decimal("150.0"),
                fifty_two_week_high=Decimal("195.0"),
                fifty_two_week_low=Decimal("105.0"),
            )

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=["AAPL"],
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["AAPL"]),
            settings=settings,
            ticker_info_factory=custom_ticker_info,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("AAPL")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert len(result.scores) == 1
        ts = result.scores[0]
        assert ts.ticker == "AAPL"
        assert ts.sector is GICSSector.INFORMATION_TECHNOLOGY
        assert ts.company_name == "Apple Inc."


# ---------------------------------------------------------------------------
# Test 4: Pipeline -> persist verifies sector/company_name saved
# ---------------------------------------------------------------------------


class TestPipelinePersistSectorData:
    """Verify that sector and company_name are passed to repository for persistence."""

    async def test_persisted_scores_include_sector(self) -> None:
        """save_ticker_scores receives TickerScore with sector set."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
        ]

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, mocks = _make_full_pipeline(
            tickers=["AAPL"],
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["AAPL"]),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("AAPL")],
        ):
            await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        # Verify save_ticker_scores was called
        mocks["repository"].save_ticker_scores.assert_awaited_once()
        saved_scores: list[TickerScore] = mocks["repository"].save_ticker_scores.call_args[0][1]
        assert len(saved_scores) >= 1
        aapl_score = next(s for s in saved_scores if s.ticker == "AAPL")
        assert aapl_score.sector is GICSSector.INFORMATION_TECHNOLOGY

    async def test_persisted_scores_include_company_name(self) -> None:
        """save_ticker_scores receives TickerScore with company_name set."""

        def custom_ticker_info(t: str) -> TickerInfo:
            return TickerInfo(
                ticker=t,
                company_name="Apple Inc.",
                sector="Technology",
                dividend_yield=0.01,
                dividend_source=DividendSource.FORWARD,
                current_price=Decimal("150.0"),
                fifty_two_week_high=Decimal("195.0"),
                fifty_two_week_low=Decimal("105.0"),
            )

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, mocks = _make_full_pipeline(
            tickers=["AAPL"],
            batch_result=_make_batch_result(["AAPL"]),
            settings=settings,
            ticker_info_factory=custom_ticker_info,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("AAPL")],
        ):
            await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        mocks["repository"].save_ticker_scores.assert_awaited_once()
        saved_scores: list[TickerScore] = mocks["repository"].save_ticker_scores.call_args[0][1]
        aapl_score = next(s for s in saved_scores if s.ticker == "AAPL")
        assert aapl_score.company_name == "Apple Inc."


# ---------------------------------------------------------------------------
# Test 5: Full pipeline with sector filter reduces scan_run metadata
# ---------------------------------------------------------------------------


class TestScanRunMetadataWithSectorFilter:
    """ScanRun metadata reflects sector-filtered universe counts."""

    async def test_tickers_scanned_reflects_filtered_universe(self) -> None:
        """ScanRun.tickers_scanned reflects filtered universe size, not total."""
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="MSFT", sector="Information Technology"),
            SP500Constituent(ticker="JPM", sector="Financials"),
            SP500Constituent(ticker="XOM", sector="Energy"),
        ]
        all_tickers = ["AAPL", "MSFT", "JPM", "XOM"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY]
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=all_tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(["AAPL", "MSFT"]),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        # Only 2 IT tickers should be scanned (not 4)
        assert result.scan_run.tickers_scanned == 2
        assert result.scan_run.tickers_scored > 0


# ---------------------------------------------------------------------------
# Test 6: Sector filter with all 11 GICS sectors
# ---------------------------------------------------------------------------


class TestAllGICSSectorsThroughPipeline:
    """All 11 GICS sectors can flow through the full pipeline."""

    async def test_all_11_sectors_enriched_correctly(self) -> None:
        """Each of the 11 GICS sectors maps correctly through the pipeline."""
        sector_pairs = [
            ("A", "Communication Services", GICSSector.COMMUNICATION_SERVICES),
            ("B", "Consumer Discretionary", GICSSector.CONSUMER_DISCRETIONARY),
            ("C", "Consumer Staples", GICSSector.CONSUMER_STAPLES),
            ("D", "Energy", GICSSector.ENERGY),
            ("E", "Financials", GICSSector.FINANCIALS),
            ("F", "Health Care", GICSSector.HEALTH_CARE),
            ("G", "Industrials", GICSSector.INDUSTRIALS),
            ("H", "Information Technology", GICSSector.INFORMATION_TECHNOLOGY),
            ("I", "Materials", GICSSector.MATERIALS),
            ("J", "Real Estate", GICSSector.REAL_ESTATE),
            ("K", "Utilities", GICSSector.UTILITIES),
        ]
        tickers = [t for t, _, _ in sector_pairs]
        sp500 = [SP500Constituent(ticker=t, sector=s) for t, s, _ in sector_pairs]

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=tickers,
            sp500_constituents=sp500,
            batch_result=_make_batch_result(tickers),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        by_ticker = {ts.ticker: ts for ts in result.scores}
        for ticker, _, expected_sector in sector_pairs:
            assert by_ticker[ticker].sector is expected_sector, (
                f"Ticker {ticker} expected sector {expected_sector}, "
                f"got {by_ticker[ticker].sector}"
            )


# ---------------------------------------------------------------------------
# Test 7: ETFS preset composes with sector filter
# ---------------------------------------------------------------------------


class TestETFSPresetWithSectorFilter:
    """ETFS preset and sector filter combine correctly."""

    async def test_etfs_preset_with_sector_filter(self) -> None:
        """ETFS preset + sector filter: both constraints apply."""
        # SPY and QQQ are ETFs; only AAPL and SPY are in SP500 IT sector
        sp500 = [
            SP500Constituent(ticker="AAPL", sector="Information Technology"),
            SP500Constituent(ticker="SPY", sector="Information Technology"),
            SP500Constituent(ticker="QQQ", sector="Financials"),
        ]
        all_tickers = ["AAPL", "SPY", "QQQ", "IWM"]
        etf_tickers = ["SPY", "QQQ", "IWM"]

        settings = AppSettings()
        settings.scan.sectors = [GICSSector.INFORMATION_TECHNOLOGY]
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(
            tickers=all_tickers,
            sp500_constituents=sp500,
            etf_tickers=etf_tickers,
            batch_result=_make_batch_result(["SPY"]),
            settings=settings,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.ETFS, token, _noop_progress)

        result_tickers = {ts.ticker for ts in result.scores}
        # ETFS preset keeps only SPY, QQQ, IWM.
        # Sector filter (IT) keeps only SPY (mapped as IT in SP500).
        # QQQ is mapped as Financials, IWM is not in SP500.
        assert result_tickers == {"SPY"}


# ---------------------------------------------------------------------------
# Test 8: Repository round-trip with sector + company_name via real DB
# ---------------------------------------------------------------------------


class TestRepositoryRoundTripSectorIntegration:
    """Verify sector and company_name survive persistence round-trip.

    Uses real in-memory SQLite database (not mocks) to verify the full
    save -> load cycle with sector/company_name.
    """

    async def test_sector_company_name_round_trip_via_real_db(self) -> None:
        """Save enriched TickerScore via Repository, load it, verify fields."""
        from options_arena.data.database import Database
        from options_arena.data.repository import Repository
        from options_arena.models import ScanRun

        db = Database(":memory:")
        await db.connect()
        try:
            repo = Repository(db)

            from datetime import UTC, datetime

            scan_run = ScanRun(
                started_at=datetime(2026, 2, 26, 10, 0, 0, tzinfo=UTC),
                completed_at=datetime(2026, 2, 26, 10, 5, 0, tzinfo=UTC),
                preset=ScanPreset.SP500,
                tickers_scanned=2,
                tickers_scored=2,
                recommendations=0,
            )
            scan_id = await repo.save_scan_run(scan_run)

            scores = [
                TickerScore(
                    ticker="AAPL",
                    composite_score=85.0,
                    direction=SignalDirection.BULLISH,
                    signals=IndicatorSignals(rsi=65.0),
                    sector=GICSSector.INFORMATION_TECHNOLOGY,
                    company_name="Apple Inc.",
                ),
                TickerScore(
                    ticker="JPM",
                    composite_score=72.0,
                    direction=SignalDirection.NEUTRAL,
                    signals=IndicatorSignals(rsi=50.0),
                    sector=GICSSector.FINANCIALS,
                    company_name="JPMorgan Chase & Co.",
                ),
            ]
            await repo.save_ticker_scores(scan_id, scores)

            loaded = await repo.get_scores_for_scan(scan_id)
            assert len(loaded) == 2

            by_ticker = {s.ticker: s for s in loaded}

            assert by_ticker["AAPL"].sector is GICSSector.INFORMATION_TECHNOLOGY
            assert isinstance(by_ticker["AAPL"].sector, GICSSector)
            assert by_ticker["AAPL"].company_name == "Apple Inc."

            assert by_ticker["JPM"].sector is GICSSector.FINANCIALS
            assert isinstance(by_ticker["JPM"].sector, GICSSector)
            assert by_ticker["JPM"].company_name == "JPMorgan Chase & Co."
        finally:
            await db.close()

    async def test_sector_none_round_trip_via_real_db(self) -> None:
        """TickerScore with sector=None survives database round-trip."""
        from options_arena.data.database import Database
        from options_arena.data.repository import Repository
        from options_arena.models import ScanRun

        db = Database(":memory:")
        await db.connect()
        try:
            repo = Repository(db)

            from datetime import UTC, datetime

            scan_run = ScanRun(
                started_at=datetime(2026, 2, 26, 10, 0, 0, tzinfo=UTC),
                completed_at=datetime(2026, 2, 26, 10, 5, 0, tzinfo=UTC),
                preset=ScanPreset.FULL,
                tickers_scanned=1,
                tickers_scored=1,
                recommendations=0,
            )
            scan_id = await repo.save_scan_run(scan_run)

            scores = [
                TickerScore(
                    ticker="XYZ",
                    composite_score=60.0,
                    direction=SignalDirection.BEARISH,
                    signals=IndicatorSignals(),
                    sector=None,
                    company_name=None,
                ),
            ]
            await repo.save_ticker_scores(scan_id, scores)

            loaded = await repo.get_scores_for_scan(scan_id)
            assert len(loaded) == 1
            assert loaded[0].sector is None
            assert loaded[0].company_name is None
        finally:
            await db.close()
