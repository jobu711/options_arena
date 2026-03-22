"""Recommendation system API regression tests (#667).

Verifies cutover-specific regression scenarios for the recommendation API:
schema shape consistency, dual-table GET semantics, response field accuracy,
and batch-start error handling. Avoids duplicating tests already in
``test_recommendation_routes.py`` and ``test_recommendation_schemas.py``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.api.deps import get_operation_lock
from options_arena.data._recommendation import RecommendationRow
from options_arena.data.repository import DebateRow
from options_arena.models import (
    AgentResponse,
    SignalDirection,
    TradeThesis,
)

# ---------------------------------------------------------------------------
# Helpers — RecommendationRow & DebateRow builders
# ---------------------------------------------------------------------------


def _make_recommendation_row(
    rec_id: int = 1,
    *,
    ticker: str = "AAPL",
    is_fallback: bool = False,
    confidence: float = 0.75,
) -> RecommendationRow:
    """Build a ``RecommendationRow`` with customizable core fields."""
    assessments = [
        {
            "desk": "trend",
            "direction": "bullish",
            "confidence": 0.8,
            "summary": "Strong uptrend.",
            "key_factors": ["ADX > 25"],
            "risks": ["Earnings in 14 days"],
            "contracts_referenced": [f"{ticker} 190C"],
            "tools_used": ["fetch_quote"],
            "model_used": "llama-3.3-70b-versatile",
        },
        {
            "desk": "volatility",
            "direction": "bullish",
            "confidence": 0.65,
            "summary": "IV at moderate levels.",
            "key_factors": ["IV rank 45"],
            "risks": ["Potential IV expansion"],
            "contracts_referenced": [f"{ticker} 190C"],
            "tools_used": ["fetch_chain"],
            "model_used": "llama-3.3-70b-versatile",
        },
    ]
    return RecommendationRow(
        id=rec_id,
        ticker=ticker,
        scan_run_id=None,
        direction="bullish",
        confidence=confidence,
        recommended_contract=f"{ticker} 190C 2026-04-18",
        entry_price="5.25",
        entry_criteria="Buy on pullback.",
        exit_criteria="Exit at 50% profit.",
        stop_loss="3.00",
        take_profit="8.00",
        position_size_pct=0.05,
        risk_reward_ratio=1.5,
        recommended_strategy="vertical",
        summary=f"Bullish momentum play on {ticker}.",
        key_factors_json=json.dumps(["Strong uptrend"]),
        risk_assessment="Moderate risk.",
        agent_agreement_score=0.85,
        dissenting_desks_json=json.dumps([]),
        assessments_json=json.dumps(assessments),
        total_input_tokens=3000,
        total_output_tokens=2000,
        duration_ms=4500,
        is_fallback=is_fallback,
        citation_density=0.45,
        position_rationale="Position sized for moderate conviction.",
        strategy_rationale="Bull call spread for defined risk.",
        max_loss_estimate="$250 per contract",
        model_used="data-driven-fallback" if is_fallback else "llama-3.3-70b-versatile",
        created_at="2026-03-22T12:00:00+00:00",
    )


def _make_debate_row(debate_id: int = 1, *, ticker: str = "AAPL") -> DebateRow:
    """Build a legacy ``DebateRow`` for backward-compat tests."""
    bull = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        argument="Strong momentum.",
        key_points=["RSI trending up"],
        risks_cited=["Earnings risk"],
        contracts_referenced=[f"{ticker} 190C"],
        model_used="llama-3.3-70b",
    )
    thesis = TradeThesis(
        ticker=ticker,
        direction=SignalDirection.BULLISH,
        confidence=0.70,
        summary="Buy the dip.",
        bull_score=7.5,
        bear_score=4.5,
        key_factors=["Strong RSI"],
        risk_assessment="Moderate risk.",
    )
    return DebateRow(
        id=debate_id,
        scan_run_id=1,
        ticker=ticker,
        bull_json=bull.model_dump_json(),
        bear_json=bull.model_dump_json(),
        risk_json=thesis.model_dump_json(),
        verdict_json=thesis.model_dump_json(),
        vol_json=None,
        rebuttal_json=None,
        total_tokens=1000,
        model_name="llama-3.3-70b",
        duration_ms=5000,
        is_fallback=False,
        created_at=datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Regression: recommendation response schema shape
# ---------------------------------------------------------------------------


class TestRecommendationResponseShape:
    """Verify the recommendation response has ALL expected top-level fields.

    This catches regressions where field renames or removals silently break
    the API contract during cutover.
    """

    @pytest.mark.critical
    async def test_recommendation_response_has_required_fields(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """GET /api/debate/{id} response includes all unified_v1 fields."""
        mock_repo.get_recommendation_by_id = AsyncMock(
            return_value=_make_recommendation_row(rec_id=10)
        )
        response = await client.get("/api/debate/10")
        assert response.status_code == 200
        data = response.json()

        # Top-level fields required by unified_v1 protocol
        required_fields = {
            "ticker",
            "recommendation",
            "assessments",
            "is_fallback",
            "recommendation_protocol",
            "model_used",
            "duration_ms",
        }
        missing = required_fields - set(data.keys())
        assert not missing, f"Missing top-level fields: {missing}"

        # Recommendation sub-object fields (per PositionRecommendationResponse schema)
        rec = data["recommendation"]
        rec_required = {
            "ticker",
            "direction",
            "confidence",
            "recommended_contract",
            "entry_price",
            "position_size_pct",
            "risk_reward_ratio",
            "rationale",
            "strategy_rationale",
        }
        rec_missing = rec_required - set(rec.keys())
        assert not rec_missing, f"Missing recommendation fields: {rec_missing}"

    async def test_recommendation_protocol_is_unified_v1(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Verify recommendation_protocol is 'unified_v1' for new data."""
        mock_repo.get_recommendation_by_id = AsyncMock(return_value=_make_recommendation_row())
        response = await client.get("/api/debate/1")
        assert response.status_code == 200
        assert response.json()["recommendation_protocol"] == "unified_v1"


