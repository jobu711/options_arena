"""Unit tests for LearningConfig and its integration with AppSettings.

Tests:
- Default values (apply_tuned_weights=False, min_confidence=0.7)
- Environment variable override via monkeypatch
- min_confidence validation (finite, [0.0, 1.0])
- Boundary values
"""

import pytest
from pydantic import ValidationError

from options_arena.models.config import AppSettings, LearningConfig

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestLearningConfigDefaults:
    """Tests for LearningConfig default values."""

    @pytest.mark.critical
    def test_defaults(self) -> None:
        """apply_tuned_weights=False, min_confidence=0.7."""
        config = LearningConfig()
        assert config.apply_tuned_weights is False
        assert config.min_confidence == pytest.approx(0.7, abs=1e-9)

    def test_explicit_construction(self) -> None:
        """Explicit values override defaults."""
        config = LearningConfig(apply_tuned_weights=True, min_confidence=0.5)
        assert config.apply_tuned_weights is True
        assert config.min_confidence == pytest.approx(0.5, abs=1e-9)

    def test_app_settings_has_learning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AppSettings includes learning config with correct defaults."""
        monkeypatch.delenv("ARENA_LEARNING__APPLY_TUNED_WEIGHTS", raising=False)
        monkeypatch.delenv("ARENA_LEARNING__MIN_CONFIDENCE", raising=False)
        settings = AppSettings()
        assert hasattr(settings, "learning")
        assert isinstance(settings.learning, LearningConfig)
        assert settings.learning.apply_tuned_weights is False
        assert settings.learning.min_confidence == pytest.approx(0.7, abs=1e-9)


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------


class TestLearningConfigEnvOverride:
    """Tests for ARENA_LEARNING__* env var overrides."""

    def test_env_override_apply_tuned_weights(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_LEARNING__APPLY_TUNED_WEIGHTS=true sets flag."""
        monkeypatch.setenv("ARENA_LEARNING__APPLY_TUNED_WEIGHTS", "true")
        settings = AppSettings()
        assert settings.learning.apply_tuned_weights is True

    def test_env_override_min_confidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_LEARNING__MIN_CONFIDENCE=0.9 overrides default."""
        monkeypatch.setenv("ARENA_LEARNING__MIN_CONFIDENCE", "0.9")
        settings = AppSettings()
        assert settings.learning.min_confidence == pytest.approx(0.9, abs=1e-9)

    def test_env_override_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ARENA_LEARNING__APPLY_TUNED_WEIGHTS=false keeps flag off."""
        monkeypatch.setenv("ARENA_LEARNING__APPLY_TUNED_WEIGHTS", "false")
        settings = AppSettings()
        assert settings.learning.apply_tuned_weights is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestLearningConfigValidation:
    """Tests for min_confidence field validation."""

    def test_min_confidence_nan_rejected(self) -> None:
        """NaN min_confidence rejected by isfinite() check."""
        with pytest.raises(ValidationError, match="finite"):
            LearningConfig(min_confidence=float("nan"))

    def test_min_confidence_inf_rejected(self) -> None:
        """Inf min_confidence rejected by isfinite() check."""
        with pytest.raises(ValidationError, match="finite"):
            LearningConfig(min_confidence=float("inf"))

    def test_min_confidence_negative_rejected(self) -> None:
        """Negative min_confidence rejected by range check."""
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            LearningConfig(min_confidence=-0.1)

    def test_min_confidence_above_one_rejected(self) -> None:
        """min_confidence > 1.0 rejected by range check."""
        with pytest.raises(ValidationError, match=r"\[0\.0, 1\.0\]"):
            LearningConfig(min_confidence=1.1)

    def test_min_confidence_zero_accepted(self) -> None:
        """min_confidence=0.0 is a valid boundary value."""
        config = LearningConfig(min_confidence=0.0)
        assert config.min_confidence == pytest.approx(0.0, abs=1e-9)

    def test_min_confidence_one_accepted(self) -> None:
        """min_confidence=1.0 is a valid boundary value."""
        config = LearningConfig(min_confidence=1.0)
        assert config.min_confidence == pytest.approx(1.0, abs=1e-9)

    def test_min_confidence_neg_inf_rejected(self) -> None:
        """Negative infinity min_confidence rejected."""
        with pytest.raises(ValidationError, match="finite"):
            LearningConfig(min_confidence=float("-inf"))

    def test_json_roundtrip(self) -> None:
        """LearningConfig survives JSON serialization roundtrip."""
        config = LearningConfig(apply_tuned_weights=True, min_confidence=0.85)
        json_str = config.model_dump_json()
        restored = LearningConfig.model_validate_json(json_str)
        assert restored.apply_tuned_weights is True
        assert restored.min_confidence == pytest.approx(0.85, abs=1e-9)
