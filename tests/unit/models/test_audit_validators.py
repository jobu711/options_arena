"""Tests for model audit fixes — validator gaps found during comprehensive audit.

Covers:
  1. TickerInfo: Decimal price field validators (current_price, 52w high/low)
  2. ScanRun: count field non-negative validators
  3. RecommendedContract: market_iv >= 0, composite_score [0, 100]
  4. ContractOutcome: holding_days/dte_at_exit non-negative validators
  5. Analytics result models: int count field validators
  6. MarketContext: contract_mid Decimal finite validator
"""

import math
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models import (
    ContractOutcome,
    DeltaPerformanceResult,
    HoldingPeriodResult,
    IndicatorAttributionResult,
    PerformanceSummary,
    RecommendedContract,
    ScoreCalibrationBucket,
    TickerInfo,
    WinRateResult,
)
from options_arena.models.enums import (
    DividendSource,
    ExerciseStyle,
    MacdSignal,
    OptionType,
    OutcomeCollectionMethod,
    ScanPreset,
    ScanSource,
    SignalDirection,
)
from options_arena.models.scan import ScanRun

NOW_UTC = datetime.now(UTC)


# ---------------------------------------------------------------------------
# 1. TickerInfo — Decimal price validators
# ---------------------------------------------------------------------------


