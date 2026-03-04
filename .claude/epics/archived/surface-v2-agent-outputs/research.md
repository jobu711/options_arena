# Research: surface-v2-agent-outputs

## PRD Summary

The v2 debate protocol computes outputs from 6 specialized agents (trend, volatility, flow, fundamental, risk_v2, contrarian) but only surfaces 2 (trend→"bull", volatility). Four agent outputs (flow, fundamental, risk_v2, contrarian) are computed, paid for in tokens, then **discarded** at the orchestrator boundary (~line 1811 of `orchestrator.py`). This PRD plumbs the missing outputs through the entire stack: model fields, persistence, API serialization, CLI rendering, web UI cards, and export sections.

## Relevant Existing Modules

- `models/analysis.py` — Contains all 4 v2 output models (`FlowThesis`, `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis`). Stable, frozen, validated.
- `agents/_parsing.py` — `DebateResult` frozen model. Currently has `bull_response`, `bear_response`, `vol_response`, `bull_rebuttal`. Missing 4 v2 fields.
- `agents/orchestrator.py` — `_run_v2_agents()` creates all 6 outputs but only passes 2 to `DebateResult` constructor (lines 1795-1822). The chokepoint.
- `data/repository.py` — `DebateRow` dataclass + `save_debate()` + `_row_to_debate_row()`. Missing v2 columns.
- `data/migrations/` — Latest is `017_create_themes_table.sql`. Next is 018.
- `cli/rendering.py` — `render_debate_panels()` renders Bull→Bear→Rebuttal→Volatility→Verdict. No v2 panels.
- `api/schemas.py` — `DebateResultDetail` has some v2 fields (contrarian_dissent, agreement_score from ExtendedTradeThesis) but not the 4 agent outputs.
- `api/routes/debate.py` — `_run_debate_background()` calls `save_debate()` without v2 params. `get_debate()` parses ExtendedTradeThesis but not v2 agent JSON.
- `reporting/debate_export.py` — `export_debate_markdown()` renders Bull→Bear→Rebuttal→Volatility→Verdict sections. No v2 sections.
- `web/src/types/debate.ts` — `DebateResult` interface missing v2 fields. `AgentResponse` shape incompatible with v2 models.
- `web/src/pages/DebateResultPage.vue` — Renders v1 AgentCards only. No protocol detection.
- `web/src/components/AgentCard.vue` — Hardcoded to v1 `AgentResponse` shape (argument, key_points, risks_cited). NOT reusable for v2.
- `web/src/stores/debate.ts` — Initializes standard agents as `['bull', 'bear', 'risk']`. Needs v2 agent support.
- `web/src/types/ws.ts` — `DebateAgentEvent.name` hardcoded to `'bull' | 'bear' | 'rebuttal' | 'volatility' | 'risk'`.

## V2 Agent Output Models (Existing, Stable)

### FlowThesis (`models/analysis.py:550-579`)
- `direction: SignalDirection`, `confidence: float`, `gex_interpretation: str`, `smart_money_signal: str`, `oi_analysis: str`, `volume_confirmation: str`, `key_flow_factors: list[str]`, `model_used: str`

### FundamentalThesis (`models/analysis.py:626-656`)
- `direction: SignalDirection`, `confidence: float`, `catalyst_impact: CatalystImpact`, `earnings_assessment: str`, `iv_crush_risk: str`, `short_interest_analysis: str | None`, `dividend_impact: str | None`, `key_fundamental_factors: list[str]`, `model_used: str`

### RiskAssessment (`models/analysis.py:581-624`)
- `risk_level: RiskLevel`, `confidence: float`, `pop_estimate: float | None`, `max_loss_estimate: str`, `charm_decay_warning: str | None`, `spread_quality_assessment: str | None`, `key_risks: list[str]`, `risk_mitigants: list[str]`, `recommended_position_size: str | None`, `model_used: str`

### ContrarianThesis (`models/analysis.py:658-686`)
- `dissent_direction: SignalDirection`, `dissent_confidence: float`, `primary_challenge: str`, `overlooked_risks: list[str]`, `consensus_weakness: str`, `alternative_scenario: str`, `model_used: str`

