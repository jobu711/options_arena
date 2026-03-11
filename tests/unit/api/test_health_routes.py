"""Tests for the health check API endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.critical
@pytest.mark.asyncio
async def test_health_check_returns_ok(client: AsyncClient) -> None:
    """GET /api/health returns 200 with status ok."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_openapi_docs_accessible(client: AsyncClient) -> None:
    """GET /docs returns the auto-generated OpenAPI docs page."""
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "swagger-ui" in response.text.lower() or "openapi" in response.text.lower()


@pytest.mark.asyncio
async def test_openapi_schema_accessible(client: AsyncClient) -> None:
    """GET /openapi.json returns the OpenAPI schema."""
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Options Arena"
    assert "/api/health" in schema["paths"]
