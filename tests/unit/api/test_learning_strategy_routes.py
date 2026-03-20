"""Tests for strategy mining and playbook API endpoints."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from options_arena.api.app import create_app
from options_arena.api.deps import get_operation_lock, get_repo
from options_arena.models import (
    ConditionOperator,
    RuleStatus,
    StrategyCondition,
    StrategyRule,
)

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)


def _make_rule(
    rule_id: str = "rule_test",
    status: RuleStatus = RuleStatus.CANDIDATE,
) -> StrategyRule:
    return StrategyRule(
        rule_id=rule_id,
        pattern="Tech | IV mid_high | DTE medium | bullish -> 70% win rate",
        conditions=[
            StrategyCondition(
                field="sector",
                operator=ConditionOperator.EQ,
                value="Information Technology",
            ),
        ],
        win_rate=0.70,
        avg_return=0.12,
        sample_size=40,
        status=status,
        created_at=_NOW,
    )


@pytest.fixture
def mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.get_strategy_rules = AsyncMock(return_value=[])
    repo.update_rule_status = AsyncMock(return_value=True)
    repo.get_weight_history = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_lock() -> asyncio.Lock:
    return asyncio.Lock()


@pytest.fixture
def app(mock_repo: MagicMock, mock_lock: asyncio.Lock) -> object:
    application = create_app()
    application.dependency_overrides[get_repo] = lambda: mock_repo
    application.dependency_overrides[get_operation_lock] = lambda: mock_lock
    return application


@pytest.fixture
async def client(app: object) -> AsyncClient:  # type: ignore[misc]
    async with AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://testserver",
    ) as ac:
        yield ac  # type: ignore[misc]


class TestMineEndpoint:
    @pytest.mark.asyncio
    async def test_mine_returns_rules(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """Verify POST /api/learning/mine returns generated rules."""
        # run_strategy_mining is called internally; just verify the route works
        response = await client.post("/api/learning/mine")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_mine_requires_lock(
        self,
        client: AsyncClient,
        mock_lock: asyncio.Lock,
    ) -> None:
        """Verify 409 when operation lock is held."""
        await mock_lock.acquire()
        try:
            response = await client.post("/api/learning/mine")
            assert response.status_code == 409
        finally:
            mock_lock.release()


class TestPlaybookEndpoint:
    @pytest.mark.asyncio
    async def test_get_all_rules(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """Verify GET /api/learning/playbook returns all rules."""
        mock_repo.get_strategy_rules = AsyncMock(
            return_value=[_make_rule("r1"), _make_rule("r2")]
        )
        response = await client.get("/api/learning/playbook")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_filter_by_status(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """Verify status query parameter filters rules."""
        mock_repo.get_strategy_rules = AsyncMock(
            return_value=[_make_rule("r1", RuleStatus.APPROVED)]
        )
        response = await client.get("/api/learning/playbook?status=approved")
        assert response.status_code == 200
        mock_repo.get_strategy_rules.assert_called_once_with(status=RuleStatus.APPROVED)

    @pytest.mark.asyncio
    async def test_update_rule_status(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """Verify PUT updates status and returns success."""
        response = await client.put("/api/learning/playbook/rule_1?status=approved")
        assert response.status_code == 200
        assert response.json() == {"updated": True}
        mock_repo.update_rule_status.assert_called_once_with("rule_1", RuleStatus.APPROVED)

    @pytest.mark.asyncio
    async def test_update_nonexistent_rule(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
    ) -> None:
        """Verify 404 for unknown rule_id."""
        mock_repo.update_rule_status = AsyncMock(return_value=False)
        response = await client.put("/api/learning/playbook/nonexistent?status=approved")
        assert response.status_code == 404
