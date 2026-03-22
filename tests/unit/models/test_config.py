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

import operator

import pytest
from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings

from options_arena.models import (
    AppSettings,
    DebateConfig,
    GICSSector,
    LLMProvider,
    PricingConfig,
    ScanConfig,
    ServiceConfig,
)
from options_arena.models.filters import (
    OptionsFilters,
    ScanFilterSpec,
    UniverseFilters,
)

# ---------------------------------------------------------------------------
# Helper: list of all ARENA_* env var names we might need to clean
# ---------------------------------------------------------------------------
_ARENA_ENV_VARS = [
    "ARENA_SCAN__FILTERS__OPTIONS__TOP_N",
    "ARENA_SCAN__FILTERS__SCORING__MIN_SCORE",
    "ARENA_SCAN__FILTERS__UNIVERSE__MIN_PRICE",
    "ARENA_SCAN__FILTERS__OPTIONS__MIN_DOLLAR_VOLUME",
    "ARENA_SCAN__FILTERS__UNIVERSE__OHLCV_MIN_BARS",
    "ARENA_SCAN__ADX_TREND_THRESHOLD",
    "ARENA_SCAN__RSI_OVERBOUGHT",
    "ARENA_SCAN__RSI_OVERSOLD",
    "ARENA_PRICING__RISK_FREE_RATE_FALLBACK",
    "ARENA_PRICING__DELTA_TARGET",
    "ARENA_PRICING__IV_SOLVER_TOL",
    "ARENA_PRICING__IV_SOLVER_MAX_ITER",
    "ARENA_SERVICE__YFINANCE_TIMEOUT",
    "ARENA_SERVICE__FRED_TIMEOUT",
    "ARENA_SERVICE__RATE_LIMIT_RPS",
    "ARENA_SERVICE__MAX_CONCURRENT_REQUESTS",
    "ARENA_SERVICE__CACHE_TTL_MARKET_HOURS",
    "ARENA_SERVICE__CACHE_TTL_AFTER_HOURS",
    "ARENA_SERVICE__GROQ_API_KEY",
    "ARENA_DEBATE__MODEL",
    "ARENA_DEBATE__API_KEY",
    "ARENA_DEBATE__NUM_CTX",
    "ARENA_DEBATE__RETRIES",
    "ARENA_DEBATE__FALLBACK_CONFIDENCE",
    "ARENA_DEBATE__MAX_TOTAL_DURATION",
    "ARENA_DEBATE__MIN_DEBATE_SCORE",
    "ARENA_DEBATE__ENABLE_VOLATILITY_AGENT",
    "ARENA_DEBATE__ENABLE_REBUTTAL",
    "ARENA_DEBATE__PHASE1_PARALLELISM",
    "ARENA_DEBATE__PHASE1_BATCH_DELAY",
    "ARENA_DEBATE__BATCH_TICKER_DELAY",
    "ARENA_DEBATE__RATE_LIMIT_RETRIES",
    "ARENA_DEBATE__RATE_LIMIT_MAX_WAIT",
    "ARENA_DEBATE__PROVIDER",
    "ARENA_DEBATE__ANTHROPIC_MODEL",
    "ARENA_DEBATE__ANTHROPIC_API_KEY",
    "ARENA_SERVICE__ANTHROPIC_API_KEY",
    "ARENA_SCAN__FILTERS__UNIVERSE__SECTORS",
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
    @pytest.mark.critical
    def test_app_settings_constructs_with_no_args(self) -> None:
        settings = AppSettings()
        assert settings is not None

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("scan.filters.options.top_n", 50),
            ("scan.filters.scoring.min_score", 0.0),
            ("scan.filters.universe.min_price", 10.0),
            ("scan.filters.options.min_dollar_volume", 10_000_000.0),
            ("scan.filters.universe.ohlcv_min_bars", 200),
            ("scan.filters.options.min_dte", 30),
            ("scan.filters.options.max_dte", 365),
            ("pricing.delta_target", 0.35),
            ("pricing.risk_free_rate_fallback", 0.05),
            ("service.yfinance_timeout", 15.0),
            ("service.max_concurrent_requests", 5),
        ],
    )
    def test_default_values(self, path: str, expected: object) -> None:
        """All nested default values are correct."""
        settings = AppSettings()
        actual = operator.attrgetter(path)(settings)
        if isinstance(expected, float):
            assert actual == pytest.approx(expected)
        else:
            assert actual == expected

    def test_service_groq_api_key_default(self) -> None:
        settings = AppSettings()
        assert settings.service.groq_api_key is None


