# Research: debate-calibrate

## PRD Summary

The 6-agent debate system is functionally a 1-agent system — all agents agree 100% of the time because they receive identical full `MarketContext` including pre-computed `COMPOSITE SCORE` and `DIRECTION`. The fix is two structural changes: (1) information partitioning — each Phase 1 agent sees only domain-specific fields, and (2) log-odds pooling replaces linear weighted averaging. Follow-up improvements add volatility direction voting, relaxed contrarian gate, vote entropy measurement, and outcome attribution for future self-calibrating weights.

9 functional requirements across 3 waves + validation wave.

## Relevant Existing Modules

- `agents/_parsing.py` — **PRIMARY TARGET (Wave 1)**. Contains `render_context_block()` (lines 377-597, ~80 fields), `PROMPT_RULES_APPENDIX` (lines 67-92, with COMPOSITE SCORE anchors), `_render_optional()`, `_render_regime_label()`, `compute_citation_density()`, `build_cleaned_*` helpers. New domain renderers go here.
- `agents/orchestrator.py` — **PRIMARY TARGET (Wave 1-3)**. Contains `_run_v2_agents()` (single `context_text` at line 1040), `synthesize_verdict()` (lines 755-901, linear pooling at 802-824), `AGENT_VOTE_WEIGHTS` (line 648), contrarian gate `if phase1_failures < 2:` (line 1284), VolatilityThesis direction skip (lines 791-793).
- `models/analysis.py` — **Wave 2 changes**. `VolatilityThesis` (lines 524-565, frozen, NO direction field), `ExtendedTradeThesis` (lines 706-736, NO ensemble_entropy), `TradeThesis` (lines 436-521), `DebateResult` (in `_parsing.py` lines 334-359), `MarketContext` (lines 52-171).
- `agents/prompts/` — Volatility prompt update for directional output (FR-6).
- `data/migrations/` — Latest is `024_drop_dead_artifacts.sql`. Next: `025`.
- `data/repository.py` — `save_debate()` (lines 277-330), needs `save_agent_predictions()`.
- `services/outcome_collector.py` — `OutcomeCollector` (lines 36-381). `AnalyticsConfig.holding_periods` already defaults to `[1, 5, 10, 20]`. Collector iterates all periods when `holding_days=None`.
- `models/enums.py` — `SignalDirection(StrEnum)`: BULLISH, BEARISH, NEUTRAL.

## Existing Patterns to Reuse

### Render Pattern
All domain renderers follow `render_context_block()`'s structure: build `lines: list[str]`, call `_render_optional(label, value, fmt)` for each optional field, join with `"\n"`. Factor shared identity into `_render_identity_block(ctx) -> list[str]`.

### NaN/Inf Guard Pattern
`_render_optional()` already guards `None` and non-finite values. Reuse for all domain renderers. New `ensemble_entropy` field needs `math.isfinite()` validator (matching `agent_agreement_score` pattern at lines 728-735).

### Frozen Model Construction
`VolatilityThesis` is `frozen=True`. `build_cleaned_volatility_thesis()` in `_parsing.py` reconstructs via constructor — must add `direction=output.direction` to the constructor call.

### Pure Function Pattern
`_log_odds_pool()` and `_vote_entropy()` are pure functions with no side effects, placed in `orchestrator.py` alongside existing pure helpers like `compute_agreement_score()`.

### Agent Prediction Persistence
Orchestrator already has optional `repository` param in `run_debate()`. Pattern: `if repository is not None: await repository.save_agent_predictions(...)`.

### Re-export Pattern
New renderers must be exported from `agents/__init__.py`.

## Existing Code to Extend

### `agents/_parsing.py`
- `render_context_block()` (line 377) — stays UNCHANGED. Used by Risk, Contrarian, persistence, display, and `compute_citation_density()`.
- `PROMPT_RULES_APPENDIX` (line 67) — remove two COMPOSITE SCORE anchor lines, replace with domain-neutral calibration.
- `_render_optional()` (line 362) — reuse in new renderers.
- `build_cleaned_volatility_thesis()` — update to pass `direction=output.direction`.

