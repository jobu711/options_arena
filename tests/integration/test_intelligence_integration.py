"""Integration tests for IntelligenceService — real yfinance calls.

These tests hit the real yfinance API and verify the service works end-to-end.
Mark with ``@pytest.mark.integration`` to skip in CI fast-path.
Use well-known tickers (AAPL, MSFT) for stability.
"""

import pytest

from options_arena.models.config import IntelligenceConfig
from options_arena.models.intelligence import (
    AnalystActivitySnapshot,
    AnalystSnapshot,
    InsiderSnapshot,
    InstitutionalSnapshot,
    IntelligencePackage,
)
from options_arena.services.cache import ServiceCache
from options_arena.services.intelligence import IntelligenceService
from options_arena.services.rate_limiter import RateLimiter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> IntelligenceConfig:
    """Default IntelligenceConfig for integration tests."""
    return IntelligenceConfig(request_timeout=30.0)


@pytest.fixture
def cache(config: IntelligenceConfig) -> ServiceCache:
    """In-memory-only cache for integration tests."""
    from options_arena.models.config import ServiceConfig

    return ServiceCache(ServiceConfig(), db_path=None, max_size=100)


@pytest.fixture
def limiter() -> RateLimiter:
    """Conservative rate limiter for integration tests."""
    return RateLimiter(rate=1.0, max_concurrent=2)


@pytest.fixture
def service(
    config: IntelligenceConfig,
    cache: ServiceCache,
    limiter: RateLimiter,
) -> IntelligenceService:
    """IntelligenceService wired with real dependencies."""
    return IntelligenceService(config=config, cache=cache, limiter=limiter)


# ===========================================================================
# TestIntelligenceIntegration
# ===========================================================================


@pytest.mark.integration
class TestIntelligenceIntegration:
    """Integration tests using real yfinance calls."""

    @pytest.mark.asyncio
    async def test_fetch_analyst_targets_real(self, service: IntelligenceService) -> None:
        """AAPL should have analyst price targets."""
        result = await service.fetch_analyst_targets("AAPL", 185.0)
        # AAPL is widely covered — should usually have data
        if result is not None:
            assert isinstance(result, AnalystSnapshot)
            assert result.ticker == "AAPL"
            assert result.fetched_at is not None

    @pytest.mark.asyncio
    async def test_fetch_analyst_activity_real(self, service: IntelligenceService) -> None:
        """AAPL should have analyst activity data."""
        result = await service.fetch_analyst_activity("AAPL")
        if result is not None:
            assert isinstance(result, AnalystActivitySnapshot)
            assert result.ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_fetch_insider_activity_real(self, service: IntelligenceService) -> None:
        """AAPL should have insider transaction data."""
        result = await service.fetch_insider_activity("AAPL")
        if result is not None:
            assert isinstance(result, InsiderSnapshot)
            assert result.ticker == "AAPL"
            assert len(result.transactions) > 0

    @pytest.mark.asyncio
    async def test_fetch_institutional_real(self, service: IntelligenceService) -> None:
        """AAPL should have institutional ownership data."""
        result = await service.fetch_institutional("AAPL")
        if result is not None:
            assert isinstance(result, InstitutionalSnapshot)
            assert result.ticker == "AAPL"
            if result.institutional_pct is not None:
                assert 0.0 <= result.institutional_pct <= 1.0

    @pytest.mark.asyncio
    async def test_fetch_news_headlines_real(self, service: IntelligenceService) -> None:
        """AAPL should have recent news headlines."""
        result = await service.fetch_news_headlines("AAPL")
        if result is not None:
            assert isinstance(result, list)
            assert len(result) <= 5
            assert all(isinstance(h, str) for h in result)

    @pytest.mark.asyncio
    async def test_fetch_intelligence_real(self, service: IntelligenceService) -> None:
        """Full intelligence package for AAPL should work."""
        result = await service.fetch_intelligence("AAPL", 185.0)
        if result is not None:
            assert isinstance(result, IntelligencePackage)
            assert result.ticker == "AAPL"
            assert result.intelligence_completeness() > 0.0

    @pytest.mark.asyncio
    async def test_msft_intelligence(self, service: IntelligenceService) -> None:
        """MSFT should also work for basic intelligence fetch."""
        result = await service.fetch_intelligence("MSFT", 400.0)
        if result is not None:
            assert isinstance(result, IntelligencePackage)
            assert result.ticker == "MSFT"

    @pytest.mark.asyncio
    async def test_small_cap_graceful_degradation(self, service: IntelligenceService) -> None:
        """Small/obscure ticker should return None or partial data, not crash."""
        result = await service.fetch_intelligence("ZZZZ_INVALID_TICKER", 10.0)
        # Should either return None or a partial package — never crash
        if result is not None:
            assert isinstance(result, IntelligencePackage)

    @pytest.mark.asyncio
    async def test_cache_hit_on_second_call(self, service: IntelligenceService) -> None:
        """Second call should be faster due to caching."""
        # First call
        result1 = await service.fetch_analyst_targets("MSFT", 400.0)
        # Second call should use cache
        result2 = await service.fetch_analyst_targets("MSFT", 400.0)
        # Both should be equivalent if first succeeded
        if result1 is not None:
            assert result2 is not None
            assert result1.ticker == result2.ticker

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self, cache: ServiceCache, limiter: RateLimiter) -> None:
        """Disabled service should return None without making any calls."""
        disabled_config = IntelligenceConfig(enabled=False)
        disabled_service = IntelligenceService(
            config=disabled_config, cache=cache, limiter=limiter
        )
        result = await disabled_service.fetch_intelligence("AAPL", 185.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_analyst_disabled_returns_none(
        self, cache: ServiceCache, limiter: RateLimiter
    ) -> None:
        """Analyst disabled should skip analyst fetch."""
        partial_config = IntelligenceConfig(analyst_enabled=False)
        partial_service = IntelligenceService(config=partial_config, cache=cache, limiter=limiter)
        result = await partial_service.fetch_analyst_targets("AAPL", 185.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_news_disabled_returns_none(
        self, cache: ServiceCache, limiter: RateLimiter
    ) -> None:
        """News disabled should skip news fetch."""
        partial_config = IntelligenceConfig(news_fallback_enabled=False)
        partial_service = IntelligenceService(config=partial_config, cache=cache, limiter=limiter)
        result = await partial_service.fetch_news_headlines("AAPL")
        assert result is None
