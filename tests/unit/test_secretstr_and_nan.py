"""Tests for SecretStr migration and NaN/Inf pricing guards.

SecretStr tests:
  - repr() hides plaintext API keys
  - model_dump() does not expose plaintext keys
  - .get_secret_value() returns the actual key
  - Config with None keys works fine

NaN/Inf pricing guard tests:
  - validate_positive_inputs rejects NaN/Inf with descriptive messages
  - american_greeks rejects non-finite sigma
  - Normal inputs still work correctly
"""

import math

import pytest
from pydantic import SecretStr

from options_arena.models.config import DebateConfig, ServiceConfig
from options_arena.models.enums import OptionType
from options_arena.pricing._common import validate_positive_inputs
from options_arena.pricing.american import american_greeks

# ---------------------------------------------------------------------------
# SecretStr — ServiceConfig
# ---------------------------------------------------------------------------


class TestServiceConfigSecretStr:
    """Tests for SecretStr on ServiceConfig API key fields."""

    def test_repr_hides_groq_api_key(self) -> None:
        """repr() shows SecretStr('**********'), not the actual key."""
        config = ServiceConfig(groq_api_key=SecretStr("sk-test-secret"))
        config_repr = repr(config)
        assert "sk-test-secret" not in config_repr
        assert "**********" in config_repr

    def test_repr_hides_fred_api_key(self) -> None:
        """repr() shows SecretStr('**********'), not the actual FRED key."""
        config = ServiceConfig(fred_api_key=SecretStr("fred-secret-key"))
        config_repr = repr(config)
        assert "fred-secret-key" not in config_repr
        assert "**********" in config_repr

    def test_model_dump_does_not_expose_plaintext_groq_key(self) -> None:
        """model_dump() does NOT expose plaintext keys."""
        config = ServiceConfig(groq_api_key=SecretStr("sk-test-secret"))
        dumped = config.model_dump()
        # SecretStr returns the SecretStr object in model_dump() — verify it's not raw str
        assert "sk-test-secret" not in str(dumped["groq_api_key"])

    def test_model_dump_does_not_expose_plaintext_fred_key(self) -> None:
        """model_dump() does NOT expose plaintext FRED keys."""
        config = ServiceConfig(fred_api_key=SecretStr("fred-secret-key"))
        dumped = config.model_dump()
        assert "fred-secret-key" not in str(dumped["fred_api_key"])

    def test_get_secret_value_returns_actual_groq_key(self) -> None:
        """.get_secret_value() returns the actual key."""
        config = ServiceConfig(groq_api_key=SecretStr("sk-test-secret"))
        assert config.groq_api_key is not None
        assert config.groq_api_key.get_secret_value() == "sk-test-secret"

    def test_get_secret_value_returns_actual_fred_key(self) -> None:
        """.get_secret_value() returns the actual FRED key."""
        config = ServiceConfig(fred_api_key=SecretStr("fred-secret-key"))
        assert config.fred_api_key is not None
        assert config.fred_api_key.get_secret_value() == "fred-secret-key"

    def test_none_keys_work_fine(self) -> None:
        """Config with None keys works fine."""
        config = ServiceConfig()
        assert config.groq_api_key is None
        assert config.fred_api_key is None


# ---------------------------------------------------------------------------
# SecretStr — DebateConfig
# ---------------------------------------------------------------------------


class TestDebateConfigSecretStr:
    """Tests for SecretStr on DebateConfig.api_key field."""

    def test_repr_hides_api_key(self) -> None:
        """repr() shows SecretStr('**********'), not the actual key."""
        config = DebateConfig(api_key=SecretStr("gsk-debate-secret"))
        config_repr = repr(config)
        assert "gsk-debate-secret" not in config_repr
        assert "**********" in config_repr

    def test_model_dump_does_not_expose_plaintext(self) -> None:
        """model_dump() does NOT expose plaintext keys."""
        config = DebateConfig(api_key=SecretStr("gsk-debate-secret"))
        dumped = config.model_dump()
        assert "gsk-debate-secret" not in str(dumped["api_key"])

    def test_get_secret_value_returns_actual_key(self) -> None:
        """.get_secret_value() returns the actual key."""
        config = DebateConfig(api_key=SecretStr("gsk-debate-secret"))
        assert config.api_key is not None
        assert config.api_key.get_secret_value() == "gsk-debate-secret"

    def test_none_key_works_fine(self) -> None:
        """Config with None key works fine."""
        config = DebateConfig()
        assert config.api_key is None


# ---------------------------------------------------------------------------
# NaN/Inf — validate_positive_inputs
# ---------------------------------------------------------------------------