class TestTickerInfoPriceValidators:
    """TickerInfo.current_price, fifty_two_week_high, fifty_two_week_low."""

    def _valid_ticker_info(self, **overrides: object) -> TickerInfo:
        defaults: dict[str, object] = {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "sector": "Information Technology",
            "current_price": Decimal("185.50"),
            "fifty_two_week_high": Decimal("200.00"),
            "fifty_two_week_low": Decimal("140.00"),
        }
        defaults.update(overrides)
        return TickerInfo(**defaults)  # type: ignore[arg-type]

    def test_construction_happy_path(self) -> None:
        ti = self._valid_ticker_info()
        assert ti.current_price == Decimal("185.50")
        assert ti.fifty_two_week_high == Decimal("200.00")
        assert ti.fifty_two_week_low == Decimal("140.00")

    def test_rejects_zero_current_price(self) -> None:
        with pytest.raises(ValidationError, match="finite and positive"):
            self._valid_ticker_info(current_price=Decimal("0"))

    def test_rejects_negative_52w_high(self) -> None:
        with pytest.raises(ValidationError, match="finite and positive"):
            self._valid_ticker_info(fifty_two_week_high=Decimal("-10"))

    def test_rejects_nan_52w_low(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            self._valid_ticker_info(fifty_two_week_low=Decimal("NaN"))

    def test_rejects_inf_current_price(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            self._valid_ticker_info(current_price=Decimal("Infinity"))

    def test_serialization_roundtrip(self) -> None:
        ti = self._valid_ticker_info()
        restored = TickerInfo.model_validate_json(ti.model_dump_json())
        assert restored == ti


# ---------------------------------------------------------------------------
# 2. ScanRun — count field validators
# ---------------------------------------------------------------------------


class TestScanRunCountValidators:
    """ScanRun.tickers_scanned, tickers_scored, recommendations."""

    def _valid_scan_run(self, **overrides: object) -> ScanRun:
        defaults: dict[str, object] = {
            "started_at": NOW_UTC,
            "preset": ScanPreset.SP500,
            "source": ScanSource.MANUAL,
            "tickers_scanned": 100,
            "tickers_scored": 50,
            "recommendations": 10,
        }
        defaults.update(overrides)
        return ScanRun(**defaults)  # type: ignore[arg-type]

    def test_construction_happy_path(self) -> None:
        sr = self._valid_scan_run()
        assert sr.tickers_scanned == 100
        assert sr.tickers_scored == 50
        assert sr.recommendations == 10

    def test_allows_zero_counts(self) -> None:
        sr = self._valid_scan_run(tickers_scanned=0, tickers_scored=0, recommendations=0)
        assert sr.tickers_scanned == 0

    def test_rejects_negative_tickers_scanned(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 0"):
            self._valid_scan_run(tickers_scanned=-1)

    def test_rejects_negative_tickers_scored(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 0"):
            self._valid_scan_run(tickers_scored=-1)

    def test_rejects_negative_recommendations(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 0"):
            self._valid_scan_run(recommendations=-1)


# ---------------------------------------------------------------------------
# 3. RecommendedContract — market_iv and composite_score bounds
# ---------------------------------------------------------------------------


class TestRecommendedContractBounds:
    """RecommendedContract.market_iv >= 0, composite_score in [0, 100]."""

    def _valid_rec(self, **overrides: object) -> RecommendedContract:
        defaults: dict[str, object] = {
            "scan_run_id": 1,
            "ticker": "AAPL",
            "option_type": OptionType.CALL,
            "strike": Decimal("185.00"),
            "bid": Decimal("3.00"),
            "ask": Decimal("3.50"),
            "expiration": date(2026, 4, 17),
            "volume": 1000,
            "open_interest": 5000,
            "market_iv": 0.35,
            "exercise_style": ExerciseStyle.AMERICAN,
            "entry_mid": Decimal("3.25"),
            "direction": SignalDirection.BULLISH,
            "composite_score": 75.0,
            "risk_free_rate": 0.05,
            "created_at": NOW_UTC,
        }
        defaults.update(overrides)
        return RecommendedContract(**defaults)  # type: ignore[arg-type]

    def test_construction_happy_path(self) -> None:
        rc = self._valid_rec()
        assert rc.market_iv == 0.35
        assert rc.composite_score == 75.0

    def test_rejects_negative_market_iv(self) -> None:
        with pytest.raises(ValidationError, match="market_iv must be >= 0"):
            self._valid_rec(market_iv=-0.1)

    def test_rejects_nan_market_iv(self) -> None:
        with pytest.raises(ValidationError, match="market_iv must be finite"):
            self._valid_rec(market_iv=float("nan"))

    def test_rejects_composite_score_above_100(self) -> None:
        with pytest.raises(ValidationError, match="composite_score must be in"):
            self._valid_rec(composite_score=101.0)

    def test_rejects_negative_composite_score(self) -> None:
        with pytest.raises(ValidationError, match="composite_score must be in"):
            self._valid_rec(composite_score=-1.0)

    def test_allows_zero_market_iv(self) -> None:
        rc = self._valid_rec(market_iv=0.0)
        assert rc.market_iv == 0.0

    def test_allows_boundary_composite_scores(self) -> None:
        rc0 = self._valid_rec(composite_score=0.0)
        rc100 = self._valid_rec(composite_score=100.0)
        assert rc0.composite_score == 0.0
        assert rc100.composite_score == 100.0


# ---------------------------------------------------------------------------
# 4. ContractOutcome — holding_days and dte_at_exit
# ---------------------------------------------------------------------------


class TestContractOutcomeIntValidators:
    """ContractOutcome.holding_days, dte_at_exit non-negative."""

    def _valid_outcome(self, **overrides: object) -> ContractOutcome:
        defaults: dict[str, object] = {
            "recommended_contract_id": 1,
            "collection_method": OutcomeCollectionMethod.MARKET,
            "collected_at": NOW_UTC,
        }
        defaults.update(overrides)
        return ContractOutcome(**defaults)  # type: ignore[arg-type]

    def test_allows_none_holding_days(self) -> None:
        co = self._valid_outcome()
        assert co.holding_days is None

    def test_allows_zero_holding_days(self) -> None:
        co = self._valid_outcome(holding_days=0)
        assert co.holding_days == 0

    def test_rejects_negative_holding_days(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 0"):
            self._valid_outcome(holding_days=-1)

    def test_rejects_negative_dte_at_exit(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 0"):
            self._valid_outcome(dte_at_exit=-5)

    def test_allows_zero_dte_at_exit(self) -> None:
        co = self._valid_outcome(dte_at_exit=0)
        assert co.dte_at_exit == 0


# ---------------------------------------------------------------------------
# 5. Analytics result models — count field validators
# ---------------------------------------------------------------------------


class TestAnalyticsCountValidators:
    """WinRateResult, ScoreCalibrationBucket, etc. — int count validators."""

    def test_win_rate_rejects_negative_total(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 0"):
            WinRateResult(
                direction=SignalDirection.BULLISH,
                total_contracts=-1,
                winners=0,
                losers=0,
                win_rate=0.0,
            )

    def test_win_rate_rejects_negative_winners(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 0"):
            WinRateResult(
                direction=SignalDirection.BULLISH,
                total_contracts=10,
                winners=-1,
                losers=0,
                win_rate=0.0,
            )

    def test_score_calibration_rejects_negative_count(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 0"):
            ScoreCalibrationBucket(
                score_min=0.0,
                score_max=10.0,
                contract_count=-1,
                avg_return_pct=5.0,
                win_rate=0.5,
            )

    def test_indicator_attribution_rejects_zero_sample(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 1"):
            IndicatorAttributionResult(
                indicator_name="rsi",
                holding_days=5,
                correlation=0.5,
                avg_return_when_high=2.0,
                avg_return_when_low=-1.0,
                sample_size=0,
            )

    def test_holding_period_rejects_zero_holding_days(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 1"):
            HoldingPeriodResult(
                holding_days=0,
                direction=SignalDirection.BULLISH,
                avg_return_pct=3.0,
                median_return_pct=2.0,
                win_rate=0.6,
                sample_size=10,
            )

    def test_delta_performance_rejects_zero_sample(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 1"):
            DeltaPerformanceResult(
                delta_min=0.2,
                delta_max=0.4,
                holding_days=5,
                avg_return_pct=3.0,
                win_rate=0.6,
                sample_size=0,
            )

    def test_performance_summary_rejects_negative_total(self) -> None:
        with pytest.raises(ValidationError, match="must be >= 0"):
            PerformanceSummary(
                lookback_days=30,
                total_contracts=-1,
                total_with_outcomes=0,
            )

    def test_performance_summary_rejects_zero_lookback(self) -> None:
        with pytest.raises(ValidationError, match="lookback_days must be >= 1"):
            PerformanceSummary(
                lookback_days=0,
                total_contracts=10,
                total_with_outcomes=5,
            )


# ---------------------------------------------------------------------------
# 6. MarketContext — contract_mid Decimal finite validator
# ---------------------------------------------------------------------------


class TestMarketContextContractMid:
    """MarketContext.contract_mid Decimal finite validator."""

    def _base_kwargs(self) -> dict[str, object]:
        return {
            "ticker": "AAPL",
            "current_price": Decimal("185.50"),
            "price_52w_high": Decimal("200.00"),
            "price_52w_low": Decimal("140.00"),
            "macd_signal": MacdSignal.NEUTRAL,
            "next_earnings": None,
            "dte_target": 45,
            "target_strike": Decimal("190.00"),
            "target_delta": 0.35,
            "sector": "Information Technology",
            "dividend_yield": 0.005,
            "exercise_style": ExerciseStyle.AMERICAN,
            "data_timestamp": NOW_UTC,
        }

    def test_allows_none_contract_mid(self) -> None:
        from options_arena.models.analysis import MarketContext

        mc = MarketContext(**self._base_kwargs())  # type: ignore[arg-type]
        assert mc.contract_mid is None

    def test_allows_finite_contract_mid(self) -> None:
        from options_arena.models.analysis import MarketContext

        kwargs = self._base_kwargs()
        kwargs["contract_mid"] = Decimal("3.25")
        mc = MarketContext(**kwargs)  # type: ignore[arg-type]
        assert mc.contract_mid == Decimal("3.25")

    def test_rejects_nan_contract_mid(self) -> None:
        from options_arena.models.analysis import MarketContext

        kwargs = self._base_kwargs()
        kwargs["contract_mid"] = Decimal("NaN")
        with pytest.raises(ValidationError, match="finite"):
            MarketContext(**kwargs)  # type: ignore[arg-type]

    def test_rejects_inf_contract_mid(self) -> None:
        from options_arena.models.analysis import MarketContext

        kwargs = self._base_kwargs()
        kwargs["contract_mid"] = Decimal("Infinity")
        with pytest.raises(ValidationError, match="finite"):
            MarketContext(**kwargs)  # type: ignore[arg-type]

    def test_serialization_roundtrip_with_contract_mid(self) -> None:
        from options_arena.models.analysis import MarketContext

        kwargs = self._base_kwargs()
        kwargs["contract_mid"] = Decimal("3.25")
        mc = MarketContext(**kwargs)  # type: ignore[arg-type]
        restored = MarketContext.model_validate_json(mc.model_dump_json())
        assert restored.contract_mid == mc.contract_mid
