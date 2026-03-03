"""Tests for model_config.py — multi-provider model building.

Tests cover:
  - build_debate_model dispatches to Groq by default
  - build_debate_model dispatches to Anthropic when provider=ANTHROPIC
  - _resolve_api_key priority: config > env > None
  - _resolve_anthropic_api_key priority: config > env > None
  - Missing API keys raise ValueError with clear messages
"""

from __future__ import annotations

import pytest
from pydantic_ai import models
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.groq import GroqModel

from options_arena.agents.model_config import (
    _resolve_anthropic_api_key,
    _resolve_api_key,
    build_debate_model,
)
from options_arena.models import DebateConfig, LLMProvider

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# _resolve_api_key (Groq)
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
# _resolve_anthropic_api_key
# ---------------------------------------------------------------------------


class TestResolveAnthropicApiKey:
    """Tests for _resolve_anthropic_api_key priority resolution."""

    def test_returns_none_when_no_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when config is None and no env var set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(anthropic_api_key=None)
        assert _resolve_anthropic_api_key(config) is None

    def test_config_key_takes_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config anthropic_api_key takes priority over env var."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
        config = DebateConfig(anthropic_api_key="sk-ant-config-key")
        assert _resolve_anthropic_api_key(config) == "sk-ant-config-key"

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ANTHROPIC_API_KEY env var is used when config key is None."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
        config = DebateConfig(anthropic_api_key=None)
        assert _resolve_anthropic_api_key(config) == "sk-ant-env-key"


# ---------------------------------------------------------------------------
# build_debate_model — Groq
# ---------------------------------------------------------------------------


class TestBuildDebateModel:
    """Tests for build_debate_model (Groq provider)."""

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

    def test_groq_default_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default provider=GROQ still builds GroqModel (regression test)."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(api_key="gsk_test")
        assert config.provider is LLMProvider.GROQ
        model = build_debate_model(config)
        assert isinstance(model, GroqModel)


# ---------------------------------------------------------------------------
# build_debate_model — Anthropic
# ---------------------------------------------------------------------------


class TestBuildAnthropicModel:
    """Tests for build_debate_model with Anthropic provider."""

    def test_builds_anthropic_model_with_config_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AnthropicModel returned when provider=ANTHROPIC and key in config."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key="sk-ant-test-key",
        )
        model = build_debate_model(config)
        assert isinstance(model, AnthropicModel)

    def test_builds_anthropic_model_with_env_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """AnthropicModel returned when provider=ANTHROPIC and key in env."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env-key")
        config = DebateConfig(provider=LLMProvider.ANTHROPIC, anthropic_api_key=None)
        model = build_debate_model(config)
        assert isinstance(model, AnthropicModel)

    def test_anthropic_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ValueError raised with clear message when no Anthropic key found."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(provider=LLMProvider.ANTHROPIC, anthropic_api_key=None)
        with pytest.raises(ValueError, match="Anthropic API key required"):
            build_debate_model(config)

    def test_uses_anthropic_model_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_debate_model uses anthropic_model name from config."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_model="claude-haiku-4-5-20251001",
            anthropic_api_key="sk-ant-test",
        )
        model = build_debate_model(config)
        assert isinstance(model, AnthropicModel)
        assert model.model_name == "claude-haiku-4-5-20251001"

    def test_dispatch_to_anthropic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """provider=ANTHROPIC routes to AnthropicModel builder."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            anthropic_api_key="sk-ant-test",
        )
        model = build_debate_model(config)
        assert isinstance(model, AnthropicModel)
        assert not isinstance(model, GroqModel)
