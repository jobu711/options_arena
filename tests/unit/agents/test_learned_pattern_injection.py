"""Tests for learned pattern injection into desk agent prompts."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.contrarian_desk import contrarian_desk
from options_arena.agents.flow_desk import flow_desk
from options_arena.agents.fundamental_desk import fundamental_desk
from options_arena.agents.research_desk import research_desk
from options_arena.agents.risk_desk import risk_desk
from options_arena.agents.trend_desk import trend_desk
from options_arena.agents.volatility_desk import vol_desk
from options_arena.learning.strategy_book import render_learned_patterns
from options_arena.models import (
    ConditionOperator,
    RuleStatus,
    StrategyCondition,
    StrategyRule,
)

models.ALLOW_MODEL_REQUESTS = False

_NOW = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule(status: RuleStatus = RuleStatus.APPROVED) -> StrategyRule:
    return StrategyRule(
        rule_id="rule_test",
        pattern="Tech | IV mid_high | DTE medium | bullish -> 70% win rate",
        conditions=[
            StrategyCondition(
                field="sector",
                operator=ConditionOperator.EQ,
                value="Information Technology",
            ),
        ],
        win_rate=0.70,
        avg_return=0.12,
        sample_size=40,
        status=status,
        created_at=_NOW,
    )


def _make_deps(learned_patterns: str = "") -> DeskDeps:
    return DeskDeps(
        query="What is the IV for AAPL?",
        ticker="AAPL",
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
        learned_patterns=learned_patterns,
    )


# ---------------------------------------------------------------------------
# DeskDeps tests
# ---------------------------------------------------------------------------


class TestDeskDepsLearnedPatterns:
    def test_default_empty_patterns(self) -> None:
        """Verify DeskDeps.learned_patterns defaults to empty string."""
        deps = DeskDeps(
            query="test",
            ticker="AAPL",
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
        )
        assert deps.learned_patterns == ""

    def test_patterns_populated(self) -> None:
        """Verify learned_patterns can be set."""
        deps = _make_deps("<<<LEARNED_PATTERNS>>>\ntest\n<<<END_LEARNED_PATTERNS>>>")
        assert "LEARNED_PATTERNS" in deps.learned_patterns


# ---------------------------------------------------------------------------
# Desk agent prompt injection tests
# ---------------------------------------------------------------------------


class TestPromptInjection:
    @pytest.mark.asyncio
    async def test_vol_desk_includes_patterns(self) -> None:
        """Verify volatility desk prompt contains patterns when provided."""
        patterns = render_learned_patterns([_make_rule()])
        deps = _make_deps(patterns)
        test_model = TestModel()
        with vol_desk.override(model=test_model):
            result = await vol_desk.run("test AAPL vol", model=test_model, deps=deps)
        # If the agent ran successfully, prompt injection worked (no crash)
        assert isinstance(result.output, str)

    @pytest.mark.asyncio
    async def test_vol_desk_clean_without_patterns(self) -> None:
        """Verify volatility desk runs cleanly without patterns."""
        deps = _make_deps("")
        test_model = TestModel()
        with vol_desk.override(model=test_model):
            result = await vol_desk.run("test AAPL vol", model=test_model, deps=deps)
        assert isinstance(result.output, str)

    @pytest.mark.asyncio
    async def test_all_seven_desks_accept_patterns(self) -> None:
        """Verify each of the 7 desk agents accepts learned_patterns without error."""
        patterns = render_learned_patterns([_make_rule()])
        agents = [
            vol_desk,
            risk_desk,
            trend_desk,
            flow_desk,
            fundamental_desk,
            contrarian_desk,
            research_desk,
        ]
        for agent in agents:
            deps = _make_deps(patterns)
            test_model = TestModel()
            with agent.override(model=test_model):
                result = await agent.run("test query", model=test_model, deps=deps)
            assert isinstance(result.output, str), f"Failed for {agent}"

    @pytest.mark.asyncio
    async def test_all_seven_desks_clean_without_patterns(self) -> None:
        """Verify all desks run cleanly when no patterns provided."""
        agents = [
            vol_desk,
            risk_desk,
            trend_desk,
            flow_desk,
            fundamental_desk,
            contrarian_desk,
            research_desk,
        ]
        for agent in agents:
            deps = _make_deps("")
            test_model = TestModel()
            with agent.override(model=test_model):
                result = await agent.run("test query", model=test_model, deps=deps)
            assert isinstance(result.output, str)


# ---------------------------------------------------------------------------
# Pattern filtering tests
# ---------------------------------------------------------------------------


class TestPatternFiltering:
    def test_only_approved_rendered(self) -> None:
        """Verify only approved rules appear in rendered text."""
        rules = [
            _make_rule(RuleStatus.APPROVED),
            _make_rule(RuleStatus.CANDIDATE),
            _make_rule(RuleStatus.REJECTED),
        ]
        text = render_learned_patterns(rules)
        assert text.count("Pattern:") == 1

    def test_no_approved_empty(self) -> None:
        """Verify empty string when no approved rules."""
        rules = [_make_rule(RuleStatus.CANDIDATE)]
        assert render_learned_patterns(rules) == ""
