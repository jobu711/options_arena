"""LLM model configuration for PydanticAI debate agents.

Supports two providers:
- **Ollama** (default): local server, ``OpenAIChatModel`` + ``OllamaProvider``.
  Host resolution: explicit config > ``OLLAMA_HOST`` env var > default localhost.
- **Groq**: cloud API, ``GroqModel`` + ``GroqProvider``.
  API key resolution: explicit config > ``GROQ_API_KEY`` env var.

Use ``build_debate_model(config)`` to get the correct model for the active provider.
"""

import logging
import os

from pydantic_ai.models import Model
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.providers.ollama import OllamaProvider

from options_arena.models import DebateConfig, DebateProvider

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "http://localhost:11434"


def build_debate_model(config: DebateConfig) -> Model:
    """Build a PydanticAI model based on the configured provider.

    Routes to Ollama or Groq based on ``config.provider``.

    Parameters
    ----------
    config
        Debate configuration with provider selection and credentials.

    Returns
    -------
    Model
        Configured PydanticAI model for the selected provider.

    Raises
    ------
    ValueError
        If Groq is selected but no API key is available.
    """
    match config.provider:
        case DebateProvider.GROQ:
            return build_groq_model(config)
        case DebateProvider.OLLAMA:
            return build_ollama_model(config)
        case _:
            raise ValueError(f"Unknown debate provider: {config.provider}")


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


def build_groq_model(config: DebateConfig) -> GroqModel:
    """Build a PydanticAI model backed by Groq cloud API.

    API key resolution: ``config.groq_api_key`` > ``GROQ_API_KEY`` env var.

    Parameters
    ----------
    config
        Debate configuration with ``groq_model`` and optional ``groq_api_key``.

    Returns
    -------
    GroqModel
        Configured for the specified Groq model.

    Raises
    ------
    ValueError
        If no API key is found in config or environment.
    """
    api_key = _resolve_groq_api_key(config)
    if api_key is None:
        raise ValueError(
            "Groq API key required. Set ARENA_DEBATE__GROQ_API_KEY or GROQ_API_KEY env var, "
            "or pass groq_api_key in DebateConfig."
        )
    logger.debug("Building GroqModel: model=%s", config.groq_model)
    provider = GroqProvider(api_key=api_key)
    return GroqModel(config.groq_model, provider=provider)


def _resolve_host(config: DebateConfig) -> str:
    """Resolve Ollama host with priority: config > env > default."""
    if config.ollama_host != _DEFAULT_HOST:
        return config.ollama_host
    env_host = os.environ.get("OLLAMA_HOST")
    if env_host:
        return env_host
    return _DEFAULT_HOST


def _resolve_groq_api_key(config: DebateConfig) -> str | None:
    """Resolve Groq API key with priority: config > env > None."""
    if config.groq_api_key is not None:
        return config.groq_api_key
    return os.environ.get("GROQ_API_KEY")
