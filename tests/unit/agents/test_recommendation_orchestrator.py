"""Tests for the recommendation orchestrator pipeline."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.recommendation_orchestrator import (
    _build_fallback_assessment,
    _build_fallback_recommendation_result,
    run_recommendation,
)
from options_arena.agents.synthesis_agent import SynthesisDeps
from options_arena.models import (
    AgencyConfig,
    AppSettings,
    DebateConfig,
    DeskType,
    DividendSource,
    ExerciseStyle,
    IndicatorSignals,
    MacdSignal,
    MarketContext,
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
    ContrarianAssessment,
    DomainAssessment,
    FlowAssessment,
    FundamentalAssessment,
    PositionRecommendation,
    RecommendationResult,
    RiskDeskAssessment,
    TrendAssessment,
    VolatilityAssessment,
)

models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_ticker_score() -> TickerScore:
    """Realistic TickerScore for AAPL with bullish direction."""
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
def mock_option_contract() -> OptionContract:
    """Realistic OptionContract for AAPL call with Greeks."""
    return OptionContract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("190.00"),
        expiration=date(2026, 5, 15),
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
def mock_quote() -> Quote:
    """Realistic Quote for AAPL."""
    return Quote(
        ticker="AAPL",
        price=Decimal("185.50"),
        bid=Decimal("185.48"),
        ask=Decimal("185.52"),
        volume=42_000_000,
        timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture()
def mock_ticker_info() -> TickerInfo:
    """Realistic TickerInfo for AAPL."""
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
def mock_market_context() -> MarketContext:
    """Realistic MarketContext for AAPL."""
    return MarketContext(
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


@pytest.fixture()
def mock_settings() -> AppSettings:
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
def mock_repo() -> MagicMock:
    """Mock Repository with async methods."""
    repo = MagicMock()
    repo.save_recommendation = AsyncMock(return_value=1)
    repo.save_agent_predictions = AsyncMock()
    repo.get_strategy_rules = AsyncMock(return_value=[])
    return repo


@pytest.fixture()
def mock_market_data() -> MagicMock:
    """Mock MarketDataService."""
    return MagicMock()


@pytest.fixture()
def mock_options_data() -> MagicMock:
    """Mock OptionsDataService."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trend_assessment(ticker: str = "AAPL") -> TrendAssessment:
    """Build a valid TrendAssessment for test use."""
    return TrendAssessment(
        direction=SignalDirection.BULLISH,
        confidence=0.7,
        summary=f"Strong uptrend for {ticker}",
        key_factors=["RSI above 60"],
        risks=["Overbought near-term"],
        contracts_referenced=[],
        tools_used=[],
        model_used="test",
        trend_strength=0.8,
        momentum_signal="bullish",
    )


def _make_vol_assessment(ticker: str = "AAPL") -> VolatilityAssessment:
    return VolatilityAssessment(
        direction=SignalDirection.NEUTRAL,
        confidence=0.6,
        summary=f"IV regime normal for {ticker}",
        key_factors=["IV rank moderate"],
        risks=["Vol crush risk"],
        contracts_referenced=[],
        tools_used=[],
        model_used="test",
        iv_regime=None,
    )


# ---------------------------------------------------------------------------
# Tests: _build_fallback_assessment
# ---------------------------------------------------------------------------


