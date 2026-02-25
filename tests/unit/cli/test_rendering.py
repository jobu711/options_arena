"""Tests for CLI rendering functions and constants.

Tests verify table structure and row counts -- NOT Rich-rendered text
output, which is terminal-dependent and fragile.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic_ai.usage import RunUsage
from rich.console import Console
from rich.panel import Panel

from options_arena.agents._parsing import DebateResult
from options_arena.cli.rendering import (
    DISCLAIMER,
    render_debate_panels,
    render_health_table,
    render_scan_table,
    render_volatility_panel,
)
from options_arena.models import AgentResponse, MarketContext, TradeThesis, VolatilityThesis
from options_arena.models.enums import (
    ExerciseStyle,
    MacdSignal,
    OptionType,
    PricingModel,
    ScanPreset,
    SignalDirection,
    SpreadType,
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


# ---------------------------------------------------------------------------
# volatility panel rendering
# ---------------------------------------------------------------------------


def test_render_volatility_panel_all_fields() -> None:
    """Panel renders with all optional fields populated and cyan border."""
    thesis = VolatilityThesis(
        iv_assessment="overpriced",
        iv_rank_interpretation="IV rank at 85 is in the top 15%",
        confidence=0.75,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="High IV favors selling premium",
        target_iv_entry=85.0,
        target_iv_exit=50.0,
        suggested_strikes=["185C", "195C"],
        key_vol_factors=["Earnings in 5 days", "IV rank 85"],
        model_used="llama3.1:8b",
    )
    panel = render_volatility_panel(thesis)
    assert isinstance(panel, Panel)
    assert panel.border_style == "cyan"  # type: ignore[union-attr]


def test_render_volatility_panel_minimal() -> None:
    """Panel renders with only required fields (no strategy, targets, minimal factors)."""
    thesis = VolatilityThesis(
        iv_assessment="fair",
        iv_rank_interpretation="IV rank at 45 is near the median",
        confidence=0.5,
        recommended_strategy=None,
        strategy_rationale="No vol play warranted",
        target_iv_entry=None,
        target_iv_exit=None,
        suggested_strikes=[],
        key_vol_factors=["IV near median"],
        model_used="llama3.1:8b",
    )
    panel = render_volatility_panel(thesis)
    assert isinstance(panel, Panel)


# ---------------------------------------------------------------------------
# debate panel rendering — rebuttal
# ---------------------------------------------------------------------------


def _make_mock_debate_result(*, with_rebuttal: bool = False) -> DebateResult:
    """Create a minimal DebateResult for rendering tests."""
    bull = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI at 62.3 indicates bullish momentum.",
        key_points=["RSI trending up", "Volume increasing"],
        risks_cited=["Earnings next week"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )
    bear = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="IV is elevated, limiting upside.",
        key_points=["IV elevated", "Overbought RSI"],
        risks_cited=["Potential reversal"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )
    rebuttal = None
    if with_rebuttal:
        rebuttal = AgentResponse(
            agent_name="bull",
            direction=SignalDirection.BULLISH,
            confidence=0.68,
            argument="IV elevation is temporary and already priced in.",
            key_points=["IV mean-reverting", "Earnings not imminent"],
            risks_cited=["Short-term vol spike possible"],
            contracts_referenced=["AAPL $190 CALL"],
            model_used="test",
        )
    thesis = TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["Momentum"],
        risk_assessment="Moderate risk.",
        recommended_strategy=None,
    )
    ctx = MarketContext(
        ticker="AAPL",
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.2,
        iv_percentile=52.1,
        atm_iv_30d=28.5,
        rsi_14=62.3,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )
    return DebateResult(
        context=ctx,
        bull_response=bull,
        bear_response=bear,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=1000,
        is_fallback=False,
        bull_rebuttal=rebuttal,
    )


def test_render_debate_panels_with_rebuttal(capsys: pytest.CaptureFixture[str]) -> None:
    """render_debate_panels renders BULL REBUTTAL panel when bull_rebuttal is set."""
    result = _make_mock_debate_result(with_rebuttal=True)
    console = Console(force_terminal=True, width=120)
    render_debate_panels(console, result)
    output = capsys.readouterr().out
    assert "BULL REBUTTAL" in output


def test_render_debate_panels_without_rebuttal(capsys: pytest.CaptureFixture[str]) -> None:
    """render_debate_panels omits BULL REBUTTAL panel when bull_rebuttal is None."""
    result = _make_mock_debate_result(with_rebuttal=False)
    console = Console(force_terminal=True, width=120)
    render_debate_panels(console, result)
    output = capsys.readouterr().out
    assert "BULL REBUTTAL" not in output
