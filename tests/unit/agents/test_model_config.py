"""Tests for model_config.py — build_ollama_model, build_groq_model, build_debate_model.

Tests cover:
  - build_ollama_model returns OpenAIChatModel (Ollama-backed)
  - build_groq_model returns GroqModel with API key
  - build_groq_model raises ValueError without API key
  - build_debate_model routes to correct provider
  - _resolve_host priority: config > env > default
  - _resolve_groq_api_key priority: config > env > None
"""

from __future__ import annotations

import pytest
from pydantic_ai import models
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.models.openai import OpenAIChatModel

from options_arena.agents.model_config import (
    _resolve_groq_api_key,
    _resolve_host,
    build_debate_model,
    build_groq_model,
    build_ollama_model,
)
from options_arena.models import DebateConfig, DebateProvider

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False

_DEFAULT_HOST = "http://localhost:11434"


class TestBuildOllamaModel:
    """Tests for build_ollama_model factory."""

    def test_returns_openai_chat_model(self) -> None:
        """build_ollama_model returns an OpenAIChatModel (Ollama-backed) instance."""
        config = DebateConfig()
        model = build_ollama_model(config)
        assert isinstance(model, OpenAIChatModel)

    def test_uses_config_model_name(self) -> None:
        """Model uses the model name from config."""
        config = DebateConfig(ollama_model="llama3.1:8b")
        model = build_ollama_model(config)
        assert isinstance(model, OpenAIChatModel)
        assert model.model_name == "llama3.1:8b"


class TestResolveHost:
    """Tests for _resolve_host priority resolution."""

    def test_returns_default_when_no_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns default host when config is default and no env var set."""
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        config = DebateConfig()
        assert _resolve_host(config) == _DEFAULT_HOST

    def test_config_override_takes_effect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-default config host is used directly."""
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        config = DebateConfig(ollama_host="http://gpu:11434")
        assert _resolve_host(config) == "http://gpu:11434"

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OLLAMA_HOST env var is used when config is default."""
        monkeypatch.setenv("OLLAMA_HOST", "http://remote:11434")
        config = DebateConfig()  # default host
        assert _resolve_host(config) == "http://remote:11434"

    def test_config_preferred_over_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config override takes priority over OLLAMA_HOST env var."""
        monkeypatch.setenv("OLLAMA_HOST", "http://env:11434")
        config = DebateConfig(ollama_host="http://config:11434")
        assert _resolve_host(config) == "http://config:11434"

    def test_empty_env_var_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty OLLAMA_HOST env var falls through to default."""
        monkeypatch.setenv("OLLAMA_HOST", "")
        config = DebateConfig()
        # Empty string is falsy, so falls through to default
        assert _resolve_host(config) == _DEFAULT_HOST


# ---------------------------------------------------------------------------
# build_groq_model
# ---------------------------------------------------------------------------


class TestBuildGroqModel:
    """Tests for build_groq_model factory."""

    def test_returns_groq_model_with_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_groq_model returns a GroqModel when API key is provided."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(groq_api_key="gsk_test_key_123")
        model = build_groq_model(config)
        assert isinstance(model, GroqModel)

    def test_uses_env_var_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_groq_model uses GROQ_API_KEY env var when config key is None."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_env_key_456")
        config = DebateConfig(groq_api_key=None)
        model = build_groq_model(config)
        assert isinstance(model, GroqModel)

    def test_raises_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_groq_model raises ValueError when no API key available."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(groq_api_key=None)
        with pytest.raises(ValueError, match="Groq API key required"):
            build_groq_model(config)

    def test_uses_config_groq_model_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """build_groq_model uses the model name from config."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(groq_model="llama-3.1-8b-instant", groq_api_key="gsk_test")
        model = build_groq_model(config)
        assert isinstance(model, GroqModel)
        assert model.model_name == "llama-3.1-8b-instant"


# ---------------------------------------------------------------------------
# _resolve_groq_api_key
# ---------------------------------------------------------------------------


class TestResolveGroqApiKey:
    """Tests for _resolve_groq_api_key priority resolution."""

    def test_returns_none_when_no_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when config is None and no env var set."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(groq_api_key=None)
        assert _resolve_groq_api_key(config) is None

    def test_config_key_takes_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config groq_api_key takes priority over env var."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_env_key")
        config = DebateConfig(groq_api_key="gsk_config_key")
        assert _resolve_groq_api_key(config) == "gsk_config_key"

    def test_env_var_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GROQ_API_KEY env var is used when config key is None."""
        monkeypatch.setenv("GROQ_API_KEY", "gsk_env_key")
        config = DebateConfig(groq_api_key=None)
        assert _resolve_groq_api_key(config) == "gsk_env_key"


# ---------------------------------------------------------------------------
# build_debate_model
# ---------------------------------------------------------------------------


class TestBuildDebateModel:
    """Tests for build_debate_model dispatcher."""

    def test_routes_to_ollama_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default provider routes to Ollama (returns OpenAIChatModel)."""
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        config = DebateConfig()  # default provider=OLLAMA
        model = build_debate_model(config)
        assert isinstance(model, OpenAIChatModel)

    def test_routes_to_groq(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Groq provider routes to GroqModel."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(provider=DebateProvider.GROQ, groq_api_key="gsk_test")
        model = build_debate_model(config)
        assert isinstance(model, GroqModel)

    def test_groq_without_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Groq provider without API key raises ValueError."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        config = DebateConfig(provider=DebateProvider.GROQ, groq_api_key=None)
        with pytest.raises(ValueError, match="Groq API key required"):
            build_debate_model(config)