class TestBuildFallbackAssessment:
    """Tests for _build_fallback_assessment helper."""

    def test_trend_returns_trend_assessment(self) -> None:
        result = _build_fallback_assessment(DeskType.TREND, "AAPL")
        assert isinstance(result, TrendAssessment)
        assert result.desk == DeskType.TREND

    def test_volatility_returns_volatility_assessment(self) -> None:
        result = _build_fallback_assessment(DeskType.VOLATILITY, "AAPL")
        assert isinstance(result, VolatilityAssessment)
        assert result.desk == DeskType.VOLATILITY

    def test_flow_returns_flow_assessment(self) -> None:
        result = _build_fallback_assessment(DeskType.FLOW, "AAPL")
        assert isinstance(result, FlowAssessment)
        assert result.desk == DeskType.FLOW

    def test_fundamental_returns_fundamental_assessment(self) -> None:
        result = _build_fallback_assessment(DeskType.FUNDAMENTAL, "AAPL")
        assert isinstance(result, FundamentalAssessment)
        assert result.desk == DeskType.FUNDAMENTAL

    def test_risk_returns_risk_assessment(self) -> None:
        result = _build_fallback_assessment(DeskType.RISK, "AAPL")
        assert isinstance(result, RiskDeskAssessment)
        assert result.desk == DeskType.RISK

    def test_contrarian_returns_contrarian_assessment(self) -> None:
        result = _build_fallback_assessment(DeskType.CONTRARIAN, "AAPL")
        assert isinstance(result, ContrarianAssessment)
        assert result.desk == DeskType.CONTRARIAN

    def test_all_desk_types_produce_valid_fallbacks(self) -> None:
        """All 6 recommendation desk types produce valid assessments."""
        desk_types = [
            DeskType.TREND,
            DeskType.VOLATILITY,
            DeskType.FLOW,
            DeskType.FUNDAMENTAL,
            DeskType.RISK,
            DeskType.CONTRARIAN,
        ]
        for dt in desk_types:
            result = _build_fallback_assessment(dt, "TSLA")
            assert isinstance(result, DomainAssessment)
            assert result.direction == SignalDirection.NEUTRAL
            assert result.confidence == pytest.approx(0.2, abs=0.01)
            assert result.model_used == "data-driven-fallback"
            assert "TSLA" in result.summary

    def test_fallback_has_correct_subclass_per_desk(self) -> None:
        """Each desk type maps to the correct DomainAssessment subclass."""
        expected_types: dict[DeskType, type[DomainAssessment]] = {
            DeskType.TREND: TrendAssessment,
            DeskType.VOLATILITY: VolatilityAssessment,
            DeskType.FLOW: FlowAssessment,
            DeskType.FUNDAMENTAL: FundamentalAssessment,
            DeskType.RISK: RiskDeskAssessment,
            DeskType.CONTRARIAN: ContrarianAssessment,
        }
        for dt, expected_cls in expected_types.items():
            result = _build_fallback_assessment(dt, "AAPL")
            assert type(result) is expected_cls, f"Expected {expected_cls} for {dt}"


# ---------------------------------------------------------------------------
# Tests: _build_fallback_recommendation_result
# ---------------------------------------------------------------------------


class TestBuildFallbackRecommendationResult:
    """Tests for _build_fallback_recommendation_result helper."""

    def test_produces_valid_result(self, mock_market_context: MarketContext) -> None:
        result = _build_fallback_recommendation_result(mock_market_context, "AAPL")
        assert isinstance(result, RecommendationResult)
        assert result.is_fallback is True
        assert result.recommendation.confidence == pytest.approx(0.2, abs=0.01)
        assert result.recommendation.direction == SignalDirection.NEUTRAL
        assert result.recommendation.model_used == "data-driven-fallback"
        assert len(result.assessments) == 6

    def test_all_assessments_are_fallbacks(self, mock_market_context: MarketContext) -> None:
        result = _build_fallback_recommendation_result(mock_market_context, "AAPL")
        for assessment in result.assessments:
            assert isinstance(assessment, DomainAssessment)
            assert assessment.confidence == pytest.approx(0.2, abs=0.01)
            assert assessment.model_used == "data-driven-fallback"

    def test_duration_ms_propagated(self, mock_market_context: MarketContext) -> None:
        result = _build_fallback_recommendation_result(
            mock_market_context, "AAPL", duration_ms=1500
        )
        assert result.duration_ms == 1500