## Existing Patterns to Reuse

### Frozen Model with Defaults (DebateResult extension)
New fields on `DebateResult` must have `None` defaults since model is `frozen=True`. Pattern: `flow_response: FlowThesis | None = None`.

### JSON Column Persistence (repository.py)
Existing pattern: `model.model_dump_json()` for writes, `Model.model_validate_json(row.column)` for reads. Used for bull_json, bear_json, vol_json, verdict_json.

### Migration Pattern (data/migrations/)
File naming: `{NNN}_{description}.sql`. Use `ALTER TABLE ai_theses ADD COLUMN {name} TEXT;` with nullable defaults. No data migration needed.

### CLI Panel Rendering (rendering.py)
Each agent type has a dedicated render function returning a Rich `Panel`. Uses `Text()` constructor with `markup=False` to avoid bracket crash. Colors: green (bull), red (bear), cyan (vol), blue (verdict).

### API Schema Pattern (schemas.py)
V2 agent outputs should use `dict[str, object] | None` (per PRD constraint) to avoid circular imports. Current `vol_response` is `str | None` (raw JSON string).

### Protocol Detection
Existing: `isinstance(thesis, ExtendedTradeThesis)` in CLI/export/API for v2-specific verdict fields. New: `debate_protocol` field on `DebateResult` enables cleaner detection.

### Frontend Card Pattern
`AgentCard.vue` uses `defineProps<Props>()`, scoped CSS, `border-left: 4px solid var(--agent-color)`, PrimeVue Aura dark surfaces. V2 cards follow same pattern but with different field layouts.

### Frontend Parsing Pattern
`vol_response` and `bull_rebuttal` arrive as raw JSON strings on the API. `tryParseAgent()` helper parses them. V2 agent outputs should follow the same pattern.

## Existing Code to Extend

| File | What Exists | What Needs Changing |
|------|-------------|---------------------|
| `agents/_parsing.py:334-354` | `DebateResult` with 5 agent-related fields | +5 new fields (4 agents + protocol) |
| `agents/orchestrator.py:1795-1822` | Return statement discards 4 outputs | Populate new DebateResult fields |
| `agents/orchestrator.py` | `_persist_result()` serializes to DB | Add 4 new JSON serializations |
| `data/repository.py:55-79` | `DebateRow` dataclass | +5 new fields with defaults |
| `data/repository.py:267-316` | `save_debate()` INSERT | +5 columns in INSERT |
| `data/repository.py:350-379` | `_row_to_debate_row()` | Extract 5 new columns |
| `cli/rendering.py:189-281` | `render_debate_panels()` | Protocol-aware layout, 4 new panels |
| `api/schemas.py:210-248` | `DebateResultDetail` | +5 new optional fields |
| `api/routes/debate.py:154-178` | `_run_debate_background()` save call | +4 JSON params |
| `api/routes/debate.py:509-588` | `get_debate()` parsing | Parse 4 new JSON columns |
| `web/src/types/debate.ts` | `DebateResult` interface | +5 new fields |
| `web/src/types/ws.ts` | `DebateAgentEvent.name` union | +4 v2 agent names |
| `web/src/pages/DebateResultPage.vue` | V1-only agent grid | Protocol detection + v2 card grid |
| `web/src/stores/debate.ts` | Standard agents `['bull', 'bear', 'risk']` | Add v2 agent initialization |
| `reporting/debate_export.py:123-243` | `export_debate_markdown()` | +4 v2 section renderers |

## Potential Conflicts

- **DebateResult is frozen** — new fields must have defaults. Adding `None` defaults is safe and backward compatible.
- **vol_response/bull_rebuttal inconsistency** — API returns these as `str | None` (raw JSON) while the model holds typed objects. V2 fields should follow the typed model pattern in the backend, raw JSON string pattern in the frontend (matching existing `vol_response` behavior).
- **ExtendedTradeThesis already has contrarian_dissent** — The verdict model already surfaces a contrarian summary string. The new `ContrarianThesis` is the full agent output (richer). No conflict, but frontend should show the full card, not duplicate the verdict's summary.
- **AgentCard.vue is V1-only** — Hardcoded to `AgentResponse` shape. V2 agents need 4 new specialized components. This is by design per the PRD.
- **WebSocket agent names** — Currently a string union. Adding v2 names is backward compatible but the debate store's `agentProgress` initialization needs protocol awareness.

