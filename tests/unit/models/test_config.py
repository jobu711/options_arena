"""Unit tests for AppSettings and sub-config models.

Tests:
  - Default construction with no args
  - All default values across ScanConfig, PricingConfig, ServiceConfig
  - Env var overrides via monkeypatch (ARENA_ prefix, __ nested delimiter)
  - Type coercion from string env vars to int/float
  - Sub-configs are BaseModel, not BaseSettings
  - AppSettings is BaseSettings subclass
  - Constructor overrides
"""

import pytest
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from options_arena.models import (
    AppSettings,
    DebateConfig,
    DebateProvider,
    PricingConfig,
    ScanConfig,
    ServiceConfig,
)

# ---------------------------------------------------------------------------
# Helper: list of all ARENA_* env var names we might need to clean
# ---------------------------------------------------------------------------
_ARENA_ENV_VARS = [
    "ARENA_SCAN__TOP_N",
    "ARENA_SCAN__MIN_SCORE",
    "ARENA_SCAN__MIN_PRICE",
    "ARENA_SCAN__MIN_DOLLAR_VOLUME",
    "ARENA_SCAN__OHLCV_MIN_BARS",
    "ARENA_SCAN__ADX_TREND_THRESHOLD",
    "ARENA_SCAN__RSI_OVERBOUGHT",
    "ARENA_SCAN__RSI_OVERSOLD",
    "ARENA_PRICING__RISK_FREE_RATE_FALLBACK",
    "ARENA_PRICING__DELTA_PRIMARY_MIN",
    "ARENA_PRICING__DELTA_PRIMARY_MAX",
    "ARENA_PRICING__DELTA_FALLBACK_MIN",
    "ARENA_PRICING__DELTA_FALLBACK_MAX",
    "ARENA_PRICING__DELTA_TARGET",
    "ARENA_PRICING__DTE_MIN",
    "ARENA_PRICING__DTE_MAX",
    "ARENA_PRICING__MIN_OI",
    "ARENA_PRICING__MIN_VOLUME",
    "ARENA_PRICING__MAX_SPREAD_PCT",
    "ARENA_PRICING__IV_SOLVER_TOL",
    "ARENA_PRICING__IV_SOLVER_MAX_ITER",
    "ARENA_SERVICE__YFINANCE_TIMEOUT",
    "ARENA_SERVICE__FRED_TIMEOUT",
    "ARENA_SERVICE__OLLAMA_TIMEOUT",
    "ARENA_SERVICE__RATE_LIMIT_RPS",
    "ARENA_SERVICE__MAX_CONCURRENT_REQUESTS",
    "ARENA_SERVICE__CACHE_TTL_MARKET_HOURS",
    "ARENA_SERVICE__CACHE_TTL_AFTER_HOURS",
    "ARENA_SERVICE__OLLAMA_HOST",
    "ARENA_SERVICE__OLLAMA_MODEL",
    "ARENA_DEBATE__PROVIDER",
    "ARENA_DEBATE__OLLAMA_HOST",
    "ARENA_DEBATE__OLLAMA_MODEL",
    "ARENA_DEBATE__OLLAMA_TIMEOUT",
    "ARENA_DEBATE__GROQ_MODEL",
    "ARENA_DEBATE__GROQ_API_KEY",
    "ARENA_DEBATE__NUM_CTX",
    "ARENA_DEBATE__RETRIES",
    "ARENA_DEBATE__FALLBACK_CONFIDENCE",
    "ARENA_DEBATE__MAX_TOTAL_DURATION",
]


