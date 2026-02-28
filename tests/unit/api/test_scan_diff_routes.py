"""Tests for GET /api/scan/{id}/diff endpoint.

Covers: happy path, edge cases (not found, empty scans), sort order, missing params.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.models import (
    IndicatorSignals,
    ScanPreset,
    ScanRun,
    SignalDirection,
    TickerScore,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_ticker_score(
    ticker: str = "AAPL",
    score: float = 78.5,
    direction: SignalDirection = SignalDirection.BULLISH,
    scan_run_id: int = 1,
) -> TickerScore:
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=direction,
        signals=IndicatorSignals(rsi=65.2, adx=28.4),
        scan_run_id=scan_run_id,
    )


# ===================================================================
# Tests
# ===================================================================


async def test_diff_happy_path(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Diff returns correct added, removed, and movers."""
    mock_repo.get_scan_by_id = AsyncMock(side_effect=lambda sid: _make_scan_run(sid))

    current_scores = [
        _make_ticker_score("AAPL", 85.0, scan_run_id=2),
        _make_ticker_score("MSFT", 72.0, scan_run_id=2),
        _make_ticker_score("NVDA", 90.0, scan_run_id=2),
    ]
    base_scores = [
        _make_ticker_score("AAPL", 78.0, scan_run_id=1),
        _make_ticker_score("MSFT", 80.0, scan_run_id=1),
        _make_ticker_score("GE", 60.0, scan_run_id=1),
    ]

    async def mock_scores(scan_id: int) -> list[TickerScore]:
        if scan_id == 2:
            return current_scores
        return base_scores

    mock_repo.get_scores_for_scan = AsyncMock(side_effect=mock_scores)

    response = await client.get("/api/scan/2/diff?base_id=1")
    assert response.status_code == 200
    data = response.json()

    assert data["current_scan_id"] == 2
    assert data["base_scan_id"] == 1
    assert "NVDA" in data["added"]
    assert "GE" in data["removed"]

    movers = data["movers"]
    assert len(movers) >= 2

    nvda_mover = next(m for m in movers if m["ticker"] == "NVDA")
    assert nvda_mover["is_new"] is True
    assert nvda_mover["previous_score"] == pytest.approx(0.0)

    aapl_mover = next(m for m in movers if m["ticker"] == "AAPL")
    assert aapl_mover["score_change"] == pytest.approx(7.0)
    assert aapl_mover["is_new"] is False