## Open Questions

1. **debate_protocol column name**: PRD says `debate_protocol` field on DebateResult and DB column. Should this reuse the existing `debate_mode` column (`"standard"`, `"v2_recon"`) or add a separate column? **Recommendation**: Add `debate_protocol TEXT DEFAULT 'v1'` as a separate column for clarity. `debate_mode` tracks CLI invocation mode; `debate_protocol` tracks the agent protocol used.
2. **V2 panel order in CLI**: PRD specifies 6 panels. Suggested order: Trend (green) → Flow (orange) → Fundamental (teal) → Volatility (cyan) → Risk Assessment (blue) → Contrarian (yellow) → Verdict (magenta). Matches phase execution order.
3. **Frontend card color palette**: PRD specifies orange/teal/blue/yellow for new cards. Need to verify these don't clash with existing PrimeVue theme variables.

## Recommended Architecture

### Data Flow (V2 Path)
```
orchestrator._run_v2_agents()
  → 6 agent outputs (trend, vol, flow, fundamental, risk_v2, contrarian)
  → DebateResult(flow_response=flow, fundamental_response=fund, risk_v2_response=risk, contrarian_response=contra, debate_protocol="v2")
  → API: save_debate() persists 4 new JSON columns + debate_protocol
  → API: get_debate() deserializes 4 new JSON columns
  → CLI: render_debate_panels() detects protocol, renders 6 panels
  → Web: DebateResultPage detects protocol, renders 6 specialized cards
  → Export: export_debate_markdown() includes 4 new sections
```

### Backward Compatibility
- All new fields default to `None`/`"v1"` — V1 debates are completely unaffected
- Protocol detection via `debate_protocol` field (not isinstance checks)
- Frontend uses `v-if` guards on all v2 card components
- CLI renders v1 layout when `debate_protocol != "v2"`

## Test Strategy Preview

### Existing Test Patterns
- `tests/test_agents/` — Uses `TestModel` for PydanticAI agents, mock market context
- `tests/test_data/` — In-memory SQLite with migration runner
- `tests/test_api/` — `httpx.AsyncClient` with `TestClient`, dependency overrides
- `tests/test_cli/` — `typer.testing.CliRunner`, mock services
- `web/e2e/` — Playwright with API mocking via `addInitScript`, page objects

### Test File Locations
- Model tests: `tests/test_agents/test_parsing.py` (DebateResult construction)
- Migration tests: `tests/test_data/test_migrations.py` (schema verification)
- Repository tests: `tests/test_data/test_repository.py` (save/load round-trip)
- Orchestrator tests: `tests/test_agents/test_orchestrator.py` (v2 output wiring)
- CLI tests: `tests/test_cli/test_rendering.py` (panel rendering)
- API tests: `tests/test_api/test_debate_routes.py` (schema + route tests)
- Export tests: `tests/test_reporting/` (markdown output)
- E2E tests: `web/e2e/debate.spec.ts` (full flow)

### Mocking Strategies
- Agents: `TestModel` from pydantic-ai (no real LLM calls)
- Repository: In-memory SQLite with migrations applied
- API: `httpx.AsyncClient` + dependency injection overrides
- Frontend: Playwright `addInitScript` for API/WebSocket mocking

## Estimated Complexity

**Large (L)** — 14 files modified, 4 new Vue components created, 1 migration, touches all layers (model → DB → orchestrator → CLI → API → frontend → export). However, this is a **clean plumbing task** — no refactoring needed, no architectural changes, all infrastructure exists. The complexity is in breadth (many files) not depth (each change is straightforward).

Estimated at **8 issues** following the execution order in the PRD:
1. Model extension (DebateResult + debate_protocol)
2. Migration + Repository
3. Orchestrator wiring
4. CLI rendering (4 new panels)
5. API schemas + routes
6. Frontend types + 4 card components
7. Frontend DebateResultPage protocol-aware rendering
8. Export (4 new sections)
