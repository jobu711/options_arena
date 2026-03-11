"""Tests for pipeline preset dispatch (NASDAQ100, RUSSELL2000, MOST_ACTIVE)
and Phase 3 max_price filter (#287).

Covers:
  - Phase 1 dispatches NASDAQ100 -> fetch_nasdaq100_constituents.
  - Phase 1 dispatches RUSSELL2000 -> fetch_russell2000_tickers.
  - Phase 1 dispatches MOST_ACTIVE -> fetch_most_active.
  - New presets intersect with optionable set.
  - Empty preset result produces empty Phase 1 output.
  - Phase 3 max_price filter excludes expensive stocks.
  - None max_price means no upper filter.
  - min and max price combined filtering.
  - Stock at exactly max_price is included (boundary).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from options_arena.models import (
    AppSettings,
    IndicatorSignals,
    ScanPreset,
    SignalDirection,
    TickerScore,
)
from options_arena.models.config import ScanConfig
from options_arena.models.enums import DividendSource, ExerciseStyle, OptionType
from options_arena.models.filters import OptionsFilters, ScanFilterSpec, UniverseFilters
from options_arena.models.market_data import OHLCV, TickerInfo
from options_arena.models.options import OptionContract
from options_arena.scan.models import (
    ScoringResult,
    UniverseResult,
)
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
    *,
    close_price: float = 100.0,
    volume: int = 1_000_000,
) -> BatchOHLCVResult:
    """Build a BatchOHLCVResult with synthetic data for the given tickers."""
    results: list[TickerOHLCVResult] = []
    for ticker in tickers:
        results.append(
            TickerOHLCVResult(
                ticker=ticker,
                data=_make_ohlcv_bars(
                    ticker, bars_per_ticker, close_price=close_price, volume=volume
                ),
            )
        )
    return BatchOHLCVResult(results=results)


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


def _make_phase1_pipeline(
    *,
    optionable_tickers: list[str] | None = None,
    sp500_constituents: list[SP500Constituent] | None = None,
    etf_tickers: list[str] | None = None,
    nasdaq100_tickers: list[str] | None = None,
    russell2000_tickers: list[str] | None = None,
    most_active_tickers: list[str] | None = None,
    batch_result: BatchOHLCVResult | None = None,
    settings: AppSettings | None = None,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services for Phase 1 preset dispatch testing."""
    _settings = settings or AppSettings(
        scan=ScanConfig(filters=ScanFilterSpec(universe=UniverseFilters(preset=ScanPreset.FULL)))
    )
    tickers = optionable_tickers if optionable_tickers is not None else ["AAPL", "MSFT", "GOOG"]

    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=sp500_constituents or [])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=etf_tickers or [])
    mock_universe.fetch_nasdaq100_constituents = AsyncMock(return_value=nasdaq100_tickers or [])
    mock_universe.fetch_russell2000_tickers = AsyncMock(return_value=russell2000_tickers or [])
    mock_universe.fetch_most_active = AsyncMock(return_value=most_active_tickers or [])

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


def _make_phase3_pipeline(
    *,
    settings: AppSettings | None = None,
    fred_rate: float = 0.045,
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

    mock_fred.fetch_risk_free_rate = AsyncMock(return_value=fred_rate)
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)
    mock_market_data.fetch_ticker_info = AsyncMock(side_effect=lambda t: _make_ticker_info(t))
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
# Phase 1: Preset dispatch tests
# ---------------------------------------------------------------------------


