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

    def test_scan_top_n_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.filters.options.top_n == 50

    def test_scan_min_score_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.filters.scoring.min_score == pytest.approx(0.0)

    def test_scan_min_price_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.filters.universe.min_price == pytest.approx(10.0)

    def test_scan_min_dollar_volume_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.filters.options.min_dollar_volume == pytest.approx(10_000_000.0)

    def test_scan_ohlcv_min_bars_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.filters.universe.ohlcv_min_bars == 200

    def test_pricing_delta_target_default(self) -> None:
        settings = AppSettings()
        assert settings.pricing.delta_target == pytest.approx(0.35)

    def test_pricing_risk_free_rate_fallback_default(self) -> None:
        settings = AppSettings()
        assert settings.pricing.risk_free_rate_fallback == pytest.approx(0.05)

    def test_options_filters_min_dte_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.filters.options.min_dte == 30

    def test_options_filters_max_dte_default(self) -> None:
        settings = AppSettings()
        assert settings.scan.filters.options.max_dte == 365

    def test_service_groq_api_key_default(self) -> None:
        settings = AppSettings(_env_file=None)
        assert settings.service.groq_api_key is None

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
        settings = AppSettings(_env_file=None)
        assert settings.debate.api_key is None

    def test_debate_config_rejects_nan_temperature(self) -> None:
        """NaN temperature is rejected by validator."""
        with pytest.raises(ValidationError, match="temperature must be finite"):
            DebateConfig(temperature=float("nan"))

    def test_debate_config_rejects_inf_temperature(self) -> None:
        """Inf temperature is rejected by validator."""
        with pytest.raises(ValidationError, match="temperature must be finite"):
            DebateConfig(temperature=float("inf"))

    def test_debate_config_rejects_negative_temperature(self) -> None:
        """Negative temperature is rejected."""
        with pytest.raises(ValidationError, match="temperature must be in"):
            DebateConfig(temperature=-0.1)

    def test_debate_config_rejects_temperature_above_2(self) -> None:
        """Temperature > 2.0 is rejected."""
        with pytest.raises(ValidationError, match="temperature must be in"):
            DebateConfig(temperature=2.1)

    def test_debate_config_accepts_temperature_boundary(self) -> None:
        """Temperature 0.0 and 2.0 are accepted."""
        config_low = DebateConfig(temperature=0.0)
        assert config_low.temperature == pytest.approx(0.0)
        config_high = DebateConfig(temperature=2.0)
        assert config_high.temperature == pytest.approx(2.0)

    def test_debate_config_rejects_nan_agent_timeout(self) -> None:
        """NaN agent_timeout is rejected."""
        with pytest.raises(ValidationError, match="timeout must be finite"):
            DebateConfig(agent_timeout=float("nan"))

    def test_debate_config_rejects_zero_agent_timeout(self) -> None:
        """Zero agent_timeout is rejected (must be > 0)."""
        with pytest.raises(ValidationError, match="timeout must be > 0"):
            DebateConfig(agent_timeout=0.0)

    def test_debate_config_rejects_negative_agent_timeout(self) -> None:
        """Negative agent_timeout is rejected."""
        with pytest.raises(ValidationError, match="timeout must be > 0"):
            DebateConfig(agent_timeout=-1.0)

    def test_debate_config_rejects_nan_max_total_duration(self) -> None:
        """NaN max_total_duration is rejected."""
        with pytest.raises(ValidationError, match="timeout must be finite"):
            DebateConfig(max_total_duration=float("nan"))

    def test_debate_config_rejects_zero_max_total_duration(self) -> None:
        """Zero max_total_duration is rejected."""
        with pytest.raises(ValidationError, match="timeout must be > 0"):
            DebateConfig(max_total_duration=0.0)

    def test_debate_config_rejects_num_ctx_below_128(self) -> None:
        """num_ctx below 128 is rejected."""
        with pytest.raises(ValidationError, match="num_ctx must be in"):
            DebateConfig(num_ctx=64)

    def test_debate_config_rejects_num_ctx_above_131072(self) -> None:
        """num_ctx above 131072 is rejected."""
        with pytest.raises(ValidationError, match="num_ctx must be in"):
            DebateConfig(num_ctx=200_000)

    def test_debate_config_accepts_num_ctx_boundary(self) -> None:
        """num_ctx 128 and 131072 are accepted."""
        config_low = DebateConfig(num_ctx=128)
        assert config_low.num_ctx == 128
        config_high = DebateConfig(num_ctx=131_072)
        assert config_high.num_ctx == 131_072

    def test_debate_config_rejects_retries_below_0(self) -> None:
        """Negative retries rejected."""
        with pytest.raises(ValidationError, match="retries must be in"):
            DebateConfig(retries=-1)

    def test_debate_config_rejects_retries_above_5(self) -> None:
        """retries above 5 is rejected."""
        with pytest.raises(ValidationError, match="retries must be in"):
            DebateConfig(retries=6)

    def test_debate_config_accepts_retries_boundary(self) -> None:
        """retries 0 and 5 are accepted."""
        config_low = DebateConfig(retries=0)
        assert config_low.retries == 0
        config_high = DebateConfig(retries=5)
        assert config_high.retries == 5


