"""End-to-end integration tests for the recommendation pipeline (#667).

Tests run the full ``run_recommendation()`` flow with ``ALLOW_MODEL_REQUESTS = False``
and mocked services, verifying that the pipeline produces valid fallback results,
correctly structures assessments, and persists to the repository.

All tests marked ``@pytest.mark.integration``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models

from options_arena.agents.recommendation_orchestrator import run_recommendation
from options_arena.models import (
    AppSettings,
    DividendSource,
    ExerciseStyle,
    IndicatorSignals,
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
    PositionRecommendation,
    RecommendationResult,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _make_ticker_score(
    ticker: str = "NVDA",
    score: float = 85.0,
    direction: SignalDirection = SignalDirection.BULLISH,
) -> TickerScore:
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=direction,
        signals=IndicatorSignals(
            rsi=68.0,
            adx=35.0,
            sma_alignment=0.9,
            bb_width=30.0,
            atr_pct=20.0,
            obv=70.0,
            relative_volume=65.0,
        ),
        scan_run_id=1,
    )


def _make_quote(ticker: str = "NVDA") -> Quote:
    return Quote(
        ticker=ticker,
        price=Decimal("850.00"),
        bid=Decimal("849.90"),
        ask=Decimal("850.10"),
        volume=50_000_000,
        timestamp=datetime(2026, 3, 22, 15, 0, 0, tzinfo=UTC),
    )


def _make_ticker_info(ticker: str = "NVDA") -> TickerInfo:
    return TickerInfo(
        ticker=ticker,
        company_name="NVIDIA Corporation",
        sector="Information Technology",
        market_cap=2_100_000_000_000,
        dividend_yield=0.0002,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal("850.00"),
        fifty_two_week_high=Decimal("950.00"),
        fifty_two_week_low=Decimal("450.00"),
    )


def _make_contract(ticker: str = "NVDA") -> OptionContract:
    return OptionContract(
        ticker=ticker,
        option_type=OptionType.CALL,
        strike=Decimal("870.00"),
        expiration=date.today() + timedelta(days=30),
        bid=Decimal("15.00"),
        ask=Decimal("16.00"),
        last=Decimal("15.50"),
        volume=5000,
        open_interest=20000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.45,
        greeks=OptionGreeks(
            delta=0.32,
            gamma=0.003,
            theta=-0.85,
            vega=1.20,
            rho=0.15,
            pricing_model=PricingModel.BAW,
        ),
    )


def _make_mock_services() -> tuple[MagicMock, MagicMock, MagicMock]:
    """Build mocked MarketDataService, OptionsDataService, FredService."""
    market_data = MagicMock()
    options_data = MagicMock()
    fred = MagicMock()
    return market_data, options_data, fred


def _make_mock_repo() -> MagicMock:
    """Build a mock Repository with recommendation persistence methods."""
    repo = MagicMock()
    repo.save_recommendation = AsyncMock(return_value=1)
    repo.get_strategy_rules = AsyncMock(return_value=[])
    repo.save_agent_predictions = AsyncMock(return_value=None)
    return repo


# ---------------------------------------------------------------------------
# E2E: Full pipeline fallback (no LLM available)
# ---------------------------------------------------------------------------


class TestRecommendationE2E:
    """Full run_recommendation() pipeline tests with ALLOW_MODEL_REQUESTS=False."""

    @pytest.mark.critical
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_recommendation_fallback_without_llm(self) -> None:
        """Full pipeline without LLM produces a valid fallback RecommendationResult.

        ALLOW_MODEL_REQUESTS=False prevents real API calls. The desk agents and
        synthesis agent should all fall back to data-driven defaults.
        """
        market_data, options_data, fred = _make_mock_services()
        repo = _make_mock_repo()
        settings = AppSettings()
        # Set short timeouts so tests don't hang
        settings.debate.agent_timeout = 1.0
        settings.debate.max_total_duration = 10.0

        result = await run_recommendation(
            ticker="NVDA",
            ticker_score=_make_ticker_score(),
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
        )

        assert isinstance(result, RecommendationResult)
        assert isinstance(result.recommendation, PositionRecommendation)
        assert result.recommendation.ticker == "NVDA"
        assert result.duration_ms >= 0
        # With ALLOW_MODEL_REQUESTS=False, agents fail -> fallback
        assert result.is_fallback is True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_fallback_recommendation_has_neutral_or_original_direction(self) -> None:
        """Fallback recommendation direction is NEUTRAL (pipeline failure mode)."""
        market_data, options_data, fred = _make_mock_services()
        repo = _make_mock_repo()
        settings = AppSettings()
        settings.debate.agent_timeout = 1.0
        settings.debate.max_total_duration = 10.0

        result = await run_recommendation(
            ticker="NVDA",
            ticker_score=_make_ticker_score(),
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
        )

        # Fallback should be NEUTRAL (conservative)
        assert result.recommendation.direction == SignalDirection.NEUTRAL
        # Confidence should be low for fallback
        assert result.recommendation.confidence <= 0.3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_fallback_has_six_assessments(self) -> None:
        """Fallback result includes all 6 desk assessments."""
        market_data, options_data, fred = _make_mock_services()
        repo = _make_mock_repo()
        settings = AppSettings()
        settings.debate.agent_timeout = 1.0
        settings.debate.max_total_duration = 10.0

        result = await run_recommendation(
            ticker="NVDA",
            ticker_score=_make_ticker_score(),
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
        )

        assert len(result.assessments) == 6
        desk_types = {a.desk for a in result.assessments}
        expected_desks = {"trend", "volatility", "flow", "fundamental", "risk", "contrarian"}
        assert desk_types == expected_desks

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_fallback_model_used_is_data_driven(self) -> None:
        """Fallback recommendation uses 'data-driven-fallback' as model_used."""
        market_data, options_data, fred = _make_mock_services()
        repo = _make_mock_repo()
        settings = AppSettings()
        settings.debate.agent_timeout = 1.0
        settings.debate.max_total_duration = 10.0

        result = await run_recommendation(
            ticker="NVDA",
            ticker_score=_make_ticker_score(),
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
        )

        assert result.recommendation.model_used == "data-driven-fallback"


# ---------------------------------------------------------------------------
# E2E: Persistence
# ---------------------------------------------------------------------------


class TestRecommendationPersistence:
    """Verify that run_recommendation persists results to the repository."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_recommendation_calls_save(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """repo.save_recommendation is called with the result."""
        from pydantic_ai.models.test import TestModel

        market_data, options_data, fred = _make_mock_services()
        repo = _make_mock_repo()
        settings = AppSettings()
        settings.debate.agent_timeout = 1.0
        settings.debate.max_total_duration = 10.0

        # Monkeypatch build_debate_model to avoid requiring an API key
        monkeypatch.setattr(
            "options_arena.agents.recommendation_orchestrator.build_debate_model",
            lambda config: TestModel(),
        )

        await run_recommendation(
            ticker="NVDA",
            ticker_score=_make_ticker_score(),
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
            scan_run_id=42,
        )

        repo.save_recommendation.assert_awaited_once()
        # First arg is the RecommendationResult
        saved_result = repo.save_recommendation.call_args[0][0]
        assert isinstance(saved_result, RecommendationResult)
        # Second arg is the scan_run_id
        assert repo.save_recommendation.call_args[0][1] == 42


# ---------------------------------------------------------------------------
# E2E: Score threshold gating
# ---------------------------------------------------------------------------


class TestScoreThresholdE2E:
    """Verify that low scores produce fallback without running agents."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_below_threshold_returns_fallback(self) -> None:
        """Score below min_recommendation_score returns fallback directly."""
        market_data, options_data, fred = _make_mock_services()
        repo = _make_mock_repo()
        settings = AppSettings()
        settings.debate.min_recommendation_score = 50.0
        settings.debate.agent_timeout = 1.0

        # Score 20.0 is well below 50.0 threshold
        low_score = _make_ticker_score(score=20.0)

        result = await run_recommendation(
            ticker="NVDA",
            ticker_score=low_score,
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
        )

        assert result.is_fallback is True
        # Should NOT persist below-threshold results
        # (it still persists as the fallback — this is expected)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_neutral_direction_returns_fallback(self) -> None:
        """NEUTRAL direction returns fallback even with high score."""
        market_data, options_data, fred = _make_mock_services()
        repo = _make_mock_repo()
        settings = AppSettings()
        settings.debate.agent_timeout = 1.0

        neutral_score = _make_ticker_score(score=90.0, direction=SignalDirection.NEUTRAL)

        result = await run_recommendation(
            ticker="NVDA",
            ticker_score=neutral_score,
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
        )

        assert result.is_fallback is True