### `agents/orchestrator.py`
- `_run_v2_agents()` (line 1040) — replace single `context_text = render_context_block(context)` with 4 domain-specific + 1 full render.
- `synthesize_verdict()` (line 802-824) — replace linear pooling with `_log_odds_pool()`. Keep agreement-based cap after.
- Direction voting (line 791-793) — remove `isinstance(output, VolatilityThesis): continue` skip.
- Contrarian gate (line 1284) — `< 2` → `< 3`.

### `models/analysis.py`
- `VolatilityThesis` (line 524) — add `direction: SignalDirection = SignalDirection.NEUTRAL`.
- `ExtendedTradeThesis` (line 706) — add `ensemble_entropy: float | None = None` with `isfinite()` validator.

### `services/outcome_collector.py`
- Already fully supports multi-period collection. CLI passes `None`, API defaults `None`, collector iterates all configured periods. **No changes needed (FR-9 eliminated).**

## Potential Conflicts

### PROMPT_RULES_APPENDIX is Shared
Imported by bull, bear, risk, trend, volatility, flow, and fundamental agents. After removing COMPOSITE SCORE anchors, verify no individual agent prompt separately references `COMPOSITE SCORE`. The replacement domain-neutral calibration applies to all agents equally.

### Risk Weight Removal
`AGENT_VOTE_WEIGHTS["risk"] = 0.15` is dead code — confirmed by tracing all code paths. Will be removed in FR-4. No downstream impact since it was never read.

### VolatilityThesis Deserialization
Adding `direction: SignalDirection = SignalDirection.NEUTRAL` with a default means existing `vol_json` records without `direction` deserialize correctly. Must test roundtrip.

### Citation Density
`compute_citation_density()` uses full `render_context_block()` output to measure cited context labels. With partitioned context, agents see fewer labels — their citation density may appear artificially high. No code change required (it still measures against the full context), but metric interpretation changes.

## Resolved Questions

1. **MACD inclusion**: MACD is a genuine indicator computed in `indicators/trend.py`, not a scan-pipeline conclusion. **Include MACD in `render_trend_context()`**. PRD exclusion was an error. Only `COMPOSITE SCORE`, `DIRECTION`, and `DIRECTION CONFIDENCE` are excluded (actual scan conclusions).

2. **Risk weight is dead code — remove it**: `AGENT_VOTE_WEIGHTS["risk"] = 0.15` is confirmed dead. `RiskAssessment` is passed separately to `synthesize_verdict()` as `risk_assessment`, never placed in `agent_outputs`. The confidence loop iterates only `agent_outputs`, so `risk`'s weight is never looked up. `RiskAssessment` has `confidence: float` but no `direction: SignalDirection`. Its confidence is never read — only `risk_level`, `max_loss_estimate`, and `key_risks` are used (for narrative text). Risk provides position sizing, not directional alpha. **Remove `"risk": 0.15` from `AGENT_VOTE_WEIGHTS`.**

3. **FR-9 requires zero code changes**: CLI `outcomes collect` already passes `holding_days=None` when no `--holding-days` arg is given (`cli/outcomes.py` line 42). API endpoint defaults `holding_days=None` (`routes/analytics.py` line 105). `OutcomeCollector.collect_outcomes(None)` iterates all `AnalyticsConfig.holding_periods` (default: `[1, 5, 10, 20]`). **FR-9 is already implemented.** Epic scope reduces from 9 to 8 FRs.

4. **agent_predictions wiring — extend `_persist_result()`**: The elegant solution uses the existing orchestrator-owned persistence pattern. Three persistence sites need the same fix:

   **a) Orchestrator CLI path** (`_persist_result()` at orchestrator.py line 577): Currently calls `await repository.save_debate(...)` but **discards the return value** (returns `None`). Fix: capture `debate_id = await repository.save_debate(...)`, then `await repository.save_agent_predictions(debate_id, result)`. All agent outputs are already available on `DebateResult` fields (`bull_response`, `bear_response`, `flow_response`, etc.). Change return type to `int | None`.

   **b) API single-debate path** (`routes/debate.py` line 190): Calls `repo.save_debate(...)` and discards the return. Fix: capture `debate_id`, call `save_agent_predictions()` immediately after.

   **c) API batch-debate path** (`routes/debate.py` line 435): **Already captures** `debate_id = await repo.save_debate(...)`. Just add `save_agent_predictions()` call after.

   This is the cleanest approach because: (1) it follows the existing persistence pattern, (2) all agent data is already on `DebateResult`, (3) no new fields on `DebateResult`, (4) no hook infrastructure, (5) predictions are always saved atomically with the debate they belong to.

