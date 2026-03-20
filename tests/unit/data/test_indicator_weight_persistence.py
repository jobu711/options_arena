"""Tests for indicator weight persistence — migration 035 + repository methods.

Covers: save_indicator_weights roundtrip, weight_type filtering, backward
compatibility, accuracy_at_time persistence, empty weights noop.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from options_arena.data import Database, Repository
from options_arena.models import AgentWeightsComparison, WeightType


@pytest_asyncio.fixture
async def repo() -> Repository:  # type: ignore[misc]
    """Fresh in-memory DB with all migrations applied."""
    db = Database(":memory:")
    await db.connect()
    yield Repository(db)  # type: ignore[misc]
    await db.close()


@pytest.mark.asyncio
@pytest.mark.db
class TestIndicatorWeightPersistence:
    """Tests for indicator weight save/retrieve with weight_type discrimination."""

    async def test_save_indicator_weights_roundtrip(self, repo: Repository) -> None:
        """Save indicator weights and retrieve via get_weight_history."""
        weights = {"rsi": 0.08, "adx": 0.06, "bb_width": 0.05}
        static = {"rsi": 0.065, "adx": 0.065, "bb_width": 0.05}
        await repo.save_indicator_weights(
            weights, static, window_days=90, accuracy=0.72
        )

        history = await repo.get_weight_history(
            limit=10, weight_type=WeightType.INDICATOR
        )
        assert len(history) == 1
        snap = history[0]
        assert snap.weight_type == WeightType.INDICATOR
        assert snap.accuracy_at_time == pytest.approx(0.72)
        assert len(snap.weights) == 3

    async def test_weight_type_filter_vote_only(self, repo: Repository) -> None:
        """get_weight_history(weight_type=VOTE) excludes indicator rows."""
        # Save vote weights
        vote_weights = [
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=0.25,
                auto_weight=0.28,
                brier_score=0.15,
                sample_size=50,
            ),
        ]
        await repo.save_auto_tune_weights(vote_weights, window_days=90)

        # Save indicator weights
        await repo.save_indicator_weights(
            {"rsi": 0.08}, {"rsi": 0.065}, window_days=90
        )

        # Filter for vote only
        vote_history = await repo.get_weight_history(
            limit=10, weight_type=WeightType.VOTE
        )
        for snap in vote_history:
            assert snap.weight_type == WeightType.VOTE

    async def test_weight_type_filter_indicator_only(self, repo: Repository) -> None:
        """get_weight_history(weight_type=INDICATOR) excludes vote rows."""
        await repo.save_auto_tune_weights(
            [
                AgentWeightsComparison(
                    agent_name="trend",
                    manual_weight=0.25,
                    auto_weight=0.28,
                    brier_score=0.15,
                    sample_size=50,
                ),
            ],
            window_days=90,
        )
        await repo.save_indicator_weights(
            {"rsi": 0.08}, {"rsi": 0.065}, window_days=90
        )

        indicator_history = await repo.get_weight_history(
            limit=10, weight_type=WeightType.INDICATOR
        )
        assert len(indicator_history) == 1
        assert indicator_history[0].weight_type == WeightType.INDICATOR

    async def test_weight_type_filter_none_returns_all(self, repo: Repository) -> None:
        """get_weight_history(weight_type=None) returns both types."""
        await repo.save_auto_tune_weights(
            [
                AgentWeightsComparison(
                    agent_name="trend",
                    manual_weight=0.25,
                    auto_weight=0.28,
                    brier_score=0.15,
                    sample_size=50,
                ),
            ],
            window_days=90,
        )
        await repo.save_indicator_weights(
            {"rsi": 0.08}, {"rsi": 0.065}, window_days=90
        )

        all_history = await repo.get_weight_history(limit=10, weight_type=None)
        assert len(all_history) == 2  # One vote snapshot + one indicator snapshot

    async def test_accuracy_at_time_persisted(self, repo: Repository) -> None:
        """accuracy_at_time field survives roundtrip."""
        await repo.save_indicator_weights(
            {"rsi": 0.08}, {"rsi": 0.065}, window_days=60, accuracy=0.85
        )

        history = await repo.get_weight_history(
            limit=10, weight_type=WeightType.INDICATOR
        )
        assert history[0].accuracy_at_time == pytest.approx(0.85)

    async def test_accuracy_at_time_none_for_votes(self, repo: Repository) -> None:
        """Vote weights have accuracy_at_time=None."""
        await repo.save_auto_tune_weights(
            [
                AgentWeightsComparison(
                    agent_name="trend",
                    manual_weight=0.25,
                    auto_weight=0.28,
                    brier_score=0.15,
                    sample_size=50,
                ),
            ],
            window_days=90,
        )

        history = await repo.get_weight_history(
            limit=10, weight_type=WeightType.VOTE
        )
        assert len(history) == 1
        assert history[0].accuracy_at_time is None

    async def test_save_empty_indicator_weights_noop(self, repo: Repository) -> None:
        """Empty dict does not insert any rows."""
        await repo.save_indicator_weights({}, {}, window_days=90)

        history = await repo.get_weight_history(
            limit=10, weight_type=WeightType.INDICATOR
        )
        assert history == []
