"""Tests for model_config.py — build_ollama_model and _resolve_host.

Tests cover:
  - build_ollama_model returns OpenAIChatModel (Ollama-backed)
  - _resolve_host uses config value when non-default
  - _resolve_host falls back to OLLAMA_HOST env var
  - _resolve_host returns default when no override
  - _resolve_host prefers config over env var
"""

from __future__ import annotations

import pytest
from pydantic_ai import models
from pydantic_ai.models.openai import OpenAIChatModel

from options_arena.agents.model_config import _resolve_host, build_ollama_model
from options_arena.models import DebateConfig

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
