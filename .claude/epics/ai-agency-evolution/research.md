# Research: ai-agency-evolution (Revised 2026-03-17)

## PRD Summary

Transform Options Arena from a batch analysis tool into an AI advisory agency. Create 7 desk Agent instances (trend, volatility, flow, fundamental, risk, contrarian, research) alongside the existing 6-agent debate pipeline. Add an Advisor agent for query routing, and a new `learning/` module for self-improvement (weight tuning, prompt A/B testing, strategy mining from outcome data). Desk agents use PydanticAI `FunctionToolset` for interactive tool-use queries with `str` output type (conversational), distinct from debate agents' structured `AgentResponse` output.

**Revision scope**: Added 3-tier tool architecture (base + analysis + ML), 2 new epics (7: Analysis & HV Tools, 8: ML Tools), revised desk descriptions with full capability enrichment, re-phased to 8 epics across 3 parallel tracks.

## Relevant Existing Modules

- `agents/` — 6 debate agents (trend, volatility, flow, fundamental, risk, contrarian) as module-level `Agent[DebateDeps, AgentResponse]` instances. Orchestrator runs 3-phase pipeline (Phase 1 parallel, Phase 2 Risk, Phase 3 Contrarian). `compute_auto_tune_weights()` exists here but will relocate to `learning/`. Key files: `orchestrator.py` (~2,150 lines), `_parsing.py` (context rendering + DebateDeps), `model_config.py` (provider dispatch). Dynamic prompts on Risk and Contrarian (`@agent.system_prompt(dynamic=True)`).
- `agents/prompts/` — 6 static prompt files (one per debate agent). Each exports `{AGENT}_SYSTEM_PROMPT` constant, concatenated with `PROMPT_RULES_APPENDIX`. <8000 chars per prompt. Desk prompts will be sibling files (`desk_*.py`).
- `models/` — ~130 exported models across 17 files. 33 StrEnums in `enums.py` (no naming conflicts with proposed DeskType, QueryType, RuleStatus, ConditionOperator, WeightType). `WeightSnapshot`, `AgentAccuracyReport`, `AgentWeightsComparison` in `analytics.py`. `AgentResponse`, `TradeThesis`, `MarketContext` in `analysis.py`. `AppSettings` (only BaseSettings) in `config.py` with 12 nested BaseModel subconfigs.
- `data/` — Repository composed from 5 mixins (Scan, Debate, Analytics, Metadata, Spreads) inheriting from `RepositoryBase`. 33 migrations (001-033). `auto_tune_weights` table exists (migration 028). `agent_predictions` table exists (migration 025). All methods return typed models, never raw dicts.
- `services/` — 6 services following `ServiceBase[ConfigT]` pattern. MarketDataService, OptionsDataService, FredService are the primary desk tool data sources. All async, DI via constructor. `OutcomeCollector` handles P&L computation.
- `scoring/` — 19 indicator weights (sum=1.0). `compute_auto_tune_weights` reads from here. `INVERTED_INDICATORS` list. Learning module will read (not write) these.
- `analysis/` — 4 pure-math modules (valuation, correlation, performance, position_sizing). No API calls, no optional deps. All functions return typed Pydantic models or NamedTuples. `FDData` is a plain `@dataclass` (not Pydantic).
- `indicators/` — ML functions with guarded imports: `vol_forecast.py` (GARCH, requires `arch`+`statsmodels`), `regime_ml.py` (Markov, requires `statsmodels`), `macro.py` (pure math), `hurst.py` (pure math), `hv_estimators.py` (pure math). Input/output is pandas Series/floats/NamedTuples.
- `api/` — FastAPI with app factory + `lifespan()`. 10 route files. DI via `Depends()` providers in `deps.py`. WebSocket progress bridge pattern. Operation mutex via `asyncio.Lock`. Services stored on `app.state`.
- `cli/` — Typer with subcommand groups (scan, universe, debate, outcomes, serve). Sync wrappers around `asyncio.run()`. `commands.py` is large (53K+ lines).

## Existing Patterns to Reuse

