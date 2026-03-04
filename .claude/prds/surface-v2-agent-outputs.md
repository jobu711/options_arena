---
name: surface-v2-agent-outputs
description: Surface all 6 v2 debate agent outputs (flow, fundamental, risk_v2, contrarian) across CLI, API, web UI, and export
status: planned
created: 2026-03-04T09:40:38Z
---

# PRD: Surface V2 Agent Outputs in Debate Display

## Executive Summary

The 6-agent v2 debate protocol computes outputs from 6 specialized agents (trend, volatility, flow, fundamental, risk_v2, contrarian) but only surfaces 2 of them to the user. Four agent outputs are computed, paid for in tokens, and then discarded before reaching any display layer. This PRD adds the missing plumbing — model fields, persistence, API serialization, CLI rendering, web UI cards, and export sections — so all 6 agent outputs are visible everywhere debates are displayed.

## Problem Statement

**Current behavior in v2 protocol:**
- `bull_response` = trend agent output (renders with misleading "BULL" label)
- `bear_response` = always a synthetic placeholder with text "Placeholder for v2 protocol" (orchestrator.py ~line 1803-1809)
- `vol_response` = volatility output (works correctly)
- `thesis` = `ExtendedTradeThesis` (works, includes contrarian_dissent + agreement score)
- Flow, fundamental, risk_v2, and contrarian agent outputs are **discarded** — never persisted, never shown

**Why this matters now:** Users running v2 debates see only 2 real agent panels (trend labeled as "bull", volatility) plus a synthetic bear panel with no real content. The full 6-agent analysis is computed and paid for but never displayed. This undermines the value proposition of the v2 protocol.

## User Stories

### US-1: CLI User Sees All V2 Agents
**As** a CLI user running `options-arena debate AAPL`,
**I want** to see all 6 agent panels (trend, volatility, flow, fundamental, risk assessment, contrarian) when using the v2 protocol,
**So that** I get the full analysis I'm paying for in API tokens.

**Acceptance Criteria:**
- V2 debate renders 6 distinct colored panels + verdict panel
- Trend panel (green) replaces misleading "BULL" label
- Synthetic "BEAR" placeholder panel is not shown for v2
- V1 debates continue rendering identically to today

### US-2: Web UI User Sees All V2 Agents
**As** a web UI user viewing a debate result,
**I want** to see specialized cards for each of the 6 agents with domain-specific fields,
**So that** I can review GEX interpretation, earnings assessment, risk mitigants, and contrarian scenarios.

**Acceptance Criteria:**
- DebateResultPage detects v2 protocol and renders 6 agent cards
- Each card displays domain-specific fields (not a generic agent response shape)
- Flow card shows GEX, smart money, OI analysis, volume confirmation
- Fundamental card shows catalyst impact, earnings assessment, IV crush risk
- Risk card shows risk level, PoP estimate, max loss, key risks + mitigants
- Contrarian card shows dissent direction, primary challenge, overlooked risks, alternative scenario
- V1 layout unchanged

### US-3: Persisted V2 Results Are Retrievable
**As** a user reviewing past debates,
**I want** v2 agent outputs to be persisted in SQLite and returned by the API,
**So that** historical v2 debates display all 6 agents, not just 2.

**Acceptance Criteria:**
- 5 new nullable columns on `ai_theses` table (flow_json, fundamental_json, risk_v2_json, contrarian_json, debate_protocol)
- V2 debates persist all 4 new agent outputs as JSON
- GET `/api/debate/{id}` returns all v2 fields when present
- V1 debates have `None` for new columns (backward compatible)

### US-4: Exported Reports Include All V2 Agents
**As** a user exporting a debate to markdown/PDF,
**I want** the export to include all 6 agent sections for v2 debates,
**So that** the exported report matches what I see on screen.

**Acceptance Criteria:**
- Markdown export includes Flow, Fundamental, Risk Assessment, and Contrarian sections for v2
- "Bull Case" renamed to "Trend Analysis" for v2
- Synthetic "Bear Case" omitted for v2
- V1 export unchanged

## Requirements

### Functional Requirements

#### FR-1: DebateResult Model Extension
- Add 5 optional fields to `DebateResult` in `_parsing.py`:
  - `flow_response: FlowThesis | None = None`
  - `fundamental_response: FundamentalThesis | None = None`
  - `risk_v2_response: RiskAssessment | None = None`
  - `contrarian_response: ContrarianThesis | None = None`
  - `debate_protocol: str = "v1"`
- All fields have `None`/`"v1"` defaults — backward compatible with frozen model

#### FR-2: Database Migration
- New migration `018_add_v2_agent_columns.sql`
- 5 ALTER TABLE ADD COLUMN statements (all nullable with defaults)
- No data migration required — existing rows get defaults

#### FR-3: Repository Layer
- `DebateRow` dataclass: +5 fields with defaults
- `save_debate()`: +5 parameters for new columns
- `_row_to_debate_row()`: extract new columns from row

#### FR-4: Orchestrator Wiring
- `_run_v2_agents()`: populate new `DebateResult` fields from agent outputs
- `_persist_result()`: serialize v2 fields to JSON and pass to repository
- Set `debate_protocol="v2"` on v2 results

