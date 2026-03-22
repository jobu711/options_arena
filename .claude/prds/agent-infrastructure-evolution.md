---
name: agent-infrastructure-evolution
description: Integrate agent evaluation, cost-aware model routing, structured tool responses, learning confidence decay, and development tooling — inspired by competitive audit of everything-claude-code
status: researched
created: 2026-03-22T18:00:00Z
revised: 2026-03-22T19:00:00Z
revision_notes: Context7 PRD audit — fixed 6 mismatches (rsi_14, next_earnings, chain_spread_pct location, tool count 23 not 30+, StrategyRule in models/strategy.py, tool return type not a PydanticAI constraint)
source_audit: https://github.com/affaan-m/everything-claude-code (MIT license, 96K+ stars)
depends_on:
  - unified-agent-system
---

# PRD: Agent Infrastructure Evolution

## Executive Summary

Integrate 9 patterns from a competitive audit of the `everything-claude-code` agent
harness (96K+ stars, MIT) into Options Arena's unified desk agent system. These are
"port the idea" adaptations — no code is copied, only patterns are reimplemented in
our Python/PydanticAI stack. The work targets four layers: **agent evaluation** (measure
recommendation quality), **cost optimization** (per-desk model routing), **reliability**
(structured tool responses), and **learning maturity** (confidence decay on strategy
rules). Combined, these close the project's largest remaining gap: no formal way to
measure whether the 7-agent recommendation pipeline produces good output.

## Problem Statement

### What problem are we solving?

Options Arena is building a 7-agent parallel pipeline (6 desks + synthesis) that produces
`PositionRecommendation` output with entry/exit criteria and position sizing. This pipeline
has **no quality measurement infrastructure**:

1. **No evaluation framework**: When a prompt changes, we can't measure whether
   recommendations improved or regressed. No pass@k, no regression baselines, no graders.
2. **No cost optimization**: Each recommendation = 7 LLM calls (6 parallel desks + synthesis).
   All use the same model tier regardless of task complexity. Batch recommendations on 50
   tickers cost the same whether tickers are simple (clear trend, high liquidity) or complex
   (ambiguous signals, earnings proximity).
3. **No structured tool feedback**: Desk agent tools return raw data or error strings. When
   a tool fails, the agent guesses what to do — there's no recovery guidance or structured
   status.
4. **No learning decay**: Strategy rules mined by `learning/strategy_book.py` have static
   confidence. Patterns that were true 6 months ago but no longer hold keep influencing
   recommendations at full weight.
5. **No pipeline observability**: The recommendation orchestrator (in progress) will run 6
   desks in parallel but has no per-desk timing, cost, or success/failure tracking.

### Why is this important now?

The unified agent system is 50% complete (foundation + desk-recommend epics done). The
orchestrator epic is next, followed by cutover. After cutover, the recommendation pipeline
becomes the **sole path** for all AI analysis — every `options-arena debate` call will
produce a `PositionRecommendation` through 7 LLM calls. Building quality infrastructure
now means:

- Eval baselines captured from day one (before prompt iterations drift quality)
- Cost routing integrated into the orchestrator as it's built (not bolted on after)
- Tool reliability improved before the pipeline goes live
- Learning decay active before stale patterns accumulate

### What does success look like?

1. `options-arena eval check` runs a suite of evals and reports pass@1, pass@3, per-desk
   accuracy, and regression status
2. Batch recommendations cost 40-60% less via per-desk model routing without quality loss
3. Desk agent tools return structured `ToolResponse` objects with recovery guidance
4. Strategy rules auto-demote when confidence decays below threshold
5. Each recommendation logs per-desk metrics (timing, status, model, tokens)

## User Stories

### Agent Quality Measurement
- **As a developer**, I want to define evals for each desk agent and the synthesis agent,
  run them after prompt changes, and see whether pass rates improved or regressed, so I can
  iterate on prompts with confidence.
  - *Acceptance*: `options-arena eval check` runs code-based and model-based graders, reports
    pass@1 and pass@3 per agent, compares against baseline, outputs SHIP/NEEDS WORK verdict.

### Recommendation Regression Prevention
- **As a developer**, I want a test suite built from historical recommendations that were
  wrong (high confidence + negative P&L), so I can verify that prompt changes don't repeat
  known failures.
  - *Acceptance*: `pytest tests/regression/` runs fixtures derived from outcome data.
    Fixtures include `MarketContext` + `TickerScore` snapshots. Tests assert direction
    and confidence bounds.