async def test_diff_current_scan_not_found(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Returns 404 when current scan doesn't exist."""
    mock_repo.get_scan_by_id = AsyncMock(return_value=None)
    response = await client.get("/api/scan/999/diff?base_id=1")
    assert response.status_code == 404
    assert "999" in response.json()["detail"]


async def test_diff_base_scan_not_found(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Returns 404 when base scan doesn't exist."""

    async def mock_scan(sid: int) -> ScanRun | None:
        if sid == 2:
            return _make_scan_run(2)
        return None

    mock_repo.get_scan_by_id = AsyncMock(side_effect=mock_scan)
    response = await client.get("/api/scan/2/diff?base_id=999")
    assert response.status_code == 404
    assert "999" in response.json()["detail"]


async def test_diff_no_base_scores(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Base scan with no scores treats all current tickers as new."""
    mock_repo.get_scan_by_id = AsyncMock(side_effect=lambda sid: _make_scan_run(sid))

    current_scores = [
        _make_ticker_score("AAPL", 85.0, scan_run_id=2),
    ]

    async def mock_scores(scan_id: int) -> list[TickerScore]:
        if scan_id == 2:
            return current_scores
        return []

    mock_repo.get_scores_for_scan = AsyncMock(side_effect=mock_scores)

    response = await client.get("/api/scan/2/diff?base_id=1")
    assert response.status_code == 200
    data = response.json()
    assert "AAPL" in data["added"]
    assert len(data["removed"]) == 0


async def test_diff_identical_scans(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Identical scans produce zero-change movers."""
    mock_repo.get_scan_by_id = AsyncMock(side_effect=lambda sid: _make_scan_run(sid))

    same_scores = [
        _make_ticker_score("AAPL", 80.0),
        _make_ticker_score("MSFT", 75.0),
    ]
    mock_repo.get_scores_for_scan = AsyncMock(return_value=same_scores)

    response = await client.get("/api/scan/2/diff?base_id=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data["added"]) == 0
    assert len(data["removed"]) == 0
    for mover in data["movers"]:
        assert mover["score_change"] == pytest.approx(0.0)


async def test_diff_movers_sorted_by_abs_change(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Movers are sorted by absolute score change descending."""
    mock_repo.get_scan_by_id = AsyncMock(side_effect=lambda sid: _make_scan_run(sid))

    current = [
        _make_ticker_score("AAPL", 85.0, scan_run_id=2),
        _make_ticker_score("MSFT", 60.0, scan_run_id=2),
        _make_ticker_score("GOOGL", 77.0, scan_run_id=2),
    ]
    base = [
        _make_ticker_score("AAPL", 80.0, scan_run_id=1),
        _make_ticker_score("MSFT", 80.0, scan_run_id=1),
        _make_ticker_score("GOOGL", 75.0, scan_run_id=1),
    ]

    async def mock_scores(scan_id: int) -> list[TickerScore]:
        if scan_id == 2:
            return current
        return base

    mock_repo.get_scores_for_scan = AsyncMock(side_effect=mock_scores)

    response = await client.get("/api/scan/2/diff?base_id=1")
    data = response.json()
    movers = data["movers"]
    assert movers[0]["ticker"] == "MSFT"
    assert movers[1]["ticker"] == "AAPL"
    assert movers[2]["ticker"] == "GOOGL"


async def test_diff_missing_base_id_param(client: AsyncClient) -> None:
    """Missing base_id query parameter returns 422."""
    response = await client.get("/api/scan/1/diff")
    assert response.status_code == 422


async def test_diff_direction_change_tracked(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Direction changes are captured in the delta."""
    mock_repo.get_scan_by_id = AsyncMock(side_effect=lambda sid: _make_scan_run(sid))

    current = [
        _make_ticker_score("TSLA", 70.0, SignalDirection.BEARISH, scan_run_id=2),
    ]
    base = [
        _make_ticker_score("TSLA", 65.0, SignalDirection.BULLISH, scan_run_id=1),
    ]

    async def mock_scores(scan_id: int) -> list[TickerScore]:
        if scan_id == 2:
            return current
        return base

    mock_repo.get_scores_for_scan = AsyncMock(side_effect=mock_scores)

    response = await client.get("/api/scan/2/diff?base_id=1")
    data = response.json()
    tsla = data["movers"][0]
    assert tsla["current_direction"] == "bearish"
    assert tsla["previous_direction"] == "bullish"


async def test_diff_both_empty_scans(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Both scans with no scores produce empty diff."""
    mock_repo.get_scan_by_id = AsyncMock(side_effect=lambda sid: _make_scan_run(sid))
    mock_repo.get_scores_for_scan = AsyncMock(return_value=[])

    response = await client.get("/api/scan/2/diff?base_id=1")
    assert response.status_code == 200
    data = response.json()
    assert data["added"] == []
    assert data["removed"] == []
    assert data["movers"] == []


async def test_diff_only_removed_tickers(client: AsyncClient, mock_repo: MagicMock) -> None:
    """Current scan empty, base has tickers — all appear in removed."""
    mock_repo.get_scan_by_id = AsyncMock(side_effect=lambda sid: _make_scan_run(sid))

    base = [
        _make_ticker_score("AAPL", 80.0, scan_run_id=1),
        _make_ticker_score("MSFT", 75.0, scan_run_id=1),
    ]

    async def mock_scores(scan_id: int) -> list[TickerScore]:
        if scan_id == 2:
            return []
        return base

    mock_repo.get_scores_for_scan = AsyncMock(side_effect=mock_scores)

    response = await client.get("/api/scan/2/diff?base_id=1")
    data = response.json()
    assert sorted(data["removed"]) == ["AAPL", "MSFT"]
    assert data["added"] == []
    assert data["movers"] == []
