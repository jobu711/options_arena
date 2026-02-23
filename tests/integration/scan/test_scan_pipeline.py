"""Integration tests for the full ScanPipeline end-to-end.

Exercises all 4 phases with mock services, verifying:
  - Happy path: full pipeline completes all 4 phases with correct metadata.
  - Cancellation: partial results at various phase boundaries.
  - Edge cases: empty universe, all OHLCV failures, all filtered by liquidity.
  - ProgressCallback invocation order matches UNIVERSE -> SCORING -> OPTIONS -> PERSIST.
  - Re-export verification: all public names importable from ``options_arena.scan``.
  - FredService fallback rate propagation.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from options_arena.models import (
    AppSettings,
    OptionContract,
    ScanPreset,
    SignalDirection,
    TickerScore,
)
from options_arena.models.enums import DividendSource, ExerciseStyle, OptionType
from options_arena.models.market_data import OHLCV, TickerInfo
from options_arena.scan.models import ScanResult
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


# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------


def _make_ohlcv_bars(
    ticker: str,
    n: int = 300,
    *,
    close_price: float = 150.0,
    volume: int = 1_000_000,
) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars for a ticker.

    Uses 300 bars by default to exceed warmup of all indicators.
    Uses close=150, volume=1M by default for avg dollar volume of $150M (passes
    the default $10M liquidity pre-filter).

    Price oscillates around close_price without drifting, ensuring the latest
    close is always near close_price.
    """
    bars: list[OHLCV] = []
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        # Oscillate +/- 5 around close_price without drift
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
    batch_result: BatchOHLCVResult | None = None,
    settings: AppSettings | None = None,
    fred_rate: float = 0.045,
    save_scan_run_return: int = 42,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a fully-mocked ScanPipeline for end-to-end integration tests.

    Mocks all 5 injected services with sensible defaults that pass all filters.
    """
    _tickers = tickers if tickers is not None else ["AAPL", "MSFT", "GOOG"]

    if settings is not None:
        _settings = settings
    else:
        _settings = AppSettings()
        # Relax filters so tickers pass by default (only when no explicit settings)
        _settings.scan.min_dollar_volume = 1.0
        _settings.scan.min_price = 1.0

    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=_tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(
        return_value=sp500_constituents
        or [SP500Constituent(ticker=t, sector="Technology") for t in _tickers]
    )

    mock_market_data = AsyncMock()
    mock_market_data.fetch_batch_ohlcv = AsyncMock(
        return_value=batch_result or _make_batch_result(_tickers)
    )
    mock_market_data.fetch_ticker_info = AsyncMock(side_effect=lambda t: _make_ticker_info(t))

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
# Test 1: Full pipeline happy path
# ---------------------------------------------------------------------------


class TestFullPipelineHappyPath:
    """Full end-to-end pipeline run with all 4 phases completing."""

    async def test_full_pipeline_completes_4_phases(self) -> None:
        """All 4 phases complete, cancelled is False, phases_completed is 4."""
        pipeline, _mocks = _make_full_pipeline(tickers=["AAPL", "MSFT"])
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("X")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.phases_completed == 4
        assert result.cancelled is False

    async def test_full_pipeline_scan_run_id_populated(self) -> None:
        """scan_run.id is populated from the repository mock."""
        pipeline, _ = _make_full_pipeline(tickers=["AAPL"], save_scan_run_return=99)
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("AAPL")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.scan_run.id == 99

    async def test_full_pipeline_scores_non_empty(self) -> None:
        """Scores list is non-empty after a full successful run."""
        pipeline, _ = _make_full_pipeline(tickers=["AAPL", "MSFT"])
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("X")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert len(result.scores) > 0
        for ts in result.scores:
            assert isinstance(ts, TickerScore)
            assert isinstance(ts.direction, SignalDirection)

    async def test_full_pipeline_risk_free_rate_set(self) -> None:
        """risk_free_rate on ScanResult matches the FRED service return."""
        pipeline, _ = _make_full_pipeline(tickers=["AAPL"], fred_rate=0.042)
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.risk_free_rate == pytest.approx(0.042)

    async def test_full_pipeline_recommendations_dict_exists(self) -> None:
        """Recommendations dict is present (may be empty if no contracts pass)."""
        pipeline, _ = _make_full_pipeline(tickers=["AAPL"])
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("AAPL")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert isinstance(result.recommendations, dict)
        # With the patched recommend_contracts returning a contract, we should
        # have at least one recommendation
        assert len(result.recommendations) >= 1

    async def test_full_pipeline_scan_run_metadata(self) -> None:
        """ScanRun metadata reflects actual pipeline execution."""
        pipeline, _ = _make_full_pipeline(
            tickers=["AAPL", "MSFT", "GOOG"],
            save_scan_run_return=7,
        )
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.scan_run.preset == ScanPreset.FULL
        assert result.scan_run.tickers_scanned == 3
        assert result.scan_run.tickers_scored > 0
        assert result.scan_run.started_at is not None
        assert result.scan_run.completed_at is not None
        assert result.scan_run.started_at <= result.scan_run.completed_at

    async def test_full_pipeline_all_services_called(self) -> None:
        """All 5 services are called during a full run."""
        pipeline, mocks = _make_full_pipeline(tickers=["AAPL"])
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        mocks["universe"].fetch_optionable_tickers.assert_awaited_once()
        mocks["universe"].fetch_sp500_constituents.assert_awaited_once()
        mocks["market_data"].fetch_batch_ohlcv.assert_awaited_once()
        mocks["fred"].fetch_risk_free_rate.assert_awaited_once()
        mocks["repository"].save_scan_run.assert_awaited_once()
        mocks["repository"].save_ticker_scores.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 2: Cancelled before Phase 1 (token pre-cancelled)
# ---------------------------------------------------------------------------


class TestCancelledBeforePhase1:
    """Token cancelled before run() is called.

    The pipeline does NOT check cancellation before Phase 1 — it checks
    BETWEEN phases. So Phase 1 will complete, then cancellation is detected.
    Result: phases_completed=1, cancelled=True.
    """

    async def test_pre_cancelled_token_stops_after_phase1(self) -> None:
        """Pre-cancelled token: Phase 1 completes, then cancelled."""
        pipeline, _ = _make_full_pipeline(tickers=["AAPL"])
        token = CancellationToken()
        token.cancel()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.cancelled is True
        assert result.phases_completed == 1
        assert result.scores == []
        assert result.recommendations == {}

    async def test_pre_cancelled_token_scan_run_has_no_id(self) -> None:
        """Pre-cancelled ScanRun has no DB-assigned id (persist never ran)."""
        pipeline, mocks = _make_full_pipeline(tickers=["AAPL"])
        token = CancellationToken()
        token.cancel()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.scan_run.id is None
        mocks["repository"].save_scan_run.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 3: Cancelled between Phase 2 and Phase 3
# ---------------------------------------------------------------------------


class TestCancelledBetweenPhase2And3:
    """Cancel token set by progress callback when SCORING phase completes."""

    async def test_cancelled_after_phase2(self) -> None:
        """Token cancelled after Phase 2: scores populated, recommendations empty."""
        pipeline, mocks = _make_full_pipeline(tickers=["AAPL"])

        token = CancellationToken()

        # Monkey-patch _phase_scoring to cancel the token after it completes
        original_phase_scoring = pipeline._phase_scoring

        async def _scoring_then_cancel(
            universe_result: object,
            progress: object,
        ) -> object:
            result = await original_phase_scoring(universe_result, progress)  # type: ignore[arg-type]
            token.cancel()
            return result

        pipeline._phase_scoring = _scoring_then_cancel  # type: ignore[assignment]

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.cancelled is True
        assert result.phases_completed == 2
        assert len(result.scores) > 0
        assert result.recommendations == {}
        # FRED should not have been called (Phase 3 never ran)
        mocks["fred"].fetch_risk_free_rate.assert_not_awaited()

    async def test_cancelled_after_phase2_uses_fallback_rate(self) -> None:
        """When cancelled before Phase 3, risk_free_rate uses fallback."""
        settings = AppSettings()
        settings.pricing.risk_free_rate_fallback = 0.05
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        pipeline, _ = _make_full_pipeline(tickers=["AAPL"], settings=settings)

        token = CancellationToken()
        original_phase_scoring = pipeline._phase_scoring

        async def _scoring_then_cancel(
            universe_result: object,
            progress: object,
        ) -> object:
            result = await original_phase_scoring(universe_result, progress)  # type: ignore[arg-type]
            token.cancel()
            return result

        pipeline._phase_scoring = _scoring_then_cancel  # type: ignore[assignment]

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.risk_free_rate == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# Test 4: Empty universe (0 tickers)
# ---------------------------------------------------------------------------


class TestEmptyUniverse:
    """UniverseService returns empty ticker list."""

    async def test_empty_universe_completes_gracefully(self) -> None:
        """0 tickers from universe: pipeline completes all 4 phases, empty results."""
        pipeline, _mocks = _make_full_pipeline(
            tickers=[],
            batch_result=BatchOHLCVResult(results=[]),
        )
        token = CancellationToken()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.phases_completed == 4
        assert result.cancelled is False
        assert result.scores == []
        assert result.recommendations == {}
        assert result.scan_run.tickers_scanned == 0
        assert result.scan_run.tickers_scored == 0
        assert result.scan_run.recommendations == 0

    async def test_empty_universe_still_persists(self) -> None:
        """Even with 0 tickers, persist phase runs and saves the ScanRun."""
        pipeline, mocks = _make_full_pipeline(
            tickers=[],
            batch_result=BatchOHLCVResult(results=[]),
            save_scan_run_return=1,
        )
        token = CancellationToken()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        mocks["repository"].save_scan_run.assert_awaited_once()
        assert result.scan_run.id == 1


# ---------------------------------------------------------------------------
# Test 5: All tickers fail OHLCV
# ---------------------------------------------------------------------------


class TestAllTickersFailOHLCV:
    """All tickers fail OHLCV fetch — BatchOHLCVResult has all failures."""

    async def test_all_ohlcv_failures_produces_empty_results(self) -> None:
        """All OHLCV failures: empty ohlcv_map, empty scores, empty recommendations."""
        tickers = ["AAPL", "MSFT", "GOOG"]
        all_failed_batch = _make_batch_result(tickers, failed_tickers=set(tickers))

        pipeline, _ = _make_full_pipeline(
            tickers=tickers,
            batch_result=all_failed_batch,
        )
        token = CancellationToken()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.phases_completed == 4
        assert result.cancelled is False
        assert result.scores == []
        assert result.recommendations == {}
        assert result.scan_run.tickers_scanned == 3
        assert result.scan_run.tickers_scored == 0

    async def test_all_ohlcv_failures_no_crash(self) -> None:
        """Pipeline does not crash when all OHLCV fetches fail."""
        tickers = ["A", "B"]
        all_failed_batch = _make_batch_result(tickers, failed_tickers=set(tickers))

        pipeline, mocks = _make_full_pipeline(
            tickers=tickers,
            batch_result=all_failed_batch,
        )
        token = CancellationToken()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        # Pipeline completed without exception
        assert isinstance(result, ScanResult)
        # FRED still called (Phase 3 runs but has 0 tickers to process)
        mocks["fred"].fetch_risk_free_rate.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 6: ProgressCallback invocation order
# ---------------------------------------------------------------------------


class TestProgressCallbackOrder:
    """ProgressCallback is invoked in the correct phase order."""

    async def test_progress_phases_in_order(self) -> None:
        """Progress calls follow UNIVERSE -> SCORING -> OPTIONS -> PERSIST order."""
        progress_calls: list[tuple[ScanPhase, int, int]] = []

        def recording_progress(phase: ScanPhase, current: int, total: int) -> None:
            progress_calls.append((phase, current, total))

        pipeline, _ = _make_full_pipeline(tickers=["AAPL"])
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            await pipeline.run(ScanPreset.FULL, token, recording_progress)

        # Extract the unique phases in order of first appearance
        seen_phases: list[ScanPhase] = []
        for phase, _, _ in progress_calls:
            if not seen_phases or seen_phases[-1] != phase:
                seen_phases.append(phase)

        expected_order = [
            ScanPhase.UNIVERSE,
            ScanPhase.SCORING,
            ScanPhase.OPTIONS,
            ScanPhase.PERSIST,
        ]
        assert seen_phases == expected_order

    async def test_each_phase_has_start_and_end_callbacks(self) -> None:
        """Each phase has at least a start (0, total) and end (total, total) callback."""
        progress_calls: list[tuple[ScanPhase, int, int]] = []

        def recording_progress(phase: ScanPhase, current: int, total: int) -> None:
            progress_calls.append((phase, current, total))

        pipeline, _ = _make_full_pipeline(tickers=["AAPL"])
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            await pipeline.run(ScanPreset.FULL, token, recording_progress)

        # Group calls by phase
        phase_calls: dict[ScanPhase, list[tuple[int, int]]] = {}
        for phase, current, total in progress_calls:
            phase_calls.setdefault(phase, []).append((current, total))

        for phase in [
            ScanPhase.UNIVERSE,
            ScanPhase.SCORING,
            ScanPhase.OPTIONS,
            ScanPhase.PERSIST,
        ]:
            calls = phase_calls.get(phase, [])
            assert len(calls) >= 1, f"Phase {phase} had no progress callbacks"
            # Last call should be completion (current == total)
            last_current, last_total = calls[-1]
            assert last_current == last_total, (
                f"Phase {phase} last callback was ({last_current}, {last_total}) "
                f"— expected current == total"
            )


# ---------------------------------------------------------------------------
# Test 7: Re-export verification
# ---------------------------------------------------------------------------


class TestReExports:
    """All public names importable from options_arena.scan."""

    def test_all_public_names_importable(self) -> None:
        """All 5 public names are importable from options_arena.scan."""
        from options_arena.scan import (
            CancellationToken as CT,
        )
        from options_arena.scan import (
            ProgressCallback as PC,
        )
        from options_arena.scan import (
            ScanPhase as SP,
        )
        from options_arena.scan import (
            ScanPipeline as SPL,
        )
        from options_arena.scan import (
            ScanResult as SR,
        )

        assert CT is CancellationToken
        assert SP is ScanPhase
        assert SPL is ScanPipeline
        assert SR is ScanResult
        # ProgressCallback is a Protocol — verify it's a runtime-checkable type
        assert isinstance(PC, type)

    def test_all_matches_expected(self) -> None:
        """__all__ contains exactly the expected public names."""
        from options_arena.scan import __all__

        expected = {
            "CancellationToken",
            "ProgressCallback",
            "ScanPhase",
            "ScanPipeline",
            "ScanResult",
        }
        assert set(__all__) == expected


# ---------------------------------------------------------------------------
# Test 8: All tickers filtered by liquidity (Phase 3)
# ---------------------------------------------------------------------------


class TestAllFilteredByLiquidity:
    """All tickers filtered by liquidity pre-filter in Phase 3."""

    async def test_all_filtered_by_dollar_volume(self) -> None:
        """Tickers with low dollar volume produce empty recommendations."""
        settings = AppSettings()
        settings.scan.min_dollar_volume = 999_999_999_999.0  # Unreachably high
        settings.scan.min_price = 1.0

        pipeline, mocks = _make_full_pipeline(
            tickers=["AAPL", "MSFT"],
            settings=settings,
        )
        token = CancellationToken()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.phases_completed == 4
        assert result.cancelled is False
        assert result.recommendations == {}
        # Scores should still be populated from Phase 2
        assert len(result.scores) > 0
        # No options chains should have been fetched
        mocks["options_data"].fetch_chain_all_expirations.assert_not_awaited()

    async def test_all_filtered_by_price(self) -> None:
        """Tickers with low price produce empty recommendations."""
        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 999_999.0  # Unreachably high

        pipeline, _ = _make_full_pipeline(
            tickers=["AAPL"],
            settings=settings,
        )
        token = CancellationToken()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.phases_completed == 4
        assert result.recommendations == {}


# ---------------------------------------------------------------------------
# Test 9: FredService returns fallback rate
# ---------------------------------------------------------------------------


class TestFredFallbackRate:
    """FredService rate propagates correctly to ScanResult."""

    async def test_fred_rate_propagates_to_result(self) -> None:
        """The FRED rate is present on the final ScanResult."""
        pipeline, _ = _make_full_pipeline(tickers=["AAPL"], fred_rate=0.0385)
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.risk_free_rate == pytest.approx(0.0385)

    async def test_fred_called_exactly_once(self) -> None:
        """FredService.fetch_risk_free_rate is called exactly once per scan."""
        pipeline, mocks = _make_full_pipeline(tickers=["AAPL", "MSFT", "GOOG"])
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        mocks["fred"].fetch_risk_free_rate.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 10: Result type validation
# ---------------------------------------------------------------------------


class TestResultTypeValidation:
    """ScanResult is a well-formed Pydantic model at all boundaries."""

    async def test_result_is_scan_result_type(self) -> None:
        """run() returns a ScanResult instance."""
        pipeline, _ = _make_full_pipeline(tickers=["AAPL"])
        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert isinstance(result, ScanResult)

    async def test_cancelled_result_is_scan_result_type(self) -> None:
        """Even a cancelled run returns a ScanResult."""
        pipeline, _ = _make_full_pipeline(tickers=["AAPL"])
        token = CancellationToken()
        token.cancel()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert isinstance(result, ScanResult)
        assert result.cancelled is True
