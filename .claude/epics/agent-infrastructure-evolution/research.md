# Research: agent-infrastructure-evolution

## PRD Summary

Integrate 9 patterns from a competitive audit of `everything-claude-code` into Options Arena's unified desk agent system. Four layers: **agent evaluation** (measure recommendation quality), **cost optimization** (per-desk model routing), **reliability** (structured tool responses), and **learning maturity** (confidence decay on strategy rules). Five epics (A-E) plus pre-orchestrator items to fold into the orchestrator epic.

## Relevant Existing Modules

- `agents/` — 6 debate agents + 7 desk agents + synthesis agent. All follow `Agent[Deps, Output]` pattern with `model=None` at init, never-raises runners, `@output_validator` with think-tag stripping. `_toolsets.py` has **23 tool functions** + 8 builders (31 total). Tools return `str`, follow never-raises contract with `TICKER_RE` validation and `math.isfinite()` guards.
- `models/` — 33 StrEnums, 50+ Pydantic models. `recommendation.py` defines `DomainAssessment` hierarchy (6 subclasses), `AnyAssessment` discriminated union, `PositionRecommendation` (21 fields), `RecommendationResult` (7 fields). `strategy.py` has `StrategyRule` (no confidence decay fields), `StrategyCondition`, `AgentMemory`. `config.py` has `AppSettings` (sole `BaseSettings`), `DebateConfig`, `AgencyConfig`.
- `learning/` — Middle-stack. `weight_tuner.py` (indicator + vote weight tuning), `strategy_book.py` (pattern mining, chi-squared significance, `render_learned_patterns()` → `<<<LEARNED_PATTERNS>>>` block). Never-raises contract on all orchestration functions.
- `data/` — 5 Repository mixins (`ScanMixin`, `DebateMixin`, `AnalyticsMixin`, `MetadataMixin`, `SpreadsMixin`) + `LearningMixin`. 36 sequential migrations (latest: `036_strategy_mining.sql`). All queries return typed models.
- `api/` — 13 route files, registered via `app.include_router()` in `create_app()`. Dependency injection via `Depends()`. Operation mutex with `asyncio.Lock`.
- `cli/` — Typer subcommand groups via `app.add_typer()`: `universe_app`, `outcomes_app`, `agency_app`. Sync wrappers + `asyncio.run()`.
- `scoring/` — 27 indicator weights (sum=1.0), composite scoring, contract filtering. Imports `pricing/dispatch` only.
- `agents/model_config.py` — `build_debate_model()` dispatches on `LLMProvider` enum (GROQ/ANTHROPIC). No per-desk tier routing exists.

## Existing Patterns to Reuse

- **Never-raises runner pattern**: All agent runners (`run_*_desk_query()`, `run_synthesis()`, `run_debate()`) catch exceptions and return fallback. Apply to eval graders and routing logic.
- **Discriminated union pattern**: `AnyAssessment` uses `Discriminator("desk")` + `Tag()` for polymorphic JSON. Apply to `ToolResponse` if generic typing needed.
- **Repository mixin pattern**: Add `EvalMixin`, `MetricsMixin` for new persistence needs. Follow `_debate.py` pattern (named columns, typed returns, explicit commit).
- **CLI subcommand pattern**: `app.add_typer(eval_app, name="eval")` — follows `outcomes_app` and `agency_app` precedent.
- **API route pattern**: New `routes/eval.py`, `routes/metrics.py` — follow existing `routes/learning.py` pattern (router prefix, Depends DI).
- **Config nesting pattern**: New `EvalConfig` and `RoutingConfig` as `BaseModel` (not `BaseSettings`), nested on `AppSettings`.
- **Migration pattern**: Sequential numbered SQL files, `CREATE TABLE IF NOT EXISTS`, idempotent.
- **Enum-based dispatch**: `match` statement for `ModelTier` routing, follows `LLMProvider` dispatch pattern.
- **Frozen model pattern**: `DeskMetrics`, `AssessmentSummary`, `EvalRun`, `ToolResponse`, `RecommendationCost` — all `ConfigDict(frozen=True)`.

## Existing Code to Extend

