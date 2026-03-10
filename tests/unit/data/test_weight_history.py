"""Tests for Repository.get_weight_history().

Covers:
  - Empty database returns empty list
  - Single snapshot retrieval
  - Multiple snapshots ordered by created_at DESC
  - Limit parameter respected
  - Snapshot contains all agents from that timestamp
  - window_days value preserved from DB
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from options_arena.data.database import Database
from options_arena.data.repository import Repository
from options_arena.models import AgentWeightsComparison

pytestmark = pytest.mark.db

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> Database:
    """Fresh in-memory database with all migrations applied."""
    database = Database(":memory:")
    await database.connect()
    yield database  # type: ignore[misc]
    await database.close()


@pytest_asyncio.fixture
async def repo(db: Database) -> Repository:
    """Repository wrapping the in-memory database."""
    return Repository(db)


def _make_weights(
    agents: list[str] | None = None,
) -> list[AgentWeightsComparison]:
    """Create a list of AgentWeightsComparison for the given agent names."""
    if agents is None:
        agents = ["trend", "volatility", "risk"]
    return [
        AgentWeightsComparison(
            agent_name=name,
            manual_weight=0.17,
            auto_weight=0.20 + i * 0.01,
            brier_score=0.15 + i * 0.05 if name != "risk" else None,
            sample_size=50 - i * 10,
        )
        for i, name in enumerate(agents)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetWeightHistory:
    """Tests for Repository.get_weight_history()."""

    async def test_empty_db_returns_empty(self, repo: Repository) -> None:
        """Verify empty list when no auto-tune weights exist."""
        result = await repo.get_weight_history()
        assert result == []

    async def test_single_snapshot(self, repo: Repository) -> None:
        """Verify a single saved weight set is retrieved as one snapshot."""
        weights = _make_weights()
        await repo.save_auto_tune_weights(weights, window_days=90)

        snapshots = await repo.get_weight_history()
        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap.window_days == 90
        assert len(snap.weights) == 3
        assert snap.computed_at.tzinfo is not None

    async def test_multiple_snapshots_ordered_desc(self, repo: Repository) -> None:
        """Verify multiple snapshots are returned newest-first."""
        weights_1 = _make_weights(["trend", "volatility"])
        await repo.save_auto_tune_weights(weights_1, window_days=30)

        # Small delay to ensure different created_at timestamps
        await asyncio.sleep(0.05)

        weights_2 = _make_weights(["trend", "volatility", "flow"])
        await repo.save_auto_tune_weights(weights_2, window_days=60)

        snapshots = await repo.get_weight_history()
        assert len(snapshots) == 2
        # Newest first
        assert snapshots[0].computed_at > snapshots[1].computed_at
        # Second set has 3 agents, first has 2
        assert len(snapshots[0].weights) == 3
        assert len(snapshots[1].weights) == 2

    async def test_limit_respected(self, repo: Repository) -> None:
        """Verify limit parameter caps the number of returned snapshots."""
        for i in range(5):
            weights = _make_weights(["trend"])
            await repo.save_auto_tune_weights(weights, window_days=30 + i * 10)
            await asyncio.sleep(0.02)

        snapshots = await repo.get_weight_history(limit=3)
        assert len(snapshots) == 3

        # They should still be newest-first
        for j in range(len(snapshots) - 1):
            assert snapshots[j].computed_at >= snapshots[j + 1].computed_at

    async def test_snapshot_contains_all_agents(self, repo: Repository) -> None:
        """Verify all agents from a single save appear in the snapshot."""
        agent_names = ["trend", "volatility", "flow", "fundamental", "contrarian"]
        weights = _make_weights(agent_names)
        await repo.save_auto_tune_weights(weights, window_days=90)

        snapshots = await repo.get_weight_history()
        assert len(snapshots) == 1
        snap = snapshots[0]
        assert len(snap.weights) == 5
        retrieved_names = sorted(w.agent_name for w in snap.weights)
        assert retrieved_names == sorted(agent_names)

    async def test_window_days_preserved(self, repo: Repository) -> None:
        """Verify window_days from DB row is preserved in snapshot."""
        weights = _make_weights(["trend"])
        await repo.save_auto_tune_weights(weights, window_days=120)

        snapshots = await repo.get_weight_history()
        assert len(snapshots) == 1
        assert snapshots[0].window_days == 120
