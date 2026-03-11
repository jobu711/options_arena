"""Tests for ScanPipeline Phase 3 — Liquidity Pre-filter + Options + Contracts.

Covers:
  - Liquidity pre-filter rejects low dollar volume.
  - Liquidity pre-filter rejects low price.
  - Top-N selection limits tickers.
  - FredService called exactly once.
  - Option chains fetched for each top-N ticker.
  - TickerInfo fetched for each top-N ticker.
  - recommend_contracts called with correct args.
  - Per-ticker error isolation: one failed ticker doesn't crash scan.
  - Empty scored tickers (all filtered by liquidity) -> empty recommendations.
  - Progress callback invoked with ScanPhase.OPTIONS.
  - No option chains -> empty recommendations for that ticker.
  - Cancellation between Phase 2 and Phase 3.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from options_arena.models import (
    AppSettings,
    IndicatorSignals,
    OptionContract,
    ScanPreset,
    SignalDirection,
    TickerScore,
)
from options_arena.models.config import ScanConfig
from options_arena.models.enums import DividendSource, ExerciseStyle, OptionType
from options_arena.models.filters import OptionsFilters, ScanFilterSpec, UniverseFilters
from options_arena.models.market_data import OHLCV, TickerInfo
from options_arena.scan.models import OptionsResult, ScoringResult, UniverseResult
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import CancellationToken, ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult
from options_arena.services.options_data import ExpirationChain

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
    """Generate *n* synthetic OHLCV bars for a ticker.

    Args:
        ticker: Ticker symbol.
        n: Number of bars.
        close_price: Base close price.
        volume: Base volume (used for dollar-volume computation).
    """
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


def _make_ticker_score(
    ticker: str,
    score: float = 75.0,
    direction: SignalDirection = SignalDirection.BULLISH,
) -> TickerScore:
    """Create a TickerScore with sensible defaults."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=direction,
        signals=IndicatorSignals(rsi=65.0, adx=25.0),
    )


def _make_ticker_info(ticker: str, current_price: float = 100.0) -> TickerInfo:
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
    close_price: float = 100.0,
    volume: int = 1_000_000,
) -> UniverseResult:
    """Build a UniverseResult with synthetic OHLCV data."""
    ohlcv_map = {t: _make_ohlcv_bars(t, close_price=close_price, volume=volume) for t in tickers}
    return UniverseResult(
        tickers=tickers,
        ohlcv_map=ohlcv_map,
        sp500_sectors={},
        failed_count=0,
        filtered_count=0,
    )


def _make_scoring_result(
    tickers: list[str],
    scores: list[float] | None = None,
) -> ScoringResult:
    """Build a ScoringResult with given tickers (sorted descending by score)."""
    _scores = scores or [90.0 - i * 5.0 for i in range(len(tickers))]
    ticker_scores = [_make_ticker_score(t, score=s) for t, s in zip(tickers, _scores, strict=True)]
    raw_signals = {t: IndicatorSignals(rsi=65.0, adx=25.0) for t in tickers}
    return ScoringResult(scores=ticker_scores, raw_signals=raw_signals)


