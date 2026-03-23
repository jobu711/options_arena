"""Tests for desk_metrics_json persistence in recommendation_results.

Covers:
  - Save and read with populated desk_metrics.
  - Empty desk_metrics saves as '[]'.
  - Migration 040 applies cleanly on fresh DB.
  - JSON round-trip preserves all DeskMetrics fields.
  - DeskMetrics with zero tokens serializes correctly.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
import pytest_asyncio
from pydantic_ai.usage import RunUsage

from options_arena.data import Database, RecommendationRow, Repository
from options_arena.models import (
    DeskMetrics,
    DeskType,
    PositionRecommendation,
    RecommendationResult,
    SignalDirection,
    TrendAssessment,
    VolatilityAssessment,
)
from options_arena.models.enums import (
    DeskRunStatus,
    ModelTier,
    SpreadType,
    VolRegime,
)
from tests.factories import make_market_context

pytestmark = pytest.mark.db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:  # type: ignore[misc]
    """Fresh in-memory database with all migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository backed by in-memory database."""
    return Repository(db)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_desk_metrics(**overrides: object) -> DeskMetrics:
    defaults: dict[str, object] = {
        "desk": DeskType.TREND,
        "status": DeskRunStatus.SUCCESS,
        "duration_ms": 1200,
        "model_tier": ModelTier.STANDARD,
        "model_used": "llama-3.3-70b-versatile",
        "input_tokens": 500,
        "output_tokens": 250,
    }
    defaults.update(overrides)
    return DeskMetrics(**defaults)  # type: ignore[arg-type]


def _make_trend_assessment(**overrides: object) -> TrendAssessment:
    defaults: dict[str, object] = {
        "desk": DeskType.TREND,
        "direction": SignalDirection.BULLISH,
        "confidence": 0.75,
        "summary": "Strong uptrend confirmed by ADX and SMA alignment.",
        "key_factors": ["ADX > 25", "SMA 20 > SMA 50"],
        "risks": ["RSI approaching overbought"],
        "contracts_referenced": ["AAPL 190C 2026-04-18"],
        "tools_used": ["fetch_indicators"],
        "model_used": "llama-3.3-70b-versatile",
        "trend_strength": 0.82,
        "momentum_signal": "bullish_crossover",
    }
    defaults.update(overrides)
    return TrendAssessment(**defaults)  # type: ignore[arg-type]


def _make_vol_assessment(**overrides: object) -> VolatilityAssessment:
    defaults: dict[str, object] = {
        "desk": DeskType.VOLATILITY,
        "direction": SignalDirection.BULLISH,
        "confidence": 0.65,
        "summary": "IV rank low — favorable for long premium.",
        "key_factors": ["IV rank at 25th percentile"],
        "risks": ["Earnings in 14 days could spike IV"],
        "contracts_referenced": ["AAPL 185C 2026-04-18"],
        "tools_used": ["fetch_iv_surface"],
        "model_used": "llama-3.3-70b-versatile",
        "iv_regime": VolRegime.LOW,
        "vol_skew_assessment": "Mild put skew",
    }
    defaults.update(overrides)
    return VolatilityAssessment(**defaults)  # type: ignore[arg-type]


def _make_recommendation(**overrides: object) -> PositionRecommendation:
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "direction": SignalDirection.BULLISH,
        "confidence": 0.72,
        "recommended_contract": "AAPL 190C 2026-04-18",
        "entry_price": Decimal("5.25"),
        "entry_criteria": "Enter on pullback to 185 support.",
        "exit_criteria": "Close at 50% profit or 30 DTE.",
        "stop_loss": Decimal("2.50"),
        "take_profit": Decimal("8.00"),
        "position_size_pct": 0.05,
        "position_rationale": "Moderate position given supportive trend.",
        "risk_reward_ratio": 1.8,
        "max_loss_estimate": "$525 per contract",
        "recommended_strategy": SpreadType.VERTICAL,
        "strategy_rationale": "Vertical spread reduces premium outlay.",
        "summary": "Bullish AAPL trade with defined risk via vertical spread.",
        "key_factors": ["Strong trend", "Low IV rank", "Supportive flow"],
        "risk_assessment": "Moderate risk — earnings in 14 days.",
        "agent_agreement_score": 0.85,
        "dissenting_desks": [DeskType.CONTRARIAN],
        "model_used": "llama-3.3-70b-versatile",
    }
    defaults.update(overrides)
    return PositionRecommendation(**defaults)  # type: ignore[arg-type]


def _make_recommendation_result(**overrides: object) -> RecommendationResult:
    defaults: dict[str, object] = {
        "context": make_market_context(),
        "assessments": [_make_trend_assessment(), _make_vol_assessment()],
        "recommendation": _make_recommendation(),
        "total_usage": RunUsage(input_tokens=1500, output_tokens=800),
        "duration_ms": 3200,
        "is_fallback": False,
        "citation_density": 0.45,
    }
    defaults.update(overrides)
    return RecommendationResult(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeskMetricsPersistence:
    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_save_and_read_with_desk_metrics(self, repo: Repository) -> None:
        """Verify desk_metrics_json round-trips through save/read."""
        metrics = [
            _make_desk_metrics(desk=DeskType.TREND, duration_ms=1200, input_tokens=500),
            _make_desk_metrics(
                desk=DeskType.VOLATILITY,
                status=DeskRunStatus.FALLBACK,
                duration_ms=800,
                model_tier=ModelTier.FAST,
                model_used="llama-3.1-8b-instant",
                input_tokens=300,
                output_tokens=150,
            ),
        ]
        result = _make_recommendation_result(desk_metrics=metrics)
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None
        assert isinstance(row, RecommendationRow)

        parsed = json.loads(row.desk_metrics_json)
        assert len(parsed) == 2
        assert parsed[0]["desk"] == "trend"
        assert parsed[0]["duration_ms"] == 1200
        assert parsed[1]["desk"] == "volatility"
        assert parsed[1]["status"] == "fallback"
        assert parsed[1]["model_tier"] == "fast"

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_empty_desk_metrics_saves_empty_array(self, repo: Repository) -> None:
        """Verify empty desk_metrics list saves as '[]'."""
        result = _make_recommendation_result(desk_metrics=[])
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None
        assert row.desk_metrics_json == "[]"
        assert json.loads(row.desk_metrics_json) == []

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_pre_migration_rows_return_empty_list(self, repo: Repository) -> None:
        """Verify rows without desk_metrics (default column value) return empty array."""
        # Save without desk_metrics — defaults to empty list on the model
        result = _make_recommendation_result()
        assert result.desk_metrics == []  # default_factory=list

        row_id = await repo.save_recommendation(result, scan_run_id=None)
        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None
        assert json.loads(row.desk_metrics_json) == []

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_desk_metrics_json_contains_all_fields(self, repo: Repository) -> None:
        """Verify serialized JSON has desk, tier, model, tokens, duration, status."""
        metrics = [
            _make_desk_metrics(
                desk=DeskType.RISK,
                status=DeskRunStatus.SUCCESS,
                duration_ms=2000,
                model_tier=ModelTier.PREMIUM,
                model_used="claude-sonnet-4-20250514",
                input_tokens=1000,
                output_tokens=500,
            ),
        ]
        result = _make_recommendation_result(desk_metrics=metrics)
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None

        parsed = json.loads(row.desk_metrics_json)
        assert len(parsed) == 1
        m = parsed[0]

        # All expected fields present
        assert m["desk"] == "risk"
        assert m["status"] == "success"
        assert m["duration_ms"] == 2000
        assert m["model_tier"] == "premium"
        assert m["model_used"] == "claude-sonnet-4-20250514"
        assert m["input_tokens"] == 1000
        assert m["output_tokens"] == 500

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_migration_040_applies_cleanly(self, db: Database) -> None:
        """Verify migration 040 runs without errors on fresh DB."""
        # The db fixture already ran all migrations (including 040) successfully.
        # Verify the column exists by querying table_info.
        async with db.conn.execute("PRAGMA table_info(recommendation_results)") as cursor:
            columns = await cursor.fetchall()

        column_names = [col[1] for col in columns]
        assert "desk_metrics_json" in column_names

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_desk_metrics_with_zero_tokens(self, repo: Repository) -> None:
        """Verify DeskMetrics with zero tokens serializes correctly."""
        metrics = [
            _make_desk_metrics(input_tokens=0, output_tokens=0),
        ]
        result = _make_recommendation_result(desk_metrics=metrics)
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None

        parsed = json.loads(row.desk_metrics_json)
        assert len(parsed) == 1
        assert parsed[0]["input_tokens"] == 0
        assert parsed[0]["output_tokens"] == 0

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_desk_metrics_json_round_trip_to_model(self, repo: Repository) -> None:
        """Verify JSON can be deserialized back into DeskMetrics models."""
        original_metrics = [
            _make_desk_metrics(desk=DeskType.FLOW, model_tier=ModelTier.FAST),
            _make_desk_metrics(desk=DeskType.FUNDAMENTAL, model_tier=ModelTier.PREMIUM),
        ]
        result = _make_recommendation_result(desk_metrics=original_metrics)
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None

        parsed = json.loads(row.desk_metrics_json)
        reconstructed = [DeskMetrics(**m) for m in parsed]
        assert len(reconstructed) == 2
        assert reconstructed[0].desk == DeskType.FLOW
        assert reconstructed[0].model_tier == ModelTier.FAST
        assert reconstructed[1].desk == DeskType.FUNDAMENTAL
        assert reconstructed[1].model_tier == ModelTier.PREMIUM
