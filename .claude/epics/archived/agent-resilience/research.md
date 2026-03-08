# Research: agent-resilience

## PRD Summary

Remove the enrichment gate in `orchestrator.py` that skips Flow and Fundamental agents when `enrichment_ratio() == 0.0`. Both agents should always run because scan-derived data (put/call ratio, max pain, OI, earnings date, IV metrics) is sufficient for meaningful analysis. Add missing-data clarity to prompts and a context block note when enrichment is absent.

## Relevant Existing Modules

- `agents/orchestrator.py` — Contains the enrichment gate at line 1080 (`has_enrichment = context.enrichment_ratio() > 0.0`), conditional spawning at lines 1086 and 1105, failure counting at lines 1203-1224, and agreement/dissenting computation
- `agents/flow_agent.py` — Flow agent definition with `FLOW_SYSTEM_PROMPT` (v1.0). Analyzes GEX, OI, volume patterns. Data sources are already scan-derived
- `agents/fundamental_agent.py` — Fundamental agent definition with `FUNDAMENTAL_SYSTEM_PROMPT` (v1.0). Analyzes earnings, IV crush, short interest, dividends. Core data is scan-derived
- `agents/_parsing.py` — `render_context_block()` builds agent context text. Uses `_render_optional()` to omit None fields. Enrichment sections (Fundamental Profile, Unusual Flow, News Sentiment) are already conditionally omitted when all fields are None
- `models/analysis.py` — `MarketContext.enrichment_ratio()` (lines 218-238) checks 11 OpenBB fields. `FlowThesis` (lines 559-587) and `FundamentalThesis` (lines 635-664) models. `ExtendedTradeThesis` holds `agents_completed`, `agent_agreement_score`, `dissenting_agents`

## Existing Patterns to Reuse

- **Never-raises orchestrator**: `run_debate()` catches all exceptions → data-driven fallback. Flow/fundamental gate removal follows this — if agents fail, they're counted as failures, not crashes
- **Phase 1 batch pattern**: Agents are gathered into `phase1_coros` list and run via `asyncio.gather()`. Removing the gate simply means they're always added to the list
- **`_render_optional()` in _parsing.py**: Already omits None fields from context blocks. No changes needed for null handling — agents already receive clean context
- **TestModel override**: Tests use `agent.override(model=TestModel())` + `ALLOW_MODEL_REQUESTS = False`. New tests should follow this pattern
- **Output validator pattern**: `@agent.output_validator` delegates to shared helpers. No changes needed

## Existing Code to Extend

- **`orchestrator.py` line 1080**: Remove or repurpose `has_enrichment` variable (keep for logging)
- **`orchestrator.py` line 1086**: Change `if flow_output is None and has_enrichment:` → `if flow_output is None:`
- **`orchestrator.py` line 1105**: Change `if fundamental_output is None and has_enrichment:` → `if fundamental_output is None:`
- **`flow_agent.py` system prompt**: Add 1-2 sentences about focusing on scan-derived data when enrichment sections are absent
- **`fundamental_agent.py` system prompt**: Add 1-2 sentences about focusing on earnings/IV/dividends when fundamental profile is absent
- **`_parsing.py` `render_context_block()`**: Add a brief note line when `context.enrichment_ratio() == 0.0`

## Potential Conflicts

- **None identified**. Changes are backward-compatible:
  - External `flow_output`/`fundamental_output` params still bypass spawning (existing behavior preserved)
  - Agent models (FlowThesis, FundamentalThesis) already handle None fields
  - Agreement score computation works on whatever agents are in `agent_directions` dict
  - Phase 1 failure counting already handles flow/fundamental failures

## Open Questions

1. **Should `has_enrichment` be kept for logging?** The variable is useful for observability ("running flow agent without enrichment data"). PRD says "remove or repurpose" — recommend keeping as a log annotation.
2. **Phase 1 failure threshold**: Currently `if phase1_failures >= 4` triggers full fallback, and `if phase1_failures < 2` enables contrarian. With flow/fundamental always running, these thresholds may need review — but since they were already counted as failures when skipped, the behavior is actually unchanged.

## Recommended Architecture

### Wave 1: Gate Removal (orchestrator.py)
1. Keep `has_enrichment` as a log-only variable
2. Remove `and has_enrichment` from lines 1086 and 1105
3. Add `logger.info()` noting when agents run without enrichment data

### Wave 2: Prompt Enhancement (flow_agent.py, fundamental_agent.py, _parsing.py)
1. Add missing-data guidance to Flow system prompt (1-2 sentences)
2. Add missing-data guidance to Fundamental system prompt (1-2 sentences)
3. Add data-availability note to `render_context_block()` when `enrichment_ratio() == 0.0`

### Wave 3: Testing
1. Add test for flow agent running with zero enrichment MarketContext
2. Add test for fundamental agent running with zero enrichment MarketContext
3. Add orchestrator integration test verifying `agents_completed == 6` with zero enrichment
4. Verify agreement score includes flow/fundamental directions

## Test Strategy Preview

- **Existing patterns**: `tests/unit/agents/test_orchestrator_v2.py` uses pre-computed flow/fundamental outputs to bypass the gate. New tests should create a `MarketContext` with zero enrichment and verify agents are spawned
- **TestModel**: All agent tests use `TestModel()` override — no real Groq API calls
- **Fixtures**: Reuse existing `mock_market_context` fixture, ensuring all enrichment fields are None
- **Key assertions**: `agents_completed == 6`, `flow_response is not None`, `fundamental_response is not None`, agreement score computed over 6 agents

## Estimated Complexity

**S (Small)** — 3-4 files modified, ~20 lines of code changed, no new models or APIs. The gate removal is a 2-line change. Prompt additions are 2-4 sentences each. Context block note is ~5 lines. Tests are the bulk of the work but follow established patterns.
