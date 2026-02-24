"""Ollama model configuration for PydanticAI agents.

Host resolution priority: explicit config > OLLAMA_HOST env var > default localhost.
"""

import logging
import os

from pydantic_ai.models.ollama import OllamaModel

from options_arena.models import DebateConfig

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "http://localhost:11434"


def build_ollama_model(config: DebateConfig) -> OllamaModel:
    """Build a PydanticAI OllamaModel with host resolution.

    Parameters
    ----------
    config
        Debate configuration with ``ollama_model`` and ``ollama_host``.

    Returns
    -------
    OllamaModel
        Configured for the specified model and host.
    """
    host = _resolve_host(config)
    logger.debug("Building OllamaModel: model=%s, host=%s", config.ollama_model, host)
    return OllamaModel(config.ollama_model, base_url=host)


def _resolve_host(config: DebateConfig) -> str:
    """Resolve Ollama host with priority: config > env > default."""
    if config.ollama_host != _DEFAULT_HOST:
        return config.ollama_host
    env_host = os.environ.get("OLLAMA_HOST")
    if env_host:
        return env_host
    return _DEFAULT_HOST
