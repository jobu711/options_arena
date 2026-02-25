"""LLM model configuration for PydanticAI debate agents.

Uses Groq cloud API exclusively. API key resolution: explicit config >
``GROQ_API_KEY`` env var.

Use ``build_debate_model(config)`` to get the configured Groq model.
"""

import logging
import os

from pydantic_ai.models import Model
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider

from options_arena.models import DebateConfig

logger = logging.getLogger(__name__)


def build_debate_model(config: DebateConfig) -> Model:
    """Build a PydanticAI model backed by Groq cloud API.

    API key resolution: ``config.api_key`` > ``GROQ_API_KEY`` env var.

    Parameters
    ----------
    config
        Debate configuration with ``model`` and optional ``api_key``.

    Returns
    -------
    Model
        Configured PydanticAI GroqModel.

    Raises
    ------
    ValueError
        If no API key is found in config or environment.
    """
    api_key = _resolve_api_key(config)
    if api_key is None:
        raise ValueError(
            "Groq API key required. Set ARENA_DEBATE__API_KEY or GROQ_API_KEY env var, "
            "or pass api_key in DebateConfig."
        )
    logger.debug("Building GroqModel: model=%s", config.model)
    provider = GroqProvider(api_key=api_key)
    return GroqModel(config.model, provider=provider)


def _resolve_api_key(config: DebateConfig) -> str | None:
    """Resolve Groq API key with priority: config > env > None."""
    if config.api_key is not None:
        return config.api_key
    return os.environ.get("GROQ_API_KEY")