# ---------------------------------------------------------------------------
# Tests: run_recommendation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRunRecommendation:
    """Tests for run_recommendation() pipeline."""

    @pytest.mark.critical
    async def test_success_path_with_test_model(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_repo: MagicMock,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """Full pipeline produces a valid RecommendationResult."""
        # Import the desk agents to override them with TestModel
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import (
            fundamental_desk_recommend,
        )
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
        overrides = [a.override(model=TestModel()) for a in agents]
        for o in overrides:
            o.__enter__()
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                settings=mock_settings,
                repo=mock_repo,
                market_data=mock_market_data,
                options_data=mock_options_data,
            )
        finally:
            for o in reversed(overrides):
                o.__exit__(None, None, None)

        assert isinstance(result, RecommendationResult)
        assert isinstance(result.recommendation, PositionRecommendation)
        assert result.context.ticker == "AAPL"
        assert len(result.assessments) == 6
        assert result.duration_ms >= 0

    async def test_partial_desk_failure_produces_fallback_assessments(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_repo: MagicMock,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """Two failed desks produce fallback assessments, synthesis still runs."""
        from options_arena.agents.synthesis_agent import synthesis_agent

        async def _failing_trend(deps: DeskDeps, **kwargs: object) -> TrendAssessment:
            raise RuntimeError("Trend desk failed")

        async def _failing_vol(deps: DeskDeps, **kwargs: object) -> VolatilityAssessment:
            raise RuntimeError("Vol desk failed")

        monkeypatch.setattr(
            "options_arena.agents.recommendation_orchestrator.run_trend_desk_recommendation",
            _failing_trend,
        )
        monkeypatch.setattr(
            "options_arena.agents.recommendation_orchestrator.run_vol_desk_recommendation",
            _failing_vol,
        )

        # Use TestModel for remaining agents
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import (
            fundamental_desk_recommend,
        )
        from options_arena.agents.risk_desk import risk_desk_recommend

        agents = [
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = [a.override(model=TestModel()) for a in agents]
        for o in overrides:
            o.__enter__()
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                settings=mock_settings,
                repo=mock_repo,
                market_data=mock_market_data,
                options_data=mock_options_data,
            )
        finally:
            for o in reversed(overrides):
                o.__exit__(None, None, None)

        assert isinstance(result, RecommendationResult)
        assert len(result.assessments) == 6

        # Check that trend and vol have fallback assessments
        trend_a = [a for a in result.assessments if isinstance(a, TrendAssessment)][0]
        vol_a = [a for a in result.assessments if isinstance(a, VolatilityAssessment)][0]
        assert trend_a.model_used == "data-driven-fallback"
        assert vol_a.model_used == "data-driven-fallback"

    async def test_all_desks_fail_returns_fallback_result(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_repo: MagicMock,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """All desk failures — synthesis still runs with fallback assessments."""
        from options_arena.agents.synthesis_agent import synthesis_agent

        async def _failing_desk(deps: DeskDeps, **kwargs: object) -> DomainAssessment:
            raise RuntimeError("Desk failed")

        # Monkeypatch all 6 desk runners
        for runner_name in [
            "run_trend_desk_recommendation",
            "run_vol_desk_recommendation",
            "run_flow_desk_recommendation",
            "run_fundamental_desk_recommendation",
            "run_risk_desk_recommendation",
            "run_contrarian_desk_recommendation",
        ]:
            monkeypatch.setattr(
                f"options_arena.agents.recommendation_orchestrator.{runner_name}",
                _failing_desk,
            )

        with synthesis_agent.override(model=TestModel()):
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                settings=mock_settings,
                repo=mock_repo,
                market_data=mock_market_data,
                options_data=mock_options_data,
            )

        assert isinstance(result, RecommendationResult)
        assert len(result.assessments) == 6

        # All assessments should be fallbacks
        for assessment in result.assessments:
            assert isinstance(assessment, DomainAssessment)
            assert assessment.model_used == "data-driven-fallback"

    async def test_synthesis_failure_returns_fallback(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_repo: MagicMock,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """Synthesis agent failure returns a fallback recommendation."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import (
            fundamental_desk_recommend,
        )
        from options_arena.agents.risk_desk import risk_desk_recommend
        from options_arena.agents.trend_desk import trend_desk_recommend
        from options_arena.agents.volatility_desk import vol_desk_recommend

        async def _failing_synthesis(
            deps: SynthesisDeps, **kwargs: object
        ) -> PositionRecommendation:
            raise RuntimeError("Synthesis failed")

        monkeypatch.setattr(
            "options_arena.agents.recommendation_orchestrator.run_synthesis",
            _failing_synthesis,
        )

        desk_agents = [
            trend_desk_recommend,
            vol_desk_recommend,
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
        ]
        overrides = [a.override(model=TestModel()) for a in desk_agents]
        for o in overrides:
            o.__enter__()
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                settings=mock_settings,
                repo=mock_repo,
                market_data=mock_market_data,
                options_data=mock_options_data,
            )
        finally:
            for o in reversed(overrides):
                o.__exit__(None, None, None)

        # Pipeline caught the synthesis error at the outer try/except level
        assert isinstance(result, RecommendationResult)
        assert result.is_fallback is True

    async def test_should_recommend_false_returns_early(
        self,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_repo: MagicMock,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """Low-score / NEUTRAL ticker returns early with conservative result."""
        low_score = TickerScore(
            ticker="AAPL",
            composite_score=25.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(rsi=50.0),
            scan_run_id=1,
        )

        result = await run_recommendation(
            ticker="AAPL",
            ticker_score=low_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            settings=mock_settings,
            repo=mock_repo,
            market_data=mock_market_data,
            options_data=mock_options_data,
        )

        assert isinstance(result, RecommendationResult)
        assert result.is_fallback is True
        assert result.recommendation.confidence == pytest.approx(0.2, abs=0.01)

    async def test_progress_callback_fires(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_repo: MagicMock,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """Verify progress_callback is called for each phase."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import (
            fundamental_desk_recommend,
        )
        from options_arena.agents.risk_desk import risk_desk_recommend
        from options_arena.agents.synthesis_agent import synthesis_agent
        from options_arena.agents.trend_desk import trend_desk_recommend
        from options_arena.agents.volatility_desk import vol_desk_recommend

        phases_called: list[str] = []

        def _track_progress(phase: str, step: int, total: int) -> None:
            phases_called.append(phase)

        agents = [
            trend_desk_recommend,
            vol_desk_recommend,
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = [a.override(model=TestModel()) for a in agents]
        for o in overrides:
            o.__enter__()
        try:
            await run_recommendation(
                ticker="AAPL",
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                settings=mock_settings,
                repo=mock_repo,
                market_data=mock_market_data,
                options_data=mock_options_data,
                progress_callback=_track_progress,
            )
        finally:
            for o in reversed(overrides):
                o.__exit__(None, None, None)

        assert "context" in phases_called
        assert "desks" in phases_called
        assert "synthesis" in phases_called
        assert "persist" in phases_called

    async def test_never_raises_on_unexpected_exception(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_repo: MagicMock,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """Any exception in the pipeline produces a valid result."""
        # Make build_market_context raise to trigger outermost fallback
        monkeypatch.setattr(
            "options_arena.agents.recommendation_orchestrator.build_market_context",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Unexpected error")),
        )

        result = await run_recommendation(
            ticker="AAPL",
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            settings=mock_settings,
            repo=mock_repo,
            market_data=mock_market_data,
            options_data=mock_options_data,
        )

        assert isinstance(result, RecommendationResult)
        assert result.is_fallback is True

    async def test_persistence_failure_does_not_crash(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """Persistence error is logged but the result is still returned."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import (
            fundamental_desk_recommend,
        )
        from options_arena.agents.risk_desk import risk_desk_recommend
        from options_arena.agents.synthesis_agent import synthesis_agent
        from options_arena.agents.trend_desk import trend_desk_recommend
        from options_arena.agents.volatility_desk import vol_desk_recommend

        failing_repo = MagicMock()
        failing_repo.save_recommendation = AsyncMock(side_effect=RuntimeError("DB write failed"))
        failing_repo.get_strategy_rules = AsyncMock(return_value=[])

        agents = [
            trend_desk_recommend,
            vol_desk_recommend,
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
            synthesis_agent,
        ]
        overrides = [a.override(model=TestModel()) for a in agents]
        for o in overrides:
            o.__enter__()
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                settings=mock_settings,
                repo=failing_repo,
                market_data=mock_market_data,
                options_data=mock_options_data,
            )
        finally:
            for o in reversed(overrides):
                o.__exit__(None, None, None)

        # Result still valid even though persistence failed
        assert isinstance(result, RecommendationResult)

    async def test_empty_contracts_list(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_repo: MagicMock,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """Pipeline handles empty contracts list without error."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import (
            fundamental_desk_recommend,
        )
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
        overrides = [a.override(model=TestModel()) for a in agents]
        for o in overrides:
            o.__enter__()
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=mock_ticker_score,
                contracts=[],  # empty
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                settings=mock_settings,
                repo=mock_repo,
                market_data=mock_market_data,
                options_data=mock_options_data,
            )
        finally:
            for o in reversed(overrides):
                o.__exit__(None, None, None)

        assert isinstance(result, RecommendationResult)

    async def test_fred_none_proceeds(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_settings: AppSettings,
        mock_repo: MagicMock,
        mock_market_data: MagicMock,
        mock_options_data: MagicMock,
    ) -> None:
        """Pipeline proceeds normally when fred=None."""
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import (
            fundamental_desk_recommend,
        )
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
        overrides = [a.override(model=TestModel()) for a in agents]
        for o in overrides:
            o.__enter__()
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                settings=mock_settings,
                repo=mock_repo,
                market_data=mock_market_data,
                options_data=mock_options_data,
                fred=None,
            )
        finally:
            for o in reversed(overrides):
                o.__exit__(None, None, None)

        assert isinstance(result, RecommendationResult)


# ---------------------------------------------------------------------------
# Tests: AgencyConfig.desk_parallelism
# ---------------------------------------------------------------------------


class TestDeskParallelismConfig:
    """Tests for desk_parallelism field on AgencyConfig."""

    def test_default_is_six(self) -> None:
        config = AgencyConfig()
        assert config.desk_parallelism == 6

    def test_custom_value(self) -> None:
        config = AgencyConfig(desk_parallelism=3)
        assert config.desk_parallelism == 3

    def test_rejects_zero(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="desk_parallelism"):
            AgencyConfig(desk_parallelism=0)

    def test_rejects_negative(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="desk_parallelism"):
            AgencyConfig(desk_parallelism=-1)

    def test_accepts_one(self) -> None:
        config = AgencyConfig(desk_parallelism=1)
        assert config.desk_parallelism == 1