# ---------------------------------------------------------------------------
# Env var overrides
# ---------------------------------------------------------------------------


class TestAppSettingsEnvOverrides:
    def test_env_override_scan_top_n(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARENA_SCAN__FILTERS__OPTIONS__TOP_N", "30")
        settings = AppSettings()
        assert settings.scan.filters.options.top_n == 30

    def test_env_override_pricing_delta_target(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARENA_PRICING__DELTA_TARGET", "0.40")
        settings = AppSettings()
        assert settings.pricing.delta_target == pytest.approx(0.40)

    def test_env_override_service_groq_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARENA_SERVICE__GROQ_API_KEY", "gsk_test_from_env")
        settings = AppSettings()
        assert settings.service.groq_api_key is not None
        assert settings.service.groq_api_key.get_secret_value() == "gsk_test_from_env"

    def test_env_override_type_coercion_string_to_int(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ARENA_SCAN__FILTERS__OPTIONS__TOP_N", "25")
        settings = AppSettings()
        assert settings.scan.filters.options.top_n == 25
        assert isinstance(settings.scan.filters.options.top_n, int)

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
        settings = AppSettings(
            scan=ScanConfig(filters=ScanFilterSpec(options=OptionsFilters(top_n=25)))
        )
        assert settings.scan.filters.options.top_n == 25

    def test_constructor_override_pricing_delta_target(self) -> None:
        settings = AppSettings(pricing=PricingConfig(delta_target=0.40))
        assert settings.pricing.delta_target == pytest.approx(0.40)

    def test_constructor_override_service_groq_api_key(self) -> None:
        settings = AppSettings(service=ServiceConfig(groq_api_key="gsk_from_constructor"))
        assert settings.service.groq_api_key is not None
        assert settings.service.groq_api_key.get_secret_value() == "gsk_from_constructor"

    def test_constructor_takes_priority_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ARENA_SCAN__FILTERS__OPTIONS__TOP_N", "30")
        settings = AppSettings(
            scan=ScanConfig(filters=ScanFilterSpec(options=OptionsFilters(top_n=99)))
        )
        assert settings.scan.filters.options.top_n == 99


# ---------------------------------------------------------------------------
# DebateConfig defaults
# ---------------------------------------------------------------------------


class TestDebateConfigDefaults:
    """Tests for DebateConfig default values and AppSettings integration."""

    def test_debate_config_constructs_with_defaults(self) -> None:
        """DebateConfig() constructs with all production defaults."""
        config = DebateConfig()
        assert config.model == "llama-3.3-70b-versatile"
        assert config.api_key is None
        assert config.agent_timeout == pytest.approx(60.0)
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
        assert settings.debate.model == "llama-3.3-70b-versatile"
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

    def test_env_override_debate_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__MODEL env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__MODEL", "llama-3.1-8b-instant")
        settings = AppSettings()
        assert settings.debate.model == "llama-3.1-8b-instant"

    def test_env_override_debate_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__API_KEY env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__API_KEY", "gsk_test_key_123")
        settings = AppSettings()
        assert settings.debate.api_key is not None
        assert settings.debate.api_key.get_secret_value() == "gsk_test_key_123"

    def test_debate_api_key_default_is_none(self) -> None:
        """Default api_key is None."""
        settings = AppSettings()
        assert settings.debate.api_key is None

    @pytest.mark.parametrize(
        "field,bad_value,match",
        [
            ("temperature", float("nan"), "temperature must be finite"),
            ("temperature", float("inf"), "temperature must be finite"),
            ("agent_timeout", float("nan"), "timeout must be finite"),
            ("max_total_duration", float("nan"), "timeout must be finite"),
        ],
    )
    def test_debate_config_rejects_non_finite(
        self, field: str, bad_value: float, match: str
    ) -> None:
        """DebateConfig rejects NaN/Inf on numeric fields."""
        with pytest.raises(ValidationError, match=match):
            DebateConfig(**{field: bad_value})

    @pytest.mark.parametrize(
        "field,bad_value,match",
        [
            ("temperature", -0.1, "temperature must be in"),
            ("temperature", 2.1, "temperature must be in"),
            ("agent_timeout", 0.0, "timeout must be > 0"),
            ("agent_timeout", -1.0, "timeout must be > 0"),
            ("max_total_duration", 0.0, "timeout must be > 0"),
            ("num_ctx", 64, "num_ctx must be in"),
            ("num_ctx", 200_000, "num_ctx must be in"),
            ("retries", -1, "retries must be in"),
            ("retries", 6, "retries must be in"),
        ],
    )
    def test_debate_config_rejects_out_of_bounds(
        self, field: str, bad_value: object, match: str
    ) -> None:
        """DebateConfig rejects out-of-range values."""
        with pytest.raises(ValidationError, match=match):
            DebateConfig(**{field: bad_value})

    @pytest.mark.parametrize(
        "field,low,high",
        [
            ("temperature", 0.0, 2.0),
            ("num_ctx", 128, 131_072),
            ("retries", 0, 5),
        ],
    )
    def test_debate_config_accepts_boundaries(self, field: str, low: object, high: object) -> None:
        """DebateConfig accepts boundary values."""
        config_low = DebateConfig(**{field: low})
        assert getattr(config_low, field) == low
        config_high = DebateConfig(**{field: high})
        assert getattr(config_high, field) == high


# ---------------------------------------------------------------------------
# Pre-screening config fields (Epic 3)
# ---------------------------------------------------------------------------


class TestDebateConfigPreScreening:
    """Tests for min_recommendation_score (renamed from min_debate_score)."""

    def test_min_recommendation_score_default(self) -> None:
        """Default min_recommendation_score is 30.0."""
        config = DebateConfig()
        assert config.min_recommendation_score == pytest.approx(30.0)

    @pytest.mark.parametrize(
        "bad_value,match",
        [
            (101.0, "min_recommendation_score must be in"),
            (-1.0, "min_recommendation_score must be in"),
            (float("nan"), "min_recommendation_score must be finite"),
            (float("inf"), "min_recommendation_score must be finite"),
        ],
    )
    def test_rejects_invalid_min_recommendation_score(
        self, bad_value: float, match: str
    ) -> None:
        """min_recommendation_score rejects out-of-range and non-finite values."""
        with pytest.raises(ValidationError, match=match):
            DebateConfig(min_recommendation_score=bad_value)

    def test_env_override_min_recommendation_score(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ARENA_DEBATE__MIN_RECOMMENDATION_SCORE env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__MIN_RECOMMENDATION_SCORE", "50.0")
        settings = AppSettings()
        assert settings.debate.min_recommendation_score == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Rate limit config fields
# ---------------------------------------------------------------------------


class TestDebateConfigRateLimit:
    """Tests for rate-limit resilience config fields on DebateConfig."""

    @pytest.mark.parametrize(
        "field,expected",
        [
            ("batch_ticker_delay", 5.0),
            ("rate_limit_retries", 3),
            ("rate_limit_max_wait", 30.0),
        ],
    )
    def test_rate_limit_defaults(self, field: str, expected: object) -> None:
        """Rate-limit fields have correct production defaults."""
        config = DebateConfig()
        actual = getattr(config, field)
        if isinstance(expected, float):
            assert actual == pytest.approx(expected)
        else:
            assert actual == expected

    @pytest.mark.parametrize(
        "field,bad_value,match",
        [
            ("batch_ticker_delay", float("nan"), "delay must be finite"),
            ("batch_ticker_delay", -0.5, "delay must be >= 0"),
            ("rate_limit_retries", -1, "rate_limit_retries must be in"),
            ("rate_limit_retries", 11, "rate_limit_retries must be in"),
            ("rate_limit_max_wait", 0.0, "rate_limit_max_wait must be > 0"),
            ("rate_limit_max_wait", -5.0, "rate_limit_max_wait must be > 0"),
            ("rate_limit_max_wait", float("nan"), "rate_limit_max_wait must be finite"),
            ("rate_limit_max_wait", float("inf"), "rate_limit_max_wait must be finite"),
        ],
    )
    def test_rate_limit_rejects_invalid(self, field: str, bad_value: object, match: str) -> None:
        """Rate-limit fields reject non-finite and out-of-range values."""
        with pytest.raises(ValidationError, match=match):
            DebateConfig(**{field: bad_value})

    @pytest.mark.parametrize(
        "field,value",
        [
            ("batch_ticker_delay", 0.0),
            ("rate_limit_retries", 0),
            ("rate_limit_retries", 10),
        ],
    )
    def test_rate_limit_accepts_boundaries(self, field: str, value: object) -> None:
        """Rate-limit fields accept valid boundary values."""
        config = DebateConfig(**{field: value})
        assert getattr(config, field) == value

    # --- Env var overrides ---

    def test_env_override_batch_ticker_delay(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__BATCH_TICKER_DELAY env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__BATCH_TICKER_DELAY", "1.0")
        settings = AppSettings()
        assert settings.debate.batch_ticker_delay == pytest.approx(1.0)

    def test_env_override_rate_limit_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__RATE_LIMIT_RETRIES env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__RATE_LIMIT_RETRIES", "0")
        settings = AppSettings()
        assert settings.debate.rate_limit_retries == 0

    def test_env_override_rate_limit_max_wait(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__RATE_LIMIT_MAX_WAIT env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__RATE_LIMIT_MAX_WAIT", "60.0")
        settings = AppSettings()
        assert settings.debate.rate_limit_max_wait == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# ScanConfig.filters.universe.sectors field and alias validation
# ---------------------------------------------------------------------------


class TestScanConfigSectors:
    def test_sectors_default_empty(self) -> None:
        """UniverseFilters.sectors defaults to empty list."""
        config = ScanConfig()
        assert config.filters.universe.sectors == []

    def test_sectors_accepts_canonical_enum_values(self) -> None:
        """Canonical GICSSector enum instances pass through."""
        config = ScanConfig(
            filters=ScanFilterSpec(
                universe=UniverseFilters(
                    sectors=[GICSSector.INFORMATION_TECHNOLOGY, GICSSector.ENERGY]
                )
            )
        )
        assert config.filters.universe.sectors == [
            GICSSector.INFORMATION_TECHNOLOGY,
            GICSSector.ENERGY,
        ]

    def test_sectors_normalizes_short_names(self) -> None:
        """Short aliases like 'tech' resolve to canonical values."""
        config = ScanConfig(
            filters=ScanFilterSpec(universe=UniverseFilters(sectors=["tech", "healthcare"]))
        )
        assert config.filters.universe.sectors == [
            GICSSector.INFORMATION_TECHNOLOGY,
            GICSSector.HEALTH_CARE,
        ]

    def test_sectors_normalizes_lowercase_canonical(self) -> None:
        """Lowercase canonical names resolve correctly."""
        config = ScanConfig(
            filters=ScanFilterSpec(
                universe=UniverseFilters(sectors=["information technology", "energy"])
            )
        )
        assert config.filters.universe.sectors == [
            GICSSector.INFORMATION_TECHNOLOGY,
            GICSSector.ENERGY,
        ]

    def test_sectors_normalizes_hyphenated(self) -> None:
        """Hyphenated variants resolve correctly."""
        config = ScanConfig(
            filters=ScanFilterSpec(
                universe=UniverseFilters(sectors=["real-estate", "health-care"])
            )
        )
        assert config.filters.universe.sectors == [
            GICSSector.REAL_ESTATE,
            GICSSector.HEALTH_CARE,
        ]

    def test_sectors_normalizes_underscored(self) -> None:
        """Underscored variants resolve correctly."""
        config = ScanConfig(
            filters=ScanFilterSpec(
                universe=UniverseFilters(sectors=["real_estate", "consumer_staples"])
            )
        )
        assert config.filters.universe.sectors == [
            GICSSector.REAL_ESTATE,
            GICSSector.CONSUMER_STAPLES,
        ]

    def test_sectors_accepts_canonical_string_values(self) -> None:
        """Canonical string values (mixed case) resolve via enum constructor."""
        config = ScanConfig(
            filters=ScanFilterSpec(
                universe=UniverseFilters(sectors=["Information Technology", "Energy"])
            )
        )
        assert config.filters.universe.sectors == [
            GICSSector.INFORMATION_TECHNOLOGY,
            GICSSector.ENERGY,
        ]

    def test_sectors_rejects_invalid_name(self) -> None:
        """Unknown sector string raises ValueError."""
        with pytest.raises(ValidationError, match="Unknown sector"):
            UniverseFilters(sectors=["nonexistent_sector"])

    def test_sectors_mixed_enum_and_string(self) -> None:
        """Mix of GICSSector enums and alias strings works."""
        config = ScanConfig(
            filters=ScanFilterSpec(universe=UniverseFilters(sectors=[GICSSector.ENERGY, "tech"]))
        )
        assert config.filters.universe.sectors == [
            GICSSector.ENERGY,
            GICSSector.INFORMATION_TECHNOLOGY,
        ]

    def test_sectors_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_SCAN__FILTERS__UNIVERSE__SECTORS env var works via JSON string."""
        monkeypatch.setenv("ARENA_SCAN__FILTERS__UNIVERSE__SECTORS", '["technology","energy"]')
        settings = AppSettings()
        assert settings.scan.filters.universe.sectors == [
            GICSSector.INFORMATION_TECHNOLOGY,
            GICSSector.ENERGY,
        ]


# ---------------------------------------------------------------------------
# LLMProvider enum
# ---------------------------------------------------------------------------


class TestLLMProviderEnum:
    def test_provider_values(self) -> None:
        """LLMProvider has exactly groq and anthropic members."""
        assert LLMProvider.GROQ == "groq"
        assert LLMProvider.ANTHROPIC == "anthropic"
        assert len(LLMProvider) == 2

    def test_provider_serialization_roundtrip(self) -> None:
        """StrEnum serializes to string and back."""
        assert LLMProvider("groq") is LLMProvider.GROQ
        assert LLMProvider("anthropic") is LLMProvider.ANTHROPIC


# ---------------------------------------------------------------------------
# DebateConfig — Anthropic fields
# ---------------------------------------------------------------------------


class TestDebateConfigAnthropicFields:
    def test_defaults_provider_groq(self) -> None:
        """Default provider is groq (backward compatible)."""
        config = DebateConfig()
        assert config.provider is LLMProvider.GROQ

    def test_anthropic_field_defaults(self) -> None:
        """Anthropic fields have correct defaults."""
        config = DebateConfig()
        assert config.anthropic_model == "claude-sonnet-4-5-20250929"
        assert config.anthropic_api_key is None
        assert config.enable_extended_thinking is False
        assert config.thinking_budget_tokens == 5000

    def test_backward_compatible_no_args(self) -> None:
        """Existing DebateConfig() with no args still works."""
        config = DebateConfig()
        assert config.model == "llama-3.3-70b-versatile"
        assert config.provider is LLMProvider.GROQ

    def test_thinking_budget_valid_range(self) -> None:
        """thinking_budget_tokens accepts values in [1024, 128000]."""
        config_low = DebateConfig(thinking_budget_tokens=1024)
        assert config_low.thinking_budget_tokens == 1024
        config_high = DebateConfig(thinking_budget_tokens=128_000)
        assert config_high.thinking_budget_tokens == 128_000

    def test_thinking_budget_too_low(self) -> None:
        """thinking_budget_tokens rejects values below 1024."""
        with pytest.raises(ValidationError, match="thinking_budget_tokens must be in"):
            DebateConfig(thinking_budget_tokens=512)

    def test_thinking_budget_too_high(self) -> None:
        """thinking_budget_tokens rejects values above 128000."""
        with pytest.raises(ValidationError, match="thinking_budget_tokens must be in"):
            DebateConfig(thinking_budget_tokens=200_000)

    def test_thinking_budget_nan_rejected(self) -> None:
        """thinking_budget_tokens rejects NaN (Pydantic int coercion rejects non-finite)."""
        with pytest.raises(ValidationError, match="finite"):
            DebateConfig(thinking_budget_tokens=float("nan"))  # type: ignore[arg-type]

    def test_env_var_provider_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__PROVIDER=anthropic overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__PROVIDER", "anthropic")
        settings = AppSettings()
        assert settings.debate.provider is LLMProvider.ANTHROPIC

    def test_env_var_anthropic_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__ANTHROPIC_API_KEY env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__ANTHROPIC_API_KEY", "sk-ant-test-key")
        settings = AppSettings()
        assert settings.debate.anthropic_api_key is not None
        assert settings.debate.anthropic_api_key.get_secret_value() == "sk-ant-test-key"

    def test_service_config_anthropic_api_key(self) -> None:
        """ServiceConfig has anthropic_api_key field defaulting to None."""
        config = ServiceConfig()
        assert config.anthropic_api_key is None

    def test_service_config_anthropic_api_key_set(self) -> None:
        """ServiceConfig.anthropic_api_key can be set."""
        config = ServiceConfig(anthropic_api_key="sk-ant-test")
        assert config.anthropic_api_key is not None
        assert config.anthropic_api_key.get_secret_value() == "sk-ant-test"

    def test_service_anthropic_api_key_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_SERVICE__ANTHROPIC_API_KEY env var works."""
        monkeypatch.setenv("ARENA_SERVICE__ANTHROPIC_API_KEY", "sk-ant-svc")
        settings = AppSettings()
        assert settings.service.anthropic_api_key is not None
        assert settings.service.anthropic_api_key.get_secret_value() == "sk-ant-svc"

    def test_provider_string_coercion(self) -> None:
        """String 'anthropic' is coerced to LLMProvider.ANTHROPIC."""
        config = DebateConfig(provider="anthropic")  # type: ignore[arg-type]
        assert config.provider is LLMProvider.ANTHROPIC