# ---------------------------------------------------------------------------
# E2E: Invalid ticker
# ---------------------------------------------------------------------------


class TestInvalidTickerE2E:
    """Verify invalid ticker produces fallback without crashing."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_invalid_ticker_returns_fallback(self) -> None:
        """Non-matching ticker regex returns fallback safely."""
        market_data, options_data, fred = _make_mock_services()
        repo = _make_mock_repo()
        settings = AppSettings()
        settings.debate.agent_timeout = 1.0

        result = await run_recommendation(
            ticker="@@INVALID@@",
            ticker_score=_make_ticker_score(ticker="NVDA"),  # mismatch is OK for fallback
            contracts=[],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
        )

        assert isinstance(result, RecommendationResult)
        assert result.is_fallback is True


# ---------------------------------------------------------------------------
# E2E: Empty contracts
# ---------------------------------------------------------------------------


class TestEmptyContractsE2E:
    """Verify pipeline handles empty contracts list gracefully."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_empty_contracts_produces_result(self) -> None:
        """Pipeline with no contracts still produces a valid result."""
        market_data, options_data, fred = _make_mock_services()
        repo = _make_mock_repo()
        settings = AppSettings()
        settings.debate.agent_timeout = 1.0
        settings.debate.max_total_duration = 10.0

        result = await run_recommendation(
            ticker="NVDA",
            ticker_score=_make_ticker_score(),
            contracts=[],  # empty
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=settings,
            repo=repo,
            market_data=market_data,
            options_data=options_data,
            fred=fred,
        )

        assert isinstance(result, RecommendationResult)
        # Should still produce a result (likely fallback)
        assert result.recommendation.ticker == "NVDA"
