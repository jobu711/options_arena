"""Integration tests for ServiceBase unification.

Verifies that all 7 services inherit from ServiceBase, instantiate with shared
infrastructure (cache + rate limiter), and close without error.  Uses in-memory
cache (``db_path=None``) and a fast limiter (1000 req/s, 100 concurrent) so no
external APIs are contacted.
"""

from __future__ import annotations

import pytest

from options_arena.models.config import (
    FinancialDatasetsConfig,
    IntelligenceConfig,
    OpenBBConfig,
    PricingConfig,
    ServiceConfig,
)
from options_arena.models.filters import OptionsFilters
from options_arena.services.base import ServiceBase
from options_arena.services.cache import ServiceCache
from options_arena.services.financial_datasets import FinancialDatasetsService
from options_arena.services.fred import FredService
from options_arena.services.intelligence import IntelligenceService
from options_arena.services.market_data import MarketDataService
from options_arena.services.openbb_service import OpenBBService
from options_arena.services.options_data import OptionsDataService
from options_arena.services.rate_limiter import RateLimiter
from options_arena.services.universe import UniverseService

# ---------------------------------------------------------------------------
# Shared config / infra fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service_config() -> ServiceConfig:
    return ServiceConfig()


@pytest.fixture
def pricing_config() -> PricingConfig:
    return PricingConfig()


@pytest.fixture
def openbb_config() -> OpenBBConfig:
    return OpenBBConfig()


@pytest.fixture
def intelligence_config() -> IntelligenceConfig:
    return IntelligenceConfig()


@pytest.fixture
def financial_datasets_config() -> FinancialDatasetsConfig:
    return FinancialDatasetsConfig(enabled=False)


@pytest.fixture
def cache(service_config: ServiceConfig) -> ServiceCache:
    """In-memory-only cache (no SQLite)."""
    return ServiceCache(service_config, db_path=None)


@pytest.fixture
def limiter() -> RateLimiter:
    """Fast limiter — effectively unlimited for instantiation tests."""
    return RateLimiter(1000.0, 100)


# ---------------------------------------------------------------------------
# Service factory helpers
# ---------------------------------------------------------------------------


def _build_all_services(
    service_config: ServiceConfig,
    pricing_config: PricingConfig,
    openbb_config: OpenBBConfig,
    intelligence_config: IntelligenceConfig,
    financial_datasets_config: FinancialDatasetsConfig,
    cache: ServiceCache,
    limiter: RateLimiter,
) -> list[ServiceBase[object]]:
    """Instantiate all 7 services with shared cache and limiter."""
    return [
        MarketDataService(config=service_config, cache=cache, limiter=limiter),
        UniverseService(config=service_config, cache=cache, limiter=limiter),
        OptionsDataService(
            config=service_config,
            options_filters=OptionsFilters(),
            cache=cache,
            limiter=limiter,
        ),
        FredService(
            config=service_config,
            pricing_config=pricing_config,
            cache=cache,
        ),
        OpenBBService(config=openbb_config, cache=cache, limiter=limiter),
        IntelligenceService(config=intelligence_config, cache=cache, limiter=limiter),
        FinancialDatasetsService(
            config=financial_datasets_config,
            cache=cache,
            limiter=limiter,
        ),
    ]