def _make_pipeline(
    *,
    settings: AppSettings | None = None,
    fred_rate: float = 0.045,
    ticker_infos: dict[str, TickerInfo] | None = None,
    expiration_chains: dict[str, list[ExpirationChain]] | None = None,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services for Phase 3 testing."""
    _settings = settings or AppSettings(
        scan=ScanConfig(filters=ScanFilterSpec(universe=UniverseFilters(preset=ScanPreset.FULL)))
    )

    mock_universe = AsyncMock()
    mock_market_data = AsyncMock()
    mock_options_data = AsyncMock()
    mock_fred = AsyncMock()
    mock_repository = AsyncMock()

    # FRED always returns the configured rate
    mock_fred.fetch_risk_free_rate = AsyncMock(return_value=fred_rate)

    # Earnings date: return None (not testing earnings in this file)
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)

    # Default ticker info: return a generic TickerInfo for any ticker
    if ticker_infos is not None:

        async def _fetch_info(ticker: str) -> TickerInfo:
            return ticker_infos[ticker]

        mock_market_data.fetch_ticker_info = AsyncMock(side_effect=_fetch_info)
    else:
        mock_market_data.fetch_ticker_info = AsyncMock(side_effect=lambda t: _make_ticker_info(t))

    # Default chains: return a single chain per ticker
    if expiration_chains is not None:

        async def _fetch_chains(ticker: str) -> list[ExpirationChain]:
            return expiration_chains.get(ticker, [])

        mock_options_data.fetch_chain_all_expirations = AsyncMock(side_effect=_fetch_chains)
    else:
        mock_options_data.fetch_chain_all_expirations = AsyncMock(
            side_effect=lambda t: [_make_expiration_chain(t)]
        )

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
# Phase 3 (Options) tests
# ---------------------------------------------------------------------------


class TestLiquidityPreFilter:
    """Liquidity pre-filter rejects tickers below dollar volume or price thresholds."""

    @pytest.mark.critical
    async def test_rejects_low_dollar_volume(self) -> None:
        """Tickers with avg dollar volume below threshold are excluded."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=10_000_000.0),
                )
            )
        )

        # AAPL: close=100, volume=50_000 -> avg_dv = 5,000,000 (below 10M)
        # MSFT: close=100, volume=200_000 -> avg_dv = 20,000,000 (above 10M)
        tickers = ["AAPL", "MSFT"]
        universe_result = UniverseResult(
            tickers=tickers,
            ohlcv_map={
                "AAPL": _make_ohlcv_bars("AAPL", close_price=100.0, volume=50_000),
                "MSFT": _make_ohlcv_bars("MSFT", close_price=100.0, volume=200_000),
            },
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )
        scoring_result = _make_scoring_result(tickers)

        pipeline, mocks = _make_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        # Only MSFT should have had options fetched
        mocks["options_data"].fetch_chain_all_expirations.assert_awaited_once()
        call_args = mocks["options_data"].fetch_chain_all_expirations.call_args_list
        fetched_tickers = [call.args[0] for call in call_args]
        assert "AAPL" not in fetched_tickers
        assert "MSFT" in fetched_tickers

    async def test_rejects_low_price(self) -> None:
        """Tickers with latest close below min_price are excluded."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(min_price=10.0),
                    options=OptionsFilters(min_dollar_volume=1.0),
                )
            )
        )

        # PENNY: close=5.0 (below $10)
        # AAPL: close=150.0 (above $10)
        tickers = ["PENNY", "AAPL"]
        universe_result = UniverseResult(
            tickers=tickers,
            ohlcv_map={
                "PENNY": _make_ohlcv_bars("PENNY", close_price=5.0, volume=5_000_000),
                "AAPL": _make_ohlcv_bars("AAPL", close_price=150.0, volume=1_000_000),
            },
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )
        scoring_result = _make_scoring_result(tickers)

        pipeline, mocks = _make_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        call_args = mocks["options_data"].fetch_chain_all_expirations.call_args_list
        fetched_tickers = [call.args[0] for call in call_args]
        assert "PENNY" not in fetched_tickers
        assert "AAPL" in fetched_tickers

    async def test_all_filtered_produces_empty_recommendations(self) -> None:
        """When all tickers are filtered by liquidity, recommendations are empty."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=999_999_999.0),
                )
            )
        )

        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers, close_price=100.0, volume=100)
        scoring_result = _make_scoring_result(tickers)

        pipeline, _ = _make_pipeline(settings=settings)

        result = await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        assert result.recommendations == {}


