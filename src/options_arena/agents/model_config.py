"""Ollama model configuration for PydanticAI agents.

Host resolution priority: explicit config > OLLAMA_HOST env var > default localhost.

PydanticAI >= 1.0 uses ``OpenAIChatModel`` + ``OllamaProvider`` (the old
``OllamaModel`` import path no longer exists).  Ollama exposes an OpenAI-
compatible endpoint, which PydanticAI wraps via the provider abstraction.
"""

import logging
import os

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from options_arena.models import DebateConfig

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "http://localhost:11434"


def build_ollama_model(config: DebateConfig) -> OpenAIChatModel:
    """Build a PydanticAI model backed by Ollama with host resolution.

    Parameters
    ----------
    config
        Debate configuration with ``ollama_model`` and ``ollama_host``.

    Returns
    -------
    OpenAIChatModel
        Configured for the specified Ollama model and host.
    """
    host = _resolve_host(config)
    logger.debug("Building OllamaModel: model=%s, host=%s", config.ollama_model, host)
    provider = OllamaProvider(base_url=f"{host}/v1")
    return OpenAIChatModel(model_name=config.ollama_model, provider=provider)


def _resolve_host(config: DebateConfig) -> str:
    """Resolve Ollama host with priority: config > env > default."""
    if config.ollama_host != _DEFAULT_HOST:
        return config.ollama_host
    env_host = os.environ.get("OLLAMA_HOST")
    if env_host:
        return env_host
    return _DEFAULT_HOST
