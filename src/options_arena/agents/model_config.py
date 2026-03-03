"""LLM model configuration for PydanticAI debate agents.

Multi-provider dispatcher: Groq (default) and Anthropic. API key resolution
follows priority: explicit config > environment variable > ``ValueError``.

Use ``build_debate_model(config)`` to get the configured model.
"""

import logging
import os

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.groq import GroqProvider

from options_arena.models import DebateConfig, LLMProvider

logger = logging.getLogger(__name__)


def build_debate_model(config: DebateConfig) -> Model:
    """Build a PydanticAI model for the configured LLM provider.

    Dispatches to Groq or Anthropic based on ``config.provider``.

    Parameters
    ----------
    config
        Debate configuration with provider, model name, and API key(s).

    Returns
    -------
    Model
        Configured PydanticAI model (GroqModel or AnthropicModel).

    Raises
    ------
    ValueError
        If no API key is found for the selected provider.
    """
    match config.provider:
        case LLMProvider.GROQ:
            return _build_groq_model(config)
        case LLMProvider.ANTHROPIC:
            return _build_anthropic_model(config)
        case _:
            raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _build_groq_model(config: DebateConfig) -> GroqModel:
    """Build a GroqModel with resolved API key."""
    api_key = _resolve_api_key(config)
    if api_key is None:
        raise ValueError(
            "Groq API key required. Set ARENA_DEBATE__API_KEY or GROQ_API_KEY env var, "
            "or pass api_key in DebateConfig."
        )
    logger.debug("Building GroqModel: model=%s", config.model)
    provider = GroqProvider(api_key=api_key)
    return GroqModel(config.model, provider=provider)


def _build_anthropic_model(config: DebateConfig) -> AnthropicModel:
    """Build an AnthropicModel with resolved API key."""
    api_key = _resolve_anthropic_api_key(config)
    if api_key is None:
        raise ValueError(
            "Anthropic API key required. Set ARENA_DEBATE__ANTHROPIC_API_KEY or "
            "ANTHROPIC_API_KEY env var, or pass anthropic_api_key in DebateConfig."
        )
    logger.debug("Building AnthropicModel: model=%s", config.anthropic_model)
    provider = AnthropicProvider(api_key=api_key)
    return AnthropicModel(config.anthropic_model, provider=provider)


def _resolve_api_key(config: DebateConfig) -> str | None:
    """Resolve Groq API key with priority: config > env > None."""
    if config.api_key is not None:
        return config.api_key.get_secret_value()
    return os.environ.get("GROQ_API_KEY")


def _resolve_anthropic_api_key(config: DebateConfig) -> str | None:
    """Resolve Anthropic API key with priority: config > env > None."""
    if config.anthropic_api_key is not None:
        return config.anthropic_api_key.get_secret_value()
    return os.environ.get("ANTHROPIC_API_KEY")
