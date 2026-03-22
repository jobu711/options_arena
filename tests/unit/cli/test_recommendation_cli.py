"""Tests for CLI debate command rewritten for run_recommendation().

Tests cover CLI routing via CliRunner + mocks, recommendation rendering,
fallback-only flag, export path, and should_recommend gate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.usage import RunUsage
from typer.testing import CliRunner

from options_arena.cli.app import app
from options_arena.models.enums import (
    DeskType,
    ExerciseStyle,
    MacdSignal,
    ScanPreset,
    SignalDirection,
)
from options_arena.models.recommendation import (
    PositionRecommendation,
    RecommendationResult,
    TrendAssessment,
    VolatilityAssessment,
)
from options_arena.models.scan import IndicatorSignals, ScanRun, TickerScore

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(ticker: str = "AAPL", score: float = 75.0) -> TickerScore:
    """Create a TickerScore for testing."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.0),
        scan_run_id=1,
    )


def _make_scan_run() -> ScanRun:
    """Create a ScanRun for testing."""
    return ScanRun(
        id=1,
        started_at=datetime(2026, 3, 22, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 22, 10, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        tickers_scanned=500,
        tickers_scored=50,
        recommendations=5,
    )


def _make_market_context(ticker: str = "AAPL") -> MagicMock:
    """Create a minimal MarketContext mock for RecommendationResult."""
    from options_arena.models.analysis import MarketContext

    return MarketContext(
        ticker=ticker,
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("200.00"),
        price_52w_low=Decimal("140.00"),
        iv_rank=45.0,
        iv_percentile=50.0,
        atm_iv_30d=0.28,
        rsi_14=55.0,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 3, 22, 14, 30, 0, tzinfo=UTC),
    )


def _make_recommendation_result(
    ticker: str = "AAPL",
    *,
    is_fallback: bool = False,
) -> RecommendationResult:
    """Create a minimal RecommendationResult for testing."""
    trend = TrendAssessment(
        desk=DeskType.TREND,
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        summary="Strong uptrend with RSI momentum.",
        key_factors=["RSI trending up", "ADX above 25"],
        risks=["Earnings next week"],
        contracts_referenced=["AAPL 190C 2026-04-18"],
        tools_used=["fetch_quote"],
        model_used="test",
        trend_strength=0.8,
    )
    vol = VolatilityAssessment(
        desk=DeskType.VOLATILITY,
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="IV rank moderate, good entry point.",
        key_factors=["IV rank at 45"],
        risks=["Potential IV expansion"],
        contracts_referenced=["AAPL 190C 2026-04-18"],
        tools_used=["fetch_chain"],
        model_used="test",
    )
    rec = PositionRecommendation(
        ticker=ticker,
        direction=SignalDirection.BULLISH,
        confidence=0.70,
        recommended_contract=f"{ticker} 190C 2026-04-18",
        entry_price=Decimal("5.25"),
        entry_criteria="Enter on pullback to support.",
        exit_criteria="Exit at 50% profit or 30% loss.",
        stop_loss=Decimal("3.50"),
        take_profit=Decimal("7.80"),
        position_size_pct=0.05,
        position_rationale="Conservative size due to earnings.",
        risk_reward_ratio=2.3,
        max_loss_estimate="$175 per contract",
        strategy_rationale="Directional call with limited risk.",
        summary="Bullish momentum with moderate IV entry.",
        key_factors=["RSI at 65", "IV rank 45"],
        risk_assessment="Moderate risk; earnings in 7 days.",
        agent_agreement_score=0.8,
        dissenting_desks=[],
        model_used="test",
    )
    return RecommendationResult(
        context=_make_market_context(ticker),
        assessments=[trend, vol],
        recommendation=rec,
        total_usage=RunUsage(),
        duration_ms=2500,
        is_fallback=is_fallback,
        citation_density=0.5,
    )


# ---------------------------------------------------------------------------
# CLI Routing Tests
# ---------------------------------------------------------------------------


@patch("options_arena.cli.commands._validate_provider_config")
@patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
def test_debate_command_calls_debate_async(
    mock_debate: AsyncMock, _mock_validate: MagicMock
) -> None:
    """Verify debate command invokes _debate_async."""
    mock_debate.return_value = None
    result = runner.invoke(app, ["debate", "AAPL"])
    assert result.exit_code == 0
    mock_debate.assert_awaited_once()


@patch("options_arena.cli.commands._validate_provider_config")
@patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
def test_fallback_only_flag_passed(mock_debate: AsyncMock, _mock_validate: MagicMock) -> None:
    """Verify --fallback-only is passed to _debate_async."""
    mock_debate.return_value = None
    result = runner.invoke(app, ["debate", "AAPL", "--fallback-only"])
    assert result.exit_code == 0
    mock_debate.assert_awaited_once()
    # Third positional arg is fallback_only
    assert mock_debate.call_args[0][2] is True


