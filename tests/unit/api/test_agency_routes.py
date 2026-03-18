"""Tests for agency API endpoints (POST /api/agency/query, GET /query/{id}, GET /queries).

All tests mock ``run_agency_query`` to avoid actual LLM calls. Uses the shared
conftest fixtures for the test app and async client.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from pydantic_ai import models

from options_arena.models import (
    AgencyResponse,
    DeskResponse,
    DeskType,
    QueryIntent,
    QueryType,
)

# Prevent accidental real LLM API calls in tests
models.ALLOW_MODEL_REQUESTS = False


def _make_agency_response(
    *,
    query_id: str = "test-uuid-1234",
    query_text: str = "What is the IV for AAPL?",
    confidence: float = 0.7,
) -> AgencyResponse:
    """Build a synthetic AgencyResponse for testing."""
    intent = QueryIntent(
        desks=[DeskType.VOLATILITY],
        query_type=QueryType.ANALYSIS,
        tickers=["AAPL"],
    )
    desk_resp = DeskResponse(
        desk=DeskType.VOLATILITY,
        response="AAPL IV rank is 45, IV percentile is 55.",
        tools_used=["fetch_quote"],
        confidence=0.7,
    )
    return AgencyResponse(
        query_id=query_id,
        query_text=query_text,
        intent=intent,
        desk_responses=[desk_resp],
        synthesis="[VOLATILITY] AAPL IV rank is 45, IV percentile is 55.",
        citations=[],
        confidence=confidence,
        created_at=datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# POST /api/agency/query
# ---------------------------------------------------------------------------


class TestSubmitQuery:
    """Tests for POST /api/agency/query."""

    @pytest.mark.asyncio
    @patch("options_arena.api.routes.agency.run_agency_query")
    @patch("options_arena.api.routes.agency.build_debate_model")
    async def test_submit_query_returns_agency_response(
        self,
        mock_build_model: MagicMock,
        mock_run_query: AsyncMock,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """POST /api/agency/query returns AgencyResponse with desk attribution."""
        response_obj = _make_agency_response()
        mock_run_query.return_value = response_obj
        mock_build_model.return_value = MagicMock()
        mock_repo.save_agency_query = AsyncMock(return_value=1)

        resp = await client.post(
            "/api/agency/query",
            json={"query": "What is the IV for AAPL?"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["query_text"] == "What is the IV for AAPL?"
        assert data["confidence"] == pytest.approx(0.7, abs=0.01)
        assert len(data["desk_responses"]) == 1
        assert data["desk_responses"][0]["desk"] == "volatility"

    @pytest.mark.asyncio
    @patch("options_arena.api.routes.agency.run_agency_query")
    @patch("options_arena.api.routes.agency.build_debate_model")
    async def test_submit_query_with_desk_override(
        self,
        mock_build_model: MagicMock,
        mock_run_query: AsyncMock,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """POST /api/agency/query with desk field routes directly to specified desk."""
        response_obj = _make_agency_response()
        mock_run_query.return_value = response_obj
        mock_build_model.return_value = MagicMock()
        mock_repo.save_agency_query = AsyncMock(return_value=1)

        resp = await client.post(
            "/api/agency/query",
            json={"query": "Check risk for TSLA", "desk": "risk"},
        )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("options_arena.api.routes.agency.run_agency_query")
    @patch("options_arena.api.routes.agency.build_debate_model")
    async def test_submit_query_with_tickers(
        self,
        mock_build_model: MagicMock,
        mock_run_query: AsyncMock,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """POST /api/agency/query with tickers passes them to routing."""
        response_obj = _make_agency_response()
        mock_run_query.return_value = response_obj
        mock_build_model.return_value = MagicMock()
        mock_repo.save_agency_query = AsyncMock(return_value=1)

        resp = await client.post(
            "/api/agency/query",
            json={"query": "Compare volatility", "tickers": ["AAPL", "MSFT"]},
        )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_submit_query_409_when_locked(
        self,
        test_app: object,
        client: AsyncClient,
    ) -> None:
        """POST /api/agency/query returns 409 when operation_lock is held."""
        from options_arena.api.deps import get_operation_lock  # noqa: PLC0415

        # Create a pre-locked Lock
        locked = asyncio.Lock()
        await locked.acquire()

        test_app.dependency_overrides[get_operation_lock] = lambda: locked  # type: ignore[union-attr]

        resp = await client.post(
            "/api/agency/query",
            json={"query": "What is the IV for AAPL?"},
        )

        assert resp.status_code == 409
        assert "Another operation" in resp.json()["detail"]

        locked.release()

    @pytest.mark.asyncio
    async def test_submit_query_empty_string_rejected(
        self,
        client: AsyncClient,
    ) -> None:
        """POST /api/agency/query with empty query returns 422."""
        resp = await client.post(
            "/api/agency/query",
            json={"query": ""},
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/agency/query/{query_id}
# ---------------------------------------------------------------------------


class TestGetQuery:
    """Tests for GET /api/agency/query/{query_id}."""

    @pytest.mark.asyncio
    async def test_get_query_returns_persisted_response(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """GET /api/agency/query/{id} returns stored AgencyResponse."""
        from options_arena.data._agency import AgencyQueryRow  # noqa: PLC0415

        response_obj = _make_agency_response(query_id="abc-123")
        row = AgencyQueryRow(
            id=1,
            query_id="abc-123",
            query_text="What is the IV?",
            desk="volatility",
            tickers_json='["AAPL"]',
            intent_json=response_obj.intent.model_dump_json(),
            response_json=response_obj.model_dump_json(),
            confidence=0.7,
            created_at="2026-03-18T12:00:00+00:00",
        )
        mock_repo.get_agency_query = AsyncMock(return_value=row)

        resp = await client.get("/api/agency/query/abc-123")

        assert resp.status_code == 200
        data = resp.json()
        assert data["query_id"] == "abc-123"
        assert data["confidence"] == pytest.approx(0.7, abs=0.01)

    @pytest.mark.asyncio
    async def test_get_query_not_found_returns_404(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """GET /api/agency/query/{id} with unknown ID returns 404."""
        mock_repo.get_agency_query = AsyncMock(return_value=None)

        resp = await client.get("/api/agency/query/nonexistent-id")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/agency/queries
# ---------------------------------------------------------------------------


class TestListQueries:
    """Tests for GET /api/agency/queries."""

    @pytest.mark.asyncio
    async def test_list_queries_returns_recent(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """GET /api/agency/queries returns list of recent queries."""
        from options_arena.data._agency import AgencyQueryRow  # noqa: PLC0415

        response_obj = _make_agency_response()
        row = AgencyQueryRow(
            id=1,
            query_id="test-uuid-1234",
            query_text="What is the IV?",
            desk="volatility",
            tickers_json='["AAPL"]',
            intent_json=response_obj.intent.model_dump_json(),
            response_json=response_obj.model_dump_json(),
            confidence=0.7,
            created_at="2026-03-18T12:00:00+00:00",
        )
        mock_repo.list_agency_queries = AsyncMock(return_value=[row])

        resp = await client.get("/api/agency/queries")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["query_id"] == "test-uuid-1234"

    @pytest.mark.asyncio
    async def test_list_queries_respects_limit(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """GET /api/agency/queries?limit=5 passes limit to repo query."""
        mock_repo.list_agency_queries = AsyncMock(return_value=[])

        resp = await client.get("/api/agency/queries?limit=5")

        assert resp.status_code == 200
        mock_repo.list_agency_queries.assert_awaited_once_with(limit=5)

    @pytest.mark.asyncio
    async def test_list_queries_empty_returns_empty_list(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """GET /api/agency/queries returns [] when no queries exist."""
        mock_repo.list_agency_queries = AsyncMock(return_value=[])

        resp = await client.get("/api/agency/queries")

        assert resp.status_code == 200
        assert resp.json() == []
