---
name: agent-resilience
description: Remove enrichment gate from Flow and Fundamental agents so they always run, even when OpenBB returns no data for a ticker
status: planned
created: 2026-03-06T17:18:19Z
updated: 2026-03-06T18:00:00Z
---

# PRD: agent-resilience

## Executive Summary

The v2 6-agent debate protocol degrades to 4 agents when OpenBB returns no enrichment data for a given ticker. `orchestrator.py:1538` gates Flow and Fundamental agents on `context.enrichment_ratio() > 0.0` — if all 11 enrichment fields are `None`, both agents are skipped. OpenBB is installed, but certain tickers lack fundamental coverage, the stockgrid extension may fail, or API calls may time out — resulting in 4-agent debates labeled as "6-agent protocol." Both agents already have prompts that handle missing data gracefully, and the scan-derived data they need (put/call ratio, max pain, earnings date, IV metrics) is available regardless of enrichment. This PRD removes the enrichment gate so both agents always run.

## Problem Statement

### What problem are we solving?

1. **4 agents masquerading as 6** — When `enrichment_ratio() == 0.0` for a ticker, the orchestrator skips both Flow and Fundamental agents. The debate is still labeled `debate_protocol = "v2"` with `agents_completed = 4/6`. The UI says "6-agent protocol" but delivers 4-agent analysis.

2. **The gate is too conservative** — `enrichment_ratio()` checks 11 OpenBB-sourced fields (7 fundamental, 3 flow, 1 sentiment). All 11 must be `None` to trigger the gate. This happens when:
   - A ticker has no yfinance fundamental coverage (small-caps, warrants, preferred shares)
   - The stockgrid extension fails or returns no data for the ticker
   - News sentiment API call errors out (timeout, rate limit)
   - All three OpenBB fetch methods fail simultaneously for a ticker

3. **Scan-derived data is sufficient** — The Flow agent's core analysis targets (put/call ratio, max pain distance, OI concentration, volume patterns) come from scan-derived fields, not enrichment. The Fundamental agent can assess earnings proximity, dividend impact, and IV crush risk from scan data. Both agents receive rich context regardless of enrichment status.

4. **Structurally broken enrichment fields** — `net_call_premium` and `net_put_premium` are hardcoded to `None` in `openbb_service.py` because stockgrid doesn't provide them. Two of the 11 enrichment fields can never be populated, making the gate even harder to pass.

### Why is this important now?

- Analytics will show agent agreement scores — with only 4 agents, agreement is artificially inflated
- The 6-agent protocol was the v2 headline feature (Epic 20) — it should deliver 6 agents reliably
- Prompt redesign effort is minimal — prompts already handle missing fields

### Root Cause

The `has_enrichment = context.enrichment_ratio() > 0.0` gate was added as a conservative safety measure during Epic 20 to avoid LLM hallucination on entirely empty enrichment sections. The prompts were designed to handle nulls but were never tested in the zero-enrichment path.

## User Stories

### US-1: Flow Agent Runs for All Tickers
**As a** user running a debate,
**I want** the Flow agent to always run using available data (put/call ratio, OI, volume, max pain),
**So that** every debate includes options flow analysis regardless of OpenBB enrichment status.

**Acceptance Criteria:**
- Flow agent runs when `enrichment_ratio() == 0.0`
- Agent receives scan-derived data: put/call ratio, max pain distance, contract volume/OI, relative volume
- Agent produces valid `FlowThesis` JSON with direction, confidence, and analysis fields
- When enrichment data IS available, it is still passed through (no regression)
- `agents_completed` correctly reflects 6 when all agents run

### US-2: Fundamental Agent Runs for All Tickers
**As a** user running a debate,
**I want** the Fundamental agent to always run using available data (earnings date, dividend yield, IV metrics),
**So that** every debate includes earnings/catalyst analysis regardless of OpenBB enrichment status.

**Acceptance Criteria:**
- Fundamental agent runs when `enrichment_ratio() == 0.0`
- Agent receives scan-derived data: next_earnings, dividend_yield, atm_iv_30d, iv_rank, iv_percentile
- Agent produces valid `FundamentalThesis` JSON
- Missing fields (P/E, debt/equity, growth rates) result in null analysis fields, not hallucination
- When enrichment data IS available, it is still passed through (no regression)

## Requirements

### Functional Requirements

