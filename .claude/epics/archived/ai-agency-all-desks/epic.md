---
name: ai-agency-all-desks
status: completed
created: 2026-03-17T14:37:45Z
progress: 100%
updated: 2026-03-20T12:00:00Z
completed: 2026-03-20T12:00:00Z
prd: .claude/prds/ai-agency-evolution.md
parent_epic: ai-agency-evolution
epic_number: 3
dependencies: [ai-agency-desk-foundation]
parallelizable_with: [ai-agency-advisor-routing]
github: https://github.com/jobu711/options_arena/issues/586
---

# Epic 3: All Desks Online

## Overview

Build the remaining 5 desk agents (Trend, Flow, Fundamental, Contrarian, Research) with base service tools and interactive prompts. After this epic, all 7 desks are operational with base-tier tools.

## Architecture Decisions

- Follow exact pattern from Epic 1 (vol/risk desks): `Agent[DeskDeps, str]` at module level, `FunctionToolset` via builder
- Contrarian is deliberately tool-light (2 tools: fetch_quote, fetch_debate_history) — debates prior analysis
- Research desk gets curated cross-domain tools (6 base tools, budget 5) — not all tools from all desks
- Each desk's prompt emphasizes its domain and available tools
- All desks registered in `agents/__init__.py` re-exports

## Technical Approach

### New Desk Agents (5 files)
- `agents/trend_desk.py` — base tools: fetch_quote, fetch_related_ohlcv, compute_indicator_on_demand
- `agents/flow_desk.py` — base tools: fetch_quote, fetch_chain_summary, fetch_unusual_activity
- `agents/fundamental_desk.py` — base tools: fetch_quote, fetch_earnings_history, fetch_sector_comparison
- `agents/contrarian_desk.py` — base tools: fetch_quote, fetch_debate_history
- `agents/research_desk.py` — curated base tools (6 total), budget 5

### Toolset Builders (in `_toolsets.py`)
- `build_trend_toolset()`, `build_flow_toolset()`, `build_fundamental_toolset()`, `build_contrarian_toolset()`, `build_research_toolset()`
- New base tool wrappers: `fetch_related_ohlcv`, `compute_indicator_on_demand`, `fetch_chain_summary`, `fetch_unusual_activity`, `fetch_earnings_history`, `fetch_sector_comparison`, `fetch_debate_history`

### Desk Prompts (5 files)
- `agents/prompts/desk_trend.py`, `desk_flow.py`, `desk_fundamental.py`, `desk_contrarian.py`, `desk_research.py`

### Frontend
- `DeskSelector.vue` — Direct desk access with desk descriptions and capability indicators

## Task Breakdown Preview

- [ ] Trend + Flow desk agents, toolsets, prompts, tests
- [ ] Fundamental + Contrarian desk agents, toolsets, prompts, tests
- [ ] Research desk (curated cross-domain tools, budget 5) + tests
- [ ] DeskSelector.vue frontend component
- [ ] Integration tests: all 7 desks via TestModel

## Dependencies

- Epic 1 (Desk Foundation) — DeskDeps, toolset builder pattern, base tool wrappers

## Success Criteria

- All 7 desks respond to domain-appropriate queries
- Research desk uses curated subset (not all tools from all desks)
- Contrarian provides dissent without running its own computations
- Each desk's tools_used reflects only domain-relevant tools
- ~30+ new tests

## Estimated Effort

4-5 issues, ~2-3 implementation sessions

## Tasks Created

- [ ] #587 - Trend + Flow desk agents with tools, prompts, and unit tests (parallel: true)
- [ ] #588 - Fundamental + Contrarian desk agents with tools, prompts, and unit tests (parallel: true)
- [ ] #589 - Research desk with curated cross-domain tools (parallel: false, depends: #587, #588)
- [ ] #590 - Routing wiring, re-exports, and integration tests for all 7 desks (parallel: false, depends: #587, #588, #589)
- [ ] #591 - DeskSelector.vue frontend component (parallel: false, depends: #590)

Total tasks: 5
Parallel tasks: 2 (#587, #588)
Sequential tasks: 3 (#589, #590, #591)
Estimated total effort: 16-24 hours

## Test Coverage Plan

Total test files planned: 6
- tests/unit/agents/test_trend_desk.py
- tests/unit/agents/test_flow_desk.py
- tests/unit/agents/test_fundamental_desk.py
- tests/unit/agents/test_contrarian_desk.py
- tests/unit/agents/test_research_desk.py
- tests/unit/agents/test_routing_all_desks.py
- tests/integration/test_all_desks_integration.py

Total test cases planned: ~55+
