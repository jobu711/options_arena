"""Tests for orchestrator batch ticker delay.

Verifies that asyncio.sleep is called between tickers in batch debates,
and tests provider-aware rate limiting: Anthropic-safe substitutions and
user overrides.

Phase 1 inter-batch delay logic was removed in Issue #664 (dead fields cleanup);
all Phase 1 agents now run concurrently via asyncio.gather.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from options_arena.agents.orchestrator import (
    effective_batch_ticker_delay,
)
from options_arena.models import DebateConfig
from options_arena.models.enums import LLMProvider


class TestBatchTickerDelay:
    """Test the inter-ticker delay pattern used in CLI and API batch debates."""

    @pytest.mark.asyncio
    async def test_sleep_called_between_tickers(self) -> None:
        """Sleep called before each ticker except the first."""
        tickers = ["AAPL", "MSFT", "GOOGL"]
        delay = 5.0
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        processed: list[str] = []

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i, ticker in enumerate(tickers):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)
                processed.append(ticker)

        assert len(sleep_calls) == 2  # Between ticker 1-2 and 2-3
        assert all(s == pytest.approx(5.0) for s in sleep_calls)
        assert processed == tickers

    @pytest.mark.asyncio
    async def test_no_sleep_when_delay_zero(self) -> None:
        """No sleep calls when batch_ticker_delay=0."""
        tickers = ["AAPL", "MSFT", "GOOGL"]
        delay = 0.0
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i, _ticker in enumerate(tickers):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)

        assert len(sleep_calls) == 0

    @pytest.mark.asyncio
    async def test_single_ticker_no_sleep(self) -> None:
        """No sleep needed for a single ticker."""
        tickers = ["AAPL"]
        delay = 5.0
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i, _ticker in enumerate(tickers):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)

        assert len(sleep_calls) == 0


class TestProviderAwareDefaults:
    """Test provider-aware rate limiting helpers.

    Anthropic Tier 1 limits (8K output tokens/min) require slower pacing than Groq.
    Helpers substitute safe values when the config holds Groq defaults; user overrides
    via env vars are respected.
    """

    # -- effective_batch_ticker_delay --

    def test_groq_batch_ticker_delay_passthrough(self) -> None:
        """Groq provider returns stored batch_ticker_delay unchanged."""
        config = DebateConfig(provider=LLMProvider.GROQ)
        assert effective_batch_ticker_delay(config) == pytest.approx(5.0)

    def test_anthropic_batch_ticker_delay_substitution(self) -> None:
        """Anthropic with Groq default -> 30s safe substitution."""
        config = DebateConfig(provider=LLMProvider.ANTHROPIC)
        assert effective_batch_ticker_delay(config) == pytest.approx(30.0)

    def test_anthropic_batch_ticker_delay_user_override(self) -> None:
        """Anthropic with user-overridden delay passes it through."""
        config = DebateConfig(provider=LLMProvider.ANTHROPIC, batch_ticker_delay=15.0)
        assert effective_batch_ticker_delay(config) == pytest.approx(15.0)