## Recommended Architecture

### Wave 1 (Core — must ship together)
1. **FR-1**: Add `_render_identity_block()` + 4 domain renderers in `_parsing.py`. Each includes shared identity + domain fields only. MACD included in trend context. Excludes only `COMPOSITE SCORE`, `DIRECTION`, `DIRECTION CONFIDENCE`.
2. **FR-2**: In `_run_v2_agents()`, generate 5 context strings: 4 domain-specific + 1 full. Pass domain text to each Phase 1 agent. Risk and Contrarian keep full.
3. **FR-3**: Replace COMPOSITE SCORE anchors in `PROMPT_RULES_APPENDIX` with domain-neutral calibration language.
4. **FR-4**: Add `_log_odds_pool()` pure function. Replace linear averaging in `synthesize_verdict()`. Remove dead `"risk": 0.15` from `AGENT_VOTE_WEIGHTS`. Keep agreement cap after.

### Wave 2 (Enhanced Signal — independent)
5. **FR-5**: Add `ensemble_entropy: float | None = None` to `ExtendedTradeThesis` with `isfinite()` validator. Add `_vote_entropy()` in orchestrator. Compute in `synthesize_verdict()`.
6. **FR-6**: Add `direction: SignalDirection = SignalDirection.NEUTRAL` to `VolatilityThesis`. Update volatility prompt with IV regime calibration anchors. Remove `isinstance(VolatilityThesis): continue` skip. Update `build_cleaned_volatility_thesis()`.
7. **FR-7**: Change `phase1_failures < 2` to `phase1_failures < 3`.

### Wave 3 (Measurement Infrastructure)
8. **FR-8**: Migration `025_agent_predictions.sql`. Add `AgentPrediction` model. Add `Repository.save_agent_predictions()`. Wire into 3 persistence sites: `_persist_result()` (capture `save_debate()` return), API single-debate (capture return), API batch (already captured — add call).

**FR-9 eliminated** — multi-period outcome collection already works. CLI passes `None`, collector iterates all configured periods.

## Test Strategy Preview

### Existing Test Patterns
- `tests/agents/` — agent tests use `TestModel` via `model=None` at agent init, `agent.run(model=TestModel())` in tests. Mocked `MarketContext` fixtures.
- `tests/models/` — model tests validate field constraints, validators, serialization roundtrip, backward compatibility.
- `tests/data/` — in-memory SQLite fixtures, migration verification.
- `tests/services/` — mocked external calls, outcome collector tests.

### New Tests Needed
- **Unit**: `_render_identity_block()`, `render_trend_context()`, `render_volatility_context()`, `render_flow_context()`, `render_fundamental_context()` — verify field inclusion/exclusion per domain.
- **Unit**: `_log_odds_pool()` — all-agree, split-vote, extreme-probability, single-agent cases per NFR-7.
- **Unit**: `_vote_entropy()` — unanimous (0.0), two-way split, three-way split, empty dict.
- **Model**: `VolatilityThesis` with/without `direction` field (backward compat deserialization).
- **Model**: `ExtendedTradeThesis` with/without `ensemble_entropy` (backward compat).
- **Integration**: `synthesize_verdict()` with partitioned agents — verify log-odds output, entropy computation, volatility direction inclusion.
- **Migration**: `025_agent_predictions.sql` creates table correctly.
- **Naming convention**: `test_<module>.py` in corresponding `tests/` subdirectory.

## Estimated Complexity

**L (Large)** — 8 functional requirements (FR-9 eliminated) across 3 modules (agents, models, data), 3 waves with dependencies, ~12-15 files touched, ~350-500 lines of new code + tests. The core structural change (Wave 1) must ship atomically. Each wave is independently testable and changes are well-specified with exact code locations identified.

Key risk: Wave 1's 4 FRs must ship together since partitioned context without updated prompts would reference missing fields. No individual FR in Wave 1 is valid in isolation.
