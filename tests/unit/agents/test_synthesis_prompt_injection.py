"""Tests for contract guidance and tuned weights injection into synthesis prompt.

Covers:
- SynthesisDeps field defaults and population
- Dynamic system prompt injection of all three blocks
- Orchestrator-level fetch/render for contract guidance and tuned weights
"""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models

from options_arena.agents.synthesis_agent import (
    SynthesisDeps,
    _synthesis_system_prompt,
)
from options_arena.learning.contract_guidance import render_contract_guidance
from options_arena.learning.weight_tuner import render_tuned_weights
from options_arena.models import AgentWeightsComparison
from options_arena.models.attribution import ContractGuidance

models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract_guidance() -> ContractGuidance:
    return ContractGuidance(
        optimal_delta_low=0.30,
        optimal_delta_high=0.40,
        optimal_dte_low=30,
        optimal_dte_high=45,
        delta_win_rate=0.65,
        dte_win_rate=0.60,
        sample_count=50,
    )


def _make_tuned_weights_text() -> str:
    weights = {"trend": 0.28, "volatility": 0.22, "flow": 0.18, "fundamental": 0.12}
    return render_tuned_weights(weights)


def _make_contract_guidance_text() -> str:
    return render_contract_guidance(_make_contract_guidance())


def _make_minimal_synthesis_deps(
    *,
    learned_patterns: str = "",
    tuned_weights: str = "",
    contract_guidance: str = "",
) -> SynthesisDeps:
    """Build a minimal SynthesisDeps for prompt testing."""
    return SynthesisDeps(
        context=MagicMock(),
        assessments=[],
        contracts=[],
        ticker_score=MagicMock(),
        learned_patterns=learned_patterns,
        tuned_weights=tuned_weights,
        contract_guidance=contract_guidance,
    )


# ---------------------------------------------------------------------------
# SynthesisDeps field tests
# ---------------------------------------------------------------------------


class TestSynthesisDepsFields:
    def test_contract_guidance_default_empty(self) -> None:
        """SynthesisDeps() has contract_guidance=''."""
        deps = SynthesisDeps(
            context=MagicMock(),
            assessments=[],
            contracts=[],
            ticker_score=MagicMock(),
        )
        assert deps.contract_guidance == ""

    def test_all_fields_populated(self) -> None:
        """Construction with all 3 injection fields works."""
        deps = SynthesisDeps(
            context=MagicMock(),
            assessments=[],
            contracts=[],
            ticker_score=MagicMock(),
            learned_patterns="<<<LEARNED_PATTERNS>>>\ntest\n<<<END_LEARNED_PATTERNS>>>",
            tuned_weights="trend: 0.25",
            contract_guidance="<<<CONTRACT_GUIDANCE>>>\ntest\n<<<END_CONTRACT_GUIDANCE>>>",
        )
        assert deps.learned_patterns != ""
        assert deps.tuned_weights != ""
        assert deps.contract_guidance != ""

    def test_tuned_weights_default_empty(self) -> None:
        """SynthesisDeps() has tuned_weights=''."""
        deps = SynthesisDeps(
            context=MagicMock(),
            assessments=[],
            contracts=[],
            ticker_score=MagicMock(),
        )
        assert deps.tuned_weights == ""

    def test_learned_patterns_default_empty(self) -> None:
        """SynthesisDeps() has learned_patterns=''."""
        deps = SynthesisDeps(
            context=MagicMock(),
            assessments=[],
            contracts=[],
            ticker_score=MagicMock(),
        )
        assert deps.learned_patterns == ""


# ---------------------------------------------------------------------------
# System prompt injection tests
# ---------------------------------------------------------------------------


class TestSynthesisSystemPrompt:
    """Test dynamic prompt injection via _synthesis_system_prompt().

    Note: The static SYNTHESIS_SYSTEM_PROMPT references ``<<<TUNED_WEIGHTS>>>``
    as documentation text. The dynamic injection wraps actual content in
    ``<<<TUNED_WEIGHTS>>>...<<<END_TUNED_WEIGHTS>>>`` blocks. Tests check for
    the closing delimiter ``<<<END_*>>>`` to distinguish dynamic injection from
    static documentation references.
    """

    @pytest.mark.asyncio
    async def test_injects_contract_guidance(self) -> None:
        """When contract_guidance set, <<<CONTRACT_GUIDANCE>>> block appears in prompt."""
        guidance_text = _make_contract_guidance_text()
        deps = _make_minimal_synthesis_deps(contract_guidance=guidance_text)

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        assert "<<<CONTRACT_GUIDANCE>>>" in prompt
        assert "<<<END_CONTRACT_GUIDANCE>>>" in prompt

    @pytest.mark.asyncio
    async def test_injects_tuned_weights(self) -> None:
        """When tuned_weights set, <<<TUNED_WEIGHTS>>>...<<<END_TUNED_WEIGHTS>>> block appears."""
        weights_text = _make_tuned_weights_text()
        deps = _make_minimal_synthesis_deps(tuned_weights=weights_text)

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        # Dynamic injection adds the END delimiter; the static prompt doesn't have it
        assert "<<<END_TUNED_WEIGHTS>>>" in prompt
        assert "auto-tuned" in prompt

    @pytest.mark.asyncio
    async def test_injects_all_three_blocks(self) -> None:
        """All 3 blocks present when all fields populated."""
        learned = "<<<LEARNED_PATTERNS>>>\nTest pattern\n<<<END_LEARNED_PATTERNS>>>"
        weights_text = _make_tuned_weights_text()
        guidance_text = _make_contract_guidance_text()

        deps = _make_minimal_synthesis_deps(
            learned_patterns=learned,
            tuned_weights=weights_text,
            contract_guidance=guidance_text,
        )

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        assert "<<<END_TUNED_WEIGHTS>>>" in prompt
        assert "<<<END_LEARNED_PATTERNS>>>" in prompt
        assert "<<<END_CONTRACT_GUIDANCE>>>" in prompt

    @pytest.mark.asyncio
    async def test_empty_fields_no_injection(self) -> None:
        """Empty strings produce no dynamic injection blocks in prompt."""
        deps = _make_minimal_synthesis_deps()

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        # Dynamic blocks add END delimiters; static prompt never has them
        assert "<<<END_TUNED_WEIGHTS>>>" not in prompt
        assert "<<<END_CONTRACT_GUIDANCE>>>" not in prompt
        assert "<<<END_LEARNED_PATTERNS>>>" not in prompt

    @pytest.mark.asyncio
    async def test_partial_injection_only_guidance(self) -> None:
        """Only contract guidance injected when other fields empty."""
        guidance_text = _make_contract_guidance_text()
        deps = _make_minimal_synthesis_deps(contract_guidance=guidance_text)

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        assert "<<<END_CONTRACT_GUIDANCE>>>" in prompt
        assert "<<<END_TUNED_WEIGHTS>>>" not in prompt

    @pytest.mark.asyncio
    async def test_partial_injection_only_weights(self) -> None:
        """Only tuned weights injected when other fields empty."""
        weights_text = _make_tuned_weights_text()
        deps = _make_minimal_synthesis_deps(tuned_weights=weights_text)

        ctx = MagicMock()
        ctx.deps = deps

        prompt = await _synthesis_system_prompt(ctx)
        assert "<<<END_TUNED_WEIGHTS>>>" in prompt
        assert "<<<END_CONTRACT_GUIDANCE>>>" not in prompt


