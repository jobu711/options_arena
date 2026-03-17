---
name: ai-agency-evolution
status: backlog
created: 2026-03-17T14:33:59Z
progress: 0%
prd: .claude/prds/ai-agency-evolution.md
type: parent
child_epics:
  - ai-agency-desk-foundation
  - ai-agency-advisor-routing
  - ai-agency-all-desks
  - ai-agency-weight-tuning
  - ai-agency-prompt-ab
  - ai-agency-strategy-mining
  - ai-agency-analysis-tools
  - ai-agency-ml-tools
github: [Will be updated when synced to GitHub]
---

# Epic: ai-agency-evolution (Parent)

## Overview

Transform Options Arena from a batch analysis tool into an AI advisory agency. Create 7 desk Agent instances (`Agent[DeskDeps, str]`) alongside the existing 6-agent debate pipeline, add an Advisor for routing, and build a `learning/` module for self-improvement. Desks use PydanticAI `FunctionToolset` with 3-tier tool architecture (base service tools + analysis pure-math tools + ML optional-dep tools). Three independent implementation tracks enable parallelization.

Zero modifications to existing debate agents — desk agents are entirely separate instances.

## Architecture Decisions

1. **Separate Agent instances for desk vs debate.** PydanticAI enforces single `deps_type`/`output_type` per Agent. Debate agents have `@output_validator` that prevents runtime `output_type` override. Desk agents use `Agent[DeskDeps, str]` (conversational) alongside existing `Agent[DebateDeps, AgentResponse]` (structured). Zero regression risk.

2. **FunctionToolset at run() time.** Tools injected via `run(toolsets=[...])` — not baked into Agent init. Enables `TestModel` testing, conditional ML tool registration, and per-desk tool scoping. Context7-verified: `FunctionToolset`, `UsageLimits(tool_calls_limit=N)`, `@agent.toolset` all available in pydantic-ai v1.62+.

3. **Three-tier tool architecture.** Base (wrap `services/` methods, always available) → Analysis (wrap `analysis/` pure math, always available) → ML (wrap `indicators/` ML functions, conditionally registered via guarded imports). Desks degrade gracefully — fewer tools = narrower analysis, not failure.

4. **Rule-based Advisor routing for V1.** Pure Python `classify_intent(query) -> QueryIntent` using keyword matching + regex ticker extraction. No LLM call for routing. Upgradeable to `Agent[..., QueryIntent]` later.

5. **`learning/` as middle-stack module.** Accesses `models/`, `data/`, `scoring/`, `agents/prompts/` (text only). Never imports agent instances, services, or orchestrator. `compute_auto_tune_weights()` relocates here from `orchestrator.py`.

6. **SQLite for all persistence.** Structured data (sector, IV bucket, DTE bucket) suits SQL WHERE clauses. No vector DB. 4 new migrations (034-037).

7. **Repository mixin pattern.** New `AgencyMixin` added to Repository's multiple inheritance chain alongside existing 5 mixins.

## Technical Approach

### Backend — Agents & Routing

- 7 desk Agent instances in `agents/{name}_desk.py` — module-level `Agent(model=None, deps_type=DeskDeps, output_type=str)`
- `DeskDeps` dataclass: query, ticker, market_data, options_data, fred, repo, tools_used accumulator
- `agents/_toolsets.py`: Builder functions per desk (`build_volatility_toolset() -> FunctionToolset`) with conditional ML registration
- `agents/_routing.py`: `classify_intent()` + `run_desk_query()` + `synthesize_responses()` orchestration
- `agents/advisor.py`: Rule-based intent classifier returning `QueryIntent` (desks, query_type, tickers)
- 7 interactive prompts in `agents/prompts/desk_*.py` (~2000 chars, conversational, tool-use-oriented)

### Backend — Learning Module

- `learning/weight_tuner.py`: Relocated `compute_auto_tune_weights()` + new indicator weight tuning via outcome correlation
- `learning/prompt_lab.py`: Prompt versioning (SQLite-backed `PromptVersion`), round-robin A/B assignment, Wilcoxon signed-rank comparison after 30+ samples
- `learning/strategy_book.py`: Outcome pattern mining by dimensions (sector × IV bucket × DTE bucket × direction), chi-squared significance test, `StrategyRule` candidate generation

### Backend — Data Layer

- `data/_agency.py`: `AgencyMixin` with CRUD for agency_queries, prompt_versions, strategy_rules, agent_memory tables
- 4 migrations: 034 (agency_queries), 035 (prompt_versions), 036 (strategy_rules + agent_memory), 037 (ALTER auto_tune_weights)

### Backend — Models

- 5 new StrEnums: `DeskType`, `QueryType`, `RuleStatus`, `ConditionOperator`, `WeightType`
- New frozen models: `AgencyQuery`, `DeskResponse`, `Citation`, `AgencyResponse`, `QueryIntent`, `AgentMemory`, `PromptVersion`, `StrategyRule`, `StrategyCondition`
- Extend `WeightSnapshot` with `weight_type` and `accuracy_at_time`
- New config: `AgencyConfig` + `LearningConfig` as nested `BaseModel` on `AppSettings`

### Backend — API & CLI

- `api/routes/agency.py`: POST/GET `/api/agency/query`, WS `/api/agency/ws`
- `api/routes/learning.py`: GET/POST weights, prompts, playbook endpoints
- `cli/agency.py`: `agency ask`, `agency learn status|weights|mine|playbook` subcommands
- WebSocket bridge for streaming desk responses