class TestTopNSelection:
    """Top-N selection limits the number of tickers processed."""

    async def test_limits_tickers_to_top_n(self) -> None:
        """Only top_n tickers by composite_score proceed to chain fetching."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(top_n=2, min_dollar_volume=1.0),
                )
            )
        )

        tickers = ["A", "B", "C", "D"]
        universe_result = _make_universe_result(tickers, close_price=100.0)
        # Scores descending: A=90, B=85, C=80, D=75
        scoring_result = _make_scoring_result(tickers, scores=[90.0, 85.0, 80.0, 75.0])

        pipeline, mocks = _make_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        # Only 2 tickers should have been fetched (top_n=2)
        assert mocks["options_data"].fetch_chain_all_expirations.await_count == 2


class TestFredService:
    """FredService is called exactly once for the entire scan."""

    async def test_fred_called_once(self) -> None:
        """FredService.fetch_risk_free_rate called exactly once."""
        tickers = ["AAPL", "MSFT"]
        universe_result = _make_universe_result(tickers, close_price=100.0)
        scoring_result = _make_scoring_result(tickers)

        pipeline, mocks = _make_pipeline()

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        mocks["fred"].fetch_risk_free_rate.assert_awaited_once()

    async def test_risk_free_rate_passed_through(self) -> None:
        """The risk-free rate from FRED is returned in the OptionsResult."""
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers, close_price=100.0)
        scoring_result = _make_scoring_result(tickers)

        pipeline, _ = _make_pipeline(fred_rate=0.042)

        result = await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        assert result.risk_free_rate == pytest.approx(0.042)


class TestPerTickerFetching:
    """Option chains and ticker info fetched for each top-N ticker."""

    async def test_chains_fetched_for_each_ticker(self) -> None:
        """fetch_chain_all_expirations called for each top-N ticker."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                )
            )
        )

        tickers = ["AAPL", "MSFT"]
        universe_result = _make_universe_result(tickers, close_price=100.0)
        scoring_result = _make_scoring_result(tickers)

        pipeline, mocks = _make_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        assert mocks["options_data"].fetch_chain_all_expirations.await_count == 2

    async def test_ticker_info_fetched_for_each_ticker(self) -> None:
        """fetch_ticker_info called for each top-N ticker."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                )
            )
        )

        tickers = ["AAPL", "MSFT"]
        universe_result = _make_universe_result(tickers, close_price=100.0)
        scoring_result = _make_scoring_result(tickers)

        pipeline, mocks = _make_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        assert mocks["market_data"].fetch_ticker_info.await_count == 2


class TestRecommendContracts:
    """recommend_contracts called with correct arguments."""

    async def test_recommend_contracts_args(self) -> None:
        """recommend_contracts receives correct spot, rate, yield, direction, config."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                )
            )
        )

        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers, close_price=150.0)
        scoring_result = _make_scoring_result(tickers)

        ticker_info = _make_ticker_info("AAPL", current_price=150.0)

        pipeline, _ = _make_pipeline(
            settings=settings,
            fred_rate=0.045,
            ticker_infos={"AAPL": ticker_info},
        )

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("AAPL")],
        ) as mock_recommend:
            await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

            mock_recommend.assert_called_once()
            call_kwargs = mock_recommend.call_args
            # Check keyword arguments
            assert call_kwargs.kwargs["spot"] == pytest.approx(150.0)
            assert call_kwargs.kwargs["risk_free_rate"] == pytest.approx(0.045)
            assert call_kwargs.kwargs["dividend_yield"] == pytest.approx(0.01)
            assert call_kwargs.kwargs["direction"] == SignalDirection.BULLISH
            assert call_kwargs.kwargs["filters"] is settings.scan.filters.options
            assert call_kwargs.kwargs["delta_target"] == pytest.approx(
                settings.pricing.delta_target
            )

    async def test_no_chains_returns_empty_recommendations(self) -> None:
        """Ticker with no option chains produces empty recommendation."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                )
            )
        )

        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers, close_price=100.0)
        scoring_result = _make_scoring_result(tickers)

        pipeline, _ = _make_pipeline(
            settings=settings,
            expiration_chains={"AAPL": []},
        )

        result = await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        assert "AAPL" not in result.recommendations


class TestPerTickerErrorIsolation:
    """One failed ticker doesn't crash the entire scan."""

    async def test_failed_ticker_does_not_crash_scan(self) -> None:
        """If one ticker's chain fetch raises, others still succeed."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                )
            )
        )

        tickers = ["AAPL", "MSFT"]
        universe_result = _make_universe_result(tickers, close_price=100.0)
        scoring_result = _make_scoring_result(tickers)

        # AAPL raises, MSFT succeeds
        async def _mock_chains(ticker: str) -> list[ExpirationChain]:
            if ticker == "AAPL":
                raise RuntimeError("yfinance timeout")
            return [_make_expiration_chain(ticker)]

        pipeline, mocks = _make_pipeline(settings=settings)
        mocks["options_data"].fetch_chain_all_expirations = AsyncMock(side_effect=_mock_chains)

        result = await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        # AAPL failed but MSFT should still be processed
        assert isinstance(result, OptionsResult)
        # The scan should not have crashed
        assert result.risk_free_rate is not None


class TestProgressCallback:
    """Progress callback invoked with ScanPhase.OPTIONS."""

    async def test_progress_invoked_with_options_phase(self) -> None:
        """Progress callback called with ScanPhase.OPTIONS."""
        progress_calls: list[tuple[ScanPhase, int, int]] = []

        def recording_progress(phase: ScanPhase, current: int, total: int) -> None:
            progress_calls.append((phase, current, total))

        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                )
            )
        )

        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers, close_price=100.0)
        scoring_result = _make_scoring_result(tickers)

        pipeline, _ = _make_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, recording_progress)

        # Should have OPTIONS phase calls
        options_calls = [c for c in progress_calls if c[0] == ScanPhase.OPTIONS]
        assert len(options_calls) >= 2

        # First call: start (0, total)
        assert options_calls[0][1] == 0

        # Last call: completion (total, total)
        assert options_calls[-1][1] == options_calls[-1][2]


class TestPerTickerTimeout:
    """Per-ticker timeout prevents one slow ticker from stalling the pipeline."""

    async def test_slow_ticker_times_out_others_succeed(self) -> None:
        """A ticker that exceeds the per-ticker timeout is isolated as a failure."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                )
            )
        )
        settings.scan.options_per_ticker_timeout = 0.1  # 100ms

        tickers = ["SLOW", "FAST"]
        universe_result = _make_universe_result(tickers, close_price=100.0)
        scoring_result = _make_scoring_result(tickers, scores=[90.0, 85.0])

        async def _mock_chains(ticker: str) -> list[ExpirationChain]:
            if ticker == "SLOW":
                await asyncio.sleep(5.0)  # Exceeds 100ms timeout
            return [_make_expiration_chain(ticker)]

        pipeline, mocks = _make_pipeline(settings=settings)
        mocks["options_data"].fetch_chain_all_expirations = AsyncMock(side_effect=_mock_chains)

        result = await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        # SLOW timed out, but scan completed successfully
        assert isinstance(result, OptionsResult)
        # SLOW should NOT be in recommendations (timed out)
        assert "SLOW" not in result.recommendations


