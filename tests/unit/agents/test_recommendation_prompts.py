"""Structural tests for the 6 recommendation prompts.

Tests cover:
  - Each prompt is a non-empty string (len > 100)
  - Each prompt is within token budget (< 8000 chars)
  - Each prompt has a VERSION header
  - Each prompt includes PROMPT_RULES_APPENDIX content
  - Each prompt references its domain-specific assessment fields
  - VERSION header format matches convention
"""

from __future__ import annotations

import importlib
import inspect
import re

import pytest

from options_arena.agents._parsing import PROMPT_RULES_APPENDIX
from options_arena.agents.prompts import (
    RECOMMEND_CONTRARIAN_PROMPT,
    RECOMMEND_FLOW_PROMPT,
    RECOMMEND_FUNDAMENTAL_PROMPT,
    RECOMMEND_RISK_PROMPT,
    RECOMMEND_TREND_PROMPT,
    RECOMMEND_VOLATILITY_PROMPT,
)

# All 6 prompts as parametrize tuples: (name, prompt_constant)
ALL_RECOMMEND_PROMPTS: list[tuple[str, str]] = [
    ("trend", RECOMMEND_TREND_PROMPT),
    ("volatility", RECOMMEND_VOLATILITY_PROMPT),
    ("flow", RECOMMEND_FLOW_PROMPT),
    ("fundamental", RECOMMEND_FUNDAMENTAL_PROMPT),
    ("risk", RECOMMEND_RISK_PROMPT),
    ("contrarian", RECOMMEND_CONTRARIAN_PROMPT),
]

TOKEN_BUDGET_CHARS = 8000

_VERSION_RE = re.compile(r"# VERSION: v\d+\.\d+", re.MULTILINE)


# ---------------------------------------------------------------------------
# Parametrized structural tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prompt_name", "prompt"),
    ALL_RECOMMEND_PROMPTS,
    ids=[name for name, _ in ALL_RECOMMEND_PROMPTS],
)
@pytest.mark.critical
class TestRecommendationPromptStructure:
    """Structural quality gates for recommendation prompts."""

    def test_prompt_exists_and_non_empty(self, prompt_name: str, prompt: str) -> None:
        """Each recommendation prompt is a non-empty string with len > 100."""
        assert isinstance(prompt, str)
        assert len(prompt) > 100, (
            f"{prompt_name} prompt is only {len(prompt)} chars, expected > 100"
        )

    def test_prompt_under_budget(self, prompt_name: str, prompt: str) -> None:
        """Each prompt is under 8000 characters."""
        assert len(prompt) < TOKEN_BUDGET_CHARS, (
            f"{prompt_name} prompt is {len(prompt)} chars, exceeds budget of {TOKEN_BUDGET_CHARS}"
        )

    def test_prompt_has_version_header(self, prompt_name: str, prompt: str) -> None:
        """Each prompt includes a VERSION header in the prompt text."""
        assert "VERSION" in prompt, f"{prompt_name} prompt is missing VERSION header"

    def test_prompt_has_rules_appendix(self, prompt_name: str, prompt: str) -> None:
        """Recommendation prompts include PROMPT_RULES_APPENDIX (unlike desk prompts)."""
        assert "Confidence calibration" in prompt, (
            f"{prompt_name} prompt does not contain PROMPT_RULES_APPENDIX"
        )
        assert "Data citation rules" in prompt, (
            f"{prompt_name} prompt is missing data citation rules from appendix"
        )

    def test_prompt_ends_with_appendix(self, prompt_name: str, prompt: str) -> None:
        """Each prompt ends with PROMPT_RULES_APPENDIX content."""
        assert prompt.endswith(PROMPT_RULES_APPENDIX), (
            f"{prompt_name} prompt does not end with PROMPT_RULES_APPENDIX"
        )

    def test_prompt_no_think_tags_allowed(self, prompt_name: str, prompt: str) -> None:
        """Prompts instruct agents not to include think tags."""
        assert "<think>" not in prompt.lower() or "do not include <think>" in prompt.lower(), (
            f"{prompt_name} prompt contains raw <think> tags"
        )

    def test_prompt_has_direction_field(self, prompt_name: str, prompt: str) -> None:
        """Each prompt instructs on the direction output field."""
        assert "direction" in prompt

    def test_prompt_has_confidence_field(self, prompt_name: str, prompt: str) -> None:
        """Each prompt instructs on the confidence output field."""
        assert "confidence" in prompt

    def test_prompt_has_key_factors_field(self, prompt_name: str, prompt: str) -> None:
        """Each prompt instructs on the key_factors output field."""
        assert "key_factors" in prompt

    def test_prompt_has_risks_field(self, prompt_name: str, prompt: str) -> None:
        """Each prompt instructs on the risks output field."""
        assert "risks" in prompt


# ---------------------------------------------------------------------------
# VERSION header format in source files
# ---------------------------------------------------------------------------


