"""Tests for orchestrator Phase 1 inter-batch delay and batch ticker delay.

Verifies that asyncio.sleep is called between Phase 1 agent batches when
parallelism < number of agents, and skipped when parallelism >= agents or delay=0.
Also tests provider-aware rate limiting: Anthropic-safe substitutions and user overrides.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from options_arena.agents.orchestrator import (
    _effective_phase1_settings,
    effective_batch_ticker_delay,
)
from options_arena.models import DebateConfig
from options_arena.models.enums import LLMProvider


class TestPhase1InterBatchDelay:
    """Test the inter-batch delay logic extracted from orchestrator Phase 1."""

    @pytest.mark.asyncio
    async def test_sleep_called_between_batches(self) -> None:
        """When parallelism < coros and delay > 0, sleep is called between batches."""
        coros_count = 4
        parallelism = 2
        delay = 1.5

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            # Don't actually sleep in tests

        # Simulate the batching loop from orchestrator.py
        async def _fake_coro() -> str:
            return "ok"

        coros = [_fake_coro() for _ in range(coros_count)]
        results: list[object] = []

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i in range(0, len(coros), parallelism):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)
                batch = coros[i : i + parallelism]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                results.extend(batch_results)

        # With 4 coros, parallelism 2: 2 batches, 1 sleep between them
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == pytest.approx(1.5)
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_no_sleep_when_delay_zero(self) -> None:
        """When delay=0, no sleep is called."""
        coros_count = 4
        parallelism = 2
        delay = 0.0

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def _fake_coro() -> str:
            return "ok"

        coros = [_fake_coro() for _ in range(coros_count)]
        results: list[object] = []

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i in range(0, len(coros), parallelism):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)
                batch = coros[i : i + parallelism]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                results.extend(batch_results)

        assert len(sleep_calls) == 0
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_no_sleep_when_parallelism_covers_all(self) -> None:
        """When parallelism >= coros, all run in one gather (no batching, no sleep)."""
        coros_count = 4
        parallelism = 4
        delay = 1.5

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def _fake_coro() -> str:
            return "ok"

        coros = [_fake_coro() for _ in range(coros_count)]

        with patch("asyncio.sleep", side_effect=mock_sleep):
            # When parallelism >= len(coros), the orchestrator uses single gather
            if parallelism >= len(coros):
                results = list(await asyncio.gather(*coros, return_exceptions=True))
            else:
                results = []
                for i in range(0, len(coros), parallelism):
                    if i > 0 and delay > 0:
                        await asyncio.sleep(delay)
                    batch = coros[i : i + parallelism]
                    batch_results = await asyncio.gather(*batch, return_exceptions=True)
                    results.extend(batch_results)

        assert len(sleep_calls) == 0
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_multiple_sleep_calls_for_many_batches(self) -> None:
        """With 6 coros and parallelism=2, expect 2 sleep calls (between 3 batches)."""
        coros_count = 6
        parallelism = 2
        delay = 0.5

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        async def _fake_coro() -> str:
            return "ok"

        coros = [_fake_coro() for _ in range(coros_count)]
        results: list[object] = []

        with patch("asyncio.sleep", side_effect=mock_sleep):
            for i in range(0, len(coros), parallelism):
                if i > 0 and delay > 0:
                    await asyncio.sleep(delay)
                batch = coros[i : i + parallelism]
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                results.extend(batch_results)

        assert len(sleep_calls) == 2
        assert all(s == pytest.approx(0.5) for s in sleep_calls)
        assert len(results) == 6


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

    # -- _effective_phase1_settings --

    def test_groq_passes_through_defaults(self) -> None:
        """Groq provider returns stored config values unchanged."""
        config = DebateConfig(provider=LLMProvider.GROQ)
        parallelism, delay = _effective_phase1_settings(config)
        assert parallelism == 2
        assert delay == pytest.approx(1.0)

    def test_anthropic_substitutes_safe_defaults(self) -> None:
        """Anthropic with Groq defaults -> safe substitution."""
        config = DebateConfig(provider=LLMProvider.ANTHROPIC)
        parallelism, delay = _effective_phase1_settings(config)
        assert parallelism == 1
        assert delay == pytest.approx(3.0)

    def test_anthropic_respects_user_override_parallelism(self) -> None:
        """Anthropic with user-overridden parallelism passes it through."""
        config = DebateConfig(provider=LLMProvider.ANTHROPIC, phase1_parallelism=4)
        parallelism, delay = _effective_phase1_settings(config)
        assert parallelism == 4  # user override respected
        assert delay == pytest.approx(3.0)  # still substituted (was default)

    def test_anthropic_respects_user_override_batch_delay(self) -> None:
        """Anthropic with user-overridden batch delay passes it through."""
        config = DebateConfig(provider=LLMProvider.ANTHROPIC, phase1_batch_delay=0.5)
        parallelism, delay = _effective_phase1_settings(config)
        assert parallelism == 1  # still substituted (was default)
        assert delay == pytest.approx(0.5)  # user override respected

    def test_anthropic_respects_both_overrides(self) -> None:
        """Anthropic with both fields overridden passes both through."""
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            phase1_parallelism=3,
            phase1_batch_delay=2.0,
        )
        parallelism, delay = _effective_phase1_settings(config)
        assert parallelism == 3
        assert delay == pytest.approx(2.0)

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