# The 7 service classes that must all inherit ServiceBase
ALL_SERVICE_CLASSES: list[type[ServiceBase[object]]] = [
    MarketDataService,  # type: ignore[list-item]
    UniverseService,  # type: ignore[list-item]
    OptionsDataService,  # type: ignore[list-item]
    FredService,  # type: ignore[list-item]
    OpenBBService,  # type: ignore[list-item]
    IntelligenceService,  # type: ignore[list-item]
    FinancialDatasetsService,  # type: ignore[list-item]
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestServiceBaseIntegration:
    """Integration tests verifying all 7 services inherit ServiceBase."""

    def test_all_services_inherit_service_base(self) -> None:
        """Verify all 7 services are ServiceBase subclasses."""
        assert len(ALL_SERVICE_CLASSES) == 7, (  # noqa: PLR2004
            f"Expected exactly 7 service classes, got {len(ALL_SERVICE_CLASSES)}"
        )
        for cls in ALL_SERVICE_CLASSES:
            assert issubclass(cls, ServiceBase), (
                f"{cls.__name__} does not inherit from ServiceBase"
            )

    def test_all_services_instantiate_with_shared_infra(
        self,
        service_config: ServiceConfig,
        pricing_config: PricingConfig,
        openbb_config: OpenBBConfig,
        intelligence_config: IntelligenceConfig,
        financial_datasets_config: FinancialDatasetsConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify all 7 services can be created with shared cache and limiter."""
        services = _build_all_services(
            service_config,
            pricing_config,
            openbb_config,
            intelligence_config,
            financial_datasets_config,
            cache,
            limiter,
        )
        assert len(services) == 7  # noqa: PLR2004
        for svc in services:
            assert isinstance(svc, ServiceBase)

    @pytest.mark.asyncio
    async def test_all_services_close_without_error(
        self,
        service_config: ServiceConfig,
        pricing_config: PricingConfig,
        openbb_config: OpenBBConfig,
        intelligence_config: IntelligenceConfig,
        financial_datasets_config: FinancialDatasetsConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify close() works on all 7 services without raising."""
        services = _build_all_services(
            service_config,
            pricing_config,
            openbb_config,
            intelligence_config,
            financial_datasets_config,
            cache,
            limiter,
        )
        for svc in services:
            await svc.close()  # must not raise

    def test_config_stored_correctly(
        self,
        service_config: ServiceConfig,
        pricing_config: PricingConfig,
        openbb_config: OpenBBConfig,
        intelligence_config: IntelligenceConfig,
        financial_datasets_config: FinancialDatasetsConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify _config attribute matches constructor arg for each service."""
        mkt = MarketDataService(config=service_config, cache=cache, limiter=limiter)
        assert mkt._config is service_config  # noqa: SLF001

        uni = UniverseService(config=service_config, cache=cache, limiter=limiter)
        assert uni._config is service_config  # noqa: SLF001

        opts = OptionsDataService(
            config=service_config,
            options_filters=OptionsFilters(),
            cache=cache,
            limiter=limiter,
        )
        assert opts._config is service_config  # noqa: SLF001

        fred = FredService(
            config=service_config,
            pricing_config=pricing_config,
            cache=cache,
        )
        assert fred._config is service_config  # noqa: SLF001

        obb = OpenBBService(config=openbb_config, cache=cache, limiter=limiter)
        assert obb._config is openbb_config  # noqa: SLF001

        intel = IntelligenceService(config=intelligence_config, cache=cache, limiter=limiter)
        assert intel._config is intelligence_config  # noqa: SLF001

        fd = FinancialDatasetsService(
            config=financial_datasets_config,
            cache=cache,
            limiter=limiter,
        )
        assert fd._config is financial_datasets_config  # noqa: SLF001

    def test_cache_shared_across_services(
        self,
        service_config: ServiceConfig,
        pricing_config: PricingConfig,
        openbb_config: OpenBBConfig,
        intelligence_config: IntelligenceConfig,
        financial_datasets_config: FinancialDatasetsConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify all services share the same cache instance."""
        services = _build_all_services(
            service_config,
            pricing_config,
            openbb_config,
            intelligence_config,
            financial_datasets_config,
            cache,
            limiter,
        )
        for svc in services:
            assert svc._cache is cache, (  # noqa: SLF001
                f"{type(svc).__name__}._cache is not the shared cache instance"
            )

    def test_limiter_shared_across_services(
        self,
        service_config: ServiceConfig,
        pricing_config: PricingConfig,
        openbb_config: OpenBBConfig,
        intelligence_config: IntelligenceConfig,
        financial_datasets_config: FinancialDatasetsConfig,
        cache: ServiceCache,
        limiter: RateLimiter,
    ) -> None:
        """Verify all services (except Fred) share the same limiter."""
        mkt = MarketDataService(config=service_config, cache=cache, limiter=limiter)
        assert mkt._limiter is limiter  # noqa: SLF001

        uni = UniverseService(config=service_config, cache=cache, limiter=limiter)
        assert uni._limiter is limiter  # noqa: SLF001

        opts = OptionsDataService(
            config=service_config,
            options_filters=OptionsFilters(),
            cache=cache,
            limiter=limiter,
        )
        assert opts._limiter is limiter  # noqa: SLF001

        obb = OpenBBService(config=openbb_config, cache=cache, limiter=limiter)
        assert obb._limiter is limiter  # noqa: SLF001

        intel = IntelligenceService(config=intelligence_config, cache=cache, limiter=limiter)
        assert intel._limiter is limiter  # noqa: SLF001

        fd = FinancialDatasetsService(
            config=financial_datasets_config,
            cache=cache,
            limiter=limiter,
        )
        assert fd._limiter is limiter  # noqa: SLF001

        # FredService does NOT require a limiter (limiter=None)
        fred = FredService(
            config=service_config,
            pricing_config=pricing_config,
            cache=cache,
        )
        assert fred._limiter is None  # noqa: SLF001

    def test_consumer_code_unchanged(self) -> None:
        """Verify import signatures match expected patterns.

        All 7 service classes must be importable from their respective modules
        and from the package ``__init__.py`` re-exports.
        """
        # Package-level re-exports
        from options_arena.services import (  # noqa: F401
            FinancialDatasetsService,
            FredService,
            IntelligenceService,
            MarketDataService,
            OpenBBService,
            OptionsDataService,
            ServiceBase,
            UniverseService,
        )

        # Direct submodule imports
        from options_arena.services.financial_datasets import (  # noqa: F401
            FinancialDatasetsService as FD,
        )
        from options_arena.services.fred import FredService as FS  # noqa: F401
        from options_arena.services.intelligence import (  # noqa: F401
            IntelligenceService as IS,
        )
        from options_arena.services.market_data import (  # noqa: F401
            MarketDataService as MD,
        )
        from options_arena.services.openbb_service import (  # noqa: F401
            OpenBBService as OBB,
        )
        from options_arena.services.options_data import (  # noqa: F401
            OptionsDataService as OD,
        )
        from options_arena.services.universe import (  # noqa: F401
            UniverseService as US,
        )

    def test_seven_services_count(self) -> None:
        """Verify exactly 7 service classes inherit ServiceBase.

        This is a guard against accidentally missing a service during
        the migration or adding a new service without updating tests.
        """
        assert len(ALL_SERVICE_CLASSES) == 7  # noqa: PLR2004
        # Verify they are distinct
        assert len(set(ALL_SERVICE_CLASSES)) == 7  # noqa: PLR2004