#### FR-5: CLI Rendering
- 4 new render functions: `render_flow_panel()`, `render_fundamental_panel()`, `render_risk_v2_panel()`, `render_contrarian_panel()`
- Each returns a Rich `Panel` with distinct border color (orange, teal, blue, yellow)
- `render_debate_panels()` detects `debate_protocol` and renders appropriate layout

#### FR-6: API Layer
- `DebateResultDetail` schema: +5 fields (`dict[str, object] | None` for JSON-serialized agent outputs)
- `get_debate()` route: parse JSON columns from DebateRow
- `_run_debate_background()`: pass v2 fields to `save_debate()`

#### FR-7: Frontend
- 4 TypeScript interfaces: `FlowThesis`, `FundamentalThesis`, `RiskAssessmentThesis`, `ContrarianThesis`
- `DebateResult` interface: +5 optional fields
- 4 specialized Vue card components (not generic AgentCard — field shapes differ)
- `DebateResultPage.vue`: protocol-aware rendering with v2 grid layout

#### FR-8: Export
- 4 new markdown section renderers for flow, fundamental, risk_v2, contrarian
- `export_debate_markdown()`: protocol-aware section inclusion

### Non-Functional Requirements

- **Backward compatibility**: V1 debates must render identically — zero regression
- **No new dependencies**: Uses only existing packages (Rich, Pydantic, Vue, PrimeVue)
- **Performance**: No additional API calls — v2 outputs already computed, just need plumbing
- **Type safety**: All new fields fully typed, mypy --strict passing

## Success Criteria

| Metric | Target |
|--------|--------|
| V2 CLI debate shows all 6 agent panels | Yes |
| V2 web debate shows all 6 agent cards | Yes |
| V1 debates render identically to before | Yes (zero regression) |
| All existing tests pass | Yes |
| mypy --strict passes | Yes |
| V2 agent outputs persist to SQLite | Yes |
| Historical v2 debates display all agents | Yes |
| Markdown/PDF export includes all v2 sections | Yes |

## Constraints & Assumptions

### Constraints
- `DebateResult` is a frozen Pydantic model — new fields must have defaults
- `AgentCard.vue` accepts only `AgentResponse` shape — v2 models have incompatible field names, requiring 4 specialized card components
- API schemas use `dict[str, object]` not model types directly to avoid circular imports between `api/schemas.py` and `models/analysis.py`

### Assumptions
- The v2 agent output models (`FlowThesis`, `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis`) in `models/analysis.py` are stable and won't change during this work
- SQLite ALTER TABLE ADD COLUMN with nullable defaults is non-breaking for existing data
- The orchestrator's `_run_v2_agents()` already has local variables holding all 4 agent outputs — they just aren't passed to the `DebateResult` constructor

## Out of Scope

- Changing v2 agent prompt templates or output schemas
- Adding new agents beyond the existing 6
- Modifying the v1 debate protocol or display
- Interactive comparison between v1 and v2 results
- Agent output editing or annotation features
- Performance optimization of the v2 debate pipeline itself

## Dependencies

### Internal
- `FlowThesis`, `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis` models in `models/analysis.py` (existing, stable)
- `DebateResult` in `agents/_parsing.py` (will be modified)
- `Repository.save_debate()` in `data/repository.py` (will be extended)
- `_run_v2_agents()` in `agents/orchestrator.py` (will be modified)

### External
- None — no new packages or services required

## Execution Order

| Step | Layer | Files | Dependencies |
|------|-------|-------|-------------|
| 1 | Model | `_parsing.py` | None |
| 2 | Migration | `018_add_v2_agent_columns.sql` | None |
| 3 | Repository | `repository.py` | Steps 1-2 |
| 4 | Orchestrator | `orchestrator.py` | Steps 1, 3 |
| 5 | CLI | `rendering.py` | Step 1 |
| 6 | API | `schemas.py`, `routes/debate.py` | Steps 1, 3 |
| 7 | Frontend | `debate.ts`, 4 cards, `DebateResultPage.vue` | Step 6 |
| 8 | Export | `debate_export.py` | Step 1 |

Steps 5, 6, 7, 8 can be parallelized after step 4 completes.

## Files Modified

| File | Change |
|------|--------|
| `src/options_arena/agents/_parsing.py` | +5 fields on DebateResult |
| `data/migrations/018_add_v2_agent_columns.sql` | New — 5 ALTER TABLE statements |
| `src/options_arena/data/repository.py` | DebateRow +5 fields, save_debate +5 params |
| `src/options_arena/agents/orchestrator.py` | _run_v2_agents populates fields, _persist_result serializes |
| `src/options_arena/cli/rendering.py` | +4 render functions, protocol-aware panels |
| `src/options_arena/api/schemas.py` | DebateResultDetail +5 fields |
| `src/options_arena/api/routes/debate.py` | Parse v2 JSON, pass v2 fields |
| `web/src/types/debate.ts` | +4 interfaces, DebateResult +5 fields |
| `web/src/components/FlowAgentCard.vue` | New — flow agent card |
| `web/src/components/FundamentalAgentCard.vue` | New — fundamental agent card |
| `web/src/components/RiskAgentCard.vue` | New — risk agent card |
| `web/src/components/ContrarianAgentCard.vue` | New — contrarian agent card |
| `web/src/pages/DebateResultPage.vue` | Protocol-aware rendering |
| `src/options_arena/reporting/debate_export.py` | +4 section renderers, protocol-aware |
