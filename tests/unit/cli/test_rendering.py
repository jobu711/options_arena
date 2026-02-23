"""Tests for CLI rendering functions and constants.

Tests verify table structure and row counts -- NOT Rich-rendered text
output, which is terminal-dependent and fragile.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from options_arena.cli.rendering import DISCLAIMER, render_health_table, render_scan_table
from options_arena.models.enums import (
    ExerciseStyle,
    OptionType,
    PricingModel,
    ScanPreset,
    SignalDirection,
)
from options_arena.models.health import HealthStatus
from options_arena.models.options import OptionGreeks
from options_arena.models.scan import IndicatorSignals, ScanRun, TickerScore
from options_arena.scan.models import ScanResult


def _make_health_status(
    name: str,
    *,
    available: bool = True,
    latency_ms: float | None = 50.0,
    error: str | None = None,
) -> HealthStatus:
    """Create a HealthStatus for testing."""
    return HealthStatus(
        service_name=name,
        available=available,
        latency_ms=latency_ms,
        error=error,
        checked_at=datetime.now(UTC),
    )


def _make_mock_scan_run() -> ScanRun:
    """Create a ScanRun for testing."""
    return ScanRun(
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        preset=ScanPreset.SP500,
        tickers_scanned=100,
        tickers_scored=50,
        recommendations=1,
    )


def test_render_health_table_columns() -> None:
    """Health table has exactly 4 columns: Service, Status, Latency, Error."""
    statuses = [_make_health_status("yfinance")]
    table = render_health_table(statuses)
    assert len(table.columns) == 4
    column_names = [col.header for col in table.columns]  # type: ignore[union-attr]
    assert column_names == ["Service", "Status", "Latency", "Error"]


def test_render_health_table_mixed_statuses() -> None:
    """Table contains one row per HealthStatus."""
    statuses = [
        _make_health_status("yfinance", available=True),
        _make_health_status("fred", available=False, error="timeout"),
        _make_health_status("ollama", available=True, latency_ms=None),
    ]
    table = render_health_table(statuses)
    assert table.row_count == 3


def test_disclaimer_constant_exists() -> None:
    """DISCLAIMER is a non-empty string."""
    assert isinstance(DISCLAIMER, str)
    assert len(DISCLAIMER) > 0
    assert "financial advice" in DISCLAIMER.lower() or "educational" in DISCLAIMER.lower()


# ---------------------------------------------------------------------------
# scan table rendering
# ---------------------------------------------------------------------------


def test_render_scan_table_columns() -> None:
    """Scan table has exactly 10 columns."""
    result = ScanResult(
        scan_run=_make_mock_scan_run(),
        scores=[],
        recommendations={},
        risk_free_rate=0.045,
        phases_completed=4,
    )
    table = render_scan_table(result)
    assert len(table.columns) == 10
    column_names = [col.header for col in table.columns]  # type: ignore[union-attr]
    assert column_names == [
        "Ticker",
        "Score",
        "Direction",
        "Type",
        "Strike",
        "Exp",
        "DTE",
        "Delta",
        "IV",
        "Bid/Ask",
    ]


def test_render_scan_table_with_results() -> None:
    """Scan table renders one row per scored ticker with contract data."""
    from options_arena.models.options import OptionContract

    mock_greeks = OptionGreeks(
        delta=0.35,
        gamma=0.02,
        theta=-0.05,
        vega=0.15,
        rho=0.01,
        pricing_model=PricingModel.BAW,
    )
    mock_contract = OptionContract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("185.00"),
        expiration=date(2026, 4, 17),
        bid=Decimal("2.45"),
        ask=Decimal("2.65"),
        last=Decimal("2.55"),
        volume=500,
        open_interest=2000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.321,
        greeks=mock_greeks,
    )
    mock_score = TickerScore(
        ticker="AAPL",
        composite_score=87.3,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(),
    )
    result = ScanResult(
        scan_run=_make_mock_scan_run(),
        scores=[mock_score],
        recommendations={"AAPL": [mock_contract]},
        risk_free_rate=0.045,
        phases_completed=4,
    )
    table = render_scan_table(result)
    assert table.row_count == 1


def test_render_scan_table_no_contracts() -> None:
    """Scored ticker with no contract shows '--' placeholders."""
    mock_score = TickerScore(
        ticker="TSLA",
        composite_score=65.0,
        direction=SignalDirection.BEARISH,
        signals=IndicatorSignals(),
    )
    result = ScanResult(
        scan_run=_make_mock_scan_run(),
        scores=[mock_score],
        recommendations={},
        risk_free_rate=0.045,
        phases_completed=4,
    )
    table = render_scan_table(result)
    assert table.row_count == 1
