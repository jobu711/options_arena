"""Tests for spread_analysis injection into DeskDeps and SynthesisDeps.

Verifies that both dataclasses accept ``SpreadAnalysis | None`` and that the
recommendation orchestrator wires the field from ``ScanEnrichment``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import models
from pydantic_ai.usage import RunUsage

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.synthesis_agent import SynthesisDeps
from options_arena.models import (
    AgencyConfig,
    AppSettings,
    DebateConfig,
    DeskType,
    DividendSource,
    ExerciseStyle,
    IndicatorSignals,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    Quote,
    ScanEnrichment,
    SignalDirection,
    TickerInfo,
    TickerScore,
)
from options_arena.models.recommendation import TrendAssessment
from tests.factories import (
    make_market_context,
    make_option_contract,
    make_spread_analysis,
    make_ticker_score,
)

models.ALLOW_MODEL_REQUESTS = False

_ORCH_MOD = "options_arena.agents.recommendation_orchestrator"


# ---------------------------------------------------------------------------
# Shared fixtures for orchestrator tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def ticker_score() -> TickerScore:
    """Bullish ticker score for AAPL."""
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
    """Realistic AAPL call contract."""
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
def quote() -> Quote:
    """Realistic AAPL quote."""
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
    """Realistic AAPL ticker info."""
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
def repo_mock() -> MagicMock:
    """Mock Repository with async methods."""
    repo = MagicMock()
    repo.save_recommendation = AsyncMock(return_value=1)
    repo.save_predictions_batch = AsyncMock(return_value=None)
    repo.get_strategy_rules = AsyncMock(return_value=[])
    return repo


def _make_trend_assessment() -> TrendAssessment:
    """Build a valid TrendAssessment fallback for desk runner mocks."""
    return TrendAssessment(
        direction=SignalDirection.BULLISH,
        confidence=0.7,
        summary="Strong uptrend for AAPL",
        key_factors=["RSI above 60"],
        risks=["Overbought near-term"],
        contracts_referenced=[],
        tools_used=[],
        model_used="test",
        trend_strength=0.8,
        momentum_signal="bullish",
    )


# ---------------------------------------------------------------------------
# DeskDeps tests
# ---------------------------------------------------------------------------


@pytest.mark.critical
class TestDeskDepsSpreadAnalysis:
    """Verify DeskDeps accepts spread_analysis field."""

    def test_desk_deps_accepts_spread(self) -> None:
        """DeskDeps constructed with SpreadAnalysis stores it."""
        spread = make_spread_analysis()
        deps = DeskDeps(
            query="Analyze AAPL",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            repo=MagicMock(),
            spread_analysis=spread,
        )
        assert deps.spread_analysis is spread

    def test_desk_deps_defaults_none(self) -> None:
        """DeskDeps without spread_analysis defaults to None."""
        deps = DeskDeps(
            query="Analyze AAPL",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            repo=MagicMock(),
        )
        assert deps.spread_analysis is None


# ---------------------------------------------------------------------------
# SynthesisDeps tests
# ---------------------------------------------------------------------------


@pytest.mark.critical
class TestSynthesisDepsSpreadAnalysis:
    """Verify SynthesisDeps accepts spread_analysis field."""

    def test_synthesis_deps_accepts_spread(self) -> None:
        """SynthesisDeps constructed with SpreadAnalysis stores it."""
        spread = make_spread_analysis()
        deps = SynthesisDeps(
            context=make_market_context(),
            assessments=[],
            contracts=[make_option_contract()],
            ticker_score=make_ticker_score(),
            spread_analysis=spread,
        )
        assert deps.spread_analysis is spread

    def test_synthesis_deps_defaults_none(self) -> None:
        """SynthesisDeps without spread_analysis defaults to None."""
        deps = SynthesisDeps(
            context=make_market_context(),
            assessments=[],
            contracts=[make_option_contract()],
            ticker_score=make_ticker_score(),
        )
        assert deps.spread_analysis is None


# ---------------------------------------------------------------------------
# Orchestrator wiring tests
# ---------------------------------------------------------------------------


@pytest.mark.critical
class TestOrchestratorSpreadWiring:
    """Verify the orchestrator passes spread_analysis from enrichment to deps."""

    @pytest.mark.asyncio
    async def test_orchestrator_passes_spread_to_synthesis(
        self,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo_mock: MagicMock,
    ) -> None:
        """Orchestrator populates SynthesisDeps.spread_analysis from enrichment."""
        spread = make_spread_analysis()
        enrichment = ScanEnrichment(spread_analysis=spread)

        captured_deps: list[SynthesisDeps] = []

        async def _fake_synthesis(
            deps: SynthesisDeps,
            model: object,
            model_settings: object = None,
            timeout: float = 120.0,
        ) -> object:
            captured_deps.append(deps)
            from options_arena.agents.synthesis_agent import _build_fallback_recommendation

            return _build_fallback_recommendation(deps)

        # Fake desk runner that returns a valid assessment + usage
        async def _fake_desk_runner(
            deps: DeskDeps,
            *,
            model: object = None,
            model_settings: object = None,
            config: object = None,
        ) -> tuple[TrendAssessment, RunUsage]:
            return _make_trend_assessment(), RunUsage()

        # Build fake _DESK_RUNNERS with the same DeskType keys but our fake runner
        fake_desk_runners = [
            (dt, _fake_desk_runner)
            for dt, _ in [
                (DeskType.TREND, None),
                (DeskType.VOLATILITY, None),
                (DeskType.FLOW, None),
                (DeskType.FUNDAMENTAL, None),
                (DeskType.RISK, None),
                (DeskType.CONTRARIAN, None),
            ]
        ]

        with (
            patch(f"{_ORCH_MOD}.run_synthesis", side_effect=_fake_synthesis),
            patch(f"{_ORCH_MOD}.build_debate_model", return_value=None),
            patch(f"{_ORCH_MOD}._DESK_RUNNERS", fake_desk_runners),
        ):
            from options_arena.agents.recommendation_orchestrator import run_recommendation

            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo_mock,
                market_data=MagicMock(),
                options_data=MagicMock(),
                enrichment=enrichment,
            )

            assert result is not None
            assert len(captured_deps) == 1
            assert captured_deps[0].spread_analysis is spread

    @pytest.mark.asyncio
    async def test_orchestrator_passes_none_when_no_enrichment(
        self,
        ticker_score: TickerScore,
        option_contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        settings: AppSettings,
        repo_mock: MagicMock,
    ) -> None:
        """Orchestrator passes None spread_analysis when enrichment is None."""
        captured_deps: list[SynthesisDeps] = []

        async def _fake_synthesis(
            deps: SynthesisDeps,
            model: object,
            model_settings: object = None,
            timeout: float = 120.0,
        ) -> object:
            captured_deps.append(deps)
            from options_arena.agents.synthesis_agent import _build_fallback_recommendation

            return _build_fallback_recommendation(deps)

        async def _fake_desk_runner(
            deps: DeskDeps,
            *,
            model: object = None,
            model_settings: object = None,
            config: object = None,
        ) -> tuple[TrendAssessment, RunUsage]:
            return _make_trend_assessment(), RunUsage()

        fake_desk_runners = [
            (dt, _fake_desk_runner)
            for dt, _ in [
                (DeskType.TREND, None),
                (DeskType.VOLATILITY, None),
                (DeskType.FLOW, None),
                (DeskType.FUNDAMENTAL, None),
                (DeskType.RISK, None),
                (DeskType.CONTRARIAN, None),
            ]
        ]

        with (
            patch(f"{_ORCH_MOD}.run_synthesis", side_effect=_fake_synthesis),
            patch(f"{_ORCH_MOD}.build_debate_model", return_value=None),
            patch(f"{_ORCH_MOD}._DESK_RUNNERS", fake_desk_runners),
        ):
            from options_arena.agents.recommendation_orchestrator import run_recommendation

            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=ticker_score,
                contracts=[option_contract],
                quote=quote,
                ticker_info=ticker_info,
                settings=settings,
                repo=repo_mock,
                market_data=MagicMock(),
                options_data=MagicMock(),
                enrichment=None,
            )

            assert result is not None
            # enrichment=None -> ScanEnrichment() default -> spread_analysis=None
            assert len(captured_deps) == 1
            assert captured_deps[0].spread_analysis is None
