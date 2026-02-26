"""Tests for FastAPI app factory and configuration."""

from __future__ import annotations

from options_arena.api.app import create_app


def test_create_app_returns_fastapi_instance() -> None:
    """create_app() returns a configured FastAPI application."""
    app = create_app()
    assert app.title == "Options Arena"
    assert app.version == "1.5.0"


def test_create_app_has_cors_middleware() -> None:
    """App includes CORS middleware for Vite dev server."""
    app = create_app()
    middleware_classes = [m.cls.__name__ for m in app.user_middleware]
    assert "CORSMiddleware" in middleware_classes


def test_create_app_registers_health_route() -> None:
    """Health route is registered at /api/health."""
    app = create_app()
    route_paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/api/health" in route_paths
