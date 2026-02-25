"""Tests for model_config.py — Groq-only model building.

Tests cover:
  - build_debate_model returns GroqModel with API key
  - build_debate_model raises ValueError without API key
  - _resolve_api_key priority: config > env > None
"""

from __future__ import annotations

import pytest
from pydantic_ai import models
from pydantic_ai.models.groq import GroqModel

from options_arena.agents.model_config import (
    _resolve_api_key,
    build_debate_model,
)
from options_arena.models import DebateConfig

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# _resolve_api_key
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
# build_debate_model
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
