"""Unit tests for options_arena.scan.models.

Tests for the four pipeline-internal models:
  UniverseResult, ScoringResult, OptionsResult, ScanResult.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models import (
    OHLCV,
    IndicatorSignals,
    OptionContract,
    ScanRun,
    TickerScore,
)
from options_arena.models.enums import (
    ExerciseStyle,
    OptionType,
    ScanPreset,
    SignalDirection,
)
from options_arena.scan.models import (
    OptionsResult,
    ScanResult,
    ScoringResult,
    UniverseResult,
)

# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------


def _make_ohlcv(ticker: str = "AAPL", day: int = 1) -> OHLCV:
    """Create a minimal valid OHLCV bar."""
    return OHLCV(
        ticker=ticker,
        date=date(2025, 1, day),
        open=Decimal("150.00"),
        high=Decimal("155.00"),
        low=Decimal("149.00"),
        close=Decimal("153.00"),
        volume=1_000_000,
        adjusted_close=Decimal("153.00"),
    )


def _make_ticker_score(
    ticker: str = "AAPL",
    composite_score: float = 75.0,
    direction: SignalDirection = SignalDirection.BULLISH,
) -> TickerScore:
    """Create a minimal valid TickerScore."""
    return TickerScore(
        ticker=ticker,
        composite_score=composite_score,
        direction=direction,
        signals=IndicatorSignals(),
    )


def _make_scan_run(
    scan_id: int | None = None,
    recommendations: int = 5,
) -> ScanRun:
    """Create a minimal valid ScanRun."""
    return ScanRun(
        id=scan_id,
        started_at=datetime.now(UTC),
        preset=ScanPreset.FULL,
        tickers_scanned=100,
        tickers_scored=80,
        recommendations=recommendations,
    )


def _make_option_contract(ticker: str = "AAPL") -> OptionContract:
    """Create a minimal valid OptionContract."""
    return OptionContract(
        ticker=ticker,
        option_type=OptionType.CALL,
        strike=Decimal("155.00"),
        expiration=date(2025, 3, 21),
        bid=Decimal("3.50"),
        ask=Decimal("3.80"),
        last=Decimal("3.65"),
        volume=500,
        open_interest=2000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.25,
    )


# ---------------------------------------------------------------------------
# UniverseResult
# ---------------------------------------------------------------------------


class TestUniverseResult:
    def test_construction_with_valid_data(self) -> None:
        bars = [_make_ohlcv("AAPL", day=1), _make_ohlcv("AAPL", day=2)]
        result = UniverseResult(
            tickers=["AAPL", "MSFT", "GOOG"],
            ohlcv_map={"AAPL": bars},
            sp500_sectors={"AAPL": "Information Technology"},
            failed_count=1,
            filtered_count=1,
        )

        assert result.tickers == ["AAPL", "MSFT", "GOOG"]
        assert len(result.ohlcv_map["AAPL"]) == 2
        assert result.sp500_sectors["AAPL"] == "Information Technology"
        assert result.failed_count == 1
        assert result.filtered_count == 1

    def test_empty_ohlcv_map_is_valid(self) -> None:
        result = UniverseResult(
            tickers=["AAPL"],
            ohlcv_map={},
            sp500_sectors={},
            failed_count=1,
            filtered_count=0,
        )

        assert result.ohlcv_map == {}

    def test_empty_sp500_sectors_is_valid(self) -> None:
        result = UniverseResult(
            tickers=["XYZ"],
            ohlcv_map={"XYZ": [_make_ohlcv("XYZ")]},
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )

        assert result.sp500_sectors == {}

    def test_ohlcv_objects_are_accessible(self) -> None:
        bar = _make_ohlcv("MSFT")
        result = UniverseResult(
            tickers=["MSFT"],
            ohlcv_map={"MSFT": [bar]},
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )

        retrieved = result.ohlcv_map["MSFT"][0]
        assert retrieved.ticker == "MSFT"
        assert retrieved.close == Decimal("153.00")


# ---------------------------------------------------------------------------
# ScoringResult
# ---------------------------------------------------------------------------


class TestScoringResult:
    def test_construction_with_scores_and_raw_signals(self) -> None:
        score = _make_ticker_score("AAPL", 80.0, SignalDirection.BULLISH)
        raw = IndicatorSignals(rsi=45.0, adx=22.0, sma_alignment=0.7)
        result = ScoringResult(
            scores=[score],
            raw_signals={"AAPL": raw},
        )

        assert len(result.scores) == 1
        assert result.scores[0].ticker == "AAPL"
        assert result.raw_signals["AAPL"].rsi == 45.0
        assert result.raw_signals["AAPL"].adx == 22.0

    def test_empty_scores_list_is_valid(self) -> None:
        result = ScoringResult(
            scores=[],
            raw_signals={},
        )

        assert result.scores == []
        assert result.raw_signals == {}

    def test_raw_signals_are_not_normalized(self) -> None:
        """Verify raw_signals stores absolute values, not 0-100 percentile ranks."""
        raw = IndicatorSignals(adx=12.5, rsi=68.3, sma_alignment=-0.3)
        result = ScoringResult(
            scores=[_make_ticker_score()],
            raw_signals={"AAPL": raw},
        )

        # ADX=12.5 and sma_alignment=-0.3 are clearly raw values, not percentile ranks
        assert result.raw_signals["AAPL"].adx == 12.5
        assert result.raw_signals["AAPL"].sma_alignment == -0.3


# ---------------------------------------------------------------------------
# OptionsResult
# ---------------------------------------------------------------------------


class TestOptionsResult:
    def test_construction_with_recommendations(self) -> None:
        contract = _make_option_contract("AAPL")
        result = OptionsResult(
            recommendations={"AAPL": [contract]},
            risk_free_rate=0.043,
        )

        assert len(result.recommendations["AAPL"]) == 1
        assert result.recommendations["AAPL"][0].ticker == "AAPL"
        assert result.risk_free_rate == 0.043

    def test_empty_recommendations_is_valid(self) -> None:
        result = OptionsResult(
            recommendations={},
            risk_free_rate=0.05,
        )

        assert result.recommendations == {}
        assert result.risk_free_rate == 0.05

    def test_ticker_with_zero_contracts(self) -> None:
        """A ticker can have an empty list (no contracts passed filter)."""
        result = OptionsResult(
            recommendations={"AAPL": []},
            risk_free_rate=0.043,
        )

        assert result.recommendations["AAPL"] == []


# ---------------------------------------------------------------------------
# ScanResult
# ---------------------------------------------------------------------------


class TestScanResult:
    def test_construction_with_all_fields(self) -> None:
        scan_run = _make_scan_run(scan_id=1, recommendations=1)
        score = _make_ticker_score("AAPL")
        contract = _make_option_contract("AAPL")

        result = ScanResult(
            scan_run=scan_run,
            scores=[score],
            recommendations={"AAPL": [contract]},
            risk_free_rate=0.043,
            cancelled=False,
            phases_completed=4,
        )

        assert result.scan_run.id == 1
        assert len(result.scores) == 1
        assert result.scores[0].ticker == "AAPL"
        assert len(result.recommendations["AAPL"]) == 1
        assert result.risk_free_rate == 0.043
        assert result.cancelled is False
        assert result.phases_completed == 4

    def test_default_cancelled_is_false(self) -> None:
        result = ScanResult(
            scan_run=_make_scan_run(),
            scores=[],
            recommendations={},
            risk_free_rate=0.05,
        )

        assert result.cancelled is False

    def test_default_phases_completed_is_zero(self) -> None:
        result = ScanResult(
            scan_run=_make_scan_run(),
            scores=[],
            recommendations={},
            risk_free_rate=0.05,
        )

        assert result.phases_completed == 0

    def test_phases_completed_range_zero_to_four(self) -> None:
        for phase in range(5):
            result = ScanResult(
                scan_run=_make_scan_run(),
                scores=[],
                recommendations={},
                risk_free_rate=0.05,
                phases_completed=phase,
            )
            assert result.phases_completed == phase

    def test_cancelled_pipeline_with_partial_progress(self) -> None:
        result = ScanResult(
            scan_run=_make_scan_run(),
            scores=[_make_ticker_score("AAPL")],
            recommendations={},
            risk_free_rate=0.05,
            cancelled=True,
            phases_completed=2,
        )

        assert result.cancelled is True
        assert result.phases_completed == 2
        assert len(result.scores) == 1

    def test_scan_run_id_none_before_persist(self) -> None:
        """scan_run.id is None before the DB layer assigns an ID."""
        scan_run = _make_scan_run(scan_id=None)
        result = ScanResult(
            scan_run=scan_run,
            scores=[],
            recommendations={},
            risk_free_rate=0.05,
        )

        assert result.scan_run.id is None

    def test_scan_run_id_populated_after_persist(self) -> None:
        """scan_run.id is an int after DB persist."""
        scan_run = _make_scan_run(scan_id=42)
        result = ScanResult(
            scan_run=scan_run,
            scores=[],
            recommendations={},
            risk_free_rate=0.05,
        )

        assert result.scan_run.id == 42

    def test_phases_completed_rejects_negative(self) -> None:
        """phases_completed below 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ScanResult(
                scan_run=_make_scan_run(),
                scores=[],
                recommendations={},
                risk_free_rate=0.05,
                phases_completed=-1,
            )

    def test_phases_completed_rejects_above_four(self) -> None:
        """phases_completed above 4 raises ValidationError."""
        with pytest.raises(ValidationError):
            ScanResult(
                scan_run=_make_scan_run(),
                scores=[],
                recommendations={},
                risk_free_rate=0.05,
                phases_completed=5,
            )

    def test_importable_from_package(self) -> None:
        """ScanResult is re-exported from the scan package."""
        from options_arena.scan import ScanResult as ReExported

        assert ReExported is ScanResult