class TestPhase1PresetDispatch:
    """Verify new preset branches (NASDAQ100, RUSSELL2000, MOST_ACTIVE)
    dispatch to the correct UniverseService methods and intersect with
    the optionable ticker set."""

    async def test_nasdaq100_dispatch(self) -> None:
        """Verify NASDAQ100 preset calls fetch_nasdaq100_constituents."""
        optionable = ["AAPL", "MSFT", "GOOG", "AMZN", "XYZ"]
        nasdaq100 = ["AAPL", "MSFT", "AMZN", "TSLA"]  # TSLA not optionable
        batch = _make_batch_result(["AAPL", "MSFT", "AMZN"])
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.NASDAQ100),
                )
            )
        )

        pipeline, mocks = _make_phase1_pipeline(
            optionable_tickers=optionable,
            nasdaq100_tickers=nasdaq100,
            batch_result=batch,
            settings=settings,
        )

        result = await pipeline._phase_universe(_noop_progress)

        mocks["universe"].fetch_nasdaq100_constituents.assert_awaited_once()
        # Only optionable AND nasdaq100 tickers should pass
        assert set(result.tickers) == {"AAPL", "MSFT", "AMZN"}
        assert "TSLA" not in result.tickers  # not in optionable set
        assert "XYZ" not in result.tickers  # not in nasdaq100

    async def test_russell2000_dispatch(self) -> None:
        """Verify RUSSELL2000 preset calls fetch_russell2000_tickers."""
        optionable = ["AAPL", "MSFT", "SMTK", "ABCD"]
        russell2000 = ["SMTK", "ABCD", "EFGH"]  # EFGH not optionable
        batch = _make_batch_result(["SMTK", "ABCD"])
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.RUSSELL2000),
                )
            )
        )

        pipeline, mocks = _make_phase1_pipeline(
            optionable_tickers=optionable,
            russell2000_tickers=russell2000,
            batch_result=batch,
            settings=settings,
        )

        result = await pipeline._phase_universe(_noop_progress)

        mocks["universe"].fetch_russell2000_tickers.assert_awaited_once_with(
            repo=mocks["repository"],
        )
        assert set(result.tickers) == {"SMTK", "ABCD"}
        assert "EFGH" not in result.tickers

    async def test_most_active_dispatch(self) -> None:
        """Verify MOST_ACTIVE preset calls fetch_most_active."""
        optionable = ["AAPL", "MSFT", "TSLA", "NVDA"]
        most_active = ["TSLA", "NVDA", "PLTR"]  # PLTR not optionable
        batch = _make_batch_result(["TSLA", "NVDA"])
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.MOST_ACTIVE),
                )
            )
        )

        pipeline, mocks = _make_phase1_pipeline(
            optionable_tickers=optionable,
            most_active_tickers=most_active,
            batch_result=batch,
            settings=settings,
        )

        result = await pipeline._phase_universe(_noop_progress)

        mocks["universe"].fetch_most_active.assert_awaited_once()
        assert set(result.tickers) == {"TSLA", "NVDA"}
        assert "PLTR" not in result.tickers

    async def test_new_presets_intersect_optionable(self) -> None:
        """Verify new preset results are intersected with optionable set."""
        optionable = ["AAPL", "MSFT"]
        # Preset returns tickers not in optionable — should be excluded
        nasdaq100 = ["AAPL", "TSLA", "NVDA"]
        batch = _make_batch_result(["AAPL"])
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.NASDAQ100),
                )
            )
        )

        pipeline, _ = _make_phase1_pipeline(
            optionable_tickers=optionable,
            nasdaq100_tickers=nasdaq100,
            batch_result=batch,
            settings=settings,
        )

        result = await pipeline._phase_universe(_noop_progress)

        # Only AAPL is in both optionable AND nasdaq100
        assert result.tickers == ["AAPL"]

    async def test_empty_preset_result(self) -> None:
        """Verify empty fetch result produces empty Phase 1 output."""
        optionable = ["AAPL", "MSFT"]
        nasdaq100: list[str] = []  # empty preset
        batch = _make_batch_result([])
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.NASDAQ100),
                )
            )
        )

        pipeline, _ = _make_phase1_pipeline(
            optionable_tickers=optionable,
            nasdaq100_tickers=nasdaq100,
            batch_result=batch,
            settings=settings,
        )

        result = await pipeline._phase_universe(_noop_progress)

        assert result.tickers == []
        assert result.ohlcv_map == {}

    async def test_empty_optionable_with_preset(self) -> None:
        """Verify empty optionable set + non-empty preset produces empty result."""
        optionable: list[str] = []
        russell2000 = ["SMTK", "ABCD"]
        batch = _make_batch_result([])
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.RUSSELL2000),
                )
            )
        )

        pipeline, _ = _make_phase1_pipeline(
            optionable_tickers=optionable,
            russell2000_tickers=russell2000,
            batch_result=batch,
            settings=settings,
        )

        result = await pipeline._phase_universe(_noop_progress)

        assert result.tickers == []