- `models/recommendation.py` — Add `DeskMetrics`, `AssessmentSummary`, `RecommendationCost` models. Extend `RecommendationResult` with `desk_metrics: list[DeskMetrics]` field.
- `models/strategy.py` — Extend `StrategyRule` with `confidence: float`, `last_validated: datetime | None`, `validation_count: int`. Currently has: `rule_id`, `pattern`, `conditions`, `win_rate`, `avg_return`, `sample_size`, `status`, `created_at`.
- `models/config.py` — Add `EvalConfig`, `RoutingConfig` as nested `BaseModel` sub-configs on `AppSettings`. Extend `DebateConfig` with routing fields.
- `models/enums.py` — Add `ModelTier` (FAST/STANDARD/PREMIUM), `ToolStatus` (SUCCESS/WARNING/ERROR), `EvalType`, `GraderType` StrEnums.
- `agents/_toolsets.py` — Refactor all 23 tool functions to wrap returns in `ToolResponse` JSON. Keep `str` return type (Option A from PRD).
- `agents/model_config.py` — Add `route_model_tier()`, `build_model_for_tier()`, `_assess_complexity()` functions alongside existing `build_debate_model()`.
- `learning/strategy_book.py` — Add `decay_confidence()`, validation trigger in `outcomes collect` flow. Extend `render_learned_patterns()` to weight by confidence.
- `data/` — New `_eval.py` (EvalMixin), extend `_analytics.py` or new `_metrics.py` for cost/metrics persistence. Add `LearningMixin` methods for confidence fields.

## New Files to Create

| File | Epic | Purpose |
|------|------|---------|
| `models/eval.py` | A | `EvalDefinition`, `EvalRun`, `EvalReport` models |
| `models/tool_response.py` | B | `ToolResponse[T]`, `ToolStatus` |
| `data/_eval.py` | A | EvalMixin for eval persistence |
| `data/migrations/038_confidence_decay.sql` | D | Add confidence fields to `strategy_rules` |
| `data/migrations/039_eval_runs.sql` | A | `eval_runs` table |
| `data/migrations/040_desk_metrics.sql` | C | `desk_metrics` + `recommendation_costs` tables (if needed) |
| `agents/model_routing.py` | C | `route_model_tier()`, `_assess_complexity()` |
| `learning/confidence_decay.py` | D | `decay_confidence()`, `auto_promote_demote()` |
| `api/routes/eval.py` | A | Eval check/report endpoints |
| `cli/eval.py` | A | `eval_app` Typer subcommand group |
| `.claude/prompts/rules-distill.md` | D | Rules distillation skill |
| `tools/generate_regression_fixtures.py` | E | Fixture generation from outcomes |
| `tests/regression/` | E | Regression test directory |

## Potential Conflicts

- **StrategyRule frozen=True**: Currently frozen. Adding mutable confidence fields requires either: (a) new model with updated fields (replace), or (b) separate ConfidenceMetadata model linked by rule_id. Recommend (a) — keep frozen but create new instances on update (immutable update pattern).
- **Tool return type str**: All 23 tools return `str`. Refactoring to `ToolResponse.model_dump_json()` keeps the `str` return signature but changes the content format. Desk agent prompts must be updated to expect JSON-structured responses. Test coverage for all 23 tools needed.
- **RecommendationResult arbitrary_types_allowed**: Already has `arbitrary_types_allowed=True` for `RunUsage`. Adding `desk_metrics` list is safe but `RunUsage` import must remain.
- **Migration numbering**: If orchestrator epic adds migrations 037+, numbering must be coordinated. Currently at 036. Recommend reserving 037 for orchestrator, 038+ for this PRD.

## Open Questions

1. **Tool response format adoption**: Should desk recommendation prompts (in `agents/prompts/recommend_*.py`) explicitly reference the ToolResponse JSON schema, or should the agent infer from the structured output? PRD recommends explicit reference.
2. **Model grader provider**: Which LLM provider should the ModelGrader use? Using the same provider as the desk agents creates a "grading your own homework" risk. Consider using Anthropic for grading even when Groq is the debate provider.
3. **Eval fixture storage**: PRD proposes `.claude/evals/` (JSON files) + SQLite persistence. Should fixtures be version-controlled (git-tracked JSON) or database-only? Recommend both — JSON for reproducibility, SQLite for history.
4. **Cost estimation accuracy**: Groq doesn't provide per-request cost via API. Cost estimates will be based on token counts × published pricing. How should we handle pricing updates? Config-driven cost-per-token map.
5. **Migration coordination with orchestrator epic**: The orchestrator epic (647-651) may add migrations. Need to agree on migration numbering — suggest orchestrator uses 037, this PRD starts at 038.
6. **Confidence decay trigger**: PRD says "when `outcomes collect` runs." Should decay also run on a time-based schedule (e.g., daily)? Or only when new outcome data arrives? Recommend outcome-triggered only (avoids unnecessary processing).

