---
name: surface-v2-agent-outputs
status: backlog
created: 2026-03-04T09:49:27Z
progress: 0%
prd: .claude/prds/surface-v2-agent-outputs.md
github: https://github.com/jobu711/options_arena/issues/248
---

# Epic: surface-v2-agent-outputs

## Overview

Plumb the 4 discarded v2 debate agent outputs (flow, fundamental, risk_v2, contrarian) through the entire stack so all 6 agent outputs are visible in CLI, API, web UI, and exported reports. This is a pure wiring task — all agent models exist and produce output; we just need to stop discarding them at the orchestrator boundary and carry them through persistence, serialization, and display layers.

## Architecture Decisions

1. **Separate `debate_protocol` column** — Add `debate_protocol TEXT DEFAULT 'v1'` to `ai_theses` rather than overloading `debate_mode`. `debate_mode` tracks CLI invocation mode; `debate_protocol` tracks agent protocol. Cleaner protocol detection everywhere.

2. **Typed models in backend, JSON strings in frontend** — Backend carries `FlowThesis | None` etc. on `DebateResult`. API serializes to `dict[str, object] | None` in `DebateResultDetail` (avoids circular imports). Frontend receives parsed JSON objects, not raw strings.

3. **4 specialized Vue card components** — V2 agent output models have incompatible field shapes (FlowThesis has `gex_interpretation`, ContrarianThesis has `dissent_direction`, etc.). Existing `AgentCard.vue` only handles `AgentResponse` shape. 4 new purpose-built cards.

4. **Protocol-aware branching** — All display layers (CLI, web, export) check `debate_protocol == "v2"` to decide layout. V1 path is completely unchanged. No `isinstance` heuristics.

5. **Panel colors** — CLI: Trend=green, Flow=bright_magenta, Fundamental=bright_cyan, Volatility=cyan, Risk=bright_blue, Contrarian=yellow, Verdict=blue. Frontend: Flow=#f97316 (orange), Fundamental=#14b8a6 (teal), Risk=#3b82f6 (blue), Contrarian=#eab308 (yellow).

## Technical Approach

### Backend (Python)

**Model layer**: Add 5 fields to frozen `DebateResult` with `None`/`"v1"` defaults. Zero breaking changes.

**Persistence**: Migration 018 adds 5 nullable TEXT columns to `ai_theses`. `DebateRow` dataclass extended. `save_debate()` accepts 5 new optional params. `_row_to_debate_row()` extracts them.

**Orchestrator**: `_run_v2_agents()` populates the 4 new `DebateResult` fields from existing local variables. `_persist_result()` serializes them via `model_dump_json()`. Sets `debate_protocol="v2"`.

**CLI**: 4 new render functions (`render_flow_panel`, `render_fundamental_panel`, `render_risk_v2_panel`, `render_contrarian_panel`). `render_debate_panels()` branches on `debate_protocol`.

**API**: `DebateResultDetail` gets 5 new optional fields. `get_debate()` deserializes JSON columns. `_run_debate_background()` passes v2 fields to `save_debate()`.

**Export**: 4 new markdown section renderers. `export_debate_markdown()` includes v2 sections when `debate_protocol == "v2"`. Renames "Bull Case" → "Trend Analysis" for v2.

### Frontend (Vue 3 + TypeScript)

**Types**: 4 new interfaces matching Python models. `DebateResult` interface gets 5 optional fields. `DebateAgentEvent.name` union extended with v2 agent names.

**Components**: 4 new card components following existing `AgentCard.vue` styling patterns (scoped CSS, `--agent-color`, PrimeVue Aura dark surfaces).

**Page**: `DebateResultPage.vue` detects `debate_protocol === 'v2'` and renders the 6-card grid instead of the v1 layout. `v-if` guards on all v2 cards.

**Store**: Debate store adds v2 agent names to progress tracking initialization.

## Implementation Strategy

### Execution Waves

**Wave 1 (Foundation)**: Tasks 1-2 — Model + migration + repository. No display changes yet.

**Wave 2 (Backend wiring)**: Task 3 — Orchestrator connects outputs to DebateResult and persistence.

**Wave 3 (Display — parallelizable)**: Tasks 4, 5, 6, 7 — CLI, API, frontend, export. All depend only on the model shape from Wave 1. Can run in parallel.

### Risk Mitigation

- V1 backward compatibility verified by running full existing test suite after each wave
- New fields all have `None`/`"v1"` defaults — existing code never sees them unless it looks
- Each task includes tests for both v2 (new) and v1 (regression) paths

## Task Breakdown Preview