class TestVersionHeaders:
    """Verify VERSION headers in recommendation prompt source files."""

    _PROMPT_SOURCES = [
        ("trend", "options_arena.agents.prompts.recommend_trend"),
        ("volatility", "options_arena.agents.prompts.recommend_volatility"),
        ("flow", "options_arena.agents.prompts.recommend_flow"),
        ("fundamental", "options_arena.agents.prompts.recommend_fundamental"),
        ("risk", "options_arena.agents.prompts.recommend_risk"),
        ("contrarian", "options_arena.agents.prompts.recommend_contrarian"),
    ]

    @pytest.mark.parametrize(
        ("agent_name", "module_path"),
        _PROMPT_SOURCES,
        ids=[name for name, _ in _PROMPT_SOURCES],
    )
    def test_version_header_in_source(self, agent_name: str, module_path: str) -> None:
        """Each recommendation prompt source file contains '# VERSION: vX.Y'."""
        module = importlib.import_module(module_path)
        source_file = inspect.getfile(module)
        with open(source_file, encoding="utf-8") as f:
            source = f.read()

        assert _VERSION_RE.search(source), (
            f"{agent_name} prompt source ({module_path}) is missing '# VERSION: vX.Y' header"
        )


# ---------------------------------------------------------------------------
# Domain-specific field tests
# ---------------------------------------------------------------------------


class TestTrendDomainFields:
    """Trend prompt references TrendAssessment-specific fields."""

    def test_references_trend_strength(self) -> None:
        assert "trend_strength" in RECOMMEND_TREND_PROMPT

    def test_references_momentum_signal(self) -> None:
        assert "momentum_signal" in RECOMMEND_TREND_PROMPT

    def test_references_adx(self) -> None:
        """Trend prompt references ADX as a key trend indicator."""
        assert "ADX" in RECOMMEND_TREND_PROMPT


class TestVolatilityDomainFields:
    """Volatility prompt references VolatilityAssessment-specific fields."""

    def test_references_iv_regime(self) -> None:
        assert "iv_regime" in RECOMMEND_VOLATILITY_PROMPT

    def test_references_vol_skew_assessment(self) -> None:
        assert "vol_skew_assessment" in RECOMMEND_VOLATILITY_PROMPT

    def test_references_term_structure_shape(self) -> None:
        assert "term_structure_shape" in RECOMMEND_VOLATILITY_PROMPT

    def test_references_iv_rank(self) -> None:
        """Volatility prompt references IV Rank as a key metric."""
        assert "IV Rank" in RECOMMEND_VOLATILITY_PROMPT


class TestFlowDomainFields:
    """Flow prompt references FlowAssessment-specific fields."""

    def test_references_flow_bias(self) -> None:
        assert "flow_bias" in RECOMMEND_FLOW_PROMPT

    def test_references_unusual_activity_noted(self) -> None:
        assert "unusual_activity_noted" in RECOMMEND_FLOW_PROMPT

    def test_references_put_call_ratio(self) -> None:
        """Flow prompt references put/call ratio as a key metric."""
        assert "put/call ratio" in RECOMMEND_FLOW_PROMPT.lower()


class TestFundamentalDomainFields:
    """Fundamental prompt references FundamentalAssessment-specific fields."""

    def test_references_valuation_signal(self) -> None:
        assert "valuation_signal" in RECOMMEND_FUNDAMENTAL_PROMPT

    def test_references_catalyst_timeline(self) -> None:
        assert "catalyst_timeline" in RECOMMEND_FUNDAMENTAL_PROMPT

    def test_references_earnings(self) -> None:
        """Fundamental prompt references earnings as a key catalyst."""
        assert "earnings" in RECOMMEND_FUNDAMENTAL_PROMPT.lower()


class TestRiskDomainFields:
    """Risk prompt references RiskDeskAssessment-specific fields."""

    def test_references_max_position_pct(self) -> None:
        assert "max_position_pct" in RECOMMEND_RISK_PROMPT

    def test_references_hedging_suggestion(self) -> None:
        assert "hedging_suggestion" in RECOMMEND_RISK_PROMPT

    def test_references_portfolio_correlation_note(self) -> None:
        assert "portfolio_correlation_note" in RECOMMEND_RISK_PROMPT

    def test_references_position_sizing(self) -> None:
        """Risk prompt references position sizing guidance."""
        assert "position sizing" in RECOMMEND_RISK_PROMPT.lower() or (
            "position_size" in RECOMMEND_RISK_PROMPT.lower()
        )


class TestContrarianDomainFields:
    """Contrarian prompt references ContrarianAssessment-specific fields."""

    def test_references_consensus_challenged(self) -> None:
        assert "consensus_challenged" in RECOMMEND_CONTRARIAN_PROMPT

    def test_references_contrarian_thesis(self) -> None:
        assert "contrarian_thesis" in RECOMMEND_CONTRARIAN_PROMPT

    def test_references_consensus(self) -> None:
        """Contrarian prompt references consensus as the view to challenge."""
        assert "consensus" in RECOMMEND_CONTRARIAN_PROMPT.lower()
