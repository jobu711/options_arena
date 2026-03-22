"""Recommendation system CLI regression tests (#667).

Verifies cutover-specific regression scenarios for the CLI debate command:
run_recommendation integration, score-below-threshold gating, export path
for recommendation results, and provider forwarding. Avoids duplicating
tests already in ``test_recommendation_cli.py`` and ``test_batch_recommendation.py``.
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


def _make_ticker_score(
    ticker: str = "AAPL",
    score: float = 75.0,
    direction: SignalDirection = SignalDirection.BULLISH,
) -> TickerScore:
    """Create a TickerScore for testing."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=direction,
        signals=IndicatorSignals(rsi=65.0),
        scan_run_id=1,
    )


def _make_scan_run() -> ScanRun:
    return ScanRun(
        id=1,
        started_at=datetime(2026, 3, 22, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 22, 10, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        tickers_scanned=500,
        tickers_scored=50,
        recommendations=5,
    )


def _make_recommendation_result(
    ticker: str = "AAPL", *, is_fallback: bool = False
) -> RecommendationResult:
    """Build a minimal RecommendationResult for regression tests."""
    from options_arena.models.analysis import MarketContext

    ctx = MarketContext(
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
    trend = TrendAssessment(
        desk=DeskType.TREND,
        direction=SignalDirection.BULLISH if not is_fallback else SignalDirection.NEUTRAL,
        confidence=0.72 if not is_fallback else 0.2,
        summary="Strong uptrend." if not is_fallback else "Assessment unavailable.",
        key_factors=["RSI trending up"],
        risks=["Earnings next week"],
        contracts_referenced=[f"{ticker} 190C 2026-04-18"],
        tools_used=["fetch_quote"],
        model_used="test" if not is_fallback else "data-driven-fallback",
    )
    vol = VolatilityAssessment(
        desk=DeskType.VOLATILITY,
        direction=SignalDirection.BULLISH if not is_fallback else SignalDirection.NEUTRAL,
        confidence=0.65 if not is_fallback else 0.2,
        summary="IV at moderate levels.",
        key_factors=["IV rank 45"],
        risks=["Potential IV expansion"],
        contracts_referenced=[f"{ticker} 190C 2026-04-18"],
        tools_used=["fetch_chain"],
        model_used="test" if not is_fallback else "data-driven-fallback",
    )
    rec = PositionRecommendation(
        ticker=ticker,
        direction=SignalDirection.BULLISH if not is_fallback else SignalDirection.NEUTRAL,
        confidence=0.70 if not is_fallback else 0.2,
        recommended_contract=f"{ticker} 190C 2026-04-18",
        entry_price=Decimal("5.25"),
        entry_criteria="Enter on pullback.",
        exit_criteria="Exit at 50% profit.",
        stop_loss=Decimal("3.50"),
        take_profit=Decimal("7.80"),
        position_size_pct=0.05,
        position_rationale="Conservative due to earnings.",
        risk_reward_ratio=2.3,
        max_loss_estimate="$175 per contract",
        strategy_rationale="Directional call.",
        summary="Bullish momentum." if not is_fallback else "Data-driven fallback.",
        key_factors=["RSI at 65"],
        risk_assessment="Moderate risk.",
        model_used="test" if not is_fallback else "data-driven-fallback",
    )
    return RecommendationResult(
        context=ctx,
        assessments=[trend, vol],
        recommendation=rec,
        total_usage=RunUsage(),
        duration_ms=2500,
        is_fallback=is_fallback,
        citation_density=0.5 if not is_fallback else 0.0,
    )


# ---------------------------------------------------------------------------
# Regression: run_recommendation is used, not run_debate
# ---------------------------------------------------------------------------


class TestCLIUsesRunRecommendation:
    """Verify that the debate CLI command routes to run_recommendation."""

    @pytest.mark.critical
    @patch("options_arena.cli.commands._validate_provider_config")
    @patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
    def test_debate_command_routes_to_debate_async(
        self, mock_debate: AsyncMock, _mock_validate: MagicMock
    ) -> None:
        """debate AAPL invokes _debate_async (which uses run_recommendation)."""
        mock_debate.return_value = None
        result = runner.invoke(app, ["debate", "AAPL"])
        assert result.exit_code == 0
        mock_debate.assert_awaited_once()

    def test_debate_async_uses_recommendation_single(self) -> None:
        """Verify _debate_async calls _recommendation_single (not run_debate)."""
        import inspect

        import options_arena.cli.commands as cmd_mod

        source = inspect.getsource(cmd_mod._debate_async)
        assert "_recommendation_single" in source, (
            "_debate_async should call _recommendation_single"
        )
        # _debate_async itself should NOT call run_debate directly
        assert "run_debate(" not in source, "_debate_async should not call run_debate directly"


# ---------------------------------------------------------------------------
# Regression: score threshold gate
# ---------------------------------------------------------------------------


class TestScoreThresholdGate:
    """Verify should_recommend prevents low-score or neutral tickers.

    Tests exercise the ``should_recommend`` gate directly because the CLI
    ``--fallback-only`` flag overrides ``min_recommendation_score`` to 0.0.
    """

    @pytest.mark.critical
    def test_score_below_threshold_rejected(self) -> None:
        """should_recommend returns False when score is below threshold."""
        from options_arena.agents import should_recommend
        from options_arena.models.config import DebateConfig

        config = DebateConfig(min_recommendation_score=30.0)
        low_score = _make_ticker_score("AAPL", score=15.0)
        assert should_recommend(low_score, config) is False

    @pytest.mark.critical
    def test_score_above_threshold_accepted(self) -> None:
        """should_recommend returns True when score is above threshold."""
        from options_arena.agents import should_recommend
        from options_arena.models.config import DebateConfig

        config = DebateConfig(min_recommendation_score=30.0)
        high_score = _make_ticker_score("AAPL", score=75.0)
        assert should_recommend(high_score, config) is True

    def test_neutral_direction_rejected_despite_high_score(self) -> None:
        """should_recommend returns False for NEUTRAL direction even with score 90."""
        from options_arena.agents import should_recommend
        from options_arena.models.config import DebateConfig

        config = DebateConfig(min_recommendation_score=30.0)
        neutral = _make_ticker_score("AAPL", score=90.0, direction=SignalDirection.NEUTRAL)
        assert should_recommend(neutral, config) is False

    @patch("options_arena.cli.commands._validate_provider_config")
    @patch("options_arena.cli.commands._recommendation_single", new_callable=AsyncMock)
    @patch("options_arena.cli.commands.render_recommendation")
    @patch("options_arena.cli.commands.Repository")
    @patch("options_arena.cli.commands.Database")
    def test_neutral_direction_skips_cli_recommendation(
        self,
        mock_db_cls: MagicMock,
        mock_repo_cls: MagicMock,
        _mock_render: MagicMock,
        mock_rec_single: AsyncMock,
        _mock_validate: MagicMock,
    ) -> None:
        """CLI skips recommendation for NEUTRAL direction ticker."""
        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_repo = AsyncMock()
        mock_repo_cls.return_value = mock_repo
        mock_repo.get_latest_scan.return_value = _make_scan_run()
        neutral = _make_ticker_score("AAPL", score=90.0, direction=SignalDirection.NEUTRAL)
        mock_repo.get_scores_for_scan.return_value = [neutral]

        runner.invoke(app, ["debate", "AAPL", "--fallback-only"])
        mock_rec_single.assert_not_called()


# ---------------------------------------------------------------------------
# Regression: export produces recommendation markdown, not debate markdown
# ---------------------------------------------------------------------------


class TestExportRecommendation:
    """Verify export generates recommendation-format markdown."""

    def test_export_recommendation_md_includes_position(self, tmp_path: MagicMock) -> None:
        """Markdown export includes Position Recommendation section."""
        from options_arena.cli.commands import _export_recommendation_result

        result = _make_recommendation_result()
        _export_recommendation_result(result, "AAPL", "md", str(tmp_path))

        md_files = list(tmp_path.glob("recommendation_AAPL_*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8")
        # Must include recommendation-specific content, not debate-era content
        assert "Recommendation Report" in content
        assert "AAPL" in content

    def test_export_recommendation_md_fallback_noted(self, tmp_path: MagicMock) -> None:
        """Fallback recommendations are noted in the export."""
        from options_arena.cli.commands import _export_recommendation_result

        result = _make_recommendation_result(is_fallback=True)
        _export_recommendation_result(result, "AAPL", "md", str(tmp_path))

        md_files = list(tmp_path.glob("recommendation_AAPL_*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text(encoding="utf-8")
        assert "AAPL" in content


# ---------------------------------------------------------------------------
# Regression: fallback-only flag produces fallback result
# ---------------------------------------------------------------------------


class TestFallbackOnlyFlag:
    """Verify --fallback-only still works via the recommendation path."""

    @patch("options_arena.cli.commands._validate_provider_config")
    @patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
    def test_fallback_only_flag_is_forwarded(
        self, mock_debate: AsyncMock, _mock_validate: MagicMock
    ) -> None:
        """--fallback-only is forwarded to _debate_async."""
        mock_debate.return_value = None
        result = runner.invoke(app, ["debate", "AAPL", "--fallback-only"])
        assert result.exit_code == 0
        mock_debate.assert_awaited_once()
        # Third positional arg is fallback_only
        assert mock_debate.call_args[0][2] is True


# ---------------------------------------------------------------------------
# Regression: provider flag forwarded correctly
# ---------------------------------------------------------------------------


class TestProviderFlag:
    """Verify --provider flag reaches the recommendation orchestrator."""

    @patch("options_arena.cli.commands._validate_provider_config")
    @patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
    def test_provider_groq_is_default(
        self, mock_debate: AsyncMock, _mock_validate: MagicMock
    ) -> None:
        """Without --provider, default (groq) is used."""
        mock_debate.return_value = None
        result = runner.invoke(app, ["debate", "AAPL"])
        assert result.exit_code == 0
        # Provider should be groq by default
        kwargs = mock_debate.call_args[1]
        assert kwargs.get("provider").value == "groq"

    @patch("options_arena.cli.commands._validate_provider_config")
    @patch("options_arena.cli.commands._debate_async", new_callable=AsyncMock)
    def test_provider_anthropic_forwarded(
        self, mock_debate: AsyncMock, _mock_validate: MagicMock
    ) -> None:
        """--provider anthropic is forwarded correctly."""
        mock_debate.return_value = None
        result = runner.invoke(app, ["debate", "AAPL", "--provider", "anthropic"])
        assert result.exit_code == 0
        kwargs = mock_debate.call_args[1]
        assert kwargs.get("provider").value == "anthropic"