@pytest.fixture(autouse=True)
def _clean_arena_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove all ARENA_* env vars before each test to prevent cross-contamination."""
    for var in _ARENA_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# Default construction
# ---------------------------------------------------------------------------


class TestAppSettingsDefaults:
    def test_app_settings_constructs_with_no_args(self) -> None:
        settings = AppSettings()
        assert settings is not None

    def test_scan_top_n_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.top_n == 50

    def test_scan_min_score_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.min_score == pytest.approx(0.0)

    def test_scan_min_price_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.min_price == pytest.approx(10.0)

    def test_scan_min_dollar_volume_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.min_dollar_volume == pytest.approx(10_000_000.0)

    def test_scan_ohlcv_min_bars_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.ohlcv_min_bars == 200

    def test_pricing_delta_target_default(self) -> None:
        settings = AppSettings()
        assert settings.pricing.delta_target == pytest.approx(0.35)

    def test_pricing_risk_free_rate_fallback_default(self) -> None:
        settings = AppSettings()
        assert settings.pricing.risk_free_rate_fallback == pytest.approx(0.05)

    def test_pricing_dte_min_default(self) -> None:
        settings = AppSettings()
        assert settings.pricing.dte_min == 30

    def test_pricing_dte_max_default(self) -> None:
        settings = AppSettings()
        assert settings.pricing.dte_max == 365

    def test_service_ollama_host_default(self) -> None:
        settings = AppSettings()
        assert settings.service.ollama_host == "http://localhost:11434"

    def test_service_ollama_model_default(self) -> None:
        settings = AppSettings()
        assert settings.service.ollama_model == "llama3.1:8b"

    def test_service_yfinance_timeout_default(self) -> None:
        settings = AppSettings()
        assert settings.service.yfinance_timeout == pytest.approx(15.0)

    def test_service_max_concurrent_requests_default(self) -> None:
        settings = AppSettings()
        assert settings.service.max_concurrent_requests == 5


# ---------------------------------------------------------------------------
# Env var overrides
# ---------------------------------------------------------------------------


class TestAppSettingsEnvOverrides:
    def test_env_override_scan_top_n(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARENA_SCAN__TOP_N", "30")
        settings = AppSettings()
        assert settings.scan.top_n == 30

    def test_env_override_pricing_delta_target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARENA_PRICING__DELTA_TARGET", "0.40")
        settings = AppSettings()
        assert settings.pricing.delta_target == pytest.approx(0.40)

    def test_env_override_service_ollama_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARENA_SERVICE__OLLAMA_HOST", "http://gpu:11434")
        settings = AppSettings()
        assert settings.service.ollama_host == "http://gpu:11434"

    def test_env_override_type_coercion_string_to_int(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ARENA_SCAN__TOP_N", "25")
        settings = AppSettings()
        assert settings.scan.top_n == 25
        assert isinstance(settings.scan.top_n, int)

    def test_env_override_type_coercion_string_to_float(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ARENA_SERVICE__YFINANCE_TIMEOUT", "30.5")
        settings = AppSettings()
        assert settings.service.yfinance_timeout == pytest.approx(30.5)
        assert isinstance(settings.service.yfinance_timeout, float)


# ---------------------------------------------------------------------------
# Type hierarchy
# ---------------------------------------------------------------------------


class TestConfigTypeHierarchy:
    def test_app_settings_is_base_settings_subclass(self) -> None:
        assert issubclass(AppSettings, BaseSettings)

    def test_scan_config_is_base_model(self) -> None:
        assert issubclass(ScanConfig, BaseModel)

    def test_scan_config_is_not_base_settings(self) -> None:
        assert not issubclass(ScanConfig, BaseSettings)

    def test_pricing_config_is_base_model(self) -> None:
        assert issubclass(PricingConfig, BaseModel)

    def test_pricing_config_is_not_base_settings(self) -> None:
        assert not issubclass(PricingConfig, BaseSettings)

    def test_service_config_is_base_model(self) -> None:
        assert issubclass(ServiceConfig, BaseModel)

    def test_service_config_is_not_base_settings(self) -> None:
        assert not issubclass(ServiceConfig, BaseSettings)


# ---------------------------------------------------------------------------
# Constructor overrides
# ---------------------------------------------------------------------------


class TestConfigConstructorOverrides:
    def test_constructor_override_scan_top_n(self) -> None:
        settings = AppSettings(scan=ScanConfig(top_n=25))
        assert settings.scan.top_n == 25

    def test_constructor_override_pricing_delta_target(self) -> None:
        settings = AppSettings(pricing=PricingConfig(delta_target=0.40))
        assert settings.pricing.delta_target == pytest.approx(0.40)

    def test_constructor_override_service_ollama_host(self) -> None:
        settings = AppSettings(service=ServiceConfig(ollama_host="http://custom:8080"))
        assert settings.service.ollama_host == "http://custom:8080"

    def test_constructor_takes_priority_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARENA_SCAN__TOP_N", "30")
        settings = AppSettings(scan=ScanConfig(top_n=99))
        assert settings.scan.top_n == 99


# ---------------------------------------------------------------------------
# DebateConfig defaults
# ---------------------------------------------------------------------------


class TestDebateConfigDefaults:
    """Tests for DebateConfig default values and AppSettings integration."""

    def test_debate_config_constructs_with_defaults(self) -> None:
        """DebateConfig() constructs with all production defaults."""
        config = DebateConfig()
        assert config.provider == DebateProvider.OLLAMA
        assert config.ollama_host == "http://localhost:11434"
        assert config.ollama_model == "llama3.1:8b"
        assert config.ollama_timeout == pytest.approx(600.0)
        assert config.groq_model == "llama-3.3-70b-versatile"
        assert config.groq_api_key is None
        assert config.num_ctx == 8192
        assert config.retries == 2
        assert config.temperature == pytest.approx(0.3)
        assert config.fallback_confidence == pytest.approx(0.3)
        assert config.max_total_duration == pytest.approx(1800.0)

    def test_app_settings_has_debate_field(self) -> None:
        """AppSettings includes a debate field."""
        settings = AppSettings()
        assert hasattr(settings, "debate")
        assert isinstance(settings.debate, DebateConfig)

    def test_app_settings_debate_defaults(self) -> None:
        """AppSettings().debate has correct defaults."""
        settings = AppSettings()
        assert settings.debate.ollama_host == "http://localhost:11434"
        assert settings.debate.num_ctx == 8192
        assert settings.debate.fallback_confidence == pytest.approx(0.3)

    def test_debate_config_is_base_model(self) -> None:
        """DebateConfig is a BaseModel, not BaseSettings."""
        assert issubclass(DebateConfig, BaseModel)
        assert not issubclass(DebateConfig, BaseSettings)

    def test_env_override_debate_num_ctx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__NUM_CTX env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__NUM_CTX", "16384")
        settings = AppSettings()
        assert settings.debate.num_ctx == 16384

    def test_env_override_debate_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__PROVIDER env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__PROVIDER", "groq")
        settings = AppSettings()
        assert settings.debate.provider == DebateProvider.GROQ

    def test_env_override_debate_groq_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__GROQ_MODEL env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__GROQ_MODEL", "llama-3.1-8b-instant")
        settings = AppSettings()
        assert settings.debate.groq_model == "llama-3.1-8b-instant"

    def test_env_override_debate_groq_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__GROQ_API_KEY env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__GROQ_API_KEY", "gsk_test_key_123")
        settings = AppSettings()
        assert settings.debate.groq_api_key == "gsk_test_key_123"

    def test_debate_provider_default_is_ollama(self) -> None:
        """Default provider is OLLAMA (backward compatible)."""
        settings = AppSettings()
        assert settings.debate.provider == DebateProvider.OLLAMA

    def test_debate_groq_api_key_default_is_none(self) -> None:
        """Default groq_api_key is None."""
        settings = AppSettings()
        assert settings.debate.groq_api_key is None
