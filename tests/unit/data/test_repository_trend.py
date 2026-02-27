"""Tests for Repository.get_debate_trend_for_ticker()."""

from __future__ import annotations

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import SignalDirection, TradeThesis

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database for each test."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository backed by the in-memory database."""
    return Repository(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_verdict_json(
    ticker: str = "AAPL",
    direction: SignalDirection = SignalDirection.BULLISH,
    confidence: float = 0.72,
    bull_score: float = 7.5,
    bear_score: float = 4.2,
) -> str:
    """Build a valid verdict_json string from a TradeThesis."""
    thesis = TradeThesis(
        ticker=ticker,
        direction=direction,
        confidence=confidence,
        summary="Strong momentum",
        bull_score=bull_score,
        bear_score=bear_score,
        key_factors=["RSI breakout"],
        risk_assessment="Moderate risk",
    )
    return thesis.model_dump_json()


async def _save_debate(
    repo: Repository,
    ticker: str = "AAPL",
    verdict_json: str | None = None,
    is_fallback: bool = False,
) -> int:
    """Helper to save a debate with minimal boilerplate."""
    if verdict_json is None:
        verdict_json = _make_verdict_json(ticker=ticker)
    return await repo.save_debate(
        scan_run_id=None,
        ticker=ticker,
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=verdict_json,
        total_tokens=100,
        model_name="test-model",
        duration_ms=1000,
        is_fallback=is_fallback,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_debate_trend_empty(repo: Repository) -> None:
    """No debates for ticker returns empty list."""
    result = await repo.get_debate_trend_for_ticker("AAPL")
    assert result == []


@pytest.mark.asyncio
async def test_get_debate_trend_single(repo: Repository) -> None:
    """One debate returns list with 1 DebateTrendPoint."""
    await _save_debate(repo, ticker="AAPL")

    result = await repo.get_debate_trend_for_ticker("AAPL")
    assert len(result) == 1
    assert result[0].ticker == "AAPL"


@pytest.mark.asyncio
async def test_get_debate_trend_multiple(repo: Repository) -> None:
    """Three debates return 3 points in chronological order."""
    for _ in range(3):
        await _save_debate(repo, ticker="AAPL")

    result = await repo.get_debate_trend_for_ticker("AAPL")
    assert len(result) == 3
    # Verify chronological order (ASC by created_at)
    for i in range(len(result) - 1):
        assert result[i].created_at <= result[i + 1].created_at


@pytest.mark.asyncio
async def test_get_debate_trend_limit(repo: Repository) -> None:
    """limit=2 with 5 debates returns 2 oldest (ASC order)."""
    for _ in range(5):
        await _save_debate(repo, ticker="AAPL")

    result = await repo.get_debate_trend_for_ticker("AAPL", limit=2)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_debate_trend_wrong_ticker(repo: Repository) -> None:
    """Debates for AAPL, query MSFT returns empty list."""
    await _save_debate(repo, ticker="AAPL")

    result = await repo.get_debate_trend_for_ticker("MSFT")
    assert result == []


@pytest.mark.asyncio
async def test_get_debate_trend_null_verdict(repo: Repository) -> None:
    """Row with verdict_json=None is skipped."""
    # Save a debate with valid verdict
    await _save_debate(repo, ticker="AAPL")
    # Save a debate with NULL verdict_json (using raw save)
    await repo.save_debate(
        scan_run_id=None,
        ticker="AAPL",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json=None,
        total_tokens=0,
        model_name="test",
        duration_ms=100,
        is_fallback=True,
    )

    result = await repo.get_debate_trend_for_ticker("AAPL")
    assert len(result) == 1  # Only the valid one


@pytest.mark.asyncio
async def test_get_debate_trend_invalid_verdict(repo: Repository) -> None:
    """Row with corrupt verdict_json is skipped."""
    # Save a debate with valid verdict
    await _save_debate(repo, ticker="AAPL")
    # Save a debate with invalid JSON string as verdict_json
    await repo.save_debate(
        scan_run_id=None,
        ticker="AAPL",
        bull_json=None,
        bear_json=None,
        risk_json=None,
        verdict_json="{not valid json!!!}",
        total_tokens=0,
        model_name="test",
        duration_ms=100,
        is_fallback=False,
    )

    result = await repo.get_debate_trend_for_ticker("AAPL")
    assert len(result) == 1  # Only the valid one


@pytest.mark.asyncio
async def test_get_debate_trend_extracts_fields(repo: Repository) -> None:
    """Verify direction, confidence, is_fallback, created_at match saved data."""
    verdict_json = _make_verdict_json(
        ticker="AAPL",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        bull_score=3.0,
        bear_score=7.0,
    )
    await _save_debate(
        repo,
        ticker="AAPL",
        verdict_json=verdict_json,
        is_fallback=True,
    )

    result = await repo.get_debate_trend_for_ticker("AAPL")
    assert len(result) == 1
    point = result[0]
    assert point.ticker == "AAPL"
    assert point.direction == SignalDirection.BEARISH
    assert point.confidence == pytest.approx(0.55)
    assert point.is_fallback is True
    assert point.created_at is not None
    assert point.created_at.tzinfo is not None
