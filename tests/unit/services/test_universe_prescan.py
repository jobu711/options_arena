"""Tests for pre-scan universe fetch methods (#286).

Tests:
- fetch_nasdaq100_constituents — CSV parse, cache hit, fallback, CBOE cross-ref
- fetch_russell2000_tickers — metadata index query, empty metadata, CBOE cross-ref
- fetch_most_active — curated list, CBOE cross-ref, never-raises
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from options_arena.models.config import ServiceConfig
from options_arena.models.enums import MarketCapTier
from options_arena.models.metadata import TickerMetadata
from options_arena.services.cache import TTL_REFERENCE, ServiceCache
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import (
    _CACHE_KEY_MOST_ACTIVE,
    _CACHE_KEY_NASDAQ100,
    _CACHE_KEY_RUSSELL2000,
    _MOST_ACTIVE_SEED,
    _NASDAQ100_FALLBACK,
    UniverseService,
)


@pytest.fixture()
def config() -> ServiceConfig:
    """Default ServiceConfig for universe tests."""
    return ServiceConfig()


@pytest.fixture()
def cache(config: ServiceConfig) -> ServiceCache:
    """In-memory-only cache for fast unit tests."""
    return ServiceCache(config, db_path=None)


@pytest.fixture()
def limiter() -> RateLimiter:
    """Rate limiter for universe tests."""
    return RateLimiter(rate=100.0, max_concurrent=10)


@pytest.fixture()
def service(config: ServiceConfig, cache: ServiceCache, limiter: RateLimiter) -> UniverseService:
    """UniverseService instance with mocked dependencies."""
    return UniverseService(config=config, cache=cache, limiter=limiter)


def _make_metadata(ticker: str, tier: MarketCapTier) -> TickerMetadata:
    """Helper to create a TickerMetadata instance."""
    return TickerMetadata(
        ticker=ticker,
        market_cap_tier=tier,
        company_name=f"{ticker} Inc.",
        last_updated=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# NASDAQ-100 — CSV happy path
# ---------------------------------------------------------------------------


class TestFetchNasdaq100:
    """Tests for fetch_nasdaq100_constituents."""

    @pytest.mark.asyncio
    async def test_returns_tickers_from_csv(self, service: UniverseService) -> None:
        """Verify CSV parsing returns expected tickers after CBOE cross-ref."""
        csv_text = "Symbol\nAAPL\nMSFT\nNVDA\nGOOG\n"
        mock_response = MagicMock()
        mock_response.text = csv_text
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        # Mock CBOE optionable to include all 4 tickers
        with (
            patch.object(
                service._client,
                "get",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
            patch(
                "options_arena.services.universe.pd.read_csv",
            ) as mock_read_csv,
            patch.object(
                service,
                "fetch_optionable_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL", "GOOG", "MSFT", "NVDA"],
            ),
        ):
            import pandas as pd  # noqa: PLC0415

            mock_read_csv.return_value = pd.DataFrame({"Symbol": ["AAPL", "MSFT", "NVDA", "GOOG"]})
            result = await service.fetch_nasdaq100_constituents()

        assert "AAPL" in result
        assert "MSFT" in result
        assert "NVDA" in result
        assert "GOOG" in result
        assert result == sorted(result)

    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetch(
        self, service: UniverseService, cache: ServiceCache
    ) -> None:
        """Verify cached data returned without HTTP call."""
        cached_tickers = ["AAPL", "MSFT", "NVDA"]
        await cache.set(
            _CACHE_KEY_NASDAQ100,
            json.dumps(cached_tickers).encode(),
            ttl=TTL_REFERENCE,
        )

        with patch.object(service._client, "get", new_callable=AsyncMock) as mock_get:
            result = await service.fetch_nasdaq100_constituents()

        mock_get.assert_not_called()
        assert result == cached_tickers

    @pytest.mark.asyncio
    async def test_fallback_on_http_error(self, service: UniverseService) -> None:
        """Verify curated fallback returned on fetch failure."""
        with (
            patch.object(
                service._client,
                "get",
                new_callable=AsyncMock,
                side_effect=Exception("Network error"),
            ),
            patch.object(
                service,
                "fetch_optionable_tickers",
                new_callable=AsyncMock,
                return_value=sorted(_NASDAQ100_FALLBACK),
            ),
        ):
            result = await service.fetch_nasdaq100_constituents()

        # Should use curated fallback, cross-referenced with CBOE
        assert len(result) > 0
        # All returned tickers should be from the curated list
        for ticker in result:
            assert ticker in _NASDAQ100_FALLBACK

    @pytest.mark.asyncio
    async def test_cboe_cross_ref_filters(self, service: UniverseService) -> None:
        """Verify non-optionable tickers removed via CBOE cross-ref."""
        csv_text = "Symbol\nAAPL\nMSFT\nFAKE\n"
        mock_response = MagicMock()
        mock_response.text = csv_text
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with (
            patch.object(
                service._client,
                "get",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
            patch(
                "options_arena.services.universe.pd.read_csv",
            ) as mock_read_csv,
            patch.object(
                service,
                "fetch_optionable_tickers",
                new_callable=AsyncMock,
                return_value=["AAPL", "MSFT"],  # FAKE not optionable
            ),
        ):
            import pandas as pd  # noqa: PLC0415

            mock_read_csv.return_value = pd.DataFrame({"Symbol": ["AAPL", "MSFT", "FAKE"]})
            result = await service.fetch_nasdaq100_constituents()

        assert "AAPL" in result
        assert "MSFT" in result
        assert "FAKE" not in result

    @pytest.mark.asyncio
    async def test_never_raises(self, service: UniverseService) -> None:
        """Verify returns empty list on total failure (CBOE cross-ref also fails)."""
        with (
            patch.object(
                service._client,
                "get",
                new_callable=AsyncMock,
                side_effect=Exception("Network error"),
            ),
            patch.object(
                service,
                "fetch_optionable_tickers",
                new_callable=AsyncMock,
                side_effect=Exception("CBOE also down"),
            ),
        ):
            result = await service.fetch_nasdaq100_constituents()

        # Should still return the curated fallback (CBOE cross-ref failed)
        assert isinstance(result, list)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Russell 2000 — metadata index query
# ---------------------------------------------------------------------------


class TestFetchRussell2000:
    """Tests for fetch_russell2000_tickers."""

    @pytest.mark.asyncio
    async def test_returns_small_and_micro_cap(self, service: UniverseService) -> None:
        """Verify both SMALL and MICRO tiers included."""
        mock_repo = MagicMock()
        mock_repo.get_all_ticker_metadata = AsyncMock(
            return_value=[
                _make_metadata("SMLL", MarketCapTier.SMALL),
                _make_metadata("MICR", MarketCapTier.MICRO),
                _make_metadata("MEGA", MarketCapTier.MEGA),
                _make_metadata("LARG", MarketCapTier.LARGE),
            ]
        )

        with patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=["LARG", "MEGA", "MICR", "SMLL"],
        ):
            result = await service.fetch_russell2000_tickers(repo=mock_repo)

        assert "SMLL" in result
        assert "MICR" in result
        assert "MEGA" not in result
        assert "LARG" not in result

    @pytest.mark.asyncio
    async def test_empty_metadata_returns_empty(self, service: UniverseService) -> None:
        """Verify empty metadata index returns empty list."""
        mock_repo = MagicMock()
        mock_repo.get_all_ticker_metadata = AsyncMock(return_value=[])

        result = await service.fetch_russell2000_tickers(repo=mock_repo)

        assert result == []

    @pytest.mark.asyncio
    async def test_no_repo_returns_empty(self, service: UniverseService) -> None:
        """Verify None repo returns empty list."""
        result = await service.fetch_russell2000_tickers(repo=None)
        assert result == []

    @pytest.mark.asyncio
    async def test_cboe_cross_ref(self, service: UniverseService) -> None:
        """Verify cross-reference filtering works."""
        mock_repo = MagicMock()
        mock_repo.get_all_ticker_metadata = AsyncMock(
            return_value=[
                _make_metadata("SMLL", MarketCapTier.SMALL),
                _make_metadata("NOOPT", MarketCapTier.MICRO),
            ]
        )

        with patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=["SMLL"],  # NOOPT not optionable
        ):
            result = await service.fetch_russell2000_tickers(repo=mock_repo)

        assert "SMLL" in result
        assert "NOOPT" not in result

    @pytest.mark.asyncio
    async def test_cache_hit(self, service: UniverseService, cache: ServiceCache) -> None:
        """Verify cached data returned without querying metadata."""
        cached_tickers = ["AAA", "BBB"]
        await cache.set(
            _CACHE_KEY_RUSSELL2000,
            json.dumps(cached_tickers).encode(),
            ttl=TTL_REFERENCE,
        )

        mock_repo = MagicMock()
        result = await service.fetch_russell2000_tickers(repo=mock_repo)

        mock_repo.get_all_ticker_metadata.assert_not_called()
        assert result == cached_tickers

    @pytest.mark.asyncio
    async def test_never_raises_on_repo_error(self, service: UniverseService) -> None:
        """Verify returns empty list when repository call fails."""
        mock_repo = MagicMock()
        mock_repo.get_all_ticker_metadata = AsyncMock(side_effect=Exception("DB error"))

        result = await service.fetch_russell2000_tickers(repo=mock_repo)

        assert result == []


# ---------------------------------------------------------------------------
# Most Active — curated seed list
# ---------------------------------------------------------------------------


class TestFetchMostActive:
    """Tests for fetch_most_active."""

    @pytest.mark.asyncio
    async def test_returns_curated_list(self, service: UniverseService) -> None:
        """Verify curated seed list returned after CBOE cross-ref."""
        with patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=sorted(_MOST_ACTIVE_SEED),
        ):
            result = await service.fetch_most_active()

        assert len(result) > 0
        assert result == sorted(result)
        # All tickers should be from the seed list
        for ticker in result:
            assert ticker in _MOST_ACTIVE_SEED

    @pytest.mark.asyncio
    async def test_cboe_cross_ref(self, service: UniverseService) -> None:
        """Verify non-optionable tickers filtered."""
        # Only AAPL is optionable
        with patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=["AAPL"],
        ):
            result = await service.fetch_most_active()

        assert result == ["AAPL"]

    @pytest.mark.asyncio
    async def test_never_raises(self, service: UniverseService) -> None:
        """Verify returns seed list when CBOE cross-ref fails."""
        with patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            side_effect=Exception("CBOE down"),
        ):
            result = await service.fetch_most_active()

        # Should fall back to full seed list
        assert len(result) > 0
        assert result == sorted(result)

    @pytest.mark.asyncio
    async def test_cache_hit(self, service: UniverseService, cache: ServiceCache) -> None:
        """Verify cached data returned without CBOE call."""
        cached_tickers = ["AAPL", "MSFT", "SPY"]
        await cache.set(
            _CACHE_KEY_MOST_ACTIVE,
            json.dumps(cached_tickers).encode(),
            ttl=TTL_REFERENCE,
        )

        with patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
        ) as mock_fetch:
            result = await service.fetch_most_active()

        mock_fetch.assert_not_called()
        assert result == cached_tickers

    @pytest.mark.asyncio
    async def test_caches_result(self, service: UniverseService, cache: ServiceCache) -> None:
        """Verify result is stored in cache after fetch."""
        with patch.object(
            service,
            "fetch_optionable_tickers",
            new_callable=AsyncMock,
            return_value=["AAPL", "SPY"],
        ):
            await service.fetch_most_active()

        cached = await cache.get(_CACHE_KEY_MOST_ACTIVE)
        assert cached is not None
        assert "AAPL" in json.loads(cached.decode())