#### FR-1: Remove Enrichment Gate
- In `orchestrator.py:1544`, change:
  ```python
  # Before
  if flow_output is None and has_enrichment:
  # After
  if flow_output is None:
  ```
- Same change at line 1563 for fundamental agent
- Remove or repurpose `has_enrichment` variable (keep for logging/metrics if useful)

#### FR-2: Enhance Prompts for Missing Data Clarity
- Flow agent: Add explicit instruction — "If the Unusual Options Flow section is absent, focus your analysis on put/call ratio, OI patterns from contracts, and volume indicators."
- Fundamental agent: Add — "If the Fundamental Profile section is absent, focus on earnings calendar, dividend impact, and IV crush risk assessment."
- Both agents already handle null fields — these additions make the missing-data path explicit

#### FR-3: Context Block Data Availability Note
- When `enrichment_ratio() == 0.0`, add a brief note to the context block: "Note: Enrichment data not available for this ticker. Analysis based on scan-derived indicators."
- Verify `_parsing.py` already omits section headers when all fields are None (it does via `_render_optional`)

#### FR-4: Verify Agreement Calculation
- With 6 agents always running, `agent_agreement_score` should reflect true 6-agent consensus
- Verify that Flow and Fundamental agent directions are included in majority vote
- Ensure `dissenting_agents` correctly lists flow/fundamental when they disagree

### Non-Functional Requirements

#### NFR-1: Output Quality
- Agents with partial data should self-assess lower confidence (0.3-0.5 range) — this is prompt-guided, not forced
- Agents must NOT hallucinate data that wasn't provided
- Output validators must still pass (valid JSON structure)

#### NFR-2: Performance
- Two additional agent invocations add ~5-10s to debate time (2 LLM calls)
- Acceptable trade-off for complete 6-agent analysis

## Success Criteria

| Metric | Target |
|--------|--------|
| Flow agent runs for tickers with zero enrichment | Yes |
| Fundamental agent runs for tickers with zero enrichment | Yes |
| `agents_completed = 6` for all full debates | Yes (was 4 for some tickers) |
| Valid JSON output from both agents with partial data | Yes |
| No hallucinated financial data | Verified via output review |
| No regression when enrichment data IS available | Yes |

## Constraints & Assumptions

### Constraints
- LLM (Groq/Llama 3.3 70B) must produce valid JSON even with shorter context (fewer data points)
- Additional 2 agents increase Groq API token usage by ~30% per debate for affected tickers
- `retries=2` on agents means failed runs get 2 retry attempts before skipping

### Assumptions
- Llama 3.3 70B can produce meaningful flow analysis from OI/volume/put-call ratio alone
- Llama 3.3 70B can produce meaningful fundamental analysis from earnings/IV data alone
- Lower confidence from partial-data agents is more useful than no analysis at all

## Out of Scope

- **Prompt A/B testing** — measuring quality of partial-data vs full-data agent outputs
- **Confidence scaling by data availability** — agents self-assess confidence; no forced scaling
- **Config toggles for individual agents** — unnecessary for single-user tool; if needed later, add then
- **Fixing structurally-None fields** — `net_call_premium`/`net_put_premium` remain None (stockgrid limitation)

## Dependencies

### Internal
- `orchestrator.py` — enrichment gate removal
- `flow_agent.py` / `fundamental_agent.py` — minor prompt additions
- `_parsing.py` — data-availability note when enrichment absent

### External
- **Groq API** — 2 additional LLM calls per debate for affected tickers (~30% more tokens)

## Technical Design Reference

### File Changes

| File | Action | Purpose |
|------|--------|---------|
| `src/options_arena/agents/orchestrator.py` | Edit | Remove enrichment gate (~3 lines) |
| `src/options_arena/agents/flow_agent.py` | Edit | Add missing-data instruction to system prompt |
| `src/options_arena/agents/fundamental_agent.py` | Edit | Add missing-data instruction to system prompt |
| `src/options_arena/agents/_parsing.py` | Edit | Add data-availability note when enrichment absent |

### Implementation Waves

| Wave | Tasks | Can Parallelize? |
|------|-------|-----------------|
| 1 | Remove enrichment gate in orchestrator | No (core change) |
| 2 | Prompt additions for missing-data clarity + context block note | After Wave 1 |
| 3 | Testing: run debates with low-enrichment tickers, validate JSON, check confidence | After Wave 2 |
