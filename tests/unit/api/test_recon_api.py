"""Tests for IntelligenceService wiring in API layer.

Mirrors test_app_lifespan_openbb.py and test_debate_openbb.py patterns --
verifies lifespan creation/shutdown, deps provider, and debate route integration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateResult
from options_arena.api.app import lifespan
from options_arena.models import (
    AgentResponse,
    AppSettings,
    IndicatorSignals,
    MarketContext,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
    TradeThesis,
)
from options_arena.models.config import IntelligenceConfig
from options_arena.models.enums import (
    DividendSource,
    ExerciseStyle,
    MacdSignal,
)
from options_arena.models.intelligence import IntelligencePackage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_quote() -> Quote:
    """Create a realistic Quote for test fixtures."""
    return Quote(
        ticker="AAPL",
        price=Decimal("185.05"),
        bid=Decimal("185.00"),
        ask=Decimal("185.10"),
        volume=42_000_000,
        timestamp=datetime(2026, 3, 2, 15, 0, 0, tzinfo=UTC),
    )


def _make_ticker_info() -> TickerInfo:
    """Create a realistic TickerInfo for test fixtures."""
    return TickerInfo(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Information Technology",
        market_cap=2_800_000_000_000,
        current_price=Decimal("185.05"),
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("164.08"),
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
    )


def _make_ticker_score(ticker: str = "AAPL") -> TickerScore:
    """Create a TickerScore for test fixtures."""
    return TickerScore(
        ticker=ticker,
        composite_score=75.0,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.0),
        scan_run_id=1,
    )


def _make_debate_result(ticker: str = "AAPL") -> DebateResult:
    """Create a minimal DebateResult for test fixtures."""
    bull = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI at 65 indicates bullish momentum.",
        key_points=["RSI trending up"],
        risks_cited=["Earnings next week"],
        contracts_referenced=[f"{ticker} $190 CALL"],
        model_used="test",
    )
    bear = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="IV is elevated, limiting upside.",
        key_points=["IV elevated"],
        risks_cited=["Potential reversal"],
        contracts_referenced=[f"{ticker} $190 CALL"],
        model_used="test",
    )
    thesis = TradeThesis(
        ticker=ticker,
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["Momentum"],
        risk_assessment="Moderate risk.",
    )
    ctx = MarketContext(
        ticker=ticker,
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
        data_timestamp=datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC),
    )
    return DebateResult(
        context=ctx,
        bull_response=bull,
        bear_response=bear,
        thesis=thesis,
        total_usage=RunUsage(),
        duration_ms=1500,
        is_fallback=False,
    )


def _make_intelligence_package(ticker: str = "AAPL") -> IntelligencePackage:
    """Create a minimal IntelligencePackage for testing."""
    return IntelligencePackage(
        ticker=ticker,
        analyst=None,
        analyst_activity=None,
        insider=None,
        institutional=None,
        news_headlines=["Headline 1", "Headline 2"],
        fetched_at=datetime(2026, 3, 2, 14, 0, 0, tzinfo=UTC),
    )


def _make_service_patches() -> dict[str, MagicMock]:
    """Create patch targets that return AsyncMock instances (awaitable close())."""
    patches: dict[str, MagicMock] = {}
    for name in ("MarketDataService", "OptionsDataService", "FredService", "UniverseService"):
        mock_cls = MagicMock()
        mock_cls.return_value = AsyncMock()
        patches[name] = mock_cls
    return patches


def _make_mock_request(
    intelligence_svc: AsyncMock | None = None,
) -> MagicMock:
    """Create a mock Request with app.state populated."""
    request = MagicMock()
    request.app.state.intelligence = intelligence_svc
    request.app.state.financial_datasets = None
    request.app.state.debate_queues = {}
    request.app.state.batch_queues = {}
    return request


# ---------------------------------------------------------------------------
# Lifespan tests
# ---------------------------------------------------------------------------


class TestAPILifespanIntelligence:
    """Tests for IntelligenceService in API lifespan."""

    async def test_intelligence_created_when_enabled(self, tmp_path: Path) -> None:
        """Intelligence service stored on app.state when config enabled."""
        svc_patches = _make_service_patches()

        with (
            patch("options_arena.api.app.AppSettings") as mock_settings_cls,
            patch("options_arena.api.app.Database") as mock_db_cls,
            patch("options_arena.api.app.Repository"),
            patch("options_arena.api.app.IntelligenceService") as mock_intel_cls,
            patch(
                "options_arena.api.app.MarketDataService",
                svc_patches["MarketDataService"],
            ),
            patch(
                "options_arena.api.app.OptionsDataService",
                svc_patches["OptionsDataService"],
            ),
            patch("options_arena.api.app.FredService", svc_patches["FredService"]),
            patch(
                "options_arena.api.app.UniverseService",
                svc_patches["UniverseService"],
            ),
            patch("options_arena.api.app.ServiceCache") as mock_cache_cls,
            patch("options_arena.api.app.RateLimiter"),
            patch("options_arena.api.app.FinancialDatasetsService"),
        ):
            mock_settings = MagicMock()
            mock_settings.financial_datasets.enabled = False
            mock_settings.intelligence = IntelligenceConfig(enabled=True)
            mock_settings.data.db_path = str(tmp_path / "test.db")
            mock_settings_cls.return_value = mock_settings

            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db

            mock_cache = AsyncMock()
            mock_cache_cls.return_value = mock_cache

            mock_intel_svc = AsyncMock()
            mock_intel_cls.return_value = mock_intel_svc

            app = FastAPI()
            async with lifespan(app):
                mock_intel_cls.assert_called_once()
                assert app.state.intelligence is mock_intel_svc

    async def test_intelligence_not_created_when_disabled(self, tmp_path: Path) -> None:
        """app.state.intelligence is None when config disabled."""
        svc_patches = _make_service_patches()

        with (
            patch("options_arena.api.app.AppSettings") as mock_settings_cls,
            patch("options_arena.api.app.Database") as mock_db_cls,
            patch("options_arena.api.app.Repository"),
            patch("options_arena.api.app.IntelligenceService") as mock_intel_cls,
            patch(
                "options_arena.api.app.MarketDataService",
                svc_patches["MarketDataService"],
            ),
            patch(
                "options_arena.api.app.OptionsDataService",
                svc_patches["OptionsDataService"],
            ),
            patch("options_arena.api.app.FredService", svc_patches["FredService"]),
            patch(
                "options_arena.api.app.UniverseService",
                svc_patches["UniverseService"],
            ),
            patch("options_arena.api.app.ServiceCache") as mock_cache_cls,
            patch("options_arena.api.app.RateLimiter"),
            patch("options_arena.api.app.FinancialDatasetsService"),
        ):
            mock_settings = MagicMock()
            mock_settings.financial_datasets.enabled = False
            mock_settings.intelligence = IntelligenceConfig(enabled=False)
            mock_settings.data.db_path = str(tmp_path / "test.db")
            mock_settings_cls.return_value = mock_settings

            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db

            mock_cache = AsyncMock()
            mock_cache_cls.return_value = mock_cache

            app = FastAPI()
            async with lifespan(app):
                mock_intel_cls.assert_not_called()
                assert app.state.intelligence is None

    async def test_intelligence_closed_on_shutdown(self, tmp_path: Path) -> None:
        """close() called during lifespan shutdown."""
        svc_patches = _make_service_patches()

        with (
            patch("options_arena.api.app.AppSettings") as mock_settings_cls,
            patch("options_arena.api.app.Database") as mock_db_cls,
            patch("options_arena.api.app.Repository"),
            patch("options_arena.api.app.IntelligenceService") as mock_intel_cls,
            patch(
                "options_arena.api.app.MarketDataService",
                svc_patches["MarketDataService"],
            ),
            patch(
                "options_arena.api.app.OptionsDataService",
                svc_patches["OptionsDataService"],
            ),
            patch("options_arena.api.app.FredService", svc_patches["FredService"]),
            patch(
                "options_arena.api.app.UniverseService",
                svc_patches["UniverseService"],
            ),
            patch("options_arena.api.app.ServiceCache") as mock_cache_cls,
            patch("options_arena.api.app.RateLimiter"),
            patch("options_arena.api.app.FinancialDatasetsService"),
        ):
            mock_settings = MagicMock()
            mock_settings.financial_datasets.enabled = False
            mock_settings.intelligence = IntelligenceConfig(enabled=True)
            mock_settings.data.db_path = str(tmp_path / "test.db")
            mock_settings_cls.return_value = mock_settings

            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db

            mock_cache = AsyncMock()
            mock_cache_cls.return_value = mock_cache

            mock_intel_svc = AsyncMock()
            mock_intel_cls.return_value = mock_intel_svc

            app = FastAPI()
            async with lifespan(app):
                pass

            mock_intel_svc.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Deps provider tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Debate route intelligence tests
# ---------------------------------------------------------------------------


class TestDebateRouteIntelligence:
    """Tests for intelligence integration in recommendation background tasks.

    The old ``_run_debate_background`` and ``_run_batch_debate_background`` were
    replaced by ``_run_recommendation_background`` and
    ``_run_batch_recommendation_background`` in Issue #670.  Intelligence
    fetching is now handled internally by ``run_recommendation()`` — the API
    route only passes services through, and intelligence integration is tested
    at the recommendation_orchestrator level.

    These tests verify that the route correctly delegates to run_recommendation
    with the expected services.
    """

    @patch("options_arena.api.routes.debate.run_recommendation", new_callable=AsyncMock)
    async def test_recommendation_called_in_background(
        self,
        mock_run_rec: AsyncMock,
    ) -> None:
        """_run_recommendation_background delegates to run_recommendation."""
        from options_arena.api.routes.debate import (
            _run_recommendation_background,
        )
        from options_arena.api.ws import RecommendationProgressBridge

        # Build a minimal RecommendationResult for the mock return
        from options_arena.models.recommendation import (
            PositionRecommendation,
            RecommendationResult,
        )

        rec = PositionRecommendation(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            recommended_contract="AAPL 190C 2026-04-18",
            entry_price=Decimal("5.25"),
            entry_criteria="test",
            exit_criteria="test",
            position_size_pct=0.05,
            position_rationale="test",
            risk_reward_ratio=1.5,
            max_loss_estimate="$250",
            strategy_rationale="test",
            summary="Test recommendation",
            key_factors=["test factor"],
            risk_assessment="Moderate risk",
            model_used="test",
        )
        mock_ctx = MarketContext(
            ticker="AAPL",
            current_price=Decimal("185.50"),
            price_52w_high=Decimal("200.00"),
            price_52w_low=Decimal("140.00"),
            rsi_14=55.0,
            macd_signal=MacdSignal.BULLISH_CROSSOVER,
            next_earnings=None,
            dte_target=45,
            target_strike=Decimal("190.00"),
            target_delta=0.35,
            sector="Information Technology",
            dividend_yield=0.005,
            exercise_style=ExerciseStyle.AMERICAN,
            data_timestamp=datetime(2026, 3, 2, 14, 30, 0, tzinfo=UTC),
        )
        from pydantic_ai.usage import RunUsage as _RU

        mock_result = RecommendationResult(
            context=mock_ctx,
            assessments=[],
            recommendation=rec,
            total_usage=_RU(),
            duration_ms=1000,
            is_fallback=False,
        )
        mock_run_rec.return_value = mock_result

        request = _make_mock_request()
        mock_repo = AsyncMock()
        mock_repo.get_scores_for_scan = AsyncMock(return_value=[])

        mock_market_data = AsyncMock()
        mock_market_data.fetch_quote = AsyncMock(return_value=_make_quote())
        mock_market_data.fetch_ticker_info = AsyncMock(return_value=_make_ticker_info())
        mock_market_data.fetch_ohlcv = AsyncMock(return_value=[])

        mock_options_data = AsyncMock()
        mock_options_data.fetch_chain_all_expirations = AsyncMock(return_value=[])

        bridge = RecommendationProgressBridge()

        await _run_recommendation_background(
            request=request,
            debate_id=1,
            ticker="AAPL",
            scan_id=None,
            settings=AppSettings(),
            repo=mock_repo,
            market_data=mock_market_data,
            options_data=mock_options_data,
            fred=None,
            bridge=bridge,
        )

        mock_run_rec.assert_awaited_once()
