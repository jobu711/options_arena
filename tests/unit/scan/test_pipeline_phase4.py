"""Tests for ScanPipeline Phase 4 — Persist + Full Run.

Covers:
  - ScanRun built with UTC timestamps.
  - repository.save_scan_run called with correct ScanRun.
  - repository.save_ticker_scores called with scan_id.
  - scan_run.id populated after save.
  - Recommendations count correct.
  - Cancellation between Phase 3 and Phase 4 returns partial result.
  - Full 4-phase run with mock services.
  - Progress callback invoked with ScanPhase.PERSIST.
  - scan/__init__.py re-exports ScanPipeline and ScanResult.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
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
from options_arena.models.enums import DividendSource, ExerciseStyle, OptionType
from options_arena.models.market_data import OHLCV, TickerInfo
from options_arena.scan.models import (
    OptionsResult,
    ScoringResult,
    UniverseResult,
)
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import CancellationToken, ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult
from options_arena.services.options_data import ExpirationChain

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_bars(
    ticker: str,
    n: int = 300,
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


def _make_options_result(
    recommendations: dict[str, list[OptionContract]] | None = None,
    risk_free_rate: float = 0.045,
) -> OptionsResult:
    """Build an OptionsResult."""
    return OptionsResult(
        recommendations=recommendations or {},
        risk_free_rate=risk_free_rate,
    )


def _noop_progress(phase: ScanPhase, current: int, total: int) -> None:
    """No-op progress callback."""


def _make_pipeline_for_persist(
    *,
    settings: AppSettings | None = None,
    save_scan_run_return: int = 42,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services focused on Phase 4 testing."""
    _settings = settings or AppSettings()

    mock_universe = AsyncMock()
    mock_market_data = AsyncMock()
    mock_options_data = AsyncMock()
    mock_fred = AsyncMock()
    mock_repository = AsyncMock()

    # Repository: save_scan_run returns the DB-assigned ID
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
# Phase 4 (Persist) tests
# ---------------------------------------------------------------------------


