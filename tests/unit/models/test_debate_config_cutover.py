"""Tests for DebateConfig cutover — dead field removal and new fields.

Issue #664: Remove 4 dead fields (enable_volatility_agent, enable_rebuttal,
phase1_parallelism, phase1_batch_delay), rename min_debate_score to
min_recommendation_score, add 5 new fields for the recommendation system.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from options_arena.models import AppSettings, DebateConfig


class TestDebateConfigCutover:
    """Verify dead fields removed and new fields added correctly."""

    # -- Dead fields no longer exist as model attributes --

    def test_dead_field_enable_volatility_agent_not_on_model(self) -> None:
        """Removed field enable_volatility_agent does not exist on DebateConfig."""
        config = DebateConfig()
        assert not hasattr(config, "enable_volatility_agent")

    def test_dead_field_enable_rebuttal_not_on_model(self) -> None:
        """Removed field enable_rebuttal does not exist on DebateConfig."""
        config = DebateConfig()
        assert not hasattr(config, "enable_rebuttal")

    def test_dead_field_phase1_parallelism_not_on_model(self) -> None:
        """Removed field phase1_parallelism does not exist on DebateConfig."""
        config = DebateConfig()
        assert not hasattr(config, "phase1_parallelism")

    def test_dead_field_phase1_batch_delay_not_on_model(self) -> None:
        """Removed field phase1_batch_delay does not exist on DebateConfig."""
        config = DebateConfig()
        assert not hasattr(config, "phase1_batch_delay")

    def test_dead_field_min_debate_score_not_on_model(self) -> None:
        """Removed field min_debate_score does not exist on DebateConfig (renamed)."""
        config = DebateConfig()
        assert not hasattr(config, "min_debate_score")

    # -- New field defaults --

    def test_new_fields_defaults(self) -> None:
        """Verify new fields have correct defaults."""
        config = DebateConfig()
        assert config.synthesis_timeout == pytest.approx(90.0)
        assert config.recommendation_protocol == "unified_v1"
        assert config.min_recommendation_score == pytest.approx(30.0)
        assert config.desk_parallelism == 6
        assert config.disabled_desks == []

    # -- NaN/Inf defense --

    def test_synthesis_timeout_nan_rejected(self) -> None:
        """Verify NaN defense on synthesis_timeout."""
        with pytest.raises(ValidationError, match="synthesis_timeout must be finite"):
            DebateConfig(synthesis_timeout=float("nan"))

    def test_synthesis_timeout_inf_rejected(self) -> None:
        """Verify Inf defense on synthesis_timeout."""
        with pytest.raises(ValidationError, match="synthesis_timeout must be finite"):
            DebateConfig(synthesis_timeout=float("inf"))

    def test_synthesis_timeout_zero_rejected(self) -> None:
        """Verify synthesis_timeout must be positive."""
        with pytest.raises(ValidationError, match="synthesis_timeout must be > 0"):
            DebateConfig(synthesis_timeout=0.0)

    def test_synthesis_timeout_negative_rejected(self) -> None:
        """Verify synthesis_timeout must be positive."""
        with pytest.raises(ValidationError, match="synthesis_timeout must be > 0"):
            DebateConfig(synthesis_timeout=-1.0)

    def test_min_recommendation_score_nan_rejected(self) -> None:
        """Verify NaN defense on min_recommendation_score."""
        with pytest.raises(
            ValidationError, match="min_recommendation_score must be finite"
        ):
            DebateConfig(min_recommendation_score=float("nan"))

    def test_min_recommendation_score_inf_rejected(self) -> None:
        """Verify Inf defense on min_recommendation_score."""
        with pytest.raises(
            ValidationError, match="min_recommendation_score must be finite"
        ):
            DebateConfig(min_recommendation_score=float("inf"))

    def test_min_recommendation_score_above_100_rejected(self) -> None:
        """Verify min_recommendation_score range [0, 100]."""
        with pytest.raises(
            ValidationError, match="min_recommendation_score must be in"
        ):
            DebateConfig(min_recommendation_score=101.0)

    def test_min_recommendation_score_below_0_rejected(self) -> None:
        """Verify min_recommendation_score range [0, 100]."""
        with pytest.raises(
            ValidationError, match="min_recommendation_score must be in"
        ):
            DebateConfig(min_recommendation_score=-1.0)

    def test_min_recommendation_score_zero_accepted(self) -> None:
        """min_recommendation_score=0.0 is valid (disables score gate)."""
        config = DebateConfig(min_recommendation_score=0.0)
        assert config.min_recommendation_score == pytest.approx(0.0)

    # -- desk_parallelism range --

    def test_desk_parallelism_range_low(self) -> None:
        """desk_parallelism=0 rejected (would cause deadlock)."""
        with pytest.raises(ValidationError, match="desk_parallelism must be in"):
            DebateConfig(desk_parallelism=0)

    def test_desk_parallelism_range_high(self) -> None:
        """desk_parallelism=13 rejected (excessive)."""
        with pytest.raises(ValidationError, match="desk_parallelism must be in"):
            DebateConfig(desk_parallelism=13)

    def test_desk_parallelism_boundary_1(self) -> None:
        """desk_parallelism=1 accepted (minimum)."""
        config = DebateConfig(desk_parallelism=1)
        assert config.desk_parallelism == 1

    def test_desk_parallelism_boundary_12(self) -> None:
        """desk_parallelism=12 accepted (maximum)."""
        config = DebateConfig(desk_parallelism=12)
        assert config.desk_parallelism == 12

    # -- disabled_desks --

    def test_disabled_desks_accepts_list(self) -> None:
        """disabled_desks accepts string list."""
        config = DebateConfig(disabled_desks=["risk", "contrarian"])
        assert len(config.disabled_desks) == 2
        assert "risk" in config.disabled_desks
        assert "contrarian" in config.disabled_desks

    def test_disabled_desks_empty_default(self) -> None:
        """disabled_desks defaults to empty list."""
        config = DebateConfig()
        assert config.disabled_desks == []

    # -- recommendation_protocol --

    def test_recommendation_protocol_custom(self) -> None:
        """recommendation_protocol accepts arbitrary string."""
        config = DebateConfig(recommendation_protocol="legacy_v0")
        assert config.recommendation_protocol == "legacy_v0"

    # -- env var prefix preserved --

    def test_env_var_prefix_preserved(self) -> None:
        """ARENA_DEBATE__ prefix still works via AppSettings."""
        settings = AppSettings(debate=DebateConfig(desk_parallelism=4))
        assert settings.debate.desk_parallelism == 4

    def test_env_var_synthesis_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ARENA_DEBATE__SYNTHESIS_TIMEOUT env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__SYNTHESIS_TIMEOUT", "120.0")
        settings = AppSettings()
        assert settings.debate.synthesis_timeout == pytest.approx(120.0)

    def test_env_var_desk_parallelism(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ARENA_DEBATE__DESK_PARALLELISM env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__DESK_PARALLELISM", "3")
        settings = AppSettings()
        assert settings.debate.desk_parallelism == 3

    def test_env_var_recommendation_protocol(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ARENA_DEBATE__RECOMMENDATION_PROTOCOL env var overrides default."""
        monkeypatch.setenv("ARENA_DEBATE__RECOMMENDATION_PROTOCOL", "unified_v2")
        settings = AppSettings()
        assert settings.debate.recommendation_protocol == "unified_v2"