## Recommended Architecture

### Epic A (Eval Harness)
New `evals/` module or `agents/evals/` subpackage. Three grader types (Code, Model, Outcome) as strategy pattern implementations. Eval definitions as JSON fixtures in `.claude/evals/`. Results persisted to SQLite via EvalMixin. CLI `eval check` runs suite, compares to baseline. API `POST /api/eval/check` for programmatic access.

### Epic B (Tool Response Contract)
`ToolResponse` model in `models/tool_response.py`. Generic `[T]` type parameter for typed payloads. All 23 tools in `_toolsets.py` refactored to construct `ToolResponse` and call `model_dump_json()`. Keep `str` return type (Option A). Update 7 recommendation desk prompts to reference ToolResponse format. Add `next_actions` guidance strings tailored per tool failure mode.

### Epic C (Model Routing + Observability)
`ModelTier` enum + `route_model_tier()` in `agents/model_routing.py`. Complexity assessment from `MarketContext` fields. `DeskMetrics` frozen model in `models/recommendation.py`. Per-desk model selection in recommendation orchestrator before `asyncio.gather`. Cost tracking via token count × config-driven pricing. `RecommendationCost` model on `RecommendationResult`.

### Epic D (Learning Decay + Rules Distill)
Extend `StrategyRule` with `confidence`, `last_validated`, `validation_count` fields. Migration 038 adds columns. `decay_confidence()` in `learning/confidence_decay.py` — exponential decay (5% per month). Auto-promote at confidence >= 0.8 + validation_count >= 5. Auto-demote at decayed confidence < 0.3. Validation triggered by `outcomes collect`. `render_learned_patterns()` weights by confidence. New `.claude/prompts/rules-distill.md` skill.

### Epic E (Regression Testing)
`tools/generate_regression_fixtures.py` queries outcomes for high-confidence failures. Serializes `MarketContext` + `TickerScore` as JSON fixtures in `tests/regression/fixtures/`. Parametrized pytest suite asserts current recommendations don't repeat known failures. Marked `@pytest.mark.regression`.

## Test Strategy Preview

- **Existing test infrastructure**: 363 test files, 27K+ parametrized, pytest + pytest-asyncio. `conftest.py` in every package with factory functions (`make_option_contract()`, `make_ticker_score()`, `make_market_context()`).
- **Agent tests**: Use `pydantic_ai.models.test.TestModel` — prevents real API calls. `model=None` at init enables override.
- **Tool tests**: Test each tool's success and error paths. Verify `ToolResponse` JSON is valid.
- **Eval tests**: Test grader logic deterministically. Model grader uses TestModel.
- **Routing tests**: Parametrize complexity scenarios. Verify tier selection matches expectations.
- **Decay tests**: Time-based tests with mocked `datetime.now()`. Verify promotion/demotion thresholds.
- **Regression tests**: Load fixtures, run with TestModel, assert direction/confidence bounds.
- **Naming**: `test_{module}_{feature}.py`, test functions `test_{behavior}`.

## Estimated Complexity

**XL** — 5 independent epics, ~22-28 tasks total, ~2,600-3,600 LOC (1,700-2,500 new + 900-1,100 modified).

Justification:
- Touches 8+ modules (models, agents, learning, data, api, cli, tools, tests)
- 3 new database migrations
- 23 tool functions refactored (Epic B)
- New eval module with 3 grader types (Epic A)
- New CLI subcommand group + API routes
- All epics independent — can be parallelized but each is M-L individually

Individual epic estimates:
- Epic A (Eval Harness): **L** — new module, 6-8 tasks, 800-1,200 LOC
- Epic B (Tool Response): **M** — mechanical refactor, 4-5 tasks, 500-700 LOC
- Epic C (Model Routing): **M** — new routing logic + metrics, 4-5 tasks, 300-500 LOC
- Epic D (Learning Decay): **M** — extends existing module, 4-5 tasks, 200-300 LOC
- Epic E (Regression Tests): **S** — test fixtures + suite, 2-3 tasks, 200-300 LOC
