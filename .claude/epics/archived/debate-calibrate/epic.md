---
name: debate-calibrate
status: backlog
created: 2026-03-07T22:30:06Z
progress: 0%
prd: .claude/prds/debate-calibrate.md
github: https://github.com/jobu711/options_arena/issues/345
---

# Epic: debate-calibrate

## Overview

The 6-agent debate system produces unanimous bullish verdicts regardless of input because all
agents receive identical MarketContext (including pre-computed COMPOSITE SCORE and DIRECTION).
This epic fixes two root causes: (1) information partitioning gives each Phase 1 agent only
its domain-specific fields, and (2) log-odds pooling replaces linear weighted averaging for
mathematically proper probability aggregation. Follow-up improvements add volatility direction
voting, vote entropy measurement, relaxed contrarian gate, and per-agent prediction persistence
for future self-calibrating weights.

8 functional requirements (FR-9 eliminated — multi-period outcome collection already works).

## Architecture Decisions

1. **Information partitioning over prompt engineering**: Breaking agent correlation by giving
   different data (Condorcet independence) rather than asking the LLM to "disagree." Four
   domain renderers in `_parsing.py`; Risk/Contrarian keep full context.

2. **Log-odds pooling (Bordley 1982)**: Weighted sum in log-odds space properly compounds
   independent agreement (three 90% → 99.7%) and respects extreme probabilities. Replaces
   linear averaging which kills extreme signals (three 90% → 90%).

3. **MACD included in trend context**: MACD is a genuine indicator from `indicators/trend.py`,
   not a scan conclusion. Only COMPOSITE SCORE, DIRECTION, and DIRECTION CONFIDENCE are
   excluded from domain renderers.

4. **Risk weight removal**: `AGENT_VOTE_WEIGHTS["risk"] = 0.15` is confirmed dead code —
   `RiskAssessment` is passed separately, never enters the confidence pooling loop. Risk
   provides position sizing, not directional alpha. Remove rather than wire.

5. **Agent predictions wiring via `_persist_result()`**: Capture `save_debate()` return value
   (currently discarded) in 3 persistence sites: `_persist_result()`, API single-debate, API
   batch (already captures). All agent data already on `DebateResult` — no new fields needed.

## Technical Approach

### Context Rendering (`agents/_parsing.py`)
- Add `_render_identity_block(ctx) -> list[str]` — shared fields for all domain renderers
- Add `render_trend_context()`, `render_volatility_context()`, `render_flow_context()`,
  `render_fundamental_context()` — each uses identity block + domain-specific fields
- `render_context_block()` unchanged — still used by Risk, Contrarian, persistence, display
- Remove COMPOSITE SCORE anchors from `PROMPT_RULES_APPENDIX`, replace with domain-neutral
  calibration language
- Re-export new renderers from `agents/__init__.py`

### Orchestrator Changes (`agents/orchestrator.py`)
- `_run_v2_agents()`: Replace single `context_text` with 4 domain texts + 1 full text
- `synthesize_verdict()`: Replace linear pooling with `_log_odds_pool()`, add `_vote_entropy()`
- Remove `isinstance(VolatilityThesis): continue` skip in direction voting
- Remove `"risk": 0.15` from `AGENT_VOTE_WEIGHTS`
- Change contrarian gate `< 2` → `< 3`
- Wire `save_agent_predictions()` into `_persist_result()`

### Model Fields (`models/analysis.py`)
- `VolatilityThesis`: add `direction: SignalDirection = SignalDirection.NEUTRAL`
- `ExtendedTradeThesis`: add `ensemble_entropy: float | None = None` with `isfinite()` validator
- Both backward-compatible via defaults — existing serialized JSON deserializes correctly

### Volatility Prompt Update
- Add directional output instructions based on IV regime
- Calibration anchors: IV rank < 25 → bullish, 25-75 → neutral, > 75 → bearish
- Update `build_cleaned_volatility_thesis()` to pass `direction=output.direction`

### Database (`data/`)
- Migration `025_agent_predictions.sql` — `agent_predictions` table with FK to `ai_theses`
- `AgentPrediction` model (frozen, UTC validator, confidence validator)
- `Repository.save_agent_predictions()` — typed CRUD, parameterized SQL

