"""Tests for scan API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.models import (
    GICSSector,
    IndicatorSignals,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
)


def _make_scan_run(scan_id: int = 1) -> ScanRun:
    return ScanRun(
        id=scan_id,
        started_at=datetime(2026, 2, 26, 10, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 2, 26, 10, 5, 0, tzinfo=UTC),
        preset=ScanPreset.SP500,
        tickers_scanned=500,
        tickers_scored=450,
        recommendations=8,
    )


def _make_ticker_score(ticker: str = "AAPL", score: float = 78.5) -> TickerScore:
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.2, adx=28.4),
        scan_run_id=1,
    )


async def test_list_scans_empty(client: AsyncClient) -> None:
    """GET /api/scan returns empty list when no scans."""
    response = await client.get("/api/scan")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.critical
async def test_list_scans_returns_data(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan returns scan list."""
    mock_repo.get_recent_scans = AsyncMock(return_value=[_make_scan_run()])
    response = await client.get("/api/scan")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["preset"] == "sp500"
    assert data[0]["tickers_scanned"] == 500


async def test_list_scans_with_limit(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan?limit=5 passes limit to repo."""
    mock_repo.get_recent_scans = AsyncMock(return_value=[])
    response = await client.get("/api/scan?limit=5")
    assert response.status_code == 200
    mock_repo.get_recent_scans.assert_called_once_with(limit=5)


async def test_get_scan_not_found(client: AsyncClient) -> None:
    """GET /api/scan/999 returns 404 when scan not found."""
    response = await client.get("/api/scan/999")
    assert response.status_code == 404


async def test_get_scan_found(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/1 returns scan metadata."""
    mock_repo.get_scan_by_id = AsyncMock(return_value=_make_scan_run())
    response = await client.get("/api/scan/1")
    assert response.status_code == 200
    assert response.json()["tickers_scanned"] == 500


async def test_get_scores_scan_not_found(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/999/scores returns 404 when scan doesn't exist."""
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    mock_repo.get_scan_by_id = AsyncMock(return_value=None)
    response = await client.get("/api/scan/999/scores")
    assert response.status_code == 404


async def test_get_scores_returns_paginated(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/1/scores returns paginated scores."""
    scores = [_make_ticker_score("AAPL", 80.0), _make_ticker_score("MSFT", 75.0)]
    mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)
    response = await client.get("/api/scan/1/scores")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["pages"] == 1
    assert len(data["items"]) == 2


async def test_get_scores_with_search(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/1/scores?search=AAPL filters by ticker."""
    scores = [_make_ticker_score("AAPL", 80.0), _make_ticker_score("MSFT", 75.0)]
    mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)
    response = await client.get("/api/scan/1/scores?search=AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["ticker"] == "AAPL"


async def test_get_scores_with_min_score(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/1/scores?min_score=77 filters by minimum score."""
    scores = [_make_ticker_score("AAPL", 80.0), _make_ticker_score("MSFT", 75.0)]
    mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)
    response = await client.get("/api/scan/1/scores?min_score=77")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["ticker"] == "AAPL"


async def test_get_scores_with_direction(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/1/scores?direction=bullish filters by direction."""
    scores = [
        _make_ticker_score("AAPL", 80.0),
        TickerScore(
            ticker="TSLA",
            composite_score=70.0,
            direction=SignalDirection.BEARISH,
            signals=IndicatorSignals(),
            scan_run_id=1,
        ),
    ]
    mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)
    response = await client.get("/api/scan/1/scores?direction=bullish")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1


async def test_get_scores_sorted_ascending(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/1/scores?order=asc sorts ascending."""
    scores = [_make_ticker_score("AAPL", 80.0), _make_ticker_score("MSFT", 75.0)]
    mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)
    response = await client.get("/api/scan/1/scores?order=asc")
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["ticker"] == "MSFT"  # lower score first


async def test_get_ticker_detail_found(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/1/scores/AAPL returns ticker detail."""
    scores = [_make_ticker_score("AAPL", 80.0)]
    mock_repo.get_scores_for_scan = AsyncMock(return_value=scores)
    mock_repo.get_contracts_for_scan = AsyncMock(return_value=[])
    response = await client.get("/api/scan/1/scores/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "AAPL"
    assert data["composite_score"] == pytest.approx(80.0)


async def test_get_ticker_detail_not_found(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/1/scores/BADTK returns 404."""
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])
    response = await client.get("/api/scan/1/scores/BADTK")
    assert response.status_code == 404


async def test_cancel_scan_no_active(client: AsyncClient) -> None:
    """DELETE /api/scan/current returns 404 when no scan running."""
    response = await client.delete("/api/scan/current")
    assert response.status_code == 404


async def test_post_scan_returns_202(client: AsyncClient) -> None:
    """POST /api/scan returns 202 with scan_id (counter-based, no DB placeholder)."""
    response = await client.post("/api/scan", json={"preset": "sp500"})
    assert response.status_code == 202
    data = response.json()
    assert data["scan_id"] >= 1


async def test_post_scan_with_sectors_returns_202(client: AsyncClient) -> None:
    """POST /api/scan with sectors normalizes aliases and returns 202."""
    response = await client.post("/api/scan", json={"preset": "sp500", "sectors": ["technology"]})
    assert response.status_code == 202
    data = response.json()
    assert data["scan_id"] >= 1


async def test_post_scan_with_invalid_sector_returns_422(client: AsyncClient) -> None:
    """POST /api/scan with invalid sector returns 422."""
    response = await client.post(
        "/api/scan", json={"preset": "sp500", "sectors": ["nonexistent_sector"]}
    )
    assert response.status_code == 422


async def test_post_scan_with_empty_sectors(client: AsyncClient) -> None:
    """POST /api/scan with empty sectors list is valid (no filtering)."""
    response = await client.post("/api/scan", json={"preset": "sp500", "sectors": []})
    assert response.status_code == 202


async def test_get_scores_includes_sector_field(client: AsyncClient, mock_repo: MagicMock) -> None:
    """GET /api/scan/1/scores returns TickerScore with sector and company_name."""
    score = TickerScore(
        ticker="AAPL",
        composite_score=85.0,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.2, adx=28.4),
        scan_run_id=1,
        sector=GICSSector.INFORMATION_TECHNOLOGY,
        company_name="Apple Inc.",
    )
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[score])
    response = await client.get("/api/scan/1/scores")
    assert response.status_code == 200
    data = response.json()
    item = data["items"][0]
    assert item["sector"] == "Information Technology"
    assert item["company_name"] == "Apple Inc."


async def test_get_scores_sector_null_when_missing(
    client: AsyncClient, mock_repo: MagicMock
) -> None:
    """GET /api/scan/1/scores returns null sector when not populated."""
    score = _make_ticker_score("AAPL", 80.0)
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[score])
    response = await client.get("/api/scan/1/scores")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["sector"] is None
    assert item["company_name"] is None