class TestPhase3Cancellation:
    """Cancellation between Phase 2 and Phase 3, and between Phase 3 and Phase 4."""

    async def test_cancelled_after_phase2_skips_phase3(self) -> None:
        """Token cancelled after Phase 2 returns phases_completed=2."""
        tickers = ["AAPL"]
        batch = BatchOHLCVResult(
            results=[
                TickerOHLCVResult(
                    ticker="AAPL",
                    data=_make_ohlcv_bars("AAPL", n=300, close_price=100.0),
                )
            ]
        )

        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])

        mock_market_data = AsyncMock()
        mock_market_data.fetch_batch_ohlcv = AsyncMock(return_value=batch)
        mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)

        mock_options_data = AsyncMock()
        mock_fred = AsyncMock()
        mock_repository = AsyncMock()

        pipeline = ScanPipeline(
            settings=AppSettings(),
            market_data=mock_market_data,
            options_data=mock_options_data,
            fred=mock_fred,
            universe=mock_universe,
            repository=mock_repository,
        )

        token = CancellationToken()

        # We need the token to NOT be cancelled after Phase 1, but cancelled
        # after Phase 2. Use a side effect on the property.
        # Since we can't easily side-effect a property, cancel after Phase 2
        # by patching _phase_scoring to cancel the token before returning.
        original_phase_scoring = pipeline._phase_scoring

        async def _scoring_then_cancel(
            universe_result: UniverseResult,
            progress: object,
        ) -> ScoringResult:
            result = await original_phase_scoring(universe_result, progress)  # type: ignore[arg-type]
            token.cancel()  # Cancel after Phase 2
            return result

        pipeline._phase_scoring = _scoring_then_cancel  # type: ignore[assignment]

        result = await pipeline.run(token, _noop_progress)

        assert result.cancelled is True
        assert result.phases_completed == 2
        assert result.recommendations == {}
        # FRED should not have been called since Phase 3 never ran
        mock_fred.fetch_risk_free_rate.assert_not_awaited()
