---
name: agent-resilience
status: completed
created: 2026-03-07T02:28:07Z
completed: 2026-03-07T05:00:00Z
progress: 100%
prd: .claude/prds/agent-resilience.md
github: https://github.com/jobu711/options_arena/issues/324
---

# Epic: agent-resilience

## Overview

Remove the enrichment gate in `orchestrator.py` that conditionally skips Flow and Fundamental agents when `enrichment_ratio() == 0.0`. Both agents already have prompts designed to handle missing OpenBB data — they analyze scan-derived signals (put/call ratio, OI, volume, earnings, IV metrics) which are always available. This is a small, surgical change: 2 lines of gate logic, ~4 sentences of prompt additions, ~5 lines of context block annotation, and tests.

## Architecture Decisions

- **Keep `has_enrichment` for logging**: Repurpose the variable as a log annotation rather than deleting it. Observability of "running without enrichment" is valuable for debugging.
- **No model changes**: `FlowThesis` and `FundamentalThesis` already handle None fields via optional fields and `_render_optional()` null omission in context blocks.
- **No threshold changes**: Phase 1 failure thresholds (`>= 4` for full fallback, `< 2` for contrarian) remain unchanged. Previously, skipped agents were already counted as failures — now they'll actually run and may succeed, reducing failure counts.
- **Prompt additions are additive**: Brief instructions telling agents to focus on scan-derived data when enrichment sections are absent. No prompt restructuring.

## Technical Approach

### Backend Changes

**orchestrator.py** (3 lines changed):
- Line 1086: `if flow_output is None and has_enrichment:` → `if flow_output is None:`
- Line 1105: `if fundamental_output is None and has_enrichment:` → `if fundamental_output is None:`
- Add `logger.info()` when `not has_enrichment` to note agents running without enrichment

**flow_agent.py** (1-2 sentences added to system prompt):
- Add instruction: "If the Unusual Options Flow section is absent, focus analysis on put/call ratio, OI concentration from contracts, and volume indicators."

**fundamental_agent.py** (1-2 sentences added to system prompt):
- Add instruction: "If the Fundamental Profile section is absent, focus on earnings calendar, dividend impact, and IV crush risk assessment."

**_parsing.py** (context block annotation):
- In `render_context_block()`, when `context.enrichment_ratio() == 0.0`, append a note: "Note: Enrichment data not available for this ticker. Analysis based on scan-derived indicators."

### Frontend Components
- None required. The UI already displays whatever agents are present in `DebateResult`.

### Infrastructure
- No deployment changes. ~30% more Groq API tokens for affected tickers (2 additional LLM calls).

## Implementation Strategy

Two waves, sequentially:

1. **Wave 1 — Gate removal + prompt enhancement**: Remove enrichment gate, add prompt instructions, add context block note. All in one commit since changes are interdependent.
2. **Wave 2 — Testing**: Add tests verifying agents run with zero enrichment, `agents_completed == 6`, and agreement score includes all 6 agents.

## Task Breakdown Preview

- [ ] Task 1: Remove enrichment gate and add prompt/context enhancements (orchestrator.py, flow_agent.py, fundamental_agent.py, _parsing.py)
- [ ] Task 2: Add tests for zero-enrichment agent execution (test_orchestrator_v2.py, test_flow.py, test_fundamental.py)
- [ ] Task 3: Verification — lint, typecheck, full test suite, manual review

## Dependencies

### External
- **Groq API**: 2 additional LLM calls per debate for previously-gated tickers (~30% more tokens)

### Internal
- No prerequisite work. All touched files are on master and stable.

## Success Criteria (Technical)

- `agents_completed == 6` for all full debates (was 4 for some tickers)
- Flow agent produces valid `FlowThesis` JSON with zero enrichment
- Fundamental agent produces valid `FundamentalThesis` JSON with zero enrichment
- No regression when enrichment data IS available
- `agent_agreement_score` computed over 6 agents (not 4)
- All existing tests pass (3,921 unit + 38 E2E)
- `ruff check`, `ruff format`, `mypy --strict` all pass

## Estimated Effort

**S (Small)** — 3-4 files modified, ~20 lines of production code, ~50-80 lines of test code. Single session. No new models, APIs, or infrastructure.

## Tasks Created

- [ ] #325 - Remove enrichment gate and enhance prompts (parallel: false)
- [ ] #326 - Add tests for zero-enrichment agent execution (parallel: false, depends on #325)
- [ ] #327 - Final verification and lint (parallel: false, depends on #325, #326)

Total tasks: 3
Parallel tasks: 0
Sequential tasks: 3
Estimated total effort: 3.5 hours

## Test Coverage Plan

Total test files planned: 3 (test_orchestrator_v2.py, test_flow.py, test_fundamental.py)
Total test cases planned: 7
