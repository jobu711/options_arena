"""Tests for RecommendationMixin — recommendation result persistence.

Covers:
  - Save returns positive integer ID.
  - Round-trip (save -> get by ID) preserves all fields.
  - Not-found returns None.
  - Recent recommendations are ordered newest first.
  - Limit parameter is respected.
  - Ticker filtering returns only matching rows.
  - AnyAssessment JSON round-trip via discriminated union.
  - Decimal fields (entry_price, stop_loss, take_profit) survive as strings.
  - scan_run_id=None stores as NULL and reads back correctly.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
import pytest_asyncio
from pydantic_ai.usage import RunUsage

from options_arena.data import Database, RecommendationRow, Repository
from options_arena.models import (
    AnyAssessment,
    DeskType,
    PositionRecommendation,
    RecommendationResult,
    SignalDirection,
    TrendAssessment,
    VolatilityAssessment,
)
from options_arena.models.enums import SpreadType, VolRegime
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


class TestRecommendationMixin:
    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_save_recommendation_returns_id(self, repo: Repository) -> None:
        """Verify save_recommendation returns a positive integer ID."""
        result = _make_recommendation_result()
        row_id = await repo.save_recommendation(result, scan_run_id=None)
        assert isinstance(row_id, int)
        assert row_id > 0

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_get_recommendation_by_id_round_trip(self, repo: Repository) -> None:
        """Verify save -> get by ID preserves all fields."""
        result = _make_recommendation_result()
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None
        assert isinstance(row, RecommendationRow)

        rec = result.recommendation
        assert row.id == row_id
        assert row.ticker == rec.ticker
        assert row.scan_run_id is None
        assert row.direction == rec.direction.value
        assert row.confidence == pytest.approx(rec.confidence, abs=1e-6)
        assert row.recommended_contract == rec.recommended_contract
        assert row.entry_price == str(rec.entry_price)
        assert row.entry_criteria == rec.entry_criteria
        assert row.exit_criteria == rec.exit_criteria
        assert row.stop_loss == str(rec.stop_loss)
        assert row.take_profit == str(rec.take_profit)
        assert row.position_size_pct == pytest.approx(rec.position_size_pct, abs=1e-6)
        assert row.risk_reward_ratio == pytest.approx(rec.risk_reward_ratio, abs=1e-6)
        assert row.recommended_strategy == rec.recommended_strategy.value  # type: ignore[union-attr]
        assert row.summary == rec.summary
        assert row.risk_assessment == rec.risk_assessment
        assert row.agent_agreement_score == pytest.approx(
            rec.agent_agreement_score,
            abs=1e-6,  # type: ignore[arg-type]
        )
        assert row.total_input_tokens == 1500
        assert row.total_output_tokens == 800
        assert row.duration_ms == 3200
        assert row.is_fallback is False
        assert row.citation_density == pytest.approx(0.45, abs=1e-6)
        assert row.model_used == rec.model_used

        # JSON fields
        key_factors = json.loads(row.key_factors_json)
        assert key_factors == rec.key_factors

        dissenting = json.loads(row.dissenting_desks_json)
        assert dissenting == [d.value for d in rec.dissenting_desks]

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_get_recommendation_by_id_not_found(self, repo: Repository) -> None:
        """Verify get_recommendation_by_id returns None for unknown ID."""
        row = await repo.get_recommendation_by_id(99999)
        assert row is None

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_get_recent_recommendations_ordered(self, repo: Repository) -> None:
        """Verify get_recent_recommendations returns newest first (by ID desc)."""
        result = _make_recommendation_result()
        id1 = await repo.save_recommendation(result, scan_run_id=None)
        id2 = await repo.save_recommendation(result, scan_run_id=None)
        id3 = await repo.save_recommendation(result, scan_run_id=None)

        rows = await repo.get_recent_recommendations(limit=10)
        assert len(rows) == 3
        assert rows[0].id == id3
        assert rows[1].id == id2
        assert rows[2].id == id1

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_get_recent_recommendations_respects_limit(self, repo: Repository) -> None:
        """Verify limit parameter works correctly."""
        result = _make_recommendation_result()
        for _ in range(5):
            await repo.save_recommendation(result, scan_run_id=None)

        rows = await repo.get_recent_recommendations(limit=3)
        assert len(rows) == 3

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_get_recommendations_for_ticker_filters(self, repo: Repository) -> None:
        """Verify ticker filtering returns only matching rows."""
        aapl_result = _make_recommendation_result()
        msft_rec = _make_recommendation(ticker="MSFT", recommended_contract="MSFT 400C 2026-04-18")
        msft_result = _make_recommendation_result(recommendation=msft_rec)

        await repo.save_recommendation(aapl_result, scan_run_id=None)
        await repo.save_recommendation(msft_result, scan_run_id=None)
        await repo.save_recommendation(aapl_result, scan_run_id=None)

        aapl_rows = await repo.get_recommendations_for_ticker("AAPL", limit=10)
        assert len(aapl_rows) == 2
        assert all(r.ticker == "AAPL" for r in aapl_rows)

        msft_rows = await repo.get_recommendations_for_ticker("MSFT", limit=10)
        assert len(msft_rows) == 1
        assert msft_rows[0].ticker == "MSFT"

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_assessments_json_round_trip(self, repo: Repository) -> None:
        """Verify AnyAssessment list survives JSON serialization to DB and back."""
        trend = _make_trend_assessment()
        vol = _make_vol_assessment()
        result = _make_recommendation_result(assessments=[trend, vol])

        row_id = await repo.save_recommendation(result, scan_run_id=None)
        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None

        # Parse the JSON back and validate via Pydantic discriminated union
        raw_list = json.loads(row.assessments_json)
        assert len(raw_list) == 2

        # Validate that discriminated union round-trips
        from pydantic import TypeAdapter

        adapter = TypeAdapter(list[AnyAssessment])
        assessments = adapter.validate_python(raw_list)
        assert len(assessments) == 2
        assert isinstance(assessments[0], TrendAssessment)
        assert isinstance(assessments[1], VolatilityAssessment)
        assert assessments[0].trend_strength == pytest.approx(0.82, abs=1e-6)
        assert assessments[1].iv_regime == VolRegime.LOW

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_decimal_fields_preserved(self, repo: Repository) -> None:
        """Verify entry_price, stop_loss, take_profit Decimal precision."""
        rec = _make_recommendation(
            entry_price=Decimal("1.05"),
            stop_loss=Decimal("0.50"),
            take_profit=Decimal("2.10"),
        )
        result = _make_recommendation_result(recommendation=rec)

        row_id = await repo.save_recommendation(result, scan_run_id=None)
        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None

        # Verify string representations match exactly (no float precision loss)
        assert row.entry_price == "1.05"
        assert row.stop_loss == "0.50"
        assert row.take_profit == "2.10"

        # Verify they can be reconstructed as Decimal
        assert Decimal(row.entry_price) == Decimal("1.05")
        assert Decimal(row.stop_loss) == Decimal("0.50")
        assert Decimal(row.take_profit) == Decimal("2.10")

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_save_with_null_scan_run_id(self, repo: Repository) -> None:
        """Verify scan_run_id=None stores as NULL and reads back correctly."""
        result = _make_recommendation_result()
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None
        assert row.scan_run_id is None

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_is_fallback_true_round_trip(self, repo: Repository) -> None:
        """Verify is_fallback=True stored as 1, read back as True."""
        result = _make_recommendation_result(is_fallback=True)
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None
        assert row.is_fallback is True

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_empty_dissenting_desks_round_trip(self, repo: Repository) -> None:
        """Verify empty dissenting_desks list serializes as '[]'."""
        rec = _make_recommendation(dissenting_desks=[])
        result = _make_recommendation_result(recommendation=rec)
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None
        assert json.loads(row.dissenting_desks_json) == []

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_null_optional_fields(self, repo: Repository) -> None:
        """Verify stop_loss=None, take_profit=None, recommended_strategy=None."""
        rec = _make_recommendation(
            stop_loss=None,
            take_profit=None,
            recommended_strategy=None,
            agent_agreement_score=None,
        )
        result = _make_recommendation_result(recommendation=rec)
        row_id = await repo.save_recommendation(result, scan_run_id=None)

        row = await repo.get_recommendation_by_id(row_id)
        assert row is not None
        assert row.stop_loss is None
        assert row.take_profit is None
        assert row.recommended_strategy is None
        assert row.agent_agreement_score is None

    @pytest.mark.asyncio
    @pytest.mark.db
    async def test_empty_db_returns_empty_list(self, repo: Repository) -> None:
        """Verify get_recent_recommendations returns [] on empty DB."""
        rows = await repo.get_recent_recommendations()
        assert rows == []
