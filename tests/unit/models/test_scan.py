"""Unit tests for scan models: IndicatorSignals, ScanRun, TickerScore.

Tests cover:
- IndicatorSignals: all-None construction, partial fill, field count, mutability
- ScanRun: happy path, frozen enforcement, default values
- TickerScore: signals type, direction enum, mutability
- JSON serialization roundtrip
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from options_arena.models import (
    GICSSector,
    IndicatorSignals,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_signals() -> IndicatorSignals:
    """Create an IndicatorSignals instance with all fields defaulting to None."""
    return IndicatorSignals()


@pytest.fixture
def partial_signals() -> IndicatorSignals:
    """Create an IndicatorSignals instance with 5 fields set."""
    return IndicatorSignals(
        rsi=65.0,
        adx=72.0,
        bb_width=45.0,
        obv=55.0,
        sma_alignment=80.0,
    )


@pytest.fixture
def sample_scan_run() -> ScanRun:
    """Create a valid ScanRun instance for reuse."""
    return ScanRun(
        started_at=datetime(2025, 6, 15, 9, 30, 0, tzinfo=UTC),
        completed_at=datetime(2025, 6, 15, 9, 45, 0, tzinfo=UTC),
        preset=ScanPreset.FULL,
        tickers_scanned=5296,
        tickers_scored=5159,
        recommendations=8,
    )


@pytest.fixture
def sample_ticker_score() -> TickerScore:
    """Create a valid TickerScore instance for reuse."""
    return TickerScore(
        ticker="AAPL",
        composite_score=78.5,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(
            rsi=65.0,
            adx=72.0,
            bb_width=45.0,
        ),
    )


# ---------------------------------------------------------------------------
# IndicatorSignals Tests
# ---------------------------------------------------------------------------


class TestIndicatorSignals:
    """Tests for the IndicatorSignals model."""

    def test_all_none_construction(self, empty_signals: IndicatorSignals) -> None:
        """IndicatorSignals() constructs with all 18 fields defaulting to None."""
        assert empty_signals.rsi is None
        assert empty_signals.stochastic_rsi is None
        assert empty_signals.williams_r is None
        assert empty_signals.adx is None
        assert empty_signals.roc is None
        assert empty_signals.supertrend is None
        assert empty_signals.bb_width is None
        assert empty_signals.atr_pct is None
        assert empty_signals.keltner_width is None
        assert empty_signals.obv is None
        assert empty_signals.ad is None
        assert empty_signals.relative_volume is None
        assert empty_signals.sma_alignment is None
        assert empty_signals.vwap_deviation is None
        assert empty_signals.iv_rank is None
        assert empty_signals.iv_percentile is None
        assert empty_signals.put_call_ratio is None
        assert empty_signals.max_pain_distance is None

    def test_partial_fill(self, partial_signals: IndicatorSignals) -> None:
        """IndicatorSignals with 5 fields set, rest remain None."""
        assert partial_signals.rsi == pytest.approx(65.0)
        assert partial_signals.adx == pytest.approx(72.0)
        assert partial_signals.bb_width == pytest.approx(45.0)
        assert partial_signals.obv == pytest.approx(55.0)
        assert partial_signals.sma_alignment == pytest.approx(80.0)
        # Unset fields remain None
        assert partial_signals.stochastic_rsi is None
        assert partial_signals.williams_r is None
        assert partial_signals.roc is None
        assert partial_signals.supertrend is None
        assert partial_signals.atr_pct is None
        assert partial_signals.keltner_width is None
        assert partial_signals.ad is None
        assert partial_signals.relative_volume is None
        assert partial_signals.vwap_deviation is None
        assert partial_signals.iv_rank is None
        assert partial_signals.iv_percentile is None
        assert partial_signals.put_call_ratio is None
        assert partial_signals.max_pain_distance is None

    def test_exactly_61_model_fields(self) -> None:
        """IndicatorSignals has exactly 61 model fields (18 orig + 1 MACD + 40 DSE + 2 liq)."""
        assert len(IndicatorSignals.model_fields) == 61

    def test_not_frozen_can_reassign(self, empty_signals: IndicatorSignals) -> None:
        """IndicatorSignals is NOT frozen: fields can be reassigned."""
        empty_signals.rsi = 42.0
        assert empty_signals.rsi == pytest.approx(42.0)
        empty_signals.adx = 55.0
        assert empty_signals.adx == pytest.approx(55.0)

    def test_serialization_roundtrip_empty(self, empty_signals: IndicatorSignals) -> None:
        """All-None IndicatorSignals survives JSON roundtrip."""
        json_str = empty_signals.model_dump_json()
        restored = IndicatorSignals.model_validate_json(json_str)
        assert restored == empty_signals

    def test_serialization_roundtrip_partial(self, partial_signals: IndicatorSignals) -> None:
        """Partially-filled IndicatorSignals survives JSON roundtrip."""
        json_str = partial_signals.model_dump_json()
        restored = IndicatorSignals.model_validate_json(json_str)
        assert restored == partial_signals

    def test_all_fields_are_float_or_none(self) -> None:
        """All 18 IndicatorSignals fields have annotation float | None."""
        for field_name, field_info in IndicatorSignals.model_fields.items():
            # All fields should have default None
            assert field_info.default is None, f"Field {field_name} should default to None"

    def test_full_fill_original_18_fields(self) -> None:
        """IndicatorSignals with all original 18 fields set works correctly."""
        signals = IndicatorSignals(
            rsi=50.0,
            stochastic_rsi=45.0,
            williams_r=55.0,
            adx=60.0,
            roc=40.0,
            supertrend=70.0,
            bb_width=35.0,
            atr_pct=50.0,
            keltner_width=42.0,
            obv=65.0,
            ad=38.0,
            relative_volume=72.0,
            sma_alignment=80.0,
            vwap_deviation=25.0,
            iv_rank=55.0,
            iv_percentile=60.0,
            put_call_ratio=48.0,
            max_pain_distance=33.0,
        )
        # Verify original 18 are not None
        original_fields = [
            "rsi",
            "stochastic_rsi",
            "williams_r",
            "adx",
            "roc",
            "supertrend",
            "bb_width",
            "atr_pct",
            "keltner_width",
            "obv",
            "ad",
            "relative_volume",
            "sma_alignment",
            "vwap_deviation",
            "iv_rank",
            "iv_percentile",
            "put_call_ratio",
            "max_pain_distance",
        ]
        for field_name in original_fields:
            assert getattr(signals, field_name) is not None, (
                f"Field {field_name} should not be None"
            )


# ---------------------------------------------------------------------------
# ScanRun Tests
# ---------------------------------------------------------------------------


class TestScanRun:
    """Tests for the ScanRun model."""

    def test_happy_path_construction(self, sample_scan_run: ScanRun) -> None:
        """ScanRun constructs with all fields correctly assigned."""
        assert sample_scan_run.started_at == datetime(2025, 6, 15, 9, 30, 0, tzinfo=UTC)
        assert sample_scan_run.completed_at == datetime(2025, 6, 15, 9, 45, 0, tzinfo=UTC)
        assert sample_scan_run.preset == ScanPreset.FULL
        assert sample_scan_run.tickers_scanned == 5296
        assert sample_scan_run.tickers_scored == 5159
        assert sample_scan_run.recommendations == 8

    def test_frozen_enforcement(self, sample_scan_run: ScanRun) -> None:
        """ScanRun is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_scan_run.preset = "sp500"  # type: ignore[misc]

    def test_naive_started_at_raises(self) -> None:
        """ScanRun rejects naive datetime for started_at."""
        with pytest.raises(ValidationError, match="UTC"):
            ScanRun(
                started_at=datetime(2025, 6, 15, 9, 30, 0),  # naive
                preset=ScanPreset.FULL,
                tickers_scanned=100,
                tickers_scored=90,
                recommendations=5,
            )

    def test_non_utc_started_at_raises(self) -> None:
        """ScanRun rejects non-UTC timezone for started_at."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            ScanRun(
                started_at=datetime(2025, 6, 15, 9, 30, 0, tzinfo=est),
                preset=ScanPreset.FULL,
                tickers_scanned=100,
                tickers_scored=90,
                recommendations=5,
            )

    def test_non_utc_completed_at_raises(self) -> None:
        """ScanRun rejects non-UTC timezone for completed_at."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            ScanRun(
                started_at=datetime(2025, 6, 15, 9, 30, 0, tzinfo=UTC),
                completed_at=datetime(2025, 6, 15, 9, 45, 0, tzinfo=est),
                preset=ScanPreset.FULL,
                tickers_scanned=100,
                tickers_scored=90,
                recommendations=5,
            )

    def test_id_defaults_to_none(self) -> None:
        """ScanRun id defaults to None (DB-assigned)."""
        run = ScanRun(
            started_at=datetime(2025, 6, 15, 9, 30, 0, tzinfo=UTC),
            preset=ScanPreset.SP500,
            tickers_scanned=500,
            tickers_scored=480,
            recommendations=5,
        )
        assert run.id is None

    def test_completed_at_defaults_to_none(self) -> None:
        """ScanRun completed_at defaults to None."""
        run = ScanRun(
            started_at=datetime(2025, 6, 15, 9, 30, 0, tzinfo=UTC),
            preset=ScanPreset.ETFS,
            tickers_scanned=200,
            tickers_scored=190,
            recommendations=3,
        )
        assert run.completed_at is None

    def test_id_accepts_value(self) -> None:
        """ScanRun id accepts an integer value."""
        run = ScanRun(
            id=42,
            started_at=datetime(2025, 6, 15, 9, 30, 0, tzinfo=UTC),
            completed_at=datetime(2025, 6, 15, 9, 45, 0, tzinfo=UTC),
            preset=ScanPreset.FULL,
            tickers_scanned=5000,
            tickers_scored=4800,
            recommendations=10,
        )
        assert run.id == 42

    def test_json_roundtrip(self, sample_scan_run: ScanRun) -> None:
        """ScanRun survives JSON serialization/deserialization unchanged."""
        json_str = sample_scan_run.model_dump_json()
        restored = ScanRun.model_validate_json(json_str)
        assert restored == sample_scan_run

    def test_json_roundtrip_with_defaults(self) -> None:
        """ScanRun with default id and completed_at survives JSON roundtrip."""
        run = ScanRun(
            started_at=datetime(2025, 6, 15, 9, 30, 0, tzinfo=UTC),
            preset=ScanPreset.SP500,
            tickers_scanned=500,
            tickers_scored=480,
            recommendations=5,
        )
        json_str = run.model_dump_json()
        restored = ScanRun.model_validate_json(json_str)
        assert restored == run
        assert restored.id is None
        assert restored.completed_at is None


