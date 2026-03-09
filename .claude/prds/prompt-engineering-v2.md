---
name: prompt-engineering-v2
description: Extract all agent prompts to agents/prompts/, add regression test suite, and enhance with few-shot examples for improved citation density
status: planned
created: 2026-03-09T17:30:00Z
parent: ai-agent-tune
---

# PRD: prompt-engineering-v2

## Executive Summary

Extract the 6 remaining inline agent system prompts into `agents/prompts/`, build a
regression test suite that catches structural/quality regressions, and add few-shot
golden examples that demonstrate proper data citation. This creates a maintainable,
testable prompt library where every change is validated automatically.

Split from the `ai-agent-tune` PRD. This epic has zero file overlap with its sibling
`agent-calibration` and can be developed fully in parallel.

## Problem Statement

Agent prompts are scattered across 8 agent modules with no unified structure:

- **Only 2 of 8 prompts extracted** — `trend_agent.py` and `contrarian_agent.py` live in
  `agents/prompts/`. The other 6 are inline in their agent files.
- **No regression tests** — A prompt change can silently break output structure, remove
  required sections, or exceed token budgets. No tests catch this.
- **No quality benchmarks** — Citation density averages ~20% with no enforcement. Agents
  frequently make vague claims without referencing specific data values.
- **No few-shot examples** — The LLM has no concrete pattern to follow for ideal output.

## User Stories

### US1: Developer extracts and organizes all prompts
**As** a developer maintaining agent prompts,
**I want** all prompts in a single `agents/prompts/` directory,
**So that** I can find, compare, and edit prompts without navigating 8 separate agent files.

**Acceptance criteria:**
- All 8 prompts in `agents/prompts/` with one file per agent
- Agent modules import from `prompts/` instead of defining inline
- Zero behavior change — prompt text byte-identical before and after
- `from options_arena.agents.prompts import BULL_SYSTEM_PROMPT` works for all 8

### US2: Developer catches prompt regressions automatically
**As** a developer iterating on agent prompts,
**I want** automated tests that catch prompt regressions,
**So that** I can change prompts confidently without degrading output quality.

**Acceptance criteria:**
- Structure tests validate: version header, required sections, PROMPT_RULES_APPENDIX presence
- Token budget tests ensure prompts fit within budget (< 2000 tokens)
- Quality tests verify each prompt produces valid structured output via `TestModel`
- Citation density > 0% on mock context (prompts instruct citation)

### US3: Developer adds few-shot examples to prompts
**As** a developer tuning agent output quality,
**I want** golden output examples embedded in prompts,
**So that** the LLM has concrete patterns to follow for each agent role.

**Acceptance criteria:**
- Each active agent prompt (6 v2 agents) includes 1 few-shot example
- Examples use "ACME" ticker (anonymized), demonstrate proper citation density
- Token budget accommodates examples (< 2000 per prompt)
- Version bumped on each modified prompt

## Requirements

### Functional Requirements

#### FR1: Prompt Extraction
- Extract inline prompts from `bull.py`, `bear.py`, `risk.py`, `volatility.py`,
  `flow_agent.py`, `fundamental_agent.py` into `agents/prompts/`
- One file per agent: `bull.py`, `bear.py`, `risk.py`, `volatility.py`, `flow.py`,
  `fundamental.py`
- Already extracted (no changes): `trend_agent.py`, `contrarian_agent.py`
- Each prompt file exports a single constant: `{AGENT}_SYSTEM_PROMPT`
- `PROMPT_RULES_APPENDIX` stays in `_parsing.py` (shared across all agents)
- `RISK_STRATEGY_TREE` moves to `agents/prompts/risk.py`
- `_REBUTTAL_PREFIX`/`_REBUTTAL_SUFFIX` stay in `bull.py` (dynamic injection, not prompt template)
- Agent modules become thin: just Agent instance + system_prompt decorator + output_validator