# ---------------------------------------------------------------------------
# Regression: dual-table lookup semantics
# ---------------------------------------------------------------------------


class TestDualTableLookup:
    """Verify GET /api/debate/{id} correctly differentiates old vs new data."""

    async def test_recommendation_table_checked_first(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """When both tables have data for the same ID, recommendation wins."""
        mock_repo.get_recommendation_by_id = AsyncMock(
            return_value=_make_recommendation_row(rec_id=5)
        )
        # This should NOT be called if recommendation lookup succeeds
        mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row(debate_id=5))

        response = await client.get("/api/debate/5")
        assert response.status_code == 200
        data = response.json()
        # New format has "recommendation" key, old has "thesis"
        assert "recommendation" in data
        assert "recommendation_protocol" in data

    async def test_old_debate_lacks_recommendation_protocol(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Old debate format response does not include recommendation_protocol."""
        mock_repo.get_recommendation_by_id = AsyncMock(return_value=None)
        mock_repo.get_debate_by_id = AsyncMock(return_value=_make_debate_row(debate_id=42))

        response = await client.get("/api/debate/42")
        assert response.status_code == 200
        data = response.json()
        assert "thesis" in data
        # Old format should NOT have recommendation_protocol
        assert data.get("recommendation_protocol") is None or "recommendation_protocol" not in data

    async def test_neither_table_returns_404(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """ID in neither table produces 404."""
        mock_repo.get_recommendation_by_id = AsyncMock(return_value=None)
        mock_repo.get_debate_by_id = AsyncMock(return_value=None)

        response = await client.get("/api/debate/99999")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Regression: fallback flag propagation
# ---------------------------------------------------------------------------


class TestFallbackFlagPropagation:
    """Verify is_fallback and confidence are correctly propagated."""

    async def test_fallback_true_propagated(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """GET returns is_fallback=True and fallback model_used."""
        mock_repo.get_recommendation_by_id = AsyncMock(
            return_value=_make_recommendation_row(is_fallback=True)
        )
        response = await client.get("/api/debate/1")
        data = response.json()
        assert data["is_fallback"] is True
        assert data["model_used"] == "data-driven-fallback"

    async def test_fallback_false_propagated(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """GET returns is_fallback=False for normal recommendations."""
        mock_repo.get_recommendation_by_id = AsyncMock(
            return_value=_make_recommendation_row(is_fallback=False)
        )
        response = await client.get("/api/debate/1")
        data = response.json()
        assert data["is_fallback"] is False
        assert data["model_used"] != "data-driven-fallback"

    async def test_confidence_value_matches_row(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Confidence in response matches the stored confidence."""
        mock_repo.get_recommendation_by_id = AsyncMock(
            return_value=_make_recommendation_row(confidence=0.42)
        )
        response = await client.get("/api/debate/1")
        data = response.json()
        assert data["recommendation"]["confidence"] == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# Regression: assessments field shape
# ---------------------------------------------------------------------------


class TestAssessmentsShape:
    """Verify assessments array is correctly serialized from JSON blob."""

    async def test_assessments_array_present_and_nonempty(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Assessments array has at least one element for non-fallback."""
        mock_repo.get_recommendation_by_id = AsyncMock(return_value=_make_recommendation_row())
        response = await client.get("/api/debate/1")
        data = response.json()
        assert isinstance(data["assessments"], list)
        assert len(data["assessments"]) >= 1

    async def test_each_assessment_has_desk_and_direction(
        self, client: AsyncClient, mock_repo: MagicMock
    ) -> None:
        """Each assessment in the array has desk and direction fields."""
        mock_repo.get_recommendation_by_id = AsyncMock(return_value=_make_recommendation_row())
        response = await client.get("/api/debate/1")
        for assessment in response.json()["assessments"]:
            assert "desk" in assessment
            assert "direction" in assessment
            assert "confidence" in assessment


# ---------------------------------------------------------------------------
# Regression: operation mutex with concurrent requests
# ---------------------------------------------------------------------------


class TestOperationMutexRegression:
    """Verify operation mutex prevents concurrent recommendation starts."""

    async def test_concurrent_single_recommendations_409(
        self, client: AsyncClient, mock_repo: MagicMock, test_app: object
    ) -> None:
        """Two rapid POST /api/debate calls: second gets 409."""
        # Pre-lock to simulate an in-progress operation
        lock = asyncio.Lock()
        await lock.acquire()
        test_app.dependency_overrides[get_operation_lock] = lambda: lock  # type: ignore[union-attr]

        mock_repo.get_scores_for_scan = AsyncMock(return_value=[])

        response = await client.post("/api/debate/batch", json={"scan_id": 1, "tickers": ["AAPL"]})
        assert response.status_code == 409

        lock.release()