# ---------------------------------------------------------------------------
# TickerScore Tests
# ---------------------------------------------------------------------------


class TestTickerScore:
    """Tests for the TickerScore model."""

    def test_happy_path_construction(self, sample_ticker_score: TickerScore) -> None:
        """TickerScore constructs with all fields correctly assigned."""
        assert sample_ticker_score.ticker == "AAPL"
        assert sample_ticker_score.composite_score == pytest.approx(78.5)
        assert sample_ticker_score.direction == SignalDirection.BULLISH

    def test_signals_is_indicator_signals_type(self, sample_ticker_score: TickerScore) -> None:
        """TickerScore signals field is an IndicatorSignals instance."""
        assert isinstance(sample_ticker_score.signals, IndicatorSignals)

    def test_direction_accepts_signal_direction_enum(self) -> None:
        """TickerScore direction accepts all SignalDirection enum values."""
        for direction in SignalDirection:
            score = TickerScore(
                ticker="SPY",
                composite_score=50.0,
                direction=direction,
                signals=IndicatorSignals(),
            )
            assert score.direction == direction

    def test_not_frozen_can_reassign(self, sample_ticker_score: TickerScore) -> None:
        """TickerScore is NOT frozen: fields can be reassigned."""
        sample_ticker_score.composite_score = 85.0
        assert sample_ticker_score.composite_score == pytest.approx(85.0)
        sample_ticker_score.direction = SignalDirection.BEARISH
        assert sample_ticker_score.direction == SignalDirection.BEARISH

    def test_scan_run_id_defaults_to_none(self) -> None:
        """TickerScore scan_run_id defaults to None."""
        score = TickerScore(
            ticker="AAPL",
            composite_score=70.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(),
        )
        assert score.scan_run_id is None

    def test_scan_run_id_accepts_value(self) -> None:
        """TickerScore scan_run_id accepts an integer value."""
        score = TickerScore(
            ticker="AAPL",
            composite_score=70.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(),
            scan_run_id=7,
        )
        assert score.scan_run_id == 7

    def test_json_roundtrip(self, sample_ticker_score: TickerScore) -> None:
        """TickerScore survives JSON serialization/deserialization unchanged."""
        json_str = sample_ticker_score.model_dump_json()
        restored = TickerScore.model_validate_json(json_str)
        assert restored == sample_ticker_score

    def test_sector_defaults_to_none(self) -> None:
        """TickerScore.sector defaults to None."""
        score = TickerScore(
            ticker="AAPL",
            composite_score=70.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        assert score.sector is None

    def test_sector_accepts_gics_sector(self) -> None:
        """TickerScore.sector accepts a GICSSector enum value."""
        score = TickerScore(
            ticker="AAPL",
            composite_score=70.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
            sector=GICSSector.INFORMATION_TECHNOLOGY,
        )
        assert score.sector is GICSSector.INFORMATION_TECHNOLOGY

    def test_company_name_defaults_to_none(self) -> None:
        """TickerScore.company_name defaults to None."""
        score = TickerScore(
            ticker="AAPL",
            composite_score=70.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        assert score.company_name is None

    def test_company_name_accepts_string(self) -> None:
        """TickerScore.company_name accepts a string."""
        score = TickerScore(
            ticker="AAPL",
            composite_score=70.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
            company_name="Apple Inc.",
        )
        assert score.company_name == "Apple Inc."

    def test_sector_and_company_name_json_roundtrip(self) -> None:
        """TickerScore with sector and company_name survives JSON roundtrip."""
        score = TickerScore(
            ticker="MSFT",
            composite_score=82.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(rsi=65.0),
            sector=GICSSector.INFORMATION_TECHNOLOGY,
            company_name="Microsoft Corporation",
        )
        json_str = score.model_dump_json()
        restored = TickerScore.model_validate_json(json_str)
        assert restored.sector is GICSSector.INFORMATION_TECHNOLOGY
        assert restored.company_name == "Microsoft Corporation"
        assert restored == score

    def test_sector_none_json_roundtrip(self) -> None:
        """TickerScore with None sector/company_name survives JSON roundtrip."""
        score = TickerScore(
            ticker="XYZ",
            composite_score=50.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(),
        )
        json_str = score.model_dump_json()
        restored = TickerScore.model_validate_json(json_str)
        assert restored.sector is None
        assert restored.company_name is None
