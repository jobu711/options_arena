---
name: ai-agency-all-desks
status: backlog
created: 2026-03-17T14:37:45Z
progress: 0%
prd: .claude/prds/ai-agency-evolution.md
parent_epic: ai-agency-evolution
epic_number: 3
dependencies: [ai-agency-desk-foundation]
parallelizable_with: [ai-agency-advisor-routing]
github: [Will be updated when synced to GitHub]
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