### No Frontend Changes
All changes are backend-only. No API contract changes, no new endpoints required.

## Task Breakdown

- [ ] **Task 1**: Domain context renderers + prompt calibration (FR-1 + FR-3) — `_parsing.py`
- [ ] **Task 2**: Orchestrator: partitioned wiring + log-odds pooling (FR-2 + FR-4) — `orchestrator.py`
- [ ] **Task 3**: Ensemble diversity: model fields + vol direction + entropy + gate (FR-5 + FR-6 + FR-7)
- [ ] **Task 4**: Agent prediction persistence (FR-8) — migration + model + repo + wiring
- [ ] **Task 5**: Full test suite + lint + typecheck verification
- [ ] **Task 6**: Live validation — run debates, measure success criteria

### Dependency Graph

```
Task 1 ──→ Task 2 ──→ Task 3 ──┐
                                ├──→ Task 5 ──→ Task 6
                   Task 4 ──────┘
```

- Tasks 1→2: Renderers must exist before orchestrator can import them
- Tasks 2→3: Both modify `orchestrator.py` — serialize to avoid conflicts
- Task 4: Independent of 3, can run after Task 2 (needs `_persist_result()` changes from Task 2)
- Task 5: After all code tasks complete
- Task 6: Post-merge validation

### Task Details

**Task 1 — Domain Renderers + Prompt Calibration** (FR-1 + FR-3)
Files: `agents/_parsing.py`, `agents/__init__.py`
- `_render_identity_block(ctx)` — shared identity fields
- `render_trend_context(ctx)` — RSI, MACD, ADX, SMA alignment, stochastic RSI, rel volume, RSI divergence, dim_trend
- `render_volatility_context(ctx)` — IV rank/pct, ATM IV, BB width, ATR%, vol regime, IV-HV spread, skew, VIX term, expected move, vega, vomma, dim_iv/hv_vol
- `render_flow_context(ctx)` — P/C ratio, max pain, GEX, unusual activity, net premiums, options P/C, rel volume, dim_flow/microstructure
- `render_fundamental_context(ctx)` — PE/PB/PEG, debt/equity, growth, margins, short interest, analyst, insider, institutional, news, dim_fundamental
- Update `PROMPT_RULES_APPENDIX`: remove COMPOSITE SCORE anchors, add domain-neutral calibration
- Re-export 4 renderers from `agents/__init__.py`

**Task 2 — Orchestrator Wiring + Log-Odds Pooling** (FR-2 + FR-4)
Files: `agents/orchestrator.py`
- In `_run_v2_agents()`: generate 4 domain texts + 1 full text, pass domain text to each Phase 1 agent
- Add `_log_odds_pool(probabilities, weights) -> float` pure function
- Replace linear averaging in `synthesize_verdict()` with `_log_odds_pool()`
- Remove `"risk": 0.15` from `AGENT_VOTE_WEIGHTS`
- Keep agreement-based confidence cap after log-odds

**Task 3 — Ensemble Diversity** (FR-5 + FR-6 + FR-7)
Files: `models/analysis.py`, `agents/orchestrator.py`, `agents/_parsing.py`, volatility prompt file
- Add `ensemble_entropy: float | None = None` to `ExtendedTradeThesis` + `isfinite()` validator
- Add `direction: SignalDirection = SignalDirection.NEUTRAL` to `VolatilityThesis`
- Add `_vote_entropy()` to orchestrator, compute in `synthesize_verdict()`
- Remove `isinstance(VolatilityThesis): continue` skip in direction voting
- Update volatility prompt with IV regime calibration anchors for directional output
- Update `build_cleaned_volatility_thesis()` to pass `direction=output.direction`
- Change contrarian gate `phase1_failures < 2` → `phase1_failures < 3`