#### FR2: Prompt Regression Test Suite
- `tests/unit/agents/test_prompt_structure.py` validates all 8 prompt constants:
  - Version header present (`# VERSION: vX.Y`)
  - Token count within budget (< 2000 tokens)
  - Required sections present (JSON schema, rules block)
  - `PROMPT_RULES_APPENDIX` concatenated (not missing)
  - `RISK_STRATEGY_TREE` present only in risk prompt
- `tests/unit/agents/test_prompt_quality.py` — `TestModel`-based quality tests:
  - Each prompt + mock context produces valid structured output
  - Citation density > 0% threshold on mock context
  - No `<think>` tags in output (validator chain working)

#### FR3: Few-Shot Examples
- Add 1 golden output example per active v2 agent prompt (6 agents)
- Examples sourced from realistic market data, anonymized to "ACME"
- Examples demonstrate: proper data citation (3+ context labels referenced),
  calibrated confidence (not extreme 0.9+), appropriate structure
- Format: `## Example Output\n{json block}` appended before `PROMPT_RULES_APPENDIX`
- Groq/Llama-optimized formatting (JSON blocks, not markdown tables)
- Version bump on each prompt (e.g., v1.0 -> v2.0)

### Non-Functional Requirements

#### NFR1: Zero Runtime Impact
- Prompt extraction is compile-time constant assignment — no runtime cost
- Few-shot examples increase prompt size but stay within 8192 context window headroom

#### NFR2: Backward Compatibility
- Prompt extraction preserves exact text (no content changes in extraction step)
- Few-shot additions are a separate step after extraction (distinct version bump)
- All existing agent tests pass unchanged after extraction

## Implementation Phases

### Wave 1: Extraction (3 parallel issues)
Extract all 6 inline prompts. Zero behavior change. Each issue handles 2 agents.

### Wave 2: Documentation
Create `agents/prompts/CLAUDE.md`, update `__init__.py` re-exports.

### Wave 3: Test Suite (3 issues)
Structure tests, token budget tests, quality tests with TestModel.

### Wave 4: Few-Shot Examples (3 parallel issues)
Add golden examples to each prompt. Version bump. Measure improvement.

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Prompt extraction | 8/8 in `agents/prompts/` | File count |
| Regression tests | 100% pass rate | `pytest tests/unit/agents/test_prompt_*` |
| Token budget | All prompts < 2000 tokens | Token budget tests |
| Few-shot coverage | 6/6 active agents have examples | File inspection |
| Citation density | Prompts instruct citation > 30% | `compute_citation_density()` target |
| Test count | 25+ new tests | Test count |

## Constraints

- **Groq-first**: Prompt optimization targets Llama 3.3 70B via Groq. Anthropic variants deferred.
- **No real LLM calls in CI**: Uses `TestModel` for quality tests.
- **Token budget**: System prompts may grow from ~1500 to ~2000 with few-shot. 8192 context has headroom.
- **Bull/Bear are v1 legacy**: Still extracted for completeness, but few-shot examples only
  added to the 6 active v2 agents (trend, volatility, flow, fundamental, risk, contrarian).

## Out of Scope

- Agent calibration and accuracy tracking (sibling epic: `agent-calibration`)
- Auto-tune vote weights (sibling epic: `agent-calibration`)
- Anthropic/Claude prompt variants
- Real-time A/B testing infrastructure
- Vue dashboard for prompt metrics

## Dependencies

### Internal
- `PROMPT_RULES_APPENDIX` in `_parsing.py` — stays in place, imported by prompt files
- `RISK_STRATEGY_TREE` in `risk.py` — moves to `prompts/risk.py`
- `compute_citation_density()` in `_parsing.py` — used by quality tests
- Existing `trend_agent.py` and `contrarian_agent.py` in `prompts/` — reference pattern

### External
- None

## Effort Estimate

**Total: M (3-4 days)**
- Wave 1: S (2-3 hours) — mechanical extraction, 3 parallel issues
- Wave 2: XS (30 min) — docs and re-exports
- Wave 3: M (1 day) — test suite creation
- Wave 4: M (1-2 days) — prompt crafting with citation examples