### Frontend Components

- `AgencyChat.vue` — Chat interface for advisor/desk interaction
- `DeskSelector.vue` — Direct desk access with capability descriptions
- `LearningDashboard.vue` — Weight evolution charts, prompt comparison, playbook viewer
- Built incrementally within each task, not as standalone frontend task

### Tool Wrappers (9 total)

**Always available (5):** `compute_composite_valuation_tool`, `compute_correlation_matrix_tool`, `compute_risk_adjusted_metrics_tool`, `compute_position_size_tool`, `compute_hv_yang_zhang_tool`

**Conditionally registered (2):** `compute_garch_forecast_tool` (requires arch+statsmodels), `compute_markov_regime_tool` (requires statsmodels)

**Pure math in ML epic (2):** `compute_macro_regime_tool`, `compute_hurst_exponent_tool`

## Implementation Strategy

### Parallelization (3 independent tracks)

```
Track A (Core Agency):      Task 1 ──> Task 2 ──> (done)

Track B (Self-Improvement):  ────────> Task 3 ──> Task 4 ──> Task 5
                                       (after Task 1-2)

Track C (Tool Enrichment):   ────────────────> Task 6
                                               (after Task 1-2)
```

Tracks B and C are fully independent — can run in parallel.

### Risk Mitigation

- **Zero regression**: Existing debate agents untouched. All new code in new files.
- **Incremental delivery**: Each task is independently deployable and testable.
- **Graceful degradation**: LLM unreachable → data-driven response. ML deps missing → tools omitted.
- **Never-raises contract**: `run_desk_query()` catches all errors, returns error response (like existing `run_debate()` pattern).

### Testing Approach

- Agent tests: `TestModel` override, mock `DeskDeps` services, `models.ALLOW_MODEL_REQUESTS = False`
- Tool tests: Mock underlying functions, verify string formatting and error handling
- Toolset registration tests: Mock `ImportError`, verify conditional registration
- API tests: httpx `TestClient` with in-memory SQLite
- E2E: Playwright for chat flow and learning dashboard
- ~180+ new tests across all tasks

## Task Breakdown Preview

- [ ] **Task 1: Desk Foundation** — DeskDeps dataclass, FunctionToolset builders (base tools only), vol + risk desk agents, desk prompts, new models/enums, AgencyConfig. Proves the pattern with 2 desks.
- [ ] **Task 2: Advisor, Remaining Desks & API** — Advisor routing, remaining 5 desks (trend, flow, fundamental, contrarian, research), _routing.py orchestration, agency_queries migration, API endpoints, CLI commands, WebSocket bridge, AgencyChat.vue.
- [ ] **Task 3: Self-Improvement P1 — Weight Tuning** — New `learning/` module, relocate `compute_auto_tune_weights()`, extend to indicator weights, WeightSnapshot extension (migration 037), weight history API/CLI, LearningDashboard weight tab.
- [ ] **Task 4: Self-Improvement P2 — Prompt A/B** — PromptVersion model, migration 035, prompt_lab.py (versioning, round-robin, Wilcoxon comparison), desk prompt dynamic loading from DB, accuracy tracking, prompt management API/CLI.
- [ ] **Task 5: Self-Improvement P3 — Strategy Mining** — AgentMemory + StrategyRule models, migration 036, strategy_book.py (pattern mining, chi-squared, rule generation), human approval workflow, playbook API/CLI, learned patterns injected into desk prompts.
- [ ] **Task 6: Analysis & ML Desk Tools** — 9 tool wrappers (5 analysis + 4 ML), conditional registration for ML tools, register on target desks, `<<<AVAILABLE_TOOLS>>>` prompt block, toolset registration tests.

## Dependencies

### Internal (existing, no changes needed)
- 6 debate agents in `agents/` (untouched)
- `services/` layer (MarketData, OptionsData, Fred, Repository)
- `analysis/` module (valuation, correlation, performance, position_sizing)
- `indicators/` ML functions (GARCH, regime, macro, Hurst, HV)
- Outcome tracking system (`OutcomeCollector`)
- WebSocket infrastructure in `api/`

### External (already installed)
- PydanticAI v1.62+ (`FunctionToolset`, `UsageLimits` — Context7-verified)
- `arch >=8.0,<9` via `[ml]` optional extra
- `statsmodels >=0.14,<0.15` via `[ml]` optional extra
- `scikit-learn >=1.5,<2` via `[ml]` optional extra

### Prerequisites
- None — all foundation code exists in master (v2.10.0)

## Success Criteria (Technical)

1. **Response time**: Single-desk query <30s, multi-desk <60s
2. **Tool degradation**: Desks function correctly with and without `[ml]` extra installed
3. **Zero regression**: All existing 26,516 tests continue passing
4. **Weight tuning**: Produces measurably different weights from defaults after 100+ outcomes
5. **Prompt A/B**: Identifies statistically significant winner within 60 queries per variant
6. **Strategy mining**: Surfaces at least 3 rules from 200+ historical outcomes
7. **Test coverage**: ~180+ new tests across all tasks

## Estimated Effort

- **Overall**: XL — 6 tasks, ~27-33 GitHub issues when decomposed
- **Critical path**: Task 1 → Task 2 (core agency must exist before self-improvement or tool enrichment)
- **Parallelizable**: Tasks 3-5 (self-improvement) and Task 6 (tool enrichment) are independent tracks
- **Per-task estimate**: 3-5 issues each, ~2-4 implementation sessions per task
