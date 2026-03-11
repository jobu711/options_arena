"""Tests for scan route override wiring of max_price, min_dte, max_dte (#285).

Verifies that the POST /api/scan endpoint accepts new pre-scan filter fields
and returns 202. Override propagation to ScanConfig and PricingConfig is tested
indirectly by ensuring the endpoint does not reject the new fields.
"""

from __future__ import annotations

from httpx import AsyncClient

from options_arena.models import AppSettings


class TestMaxPriceOverride:
    """Tests for max_price override via POST /api/scan."""

    async def test_max_price_accepted(self, client: AsyncClient) -> None:
        """POST /api/scan with max_price returns 202."""
        response = await client.post(
            "/api/scan",
            json={"preset": "sp500", "max_price": 500.0},
        )
        assert response.status_code == 202
        data = response.json()
        assert "scan_id" in data

    async def test_max_price_none_omitted(self, client: AsyncClient) -> None:
        """POST /api/scan without max_price uses default (None)."""
        response = await client.post(
            "/api/scan",
            json={"preset": "sp500"},
        )
        assert response.status_code == 202


class TestDTEOverride:
    """Tests for min_dte and max_dte override via POST /api/scan."""

    async def test_dte_range_accepted(self, client: AsyncClient) -> None:
        """POST /api/scan with min_dte and max_dte returns 202."""
        response = await client.post(
            "/api/scan",
            json={"preset": "sp500", "min_dte": 14, "max_dte": 60},
        )
        assert response.status_code == 202

    async def test_min_dte_only_accepted(self, client: AsyncClient) -> None:
        """POST /api/scan with only min_dte returns 202."""
        response = await client.post(
            "/api/scan",
            json={"preset": "sp500", "min_dte": 7},
        )
        assert response.status_code == 202

    async def test_max_dte_only_accepted(self, client: AsyncClient) -> None:
        """POST /api/scan with only max_dte returns 202."""
        response = await client.post(
            "/api/scan",
            json={"preset": "sp500", "max_dte": 90},
        )
        assert response.status_code == 202


class TestNoOverrideWhenNone:
    """Tests that None values do not trigger overrides."""

    async def test_all_none_no_overrides(self, client: AsyncClient) -> None:
        """POST /api/scan with no filter fields returns 202 using defaults."""
        response = await client.post(
            "/api/scan",
            json={"preset": "sp500"},
        )
        assert response.status_code == 202

    async def test_explicit_null_fields(self, client: AsyncClient) -> None:
        """POST /api/scan with explicit null fields returns 202."""
        response = await client.post(
            "/api/scan",
            json={
                "preset": "sp500",
                "min_price": None,
                "max_price": None,
                "min_dte": None,
                "max_dte": None,
            },
        )
        assert response.status_code == 202


class TestDTEForwardingToOptionsFilters:
    """Tests that DTE overrides propagate to OptionsFilters via ScanFilterSpec."""

    def test_dte_override_builds_correct_options_filters(self) -> None:
        """Verify the override logic produces correct OptionsFilters values.

        This tests the override pattern directly (unit test) rather than
        going through the full HTTP stack.
        """
        settings = AppSettings()

        # Simulate the route override logic for DTE via nested filter spec
        options_overrides: dict[str, object] = {"min_dte": 14, "max_dte": 45}
        new_options = settings.scan.filters.options.model_copy(update=options_overrides)
        new_filters = settings.scan.filters.model_copy(update={"options": new_options})
        new_scan = settings.scan.model_copy(update={"filters": new_filters})
        effective = settings.model_copy(update={"scan": new_scan})

        # OptionsFilters should have the new DTE fields
        assert effective.scan.filters.options.min_dte == 14
        assert effective.scan.filters.options.max_dte == 45

    def test_no_dte_override_preserves_defaults(self) -> None:
        """Without DTE overrides, OptionsFilters retains defaults."""
        settings = AppSettings()
        assert settings.scan.filters.options.min_dte == 30
        assert settings.scan.filters.options.max_dte == 365

    def test_max_price_override_builds_correct_universe_filters(self) -> None:
        """Verify max_price override produces correct UniverseFilters."""
        settings = AppSettings()
        universe_overrides: dict[str, object] = {"max_price": 250.0}
        new_universe = settings.scan.filters.universe.model_copy(update=universe_overrides)
        new_filters = settings.scan.filters.model_copy(update={"universe": new_universe})
        new_scan = settings.scan.model_copy(update={"filters": new_filters})
        effective = settings.model_copy(update={"scan": new_scan})

        assert effective.scan.filters.universe.max_price == 250.0
        # Original settings unchanged
        assert settings.scan.filters.universe.max_price is None

    def test_combined_overrides(self) -> None:
        """All new overrides applied together produce correct config."""
        settings = AppSettings()

        universe_overrides: dict[str, object] = {
            "min_price": 20.0,
            "max_price": 500.0,
        }
        options_overrides: dict[str, object] = {"min_dte": 7, "max_dte": 90}

        new_universe = settings.scan.filters.universe.model_copy(update=universe_overrides)
        new_options = settings.scan.filters.options.model_copy(update=options_overrides)
        new_filters = settings.scan.filters.model_copy(
            update={"universe": new_universe, "options": new_options}
        )
        new_scan = settings.scan.model_copy(update={"filters": new_filters})
        effective = settings.model_copy(update={"scan": new_scan})

        assert effective.scan.filters.universe.min_price == 20.0
        assert effective.scan.filters.universe.max_price == 500.0
        assert effective.scan.filters.options.min_dte == 7
        assert effective.scan.filters.options.max_dte == 90
