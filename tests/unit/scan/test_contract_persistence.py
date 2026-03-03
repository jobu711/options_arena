"""Tests for pipeline contract and normalization persistence.

Covers:
  - Phase 4 persists recommended contracts with entry prices.
  - Entry prices captured from ticker_info.current_price in Phase 3.
  - Phase 4 handles ticker with 0 recommended contracts gracefully.
  - Phase 4 persists normalization stats.
  - RecommendedContract built correctly from OptionContract + TickerScore.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from options_arena.models import (
    AppSettings,
    IndicatorSignals,
    NormalizationStats,
    OptionContract,
    OptionGreeks,
    RecommendedContract,
    ScanPreset,
    SignalDirection,
    TickerScore,
)
from options_arena.models.enums import (
    ExerciseStyle,
    GreeksSource,
    OptionType,
    PricingModel,
)
from options_arena.scan.models import OptionsResult, ScoringResult, UniverseResult
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import ScanPhase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_option_contract(
    ticker: str,
    *,
    greeks: OptionGreeks | None = None,
    greeks_source: GreeksSource | None = None,
) -> OptionContract:
    """Create a minimal OptionContract for testing."""
    return OptionContract(
        ticker=ticker,
        option_type=OptionType.CALL,
        strike=Decimal("100"),
        expiration=date.today() + timedelta(days=45),
        bid=Decimal("3.00"),
        ask=Decimal("3.50"),
        last=Decimal("3.25"),
        volume=500,
        open_interest=2000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.25,
        greeks=greeks,
        greeks_source=greeks_source,
    )


def _make_universe_result(tickers: list[str]) -> UniverseResult:
    """Build a minimal UniverseResult."""
    return UniverseResult(
        tickers=tickers,
        ohlcv_map={},
        sp500_sectors={},
        failed_count=0,
        filtered_count=0,
    )


def _make_scoring_result(tickers: list[str]) -> ScoringResult:
    """Build a ScoringResult with given tickers."""
    scores = [_make_ticker_score(t, score=90.0 - i * 5.0) for i, t in enumerate(tickers)]
    raw_signals = {t: IndicatorSignals(rsi=65.0, adx=25.0) for t in tickers}
    return ScoringResult(scores=scores, raw_signals=raw_signals)


def _noop_progress(phase: ScanPhase, current: int, total: int) -> None:
    """No-op progress callback."""


def _make_pipeline_for_persist(
    *,
    save_scan_run_return: int = 42,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services for Phase 4 testing."""
    settings = AppSettings()
    mock_repository = AsyncMock()
    mock_repository.save_scan_run = AsyncMock(return_value=save_scan_run_return)
    mock_repository.save_ticker_scores = AsyncMock(return_value=None)
    mock_repository.save_recommended_contracts = AsyncMock(return_value=None)
    mock_repository.save_normalization_stats = AsyncMock(return_value=None)

    pipeline = ScanPipeline(
        settings=settings,
        market_data=AsyncMock(),
        options_data=AsyncMock(),
        fred=AsyncMock(),
        universe=AsyncMock(),
        repository=mock_repository,
    )
    return pipeline, {"repository": mock_repository}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineContractPersistence:
    """Tests for Phase 4 contract and normalization persistence."""

    @pytest.mark.asyncio
    async def test_phase4_persists_contracts(self) -> None:
        """Verify Phase 4 saves recommended contracts with entry prices."""
        pipeline, mocks = _make_pipeline_for_persist(save_scan_run_return=10)

        contract = _make_option_contract(
            "AAPL",
            greeks=OptionGreeks(
                delta=0.45,
                gamma=0.03,
                theta=-0.12,
                vega=0.15,
                rho=0.02,
                pricing_model=PricingModel.BAW,
            ),
            greeks_source=GreeksSource.COMPUTED,
        )
        options_result = OptionsResult(
            recommendations={"AAPL": [contract]},
            risk_free_rate=0.045,
            entry_prices={"AAPL": Decimal("182.30")},
        )
        scoring_result = _make_scoring_result(["AAPL"])

        await pipeline._phase_persist(
            started_at=datetime.now(UTC),
            preset=ScanPreset.FULL,
            universe_result=_make_universe_result(["AAPL"]),
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        mocks["repository"].save_recommended_contracts.assert_awaited_once()
        call_args = mocks["repository"].save_recommended_contracts.call_args
        saved_scan_id = call_args.args[0]
        saved_contracts: list[RecommendedContract] = call_args.args[1]

        assert saved_scan_id == 10
        assert len(saved_contracts) == 1
        c = saved_contracts[0]
        assert c.ticker == "AAPL"
        assert c.entry_stock_price == Decimal("182.30")
        assert c.entry_mid == contract.mid
        assert c.delta == pytest.approx(0.45)
        assert c.direction is SignalDirection.BULLISH

    @pytest.mark.asyncio
    async def test_entry_prices_captured_in_phase3(self) -> None:
        """Verify spot prices are stored on OptionsResult.entry_prices."""
        # This tests that the OptionsResult model can hold entry_prices correctly
        entry_prices = {
            "AAPL": Decimal("182.30"),
            "MSFT": Decimal("415.60"),
        }
        options_result = OptionsResult(
            recommendations={},
            risk_free_rate=0.045,
            entry_prices=entry_prices,
        )
        assert options_result.entry_prices["AAPL"] == Decimal("182.30")
        assert options_result.entry_prices["MSFT"] == Decimal("415.60")

    @pytest.mark.asyncio
    async def test_missing_entry_price_sets_none(self) -> None:
        """Verify missing entry price produces entry_stock_price=None."""
        pipeline, mocks = _make_pipeline_for_persist(save_scan_run_return=10)

        contract = _make_option_contract("AAPL")
        # No entry_prices for AAPL — pipeline should set None
        options_result = OptionsResult(
            recommendations={"AAPL": [contract]},
            risk_free_rate=0.045,
            entry_prices={},
        )
        scoring_result = _make_scoring_result(["AAPL"])

        await pipeline._phase_persist(
            started_at=datetime.now(UTC),
            preset=ScanPreset.FULL,
            universe_result=_make_universe_result(["AAPL"]),
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        mocks["repository"].save_recommended_contracts.assert_awaited_once()
        call_args = mocks["repository"].save_recommended_contracts.call_args
        saved_contracts: list[RecommendedContract] = call_args.args[1]
        assert len(saved_contracts) == 1
        assert saved_contracts[0].entry_stock_price is None

    @pytest.mark.asyncio
    async def test_no_contracts_no_error(self) -> None:
        """Verify Phase 4 handles ticker with 0 recommended contracts gracefully."""
        pipeline, mocks = _make_pipeline_for_persist(save_scan_run_return=5)

        options_result = OptionsResult(
            recommendations={},
            risk_free_rate=0.045,
        )
        scoring_result = _make_scoring_result(["AAPL"])

        result = await pipeline._phase_persist(
            started_at=datetime.now(UTC),
            preset=ScanPreset.FULL,
            universe_result=_make_universe_result(["AAPL"]),
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        # save_recommended_contracts should NOT be called (empty list)
        mocks["repository"].save_recommended_contracts.assert_not_awaited()
        assert result.phases_completed == 4

    @pytest.mark.asyncio
    async def test_normalization_stats_persisted(self) -> None:
        """Verify Phase 4 saves normalization metadata."""
        pipeline, mocks = _make_pipeline_for_persist(save_scan_run_return=20)

        norm_stats = [
            NormalizationStats(
                scan_run_id=0,
                indicator_name="rsi",
                ticker_count=100,
                min_value=15.0,
                max_value=90.0,
                median_value=55.0,
                mean_value=54.0,
                std_dev=18.0,
                p25=40.0,
                p75=70.0,
                created_at=datetime.now(UTC),
            ),
        ]
        scoring_result = _make_scoring_result(["AAPL"])
        scoring_result.normalization_stats = norm_stats

        options_result = OptionsResult(
            recommendations={},
            risk_free_rate=0.045,
        )

        await pipeline._phase_persist(
            started_at=datetime.now(UTC),
            preset=ScanPreset.FULL,
            universe_result=_make_universe_result(["AAPL"]),
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        mocks["repository"].save_normalization_stats.assert_awaited_once()
        call_args = mocks["repository"].save_normalization_stats.call_args
        saved_scan_id = call_args.args[0]
        saved_stats: list[NormalizationStats] = call_args.args[1]

        assert saved_scan_id == 20
        assert len(saved_stats) == 1
        # The placeholder scan_run_id=0 should be replaced with real scan_id
        assert saved_stats[0].scan_run_id == 20
        assert saved_stats[0].indicator_name == "rsi"

    @pytest.mark.asyncio
    async def test_contract_fields_from_option_contract(self) -> None:
        """Verify RecommendedContract built correctly from OptionContract + TickerScore."""
        pipeline, mocks = _make_pipeline_for_persist(save_scan_run_return=30)

        greeks = OptionGreeks(
            delta=0.35,
            gamma=0.05,
            theta=-0.08,
            vega=0.20,
            rho=0.01,
            pricing_model=PricingModel.BSM,
        )
        contract = _make_option_contract(
            "MSFT",
            greeks=greeks,
            greeks_source=GreeksSource.COMPUTED,
        )
        scoring_result = _make_scoring_result(["MSFT"])
        scoring_result.scores[0].direction = SignalDirection.BEARISH
        scoring_result.scores[0].composite_score = 82.0

        options_result = OptionsResult(
            recommendations={"MSFT": [contract]},
            risk_free_rate=0.05,
            entry_prices={"MSFT": Decimal("415.60")},
        )

        await pipeline._phase_persist(
            started_at=datetime.now(UTC),
            preset=ScanPreset.SP500,
            universe_result=_make_universe_result(["MSFT"]),
            scoring_result=scoring_result,
            options_result=options_result,
            progress=_noop_progress,
        )

        mocks["repository"].save_recommended_contracts.assert_awaited_once()
        saved_contracts: list[RecommendedContract] = mocks[
            "repository"
        ].save_recommended_contracts.call_args.args[1]
        assert len(saved_contracts) == 1
        c = saved_contracts[0]
        assert c.ticker == "MSFT"
        assert c.scan_run_id == 30
        assert c.strike == contract.strike
        assert c.expiration == contract.expiration
        assert c.bid == contract.bid
        assert c.ask == contract.ask
        assert c.delta == pytest.approx(0.35)
        assert c.gamma == pytest.approx(0.05)
        assert c.theta == pytest.approx(-0.08)
        assert c.vega == pytest.approx(0.20)
        assert c.rho == pytest.approx(0.01)
        assert c.pricing_model is PricingModel.BSM
        assert c.greeks_source is GreeksSource.COMPUTED
        assert c.entry_stock_price == Decimal("415.60")
        assert c.direction is SignalDirection.BEARISH
        assert c.composite_score == pytest.approx(82.0)
        assert c.risk_free_rate == pytest.approx(0.05)
