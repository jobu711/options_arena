---
name: prompt-engineering-v2
status: backlog
created: 2026-03-09T16:45:40Z
progress: 0%
prd: .claude/prds/prompt-engineering-v2.md
github: https://github.com/jobu711/options_arena/issues/402
---

# Epic: prompt-engineering-v2

## Overview

Extract all 6 remaining inline agent system prompts into `agents/prompts/`, build a
regression test suite that catches structural/quality regressions, and add few-shot golden
examples to the 6 active v2 agents. Creates a maintainable, testable prompt library.

## Architecture Decisions

- **Extraction is mechanical**: Move string constants, update imports. Zero behavior change.
  Follow existing pattern from `prompts/trend_agent.py` and `prompts/contrarian_agent.py`.
- **One file per agent in `prompts/`**: Each exports a single `{AGENT}_SYSTEM_PROMPT` constant.
- **`RISK_STRATEGY_TREE` moves to `prompts/risk.py`**: Co-located with risk prompts it belongs to.
- **`_REBUTTAL_PREFIX/SUFFIX` stay in `bull.py`**: Dynamic injection, not prompt template.
- **`PROMPT_RULES_APPENDIX` stays in `_parsing.py`**: Shared across all agents, imported by prompt files.
- **Token counting via heuristic**: `len(prompt) / 4` (~4 chars/token). No `tiktoken` dependency.
  Budget: < 2000 tokens ≈ < 8000 chars per prompt.
- **Few-shot only for 6 active v2 agents**: trend, volatility, flow, fundamental, risk (v2),
  contrarian. Bull/Bear are v1 legacy — extracted but no few-shot.
- **Both Risk v1 and v2 extracted**: `RISK_SYSTEM_PROMPT` (fallback) + `RISK_V2_SYSTEM_PROMPT`
  (active). Only v2 gets a few-shot example.

## Technical Approach

### Prompt Extraction (Wave 1)

For each of the 6 agents (bull, bear, volatility, flow, fundamental, risk):

1. Create `agents/prompts/{agent}.py` with module docstring, import of
   `PROMPT_RULES_APPENDIX` from `_parsing.py`, and the prompt constant
2. For risk: also move `RISK_STRATEGY_TREE` and `RISK_V2_SYSTEM_PROMPT`
3. Update agent module to `from options_arena.agents.prompts.{agent} import {AGENT}_SYSTEM_PROMPT`
4. Verify byte-identical prompt text before/after
5. Run existing agent tests to confirm zero behavior change

### Documentation & Re-exports (Wave 2)

1. Create `agents/prompts/CLAUDE.md` documenting the prompt library conventions
2. Update `agents/prompts/__init__.py` with re-exports for all 8 prompt constants
   so consumers can `from options_arena.agents.prompts import BULL_SYSTEM_PROMPT`

### Regression Test Suite (Wave 3)

**`tests/unit/agents/test_prompt_structure.py`** — parametrized across all 8 prompts:
- Version header present (`# VERSION: vX.Y`)
- Token count within budget (< 8000 chars ≈ 2000 tokens)
- `PROMPT_RULES_APPENDIX` text present in concatenated prompt
- `RISK_STRATEGY_TREE` present only in risk prompt
- Required sections (JSON schema block, rules)

**`tests/unit/agents/test_prompt_quality.py`** — TestModel-based:
- Each prompt + mock context produces valid structured output
- Citation density > 0% on mock context
- No `<think>` tags in output (validator chain working)

### Few-Shot Examples (Wave 4)

For each of the 6 active v2 agents:
1. Add `## Example Output\n{json block}` section before `PROMPT_RULES_APPENDIX` concatenation
2. Use "ACME" ticker (anonymized), demonstrate 3+ context label citations
3. Calibrated confidence (0.4-0.7 range, not extreme)
4. Groq/Llama-optimized formatting (JSON blocks)
5. Version bump (e.g., v1.0 → v2.0)
6. Verify total prompt stays within 8000-char budget

## Implementation Strategy

### Wave 1: Extraction (2 parallel issues)
Mechanical extraction — zero behavior change. Can parallelize.

### Wave 2: Documentation (1 issue)
Quick follow-up: CLAUDE.md + re-exports. Depends on Wave 1.

### Wave 3: Test Suite (1 issue)
Structure + quality tests in 2 test files. Depends on Wave 1 (imports extracted constants).

### Wave 4: Few-Shot Examples (2 parallel issues)
Creative prompt work — craft golden examples. Depends on Wave 1 (prompts in `prompts/`).

### Risk Mitigation
- Extraction is reversible (git revert)
- Few-shot may push prompts over token budget → measure before/after
- TestModel may not perfectly simulate Llama behavior → quality tests are safety nets, not guarantees

## Task Breakdown Preview

- [ ] Task 1: Extract bull + bear + volatility prompts to `agents/prompts/`
- [ ] Task 2: Extract flow + fundamental + risk prompts to `agents/prompts/`
- [ ] Task 3: Create `agents/prompts/CLAUDE.md` + update `__init__.py` re-exports
- [ ] Task 4: Prompt regression test suite (structure + token budget + quality)
- [ ] Task 5: Add few-shot examples to trend, contrarian, and volatility prompts
- [ ] Task 6: Add few-shot examples to flow, fundamental, and risk prompts

## Dependencies

### Internal
- `agents/_parsing.py` — `PROMPT_RULES_APPENDIX`, `compute_citation_density()` (no changes)
- `agents/prompts/trend_agent.py`, `contrarian_agent.py` — reference pattern (no changes)
- Existing agent tests in `tests/unit/agents/` — must pass unchanged after extraction

### External
- None

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Prompt extraction | 8/8 constants in `agents/prompts/` |
| Existing tests | 100% pass after extraction (zero regressions) |
| New regression tests | 25+ tests, 100% pass |
| Token budget | All prompts < 8000 chars (≈ 2000 tokens) |
| Few-shot coverage | 6/6 active v2 agents have golden examples |
| Re-exports | `from options_arena.agents.prompts import X` works for all 8 |

## Estimated Effort

**Total: M (3-4 days)**
- Wave 1 (Extraction): S — 2-3 hours, mechanical, 2 parallel issues
- Wave 2 (Docs): XS — 30 min
- Wave 3 (Tests): M — 1 day
- Wave 4 (Few-shot): M — 1-2 days, creative prompt crafting

**Critical path**: Wave 1 → Wave 3/4 (parallel) → done.
Wave 2 can run alongside Wave 3/4.

## Tasks Created

- [ ] #403 - Extract bull, bear, and volatility prompts (parallel: true)
- [ ] #404 - Extract flow, fundamental, and risk prompts (parallel: true)
- [ ] #405 - Create prompts CLAUDE.md and update re-exports (parallel: false, depends: #403, #404)
- [ ] #406 - Prompt regression test suite (parallel: true, depends: #403, #404, #405)
- [ ] #408 - Few-shot examples for trend, contrarian, and volatility (parallel: true, depends: #403, #404)
- [ ] #409 - Few-shot examples for flow, fundamental, and risk (parallel: true, depends: #403, #404)

Total tasks: 6
Parallel tasks: 5 (#403, #404 in Wave 1; #406, #408, #409 in Wave 3/4)
Sequential tasks: 1 (#405 gates on Wave 1)
Estimated total effort: 12-18 hours

## Test Coverage Plan

Total test files planned: 2
Total test cases planned: 25+