# ---------------------------------------------------------------------------
# Orchestrator injection tests
#
# The orchestrator uses lazy imports inside try/except blocks, so we test the
# fetch-render logic directly rather than patching module-level attributes.
# ---------------------------------------------------------------------------


class TestOrchestratorInjection:
    @pytest.mark.asyncio
    async def test_guidance_fetched_and_rendered(self) -> None:
        """Contract guidance populated when fetch returns data."""
        guidance = _make_contract_guidance()
        mock_fetch = AsyncMock(return_value=guidance)

        # Replicate the orchestrator's never-raises fetch pattern
        contract_guidance_text = ""
        try:
            result = await mock_fetch(MagicMock())
            if result:
                contract_guidance_text = render_contract_guidance(result)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, ImportError):
            pass

        assert "<<<CONTRACT_GUIDANCE>>>" in contract_guidance_text
        assert "0.30" in contract_guidance_text
        mock_fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_weights_fetched_and_rendered(self) -> None:
        """Tuned weights populated when auto_tune_weights returns comparisons."""
        comparisons = [
            AgentWeightsComparison(
                agent_name="trend",
                manual_weight=0.25,
                auto_weight=0.28,
                brier_score=0.35,
                sample_size=50,
            ),
            AgentWeightsComparison(
                agent_name="volatility",
                manual_weight=0.20,
                auto_weight=0.22,
                brier_score=0.40,
                sample_size=45,
            ),
        ]
        mock_tune = AsyncMock(return_value=comparisons)

        # Replicate the orchestrator's never-raises fetch pattern
        tuned_weights_text = ""
        try:
            tune_result = await mock_tune(MagicMock(), dry_run=True)
            if tune_result:
                current_weights = {r.agent_name: r.auto_weight for r in tune_result}
                tuned_weights_text = render_tuned_weights(current_weights)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, ImportError):
            pass

        assert tuned_weights_text != ""
        assert "trend" in tuned_weights_text
        assert "0.28" in tuned_weights_text
        mock_tune.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_guidance_failure_continues(self) -> None:
        """Exception in contract guidance fetch produces empty string, no crash."""
        mock_fetch = AsyncMock(side_effect=sqlite3.Error("DB error"))

        contract_guidance_text = ""
        try:
            result = await mock_fetch(MagicMock())
            if result:
                contract_guidance_text = render_contract_guidance(result)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, ImportError):
            pass

        assert contract_guidance_text == ""

    @pytest.mark.asyncio
    async def test_fetch_weights_failure_continues(self) -> None:
        """Exception in tuned weights fetch produces empty string, no crash."""
        mock_tune = AsyncMock(side_effect=ImportError("Module not found"))

        tuned_weights_text = ""
        try:
            tune_result = await mock_tune(MagicMock(), dry_run=True)
            if tune_result:
                current_weights = {r.agent_name: r.auto_weight for r in tune_result}
                tuned_weights_text = render_tuned_weights(current_weights)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, ImportError):
            pass

        assert tuned_weights_text == ""

    @pytest.mark.asyncio
    async def test_guidance_none_returns_empty(self) -> None:
        """When fetch_contract_guidance returns None, no guidance text produced."""
        mock_fetch = AsyncMock(return_value=None)

        contract_guidance_text = ""
        guidance = await mock_fetch(MagicMock())
        if guidance:
            contract_guidance_text = render_contract_guidance(guidance)

        assert contract_guidance_text == ""

    @pytest.mark.asyncio
    async def test_weights_empty_list_returns_empty(self) -> None:
        """When auto_tune_weights returns empty list, no weights text produced."""
        mock_tune = AsyncMock(return_value=[])

        tuned_weights_text = ""
        tune_result = await mock_tune(MagicMock(), dry_run=True)
        if tune_result:
            current_weights = {r.agent_name: r.auto_weight for r in tune_result}
            tuned_weights_text = render_tuned_weights(current_weights)

        assert tuned_weights_text == ""
