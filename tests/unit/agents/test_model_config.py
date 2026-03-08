"""Tests for model_config.py — multi-provider model building.

Tests cover:
  - build_debate_model dispatches to Groq (default) and Anthropic
  - _resolve_api_key priority: config > env > None (Groq legacy)
  - _resolve_groq_api_key priority: config > env > ValueError
  - _resolve_anthropic_api_key priority: config > env > ValueError
  - _build_anthropic_model returns AnthropicModel with correct model name
  - _build_groq_model returns GroqModel (existing behavior preserved)
"""

from __future__ import annotations

import pytest
from pydantic_ai import models
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.groq import GroqModel

from options_arena.agents.model_config import (
    _resolve_anthropic_api_key,
    _resolve_api_key,
    _resolve_groq_api_key,
    build_debate_model,
)
from options_arena.models import DebateConfig, LLMProvider

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# _resolve_api_key (legacy)
# ---------------------------------------------------------------------------


class TestResolveApiKey:
    """Tests for _resolve_api_key priority resolution."""

    def test_returns_none_when_no_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when config is None and no env var set."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(api_key=None)
        assert _resolve_api_key(config) is None

    def test_config_key_takes_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config api_key takes priority over env var."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_env_key")
        config = DebateConfig(api_key="gsk_config_key")
        assert _resolve_api_key(config) == "gsk_config_key"

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GROQ_API_KEY env var is used when config key is None."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_env_key")
        config = DebateConfig(api_key=None)
        assert _resolve_api_key(config) == "gsk_env_key"


# ---------------------------------------------------------------------------
# _resolve_groq_api_key
# ---------------------------------------------------------------------------


class TestResolveGroqApiKey:
    """Tests for _resolve_groq_api_key priority resolution."""

    def test_config_key_takes_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config api_key takes priority over env var."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_env_key")
        config = DebateConfig(api_key="gsk_config_key")
        assert _resolve_groq_api_key(config) == "gsk_config_key"

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GROQ_API_KEY env var is used when config key is None."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_env_key")
        config = DebateConfig(api_key=None)
        assert _resolve_groq_api_key(config) == "gsk_env_key"

    def test_raises_when_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises ValueError when no Groq API key is available."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(api_key=None)
        with pytest.raises(ValueError, match="Groq API key required"):
            _resolve_groq_api_key(config)


# ---------------------------------------------------------------------------
# _resolve_anthropic_api_key
# ---------------------------------------------------------------------------


class TestResolveAnthropicApiKey:
    """Tests for _resolve_anthropic_api_key priority resolution."""

    def test_config_key_takes_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config anthropic_api_key takes priority over env var."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(anthropic_api_key="sk-ant-config-key")
        assert _resolve_anthropic_api_key(config) == "sk-ant-config-key"

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ANTHROPIC_API_KEY env var is used when config key is None."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(anthropic_api_key=None)
        assert _resolve_anthropic_api_key(config) == "sk-ant-env-key"

    def test_raises_when_no_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raises ValueError when no Anthropic API key is available."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(anthropic_api_key=None)
        with pytest.raises(ValueError, match="Anthropic API key required"):
            _resolve_anthropic_api_key(config)


# ---------------------------------------------------------------------------
# build_debate_model (Groq — existing behavior)
# ---------------------------------------------------------------------------


class TestBuildDebateModel:
    """Tests for build_debate_model (Groq-only)."""

    def test_returns_groq_model_with_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_debate_model returns a GroqModel when API key is provided."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(api_key="gsk_test_key_123")
        model = build_debate_model(config)
        assert isinstance(model, GroqModel)

    def test_uses_env_var_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_debate_model uses GROQ_API_KEY env var when config key is None."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_env_key_456")
        config = DebateConfig(api_key=None)
        model = build_debate_model(config)
        assert isinstance(model, GroqModel)

    def test_raises_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_debate_model raises ValueError when no API key available."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(api_key=None)
        with pytest.raises(ValueError, match="Groq API key required"):
            build_debate_model(config)

    def test_uses_config_model_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_debate_model uses the model name from config."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(model="llama-3.1-8b-instant", api_key="gsk_test")
        model = build_debate_model(config)
        assert isinstance(model, GroqModel)
        assert model.model_name == "llama-3.1-8b-instant"


# ---------------------------------------------------------------------------
# build_debate_model — Anthropic provider
# ---------------------------------------------------------------------------


class TestBuildAnthropicModel:
    """Tests for build_debate_model with Anthropic provider."""

    def test_returns_anthropic_model_with_config_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """build_debate_model returns AnthropicModel when config key is provided."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key="sk-ant-test-key-123",
        )
        model = build_debate_model(config)
        assert isinstance(model, AnthropicModel)

    def test_returns_anthropic_model_with_env_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_debate_model uses ANTHROPIC_API_KEY env var as fallback."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key-456")
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key=None,
        )
        model = build_debate_model(config)
        assert isinstance(model, AnthropicModel)

    def test_raises_without_anthropic_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_debate_model raises ValueError when no Anthropic API key available."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key=None,
        )
        with pytest.raises(ValueError, match="Anthropic API key required"):
            build_debate_model(config)

    def test_config_key_takes_priority_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config anthropic_api_key is preferred over ANTHROPIC_API_KEY env var."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key="sk-ant-config-key",
        )
        model = build_debate_model(config)
        assert isinstance(model, AnthropicModel)

    def test_uses_anthropic_model_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_debate_model uses anthropic_model name from config."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_model="claude-opus-4-5-20250220",
            anthropic_api_key="sk-ant-test-key",
        )
        model = build_debate_model(config)
        assert isinstance(model, AnthropicModel)
        assert model.model_name == "claude-opus-4-5-20250220"


# ---------------------------------------------------------------------------
# build_debate_model — dispatch
# ---------------------------------------------------------------------------


class TestBuildDebateModelDispatch:
    """Tests for build_debate_model provider dispatch."""

    def test_groq_is_default_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default provider is Groq; build_debate_model returns GroqModel."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(api_key="gsk_test_key")
        assert config.provider == LLMProvider.GROQ
        model = build_debate_model(config)
        assert isinstance(model, GroqModel)

    def test_dispatch_to_anthropic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Provider ANTHROPIC dispatches to AnthropicModel builder."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key="sk-ant-dispatch-test",
        )
        model = build_debate_model(config)
        assert isinstance(model, AnthropicModel)
        assert not isinstance(model, GroqModel)

    def test_groq_dispatch_ignores_anthropic_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Groq provider does not use Anthropic API key."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(
            provider=LLMProvider.GROQ,
            api_key=None,
            anthropic_api_key="sk-ant-should-not-use",
        )
        with pytest.raises(ValueError, match="Groq API key required"):
            build_debate_model(config)

    def test_anthropic_dispatch_ignores_groq_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Anthropic provider does not use Groq API key."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            api_key="gsk_should_not_use",
            anthropic_api_key=None,
        )
        with pytest.raises(ValueError, match="Anthropic API key required"):
            build_debate_model(config)
