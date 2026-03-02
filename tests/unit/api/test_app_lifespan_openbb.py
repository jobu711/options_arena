"""Tests for OpenBB service lifecycle in FastAPI lifespan."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI

from options_arena.api.app import lifespan
from options_arena.models.config import OpenBBConfig


def _make_service_patches() -> dict[str, MagicMock]:
    """Create patch targets that return AsyncMock instances (awaitable close())."""
    patches: dict[str, MagicMock] = {}
    for name in ("MarketDataService", "OptionsDataService", "FredService", "UniverseService"):
        mock_cls = MagicMock()
        mock_cls.return_value = AsyncMock()
        patches[name] = mock_cls
    return patches


async def test_lifespan_creates_openbb_when_enabled(tmp_path: Path) -> None:
    """Verify OpenBBService created and stored on app.state.openbb when enabled."""
    svc_patches = _make_service_patches()

    with (
        patch("options_arena.api.app.AppSettings") as mock_settings_cls,
        patch("options_arena.api.app.Database") as mock_db_cls,
        patch("options_arena.api.app.Repository"),
        patch("options_arena.api.app.OpenBBService") as mock_openbb_cls,
        patch("options_arena.api.app.MarketDataService", svc_patches["MarketDataService"]),
        patch("options_arena.api.app.OptionsDataService", svc_patches["OptionsDataService"]),
        patch("options_arena.api.app.FredService", svc_patches["FredService"]),
        patch("options_arena.api.app.UniverseService", svc_patches["UniverseService"]),
        patch("options_arena.api.app.ServiceCache") as mock_cache_cls,
        patch("options_arena.api.app.RateLimiter"),
    ):
        mock_settings = MagicMock()
        mock_settings.openbb = OpenBBConfig(enabled=True)
        mock_settings.data.db_path = str(tmp_path / "test.db")
        mock_settings_cls.return_value = mock_settings

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        mock_openbb_svc = AsyncMock()
        mock_openbb_cls.return_value = mock_openbb_svc

        app = FastAPI()
        async with lifespan(app):
            # Verify OpenBBService was constructed
            mock_openbb_cls.assert_called_once()
            # Verify it was stored on app.state
            assert app.state.openbb is mock_openbb_svc


async def test_lifespan_stores_none_when_disabled(tmp_path: Path) -> None:
    """Verify app.state.openbb is None when OpenBBConfig.enabled=False."""
    svc_patches = _make_service_patches()

    with (
        patch("options_arena.api.app.AppSettings") as mock_settings_cls,
        patch("options_arena.api.app.Database") as mock_db_cls,
        patch("options_arena.api.app.Repository"),
        patch("options_arena.api.app.OpenBBService") as mock_openbb_cls,
        patch("options_arena.api.app.MarketDataService", svc_patches["MarketDataService"]),
        patch("options_arena.api.app.OptionsDataService", svc_patches["OptionsDataService"]),
        patch("options_arena.api.app.FredService", svc_patches["FredService"]),
        patch("options_arena.api.app.UniverseService", svc_patches["UniverseService"]),
        patch("options_arena.api.app.ServiceCache") as mock_cache_cls,
        patch("options_arena.api.app.RateLimiter"),
    ):
        mock_settings = MagicMock()
        mock_settings.openbb = OpenBBConfig(enabled=False)
        mock_settings.data.db_path = str(tmp_path / "test.db")
        mock_settings_cls.return_value = mock_settings

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        app = FastAPI()
        async with lifespan(app):
            # OpenBBService constructor should NOT have been called
            mock_openbb_cls.assert_not_called()
            # app.state.openbb should be None
            assert app.state.openbb is None


async def test_lifespan_closes_openbb_at_shutdown(tmp_path: Path) -> None:
    """Verify OpenBBService.close() called during shutdown."""
    svc_patches = _make_service_patches()

    with (
        patch("options_arena.api.app.AppSettings") as mock_settings_cls,
        patch("options_arena.api.app.Database") as mock_db_cls,
        patch("options_arena.api.app.Repository"),
        patch("options_arena.api.app.OpenBBService") as mock_openbb_cls,
        patch("options_arena.api.app.MarketDataService", svc_patches["MarketDataService"]),
        patch("options_arena.api.app.OptionsDataService", svc_patches["OptionsDataService"]),
        patch("options_arena.api.app.FredService", svc_patches["FredService"]),
        patch("options_arena.api.app.UniverseService", svc_patches["UniverseService"]),
        patch("options_arena.api.app.ServiceCache") as mock_cache_cls,
        patch("options_arena.api.app.RateLimiter"),
    ):
        mock_settings = MagicMock()
        mock_settings.openbb = OpenBBConfig(enabled=True)
        mock_settings.data.db_path = str(tmp_path / "test.db")
        mock_settings_cls.return_value = mock_settings

        mock_db = AsyncMock()
        mock_db_cls.return_value = mock_db

        mock_cache = AsyncMock()
        mock_cache_cls.return_value = mock_cache

        mock_openbb_svc = AsyncMock()
        mock_openbb_cls.return_value = mock_openbb_svc

        app = FastAPI()
        async with lifespan(app):
            pass  # lifespan entered successfully

        # After exiting the context, shutdown has run.
        # Verify close() was called on the OpenBB service.
        mock_openbb_svc.close.assert_awaited_once()