### Cost-Efficient Batch Recommendations
- **As a user running batch recommendations**, I want the system to use cheaper models for
  straightforward tickers and more capable models for complex ones, so I get better results
  where they matter without paying premium rates everywhere.
  - *Acceptance*: Batch recommendation of 50 tickers routes each desk call to appropriate
    model tier. Cost summary shows per-tier breakdown. Quality metrics (from eval) show no
    degradation vs uniform model.

### Tool Reliability
- **As a user**, I want desk agent recommendations to gracefully degrade when data is
  incomplete (e.g., no IV surface available) rather than producing low-confidence fallbacks,
  so I get the best possible recommendation even with partial data.
  - *Acceptance*: `ToolResponse` includes `status` and `next_actions` that guide the agent
    to adjust specific assessment fields when data is unavailable.

### Self-Maintaining Learning
- **As a user who runs outcome collection**, I want strategy rules that are no longer
  predictive to automatically lose influence and eventually be demoted, so stale patterns
  don't degrade recommendation quality.
  - *Acceptance*: Rules not re-validated in 3+ months have decayed confidence. Rules below
    0.3 confidence are auto-rejected. `learn playbook` shows confidence scores and last
    validation dates.

### Pipeline Observability
- **As a developer debugging recommendation quality**, I want to see per-desk timing,
  model used, token consumption, and success/failure status for each recommendation, so I
  can identify bottlenecks and failure patterns.
  - *Acceptance*: `RecommendationResult` includes `desk_metrics: list[DeskMetrics]`.
    CLI and API surface per-desk breakdown.

## Architecture & Design

### Epic Decomposition

This PRD decomposes into **4 epics** with a dependency structure that allows partial
parallelism:

```
Epic A: Eval Harness ─────────────────────┐
Epic B: Tool Response Contract ───────────┤── can start in parallel
Epic C: Model Routing + Observability ────┤   (after unified-agent-system completes)
Epic D: Learning Decay + Rules Distill ───┘
```

Epics A-D are **independent** — no cross-dependencies. All depend on the unified agent
system being complete (orchestrator + cutover epics). However, items B6 (assessment
handoff) and B7 (desk metrics) from the audit should be folded into the orchestrator epic
directly — they're foundational and cheap.

### Pre-Orchestrator Items (Fold into unified-agent-system-orchestrator)