# ---------------------------------------------------------------------------
# Phase 3: max_price filter tests
# ---------------------------------------------------------------------------


class TestPhase3MaxPriceFilter:
    """Verify max_price filter in Phase 3 liquidity pre-filter."""

    async def test_max_price_filters_expensive(self) -> None:
        """Verify stocks above max_price are excluded."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                    universe=UniverseFilters(min_price=1.0, max_price=200.0),
                )
            )
        )

        tickers = ["CHEAP", "EXPENSIVE"]
        universe_result = UniverseResult(
            tickers=tickers,
            ohlcv_map={
                "CHEAP": _make_ohlcv_bars("CHEAP", close_price=150.0),
                "EXPENSIVE": _make_ohlcv_bars("EXPENSIVE", close_price=500.0),
            },
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )
        scoring_result = _make_scoring_result(tickers)

        pipeline, mocks = _make_phase3_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        # Only CHEAP should pass through to option chain fetch
        call_args = mocks["options_data"].fetch_chain_all_expirations.call_args_list
        fetched_tickers = [call.args[0] for call in call_args]
        assert "CHEAP" in fetched_tickers
        assert "EXPENSIVE" not in fetched_tickers

    async def test_max_price_none_no_filter(self) -> None:
        """Verify None max_price means no upper filter is applied."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                    universe=UniverseFilters(min_price=1.0, max_price=None),
                )
            )
        )

        tickers = ["AAPL", "BRK"]
        universe_result = UniverseResult(
            tickers=tickers,
            ohlcv_map={
                "AAPL": _make_ohlcv_bars("AAPL", close_price=150.0),
                "BRK": _make_ohlcv_bars("BRK", close_price=600_000.0),
            },
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )
        scoring_result = _make_scoring_result(tickers)

        pipeline, mocks = _make_phase3_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        # Both should pass — no max_price filter
        call_args = mocks["options_data"].fetch_chain_all_expirations.call_args_list
        fetched_tickers = [call.args[0] for call in call_args]
        assert "AAPL" in fetched_tickers
        assert "BRK" in fetched_tickers

    async def test_min_and_max_price_combined(self) -> None:
        """Verify both min and max price filters applied together."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                    universe=UniverseFilters(min_price=20.0, max_price=300.0),
                )
            )
        )

        tickers = ["PENNY", "MIDRANGE", "PRICEY"]
        universe_result = UniverseResult(
            tickers=tickers,
            ohlcv_map={
                "PENNY": _make_ohlcv_bars("PENNY", close_price=5.0),  # below min
                "MIDRANGE": _make_ohlcv_bars("MIDRANGE", close_price=150.0),  # in range
                "PRICEY": _make_ohlcv_bars("PRICEY", close_price=500.0),  # above max
            },
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )
        scoring_result = _make_scoring_result(tickers)

        pipeline, mocks = _make_phase3_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        # Only MIDRANGE should pass through
        call_args = mocks["options_data"].fetch_chain_all_expirations.call_args_list
        fetched_tickers = [call.args[0] for call in call_args]
        assert "MIDRANGE" in fetched_tickers
        assert "PENNY" not in fetched_tickers
        assert "PRICEY" not in fetched_tickers

    async def test_max_price_boundary(self) -> None:
        """Verify stock at exactly max_price is included (not excluded)."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    options=OptionsFilters(min_dollar_volume=1.0),
                    universe=UniverseFilters(min_price=1.0, max_price=200.0),
                )
            )
        )

        tickers = ["EXACT"]
        universe_result = UniverseResult(
            tickers=tickers,
            ohlcv_map={
                "EXACT": _make_ohlcv_bars("EXACT", close_price=200.0),  # exactly at max
            },
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )
        scoring_result = _make_scoring_result(tickers)

        pipeline, mocks = _make_phase3_pipeline(settings=settings)

        await pipeline._phase_options(scoring_result, universe_result, _noop_progress)

        # Stock at exactly max_price should be included (> not >=)
        call_args = mocks["options_data"].fetch_chain_all_expirations.call_args_list
        fetched_tickers = [call.args[0] for call in call_args]
        assert "EXACT" in fetched_tickers
