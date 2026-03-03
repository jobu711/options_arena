"""Unit tests for IntelligenceConfig and its nesting in AppSettings.

Tests cover:
- Default values for all IntelligenceConfig fields
- Master toggle behavior
- Per-source toggle behavior
- Nesting in AppSettings
- Env var overrides via ARENA_INTELLIGENCE__* prefix
"""

import pytest
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from options_arena.models import AppSettings
from options_arena.models.config import IntelligenceConfig

# ---------------------------------------------------------------------------
# Env vars to clean before each test
# ---------------------------------------------------------------------------

_ARENA_INTELLIGENCE_VARS = [
    "ARENA_INTELLIGENCE__ENABLED",
    "ARENA_INTELLIGENCE__ANALYST_ENABLED",
    "ARENA_INTELLIGENCE__INSIDER_ENABLED",
    "ARENA_INTELLIGENCE__INSTITUTIONAL_ENABLED",
    "ARENA_INTELLIGENCE__NEWS_FALLBACK_ENABLED",
    "ARENA_INTELLIGENCE__ANALYST_CACHE_TTL",
    "ARENA_INTELLIGENCE__INSIDER_CACHE_TTL",
    "ARENA_INTELLIGENCE__INSTITUTIONAL_CACHE_TTL",
    "ARENA_INTELLIGENCE__NEWS_CACHE_TTL",
    "ARENA_INTELLIGENCE__REQUEST_TIMEOUT",
]


@pytest.fixture(autouse=True)
def _clean_arena_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all ARENA_INTELLIGENCE__* env vars before each test."""
    for var in _ARENA_INTELLIGENCE_VARS:
        monkeypatch.delenv(var, raising=False)


# ===========================================================================
# IntelligenceConfig
# ===========================================================================


class TestIntelligenceConfig:
    """Tests for the IntelligenceConfig model."""

    def test_default_values(self) -> None:
        """IntelligenceConfig defaults are correct."""
        config = IntelligenceConfig()
        assert config.enabled is True
        assert config.analyst_enabled is True
        assert config.insider_enabled is True
        assert config.institutional_enabled is True
        assert config.news_fallback_enabled is True
        assert config.analyst_cache_ttl == 86400
        assert config.insider_cache_ttl == 21600
        assert config.institutional_cache_ttl == 86400
        assert config.news_cache_ttl == 900
        assert config.request_timeout == pytest.approx(15.0)

    def test_is_base_model_not_base_settings(self) -> None:
        """IntelligenceConfig is BaseModel, not BaseSettings."""
        assert issubclass(IntelligenceConfig, BaseModel)
        assert not issubclass(IntelligenceConfig, BaseSettings)

    def test_disabled_master_switch(self) -> None:
        """IntelligenceConfig enabled=False disables at config level."""
        config = IntelligenceConfig(enabled=False)
        assert config.enabled is False
        # Individual toggles retain their defaults
        assert config.analyst_enabled is True

    def test_custom_ttls(self) -> None:
        """IntelligenceConfig accepts custom TTL values."""
        config = IntelligenceConfig(
            analyst_cache_ttl=3600,
            insider_cache_ttl=1800,
            news_cache_ttl=300,
        )
        assert config.analyst_cache_ttl == 3600
        assert config.insider_cache_ttl == 1800
        assert config.news_cache_ttl == 300

    def test_nested_in_app_settings(self) -> None:
        """IntelligenceConfig is nested in AppSettings with defaults."""
        settings = AppSettings()
        assert hasattr(settings, "intelligence")
        assert isinstance(settings.intelligence, IntelligenceConfig)
        assert settings.intelligence.enabled is True

    def test_env_override_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_INTELLIGENCE__ENABLED=false disables via env var."""
        monkeypatch.setenv("ARENA_INTELLIGENCE__ENABLED", "false")
        settings = AppSettings()
        assert settings.intelligence.enabled is False

    def test_env_override_cache_ttl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_INTELLIGENCE__ANALYST_CACHE_TTL=3600 overrides default."""
        monkeypatch.setenv("ARENA_INTELLIGENCE__ANALYST_CACHE_TTL", "3600")
        settings = AppSettings()
        assert settings.intelligence.analyst_cache_ttl == 3600

    def test_env_override_request_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_INTELLIGENCE__REQUEST_TIMEOUT=30.0 overrides default."""
        monkeypatch.setenv("ARENA_INTELLIGENCE__REQUEST_TIMEOUT", "30.0")
        settings = AppSettings()
        assert settings.intelligence.request_timeout == pytest.approx(30.0)