Two items should be built as part of the orchestrator epic (#647-#651), not deferred to
this PRD:

#### Assessment → Synthesis Handoff Summary

Build an `AssessmentSummary` that the orchestrator computes between Phase 1 (desks) and
Phase 2 (synthesis):

```python
class AssessmentSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    direction_votes: dict[SignalDirection, int]    # vote count per direction
    avg_confidence: float                          # mean confidence across desks
    disagreement_desks: list[DeskType]             # desks that disagree with majority
    risk_flags: list[str]                          # extracted from RiskDeskAssessment
    data_completeness: float                       # fraction of non-None domain fields
```

Injected into the synthesis prompt as structured context. This directly supports the
`agent_agreement_score` and `dissenting_desks` fields on `PositionRecommendation`.

**Module**: `models/recommendation.py` (new model), `agents/recommendation_orchestrator.py`
(computed between phases)

#### Per-Desk Metrics

Track timing and status for each desk in the parallel pipeline:

```python
class DeskMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)
    desk: DeskType
    status: Literal["success", "fallback", "timeout", "skipped"]
    duration_ms: int
    model_used: str
    token_usage: int
```

Added to `RecommendationResult` as `desk_metrics: list[DeskMetrics]`.

**Module**: `models/recommendation.py` (new model),
`agents/recommendation_orchestrator.py` (populated per desk)

---

### Epic A: Eval Harness for Desk + Synthesis Agents

**Source pattern**: `everything-claude-code/skills/eval-harness/SKILL.md`,
`skills/agent-eval/SKILL.md` (MIT)

**Approach**: Port the idea — define eval schemas, grader types, and pass@k metrics
native to our PydanticAI + pytest stack. No JavaScript code ported.

#### Data Models

```python
class EvalType(StrEnum):
    CAPABILITY = "capability"    # can the agent do X it couldn't before?
    REGRESSION = "regression"    # did a change break existing behavior?

class GraderType(StrEnum):
    CODE = "code"       # pytest assertion on assessment fields
    MODEL = "model"     # LLM-as-judge on qualitative fields (key_factors, summary)
    OUTCOME = "outcome" # compare direction/confidence vs actual P&L

class EvalDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    eval_type: EvalType
    target_desk: DeskType | None = None    # None = synthesis agent
    description: str
    grader_type: GraderType
    market_context_fixture: str            # path to JSON fixture
    expected_direction: SignalDirection | None = None
    expected_confidence_range: tuple[float, float] | None = None
    custom_assertions: list[str] = Field(default_factory=list)

class EvalRun(BaseModel):
    model_config = ConfigDict(frozen=True)
    eval_name: str
    timestamp: datetime        # UTC validator
    passed: bool
    attempts: int              # for pass@k
    successes: int
    model_used: str
    duration_ms: int
    details: str               # JSON grader output

class EvalReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    runs: list[EvalRun]
    pass_at_1: float           # fraction passing on first attempt
    pass_at_3: float           # fraction passing at least once in 3 attempts
    regressions: list[str]     # eval names that regressed vs baseline
    verdict: Literal["SHIP", "NEEDS_WORK", "BLOCKED"]
```

#### Grader Implementations

| Grader | Mechanism | When to Use |
|--------|-----------|-------------|
| `CodeGrader` | pytest assertions on typed `DomainAssessment` fields: `direction`, `confidence`, `trend_strength`, `iv_regime`, etc. | Deterministic checks: "AAPL with RSI=75 should be BULLISH" |
| `ModelGrader` | PydanticAI agent with rubric prompt judges qualitative fields (`key_factors`, `summary`, `contrarian_thesis`). Returns pass/fail + reasoning. | Qualitative: "Are key_factors specific and data-cited?" |
| `OutcomeGrader` | Compare `PositionRecommendation.direction` + `confidence` against actual P&L from `outcomes collect`. Calibration curve. | Calibration: "70% confidence should win ~70% of the time" |

#### Eval Storage

```
.claude/evals/
  trend_bullish_clear.json      # EvalDefinition
  volatility_high_iv.json
  synthesis_consensus.json
  regression_baseline.json      # EvalRun history for baseline comparison

data/migrations/038_eval_runs.sql  # Persistent eval history in SQLite
```

#### CLI

```
options-arena eval define <name>     # Create eval definition interactively
options-arena eval check [--desk X]  # Run evals, compare to baseline
options-arena eval report            # Full report with pass@k, regressions, verdict
options-arena eval list              # All evals with status
```

#### API

```
POST /api/eval/check         # Trigger eval run
GET  /api/eval/report        # Latest report
GET  /api/eval/history       # Historical pass rates
```

#### Seeding Strategy

Seed initial evals from existing outcome data:
1. Query `outcomes` table for recommendations with known P&L
2. Serialize `MarketContext` + `TickerScore` as JSON fixtures
3. Create `OutcomeGrader` evals with actual P&L as ground truth
4. Create `CodeGrader` evals for obvious cases (RSI > 70 + ADX > 25 = BULLISH)

**Module changes**: New `evals/` module (or `agents/evals.py`), `models/eval.py`,
`data/_eval.py` (EvalMixin), migration 038, `cli/` eval subcommand, `api/routes/eval.py`

**Estimated tasks**: 6-8
**Estimated LOC**: 800-1,200 new

---

### Epic B: Structured Tool Response Contract

**Source pattern**: `everything-claude-code/skills/agent-harness-construction/SKILL.md`
(MIT, section: "Observation formatting")

**Approach**: Wrap all desk agent tools in `_toolsets.py` with a `ToolResponse` model
that includes status, summary, and recovery guidance.

#### Data Model

```python
class ToolStatus(StrEnum):
    SUCCESS = "success"
    WARNING = "warning"      # partial data available
    ERROR = "error"          # no data, but agent can proceed

class ToolResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)
    status: ToolStatus
    summary: str                          # one-line for agent context
    data: T | None = None                 # typed payload
    next_actions: list[str] = Field(default_factory=list)  # recovery guidance
```

#### Tool Wrapping Strategy

Each tool in `_toolsets.py` already follows a never-raises contract (returns `str` for
agent consumption). The change wraps the string return with structured metadata:

```python
# BEFORE
async def vol_fetch_iv_surface(ctx: RunContext[DeskDeps], ticker: str) -> str:
    try:
        data = await ...
        return f"IV surface for {ticker}: ..."
    except Exception:
        return f"Error fetching IV surface for {ticker}"

# AFTER
async def vol_fetch_iv_surface(ctx: RunContext[DeskDeps], ticker: str) -> str:
    try:
        data = await ...
        response = ToolResponse(
            status=ToolStatus.SUCCESS,
            summary=f"{ticker} IV surface: {len(data.expirations)} expirations",
            data=data,
            next_actions=["assess term structure shape", "compare IV rank"],
        )
    except Exception as exc:
        response = ToolResponse(
            status=ToolStatus.ERROR,
            summary=f"IV surface unavailable for {ticker}: {_sanitize(exc)}",
            data=None,
            next_actions=[
                "set term_structure_shape to None",
                "reduce vol_skew confidence",
                "note data gap in risks list",
            ],
        )
    ctx.deps.tools_used.append("vol_fetch_iv_surface")
    return response.model_dump_json()
```

The agent sees the JSON in its context window. The `next_actions` give explicit guidance
on how to adjust the `DomainAssessment` when data is incomplete — rather than guessing.

**Key design decision**: PydanticAI tools can return any serializable type (str, float,
BaseModel subclasses, datetime — Context7-verified v1.0.5). Options Arena's existing tools
return `str` by convention so tool output appears as readable text in the agent's context
window. Two options for `ToolResponse`:

- **Option A (recommended): Keep `str` return** — serialize `ToolResponse` to JSON string
  via `model_dump_json()`. Agent sees structured JSON in context. Zero change to existing
  tool signatures. Consistent with current codebase convention.
- **Option B: Return `ToolResponse` directly** — PydanticAI auto-serializes the model.
  Cleaner type signatures but changes how tool output appears in agent context (framework
  controls serialization format). Requires updating all tool return type annotations.

#### Scope

- Refactor all 23 tool functions in `_toolsets.py`
- Add `ToolResponse` and `ToolStatus` to `models/`
- Update recommendation prompts to reference the structured response format
- Tests: verify each tool returns valid `ToolResponse` JSON on success and error paths

**Module changes**: `models/` (new model), `agents/_toolsets.py` (refactor all tools),
`agents/prompts/recommend_*.py` (reference ToolResponse in prompt)

**Estimated tasks**: 4-5
**Estimated LOC**: 400-600 modified (toolsets) + 100 new (model + tests)

---

### Epic C: Cost-Aware Model Routing + Pipeline Observability

**Source pattern**: `everything-claude-code/skills/cost-aware-llm-pipeline/SKILL.md`,
`commands/model-route.md` (MIT)

**Approach**: Route each desk to an appropriate model tier based on task complexity.
Track cost per desk per recommendation.

#### Model Tier Routing

```python
class ModelTier(StrEnum):
    FAST = "fast"           # Groq llama-3.3-70b, reduced token budget
    STANDARD = "standard"   # Groq llama-3.3-70b, full token budget
    PREMIUM = "premium"     # Anthropic Claude, extended thinking

def route_model_tier(
    desk: DeskType,
    context: MarketContext,
    config: DebateConfig,
) -> ModelTier:
    """Route desk to model tier based on task complexity."""
    # Synthesis always premium
    if desk is None:  # synthesis
        return ModelTier.PREMIUM

    # Risk always standard+ (safety-critical)
    if desk == DeskType.RISK:
        return ModelTier.STANDARD

    # Complexity heuristics from MarketContext
    complexity = _assess_complexity(context)
    if complexity < 0.3:
        return ModelTier.FAST
    if complexity < 0.7:
        return ModelTier.STANDARD
    return ModelTier.PREMIUM

def _assess_complexity(
    context: MarketContext,
    ticker_score: TickerScore | None = None,
) -> float:
    """0.0 = simple, 1.0 = complex. Based on data completeness and signal clarity."""
    score = 0.0
    # Low data completeness = complex (more inference needed)
    if context.completeness_ratio() < 0.6:
        score += 0.3
    # Earnings within 7 days = complex
    if context.next_earnings and (context.next_earnings - date.today()).days <= 7:
        score += 0.2
    # Conflicting indicators = complex
    if context.rsi_14 and context.adx:
        if context.rsi_14 > 70 and context.adx < 20:  # overbought but no trend
            score += 0.2
    # Extreme IV = complex
    if context.iv_rank and context.iv_rank > 80:
        score += 0.15
    # Low liquidity = complex (chain_spread_pct is on IndicatorSignals, not MarketContext
    # — pass ticker_score alongside context, or extend MarketContext with this field)
    if ticker_score and ticker_score.signals.chain_spread_pct is not None:
        if ticker_score.signals.chain_spread_pct > 10.0:  # normalized 0-100 scale
            score += 0.15
    return min(score, 1.0)
```

#### Integration with Orchestrator

The recommendation orchestrator calls `route_model_tier()` per desk before launching
the parallel Phase 1. Each `asyncio.gather` task receives its own model instance:

```python
# In recommendation_orchestrator.py Phase 1
tasks = []
for desk_type, runner in desk_runners.items():
    tier = route_model_tier(desk_type, context, config)
    model = build_model_for_tier(tier, config)
    tasks.append(runner(deps, model, settings, config))
results = await asyncio.gather(*tasks, return_exceptions=True)
```

#### Cost Tracking

```python
class RecommendationCost(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_tokens: int
    total_cost_usd: float           # estimated from model pricing
    per_desk: dict[DeskType, float] # cost per desk
    synthesis_cost: float
    model_tier_distribution: dict[ModelTier, int]  # count per tier
```

Added to `RecommendationResult`. Persisted to SQLite for cost trend analysis.

#### CLI + API

```
options-arena debate AAPL --cost-summary   # Show per-desk cost breakdown
```

```
GET /api/analytics/recommendation-costs    # Cost trend over time
```

**Module changes**: `agents/model_config.py` (routing logic), `models/recommendation.py`
(new models), `agents/recommendation_orchestrator.py` (integration),
`data/_recommendation.py` (cost persistence)

**Estimated tasks**: 4-5
**Estimated LOC**: 300-500 new

---

### Epic D: Learning Confidence Decay + Rules Distillation

**Source patterns**: `everything-claude-code/skills/continuous-learning-v2/SKILL.md` (MIT,
confidence scoring), `skills/rules-distill/SKILL.md` (MIT, rules extraction)

Two independent work streams in one epic.

#### D1: Confidence Decay on Strategy Rules

Extend `models/strategy.py` (`StrategyRule` model) with confidence fields, and add
decay logic to `learning/strategy_book.py`:

```python
# Extended StrategyRule fields (in models/strategy.py)
class StrategyRule(BaseModel):
    # ... existing fields (rule_id, pattern, conditions, win_rate, avg_return, etc.) ...
    confidence: float = 0.5              # [0.0, 1.0] — initial confidence
    last_validated: datetime | None = None  # UTC, when outcome data last confirmed rule
    validation_count: int = 0            # how many times re-confirmed

def decay_confidence(rule: StrategyRule, now: datetime) -> float:
    """Exponential decay: 5% per month since last validation."""
    if rule.last_validated is None:
        return rule.confidence * 0.5  # never validated = heavy penalty
    months = (now - rule.last_validated).days / 30.0
    return rule.confidence * (0.95 ** months)
```

**Auto-promotion**: `confidence >= 0.8` AND `validation_count >= 5` → `approved`
**Auto-demotion**: `decayed_confidence < 0.3` → `rejected`

The `render_learned_patterns()` function weights pattern prominence by confidence —
high-confidence rules appear first with stronger language, low-confidence rules appear
as caveats.

**Migration**: Add `confidence REAL DEFAULT 0.5`, `last_validated TEXT`,
`validation_count INTEGER DEFAULT 0` to `strategy_rules` table.

**Validation trigger**: When `outcomes collect` runs, cross-reference new P&L data against
strategy rule conditions. Rules whose conditions match successful outcomes get
`validation_count += 1` and `last_validated = now`. Rules whose conditions match failures
get `confidence *= 0.9`.

#### D2: Rules Distillation Skill

New `.claude/prompts/rules-distill.md` skill that systematically extracts cross-cutting
principles from agent prompts and solution docs:

**Phase 1** (deterministic): Glob all files:
- `agents/prompts/recommend_*.py` (6 recommendation prompts)
- `agents/prompts/desk_*.py` (7 desk prompts)
- `agents/prompts/synthesis.py` (synthesis prompt)
- `docs/solutions/*.md` (captured solutions)

**Phase 2** (LLM judgment): Cross-read all files, identify principles appearing in 2+
sources. Extraction criteria:
- Appears in 2+ prompts or solutions
- Actionable behavior change ("do X" / "don't do Y")
- Not already in `.claude/rules/*.md`

**Phase 3** (user approval): Present candidates in table format. User approves, modifies,
or skips. Approved rules appended to appropriate `.claude/rules/` file.

Pairs with existing `/compound` skill: `/compound` captures individual solutions,
`/rules-distill` extracts cross-cutting rules from accumulated solutions.

**Module changes**: `models/strategy.py` (new fields on StrategyRule),
`learning/strategy_book.py` (decay logic + validation trigger),
`data/migrations/` (new migration), `.claude/prompts/rules-distill.md` (new skill)

**Estimated tasks**: 4-5
**Estimated LOC**: 200-300 modified (strategy_book) + 100 new (skill)

---

### Epic E: AI Regression Testing

**Source pattern**: `everything-claude-code/skills/ai-regression-testing/SKILL.md` (MIT)

**Approach**: Build regression test fixtures from historical recommendations that were
wrong (high confidence + negative P&L). These are "tests for bugs that were found."

#### Fixture Generation

```python
# tools/generate_regression_fixtures.py
async def generate_fixtures(repo: Repository, min_confidence: float = 0.6) -> None:
    """Find wrong recommendations and serialize as test fixtures."""
    outcomes = await repo.get_outcomes_with_pnl()
    wrong = [
        o for o in outcomes
        if o.confidence >= min_confidence and o.pnl_pct < -20.0
    ]
    for outcome in wrong:
        fixture = {
            "ticker": outcome.ticker,
            "market_context": outcome.market_context_json,
            "ticker_score": outcome.ticker_score_json,
            "actual_direction": "BEARISH" if outcome.pnl_pct < 0 else "BULLISH",
            "actual_pnl_pct": outcome.pnl_pct,
            "original_direction": outcome.direction,
            "original_confidence": outcome.confidence,
        }
        # Write to tests/regression/fixtures/
```

#### Test Pattern

```python
# tests/regression/test_recommendation_regression.py
@pytest.mark.parametrize("fixture", load_regression_fixtures())
async def test_no_high_confidence_repeat(fixture: dict) -> None:
    """Verify prompt changes don't repeat known failures."""
    context = MarketContext.model_validate_json(fixture["market_context"])
    # Run desk recommendation with TestModel
    assessment = await run_trend_desk_recommendation(deps, model, settings, config)
    # If original was wrong with high confidence, new should be more cautious
    if fixture["original_confidence"] > 0.7:
        assert assessment.confidence <= 0.7, (
            f"Repeated high-confidence failure for {fixture['ticker']}"
        )
```

#### Key Insight from Source

The source pattern identifies that "when an AI writes code and reviews its own work, it
carries the same assumptions." The financial equivalent: if all 6 desks use the same
underlying model, they may share the same blind spots. Regression tests should verify that
the synthesis agent doesn't just amplify desk agreement — it should show reduced confidence
when desks agree but the historical outcome was negative.

**Module changes**: `tools/generate_regression_fixtures.py` (new),
`tests/regression/` (new directory), test fixtures

**Estimated tasks**: 2-3
**Estimated LOC**: 200-300 new

---

## Boundary Table Impact

| Module | Change | Boundary Compliance |
|--------|--------|-------------------|
| `models/` | New: `eval.py`, extend `recommendation.py` (ToolResponse, DeskMetrics, AssessmentSummary, RecommendationCost, ModelTier). Data shapes only. | Yes |
| `agents/_toolsets.py` | Refactor tool returns to `ToolResponse` JSON. | Yes — tools still return `str` |
| `agents/model_config.py` | Add `route_model_tier()` + `build_model_for_tier()`. | Yes — model dispatch only |
| `agents/recommendation_orchestrator.py` | Integrate routing, metrics, handoff summary. | Yes — orchestration only |
| `learning/strategy_book.py` | Add confidence decay + auto-promote/demote. | Yes — middle stack |
| `data/` | New migrations (eval_runs, strategy_rule columns). | Yes — persistence only |
| `cli/` | New `eval` subcommand. | Yes — top of stack |
| `api/` | New eval + cost routes. | Yes — top of stack |
| `.claude/prompts/` | New `rules-distill.md` skill. | N/A — dev tooling |

No boundary violations. All modules stay within their designated access patterns.

## Dependencies

### On Unified Agent System

All 4 epics in this PRD depend on the unified agent system being complete:
- **Orchestrator epic** must be done (provides `run_recommendation()` pipeline)
- **Cutover epic** must be done (debate agents deleted, recommendation is sole path)
- **Exception**: Pre-orchestrator items (AssessmentSummary, DeskMetrics) fold into the
  orchestrator epic itself

### Between Epics

Epics A-E are **independent** — no cross-dependencies. Can be parallelized or executed
in any order. Recommended order is A → C → B → D → E (eval first for measurement, then
cost optimization, then tool reliability, then learning, then regression tests that need
outcome data).

### External Dependencies

None new. All patterns reimplement ideas from `everything-claude-code` (MIT license)
using existing Options Arena dependencies (PydanticAI, Pydantic v2, aiosqlite, pytest).

## Config Changes

New fields on `DebateConfig`:

```python
class DebateConfig(BaseModel):
    # ... existing fields ...

    # Epic C: Model routing
    enable_model_routing: bool = False          # opt-in, default uniform model
    complexity_threshold_fast: float = 0.3      # below = FAST tier
    complexity_threshold_premium: float = 0.7   # above = PREMIUM tier
    synthesis_model_tier: str = "premium"        # synthesis always premium by default
```

New `EvalConfig` on `AppSettings`:

```python
class EvalConfig(BaseModel):
    eval_dir: str = ".claude/evals"
    pass_at_k: int = 3                          # number of attempts for pass@k
    model_grader_model: str = "groq"            # which provider for model grader
    auto_run_on_prompt_change: bool = False      # future: auto-trigger evals
```

## Estimated Effort

| Epic | Tasks | New LOC | Modified LOC | Risk |
|------|-------|---------|-------------|------|
| Pre-orchestrator (fold in) | 2 | 100 | 50 | Low — additive models + orchestrator wiring |
| A: Eval Harness | 6-8 | 800-1,200 | 100 | Medium — new module, but patterns are established |
| B: Tool Response Contract | 4-5 | 100 | 400-600 | Medium — touches all 23 tools, but mechanical refactor |
| C: Model Routing + Observability | 4-5 | 300-500 | 200 | Medium — model dispatch logic, cost estimation |
| D: Learning Decay + Distill | 4-5 | 200-300 | 150 | Low — extends existing strategy_book.py |
| E: Regression Testing | 2-3 | 200-300 | 0 | Low — test fixtures, no production code changes |
| **Total** | **22-28** | **1,700-2,500** | **900-1,100** | |

## Success Criteria (Technical)

1. `options-arena eval check` runs 10+ evals and reports pass@k metrics
2. Eval baselines exist for all 6 desks + synthesis agent
3. `route_model_tier()` correctly routes 3 tiers based on `MarketContext` complexity
4. Batch recommendation of 50 tickers shows measurable cost reduction (>30%) with routing
5. All 23 tools in `_toolsets.py` return `ToolResponse` JSON
6. Desk recommendation prompts reference `ToolResponse` format
7. Strategy rules show `confidence` scores in `learn playbook` output
8. Confidence decay runs when `outcomes collect` processes new data
9. Auto-promotion/demotion fires at threshold boundaries
10. `RecommendationResult` includes `desk_metrics` with per-desk timing and status
11. Regression test suite has 5+ fixtures from historical wrong recommendations
12. All tests pass: `ruff check`, `pytest`, `mypy --strict`

## Implementation Roadmap

```
Phase 1: During unified-agent-system-orchestrator (NOW)
  └─ AssessmentSummary model + DeskMetrics model (fold into orchestrator tasks)

Phase 2: Post-cutover — Quality Infrastructure
  ├─ Epic A: Eval Harness (6-8 tasks, ~2 work sessions)
  └─ Epic E: Regression Testing (2-3 tasks, ~1 work session)

Phase 3: Post-cutover — Cost + Reliability
  ├─ Epic C: Model Routing (4-5 tasks, ~1-2 work sessions)
  └─ Epic B: Tool Response Contract (4-5 tasks, ~1-2 work sessions)

Phase 4: Ongoing — Learning Maturity
  └─ Epic D: Confidence Decay + Rules Distill (4-5 tasks, ~1 work session)
```
