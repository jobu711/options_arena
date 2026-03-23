"""Integration tests for the token attribution pipeline.

Verifies end-to-end token flow: desk runner -> orchestrator -> DeskMetrics ->
RecommendationResult.  Uses TestModel for all agent calls; does not hit real APIs.

Tests in this file exercise the full recommendation orchestrator pipeline with
TestModel overrides to verify that token usage data propagates correctly from
desk runners through to the final RecommendationResult.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from options_arena.agents.recommendation_orchestrator import (
    _compute_recommendation_cost,
    run_recommendation,
)
from options_arena.models import (
    AgencyConfig,
    AppSettings,
    DebateConfig,
    DeskRunStatus,
    DeskType,
    DividendSource,
    ExerciseStyle,
    IndicatorSignals,
    ModelTier,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
)
from options_arena.models.recommendation import (
    DeskMetrics,
    DomainAssessment,
    PositionRecommendation,
    RecommendationCost,
    RecommendationResult,
)

models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ticker_score() -> TickerScore:
    """Bullish TickerScore for AAPL."""
    return TickerScore(
        ticker="AAPL",
        composite_score=72.5,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(
            rsi=62.3,
            adx=28.4,
            sma_alignment=0.7,
            bb_width=42.1,
            atr_pct=15.3,
            obv=65.0,
            relative_volume=55.0,
        ),
        scan_run_id=1,
    )


@pytest.fixture()
def option_contract() -> OptionContract:
    """AAPL call contract with Greeks."""
    return OptionContract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("190.00"),
        expiration=date.today() + timedelta(days=45),
        bid=Decimal("4.50"),
        ask=Decimal("4.80"),
        last=Decimal("4.65"),
        volume=1500,
        open_interest=12000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.285,
        greeks=OptionGreeks(
            delta=0.35,
            gamma=0.025,
            theta=-0.045,
            vega=0.32,
            rho=0.08,
            pricing_model=PricingModel.BAW,
        ),
    )


@pytest.fixture()
def quote() -> Quote:
    """AAPL quote snapshot."""
    return Quote(
        ticker="AAPL",
        price=Decimal("185.50"),
        bid=Decimal("185.48"),
        ask=Decimal("185.52"),
        volume=42_000_000,
        timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture()
def ticker_info() -> TickerInfo:
    """AAPL ticker info."""
    return TickerInfo(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Information Technology",
        market_cap=2_800_000_000_000,
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal("185.50"),
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("164.08"),
    )


@pytest.fixture()
def settings() -> AppSettings:
    """AppSettings with reduced timeouts for fast tests."""
    return AppSettings(
        debate=DebateConfig(
            agent_timeout=10.0,
            max_total_duration=30.0,
        ),
        agency=AgencyConfig(
            agent_timeout=10.0,
            desk_parallelism=6,
        ),
    )


@pytest.fixture()
def repo() -> MagicMock:
    """Mock Repository with async methods."""
    mock_repo = MagicMock()
    mock_repo.save_recommendation = AsyncMock(return_value=1)
    mock_repo.save_agent_predictions = AsyncMock()
    mock_repo.get_strategy_rules = AsyncMock(return_value=[])
    return mock_repo


@pytest.fixture()
def market_data() -> MagicMock:
    """Mock MarketDataService."""
    return MagicMock()


@pytest.fixture()
def options_data() -> MagicMock:
    """Mock OptionsDataService."""
    return MagicMock()


def _enter_overrides(agents: list[object]) -> list[object]:
    """Enter TestModel overrides for a list of agents."""
    overrides = [a.override(model=TestModel()) for a in agents]  # type: ignore[union-attr]
    for o in overrides:
        o.__enter__()
    return overrides


def _exit_overrides(overrides: list[object]) -> None:
    """Exit TestModel overrides in reverse order."""
    for o in reversed(overrides):
        o.__exit__(None, None, None)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Tests: Full pipeline token attribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTokenAttributionIntegration:
    """Integration tests verifying end-to-end token attribution pipeline."""

    @pytest.mark.critical
    async def test_full_pipeline_tokens_flow(
        self,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo: MagicMock,
        market_data: MagicMock,
        options_data: MagicMock,
    ) -> None:
        """Verify tokens propagate from desk runners through to RecommendationResult."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import fundamental_desk_recommend
        from options_arena.agents.risk_desk import risk_desk_recommend
        from options_arena.agents.synthesis_agent import synthesis_agent
        from options_arena.agents.trend_desk import trend_desk_recommend
        from options_arena.agents.volatility_desk import vol_desk_recommend

        agents = [
            trend_desk_recommend,
            vol_desk_recommend,
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = _enter_overrides(agents)
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo,
                market_data=market_data,
                options_data=options_data,
            )
        finally:
            _exit_overrides(overrides)

        assert isinstance(result, RecommendationResult)
        assert isinstance(result.recommendation, PositionRecommendation)

        # desk_metrics should have one entry per desk (6 desks)
        assert len(result.desk_metrics) == 6

        # Each desk metric should have non-negative token counts
        for metric in result.desk_metrics:
            assert isinstance(metric, DeskMetrics)
            assert metric.input_tokens >= 0
            assert metric.output_tokens >= 0
            assert metric.duration_ms >= 0

        # total_usage should aggregate tokens from desk metrics
        assert isinstance(result.total_usage, RunUsage)
        total_in = sum(m.input_tokens for m in result.desk_metrics)
        total_out = sum(m.output_tokens for m in result.desk_metrics)
        assert result.total_usage.input_tokens == total_in
        assert result.total_usage.output_tokens == total_out

    async def test_cost_populated_with_default_model(
        self,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo: MagicMock,
        market_data: MagicMock,
        options_data: MagicMock,
    ) -> None:
        """Verify cost is computed using default model rate when routing disabled."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import fundamental_desk_recommend
        from options_arena.agents.risk_desk import risk_desk_recommend
        from options_arena.agents.synthesis_agent import synthesis_agent
        from options_arena.agents.trend_desk import trend_desk_recommend
        from options_arena.agents.volatility_desk import vol_desk_recommend

        agents = [
            trend_desk_recommend,
            vol_desk_recommend,
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = _enter_overrides(agents)
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo,
                market_data=market_data,
                options_data=options_data,
            )
        finally:
            _exit_overrides(overrides)

        # Cost should always be computed (never None)
        assert result.cost is not None
        assert isinstance(result.cost, RecommendationCost)
        assert result.cost.total_cost_usd >= 0.0
        assert result.cost.total_input_tokens >= 0
        assert result.cost.total_output_tokens >= 0

    async def test_desk_metrics_count_matches_desks(
        self,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo: MagicMock,
        market_data: MagicMock,
        options_data: MagicMock,
    ) -> None:
        """Verify desk_metrics list has one entry per desk (6 desks)."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import fundamental_desk_recommend
        from options_arena.agents.risk_desk import risk_desk_recommend
        from options_arena.agents.synthesis_agent import synthesis_agent
        from options_arena.agents.trend_desk import trend_desk_recommend
        from options_arena.agents.volatility_desk import vol_desk_recommend

        agents = [
            trend_desk_recommend,
            vol_desk_recommend,
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = _enter_overrides(agents)
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo,
                market_data=market_data,
                options_data=options_data,
            )
        finally:
            _exit_overrides(overrides)

        assert len(result.desk_metrics) == 6

        # Verify all 6 expected desks are represented
        desk_types = {m.desk for m in result.desk_metrics}
        expected_desks = {
            DeskType.TREND,
            DeskType.VOLATILITY,
            DeskType.FLOW,
            DeskType.FUNDAMENTAL,
            DeskType.RISK,
            DeskType.CONTRARIAN,
        }
        assert desk_types == expected_desks

    async def test_total_usage_equals_sum_of_desks(
        self,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo: MagicMock,
        market_data: MagicMock,
        options_data: MagicMock,
    ) -> None:
        """Verify total_usage input/output tokens equal sum of desk metrics."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import fundamental_desk_recommend
        from options_arena.agents.risk_desk import risk_desk_recommend
        from options_arena.agents.synthesis_agent import synthesis_agent
        from options_arena.agents.trend_desk import trend_desk_recommend
        from options_arena.agents.volatility_desk import vol_desk_recommend

        agents = [
            trend_desk_recommend,
            vol_desk_recommend,
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = _enter_overrides(agents)
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo,
                market_data=market_data,
                options_data=options_data,
            )
        finally:
            _exit_overrides(overrides)

        expected_input = sum(m.input_tokens for m in result.desk_metrics)
        expected_output = sum(m.output_tokens for m in result.desk_metrics)

        assert result.total_usage.input_tokens == expected_input
        assert result.total_usage.output_tokens == expected_output

    async def test_desk_metrics_have_model_info(
        self,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo: MagicMock,
        market_data: MagicMock,
        options_data: MagicMock,
    ) -> None:
        """Verify each DeskMetrics has model tier and model name populated."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import fundamental_desk_recommend
        from options_arena.agents.risk_desk import risk_desk_recommend
        from options_arena.agents.synthesis_agent import synthesis_agent
        from options_arena.agents.trend_desk import trend_desk_recommend
        from options_arena.agents.volatility_desk import vol_desk_recommend

        agents = [
            trend_desk_recommend,
            vol_desk_recommend,
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = _enter_overrides(agents)
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo,
                market_data=market_data,
                options_data=options_data,
            )
        finally:
            _exit_overrides(overrides)

        for metric in result.desk_metrics:
            assert isinstance(metric.model_tier, ModelTier)
            assert metric.model_used  # non-empty string
            assert isinstance(metric.status, DeskRunStatus)

    async def test_assessment_summary_populated(
        self,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo: MagicMock,
        market_data: MagicMock,
        options_data: MagicMock,
    ) -> None:
        """Verify assessment_summary is computed between Phase 1 and Phase 2."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import fundamental_desk_recommend
        from options_arena.agents.risk_desk import risk_desk_recommend
        from options_arena.agents.synthesis_agent import synthesis_agent
        from options_arena.agents.trend_desk import trend_desk_recommend
        from options_arena.agents.volatility_desk import vol_desk_recommend

        agents = [
            trend_desk_recommend,
            vol_desk_recommend,
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = _enter_overrides(agents)
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo,
                market_data=market_data,
                options_data=options_data,
            )
        finally:
            _exit_overrides(overrides)

        assert result.assessment_summary is not None
        assert 0.0 <= result.assessment_summary.avg_confidence <= 1.0
        assert len(result.assessment_summary.direction_votes) > 0


# ---------------------------------------------------------------------------
# Tests: Fallback token attribution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFallbackTokenAttribution:
    """Tests verifying token attribution when desks fall back."""

    async def test_all_desks_fallback_zero_tokens(
        self,
        monkeypatch: pytest.MonkeyPatch,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo: MagicMock,
        market_data: MagicMock,
        options_data: MagicMock,
    ) -> None:
        """All desk failures produce DeskMetrics with zero tokens and $0 cost.

        Monkepatches ``_DESK_RUNNERS`` directly because the list captures function
        references at module import time — patching module-level names after import
        does not change the references already stored in the list.
        """
        from options_arena.agents import recommendation_orchestrator as orch
        from options_arena.agents._desk_deps import DeskDeps
        from options_arena.agents.synthesis_agent import synthesis_agent

        async def _failing_desk(
            deps: DeskDeps, **kwargs: object
        ) -> tuple[DomainAssessment, RunUsage]:
            raise RuntimeError("Desk failed")

        # Replace _DESK_RUNNERS with failing runners for all 6 desks
        failing_runners = [
            (DeskType.TREND, _failing_desk),
            (DeskType.VOLATILITY, _failing_desk),
            (DeskType.FLOW, _failing_desk),
            (DeskType.FUNDAMENTAL, _failing_desk),
            (DeskType.RISK, _failing_desk),
            (DeskType.CONTRARIAN, _failing_desk),
        ]
        monkeypatch.setattr(orch, "_DESK_RUNNERS", failing_runners)

        with synthesis_agent.override(model=TestModel()):
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo,
                market_data=market_data,
                options_data=options_data,
            )

        assert isinstance(result, RecommendationResult)
        assert len(result.desk_metrics) == 6

        # All desks should be FALLBACK status with zero tokens
        for metric in result.desk_metrics:
            assert metric.status == DeskRunStatus.FALLBACK
            assert metric.input_tokens == 0
            assert metric.output_tokens == 0

        # Total usage should be zero
        assert result.total_usage.input_tokens == 0
        assert result.total_usage.output_tokens == 0

        # Cost should still be computed (just $0.00)
        assert result.cost is not None
        assert result.cost.total_cost_usd == pytest.approx(0.0)
        assert result.cost.total_input_tokens == 0
        assert result.cost.total_output_tokens == 0

    async def test_partial_failure_mixed_tokens(
        self,
        monkeypatch: pytest.MonkeyPatch,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo: MagicMock,
        market_data: MagicMock,
        options_data: MagicMock,
    ) -> None:
        """Mix of successful and failed desks: failed have FALLBACK status and zero tokens.

        Monkeypatches ``_DESK_RUNNERS`` to replace trend and vol with raising
        functions while keeping the real runners for the other 4 desks.
        """
        from options_arena.agents import recommendation_orchestrator as orch
        from options_arena.agents._desk_deps import DeskDeps
        from options_arena.agents.contrarian_desk import (
            contrarian_desk_recommend,
            run_contrarian_desk_recommendation,
        )
        from options_arena.agents.flow_desk import (
            flow_desk_recommend,
            run_flow_desk_recommendation,
        )
        from options_arena.agents.fundamental_desk import (
            fundamental_desk_recommend,
            run_fundamental_desk_recommendation,
        )
        from options_arena.agents.risk_desk import (
            risk_desk_recommend,
            run_risk_desk_recommendation,
        )
        from options_arena.agents.synthesis_agent import synthesis_agent

        async def _failing_desk(
            deps: DeskDeps, **kwargs: object
        ) -> tuple[DomainAssessment, RunUsage]:
            raise RuntimeError("Desk failed")

        # Replace _DESK_RUNNERS: trend and vol fail, the rest use real runners
        mixed_runners = [
            (DeskType.TREND, _failing_desk),
            (DeskType.VOLATILITY, _failing_desk),
            (DeskType.FLOW, run_flow_desk_recommendation),
            (DeskType.FUNDAMENTAL, run_fundamental_desk_recommendation),
            (DeskType.RISK, run_risk_desk_recommendation),
            (DeskType.CONTRARIAN, run_contrarian_desk_recommendation),
        ]
        monkeypatch.setattr(orch, "_DESK_RUNNERS", mixed_runners)

        remaining_agents = [
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = _enter_overrides(remaining_agents)
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo,
                market_data=market_data,
                options_data=options_data,
            )
        finally:
            _exit_overrides(overrides)

        assert len(result.desk_metrics) == 6

        # Separate metrics by desk type
        metrics_by_desk = {m.desk: m for m in result.desk_metrics}

        # Failed desks should have FALLBACK status and zero tokens
        assert metrics_by_desk[DeskType.TREND].status == DeskRunStatus.FALLBACK
        assert metrics_by_desk[DeskType.TREND].input_tokens == 0
        assert metrics_by_desk[DeskType.VOLATILITY].status == DeskRunStatus.FALLBACK
        assert metrics_by_desk[DeskType.VOLATILITY].input_tokens == 0

        # Successful desks should have SUCCESS status
        for desk in [DeskType.FLOW, DeskType.FUNDAMENTAL, DeskType.RISK, DeskType.CONTRARIAN]:
            assert metrics_by_desk[desk].status == DeskRunStatus.SUCCESS


# ---------------------------------------------------------------------------
# Tests: _compute_recommendation_cost unit tests
# ---------------------------------------------------------------------------


class TestComputeRecommendationCost:
    """Unit tests for _compute_recommendation_cost helper."""

    def test_cost_with_zero_tokens(self) -> None:
        """Zero tokens -> $0 cost."""
        metrics = [
            DeskMetrics(
                desk=DeskType.TREND,
                status=DeskRunStatus.FALLBACK,
                duration_ms=0,
                model_tier=ModelTier.STANDARD,
                model_used="test-model",
                input_tokens=0,
                output_tokens=0,
            ),
        ]
        cost_map: dict[str, float] = {"test-model": 1.0}
        cost = _compute_recommendation_cost(metrics, cost_map)
        assert cost.total_cost_usd == pytest.approx(0.0)
        assert cost.total_input_tokens == 0
        assert cost.total_output_tokens == 0

    def test_cost_computation_accuracy(self) -> None:
        """Verify cost = (input + output) / 1M * rate_per_million."""
        metrics = [
            DeskMetrics(
                desk=DeskType.TREND,
                status=DeskRunStatus.SUCCESS,
                duration_ms=100,
                model_tier=ModelTier.STANDARD,
                model_used="model-a",
                input_tokens=1_000_000,
                output_tokens=0,
            ),
        ]
        cost_map: dict[str, float] = {"model-a": 2.0}
        cost = _compute_recommendation_cost(metrics, cost_map)
        # 1M tokens * $2/M = $2.00
        assert cost.total_cost_usd == pytest.approx(2.0)

    def test_cost_aggregates_across_desks(self) -> None:
        """Cost aggregates across multiple desks."""
        metrics = [
            DeskMetrics(
                desk=DeskType.TREND,
                status=DeskRunStatus.SUCCESS,
                duration_ms=100,
                model_tier=ModelTier.STANDARD,
                model_used="model-a",
                input_tokens=500_000,
                output_tokens=100_000,
            ),
            DeskMetrics(
                desk=DeskType.VOLATILITY,
                status=DeskRunStatus.SUCCESS,
                duration_ms=100,
                model_tier=ModelTier.FAST,
                model_used="model-b",
                input_tokens=200_000,
                output_tokens=50_000,
            ),
        ]
        cost_map: dict[str, float] = {"model-a": 1.0, "model-b": 0.5}
        cost = _compute_recommendation_cost(metrics, cost_map)
        assert cost.total_input_tokens == 700_000
        assert cost.total_output_tokens == 150_000
        # (600K/1M)*$1 + (250K/1M)*$0.5 = $0.60 + $0.125 = $0.725
        assert cost.total_cost_usd == pytest.approx(0.725)

    def test_tier_distribution(self) -> None:
        """Verify tier_distribution counts are correct."""
        metrics = [
            DeskMetrics(
                desk=DeskType.TREND,
                status=DeskRunStatus.SUCCESS,
                duration_ms=100,
                model_tier=ModelTier.STANDARD,
                model_used="model-a",
            ),
            DeskMetrics(
                desk=DeskType.VOLATILITY,
                status=DeskRunStatus.SUCCESS,
                duration_ms=100,
                model_tier=ModelTier.STANDARD,
                model_used="model-a",
            ),
            DeskMetrics(
                desk=DeskType.FLOW,
                status=DeskRunStatus.SUCCESS,
                duration_ms=100,
                model_tier=ModelTier.FAST,
                model_used="model-b",
            ),
        ]
        cost = _compute_recommendation_cost(metrics, {})
        assert cost.tier_distribution[ModelTier.STANDARD] == 2
        assert cost.tier_distribution[ModelTier.FAST] == 1

    def test_unknown_model_zero_cost(self) -> None:
        """Unknown model in cost_map defaults to $0 rate."""
        metrics = [
            DeskMetrics(
                desk=DeskType.TREND,
                status=DeskRunStatus.SUCCESS,
                duration_ms=100,
                model_tier=ModelTier.STANDARD,
                model_used="unknown-model",
                input_tokens=1_000_000,
                output_tokens=500_000,
            ),
        ]
        cost = _compute_recommendation_cost(metrics, {})
        assert cost.total_cost_usd == pytest.approx(0.0)
        assert cost.total_input_tokens == 1_000_000
        assert cost.total_output_tokens == 500_000
