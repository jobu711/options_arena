"""Unit tests for analytics persistence models.

Tests cover:
- Happy path construction with valid data for all 9 models
- Frozen enforcement (attribute reassignment raises ValidationError)
- NaN/Inf rejection via isfinite validators on all float/Decimal fields
- UTC enforcement on all datetime fields
- Decimal precision survives JSON roundtrip
- Optional fields accept None
- Boundary validation (delta range, win_rate bounds, correlation bounds)
- Computed fields (mid on RecommendedContract)
- Decimal field serializers produce strings
- OutcomeCollectionMethod enum (member count, StrEnum subclass)
- AnalyticsConfig (defaults, validators, env override via AppSettings)
"""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AnalyticsConfig,
    AppSettings,
    ContractOutcome,
    DeltaPerformanceResult,
    ExerciseStyle,
    GreeksSource,
    HoldingPeriodResult,
    IndicatorAttributionResult,
    NormalizationStats,
    OptionType,
    OutcomeCollectionMethod,
    PerformanceSummary,
    PricingModel,
    RecommendedContract,
    ScoreCalibrationBucket,
    SignalDirection,
    WinRateResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

UTC_NOW = datetime(2026, 3, 3, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def sample_recommended_contract() -> RecommendedContract:
    """Create a valid RecommendedContract for reuse."""
    return RecommendedContract(
        scan_run_id=1,
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("185.00"),
        expiration=date(2026, 6, 19),
        bid=Decimal("5.20"),
        ask=Decimal("5.40"),
        last=Decimal("5.30"),
        volume=1500,
        open_interest=12000,
        market_iv=0.32,
        exercise_style=ExerciseStyle.AMERICAN,
        delta=0.45,
        gamma=0.03,
        theta=-0.08,
        vega=0.15,
        rho=0.02,
        pricing_model=PricingModel.BAW,
        greeks_source=GreeksSource.COMPUTED,
        entry_stock_price=Decimal("182.50"),
        entry_mid=Decimal("5.30"),
        direction=SignalDirection.BULLISH,
        composite_score=72.5,
        risk_free_rate=0.045,
        created_at=UTC_NOW,
    )


@pytest.fixture
def sample_contract_outcome() -> ContractOutcome:
    """Create a valid ContractOutcome for reuse."""
    return ContractOutcome(
        recommended_contract_id=1,
        exit_stock_price=Decimal("190.00"),
        exit_contract_mid=Decimal("9.50"),
        exit_contract_bid=Decimal("9.40"),
        exit_contract_ask=Decimal("9.60"),
        exit_date=date(2026, 3, 8),
        stock_return_pct=4.11,
        contract_return_pct=79.25,
        is_winner=True,
        holding_days=5,
        dte_at_exit=103,
        collection_method=OutcomeCollectionMethod.MARKET,
        collected_at=UTC_NOW,
    )


# ---------------------------------------------------------------------------
# RecommendedContract
# ---------------------------------------------------------------------------


class TestRecommendedContract:
    def test_construction_with_valid_data(
        self, sample_recommended_contract: RecommendedContract
    ) -> None:
        """Verify RecommendedContract constructs with all required fields."""
        rc = sample_recommended_contract
        assert rc.ticker == "AAPL"
        assert rc.option_type == OptionType.CALL
        assert rc.strike == Decimal("185.00")
        assert rc.scan_run_id == 1
        assert rc.entry_stock_price == Decimal("182.50")
        assert rc.direction == SignalDirection.BULLISH
        assert rc.composite_score == pytest.approx(72.5)
        assert rc.created_at == UTC_NOW

    def test_frozen_rejects_mutation(
        self, sample_recommended_contract: RecommendedContract
    ) -> None:
        """Verify frozen=True prevents attribute reassignment."""
        with pytest.raises(ValidationError):
            sample_recommended_contract.ticker = "MSFT"  # type: ignore[misc]

    def test_computed_mid_field(
        self, sample_recommended_contract: RecommendedContract
    ) -> None:
        """Verify mid = (bid + ask) / 2 with Decimal precision."""
        assert sample_recommended_contract.mid == Decimal("5.30")

    def test_decimal_precision_survives_json_roundtrip(
        self, sample_recommended_contract: RecommendedContract
    ) -> None:
        """Verify Decimal('185.00') survives roundtrip without float precision loss."""
        json_str = sample_recommended_contract.model_dump_json()
        restored = RecommendedContract.model_validate_json(json_str)
        assert restored.strike == Decimal("185.00")
        assert restored.entry_stock_price == Decimal("182.50")
        assert restored.entry_mid == Decimal("5.30")

    def test_decimal_field_serializer(
        self, sample_recommended_contract: RecommendedContract
    ) -> None:
        """Verify Decimal fields serialize as strings in JSON."""
        data = sample_recommended_contract.model_dump()
        assert isinstance(data["strike"], str)
        assert data["strike"] == "185.00"
        assert isinstance(data["entry_stock_price"], str)
        assert data["entry_stock_price"] == "182.50"

    def test_rejects_non_finite_market_iv(self) -> None:
        """Verify NaN market_iv rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="market_iv"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                expiration=date(2026, 6, 19),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                volume=1500,
                open_interest=12000,
                market_iv=float("nan"),
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=UTC_NOW,
            )

    def test_rejects_inf_composite_score(self) -> None:
        """Verify Inf composite_score rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="composite_score"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                expiration=date(2026, 6, 19),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                volume=1500,
                open_interest=12000,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=float("inf"),
                risk_free_rate=0.045,
                created_at=UTC_NOW,
            )

    def test_rejects_non_utc_created_at(self) -> None:
        """Verify naive datetime rejected."""
        with pytest.raises(ValidationError, match="UTC"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                expiration=date(2026, 6, 19),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                volume=1500,
                open_interest=12000,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=datetime(2026, 3, 3, 12, 0, 0),  # naive, no tzinfo
            )

    def test_rejects_non_utc_timezone(self) -> None:
        """Verify non-UTC timezone rejected."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                expiration=date(2026, 6, 19),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                volume=1500,
                open_interest=12000,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=datetime(2026, 3, 3, 12, 0, 0, tzinfo=est),
            )

    def test_optional_greeks_none(self) -> None:
        """Verify all Greek fields accept None."""
        rc = RecommendedContract(
            scan_run_id=1,
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2026, 6, 19),
            bid=Decimal("5.20"),
            ask=Decimal("5.40"),
            volume=1500,
            open_interest=12000,
            market_iv=0.32,
            exercise_style=ExerciseStyle.AMERICAN,
            entry_stock_price=Decimal("182.50"),
            entry_mid=Decimal("5.30"),
            direction=SignalDirection.BULLISH,
            composite_score=72.5,
            risk_free_rate=0.045,
            created_at=UTC_NOW,
        )
        assert rc.delta is None
        assert rc.gamma is None
        assert rc.theta is None
        assert rc.vega is None
        assert rc.rho is None
        assert rc.pricing_model is None
        assert rc.greeks_source is None
        assert rc.last is None

    def test_delta_range_validation(self) -> None:
        """Verify delta outside [-1, 1] rejected when not None."""
        with pytest.raises(ValidationError, match="delta"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                expiration=date(2026, 6, 19),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                volume=1500,
                open_interest=12000,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                delta=1.5,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=UTC_NOW,
            )

    def test_negative_volume_rejected(self) -> None:
        """Verify negative volume rejected."""
        with pytest.raises(ValidationError, match="must be >= 0"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                expiration=date(2026, 6, 19),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                volume=-1,
                open_interest=12000,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=UTC_NOW,
            )

    def test_non_finite_decimal_rejected(self) -> None:
        """Verify NaN Decimal strike rejected."""
        with pytest.raises(ValidationError, match="finite"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("NaN"),
                expiration=date(2026, 6, 19),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                volume=1500,
                open_interest=12000,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=UTC_NOW,
            )

    def test_id_defaults_to_none(self) -> None:
        """Verify id defaults to None (DB-assigned)."""
        rc = RecommendedContract(
            scan_run_id=1,
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            expiration=date(2026, 6, 19),
            bid=Decimal("5.20"),
            ask=Decimal("5.40"),
            volume=1500,
            open_interest=12000,
            market_iv=0.32,
            exercise_style=ExerciseStyle.AMERICAN,
            entry_stock_price=Decimal("182.50"),
            entry_mid=Decimal("5.30"),
            direction=SignalDirection.BULLISH,
            composite_score=72.5,
            risk_free_rate=0.045,
            created_at=UTC_NOW,
        )
        assert rc.id is None


# ---------------------------------------------------------------------------
# ContractOutcome
# ---------------------------------------------------------------------------


class TestContractOutcome:
    def test_construction_with_valid_data(
        self, sample_contract_outcome: ContractOutcome
    ) -> None:
        """Verify ContractOutcome constructs with all fields."""
        co = sample_contract_outcome
        assert co.recommended_contract_id == 1
        assert co.exit_stock_price == Decimal("190.00")
        assert co.stock_return_pct == pytest.approx(4.11)
        assert co.is_winner is True
        assert co.holding_days == 5
        assert co.collection_method == OutcomeCollectionMethod.MARKET

    def test_frozen_rejects_mutation(
        self, sample_contract_outcome: ContractOutcome
    ) -> None:
        """Verify frozen=True prevents reassignment."""
        with pytest.raises(ValidationError):
            sample_contract_outcome.is_winner = False  # type: ignore[misc]

    def test_rejects_non_finite_return_pct(self) -> None:
        """Verify NaN stock_return_pct rejected."""
        with pytest.raises(ValidationError, match="finite"):
            ContractOutcome(
                recommended_contract_id=1,
                stock_return_pct=float("nan"),
                collection_method=OutcomeCollectionMethod.MARKET,
                collected_at=UTC_NOW,
            )

    def test_rejects_inf_contract_return_pct(self) -> None:
        """Verify Inf contract_return_pct rejected."""
        with pytest.raises(ValidationError, match="finite"):
            ContractOutcome(
                recommended_contract_id=1,
                contract_return_pct=float("inf"),
                collection_method=OutcomeCollectionMethod.MARKET,
                collected_at=UTC_NOW,
            )

    def test_optional_fields_accept_none(self) -> None:
        """Verify all optional fields accept None."""
        co = ContractOutcome(
            recommended_contract_id=1,
            collection_method=OutcomeCollectionMethod.EXPIRED_WORTHLESS,
            collected_at=UTC_NOW,
        )
        assert co.exit_stock_price is None
        assert co.exit_contract_mid is None
        assert co.exit_contract_bid is None
        assert co.exit_contract_ask is None
        assert co.exit_date is None
        assert co.stock_return_pct is None
        assert co.contract_return_pct is None
        assert co.is_winner is None
        assert co.holding_days is None
        assert co.dte_at_exit is None

    def test_json_roundtrip(self, sample_contract_outcome: ContractOutcome) -> None:
        """Verify model survives JSON serialization roundtrip."""
        json_str = sample_contract_outcome.model_dump_json()
        restored = ContractOutcome.model_validate_json(json_str)
        assert restored.exit_stock_price == Decimal("190.00")
        assert restored.stock_return_pct == pytest.approx(4.11)
        assert restored.collection_method == OutcomeCollectionMethod.MARKET

    def test_rejects_non_utc_collected_at(self) -> None:
        """Verify naive datetime rejected on collected_at."""
        with pytest.raises(ValidationError, match="UTC"):
            ContractOutcome(
                recommended_contract_id=1,
                collection_method=OutcomeCollectionMethod.MARKET,
                collected_at=datetime(2026, 3, 3, 12, 0, 0),
            )

    def test_rejects_negative_holding_days(self) -> None:
        """Verify negative holding_days rejected."""
        with pytest.raises(ValidationError, match=">= 0"):
            ContractOutcome(
                recommended_contract_id=1,
                holding_days=-5,
                collection_method=OutcomeCollectionMethod.MARKET,
                collected_at=UTC_NOW,
            )

    def test_rejects_negative_dte_at_exit(self) -> None:
        """Verify negative dte_at_exit rejected."""
        with pytest.raises(ValidationError, match=">= 0"):
            ContractOutcome(
                recommended_contract_id=1,
                dte_at_exit=-1,
                collection_method=OutcomeCollectionMethod.MARKET,
                collected_at=UTC_NOW,
            )

    def test_zero_holding_days_accepted(self) -> None:
        """Verify holding_days == 0 accepted (same-day exit)."""
        co = ContractOutcome(
            recommended_contract_id=1,
            holding_days=0,
            collection_method=OutcomeCollectionMethod.MARKET,
            collected_at=UTC_NOW,
        )
        assert co.holding_days == 0

    def test_decimal_serializer(self, sample_contract_outcome: ContractOutcome) -> None:
        """Verify Decimal fields serialize as strings."""
        data = sample_contract_outcome.model_dump()
        assert isinstance(data["exit_stock_price"], str)
        assert data["exit_stock_price"] == "190.00"


# ---------------------------------------------------------------------------
# NormalizationStats
# ---------------------------------------------------------------------------


class TestNormalizationStats:
    def test_construction(self) -> None:
        """Verify NormalizationStats constructs with valid data."""
        ns = NormalizationStats(
            scan_run_id=1,
            indicator_name="rsi",
            ticker_count=50,
            min_value=15.2,
            max_value=88.7,
            median_value=52.3,
            mean_value=51.8,
            std_dev=18.4,
            p25=38.1,
            p75=65.9,
            created_at=UTC_NOW,
        )
        assert ns.indicator_name == "rsi"
        assert ns.ticker_count == 50
        assert ns.min_value == pytest.approx(15.2)

    def test_rejects_negative_ticker_count(self) -> None:
        """Verify ticker_count < 0 rejected."""
        with pytest.raises(ValidationError, match="ticker_count"):
            NormalizationStats(
                scan_run_id=1,
                indicator_name="rsi",
                ticker_count=-1,
                created_at=UTC_NOW,
            )

    def test_zero_ticker_count_accepted(self) -> None:
        """Verify ticker_count == 0 accepted (valid empty scan)."""
        ns = NormalizationStats(
            scan_run_id=1,
            indicator_name="rsi",
            ticker_count=0,
            created_at=UTC_NOW,
        )
        assert ns.ticker_count == 0

    def test_optional_stats_accept_none(self) -> None:
        """Verify all float stats accept None."""
        ns = NormalizationStats(
            scan_run_id=1,
            indicator_name="rsi",
            ticker_count=50,
            created_at=UTC_NOW,
        )
        assert ns.min_value is None
        assert ns.max_value is None
        assert ns.median_value is None
        assert ns.mean_value is None
        assert ns.std_dev is None
        assert ns.p25 is None
        assert ns.p75 is None

    def test_rejects_nan_stat_value(self) -> None:
        """Verify NaN stat value rejected."""
        with pytest.raises(ValidationError, match="finite"):
            NormalizationStats(
                scan_run_id=1,
                indicator_name="rsi",
                ticker_count=50,
                min_value=float("nan"),
                created_at=UTC_NOW,
            )

    def test_frozen(self) -> None:
        """Verify frozen=True prevents mutation."""
        ns = NormalizationStats(
            scan_run_id=1,
            indicator_name="rsi",
            ticker_count=50,
            created_at=UTC_NOW,
        )
        with pytest.raises(ValidationError):
            ns.ticker_count = 100  # type: ignore[misc]

    def test_rejects_negative_std_dev(self) -> None:
        """Verify negative std_dev rejected."""
        with pytest.raises(ValidationError, match="std_dev"):
            NormalizationStats(
                scan_run_id=1,
                indicator_name="rsi",
                ticker_count=50,
                std_dev=-1.5,
                created_at=UTC_NOW,
            )

    def test_zero_std_dev_accepted(self) -> None:
        """Verify std_dev == 0.0 accepted (all identical values)."""
        ns = NormalizationStats(
            scan_run_id=1,
            indicator_name="rsi",
            ticker_count=50,
            std_dev=0.0,
            created_at=UTC_NOW,
        )
        assert ns.std_dev == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# WinRateResult
# ---------------------------------------------------------------------------


class TestWinRateResult:
    def test_construction(self) -> None:
        """Verify WinRateResult with valid data."""
        wr = WinRateResult(
            direction=SignalDirection.BULLISH,
            total_contracts=100,
            winners=65,
            losers=35,
            win_rate=0.65,
        )
        assert wr.direction == SignalDirection.BULLISH
        assert wr.win_rate == pytest.approx(0.65)

    def test_win_rate_bounded_above(self) -> None:
        """Verify win_rate > 1.0 rejected."""
        with pytest.raises(ValidationError, match="win_rate"):
            WinRateResult(
                direction=SignalDirection.BULLISH,
                total_contracts=100,
                winners=100,
                losers=0,
                win_rate=1.5,
            )

    def test_win_rate_bounded_below(self) -> None:
        """Verify win_rate < 0.0 rejected."""
        with pytest.raises(ValidationError, match="win_rate"):
            WinRateResult(
                direction=SignalDirection.BEARISH,
                total_contracts=100,
                winners=0,
                losers=100,
                win_rate=-0.1,
            )

    def test_win_rate_nan_rejected(self) -> None:
        """Verify NaN win_rate rejected."""
        with pytest.raises(ValidationError, match="finite"):
            WinRateResult(
                direction=SignalDirection.BULLISH,
                total_contracts=100,
                winners=50,
                losers=50,
                win_rate=float("nan"),
            )


# ---------------------------------------------------------------------------
# ScoreCalibrationBucket
# ---------------------------------------------------------------------------


class TestScoreCalibrationBucket:
    def test_construction(self) -> None:
        """Verify ScoreCalibrationBucket with valid data."""
        bucket = ScoreCalibrationBucket(
            score_min=60.0,
            score_max=70.0,
            contract_count=25,
            avg_return_pct=12.5,
            win_rate=0.72,
        )
        assert bucket.score_min == pytest.approx(60.0)
        assert bucket.win_rate == pytest.approx(0.72)

    def test_rejects_nan_score(self) -> None:
        """Verify NaN score_min rejected."""
        with pytest.raises(ValidationError, match="finite"):
            ScoreCalibrationBucket(
                score_min=float("nan"),
                score_max=70.0,
                contract_count=25,
                avg_return_pct=12.5,
                win_rate=0.72,
            )


# ---------------------------------------------------------------------------
# IndicatorAttributionResult
# ---------------------------------------------------------------------------


class TestIndicatorAttributionResult:
    def test_construction(self) -> None:
        """Verify IndicatorAttributionResult with valid data."""
        result = IndicatorAttributionResult(
            indicator_name="rsi",
            holding_days=5,
            correlation=0.35,
            avg_return_when_high=8.2,
            avg_return_when_low=-2.1,
            sample_size=200,
        )
        assert result.correlation == pytest.approx(0.35)

    def test_correlation_bounded(self) -> None:
        """Verify correlation must be in [-1.0, 1.0]."""
        with pytest.raises(ValidationError, match="correlation"):
            IndicatorAttributionResult(
                indicator_name="rsi",
                holding_days=5,
                correlation=1.5,
                avg_return_when_high=8.2,
                avg_return_when_low=-2.1,
                sample_size=200,
            )

    def test_correlation_negative_bound(self) -> None:
        """Verify correlation < -1.0 rejected."""
        with pytest.raises(ValidationError, match="correlation"):
            IndicatorAttributionResult(
                indicator_name="rsi",
                holding_days=5,
                correlation=-1.5,
                avg_return_when_high=8.2,
                avg_return_when_low=-2.1,
                sample_size=200,
            )

    def test_correlation_at_bounds_accepted(self) -> None:
        """Verify correlation exactly -1.0 and 1.0 accepted."""
        r1 = IndicatorAttributionResult(
            indicator_name="rsi",
            holding_days=5,
            correlation=-1.0,
            avg_return_when_high=0.0,
            avg_return_when_low=0.0,
            sample_size=10,
        )
        r2 = IndicatorAttributionResult(
            indicator_name="rsi",
            holding_days=5,
            correlation=1.0,
            avg_return_when_high=0.0,
            avg_return_when_low=0.0,
            sample_size=10,
        )
        assert r1.correlation == pytest.approx(-1.0)
        assert r2.correlation == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# HoldingPeriodResult
# ---------------------------------------------------------------------------


class TestHoldingPeriodResult:
    def test_construction(self) -> None:
        """Verify HoldingPeriodResult with valid data."""
        result = HoldingPeriodResult(
            holding_days=5,
            direction=SignalDirection.BULLISH,
            avg_return_pct=6.3,
            median_return_pct=4.8,
            win_rate=0.58,
            sample_size=150,
        )
        assert result.holding_days == 5
        assert result.win_rate == pytest.approx(0.58)

    def test_win_rate_bounded(self) -> None:
        """Verify win_rate must be in [0.0, 1.0]."""
        with pytest.raises(ValidationError, match="win_rate"):
            HoldingPeriodResult(
                holding_days=5,
                direction=SignalDirection.BULLISH,
                avg_return_pct=6.3,
                median_return_pct=4.8,
                win_rate=2.0,
                sample_size=150,
            )


# ---------------------------------------------------------------------------
# DeltaPerformanceResult
# ---------------------------------------------------------------------------


class TestDeltaPerformanceResult:
    def test_construction(self) -> None:
        """Verify DeltaPerformanceResult with valid data."""
        result = DeltaPerformanceResult(
            delta_min=0.2,
            delta_max=0.3,
            holding_days=5,
            avg_return_pct=8.1,
            win_rate=0.62,
            sample_size=80,
        )
        assert result.delta_min == pytest.approx(0.2)
        assert result.win_rate == pytest.approx(0.62)

    def test_rejects_nan_delta(self) -> None:
        """Verify NaN delta_min rejected."""
        with pytest.raises(ValidationError, match="finite"):
            DeltaPerformanceResult(
                delta_min=float("nan"),
                delta_max=0.3,
                holding_days=5,
                avg_return_pct=8.1,
                win_rate=0.62,
                sample_size=80,
            )


# ---------------------------------------------------------------------------
# PerformanceSummary
# ---------------------------------------------------------------------------


class TestPerformanceSummary:
    def test_construction_all_none_optional(self) -> None:
        """Verify PerformanceSummary when no outcomes exist (all optional None)."""
        ps = PerformanceSummary(
            lookback_days=30,
            total_contracts=0,
            total_with_outcomes=0,
        )
        assert ps.overall_win_rate is None
        assert ps.avg_stock_return_pct is None
        assert ps.avg_contract_return_pct is None
        assert ps.best_direction is None
        assert ps.best_holding_days is None

    def test_construction_with_data(self) -> None:
        """Verify PerformanceSummary with populated stats."""
        ps = PerformanceSummary(
            lookback_days=30,
            total_contracts=200,
            total_with_outcomes=150,
            overall_win_rate=0.62,
            avg_stock_return_pct=3.5,
            avg_contract_return_pct=15.2,
            best_direction=SignalDirection.BULLISH,
            best_holding_days=5,
        )
        assert ps.overall_win_rate == pytest.approx(0.62)
        assert ps.best_direction == SignalDirection.BULLISH

    def test_win_rate_bounded(self) -> None:
        """Verify win_rate > 1.0 rejected when provided."""
        with pytest.raises(ValidationError, match="win_rate"):
            PerformanceSummary(
                lookback_days=30,
                total_contracts=200,
                total_with_outcomes=150,
                overall_win_rate=1.5,
            )

    def test_nan_return_rejected(self) -> None:
        """Verify NaN avg_stock_return_pct rejected."""
        with pytest.raises(ValidationError, match="finite"):
            PerformanceSummary(
                lookback_days=30,
                total_contracts=200,
                total_with_outcomes=150,
                avg_stock_return_pct=float("nan"),
            )


# ---------------------------------------------------------------------------
# OutcomeCollectionMethod enum
# ---------------------------------------------------------------------------


class TestOutcomeCollectionMethodEnum:
    def test_member_count(self) -> None:
        """Verify exactly 3 members."""
        assert len(OutcomeCollectionMethod) == 3

    def test_str_enum_subclass(self) -> None:
        """Verify StrEnum subclass."""
        assert issubclass(OutcomeCollectionMethod, StrEnum)

    def test_values(self) -> None:
        """Verify expected string values."""
        assert OutcomeCollectionMethod.MARKET == "market"
        assert OutcomeCollectionMethod.INTRINSIC == "intrinsic"
        assert OutcomeCollectionMethod.EXPIRED_WORTHLESS == "expired_worthless"


# ---------------------------------------------------------------------------
# AnalyticsConfig
# ---------------------------------------------------------------------------


class TestAnalyticsConfig:
    def test_defaults(self) -> None:
        """Verify default holding_periods=[1,5,10,20], auto_collect=False, batch_size=50."""
        config = AnalyticsConfig()
        assert config.holding_periods == [1, 5, 10, 20]
        assert config.auto_collect is False
        assert config.batch_size == 50

    def test_custom_values(self) -> None:
        """Verify custom values accepted."""
        config = AnalyticsConfig(
            holding_periods=[1, 3, 7],
            auto_collect=True,
            batch_size=100,
        )
        assert config.holding_periods == [1, 3, 7]
        assert config.auto_collect is True

    def test_empty_holding_periods_rejected(self) -> None:
        """Verify empty holding_periods list rejected."""
        with pytest.raises(ValidationError, match="holding_periods must not be empty"):
            AnalyticsConfig(holding_periods=[])

    def test_negative_holding_period_rejected(self) -> None:
        """Verify negative holding period rejected."""
        with pytest.raises(ValidationError, match="holding period must be >= 1"):
            AnalyticsConfig(holding_periods=[1, -5, 10])

    def test_zero_batch_size_rejected(self) -> None:
        """Verify batch_size < 1 rejected."""
        with pytest.raises(ValidationError, match="batch_size must be >= 1"):
            AnalyticsConfig(batch_size=0)

    def test_env_override_via_appsettings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify ARENA_ANALYTICS__BATCH_SIZE env override works via AppSettings."""
        monkeypatch.setenv("ARENA_ANALYTICS__BATCH_SIZE", "25")
        settings = AppSettings()
        assert settings.analytics.batch_size == 25

    def test_appsettings_has_analytics_default(self) -> None:
        """Verify AppSettings includes analytics with default config."""
        settings = AppSettings()
        assert isinstance(settings.analytics, AnalyticsConfig)
        assert settings.analytics.holding_periods == [1, 5, 10, 20]
