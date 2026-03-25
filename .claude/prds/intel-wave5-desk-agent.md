---
name: intel-wave5-desk-agent
description: Intelligence desk agent — 7th recommendation desk providing macro/event context to synthesis
status: backlog
created: 2026-03-24T15:48:29Z
effort: L
---

# PRD: intel-wave5-desk-agent

## Executive Summary

Add a 7th recommendation desk agent ("Intelligence Desk") that consumes the IntelligenceSnapshot and DeltaReport to provide macro-economic regime assessment, event-driven risk factors, and cross-domain signal correlation to the synthesis agent. This transforms Options Arena's recommendations from pure technical/fundamental analysis into macro-aware, event-contextualized positions.

## Problem Statement

### What problem are we solving?

The 6 existing desk agents (Trend, Volatility, Flow, Fundamental, Risk, Contrarian) analyze ticker-specific data. None of them assess the broader macro environment: "Is the market in a risk-off regime? Are there geopolitical events that could impact this sector? Is supply chain stress elevated?" The Intelligence Desk fills this gap, giving the synthesis agent a 7th perspective grounded in cross-domain intelligence data.

### Why is this important now?

Depends on Wave 1 (models), Wave 2 (data sources), and Wave 3 (collector + delta engine). With all data infrastructure in place, the Intelligence Desk can consume the `IntelligenceSnapshot` and `DeltaReport` to provide contextual analysis.

## User Stories

### US-1: Macro-Aware Recommendations
**As a** trader receiving AI recommendations,
**I want** the recommendation to account for the current macro regime (expansionary/contractionary/risk-off),
**So that** I don't enter bullish positions during a confirmed risk-off shift.

**Acceptance criteria:**
- Intelligence desk assessment visible in recommendation detail
- Regime classification (risk-on/risk-off/mixed) shown
- Key risk events listed
- Event catalysts that could impact the ticker

### US-2: Event-Driven Context
**As a** trader analyzing AAPL options,
**I want** the recommendation to note "NFP release this Friday — elevated volatility expected" or "energy spike affecting tech supply chains",
**So that** I can factor event risk into my position sizing and DTE selection.

## Requirements

### Functional Requirements

#### FR-1: Prompt Files

**`agents/prompts/desk_intelligence.py`** — Interactive mode:
- Analyze current macro regime from IntelligenceSnapshot data
- Cross-correlate economic + energy + credit + supply chain signals
- Identify event-driven catalysts for the queried ticker
- Available tools: fetch_intelligence_snapshot, fetch_delta_report, compute_macro_regime_tool (existing)

**`agents/prompts/recommend_intelligence.py`** — Recommendation mode (with PROMPT_RULES_APPENDIX):
- Output: IntelligenceAssessment fields (market_regime_label, key_risk_events, directional_bias, event_catalysts, macro_summary, cross_correlation_notes)
- Cross-domain correlation patterns: "VIX elevated + credit spreads widening + energy spiking = risk-off"
- Focus on "what the macro environment means for THIS ticker's options"

#### FR-2: Tool Functions (`agents/_toolsets.py`)

Add tools + `build_intelligence_toolset()`:

```python
async def fetch_intelligence_snapshot_tool(ctx: RunContext[DeskDeps]) -> str:
    """Format pre-fetched intelligence snapshot for LLM consumption."""
    # Reads from ctx.deps.intelligence_snapshot (pre-fetched by orchestrator, no I/O)

async def fetch_delta_report_tool(ctx: RunContext[DeskDeps]) -> str:
    """Format pre-fetched delta report showing market changes."""
    # Reads from ctx.deps.delta_report (pre-fetched, no I/O)
```

**Critical design**: Tools are pure formatters — intelligence data is pre-fetched into DeskDeps by the orchestrator (Option A from plan). No service calls in tools.

#### FR-3: Agent Module (`agents/intelligence_desk.py`)

Follow exact pattern of `contrarian_desk.py`:

