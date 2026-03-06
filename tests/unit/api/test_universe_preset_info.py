"""Tests for GET /api/universe/preset-info endpoint (#286).

Tests:
- Returns all 6 presets
- Counts match service output
- Handles service failures gracefully
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from options_arena.services.universe import SP500Constituent


class TestPresetInfoEndpoint:
    """Tests for GET /api/universe/preset-info."""

    @pytest.mark.asyncio
    async def test_returns_all_six_presets(
        self, client: AsyncClient, mock_universe: MagicMock
    ) -> None:
        """Verify 6 PresetInfo items returned."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["AAPL", "MSFT", "GOOG"])
        mock_universe.fetch_sp500_constituents = AsyncMock(
            return_value=[
                SP500Constituent(ticker="AAPL", sector="Information Technology"),
                SP500Constituent(ticker="MSFT", sector="Information Technology"),
            ]
        )
        mock_universe.fetch_etf_tickers = AsyncMock(return_value=["SPY", "QQQ"])
        mock_universe.fetch_nasdaq100_constituents = AsyncMock(
            return_value=["AAPL", "MSFT", "NVDA"]
        )
        mock_universe.fetch_russell2000_tickers = AsyncMock(return_value=["SMLL", "MICR"])
        mock_universe.fetch_most_active = AsyncMock(return_value=["AAPL", "SPY", "QQQ", "TSLA"])

        response = await client.get("/api/universe/preset-info")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 6

        # Verify all preset keys are present
        preset_names = [item["preset"] for item in data]
        assert "full" in preset_names
        assert "sp500" in preset_names
        assert "etfs" in preset_names
        assert "nasdaq100" in preset_names
        assert "russell2000" in preset_names
        assert "most_active" in preset_names

    @pytest.mark.asyncio
    async def test_counts_match_service_output(
        self, client: AsyncClient, mock_universe: MagicMock
    ) -> None:
        """Verify estimated_count matches service method length."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["A", "B", "C", "D", "E"])
        mock_universe.fetch_sp500_constituents = AsyncMock(
            return_value=[
                SP500Constituent(ticker="A", sector="Energy"),
                SP500Constituent(ticker="B", sector="Energy"),
                SP500Constituent(ticker="C", sector="Financials"),
            ]
        )
        mock_universe.fetch_etf_tickers = AsyncMock(return_value=["SPY"])
        mock_universe.fetch_nasdaq100_constituents = AsyncMock(return_value=["A", "B"])
        mock_universe.fetch_russell2000_tickers = AsyncMock(return_value=[])
        mock_universe.fetch_most_active = AsyncMock(return_value=["A", "B", "C"])

        response = await client.get("/api/universe/preset-info")

        assert response.status_code == 200
        data = response.json()
        by_preset = {item["preset"]: item for item in data}

        assert by_preset["full"]["estimated_count"] == 5
        assert by_preset["sp500"]["estimated_count"] == 3
        assert by_preset["etfs"]["estimated_count"] == 1
        assert by_preset["nasdaq100"]["estimated_count"] == 2
        assert by_preset["russell2000"]["estimated_count"] == 0
        assert by_preset["most_active"]["estimated_count"] == 3

    @pytest.mark.asyncio
    async def test_labels_and_descriptions_present(
        self, client: AsyncClient, mock_universe: MagicMock
    ) -> None:
        """Verify each preset has a non-empty label and description."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=[])
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])
        mock_universe.fetch_etf_tickers = AsyncMock(return_value=[])
        mock_universe.fetch_nasdaq100_constituents = AsyncMock(return_value=[])
        mock_universe.fetch_russell2000_tickers = AsyncMock(return_value=[])
        mock_universe.fetch_most_active = AsyncMock(return_value=[])

        response = await client.get("/api/universe/preset-info")

        assert response.status_code == 200
        data = response.json()

        for item in data:
            assert isinstance(item["label"], str)
            assert len(item["label"]) > 0
            assert isinstance(item["description"], str)
            assert len(item["description"]) > 0

    @pytest.mark.asyncio
    async def test_handles_service_exception_gracefully(
        self, client: AsyncClient, mock_universe: MagicMock
    ) -> None:
        """Verify failing fetches return 0 count instead of crashing."""
        # Some methods succeed, some fail
        mock_universe.fetch_optionable_tickers = AsyncMock(side_effect=Exception("CBOE down"))
        mock_universe.fetch_sp500_constituents = AsyncMock(
            return_value=[SP500Constituent(ticker="AAPL", sector="Tech")]
        )
        mock_universe.fetch_etf_tickers = AsyncMock(side_effect=Exception("ETF check failed"))
        mock_universe.fetch_nasdaq100_constituents = AsyncMock(return_value=["NVDA"])
        mock_universe.fetch_russell2000_tickers = AsyncMock(return_value=[])
        mock_universe.fetch_most_active = AsyncMock(return_value=["SPY"])

        response = await client.get("/api/universe/preset-info")

        assert response.status_code == 200
        data = response.json()
        by_preset = {item["preset"]: item for item in data}

        # Failed presets should have count 0
        assert by_preset["full"]["estimated_count"] == 0
        assert by_preset["etfs"]["estimated_count"] == 0
        # Successful presets should have correct counts
        assert by_preset["sp500"]["estimated_count"] == 1
        assert by_preset["nasdaq100"]["estimated_count"] == 1
        assert by_preset["most_active"]["estimated_count"] == 1

    @pytest.mark.asyncio
    async def test_preset_order_is_consistent(
        self, client: AsyncClient, mock_universe: MagicMock
    ) -> None:
        """Verify presets are returned in a stable order."""
        mock_universe.fetch_optionable_tickers = AsyncMock(return_value=[])
        mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])
        mock_universe.fetch_etf_tickers = AsyncMock(return_value=[])
        mock_universe.fetch_nasdaq100_constituents = AsyncMock(return_value=[])
        mock_universe.fetch_russell2000_tickers = AsyncMock(return_value=[])
        mock_universe.fetch_most_active = AsyncMock(return_value=[])

        response = await client.get("/api/universe/preset-info")

        assert response.status_code == 200
        data = response.json()
        preset_order = [item["preset"] for item in data]
        assert preset_order == [
            "full",
            "sp500",
            "etfs",
            "nasdaq100",
            "russell2000",
            "most_active",
        ]