**Task 4 — Agent Prediction Persistence** (FR-8)
Files: `data/migrations/025_agent_predictions.sql`, `models/analysis.py`, `data/repository.py`, `agents/orchestrator.py`, `api/routes/debate.py`
- Create migration `025_agent_predictions.sql`
- Add `AgentPrediction` model (frozen, UTC validator, confidence validator)
- Add `Repository.save_agent_predictions(debate_id, result)` method
- Wire into `_persist_result()`: capture `save_debate()` return, call `save_agent_predictions()`
- Wire into API single-debate: capture return, add call
- Wire into API batch-debate: add call after existing `debate_id` capture

**Task 5 — Tests + Verification**
- Unit tests: 4 domain renderers (field inclusion/exclusion), `_log_odds_pool()` (4 cases), `_vote_entropy()` (4 cases)
- Model tests: VolatilityThesis backward compat, ExtendedTradeThesis backward compat
- Integration: `synthesize_verdict()` with log-odds, entropy, vol direction
- Migration: `025_agent_predictions.sql` table creation
- Run full test suite (3,921 Python + 38 E2E), ruff, mypy

**Task 6 — Live Validation** (post-merge)
- Run 50+ debates across diverse tickers
- Measure: unanimity rate (<50%), mean entropy (>0.4), trend echo rate (<60%)
- Measure: fundamental confidence std (>0.10), contrarian execution (>80%)
- Compare log-odds confidence vs win rates (calibration curve)

## Dependencies

### Internal
| Dependency | Module | Required By |
|---|---|---|
| `render_context_block()` | `agents/_parsing.py` | Task 1 (extend, don't break) |
| `_render_optional()` | `agents/_parsing.py` | Task 1 (reuse) |
| `PROMPT_RULES_APPENDIX` | `agents/_parsing.py` | Task 1 |
| `_run_v2_agents()` | `agents/orchestrator.py` | Task 2 |
| `synthesize_verdict()` | `agents/orchestrator.py` | Tasks 2, 3 |
| `VolatilityThesis` | `models/analysis.py` | Task 3 |
| `ExtendedTradeThesis` | `models/analysis.py` | Task 3 |
| `build_cleaned_volatility_thesis()` | `agents/_parsing.py` | Task 3 |
| Migration runner | `data/database.py` | Task 4 |
| `_persist_result()` | `agents/orchestrator.py` | Task 4 |

### External
None. All changes are internal to the codebase.

## Success Criteria (Technical)

### Quality Gates (every commit)
- All 3,921+ Python tests pass
- `ruff check` + `ruff format` clean
- `mypy --strict` passes
- All 38 E2E tests pass

### Functional Targets (post-50 debates)
| Metric | Current | Target |
|---|---|---|
| Unanimous agreement rate | 100% | < 50% |
| Ensemble entropy (mean) | 0.0 | > 0.4 |
| Trend echo rate | 80% | < 60% |
| Fundamental confidence std | 0.000 | > 0.10 |
| Contrarian execution rate | 20% | > 80% |
| Per-agent token count | ~2,600 | < 2,000 |

## Estimated Effort

**Size**: L (Large) — 8 FRs across 3 modules, ~12-15 files touched, ~350-500 lines new code + tests.

**Critical path**: Task 1 → Task 2 → Task 3 → Task 5 (serialized due to shared file conflicts in `orchestrator.py`). Task 4 can run in parallel with Task 3.

**Risk**: Wave 1 (Tasks 1+2) must ship atomically — partitioned context without updated prompt rules would reference missing fields.

## Tasks Created
- [ ] #346 - Domain context renderers + prompt calibration (parallel: false)
- [ ] #347 - Orchestrator wiring + log-odds pooling (parallel: false)
- [ ] #348 - Ensemble diversity — model fields, vol direction, entropy, gate (parallel: true)
- [ ] #349 - Agent prediction persistence (parallel: true)
- [ ] #350 - Full test suite + lint + typecheck verification (parallel: false)
- [ ] #351 - Live validation — run debates, measure success criteria (parallel: false)

Total tasks: 6
Parallel tasks: 2 (#348 + #349 can run concurrently after #347)
Sequential tasks: 4 (#346 → #347 → [#348 || #349] → #350 → #351)
Estimated total effort: 23-33 hours

## Test Coverage Plan
Total test files planned: 8
Total test cases planned: 48+