- **Agent Instance Pattern**: `Agent(model=None, deps_type=X, output_type=Y, retries=2)` at module level. Model passed at `run(model=...)` time. Apply to all 7 desk agents + advisor, but with `DeskDeps` and `output_type=str`.
- **Dynamic System Prompts**: Risk and Contrarian already use `@agent.system_prompt(dynamic=True)` to inject prior outputs. Desk agents can use same pattern to inject `<<<AVAILABLE_TOOLS>>>` block.
- **Output Validator Pattern**: All 6 debate agents use `@output_validator` → `build_cleaned_agent_response()`. Desk agents with `output_type=str` don't need this (no structured output to validate).
- **Service DI via Deps Dataclass**: `@dataclass` with typed service fields. Debate uses `DebateDeps` (16 fields: context, ticker_score, contracts + 13 coordination fields). Desk agents use new `DeskDeps` (7 fields). Services injected at call site, not import time.
- **FunctionToolset (Context7-verified)**: `FunctionToolset(tools=[fn1, fn2])` or `@toolset.tool` decorator. Passed at `run(toolsets=[...])` time. `UsageLimits(tool_calls_limit=N)` enforces budget. Dynamic toolset via `@agent.toolset` decorator with `RunContext`.
- **Repository Mixin Decomposition**: New `AgencyMixin` follows same pattern as `ScanMixin`, `DebateMixin`, etc. Async methods, parameterized queries, typed Pydantic returns, `await db.commit()` after writes. Named row access via `row["column_name"]`.
- **API Route Organization**: `APIRouter(prefix="/api/...", tags=[...])` per domain. New `routes/agency.py` and `routes/learning.py`. DI via `Depends(get_repo)` etc.
- **WebSocket Progress Bridge**: Sync callback -> `asyncio.Queue` -> WebSocket JSON events. Reuse for agency chat streaming.
- **CLI Subcommand Groups**: `typer.Typer()` + `app.add_typer(name="agency")`. Sync commands with `asyncio.run()`.
- **Migration Pattern**: Sequential numbering (034-037), `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, TEXT for datetimes, TEXT for Decimal fields.
- **Config Pattern**: Nested `BaseModel` subconfigs under `AppSettings(BaseSettings)`. New `AgencyConfig` and `LearningConfig` as `BaseModel`, not `BaseSettings`. 12 existing nested configs as precedent.
- **Never-Raises Pattern**: `run_debate()` catches all errors → data-driven fallback. Apply to `run_desk_query()`.
- **Guarded Import Pattern**: ML functions use `try/except ImportError` → return `None`. Apply to ML tool registration in `FunctionToolset` builders.

## Existing Code to Extend

- `models/enums.py` — Add 5 new StrEnums: `DeskType`, `QueryType`, `RuleStatus`, `ConditionOperator`, `WeightType` (no naming conflicts with existing 33 enums)
- `models/analytics.py` — Extend `WeightSnapshot` with `weight_type: WeightType` and `accuracy_at_time: float | None` fields. Add `PromptVersion`, `StrategyRule`, `StrategyCondition`, `AgentMemory` models.
- `models/config.py` — Add `AgencyConfig` and `LearningConfig` as nested BaseModel subconfigs on `AppSettings`
- `agents/orchestrator.py` — `compute_auto_tune_weights()` (lines 933-1015) relocates to `learning/weight_tuner.py`. Uses inverse-Brier scoring, clamped [0.05, 0.35], normalized to sum=0.85. Risk always 0.0. Min 10 samples per agent. Orchestrator keeps thin re-export or calls learning module.
- `agents/_parsing.py` — `DebateDeps` dataclass lives here (16 fields). `render_*_context()` functions (trend, volatility, flow, fundamental, macro) format MarketContext into flat text blocks. Pattern for new `render_learned_patterns()`.
- `data/repository.py` — Add `AgencyMixin` to Repository's multiple inheritance chain (currently: Scan, Debate, Analytics, Metadata, Spreads)
- `data/_debate.py` — Existing `save_auto_tune_weights()` uses `executemany` with parameterized queries. Pattern for new agency persistence methods.
- `api/app.py` — Register new route groups (`/api/agency/*`, `/api/learning/*`). Add services to `lifespan()`. Existing pattern: try/except with `_closeable` list for cleanup.
- `api/deps.py` — Add DI providers for any new services (e.g., `get_learning_service()`). Pattern: `cast(Type, request.app.state.field)`.
- `agents/__init__.py` — Re-export new desk agents + advisor
- `analysis/__init__.py` — Currently only re-exports `compute_composite_valuation`. Other functions (`compute_correlation_matrix`, `compute_risk_adjusted_metrics`, `compute_position_size`) need re-export for tool wrapping.

## New Code to Create

| File/Module | Purpose | Epic |
|-------------|---------|------|
| `agents/trend_desk.py` ... (6 desk files) | Interactive desk Agent instances (`Agent[DeskDeps, str]`) | 1, 3 |
| `agents/research_desk.py` | Research desk with curated cross-domain tools (budget: 5) | 3 |
| `agents/advisor.py` | Advisor agent for intent classification + routing | 2 |
| `agents/_routing.py` | Multi-desk dispatch orchestration, response synthesis | 2 |
| `agents/_toolsets.py` | FunctionToolset builders per desk (3-tier registration) | 1, 7, 8 |
| `agents/prompts/desk_*.py` (7 files) | Interactive prompts (~2000 chars, conversational) | 1, 3 |
| `learning/__init__.py` | Package re-exports | 4 |
| `learning/weight_tuner.py` | Auto-tune vote + indicator weights from outcome data | 4 |
| `learning/prompt_lab.py` | Prompt versioning, A/B testing, Wilcoxon comparison | 5 |
| `learning/strategy_book.py` | Pattern mining, StrategyRule generation, chi-squared tests | 6 |
| `learning/CLAUDE.md` | Module conventions | 4 |
| `data/_agency.py` | AgencyMixin (queries, prompt versions, strategy rules, agent memory) | 2 |
| `data/migrations/034-037.sql` | 4 new migrations | 2, 5, 6, 4 |
| `api/routes/agency.py` | Agency interaction endpoints | 2 |
| `api/routes/learning.py` | Learning/tuning endpoints | 4 |
| New models in `models/` | `AgencyQuery`, `DeskResponse`, `Citation`, `AgencyResponse`, `QueryIntent`, `AgentMemory` | 1-2 |

## Tool Wrapping Catalog (Epics 7-8)

### Epic 7: Analysis & HV Tools (always available, no optional deps)

| Tool | Source | Signature | Input Adaptation | Wrapper Complexity |
|------|--------|-----------|-----------------|-------------------|
| `compute_composite_valuation_tool` | `analysis/valuation.py` | `(ticker, price, FDData, rate) -> CompositeValuation` | Build `FDData` from service data; format Pydantic output as string | Low |
| `compute_correlation_matrix_tool` | `analysis/correlation.py` | `(dict[str, DataFrame], min_overlap) -> CorrelationMatrix` | Fetch OHLCV for multiple tickers, build DataFrame dict | Medium |
| `compute_risk_adjusted_metrics_tool` | `analysis/performance.py` | `(returns, holding_days, rate, min_trades) -> RiskAdjustedMetrics` | Build lists from Repository outcome data | Low |
| `compute_position_size_tool` | `analysis/position_sizing.py` | `(iv, correlation, config) -> PositionSizeResult` | Pass IV float from quote/chain data | Low |
| `compute_hv_yang_zhang_tool` | `indicators/hv_estimators.py` | `(open_, high, low, close, period) -> float \| None` | Fetch OHLCV, split into O/H/L/C Series | Medium |

### Epic 8: ML Desk Tools (2 require `[ml]`, 2 pure math grouped thematically)

| Tool | Source | Signature | Optional Dep | Wrapper Complexity |
|------|--------|-----------|-------------|-------------------|
| `compute_garch_forecast_tool` | `indicators/vol_forecast.py` | `(returns: Series, p, q, horizon) -> float \| None` | `arch`, `statsmodels` | High — compute % returns, handle None |
| `compute_markov_regime_tool` | `indicators/regime_ml.py` | `(returns: Series, k_regimes) -> MarkovRegimeOutput \| None` | `statsmodels` | High — guarded import, NamedTuple output |
| `compute_macro_regime_tool` | `indicators/macro.py` | `(**kwargs) -> MacroClassification \| None` | None (pure math) | Low — pass FRED primitives |
| `compute_hurst_exponent_tool` | `indicators/hurst.py` | `(close: Series, min_bars, max_lag, r2_threshold) -> float \| None` | None (pure math) | Medium — fetch close Series |

### Gotchas for Tool Implementation

1. `FDData` is a plain `@dataclass`, not Pydantic — tool wrapper must construct it from dict/service data
2. `compute_hv_yang_zhang` needs 4 separate pd.Series (O/H/L/C) — fetch single OHLCV DataFrame, split columns
3. GARCH expects returns in `%` form (multiply by 100) — tool must compute `np.log(price[t]/price[t-1]) * 100`
4. `compute_macro_regime` uses keyword-only params — tool wrapper must map FRED context fields to kwargs
5. Regime functions return NamedTuples, not Pydantic — format as strings, don't serialize
6. All tools must follow never-raises contract: return `f"Error: {message}"` on failure

## PydanticAI API Verification (Context7-verified 2026-03-17)

### FunctionToolset

```python
# Three registration methods:
toolset = FunctionToolset(tools=[fn1, fn2])       # constructor
@toolset.tool                                      # decorator
def my_tool(ctx: RunContext, arg: str) -> str: ...
toolset.add_function(fn, name='alias')             # add_function

# Pass at run time:
result = await agent.run(prompt, toolsets=[toolset])
```

### UsageLimits

```python
from pydantic_ai.usage import UsageLimits
# Raises UsageLimitExceeded when exceeded:
result = await agent.run(prompt, usage_limits=UsageLimits(tool_calls_limit=3))
```

### Dynamic Toolset (deps-aware)

```python
@agent.toolset
def dynamic_toolset(ctx: RunContext[DeskDeps]):
    if ctx.deps.active == 'weather':
        return weather_toolset
    else:
        return datetime_toolset
```

### Key API Notes

- `FunctionToolset` is standalone — no agent registration needed at init time
- Tools can receive `RunContext` as first param (optional) to access deps
- `UsageLimits` is passed at `run()` time, not at Agent init
- `@agent.toolset` decorator enables dynamic toolset selection based on RunContext
- `instructions=` parameter on `run()` for mode-specific context injection

## Potential Conflicts

- **WeightSnapshot extension (migration 037)**: Adding `weight_type` and `accuracy_at_time` to existing model. Must use ALTER TABLE on existing `auto_tune_weights` table. Risk: existing rows have NULL for new columns.
  - *Mitigation*: `weight_type TEXT DEFAULT 'vote'`, `accuracy_at_time REAL` (nullable). Existing rows auto-populate as vote weights.

- **orchestrator.py relocation**: Moving `compute_auto_tune_weights()` to `learning/` while maintaining backward compatibility for existing callers.
  - *Mitigation*: Move function to `learning/weight_tuner.py`. Add thin re-export in orchestrator or update imports.

- **commands.py size**: Already 53K+ lines. Adding agency subcommand group increases size.
  - *Mitigation*: Extract agency commands to separate `cli/agency.py` file. Typer supports `add_typer()` from separate modules.

- **analysis/__init__.py incomplete re-exports**: Only `compute_composite_valuation` re-exported. Other functions need re-export for tool wrapping.
  - *Mitigation*: Add re-exports during Epic 7 implementation.

- **No conflicts with existing debate agents**: Desk agents are entirely separate `Agent` instances with different `deps_type` and `output_type`. Zero modifications to existing debate agents.

- **No conflicts with analysis/indicators modules**: Tool wrappers are thin adapters — underlying functions unchanged.

## Open Questions

1. **FunctionToolset verified**: Context7 confirms `FunctionToolset`, `UsageLimits(tool_calls_limit=N)`, `toolsets=[...]` at `run()`, and `@agent.toolset` dynamic decorator. All available in pydantic-ai v1.62+. **RESOLVED**.

2. **Advisor routing: rule-based vs LLM-based**: PRD specifies rule-based for V1 (keyword matching + regex ticker extraction). Recommend starting with pure Python function in `_routing.py`, structured as `classify_intent(query: str) -> QueryIntent`. Can upgrade to PydanticAI Agent with `output_type=QueryIntent` later.

3. **Learning module boundary**: PRD says learning "accesses `agents/prompts/` for text only." Since desk prompts support `dynamic=True` with text loaded from DB via `PromptVersion`, learning reads from DB via Repository, not from prompt files. Initial desk prompt text seeded from `desk_*.py` files into `prompt_versions` table during migration/first-run.

4. **Outcome collection trigger**: Recommend calling weight tuner inline after `collect_outcomes()` completes — single `await auto_tune_weights(repo)` call at end of collection flow. Cleaner than requiring separate manual step.

5. **DeskDeps `tools_used` accumulator**: PydanticAI shares the `deps` reference (confirmed by `RunContext` docs — deps is mutable). `list[str]` accumulator in `@dataclass` is safe. Tools append to it during execution.

6. **Tool budget vs UsageLimits**: Documented as "finalize during Epic 1" in PRD. Recommend removing `tool_call_budget` from `DeskDeps` and relying solely on `UsageLimits(tool_calls_limit=N)` at `run()` time.

## Recommended Architecture

### High-Level Design

```
CLI / API (entry points)
    |
    v
agents/_routing.py (query orchestration)
    |
    +---> Advisor (rule-based V1, intent classification)
    |
    +---> Desk Agents (7 desks, each Agent[DeskDeps, str])
    |         |
    |         v
    |     FunctionToolset (3-tier: base + analysis + ML)
    |         |
    |         v
    |     Services (MarketData, OptionsData, Fred, Repository)
    |     analysis/ (valuation, correlation, performance, position_sizing)
    |     indicators/ (GARCH, regime, macro, Hurst, HV)
    |
    v
AgencyResponse (synthesized multi-desk response)
    |
    v
data/_agency.py (persist query + response for audit trail)

---

learning/ (triggered after outcome collection or manually)
    |
    +---> weight_tuner.py (reads outcomes from repo, computes weights, persists)
    +---> prompt_lab.py (reads prompt performance from repo, promotes variants)
    +---> strategy_book.py (reads outcomes, mines patterns, generates rules)
```

### Three-Track Parallelization

```
Track A (Core Agency):    Epic 1 ──> Epic 2 ──> (done)
                            │          │
                            └──> Epic 3 ┘  (parallel with Epic 2)

Track B (Self-Improvement): ──────────> Epic 4 ──> Epic 5 ──> Epic 6
                                        (after Epics 1-2)

Track C (Tool Enrichment):  ──────────────────> Epic 7 ┐  (after Epics 1-3)
                                                Epic 8 ┘  (parallel with each other)
```

### Key Design Decisions

1. **Separate Agent instances for desk vs debate** — zero regression risk, clean type safety
2. **FunctionToolset injected at run() time** — testable with TestModel, tools swappable
3. **Three-tier tool architecture** — base (always) + analysis (always) + ML (conditional)
4. **Tools return formatted strings** — agents process text, not Pydantic models
5. **Learning module is middle-stack** — reads from `models/`, `data/`, `scoring/`, `agents/prompts/` (text only)
6. **SQLite for all persistence** — no vector DB; structured data suits SQL WHERE clauses
7. **Rule-based routing for V1** — fast, deterministic, upgradeable to LLM-based later
8. **Desk prompts separate from debate prompts** — different purpose (conversational vs structured thesis)
9. **Existing computation modules as tool sources** — `analysis/` and `indicators/` wrapped, not reimplemented

## Test Strategy Preview

- **Existing patterns**: pytest + pytest-asyncio, `TestModel` for PydanticAI agents (via `agent.override(model=TestModel())`), mock services via dependency injection, `aiosqlite` in-memory DBs for repository tests. Module-level `models.ALLOW_MODEL_REQUESTS = False` prevents accidental real API calls.
- **Naming convention**: `tests/test_{module}.py` or `tests/{module}/test_{file}.py`
- **Marker convention**: `@pytest.mark.critical` for happy-path, `@pytest.mark.exhaustive` for parametrize grids
- **Desk agent tests**: Use `TestModel` (no real LLM), mock `DeskDeps` services, verify tool calls and response format
- **Tool wrapper tests** (Epics 7-8): Mock underlying function, verify string formatting, error handling (`None` inputs, missing `[ml]` deps), correct arg passing
- **Toolset registration tests** (Epic 8): Mock `ImportError` on `arch`/`statsmodels`, assert toolset still builds with base + analysis tools
- **Routing tests**: Unit test intent classification with known queries, verify desk selection
- **Learning tests**: Unit test weight computation with synthetic accuracy data, prompt comparison with synthetic performance data, strategy mining with synthetic outcomes
- **API tests**: httpx `TestClient`, test DB, verify response schemas
- **E2E**: Playwright for agency chat flow and learning dashboard
- **Estimated**: ~180+ new tests across all 8 epics

## Estimated Complexity

**XL** — Justification:
- 8 epic phases across 27-33 GitHub issues
- New `learning/` module (entirely new package with 3 submodules)
- 7 new desk Agent instances + 1 Advisor agent + 7 new prompt files
- 9 tool wrappers across 2 tool enrichment epics (5 analysis + 4 ML)
- 4 new database migrations + new Repository mixin
- New API route groups (agency + learning) + CLI subcommand group
- 3-phase self-improvement engine (weight tuning, prompt A/B, strategy mining)
- Frontend components (chat, desk selector, learning dashboard)
- ~180+ new tests

Risk is **moderate** because:
- Zero changes to existing debate agents (no regression risk)
- All patterns are well-established in the codebase
- Foundation infrastructure exists (auto-tune weights, outcome tracking, agent predictions)
- Clean module boundaries prevent cascading changes
- Tool enrichment (Epics 7-8) is independent of self-improvement (Epics 4-6)
- Analysis/indicators functions are already tested — tool wrappers are thin adapters
