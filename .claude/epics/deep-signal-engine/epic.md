---
name: deep-signal-engine
status: backlog
created: 2026-02-28T15:31:47Z
progress: 0%
prd: .claude/prds/deep-signal-engine.md
github: https://github.com/jobu711/options_arena/issues/151
updated: 2026-02-28T15:47:54Z
---

# Epic: deep-signal-engine

## Overview

Expand Options Arena's analytical engine from 18 to ~58 indicators across 8 analytical dimensions, upgrade the 3-agent sequential debate to a 6-agent parallel-first protocol with adversarial stress-testing, and replace the single composite score with multi-dimensional family sub-scores with regime-adjusted weights.

The implementation follows a Foundation-first, parallel-epic architecture. Phase 0 defines all shared model interfaces upfront (enums, IndicatorSignals fields, agent output models, config). Four parallel epics then implement indicators, agents, scoring, and debate independently — each owning distinct files with no merge conflicts. A final integration phase wires everything into the scan pipeline.

## Architecture Decisions

- **Interface-first parallel development**: Foundation (Phase 0) defines all new Pydantic models, enums, and config fields before any epic starts. Epics implement against these contracts. New indicator fields default to `None`, enabling graceful partial operation during parallel development.
- **File ownership matrix**: Each epic owns distinct files. `models/` is read-only after Foundation merges. No epic modifies another's files. This eliminates merge conflicts.
- **Parallel-first debate protocol**: Phase 1 runs 4 agents in parallel (Trend, Volatility, Flow, Fundamental), Phase 2 runs Risk sequentially (sees Phase 1), Phase 3 runs Contrarian (sees all). 6 LLM calls total, but wall-clock time = ~2 sequential calls due to parallelism.
- **Graceful degradation preserved**: Every new agent/indicator returns `None` on failure. Scoring skips `None` values and redistributes weights. Debate degrades from 6→5→4→data-driven as agents fail. The "never-raises" contract is maintained.
- **Existing infrastructure reuse**: IV solving uses existing `pricing/dispatch.py`. Second-order Greeks use finite difference on existing BAW/BSM. No new external dependencies. Universe-wide data (^VIX, ^GSPC) fetched once per scan via existing `services/market_data.py`.
- **Backward compatibility**: Existing `TickerScore.direction` stays `SignalDirection`. `TradeThesis` stays valid. New `ExtendedTradeThesis` extends it. Composite score regression test ensures same inputs → same output with new weight system.

## Technical Approach

### Indicators Layer (~40 new indicators)
- **IV Analytics** (`indicators/iv_analytics.py`): 13 indicators — IV-HV spread, term structure slope/shape, put/call skew, vol regime, EWMA forecast, expected move. Built on new `pricing/iv_surface.py` batch IV solving utilities.
- **Flow Analytics** (`indicators/flow_analytics.py`): 5 indicators — GEX, OI concentration, unusual activity, max pain magnet, dollar volume trend. Uses existing chain data + gamma from `pricing/dispatch.py`.
- **Second-Order Greeks** (`pricing/greeks_extended.py`): Vanna, charm, vomma via central finite difference on existing pricing functions. ~300 extra pricing calls per scan (<1s).
- **Extended Options** (`indicators/options_specific.py`): PoP (N(d2)), optimal DTE, spread quality, max loss ratio.
- **Trend Extensions** (`indicators/trend.py`): Multi-TF alignment (weekly supertrend), RSI divergence, ADX exhaustion.
- **Fundamental** (`indicators/fundamental.py`): Earnings EM vs IV, days-to-earnings impact, short interest, div impact, IV crush history.
- **Regime & Macro** (`indicators/regime.py`): Market regime classifier, VIX term structure, risk-on/off, sector momentum, RS vs SPX, correlation regime shift, volume profile skew. Universe-wide data fetched once via `services/market_data.py`.

