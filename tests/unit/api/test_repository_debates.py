"""Tests for Repository.get_recent_debates."""

from __future__ import annotations

import pytest

from options_arena.data import Database, Repository


@pytest.fixture()
async def repo() -> Repository:
    """Create an in-memory database with migrations and return a Repository."""
    db = Database(":memory:")
    await db.connect()
    yield Repository(db)  # type: ignore[misc]
    await db.close()


async def test_get_recent_debates_empty(repo: Repository) -> None:
    """get_recent_debates returns empty list on fresh DB."""
    debates = await repo.get_recent_debates()
    assert debates == []


async def test_get_recent_debates_returns_data(repo: Repository) -> None:
    """get_recent_debates returns debate rows ordered newest first."""
    # Save two debates
    id1 = await repo.save_debate(
        scan_run_id=None,
        ticker="AAPL",
        bull_json='{"test": 1}',
        bear_json='{"test": 2}',
        risk_json=None,
        verdict_json=None,
        total_tokens=100,
        model_name="test-model",
        duration_ms=1000,
        is_fallback=False,
    )
    id2 = await repo.save_debate(
        scan_run_id=None,
        ticker="MSFT",
        bull_json='{"test": 3}',
        bear_json='{"test": 4}',
        risk_json=None,
        verdict_json=None,
        total_tokens=200,
        model_name="test-model",
        duration_ms=2000,
        is_fallback=True,
    )
    debates = await repo.get_recent_debates(limit=10)
    assert len(debates) == 2
    # Newest first
    assert debates[0].ticker == "MSFT"
    assert debates[1].ticker == "AAPL"
    assert debates[0].id == id2
    assert debates[1].id == id1


async def test_get_recent_debates_respects_limit(repo: Repository) -> None:
    """get_recent_debates respects the limit parameter."""
    for i in range(5):
        await repo.save_debate(
            scan_run_id=None,
            ticker=f"TK{i}",
            bull_json=None,
            bear_json=None,
            risk_json=None,
            verdict_json=None,
            total_tokens=0,
            model_name="test",
            duration_ms=0,
            is_fallback=False,
        )
    debates = await repo.get_recent_debates(limit=3)
    assert len(debates) == 3