- `intelligence_desk: Agent[DeskDeps, str]` (interactive mode, model=None at init)
- `intelligence_desk_recommend: Agent[DeskDeps, IntelligenceAssessment]` (recommendation mode)
- `run_intelligence_desk_query() -> DeskResponse` (never raises)
- `run_intelligence_desk_recommendation() -> tuple[IntelligenceAssessment, RunUsage]`
- `@output_validator` with `strip_think_tags()` / `build_cleaned_domain_assessment()`
- `@system_prompt(dynamic=True)` for learned_patterns injection
- `asyncio.wait_for(agent.run(...), timeout=config.agent_timeout)` on every run
- `UsageLimits(request_limit=cfg.default_tool_budget + 2, tool_calls_limit=cfg.default_tool_budget)`
- **Early return**: if `ctx.deps.intelligence_snapshot is None`, return neutral fallback immediately (zero LLM cost when intelligence is disabled)

#### FR-4: Orchestrator Registration (`agents/recommendation_orchestrator.py`)

1. Import `run_intelligence_desk_recommendation`
2. Add to parallel desk gather — conditionally included only when `intelligence_snapshot is not None` on DeskDeps
3. Update `_build_fallback_assessment()` match for `DeskType.INTELLIGENCE`
4. Pre-fetch intelligence data in orchestrator before Phase 1:
   ```python
   # Before desk agent parallel gather:
   if intelligence_collector:
       snapshot = await intelligence_collector.collect_snapshot(ticker, company_name)
       previous = await repo.get_latest_snapshot()
       delta = delta_engine.compute_delta(previous, snapshot) if previous else None
       await repo.save_intelligence_snapshot(snapshot)
       if delta:
           await repo.save_delta_report(delta)
       # Inject into DeskDeps
       deps.intelligence_snapshot = snapshot
       deps.delta_report = delta
   ```

#### FR-5: Intent Routing (`agents/_routing.py`)

Add INTELLIGENCE desk keywords for interactive mode:
- "macro", "economy", "economic", "intelligence", "regime", "recession", "inflation", "fed", "federal reserve", "treasury", "yield curve", "credit spread", "geopolitical", "energy prices", "supply chain", "risk off", "risk on"

#### FR-6: PredictionSource Update

Add `DESK_INTELLIGENCE = "desk_intelligence"` to `PredictionSource` in `models/attribution.py`.

### Non-Functional Requirements

- Intelligence desk follows never-raises contract (same as all desk agents)
- Zero LLM cost when `intelligence_snapshot is None` (early return)
- Zero impact on existing 6-desk flow when intelligence is disabled
- Model dispatched at runtime: `agent.run(model=build_debate_model(...))`
- TestModel for all unit tests — never hit real LLM APIs

## Success Criteria

- Agent tests: TestModel produces valid IntelligenceAssessment, never-raises verified, fallback on None snapshot
- Orchestrator tests: 7-desk parallel gather works, intelligence desk included/excluded correctly
- Integration: recommendation with intelligence enabled shows IntelligenceAssessment in assessments list
- `uv run pytest tests/unit/agents/test_intelligence_desk.py -v` passes

## Out of Scope

- Frontend display of intelligence assessment (Wave 7)
- Synthesis prompt changes (Wave 6)
- Alert delivery from intelligence desk (Wave 4 handles alerts from delta engine directly)

## Dependencies

- **Wave 1** (intel-wave1-foundation) — models, DeskType.INTELLIGENCE, DeskDeps fields
- **Wave 3** (intel-wave3-delta-engine) — IntelligenceCollector, DeltaEngine, Repository mixin

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/options_arena/agents/prompts/desk_intelligence.py` | **Create** |
| `src/options_arena/agents/prompts/recommend_intelligence.py` | **Create** |
| `src/options_arena/agents/_toolsets.py` | Modify — add intelligence tools + builder |
| `src/options_arena/agents/intelligence_desk.py` | **Create** |
| `src/options_arena/agents/recommendation_orchestrator.py` | Modify — register desk, pre-fetch data |
| `src/options_arena/agents/_routing.py` | Modify — add INTELLIGENCE keywords |
| `src/options_arena/models/attribution.py` | Modify — add DESK_INTELLIGENCE to PredictionSource |
| `tests/unit/agents/test_intelligence_desk.py` | **Create** |