class TestPhasePersist:
    """Phase 4 persists scan results to the database."""

    async def test_scan_run_has_utc_timestamps(self) -> None:
        """ScanRun built in Phase 4 has UTC timestamps."""
        pipeline, _mocks = _make_pipeline_for_persist(save_scan_run_return=1)

        started_at = datetime.now(UTC)
        universe_result = _make_universe_result(["AAPL"])
        scoring_result = _make_scoring_result(["AAPL"])
        options_result = _make_options_result()

        result = await pipeline._phase_persist(
            started_at=started_at,
            preset=ScanPreset.FULL,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        assert result.scan_run.started_at.tzinfo is not None
        assert result.scan_run.started_at.utcoffset() == timedelta(0)
        assert result.scan_run.completed_at is not None
        assert result.scan_run.completed_at.utcoffset() == timedelta(0)  # type: ignore[union-attr]

    async def test_save_scan_run_called(self) -> None:
        """repository.save_scan_run is called with a ScanRun."""
        pipeline, mocks = _make_pipeline_for_persist(save_scan_run_return=7)

        started_at = datetime.now(UTC)
        universe_result = _make_universe_result(["AAPL", "MSFT"])
        scoring_result = _make_scoring_result(["AAPL", "MSFT"])
        options_result = _make_options_result(
            recommendations={"AAPL": [_make_option_contract("AAPL")]}
        )

        await pipeline._phase_persist(
            started_at=started_at,
            preset=ScanPreset.SP500,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        mocks["repository"].save_scan_run.assert_awaited_once()
        saved_run = mocks["repository"].save_scan_run.call_args.args[0]
        assert saved_run.preset == ScanPreset.SP500
        assert saved_run.tickers_scanned == 2
        assert saved_run.tickers_scored == 2
        assert saved_run.recommendations == 1

    async def test_save_ticker_scores_called_with_scan_id(self) -> None:
        """repository.save_ticker_scores called with the DB-assigned scan ID."""
        pipeline, mocks = _make_pipeline_for_persist(save_scan_run_return=99)

        started_at = datetime.now(UTC)
        universe_result = _make_universe_result(["AAPL"])
        scoring_result = _make_scoring_result(["AAPL"])
        options_result = _make_options_result()

        await pipeline._phase_persist(
            started_at=started_at,
            preset=ScanPreset.FULL,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        mocks["repository"].save_ticker_scores.assert_awaited_once()
        call_args = mocks["repository"].save_ticker_scores.call_args
        assert call_args.args[0] == 99  # scan_id

    async def test_scan_run_id_populated_after_save(self) -> None:
        """The returned ScanResult has scan_run.id set from the database."""
        pipeline, _ = _make_pipeline_for_persist(save_scan_run_return=42)

        started_at = datetime.now(UTC)
        universe_result = _make_universe_result(["AAPL"])
        scoring_result = _make_scoring_result(["AAPL"])
        options_result = _make_options_result()

        result = await pipeline._phase_persist(
            started_at=started_at,
            preset=ScanPreset.FULL,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        assert result.scan_run.id == 42

    async def test_recommendations_count_correct(self) -> None:
        """ScanRun.recommendations reflects total contracts across all tickers."""
        pipeline, _mocks = _make_pipeline_for_persist(save_scan_run_return=1)

        started_at = datetime.now(UTC)
        universe_result = _make_universe_result(["AAPL", "MSFT"])
        scoring_result = _make_scoring_result(["AAPL", "MSFT"])
        options_result = _make_options_result(
            recommendations={
                "AAPL": [_make_option_contract("AAPL")],
                "MSFT": [_make_option_contract("MSFT")],
            }
        )

        result = await pipeline._phase_persist(
            started_at=started_at,
            preset=ScanPreset.FULL,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        assert result.scan_run.recommendations == 2

    async def test_ticker_scores_scan_run_id_updated(self) -> None:
        """Each TickerScore's scan_run_id is set to the DB-assigned ID."""
        pipeline, _ = _make_pipeline_for_persist(save_scan_run_return=77)

        started_at = datetime.now(UTC)
        universe_result = _make_universe_result(["AAPL", "MSFT"])
        scoring_result = _make_scoring_result(["AAPL", "MSFT"])
        options_result = _make_options_result()

        result = await pipeline._phase_persist(
            started_at=started_at,
            preset=ScanPreset.FULL,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        for ts in result.scores:
            assert ts.scan_run_id == 77

    async def test_progress_callback_invoked_with_persist_phase(self) -> None:
        """Progress callback called with ScanPhase.PERSIST."""
        progress_calls: list[tuple[ScanPhase, int, int]] = []

        def recording_progress(phase: ScanPhase, current: int, total: int) -> None:
            progress_calls.append((phase, current, total))

        pipeline, _ = _make_pipeline_for_persist(save_scan_run_return=1)

        started_at = datetime.now(UTC)
        universe_result = _make_universe_result(["AAPL"])
        scoring_result = _make_scoring_result(["AAPL"])
        options_result = _make_options_result()

        await pipeline._phase_persist(
            started_at=started_at,
            preset=ScanPreset.FULL,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=recording_progress,
        )

        persist_calls = [c for c in progress_calls if c[0] == ScanPhase.PERSIST]
        assert len(persist_calls) >= 1
        assert persist_calls[0] == (ScanPhase.PERSIST, 1, 1)


class TestPhase4Cancellation:
    """Cancellation between Phase 3 and Phase 4."""

    async def test_cancelled_after_phase3_returns_partial_result(self) -> None:
        """Cancellation after Phase 3 includes options data but no persist."""
        tickers = ["AAPL"]
        batch = BatchOHLCVResult(
            results=[
                TickerOHLCVResult(
                    ticker="AAPL",
                    data=_make_ohlcv_bars("AAPL", n=300, close_price=100.0),
                )
            ]
        )

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])

        mock_market_data = AsyncMock()
        mock_market_data.fetch_batch_ohlcv = AsyncMock(return_value=batch)
        mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info("AAPL"))

        mock_options_data = AsyncMock()
        mock_options_data.fetch_chain_all_expirations = AsyncMock(
            return_value=[_make_expiration_chain("AAPL")]
        )

        mock_fred = AsyncMock()
        mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

        mock_repository = AsyncMock()
        mock_repository.save_scan_run = AsyncMock(return_value=1)

        pipeline = ScanPipeline(
            settings=settings,
            market_data=mock_market_data,
            options_data=mock_options_data,
            fred=mock_fred,
            universe=mock_universe,
            repository=mock_repository,
        )

        # Patch _phase_options to cancel the token right after it completes
        original_phase_options = pipeline._phase_options

        async def _options_then_cancel(
            scoring_result: ScoringResult,
            universe_result: UniverseResult,
            progress: object,
        ) -> OptionsResult:
            # Mock recommend_contracts to return something
            with patch(
                "options_arena.scan.pipeline.recommend_contracts",
                return_value=[_make_option_contract("AAPL")],
            ):
                result = await original_phase_options(scoring_result, universe_result, progress)  # type: ignore[arg-type]
            token.cancel()
            return result

        pipeline._phase_options = _options_then_cancel  # type: ignore[assignment]

        token = CancellationToken()

        result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.cancelled is True
        assert result.phases_completed == 3
        # Repository should NOT have been called (Phase 4 skipped)
        mock_repository.save_scan_run.assert_not_awaited()


# ---------------------------------------------------------------------------
# Full 4-phase run integration tests
# ---------------------------------------------------------------------------


class TestFullPipelineRun:
    """Full 4-phase pipeline run with mock services."""

    async def test_full_run_completes_4_phases(self) -> None:
        """A full uncancelled run completes with phases_completed=4."""
        tickers = ["AAPL"]
        batch = BatchOHLCVResult(
            results=[
                TickerOHLCVResult(
                    ticker="AAPL",
                    data=_make_ohlcv_bars("AAPL", n=300, close_price=100.0),
                )
            ]
        )

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])

        mock_market_data = AsyncMock()
        mock_market_data.fetch_batch_ohlcv = AsyncMock(return_value=batch)
        mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info("AAPL"))

        mock_options_data = AsyncMock()
        mock_options_data.fetch_chain_all_expirations = AsyncMock(
            return_value=[_make_expiration_chain("AAPL")]
        )

        mock_fred = AsyncMock()
        mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.045)

        mock_repository = AsyncMock()
        mock_repository.save_scan_run = AsyncMock(return_value=10)
        mock_repository.save_ticker_scores = AsyncMock(return_value=None)

        pipeline = ScanPipeline(
            settings=settings,
            market_data=mock_market_data,
            options_data=mock_options_data,
            fred=mock_fred,
            universe=mock_universe,
            repository=mock_repository,
        )

        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("AAPL")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.phases_completed == 4
        assert result.cancelled is False
        assert result.scan_run.id == 10
        assert result.risk_free_rate == pytest.approx(0.045)
        assert len(result.scores) > 0

        # Verify all service calls happened
        mock_fred.fetch_risk_free_rate.assert_awaited_once()
        mock_repository.save_scan_run.assert_awaited_once()
        mock_repository.save_ticker_scores.assert_awaited_once()

    async def test_full_run_scan_run_metadata(self) -> None:
        """Full run produces correct ScanRun metadata."""
        tickers = ["AAPL", "MSFT"]
        batch = BatchOHLCVResult(
            results=[
                TickerOHLCVResult(
                    ticker=t,
                    data=_make_ohlcv_bars(t, n=300, close_price=100.0),
                )
                for t in tickers
            ]
        )

        settings = AppSettings()
        settings.scan.min_dollar_volume = 1.0
        settings.scan.min_price = 1.0

        mock_universe = AsyncMock()
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])

        mock_market_data = AsyncMock()
        mock_market_data.fetch_batch_ohlcv = AsyncMock(return_value=batch)
        mock_market_data.fetch_ticker_info = AsyncMock(side_effect=lambda t: _make_ticker_info(t))

        mock_options_data = AsyncMock()
        mock_options_data.fetch_chain_all_expirations = AsyncMock(
            side_effect=lambda t: [_make_expiration_chain(t)]
        )

        mock_fred = AsyncMock()
        mock_fred.fetch_risk_free_rate = AsyncMock(return_value=0.04)

        mock_repository = AsyncMock()
        mock_repository.save_scan_run = AsyncMock(return_value=5)
        mock_repository.save_ticker_scores = AsyncMock(return_value=None)

        pipeline = ScanPipeline(
            settings=settings,
            market_data=mock_market_data,
            options_data=mock_options_data,
            fred=mock_fred,
            universe=mock_universe,
            repository=mock_repository,
        )

        token = CancellationToken()

        with patch(
            "options_arena.scan.pipeline.recommend_contracts",
            return_value=[_make_option_contract("X")],
        ):
            result = await pipeline.run(ScanPreset.FULL, token, _noop_progress)

        assert result.scan_run.tickers_scanned == 2
        assert result.scan_run.tickers_scored > 0
        assert result.scan_run.started_at <= result.scan_run.completed_at  # type: ignore[operator]
        assert result.scan_run.preset == ScanPreset.FULL


# ---------------------------------------------------------------------------
# Re-export tests
# ---------------------------------------------------------------------------


class TestScanReExports:
    """scan/__init__.py re-exports ScanPipeline and ScanResult."""

    def test_scan_pipeline_importable(self) -> None:
        """ScanPipeline can be imported from options_arena.scan."""
        from options_arena.scan import ScanPipeline as Imported

        assert Imported is ScanPipeline

    def test_scan_result_importable(self) -> None:
        """ScanResult can be imported from options_arena.scan."""
        from options_arena.scan import ScanResult

        assert ScanResult is not None

    def test_all_exports(self) -> None:
        """__all__ contains all expected public names."""
        from options_arena.scan import __all__

        expected = {
            "CancellationToken",
            "ProgressCallback",
            "ScanPhase",
            "ScanPipeline",
            "ScanResult",
        }
        assert set(__all__) == expected
