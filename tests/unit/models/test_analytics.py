"""Unit tests for analytics persistence models.

Tests cover:
- Happy path construction with all required fields
- Frozen enforcement (attribute reassignment raises ValidationError)
- Decimal precision through JSON roundtrip
- Computed fields (mid)
- isfinite() validators reject NaN/Inf on all float fields
- is_finite() validators reject NaN/Inf on all Decimal fields
- UTC datetime validators reject naive and non-UTC datetimes
- Optional fields accept None
- Delta range validation [-1, 1]
- Gamma/vega non-negative validation
- Win rate bounded in [0.0, 1.0]
- Correlation bounded in [-1.0, 1.0]
- Decimal field_serializer produces strings in JSON
- OutcomeCollectionMethod enum membership
- AnalyticsConfig defaults and env override via AppSettings
"""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AnalyticsConfig,
    AppSettings,
    ExerciseStyle,
    GreeksSource,
    OptionType,
    OutcomeCollectionMethod,
    PricingModel,
    SignalDirection,
)
from options_arena.models.analytics import (
    ContractOutcome,
    DeltaPerformanceResult,
    HoldingPeriodResult,
    IndicatorAttributionResult,
    NormalizationStats,
    PerformanceSummary,
    RecommendedContract,
    ScoreCalibrationBucket,
    WinRateResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW_UTC = datetime(2026, 3, 3, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def sample_recommended_contract() -> RecommendedContract:
    """Create a valid RecommendedContract for reuse."""
    return RecommendedContract(
        scan_run_id=1,
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("185.00"),
        bid=Decimal("5.20"),
        ask=Decimal("5.40"),
        last=Decimal("5.30"),
        expiration=date(2026, 4, 17),
        volume=1500,
        open_interest=8500,
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
        created_at=NOW_UTC,
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
        exit_date=date(2026, 3, 10),
        stock_return_pct=4.11,
        contract_return_pct=79.25,
        is_winner=True,
        holding_days=5,
        dte_at_exit=38,
        collection_method=OutcomeCollectionMethod.MARKET,
        collected_at=NOW_UTC,
    )


# ---------------------------------------------------------------------------
# TestRecommendedContract
# ---------------------------------------------------------------------------


class TestRecommendedContract:
    """Tests for the RecommendedContract frozen model."""

    def test_construction_with_valid_data(
        self, sample_recommended_contract: RecommendedContract
    ) -> None:
        """Verify RecommendedContract constructs with all required fields."""
        rc = sample_recommended_contract
        assert rc.ticker == "AAPL"
        assert rc.option_type == OptionType.CALL
        assert rc.strike == Decimal("185.00")
        assert rc.scan_run_id == 1
        assert rc.market_iv == pytest.approx(0.32, rel=1e-6)
        assert rc.composite_score == pytest.approx(72.5, rel=1e-6)
        assert rc.direction == SignalDirection.BULLISH
        assert rc.id is None

    def test_frozen_rejects_mutation(
        self, sample_recommended_contract: RecommendedContract
    ) -> None:
        """Verify frozen=True prevents attribute reassignment."""
        with pytest.raises(ValidationError):
            sample_recommended_contract.ticker = "MSFT"  # type: ignore[misc]

    def test_decimal_precision_survives_json_roundtrip(
        self, sample_recommended_contract: RecommendedContract
    ) -> None:
        """Verify Decimal('1.05') != 1.0500000000000000444 after roundtrip."""
        json_str = sample_recommended_contract.model_dump_json()
        assert '"185.00"' in json_str  # strike serialized as string
        # Roundtrip: reconstruct from JSON
        restored = RecommendedContract.model_validate_json(json_str)
        assert restored.strike == Decimal("185.00")
        assert restored.entry_stock_price == Decimal("182.50")

    def test_computed_mid_field(self, sample_recommended_contract: RecommendedContract) -> None:
        """Verify mid = (bid + ask) / 2 with Decimal precision."""
        expected_mid = (Decimal("5.20") + Decimal("5.40")) / Decimal("2")
        assert sample_recommended_contract.mid == expected_mid

    def test_rejects_non_finite_market_iv(self) -> None:
        """Verify NaN market_iv rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                expiration=date(2026, 4, 17),
                volume=1500,
                open_interest=8500,
                market_iv=float("nan"),
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=NOW_UTC,
            )

    def test_rejects_inf_composite_score(self) -> None:
        """Verify Inf composite_score rejected by isfinite validator."""
        with pytest.raises(ValidationError, match="finite"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                expiration=date(2026, 4, 17),
                volume=1500,
                open_interest=8500,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=float("inf"),
                risk_free_rate=0.045,
                created_at=NOW_UTC,
            )

    def test_rejects_non_utc_created_at(self) -> None:
        """Verify naive or non-UTC datetime rejected."""
        # Naive datetime
        with pytest.raises(ValidationError, match="UTC"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                expiration=date(2026, 4, 17),
                volume=1500,
                open_interest=8500,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=datetime(2026, 3, 3, 12, 0, 0),  # naive
            )
        # Non-UTC timezone (US Eastern = UTC-5)
        eastern = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                expiration=date(2026, 4, 17),
                volume=1500,
                open_interest=8500,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=datetime(2026, 3, 3, 12, 0, 0, tzinfo=eastern),
            )

    def test_optional_greeks_none(self) -> None:
        """Verify all Greek fields accept None."""
        rc = RecommendedContract(
            scan_run_id=1,
            ticker="AAPL",
            option_type=OptionType.CALL,
            strike=Decimal("185.00"),
            bid=Decimal("5.20"),
            ask=Decimal("5.40"),
            expiration=date(2026, 4, 17),
            volume=1500,
            open_interest=8500,
            market_iv=0.32,
            exercise_style=ExerciseStyle.AMERICAN,
            entry_stock_price=Decimal("182.50"),
            entry_mid=Decimal("5.30"),
            direction=SignalDirection.BULLISH,
            composite_score=72.5,
            risk_free_rate=0.045,
            created_at=NOW_UTC,
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
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                expiration=date(2026, 4, 17),
                volume=1500,
                open_interest=8500,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                delta=1.5,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=NOW_UTC,
            )

    def test_gamma_rejects_negative(self) -> None:
        """Verify negative gamma rejected."""
        with pytest.raises(ValidationError, match=">= 0"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                expiration=date(2026, 4, 17),
                volume=1500,
                open_interest=8500,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                gamma=-0.01,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=NOW_UTC,
            )

    def test_vega_rejects_negative(self) -> None:
        """Verify negative vega rejected."""
        with pytest.raises(ValidationError, match=">= 0"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("185.00"),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                expiration=date(2026, 4, 17),
                volume=1500,
                open_interest=8500,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                vega=-0.05,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=NOW_UTC,
            )

    def test_decimal_field_serializer(
        self, sample_recommended_contract: RecommendedContract
    ) -> None:
        """Verify Decimal fields serialize as strings in JSON."""
        data = sample_recommended_contract.model_dump(mode="json")
        assert isinstance(data["strike"], str)
        assert isinstance(data["bid"], str)
        assert isinstance(data["ask"], str)
        assert isinstance(data["last"], str)
        assert isinstance(data["entry_stock_price"], str)
        assert isinstance(data["entry_mid"], str)

    def test_rejects_non_finite_decimal_strike(self) -> None:
        """Verify non-finite Decimal strike rejected."""
        with pytest.raises(ValidationError, match="finite"):
            RecommendedContract(
                scan_run_id=1,
                ticker="AAPL",
                option_type=OptionType.CALL,
                strike=Decimal("Infinity"),
                bid=Decimal("5.20"),
                ask=Decimal("5.40"),
                expiration=date(2026, 4, 17),
                volume=1500,
                open_interest=8500,
                market_iv=0.32,
                exercise_style=ExerciseStyle.AMERICAN,
                entry_stock_price=Decimal("182.50"),
                entry_mid=Decimal("5.30"),
                direction=SignalDirection.BULLISH,
                composite_score=72.5,
                risk_free_rate=0.045,
                created_at=NOW_UTC,
            )

    def test_mid_in_model_dump(self, sample_recommended_contract: RecommendedContract) -> None:
        """Verify computed mid field appears in model_dump output."""
        data = sample_recommended_contract.model_dump()
        assert "mid" in data


# ---------------------------------------------------------------------------
# TestContractOutcome
# ---------------------------------------------------------------------------


class TestContractOutcome:
    """Tests for the ContractOutcome frozen model."""

    def test_construction_with_valid_data(self, sample_contract_outcome: ContractOutcome) -> None:
        """Verify ContractOutcome constructs with all fields."""
        co = sample_contract_outcome
        assert co.recommended_contract_id == 1
        assert co.exit_stock_price == Decimal("190.00")
        assert co.stock_return_pct == pytest.approx(4.11, rel=1e-6)
        assert co.is_winner is True
        assert co.holding_days == 5
        assert co.collection_method == OutcomeCollectionMethod.MARKET

    def test_frozen_rejects_mutation(self, sample_contract_outcome: ContractOutcome) -> None:
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
                collected_at=NOW_UTC,
            )

    def test_rejects_inf_contract_return_pct(self) -> None:
        """Verify Inf contract_return_pct rejected."""
        with pytest.raises(ValidationError, match="finite"):
            ContractOutcome(
                recommended_contract_id=1,
                contract_return_pct=float("inf"),
                collection_method=OutcomeCollectionMethod.MARKET,
                collected_at=NOW_UTC,
            )

    def test_optional_fields_accept_none(self) -> None:
        """Verify all optional fields accept None."""
        co = ContractOutcome(
            recommended_contract_id=1,
            collection_method=OutcomeCollectionMethod.EXPIRED_WORTHLESS,
            collected_at=NOW_UTC,
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
        assert restored.recommended_contract_id == sample_contract_outcome.recommended_contract_id
        assert restored.exit_stock_price == sample_contract_outcome.exit_stock_price
        assert restored.collection_method == sample_contract_outcome.collection_method

    def test_rejects_non_utc_collected_at(self) -> None:
        """Verify naive datetime rejected on collected_at."""
        with pytest.raises(ValidationError, match="UTC"):
            ContractOutcome(
                recommended_contract_id=1,
                collection_method=OutcomeCollectionMethod.MARKET,
                collected_at=datetime(2026, 3, 3, 12, 0, 0),  # naive
            )

    def test_rejects_non_finite_decimal_exit_price(self) -> None:
        """Verify non-finite Decimal exit_stock_price rejected."""
        with pytest.raises(ValidationError, match="finite"):
            ContractOutcome(
                recommended_contract_id=1,
                exit_stock_price=Decimal("NaN"),
                collection_method=OutcomeCollectionMethod.MARKET,
                collected_at=NOW_UTC,
            )


# ---------------------------------------------------------------------------
# TestNormalizationStats
# ---------------------------------------------------------------------------


class TestNormalizationStats:
    """Tests for the NormalizationStats frozen model."""

    def test_construction(self) -> None:
        """Verify NormalizationStats constructs with valid data."""
        ns = NormalizationStats(
            scan_run_id=1,
            indicator_name="rsi",
            ticker_count=50,
            min_value=15.3,
            max_value=88.7,
            median_value=52.1,
            mean_value=51.8,
            std_dev=18.4,
            p25=38.2,
            p75=65.9,
            created_at=NOW_UTC,
        )
        assert ns.indicator_name == "rsi"
        assert ns.ticker_count == 50
        assert ns.min_value == pytest.approx(15.3, rel=1e-6)

    def test_rejects_negative_ticker_count(self) -> None:
        """Verify ticker_count < 0 rejected."""
        with pytest.raises(ValidationError, match="ticker_count"):
            NormalizationStats(
                scan_run_id=1,
                indicator_name="rsi",
                ticker_count=-1,
                created_at=NOW_UTC,
            )

    def test_zero_ticker_count_accepted(self) -> None:
        """Verify ticker_count == 0 is accepted (valid empty scan)."""
        ns = NormalizationStats(
            scan_run_id=1,
            indicator_name="rsi",
            ticker_count=0,
            created_at=NOW_UTC,
        )
        assert ns.ticker_count == 0

    def test_optional_stats_accept_none(self) -> None:
        """Verify all float stats accept None."""
        ns = NormalizationStats(
            scan_run_id=1,
            indicator_name="rsi",
            ticker_count=10,
            created_at=NOW_UTC,
        )
        assert ns.min_value is None
        assert ns.max_value is None
        assert ns.median_value is None
        assert ns.mean_value is None
        assert ns.std_dev is None
        assert ns.p25 is None
        assert ns.p75 is None

    def test_rejects_non_finite_stats(self) -> None:
        """Verify NaN float stats rejected."""
        with pytest.raises(ValidationError, match="finite"):
            NormalizationStats(
                scan_run_id=1,
                indicator_name="rsi",
                ticker_count=10,
                min_value=float("nan"),
                created_at=NOW_UTC,
            )

    def test_rejects_non_utc_created_at(self) -> None:
        """Verify naive datetime rejected."""
        with pytest.raises(ValidationError, match="UTC"):
            NormalizationStats(
                scan_run_id=1,
                indicator_name="rsi",
                ticker_count=10,
                created_at=datetime(2026, 3, 3, 12, 0, 0),
            )


# ---------------------------------------------------------------------------
# TestWinRateResult
# ---------------------------------------------------------------------------


class TestWinRateResult:
    """Tests for the WinRateResult frozen model."""

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
        assert wr.win_rate == pytest.approx(0.65, rel=1e-6)

    def test_win_rate_bounded_above(self) -> None:
        """Verify win_rate > 1.0 rejected."""
        with pytest.raises(ValidationError, match="win_rate"):
            WinRateResult(
                direction=SignalDirection.BULLISH,
                total_contracts=100,
                winners=65,
                losers=35,
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

    def test_win_rate_rejects_nan(self) -> None:
        """Verify NaN win_rate rejected by isfinite check."""
        with pytest.raises(ValidationError, match="finite"):
            WinRateResult(
                direction=SignalDirection.BULLISH,
                total_contracts=10,
                winners=5,
                losers=5,
                win_rate=float("nan"),
            )


# ---------------------------------------------------------------------------
# TestScoreCalibrationBucket
# ---------------------------------------------------------------------------


class TestScoreCalibrationBucket:
    """Tests for the ScoreCalibrationBucket frozen model."""

    def test_construction(self) -> None:
        """Verify ScoreCalibrationBucket with valid data."""
        bucket = ScoreCalibrationBucket(
            score_min=60.0,
            score_max=70.0,
            contract_count=25,
            avg_return_pct=12.5,
            win_rate=0.72,
        )
        assert bucket.score_min == pytest.approx(60.0, rel=1e-6)
        assert bucket.win_rate == pytest.approx(0.72, rel=1e-6)

    def test_rejects_non_finite_score(self) -> None:
        """Verify NaN score rejected."""
        with pytest.raises(ValidationError, match="finite"):
            ScoreCalibrationBucket(
                score_min=float("inf"),
                score_max=70.0,
                contract_count=25,
                avg_return_pct=12.5,
                win_rate=0.72,
            )

    def test_rejects_win_rate_above_one(self) -> None:
        """Verify win_rate > 1.0 rejected."""
        with pytest.raises(ValidationError, match="win_rate"):
            ScoreCalibrationBucket(
                score_min=60.0,
                score_max=70.0,
                contract_count=25,
                avg_return_pct=12.5,
                win_rate=1.01,
            )


# ---------------------------------------------------------------------------
# TestIndicatorAttributionResult
# ---------------------------------------------------------------------------


class TestIndicatorAttributionResult:
    """Tests for the IndicatorAttributionResult frozen model."""

    def test_construction(self) -> None:
        """Verify IndicatorAttributionResult with valid data."""
        attr = IndicatorAttributionResult(
            indicator_name="rsi",
            holding_days=5,
            correlation=0.35,
            avg_return_when_high=8.2,
            avg_return_when_low=-3.1,
            sample_size=200,
        )
        assert attr.indicator_name == "rsi"
        assert attr.correlation == pytest.approx(0.35, rel=1e-6)

    def test_correlation_bounded_above(self) -> None:
        """Verify correlation > 1.0 rejected."""
        with pytest.raises(ValidationError, match="correlation"):
            IndicatorAttributionResult(
                indicator_name="rsi",
                holding_days=5,
                correlation=1.5,
                avg_return_when_high=8.2,
                avg_return_when_low=-3.1,
                sample_size=200,
            )

    def test_correlation_bounded_below(self) -> None:
        """Verify correlation < -1.0 rejected."""
        with pytest.raises(ValidationError, match="correlation"):
            IndicatorAttributionResult(
                indicator_name="rsi",
                holding_days=5,
                correlation=-1.5,
                avg_return_when_high=8.2,
                avg_return_when_low=-3.1,
                sample_size=200,
            )

    def test_correlation_rejects_nan(self) -> None:
        """Verify NaN correlation rejected."""
        with pytest.raises(ValidationError, match="finite"):
            IndicatorAttributionResult(
                indicator_name="rsi",
                holding_days=5,
                correlation=float("nan"),
                avg_return_when_high=8.2,
                avg_return_when_low=-3.1,
                sample_size=200,
            )

    def test_rejects_non_finite_avg_return(self) -> None:
        """Verify Inf avg_return_when_high rejected."""
        with pytest.raises(ValidationError, match="finite"):
            IndicatorAttributionResult(
                indicator_name="rsi",
                holding_days=5,
                correlation=0.35,
                avg_return_when_high=float("inf"),
                avg_return_when_low=-3.1,
                sample_size=200,
            )


# ---------------------------------------------------------------------------
# TestHoldingPeriodResult
# ---------------------------------------------------------------------------


class TestHoldingPeriodResult:
    """Tests for the HoldingPeriodResult frozen model."""

    def test_construction(self) -> None:
        """Verify HoldingPeriodResult with valid data."""
        hp = HoldingPeriodResult(
            holding_days=5,
            direction=SignalDirection.BULLISH,
            avg_return_pct=6.3,
            median_return_pct=4.8,
            win_rate=0.68,
            sample_size=150,
        )
        assert hp.holding_days == 5
        assert hp.win_rate == pytest.approx(0.68, rel=1e-6)

    def test_win_rate_bounded(self) -> None:
        """Verify win_rate must be in [0.0, 1.0]."""
        with pytest.raises(ValidationError, match="win_rate"):
            HoldingPeriodResult(
                holding_days=5,
                direction=SignalDirection.BULLISH,
                avg_return_pct=6.3,
                median_return_pct=4.8,
                win_rate=1.1,
                sample_size=150,
            )

    def test_rejects_nan_return(self) -> None:
        """Verify NaN avg_return_pct rejected."""
        with pytest.raises(ValidationError, match="finite"):
            HoldingPeriodResult(
                holding_days=5,
                direction=SignalDirection.BULLISH,
                avg_return_pct=float("nan"),
                median_return_pct=4.8,
                win_rate=0.68,
                sample_size=150,
            )


# ---------------------------------------------------------------------------
# TestDeltaPerformanceResult
# ---------------------------------------------------------------------------


class TestDeltaPerformanceResult:
    """Tests for the DeltaPerformanceResult frozen model."""

    def test_construction(self) -> None:
        """Verify DeltaPerformanceResult with valid data."""
        dp = DeltaPerformanceResult(
            delta_min=0.2,
            delta_max=0.4,
            holding_days=10,
            avg_return_pct=7.5,
            win_rate=0.62,
            sample_size=80,
        )
        assert dp.delta_min == pytest.approx(0.2, rel=1e-6)
        assert dp.win_rate == pytest.approx(0.62, rel=1e-6)

    def test_win_rate_bounded(self) -> None:
        """Verify win_rate must be in [0.0, 1.0]."""
        with pytest.raises(ValidationError, match="win_rate"):
            DeltaPerformanceResult(
                delta_min=0.2,
                delta_max=0.4,
                holding_days=10,
                avg_return_pct=7.5,
                win_rate=-0.01,
                sample_size=80,
            )

    def test_rejects_non_finite_delta(self) -> None:
        """Verify Inf delta_min rejected."""
        with pytest.raises(ValidationError, match="finite"):
            DeltaPerformanceResult(
                delta_min=float("inf"),
                delta_max=0.4,
                holding_days=10,
                avg_return_pct=7.5,
                win_rate=0.62,
                sample_size=80,
            )


# ---------------------------------------------------------------------------
# TestPerformanceSummary
# ---------------------------------------------------------------------------


class TestPerformanceSummary:
    """Tests for the PerformanceSummary frozen model."""

    def test_construction_all_none_optional(self) -> None:
        """Verify PerformanceSummary when no outcomes exist (all optional None)."""
        ps = PerformanceSummary(
            lookback_days=30,
            total_contracts=100,
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
            total_contracts=100,
            total_with_outcomes=75,
            overall_win_rate=0.64,
            avg_stock_return_pct=3.2,
            avg_contract_return_pct=28.5,
            best_direction=SignalDirection.BULLISH,
            best_holding_days=5,
        )
        assert ps.overall_win_rate == pytest.approx(0.64, rel=1e-6)
        assert ps.best_direction == SignalDirection.BULLISH

    def test_win_rate_bounded(self) -> None:
        """Verify overall_win_rate must be in [0.0, 1.0] when provided."""
        with pytest.raises(ValidationError, match="overall_win_rate"):
            PerformanceSummary(
                lookback_days=30,
                total_contracts=100,
                total_with_outcomes=75,
                overall_win_rate=1.5,
            )

    def test_rejects_nan_avg_return(self) -> None:
        """Verify NaN avg_stock_return_pct rejected."""
        with pytest.raises(ValidationError, match="finite"):
            PerformanceSummary(
                lookback_days=30,
                total_contracts=100,
                total_with_outcomes=75,
                avg_stock_return_pct=float("nan"),
            )


# ---------------------------------------------------------------------------
# TestOutcomeCollectionMethodEnum
# ---------------------------------------------------------------------------


class TestOutcomeCollectionMethodEnum:
    """Tests for the OutcomeCollectionMethod StrEnum."""

    def test_member_count(self) -> None:
        """Verify exactly 3 members."""
        assert len(OutcomeCollectionMethod) == 3

    def test_str_enum_subclass(self) -> None:
        """Verify StrEnum subclass."""
        assert issubclass(OutcomeCollectionMethod, str)

    def test_member_values(self) -> None:
        """Verify the expected member values."""
        assert OutcomeCollectionMethod.MARKET == "market"
        assert OutcomeCollectionMethod.INTRINSIC == "intrinsic"
        assert OutcomeCollectionMethod.EXPIRED_WORTHLESS == "expired_worthless"


# ---------------------------------------------------------------------------
# TestAnalyticsConfig
# ---------------------------------------------------------------------------


class TestAnalyticsConfig:
    """Tests for the AnalyticsConfig BaseModel and AppSettings wiring."""

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
        assert config.batch_size == 100

    def test_batch_size_rejects_zero(self) -> None:
        """Verify batch_size < 1 rejected."""
        with pytest.raises(ValidationError, match="batch_size"):
            AnalyticsConfig(batch_size=0)

    def test_holding_periods_rejects_negative(self) -> None:
        """Verify negative holding period rejected."""
        with pytest.raises(ValidationError, match="holding_period"):
            AnalyticsConfig(holding_periods=[1, -5, 10])

    def test_app_settings_wiring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify AppSettings includes analytics config with defaults."""
        # Clear env vars that might interfere
        monkeypatch.delenv("ARENA_ANALYTICS__HOLDING_PERIODS", raising=False)
        monkeypatch.delenv("ARENA_ANALYTICS__AUTO_COLLECT", raising=False)
        monkeypatch.delenv("ARENA_ANALYTICS__BATCH_SIZE", raising=False)
        settings = AppSettings()
        assert settings.analytics.holding_periods == [1, 5, 10, 20]
        assert settings.analytics.auto_collect is False
        assert settings.analytics.batch_size == 50

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify ARENA_ANALYTICS__BATCH_SIZE env override works via AppSettings."""
        monkeypatch.setenv("ARENA_ANALYTICS__BATCH_SIZE", "200")
        settings = AppSettings()
        assert settings.analytics.batch_size == 200