### Scoring Layer
- **Dimensional scoring** (`scoring/dimensional.py`): 8 family sub-scores (trend, iv_vol, hv_vol, flow, microstructure, fundamental, regime, risk) using weighted geometric mean scoped per family.
- **Regime-adjusted weights**: 4 weight profiles keyed to `MarketRegime`. Opt-in via `enable_regime_weights` config flag.
- **Continuous direction confidence** (`scoring/direction.py`): Replace 3-class discrete direction with `DirectionSignal` (direction + continuous confidence + contributing signals).

### Agent Layer (3 new + 1 expanded)
- **Trend Agent** (replaces Bull): Direction-agnostic momentum analysis. 6 exclusive + 5 shared signals.
- **Flow Agent** (new): Smart money activity, GEX interpretation, unusual flow. 5 exclusive + 5 shared signals.
- **Fundamental Agent** (new): Earnings catalysts, IV crush risk, short squeeze, dividend impact. 4 exclusive + 2 shared signals.
- **Contrarian Agent** (new): Adversarial stress-tester. Sees all 5 prior outputs. Challenges consensus.
- **Risk Agent** (expanded): Quantified risk with `RiskAssessment` output. 6 exclusive + 6 shared signals.
- **Volatility Agent** (expanded prompt): Existing agent with rich IV context from 13 new indicators.

### Debate Protocol
- **Phase 1** (parallel): Trend + Volatility + Flow + Fundamental (4 LLM calls)
- **Phase 2** (sequential): Risk Agent (sees Phase 1 outputs)
- **Phase 3** (sequential): Contrarian Agent (sees all 5 outputs)
- **Phase 4** (algorithmic): Verdict synthesis with agreement scoring, confidence capping, weighted vote
- **Degradation**: 0-4 Phase 1 failures handled gracefully. Contrarian skipped at >=2 failures.

### Infrastructure
- No new external dependencies or services
- Compute budget: ~70s additional on full scan (dominated by 6 LLM calls vs 3 current)
- Total pipeline target: <190s for full universe scan
- Universe-wide data (^GSPC, ^VIX, ^VIX3M, sector ETFs) cached with existing 2-tier caching

## Implementation Strategy

### Phase 0: Foundation — must complete first
Single branch (`epic/dse-foundation`). Extends `models/enums.py`, `models/scan.py`, `models/analysis.py`, `models/config.py`. Creates `models/scoring.py`. Defines all new enums (MarketRegime, VolRegime, IVTermStructureShape, RiskLevel, CatalystImpact), adds ~40 optional fields to IndicatorSignals, creates agent output models (FlowThesis, RiskAssessment, FundamentalThesis, ContrarianThesis, ExtendedTradeThesis), and extends config (DebateConfig, ScanConfig). All existing tests must pass unchanged.

### Epics 1-3: Parallel indicator development
Each runs on its own branch, owns distinct files, can unit-test in isolation with mock data. No cross-epic imports.

### Epic 4: Scoring & Debate
Develops against `None` indicator values during parallel phase. Full integration after Epics 1-3 merge.

### Integration Merge: Final wiring
After all 4 epics merge, wire indicators into scan pipeline, verify all 8 family scores compute with real data, run full debate protocol with mock LLM, regression-test composite scores.

## Task Breakdown Preview

- [ ] **Task 1: Foundation models & config** — New enums, ~40 IndicatorSignals fields, agent output models, DimensionalScores/DirectionSignal models, config extensions. All in `models/`. Tests for new models.
- [ ] **Task 2: IV & Volatility indicators** — `indicators/iv_analytics.py`, `pricing/iv_surface.py`, extend `indicators/volatility.py` and volatility agent prompt. 13 indicators + unit tests.
- [ ] **Task 3: Flow, risk & options indicators** — `indicators/flow_analytics.py`, `pricing/greeks_extended.py`, extend `indicators/options_specific.py`, create Flow Agent. 12 indicators + unit tests.
- [ ] **Task 4: Trend, fundamental & regime indicators** — Extend `indicators/trend.py`, create `indicators/fundamental.py` and `indicators/regime.py`, extend `services/market_data.py` with universe data, create Fundamental Agent. 15 indicators + unit tests.
- [ ] **Task 5: Multi-dimensional scoring** — `scoring/dimensional.py`, extend `scoring/composite.py` (regime weights) and `scoring/direction.py` (continuous confidence). Unit tests.
- [ ] **Task 6: 6-agent debate protocol** — Trend Agent, Contrarian Agent, expanded Risk Agent, refactored orchestrator (parallel Phase 1 → sequential Phase 2/3), verdict synthesis. Integration tests.
- [ ] **Task 7: Pipeline integration & E2E** — Wire all indicators into scan pipeline, verify all 8 family scores, full debate protocol E2E with mock LLM, regression tests, pipeline timing validation.