@patch("options_arena.cli.commands._validate_provider_config")
@patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
def test_provider_flag_passed(mock_debate: AsyncMock, _mock_validate: MagicMock) -> None:
    """Verify --provider anthropic is forwarded to _debate_async."""
    mock_debate.return_value = None
    result = runner.invoke(app, ["debate", "AAPL", "--provider", "anthropic"])
    assert result.exit_code == 0
    mock_debate.assert_awaited_once()
    kwargs = mock_debate.call_args[1]
    assert kwargs.get("provider").value == "anthropic"


# ---------------------------------------------------------------------------
# Recommendation Rendering Tests
# ---------------------------------------------------------------------------


def test_render_recommendation_produces_output() -> None:
    """Verify render_recommendation writes assessment panels and recommendation table."""
    from io import StringIO

    from rich.console import Console

    from options_arena.cli.rendering import render_recommendation

    buf = StringIO()
    test_console = Console(file=buf, width=120, force_terminal=True)
    result = _make_recommendation_result()
    render_recommendation(test_console, result)
    output = buf.getvalue()
    # Should contain assessment desk names and recommendation details
    assert "TREND" in output
    assert "VOLATILITY" in output
    assert "Position Recommendation" in output
    assert "AAPL" in output


def test_render_recommendation_fallback_badge() -> None:
    """Verify fallback badge rendered when is_fallback=True."""
    from io import StringIO

    from rich.console import Console

    from options_arena.cli.rendering import render_recommendation

    buf = StringIO()
    test_console = Console(file=buf, width=120, force_terminal=True)
    result = _make_recommendation_result(is_fallback=True)
    render_recommendation(test_console, result)
    output = buf.getvalue()
    assert "FALLBACK" in output


def test_render_recommendation_empty_assessments() -> None:
    """Verify graceful handling when assessments list is empty."""
    from io import StringIO

    from rich.console import Console

    from options_arena.cli.rendering import render_recommendation

    result = _make_recommendation_result()
    # Create a result with empty assessments
    empty_result = RecommendationResult(
        context=result.context,
        assessments=[],
        recommendation=result.recommendation,
        total_usage=RunUsage(),
        duration_ms=1000,
        is_fallback=False,
    )
    buf = StringIO()
    test_console = Console(file=buf, width=120, force_terminal=True)
    render_recommendation(test_console, empty_result)
    output = buf.getvalue()
    assert "No assessments available" in output


# ---------------------------------------------------------------------------
# should_recommend Gate Tests
# ---------------------------------------------------------------------------


@pytest.mark.critical
def test_should_recommend_gate_below_threshold() -> None:
    """Verify should_recommend returns False when score is below threshold."""
    from options_arena.agents import should_recommend
    from options_arena.models.config import DebateConfig

    config = DebateConfig(min_recommendation_score=30.0)
    low_score = _make_ticker_score("AAPL", score=20.0)
    assert should_recommend(low_score, config) is False


@pytest.mark.critical
def test_should_recommend_gate_above_threshold() -> None:
    """Verify should_recommend returns True when score is above threshold."""
    from options_arena.agents import should_recommend
    from options_arena.models.config import DebateConfig

    config = DebateConfig(min_recommendation_score=30.0)
    high_score = _make_ticker_score("AAPL", score=75.0)
    assert should_recommend(high_score, config) is True


@pytest.mark.critical
@patch("options_arena.cli.commands._validate_provider_config")
@patch("options_arena.cli.commands._recommendation_single", new_callable=AsyncMock)
@patch("options_arena.cli.commands.render_recommendation")
@patch("options_arena.cli.commands.Repository")
@patch("options_arena.cli.commands.Database")
def test_should_recommend_gate_neutral_direction(
    mock_db_cls: MagicMock,
    mock_repo_cls: MagicMock,
    _mock_render: MagicMock,
    mock_rec_single: AsyncMock,
    _mock_validate: MagicMock,
) -> None:
    """Verify should_recommend returns False for neutral direction."""
    mock_db = AsyncMock()
    mock_db_cls.return_value = mock_db

    mock_repo = AsyncMock()
    mock_repo_cls.return_value = mock_repo
    mock_repo.get_latest_scan.return_value = _make_scan_run()
    neutral_score = TickerScore(
        ticker="AAPL",
        composite_score=80.0,
        direction=SignalDirection.NEUTRAL,
        signals=IndicatorSignals(rsi=50.0),
        scan_run_id=1,
    )
    mock_repo.get_scores_for_scan.return_value = [neutral_score]

    runner.invoke(app, ["debate", "AAPL", "--fallback-only"])
    # Neutral direction should be rejected by should_recommend
    mock_rec_single.assert_not_called()


# ---------------------------------------------------------------------------
# Export Tests
# ---------------------------------------------------------------------------


def test_export_recommendation_result_md(tmp_path: MagicMock) -> None:
    """Verify _export_recommendation_result writes a markdown file."""
    from options_arena.cli.commands import _export_recommendation_result

    result = _make_recommendation_result()
    _export_recommendation_result(result, "AAPL", "md", str(tmp_path))

    # Find the written file
    md_files = list(tmp_path.glob("recommendation_AAPL_*.md"))
    assert len(md_files) == 1
    content = md_files[0].read_text(encoding="utf-8")
    assert "Recommendation Report" in content
    assert "AAPL" in content