- [ ] Task 1: **Model + Migration** — Add 5 fields to `DebateResult`, create migration 018 with 5 ALTER TABLE statements, add tests for model construction + JSON round-trip
- [ ] Task 2: **Repository** — Extend `DebateRow`, `save_debate()`, `_row_to_debate_row()` with 5 new columns. Tests for save/load round-trip with v2 data
- [ ] Task 3: **Orchestrator wiring** — Populate `DebateResult` v2 fields in `_run_v2_agents()`, serialize in `_persist_result()`, set `debate_protocol="v2"`. Tests for v2 output propagation
- [ ] Task 4: **CLI rendering** — 4 new panel render functions, protocol-aware `render_debate_panels()`. Tests for v2 panel output + v1 regression
- [ ] Task 5: **API layer** — Extend `DebateResultDetail`, update `get_debate()` parsing, update `_run_debate_background()` persistence. Tests for v2 API response shape
- [ ] Task 6: **Frontend** — 4 TS interfaces, 4 Vue card components, protocol-aware `DebateResultPage.vue`, debate store v2 support, WebSocket type extension
- [ ] Task 7: **Export** — 4 markdown section renderers, protocol-aware `export_debate_markdown()`. Tests for v2 export output + v1 regression

## Dependencies

### Internal (all existing, stable)
- `FlowThesis`, `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis` in `models/analysis.py`
- `DebateResult` in `agents/_parsing.py`
- `Repository.save_debate()` in `data/repository.py`
- `_run_v2_agents()` in `agents/orchestrator.py`

### External
- None — no new packages or services

### Task Dependencies
```
#249 (model + migration) → #250 (repository) → #251 (orchestrator)
#251 → #253, #254, #255, #256 (all parallelizable)
#254 (API) → #255 (frontend, needs API shape)
```

## Success Criteria (Technical)

| Criteria | Verification |
|----------|-------------|
| `DebateResult` accepts 4 v2 agent fields + protocol | Unit test: construct with all fields, JSON round-trip |
| Migration 018 adds 5 columns without breaking existing data | Migration test: apply to populated DB |
| V2 debates persist all 6 agent outputs to SQLite | Repository test: save + load round-trip |
| `_run_v2_agents()` populates all DebateResult fields | Orchestrator test: mock agents, verify output |
| CLI shows 6 panels for v2, unchanged for v1 | Rendering test: both protocols |
| API returns v2 fields in `DebateResultDetail` | Route test: v2 debate endpoint |
| Frontend renders 6 cards for v2 protocol | E2E or manual: v2 debate page |
| Export includes 4 v2 sections | Export test: markdown output |
| `uv run ruff check .`, `uv run mypy src/ --strict`, `uv run pytest tests/ -v` all pass | CI gates |
| V1 debates render identically (zero regression) | All existing tests pass unchanged |

## Tasks Created

- [ ] #249 - DebateResult model extension + migration 018 (parallel: false)
- [ ] #250 - Repository layer — persist and load v2 agent outputs (parallel: false)
- [ ] #251 - Orchestrator wiring — populate and persist v2 fields (parallel: false)
- [ ] #253 - CLI rendering — 4 v2 agent panels + protocol-aware layout (parallel: true)
- [ ] #254 - API layer — v2 schema fields, route parsing, persistence (parallel: true)
- [ ] #255 - Frontend — v2 types, 4 agent cards, protocol-aware page (parallel: true)
- [ ] #256 - Export — 4 v2 section renderers + protocol-aware export (parallel: true)

Total tasks: 7
Parallel tasks: 4 (#253-#256 after wave 2)
Sequential tasks: 3 (#249-#251, foundation)
Estimated total effort: 21-27 hours

## Test Coverage Plan

Total test files planned: 6
Total test cases planned: ~38
- tests/test_agents/test_parsing_v2.py (5 cases)
- tests/test_data/test_migration_018.py (2 cases)
- tests/test_data/test_repository_v2.py (5 cases)
- tests/test_agents/test_orchestrator_v2.py (5 cases)
- tests/test_cli/test_rendering_v2.py (8 cases)
- tests/test_api/test_debate_routes_v2.py (5 cases)
- tests/test_reporting/test_export_v2.py (8 cases)

## Estimated Effort

- **Size**: Large (L) — 14 files modified, 4 new Vue components, 1 migration
- **Complexity**: Low per-task (plumbing, not architecture) — high breadth (7 layers)
- **Tasks**: 7 issues
- **Critical path**: Tasks 1 → 2 → 3 (serial foundation), then 4/5/6/7 in parallel
