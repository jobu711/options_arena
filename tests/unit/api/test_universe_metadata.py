"""Tests for metadata index API endpoints (#274).

Tests:
- GET /api/universe/metadata/stats — coverage statistics
- POST /api/universe/index — background bulk indexing with operation lock
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from options_arena.models.metadata import MetadataCoverage


class TestMetadataStatsEndpoint:
    """Tests for GET /api/universe/metadata/stats."""

    async def test_returns_coverage_stats(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify GET /api/universe/metadata/stats returns MetadataStats."""
        mock_repo.get_metadata_coverage = AsyncMock(
            return_value=MetadataCoverage(
                total=100,
                with_sector=80,
                with_industry_group=60,
                coverage=0.8,
            )
        )
        response = await client.get("/api/universe/metadata/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 100
        assert data["with_sector"] == 80
        assert data["with_industry_group"] == 60
        assert data["coverage"] == pytest.approx(0.8)

    async def test_empty_database(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify returns zeros when no metadata exists."""
        mock_repo.get_metadata_coverage = AsyncMock(
            return_value=MetadataCoverage(
                total=0,
                with_sector=0,
                with_industry_group=0,
                coverage=0.0,
            )
        )
        response = await client.get("/api/universe/metadata/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["with_sector"] == 0
        assert data["with_industry_group"] == 0
        assert data["coverage"] == pytest.approx(0.0)

    async def test_coverage_calculation(self, client: AsyncClient, mock_repo: MagicMock) -> None:
        """Verify coverage = with_sector / total."""
        mock_repo.get_metadata_coverage = AsyncMock(
            return_value=MetadataCoverage(
                total=200,
                with_sector=50,
                with_industry_group=30,
                coverage=0.25,
            )
        )
        response = await client.get("/api/universe/metadata/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["coverage"] == pytest.approx(0.25)


class TestIndexEndpoint:
    """Tests for POST /api/universe/index."""

    async def test_returns_202_accepted(
        self, client: AsyncClient, mock_repo: MagicMock, mock_universe: MagicMock
    ) -> None:
        """Verify POST /api/universe/index returns 202."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["AAPL"])
        mock_repo.get_stale_tickers = AsyncMock(return_value=[])
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])
        response = await client.post("/api/universe/index")
        assert response.status_code == 202
        data = response.json()
        assert "index_task_id" in data
        assert data["index_task_id"] >= 1
        # Allow background task to complete
        await asyncio.sleep(0.1)

    async def test_returns_409_when_locked(self, client: AsyncClient, test_app: object) -> None:
        """Verify returns 409 when operation lock is held."""
        from options_arena.api.deps import get_operation_lock  # noqa: PLC0415

        # Create a pre-locked lock
        locked_lock = asyncio.Lock()
        await locked_lock.acquire()
        test_app.dependency_overrides[get_operation_lock] = lambda: locked_lock  # type: ignore[union-attr]

        response = await client.post("/api/universe/index")
        assert response.status_code == 409
        assert "Another operation is in progress" in response.json()["detail"]

        # Clean up — release the lock
        locked_lock.release()

    async def test_accepts_force_param(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
        mock_universe: MagicMock,
    ) -> None:
        """Verify force=true param triggers full indexing."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["AAPL", "MSFT"])
        # With force=true, stale_tickers and get_all_ticker_metadata should NOT be called
        mock_repo.get_stale_tickers = AsyncMock(return_value=[])
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])
        mock_repo.upsert_ticker_metadata = AsyncMock()

        response = await client.post("/api/universe/index?force=true")
        assert response.status_code == 202
        # Allow background task to run
        await asyncio.sleep(0.1)
        # With force=true, get_stale_tickers should NOT be called
        mock_repo.get_stale_tickers.assert_not_called()

    async def test_accepts_max_age_param(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
        mock_universe: MagicMock,
    ) -> None:
        """Verify max_age param is passed to stale ticker query."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["AAPL"])
        mock_repo.get_stale_tickers = AsyncMock(return_value=[])
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])

        response = await client.post("/api/universe/index?max_age=7")
        assert response.status_code == 202
        # Allow background task to run
        await asyncio.sleep(0.1)
        mock_repo.get_stale_tickers.assert_called_once_with(max_age_days=7)

    async def test_lock_released_on_completion(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
        mock_universe: MagicMock,
    ) -> None:
        """Verify operation lock is released after indexing completes."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=[])
        mock_repo.get_stale_tickers = AsyncMock(return_value=[])
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])

        response = await client.post("/api/universe/index")
        assert response.status_code == 202

        # Allow background task to complete
        await asyncio.sleep(0.1)

        # Second request should also succeed (lock was released)
        response2 = await client.post("/api/universe/index")
        assert response2.status_code == 202
        await asyncio.sleep(0.1)

    async def test_lock_released_on_error(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
        mock_universe: MagicMock,
    ) -> None:
        """Verify operation lock is released even if indexing fails."""
        mock_universe.fetch_optionable_tickers = AsyncMock(side_effect=RuntimeError("CBOE down"))

        response = await client.post("/api/universe/index")
        assert response.status_code == 202

        # Allow background task to fail
        await asyncio.sleep(0.1)

        # Lock should be released — second request should succeed
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=[])
        mock_repo.get_stale_tickers = AsyncMock(return_value=[])
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])

        response2 = await client.post("/api/universe/index")
        assert response2.status_code == 202
        await asyncio.sleep(0.1)

    @patch("options_arena.api.routes.universe.map_yfinance_to_metadata")
    async def test_per_ticker_errors_isolated(
        self,
        mock_map: MagicMock,
        client: AsyncClient,
        mock_repo: MagicMock,
        mock_universe: MagicMock,
        mock_market_data: MagicMock,
    ) -> None:
        """Verify per-ticker errors don't crash the entire indexing task."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["AAPL", "BADTK", "MSFT"])
        mock_repo.get_stale_tickers = AsyncMock(return_value=[])
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])
        mock_repo.upsert_ticker_metadata = AsyncMock()

        # fetch_ticker_info fails for BADTK but succeeds for others
        async def _fetch_ticker_info(ticker: str) -> MagicMock:
            if ticker == "BADTK":
                raise RuntimeError("Ticker not found")
            return MagicMock()

        mock_market_data.fetch_ticker_info = AsyncMock(side_effect=_fetch_ticker_info)
        mock_map.return_value = MagicMock()

        response = await client.post("/api/universe/index?force=true")
        assert response.status_code == 202

        # Allow background task to complete
        await asyncio.sleep(0.2)

        # upsert should be called for AAPL and MSFT (2 out of 3)
        assert mock_repo.upsert_ticker_metadata.call_count == 2

    async def test_counter_increments(
        self,
        client: AsyncClient,
        mock_repo: MagicMock,
        mock_universe: MagicMock,
    ) -> None:
        """Verify task IDs increment on subsequent requests."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=[])
        mock_repo.get_stale_tickers = AsyncMock(return_value=[])
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])

        response1 = await client.post("/api/universe/index")
        assert response1.status_code == 202
        id1 = response1.json()["index_task_id"]
        await asyncio.sleep(0.1)

        response2 = await client.post("/api/universe/index")
        assert response2.status_code == 202
        id2 = response2.json()["index_task_id"]
        await asyncio.sleep(0.1)

        assert id2 > id1