## Dependencies

### External Service Dependencies
- **Groq API**: 6 LLM calls per debate (up from 3). Free tier rate limit (30 RPM) handled via `phase1_parallelism` config (4 for paid, 2 for free).
- **yfinance**: No new API surface — all new indicators derive from existing OHLCV, chain, and `info` data already fetched.
- **Additional tickers**: ^VIX3M, HYG, LQD, 11 sector ETFs fetched once per scan for regime/macro indicators.

### Internal Dependencies
- Foundation (Task 1) must merge before Tasks 2-6 start
- Tasks 2, 3, 4 are fully parallel (no file conflicts)
- Task 5 can develop in parallel using `None` indicator values
- Task 6 can develop in parallel using mock agent outputs
- Task 7 requires all prior tasks merged

### Prerequisite Work
- None — all infrastructure exists (BSM/BAW pricing, yfinance services, PydanticAI agents, scan pipeline)

## Success Criteria (Technical)

- **Coverage**: Indicator count 18 → 58 across 8 analytical dimensions
- **Agent specialization**: Each agent owns 4+ exclusive signals
- **Debate citation density**: 0.6 → 0.8+ (more signals to cite)
- **IV modeling**: Zero → full term structure, skew, vol regime classification
- **Adversarial challenge**: Every verdict includes contrarian dissent + agreement score
- **Stability**: Zero increase in crash rate (never-raises contract preserved)
- **Backward compatibility**: All 1,752 existing tests pass without modification after each task merges
- **Performance**: Full universe scan pipeline < 190s
- **Graceful degradation**: Scoring handles partial `None` indicators; debate handles 0-4 agent failures

## Estimated Effort

- **Task 1 (Foundation)**: Small — model definitions, enums, config fields. ~1 day.
- **Tasks 2-4 (Indicators)**: Medium each — ~40 indicator functions + tests across 3 parallel streams. ~2-3 days each (parallel).
- **Task 5 (Scoring)**: Medium — dimensional scoring + regime weights + direction confidence. ~2 days.
- **Task 6 (Debate)**: Large — 3 new agents + orchestrator refactor + verdict synthesis. ~3 days.
- **Task 7 (Integration)**: Medium — pipeline wiring + E2E validation + regression. ~2 days.
- **Critical path**: Task 1 → Tasks 2-6 (parallel) → Task 7. Wall-clock: ~8-10 days with parallelism.

## Tasks Created

- [ ] #154 - Foundation models, enums & config (parallel: false)
- [ ] #155 - IV & Volatility indicators + IV surface utilities (parallel: true)
- [ ] #157 - Flow, risk & options indicators + Flow Agent (parallel: true)
- [ ] #152 - Trend, fundamental & regime indicators + Fundamental Agent (parallel: true)
- [ ] #153 - Multi-dimensional scoring engine (parallel: true)
- [ ] #156 - 6-agent debate protocol + Trend & Contrarian agents (parallel: true)
- [ ] #158 - Pipeline integration & E2E validation (parallel: false)

Total tasks: 7
Parallel tasks: 5 (#155, #157, #152, #153, #156 — after #154 completes)
Sequential tasks: 2 (#154 first, #158 last)
Estimated total effort: 112-152 hours