class TestValidatePositiveInputsNanInf:
    """Tests for NaN/Inf guards in validate_positive_inputs."""

    def test_nan_s_raises_mentioning_s(self) -> None:
        """NaN S raises ValueError mentioning 'S'."""
        with pytest.raises(ValueError, match="S must be a finite number"):
            validate_positive_inputs(float("nan"), 100.0, 1.0, 0.05)

    def test_inf_k_raises_mentioning_k(self) -> None:
        """Inf K raises ValueError mentioning 'K'."""
        with pytest.raises(ValueError, match="K must be a finite number"):
            validate_positive_inputs(100.0, float("inf"), 1.0, 0.05)

    def test_neg_inf_t_raises_mentioning_t(self) -> None:
        """-Inf T raises ValueError mentioning 'T'."""
        with pytest.raises(ValueError, match="T must be a finite number"):
            validate_positive_inputs(100.0, 100.0, float("-inf"), 0.05)

    def test_nan_r_raises_mentioning_r(self) -> None:
        """NaN r raises ValueError mentioning 'r'."""
        with pytest.raises(ValueError, match="r must be a finite number"):
            validate_positive_inputs(100.0, 100.0, 1.0, float("nan"))

    def test_inf_s_raises_mentioning_s(self) -> None:
        """Inf S raises ValueError mentioning 'S'."""
        with pytest.raises(ValueError, match="S must be a finite number"):
            validate_positive_inputs(float("inf"), 100.0, 1.0, 0.05)

    def test_neg_inf_k_raises_mentioning_k(self) -> None:
        """-Inf K raises ValueError mentioning 'K'."""
        with pytest.raises(ValueError, match="K must be a finite number"):
            validate_positive_inputs(100.0, float("-inf"), 1.0, 0.05)

    def test_normal_inputs_pass(self) -> None:
        """Normal positive inputs pass without error."""
        validate_positive_inputs(100.0, 100.0, 1.0, 0.05)

    def test_normal_inputs_s_k_only_pass(self) -> None:
        """Normal S, K only (no T, r) pass without error."""
        validate_positive_inputs(100.0, 100.0)

    def test_positivity_check_still_works_for_s(self) -> None:
        """S <= 0 still raises after finite check passes."""
        with pytest.raises(ValueError, match="S.*must be > 0"):
            validate_positive_inputs(-1.0, 100.0)

    def test_positivity_check_still_works_for_k(self) -> None:
        """K <= 0 still raises after finite check passes."""
        with pytest.raises(ValueError, match="K.*must be > 0"):
            validate_positive_inputs(100.0, 0.0)


# ---------------------------------------------------------------------------
# NaN/Inf — american_greeks sigma guard
# ---------------------------------------------------------------------------


class TestAmericanGreeksSigmaGuard:
    """Tests for NaN/Inf sigma guard in american_greeks."""

    def test_nan_sigma_raises_mentioning_sigma(self) -> None:
        """NaN sigma raises ValueError mentioning 'sigma'."""
        with pytest.raises(ValueError, match="sigma must be a finite number"):
            american_greeks(100.0, 100.0, 1.0, 0.05, 0.0, float("nan"), OptionType.CALL)

    def test_inf_sigma_raises_mentioning_sigma(self) -> None:
        """Inf sigma raises ValueError mentioning 'sigma'."""
        with pytest.raises(ValueError, match="sigma must be a finite number"):
            american_greeks(100.0, 100.0, 1.0, 0.05, 0.0, float("inf"), OptionType.CALL)

    def test_neg_inf_sigma_raises_mentioning_sigma(self) -> None:
        """-Inf sigma raises ValueError mentioning 'sigma'."""
        with pytest.raises(ValueError, match="sigma must be a finite number"):
            american_greeks(100.0, 100.0, 1.0, 0.05, 0.0, float("-inf"), OptionType.PUT)

    def test_normal_sigma_works(self) -> None:
        """Normal sigma produces valid OptionGreeks."""
        greeks = american_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.25, OptionType.CALL)
        assert math.isfinite(greeks.delta)
        assert math.isfinite(greeks.gamma)
        assert math.isfinite(greeks.theta)
        assert math.isfinite(greeks.vega)
        assert math.isfinite(greeks.rho)

    def test_zero_sigma_returns_boundary_greeks(self) -> None:
        """Sigma=0 returns boundary greeks (not an error)."""
        greeks = american_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.0, OptionType.CALL)
        # At the money with sigma=0, delta should be 0.0 (OTM boundary)
        assert greeks.delta == pytest.approx(0.0, abs=0.01) or greeks.delta == pytest.approx(
            1.0, abs=0.01
        )