# ---------------------------------------------------------------------------
# Pre-screening config fields (Epic 3)
# ---------------------------------------------------------------------------


class TestDebateConfigPreScreening:
    """Tests for min_debate_score, enable_volatility_agent, enable_rebuttal."""

    def test_min_debate_score_default(self) -> None:
        """Default min_debate_score is 30.0."""
        config = DebateConfig()
        assert config.min_debate_score == pytest.approx(30.0)

    def test_enable_volatility_agent_default(self) -> None:
        """Default enable_volatility_agent is False."""
        config = DebateConfig()
        assert config.enable_volatility_agent is False

    def test_enable_rebuttal_default(self) -> None:
        """Default enable_rebuttal is False."""
        config = DebateConfig()
        assert config.enable_rebuttal is False

    def test_rejects_min_debate_score_above_100(self) -> None:
        """min_debate_score > 100 is rejected."""
        with pytest.raises(ValidationError, match="min_debate_score must be in"):
            DebateConfig(min_debate_score=101.0)

    def test_rejects_min_debate_score_below_0(self) -> None:
        """Negative min_debate_score is rejected."""
        with pytest.raises(ValidationError, match="min_debate_score must be in"):
            DebateConfig(min_debate_score=-1.0)

    def test_rejects_min_debate_score_nan(self) -> None:
        """NaN min_debate_score is rejected."""
        with pytest.raises(ValidationError, match="min_debate_score must be finite"):
            DebateConfig(min_debate_score=float("nan"))

    def test_rejects_min_debate_score_inf(self) -> None:
        """Inf min_debate_score is rejected."""
        with pytest.raises(ValidationError, match="min_debate_score must be finite"):
            DebateConfig(min_debate_score=float("inf"))

    def test_env_override_min_debate_score(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__MIN_DEBATE_SCORE env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__MIN_DEBATE_SCORE", "50.0")
        settings = AppSettings()
        assert settings.debate.min_debate_score == pytest.approx(50.0)

    def test_env_override_enable_volatility_agent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__ENABLE_VOLATILITY_AGENT env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__ENABLE_VOLATILITY_AGENT", "true")
        settings = AppSettings()
        assert settings.debate.enable_volatility_agent is True


# ---------------------------------------------------------------------------
# Rate limit config fields
# ---------------------------------------------------------------------------


class TestDebateConfigRateLimit:
    """Tests for rate-limit resilience config fields on DebateConfig."""

    def test_phase1_batch_delay_default(self) -> None:
        """Default phase1_batch_delay is 1.0."""
        config = DebateConfig()
        assert config.phase1_batch_delay == pytest.approx(1.0)

    def test_batch_ticker_delay_default(self) -> None:
        """Default batch_ticker_delay is 5.0."""
        config = DebateConfig()
        assert config.batch_ticker_delay == pytest.approx(5.0)

    def test_rate_limit_retries_default(self) -> None:
        """Default rate_limit_retries is 3."""
        config = DebateConfig()
        assert config.rate_limit_retries == 3

    def test_rate_limit_max_wait_default(self) -> None:
        """Default rate_limit_max_wait is 30.0."""
        config = DebateConfig()
        assert config.rate_limit_max_wait == pytest.approx(30.0)

    def test_phase1_parallelism_default_is_2(self) -> None:
        """Default phase1_parallelism changed to 2 (free tier optimized)."""
        config = DebateConfig()
        assert config.phase1_parallelism == 2

    # --- Delay validation ---

    def test_rejects_negative_phase1_batch_delay(self) -> None:
        """Negative phase1_batch_delay is rejected."""
        with pytest.raises(ValidationError, match="delay must be >= 0"):
            DebateConfig(phase1_batch_delay=-1.0)

    def test_accepts_zero_phase1_batch_delay(self) -> None:
        """Zero delay is valid (disables delay)."""
        config = DebateConfig(phase1_batch_delay=0.0)
        assert config.phase1_batch_delay == pytest.approx(0.0)

    def test_rejects_nan_phase1_batch_delay(self) -> None:
        """NaN delay is rejected."""
        with pytest.raises(ValidationError, match="delay must be finite"):
            DebateConfig(phase1_batch_delay=float("nan"))

    def test_rejects_inf_phase1_batch_delay(self) -> None:
        """Inf delay is rejected."""
        with pytest.raises(ValidationError, match="delay must be finite"):
            DebateConfig(phase1_batch_delay=float("inf"))

    def test_rejects_negative_batch_ticker_delay(self) -> None:
        """Negative batch_ticker_delay is rejected."""
        with pytest.raises(ValidationError, match="delay must be >= 0"):
            DebateConfig(batch_ticker_delay=-0.5)

    def test_accepts_zero_batch_ticker_delay(self) -> None:
        """Zero batch_ticker_delay is valid."""
        config = DebateConfig(batch_ticker_delay=0.0)
        assert config.batch_ticker_delay == pytest.approx(0.0)

    def test_rejects_nan_batch_ticker_delay(self) -> None:
        """NaN batch_ticker_delay is rejected."""
        with pytest.raises(ValidationError, match="delay must be finite"):
            DebateConfig(batch_ticker_delay=float("nan"))

    # --- Rate limit retries validation ---

    def test_rejects_negative_rate_limit_retries(self) -> None:
        """Negative rate_limit_retries is rejected."""
        with pytest.raises(ValidationError, match="rate_limit_retries must be in"):
            DebateConfig(rate_limit_retries=-1)

    def test_rejects_rate_limit_retries_above_10(self) -> None:
        """rate_limit_retries above 10 is rejected."""
        with pytest.raises(ValidationError, match="rate_limit_retries must be in"):
            DebateConfig(rate_limit_retries=11)

    def test_accepts_rate_limit_retries_boundary(self) -> None:
        """rate_limit_retries 0 and 10 are accepted."""
        config_low = DebateConfig(rate_limit_retries=0)
        assert config_low.rate_limit_retries == 0
        config_high = DebateConfig(rate_limit_retries=10)
        assert config_high.rate_limit_retries == 10

    # --- Rate limit max wait validation ---

    def test_rejects_zero_rate_limit_max_wait(self) -> None:
        """Zero rate_limit_max_wait is rejected (must be > 0)."""
        with pytest.raises(ValidationError, match="rate_limit_max_wait must be > 0"):
            DebateConfig(rate_limit_max_wait=0.0)

    def test_rejects_negative_rate_limit_max_wait(self) -> None:
        """Negative rate_limit_max_wait is rejected."""
        with pytest.raises(ValidationError, match="rate_limit_max_wait must be > 0"):
            DebateConfig(rate_limit_max_wait=-5.0)

    def test_rejects_nan_rate_limit_max_wait(self) -> None:
        """NaN rate_limit_max_wait is rejected."""
        with pytest.raises(ValidationError, match="rate_limit_max_wait must be finite"):
            DebateConfig(rate_limit_max_wait=float("nan"))

    def test_rejects_inf_rate_limit_max_wait(self) -> None:
        """Inf rate_limit_max_wait is rejected."""
        with pytest.raises(ValidationError, match="rate_limit_max_wait must be finite"):
            DebateConfig(rate_limit_max_wait=float("inf"))

    # --- Env var overrides ---

    def test_env_override_phase1_batch_delay(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__PHASE1_BATCH_DELAY env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__PHASE1_BATCH_DELAY", "0.0")
        settings = AppSettings()
        assert settings.debate.phase1_batch_delay == pytest.approx(0.0)

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

    def test_env_override_phase1_parallelism(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_DEBATE__PHASE1_PARALLELISM env var overrides default to paid tier value."""
        monkeypatch.setenv("ARENA_DEBATE__PHASE1_PARALLELISM", "4")
        settings = AppSettings()
        assert settings.debate.phase1_parallelism == 4


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

    def test_provider_is_str_enum(self) -> None:
        """LLMProvider is a StrEnum subclass."""
        from enum import StrEnum

        assert issubclass(LLMProvider, StrEnum)

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
