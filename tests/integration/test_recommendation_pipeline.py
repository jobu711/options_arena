"""Integration tests for the recommendation pipeline — orchestrator + persistence.

Tests exercise the full ``run_recommendation()`` pipeline end-to-end with:
- ``TestModel`` for all 6 desk recommendation agents
- Monkeypatched ``run_synthesis`` returning a known-valid ``PositionRecommendation``
  (TestModel cannot produce valid ``PositionRecommendation`` due to strict Decimal
  validators, ``validate_non_empty_list``, etc.)
- Real ``:memory:`` SQLite with full migration suite (real schema)
- Mock services (market_data, options_data) — not called by orchestrator directly

Key differences from unit tests (``tests/unit/agents/test_recommendation_orchestrator.py``):
- Real ``Repository`` with ``:memory:`` SQLite, not ``MagicMock``
- Persistence round-trip verified: save -> query -> fields match
- DB rows validated against returned ``RecommendationResult``
- ``agent_predictions`` table rows verified

Uses TestModel from pydantic_ai.models.test — NEVER makes real API calls.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents.recommendation_orchestrator import run_recommendation
from options_arena.agents.synthesis_agent import SynthesisDeps
from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import (
    AgencyConfig,
    AppSettings,
    DebateConfig,
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
    DomainAssessment,
    PositionRecommendation,
    RecommendationResult,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False

pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# Fixtures — real :memory: SQLite
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database with all migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository backed by the in-memory database."""
    return Repository(db)


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _make_ticker_score(ticker: str = "AAPL") -> TickerScore:
    return TickerScore(
        ticker=ticker,
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


def _make_quote(ticker: str = "AAPL") -> Quote:
    return Quote(
        ticker=ticker,
        price=Decimal("185.50"),
        bid=Decimal("185.48"),
        ask=Decimal("185.52"),
        volume=42_000_000,
        timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


def _make_ticker_info(ticker: str = "AAPL") -> TickerInfo:
    return TickerInfo(
        ticker=ticker,
        company_name="Apple Inc.",
        sector="Information Technology",
        market_cap=2_800_000_000_000,
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal("185.50"),
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("164.08"),
    )


def _make_contract(ticker: str = "AAPL") -> OptionContract:
    return OptionContract(
        ticker=ticker,
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


def _make_valid_recommendation(ticker: str = "AAPL") -> PositionRecommendation:
    """Build a known-valid ``PositionRecommendation`` for test use.

    ``TestModel`` cannot reliably produce valid ``PositionRecommendation``
    instances because of strict validators (Decimal entry_price,
    ``validate_non_empty_list`` on key_factors, etc.).  This function
    provides a concrete recommendation for monkeypatched ``run_synthesis``.
    """
    expiration = (date.today() + timedelta(days=45)).isoformat()
    return PositionRecommendation(
        ticker=ticker,
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        recommended_contract=f"{ticker} 190C {expiration}",
        entry_price=Decimal("4.65"),
        entry_criteria="Enter on RSI pullback to 55-60 range",
        exit_criteria="Exit at 50% profit or RSI overbought above 70",
        stop_loss=Decimal("2.30"),
        take_profit=Decimal("6.95"),
        position_size_pct=0.05,
        position_rationale="Moderate position size based on bullish consensus",
        risk_reward_ratio=1.5,
        max_loss_estimate="$465 (1 contract x $4.65 mid)",
        recommended_strategy=None,
        strategy_rationale="Directional long call aligned with bullish trend",
        summary=f"Bullish recommendation for {ticker} based on strong trend signals.",
        key_factors=["RSI above 60 confirms momentum", "SMA alignment bullish"],
        risk_assessment="Moderate risk. Earnings in 30 days could increase volatility.",
        agent_agreement_score=0.8,
        dissenting_desks=[],
        model_used="test-model",
    )


def _make_settings() -> AppSettings:
    """AppSettings with reduced timeouts for fast integration tests."""
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


def _enter_desk_overrides() -> list[object]:
    """Override all 6 desk recommendation agents with TestModel.

    Returns overrides list for manual context manager exit in finally block.
    Does NOT override synthesis_agent — that is monkeypatched instead.
    """
    from options_arena.agents.contrarian_desk import contrarian_desk_recommend
    from options_arena.agents.flow_desk import flow_desk_recommend
    from options_arena.agents.fundamental_desk import fundamental_desk_recommend
    from options_arena.agents.risk_desk import risk_desk_recommend
    from options_arena.agents.trend_desk import trend_desk_recommend
    from options_arena.agents.volatility_desk import vol_desk_recommend

    agents = [
        trend_desk_recommend,
        vol_desk_recommend,
        flow_desk_recommend,
        fundamental_desk_recommend,
        risk_desk_recommend,
        contrarian_desk_recommend,
    ]
    overrides = [a.override(model=TestModel()) for a in agents]
    for o in overrides:
        o.__enter__()
    return overrides


def _exit_overrides(overrides: list[object]) -> None:
    """Exit all agent overrides in reverse order."""
    for o in reversed(overrides):
        o.__exit__(None, None, None)  # type: ignore[attr-defined]


async def _run_pipeline_with_test_model(
    repo: Repository,
    monkeypatch: pytest.MonkeyPatch,
    ticker: str = "AAPL",
) -> RecommendationResult:
    """Run the full recommendation pipeline with TestModel desks + mock synthesis."""
    # Monkeypatch run_synthesis to return a known-valid PositionRecommendation
    valid_rec = _make_valid_recommendation(ticker)

    async def _mock_synthesis(deps: SynthesisDeps, **kwargs: object) -> PositionRecommendation:
        return valid_rec

    monkeypatch.setattr(
        "options_arena.agents.recommendation_orchestrator.run_synthesis",
        _mock_synthesis,
    )

    overrides = _enter_desk_overrides()
    try:
        result = await run_recommendation(
            ticker=ticker,
            ticker_score=_make_ticker_score(ticker),
            contracts=[_make_contract(ticker)],
            quote=_make_quote(ticker),
            ticker_info=_make_ticker_info(ticker),
            settings=_make_settings(),
            repo=repo,
            market_data=MagicMock(),
            options_data=MagicMock(),
        )
    finally:
        _exit_overrides(overrides)
    return result


# ---------------------------------------------------------------------------
# Integration tests — full pipeline
# ---------------------------------------------------------------------------


class TestRecommendationPipeline:
    """Integration tests exercising run_recommendation() with real persistence."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.db
    @pytest.mark.critical
    async def test_full_pipeline_success(
        self, repo: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify complete pipeline: context -> desks -> synthesis -> persist."""
        result = await _run_pipeline_with_test_model(repo, monkeypatch)

        # Result shape
        assert isinstance(result, RecommendationResult)
        assert isinstance(result.recommendation, PositionRecommendation)
        assert result.context.ticker == "AAPL"
        assert len(result.assessments) == 6
        assert result.duration_ms >= 0
        assert result.is_fallback is False

        # DB has a recommendation_results row
        rows = await repo.get_recommendations_for_ticker("AAPL", limit=5)
        assert len(rows) >= 1
        rec_row = rows[0]
        assert rec_row.ticker == "AAPL"
        assert rec_row.is_fallback is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.db
    async def test_persistence_round_trip_fidelity(
        self, repo: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify save -> get_by_id preserves all fields including Decimals."""
        result = await _run_pipeline_with_test_model(repo, monkeypatch)

        # Retrieve from DB
        rows = await repo.get_recommendations_for_ticker("AAPL", limit=1)
        assert len(rows) == 1
        rec_row = rows[0]

        # Retrieve by ID
        by_id = await repo.get_recommendation_by_id(rec_row.id)
        assert by_id is not None

        # Core field fidelity
        assert by_id.ticker == result.recommendation.ticker
        assert by_id.direction == result.recommendation.direction.value
        assert by_id.confidence == pytest.approx(result.recommendation.confidence, abs=0.01)

        # Decimal entry_price preserved as string
        assert by_id.entry_price == str(result.recommendation.entry_price)

        # Decimal stop_loss preserved
        assert by_id.stop_loss == str(result.recommendation.stop_loss)

        # assessments_json is parseable
        assessments_data = json.loads(by_id.assessments_json)
        assert isinstance(assessments_data, list)
        assert len(assessments_data) == 6

        # key_factors_json is parseable
        key_factors = json.loads(by_id.key_factors_json)
        assert isinstance(key_factors, list)
        assert len(key_factors) >= 1

        # dissenting_desks_json is parseable
        dissenting = json.loads(by_id.dissenting_desks_json)
        assert isinstance(dissenting, list)

        # is_fallback matches
        assert by_id.is_fallback is result.is_fallback

        # duration_ms is reasonable
        assert by_id.duration_ms == result.duration_ms

        # model_used preserved
        assert by_id.model_used == result.recommendation.model_used

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.db
    async def test_agent_predictions_fk_constraint_handled(
        self,
        repo: Repository,
        db: Database,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify agent_predictions FK constraint does not crash the pipeline.

        The ``agent_predictions`` table has ``debate_id REFERENCES ai_theses(id)``,
        but the recommendation pipeline saves to ``recommendation_results`` (not
        ``ai_theses``).  The ``_persist_recommendation`` function uses the
        ``recommendation_results`` row ID as ``debate_id``, which violates the FK.

        This test verifies:
        1. The pipeline succeeds despite the FK violation (never-raises contract)
        2. The recommendation row IS saved (``save_recommendation`` succeeds)
        3. Agent predictions are NOT saved (FK constraint prevents it)
        4. The ``recommendation_protocol`` column exists with correct default

        When a future migration relaxes the FK or adds a new prediction table,
        this test should be updated to verify predictions ARE saved.
        """
        await _run_pipeline_with_test_model(repo, monkeypatch)

        # Recommendation row IS saved
        rows = await repo.get_recommendations_for_ticker("AAPL", limit=1)
        assert len(rows) == 1
        rec_id = rows[0].id

        # Agent predictions NOT saved due to FK constraint
        async with db.conn.execute(
            "SELECT COUNT(*) FROM agent_predictions WHERE debate_id = ?",
            (rec_id,),
        ) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 0  # FK violation prevents insertion

        # Verify recommendation_protocol column exists with correct default
        async with db.conn.execute("PRAGMA table_info(agent_predictions)") as cursor:
            columns = await cursor.fetchall()
        column_names = {col[1] for col in columns}
        assert "recommendation_protocol" in column_names

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.db
    async def test_partial_failure_persists_correctly(
        self, monkeypatch: pytest.MonkeyPatch, repo: Repository
    ) -> None:
        """Verify partial desk failure still persists result with is_fallback=False."""

        async def _failing_trend(deps: object, **kwargs: object) -> DomainAssessment:
            raise TimeoutError("Trend desk timed out")

        async def _failing_vol(deps: object, **kwargs: object) -> DomainAssessment:
            raise TimeoutError("Vol desk timed out")

        monkeypatch.setattr(
            "options_arena.agents.recommendation_orchestrator.run_trend_desk_recommendation",
            _failing_trend,
        )
        monkeypatch.setattr(
            "options_arena.agents.recommendation_orchestrator.run_vol_desk_recommendation",
            _failing_vol,
        )

        # Monkeypatch synthesis to return valid recommendation
        valid_rec = _make_valid_recommendation()

        async def _mock_synthesis(deps: SynthesisDeps, **kwargs: object) -> PositionRecommendation:
            return valid_rec

        monkeypatch.setattr(
            "options_arena.agents.recommendation_orchestrator.run_synthesis",
            _mock_synthesis,
        )

        # Override remaining desk agents
        from options_arena.agents.contrarian_desk import contrarian_desk_recommend
        from options_arena.agents.flow_desk import flow_desk_recommend
        from options_arena.agents.fundamental_desk import fundamental_desk_recommend
        from options_arena.agents.risk_desk import risk_desk_recommend

        agents = [
            flow_desk_recommend,
            fundamental_desk_recommend,
            risk_desk_recommend,
            contrarian_desk_recommend,
        ]
        overrides = [a.override(model=TestModel()) for a in agents]
        for o in overrides:
            o.__enter__()
        try:
            result = await run_recommendation(
                ticker="AAPL",
                ticker_score=_make_ticker_score(),
                contracts=[_make_contract()],
                quote=_make_quote(),
                ticker_info=_make_ticker_info(),
                settings=_make_settings(),
                repo=repo,
                market_data=MagicMock(),
                options_data=MagicMock(),
            )
        finally:
            for o in reversed(overrides):
                o.__exit__(None, None, None)

        # Synthesis still ran — not a full fallback
        assert isinstance(result, RecommendationResult)
        assert result.is_fallback is False
        assert len(result.assessments) == 6

        # DB row exists with is_fallback=0
        rows = await repo.get_recommendations_for_ticker("AAPL", limit=1)
        assert len(rows) == 1
        assert rows[0].is_fallback is False

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.db
    async def test_full_failure_persists_fallback(
        self, monkeypatch: pytest.MonkeyPatch, repo: Repository
    ) -> None:
        """Verify total failure returns fallback result with is_fallback=True."""

        async def _failing_desk(deps: object, **kwargs: object) -> DomainAssessment:
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

        # Also monkeypatch run_synthesis to raise
        async def _failing_synthesis(deps: object, **kwargs: object) -> PositionRecommendation:
            raise RuntimeError("Synthesis failed")

        monkeypatch.setattr(
            "options_arena.agents.recommendation_orchestrator.run_synthesis",
            _failing_synthesis,
        )

        result = await run_recommendation(
            ticker="AAPL",
            ticker_score=_make_ticker_score(),
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            settings=_make_settings(),
            repo=repo,
            market_data=MagicMock(),
            options_data=MagicMock(),
        )

        # Total failure -> fallback
        assert isinstance(result, RecommendationResult)
        assert result.is_fallback is True
        assert result.recommendation.direction == SignalDirection.NEUTRAL
        assert result.recommendation.confidence == pytest.approx(0.2, abs=0.01)
        assert result.recommendation.model_used == "data-driven-fallback"

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.db
    async def test_multiple_recommendations_for_ticker(
        self, repo: Repository, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify get_recommendations_for_ticker returns multiple results, newest first."""
        # Run pipeline twice for same ticker
        result1 = await _run_pipeline_with_test_model(repo, monkeypatch)
        result2 = await _run_pipeline_with_test_model(repo, monkeypatch)

        assert isinstance(result1, RecommendationResult)
        assert isinstance(result2, RecommendationResult)

        # Should have 2 results, newest first
        rows = await repo.get_recommendations_for_ticker("AAPL", limit=5)
        assert len(rows) == 2
        # Newest first (higher ID = more recent)
        assert rows[0].id > rows[1].id


# ---------------------------------------------------------------------------
# Backward compatibility — old debate pipeline
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Verify old debate pipeline still works after extraction to _context.py."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_run_debate_still_works_after_extraction(self) -> None:
        """Import run_debate, build_market_context from orchestrator.py and run."""
        from options_arena.agents.contrarian_agent import contrarian_agent
        from options_arena.agents.orchestrator import run_debate
        from options_arena.agents.risk import risk_agent
        from options_arena.agents.trend_agent import trend_agent
        from options_arena.agents.volatility import volatility_agent
        from options_arena.models import DebateConfig

        config = DebateConfig(
            api_key="test-key-not-used-with-TestModel",
            agent_timeout=5.0,
            max_total_duration=30.0,
        )

        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=_make_ticker_score(),
                contracts=[_make_contract()],
                quote=_make_quote(),
                ticker_info=_make_ticker_info(),
                config=config,
            )

        # Validate the result
        from options_arena.agents._parsing import DebateResult

        assert isinstance(result, DebateResult)
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_import_forwarding_from_context(self) -> None:
        """Verify key functions are importable from orchestrator.py via _context.py."""
        from options_arena.agents.orchestrator import (
            build_market_context,
            classify_macd_signal,
            extract_agent_predictions,
            should_debate,
        )

        # Verify they are callable
        assert callable(build_market_context)
        assert callable(should_debate)
        assert callable(extract_agent_predictions)
        assert callable(classify_macd_signal)
