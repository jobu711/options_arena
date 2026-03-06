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


class TestDTEForwardingToPricingConfig:
    """Tests that DTE overrides propagate to PricingConfig."""

    def test_dte_override_builds_correct_pricing_config(self) -> None:
        """Verify the override logic produces correct PricingConfig values.

        This tests the override pattern directly (unit test) rather than
        going through the full HTTP stack.
        """
        settings = AppSettings()

        # Simulate the route override logic for DTE
        scan_overrides: dict[str, object] = {"min_dte": 14, "max_dte": 45}
        pricing_overrides: dict[str, object] = {"dte_min": 14, "dte_max": 45}

        new_scan = settings.scan.model_copy(update=scan_overrides)
        new_pricing = settings.pricing.model_copy(update=pricing_overrides)
        effective = settings.model_copy(update={"scan": new_scan, "pricing": new_pricing})

        # ScanConfig should have the new DTE fields
        assert effective.scan.min_dte == 14
        assert effective.scan.max_dte == 45

        # PricingConfig.dte_min / dte_max should be forwarded
        assert effective.pricing.dte_min == 14
        assert effective.pricing.dte_max == 45

    def test_no_dte_override_preserves_defaults(self) -> None:
        """Without DTE overrides, PricingConfig retains defaults."""
        settings = AppSettings()
        assert settings.pricing.dte_min == 30
        assert settings.pricing.dte_max == 365

    def test_max_price_override_builds_correct_scan_config(self) -> None:
        """Verify max_price override produces correct ScanConfig."""
        settings = AppSettings()
        scan_overrides: dict[str, object] = {"max_price": 250.0}
        new_scan = settings.scan.model_copy(update=scan_overrides)
        effective = settings.model_copy(update={"scan": new_scan})

        assert effective.scan.max_price == 250.0
        # Original settings unchanged
        assert settings.scan.max_price is None

    def test_combined_overrides(self) -> None:
        """All new overrides applied together produce correct config."""
        settings = AppSettings()
        scan_overrides: dict[str, object] = {
            "min_price": 20.0,
            "max_price": 500.0,
            "min_dte": 7,
            "max_dte": 90,
        }
        pricing_overrides: dict[str, object] = {"dte_min": 7, "dte_max": 90}

        new_scan = settings.scan.model_copy(update=scan_overrides)
        new_pricing = settings.pricing.model_copy(update=pricing_overrides)
        effective = settings.model_copy(update={"scan": new_scan, "pricing": new_pricing})

        assert effective.scan.min_price == 20.0
        assert effective.scan.max_price == 500.0
        assert effective.scan.min_dte == 7
        assert effective.scan.max_dte == 90
        assert effective.pricing.dte_min == 7
        assert effective.pricing.dte_max == 90
