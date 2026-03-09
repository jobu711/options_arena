---
name: ai-agent-tune
description: Agent calibration feedback loop and prompt engineering v2 — measure per-agent accuracy, auto-tune vote weights, extract and optimize all prompts with regression testing
status: planned
created: 2026-03-09T16:08:16Z
---

# PRD: ai-agent-tune

## Executive Summary

Build a closed-loop agent tuning system that measures per-agent prediction accuracy
against real outcomes, auto-adjusts `AGENT_VOTE_WEIGHTS`, and upgrades all 6 agent
prompts with extracted templates, few-shot examples, and regression tests. The
calibration data then guides future prompt iteration — creating a virtuous cycle where
debate quality improves with every run.

The existing infrastructure already collects outcome data at 4 time horizons
(T+1/T+5/T+10/T+20 via `OutcomeCollector`) and persists per-agent predictions
(`AgentPrediction` model, migration 025). This epic closes the feedback loop: analyze
that data per-agent, expose calibration metrics, and use the insights to refine prompts.

## Problem Statement

Options Arena's 6 debate agents operate without knowing if they're right. The system
collects outcome data and per-agent predictions but never analyzes them to answer:

- **Which agents are accurate?** No per-agent direction hit rate or confidence calibration.
- **Are vote weights optimal?** `AGENT_VOTE_WEIGHTS` are hand-tuned constants with no
  empirical basis.
- **Are prompts effective?** No regression tests, no quality benchmarks, no way to measure
  if a prompt change improved output.
- **Is confidence calibrated?** An agent saying "0.8 confidence" should be right ~80% of
  the time. No way to verify this.

The agents are stable (482 unit tests, no TODOs), but operating blind. Every debate run
generates data that could improve the next one, but that data is wasted.

## User Stories

### US1: Analyst reviews agent track record
**As** an options analyst using the debate tool,
**I want** to see which agents are most accurate over time,
**So that** I can weight their opinions appropriately when making trading decisions.

**Acceptance criteria:**
- CLI command shows per-agent accuracy table (direction hit rate, mean confidence, Brier score)
- API endpoint returns structured calibration data
- Data filterable by time window (30d, 90d, all-time)
- At least 10 outcomes required before showing agent stats (avoid small-sample noise)

### US2: System auto-tunes vote weights
**As** the system operator,
**I want** vote weights to adapt based on observed agent accuracy,
**So that** more accurate agents have more influence on the verdict.

**Acceptance criteria:**
- Auto-tuned weights computed from rolling 90-day accuracy window
- Weights exposed via `outcomes agent-weights` CLI command
- Config toggle to enable/disable auto-tuning (`DebateConfig.auto_tune_weights`)
- Manual weights remain the default; auto-tune is opt-in
- Weights sum intentionally < 1.0 (maintain existing constraint)
- Risk agent excluded from directional voting (maintain existing constraint)

### US3: Developer improves prompt quality with regression tests
**As** a developer iterating on agent prompts,
**I want** automated tests that catch prompt regressions,
**So that** I can change prompts confidently without degrading output quality.

**Acceptance criteria:**
- All 6 agent prompts extracted to `agents/prompts/` (currently only 2 of 6)
- Prompt regression test suite validates structure (version header, required sections)
- Token count tests ensure prompts fit within budget (system prompt < 1500 tokens)
- Citation density benchmark (flag prompts that produce < 20% citation rate)
- `TestModel`-based tests verify each prompt produces valid structured output

### US4: Developer adds few-shot examples to prompts
**As** a developer tuning agent output quality,
**I want** golden output examples embedded in prompts,
**So that** the LLM has concrete patterns to follow for each agent role.

**Acceptance criteria:**
- Each agent prompt includes 1 few-shot example of ideal output
- Examples use real (anonymized) market data, not synthetic
- Examples demonstrate proper citation density and data anchoring
- Token budget accommodates examples (adjust from 1500 to 2000 if needed)
- Output quality measurably improves (citation density > 30% target)

### US5: Analyst views confidence calibration
**As** an analyst evaluating debate quality,
**I want** to see if agent confidence predictions match reality,
**So that** I can trust (or discount) high-confidence recommendations.

**Acceptance criteria:**
- Calibration curve data: confidence buckets (0-0.2, 0.2-0.4, etc.) vs actual hit rate
- Per-agent and aggregate views
- CLI `outcomes calibration` subcommand
- API `GET /api/analytics/agent-calibration` endpoint

## Requirements

### Functional Requirements

#### FR1: Per-Agent Accuracy Tracking
- Compute direction hit rate per agent (correct direction vs actual price move)
- Compute mean confidence per agent
- Compute Brier score per agent: `mean((confidence - outcome)^2)` where outcome is 0 or 1
- Use existing `AgentPrediction` records joined with `Outcome` records
- Support time-window filtering (30d, 90d, all-time)
- Minimum sample size: 10 outcomes before reporting stats
- Models: `AgentAccuracyReport`, `CalibrationBucket`, `AgentCalibrationData`

#### FR2: Auto-Tune Vote Weights
- Rolling 90-day accuracy window for weight computation
- Weight formula: normalized inverse Brier score (lower Brier = higher weight)
- Floor weight of 0.05 per agent (no agent gets zero influence)
- Cap weight of 0.35 per agent (no single agent dominates)
- Risk agent excluded from directional weight tuning (existing constraint)
- Contrarian weight scales with `_vote_entropy()` (higher entropy = more contrarian weight)
- Store computed weights in `auto_tune_weights` SQLite table
- Config: `DebateConfig.auto_tune_weights: bool = False` (opt-in)
- Orchestrator reads auto-tuned weights when enabled, falls back to manual `AGENT_VOTE_WEIGHTS`

#### FR3: Prompt Extraction & Organization
- Extract inline prompts from `bull.py`, `bear.py`, `risk.py`, `volatility.py`,
  `flow_agent.py`, `fundamental_agent.py` into `agents/prompts/`
- One file per agent: `bull.py`, `bear.py`, `risk.py`, `volatility.py`, `flow.py`, `fundamental.py`
- Already extracted: `trend_agent.py`, `contrarian_agent.py` (no changes needed)
- Each prompt file exports a single constant: `{AGENT}_SYSTEM_PROMPT`
- Agent modules import from `agents/prompts/` instead of defining inline
- `PROMPT_RULES_APPENDIX` stays in `_parsing.py` (shared across all agents)
- `RISK_STRATEGY_TREE` moves to `agents/prompts/risk.py`

#### FR4: Few-Shot Examples
- Add 1 golden output example per agent prompt
- Examples sourced from real debate outputs (anonymize ticker to "ACME")
- Examples demonstrate: proper data citation, appropriate confidence level, contract references
- Format: `## Example Output\n{json block}` appended before `PROMPT_RULES_APPENDIX`
- Groq/Llama-optimized formatting (JSON blocks, not markdown tables)

#### FR5: Prompt Regression Test Suite
- `tests/unit/agents/test_prompt_structure.py` — validates all 8 prompt constants:
  - Version header present (`# VERSION: vX.Y`)
  - Token count within budget (< 2000 tokens including few-shot)
  - Required sections present (JSON schema, rules block)
  - `PROMPT_RULES_APPENDIX` concatenated (not missing)
- `tests/unit/agents/test_prompt_quality.py` — `TestModel`-based quality tests:
  - Each prompt + mock context produces valid structured output
  - Citation density > 20% threshold on mock context
  - No `<think>` tags in output (validator chain working)

#### FR6: CLI & API Endpoints
- `outcomes agent-accuracy` — per-agent accuracy table (Rich table)
- `outcomes calibration` — confidence calibration data (Rich table)
- `outcomes agent-weights` — current vs auto-tuned weights comparison
- `GET /api/analytics/agent-accuracy` — `list[AgentAccuracyReport]`
- `GET /api/analytics/agent-calibration` — `AgentCalibrationData`
- `GET /api/analytics/agent-weights` — current + auto-tuned weights

### Non-Functional Requirements

#### NFR1: Performance
- Accuracy queries scan `agent_predictions` + `outcomes` tables — add index on
  `agent_predictions.agent_name` + `agent_predictions.scan_run_id`
- Calibration computation: < 500ms for 1000 predictions
- Auto-tune weight computation: < 1s for 90-day window
- Prompt extraction: zero runtime performance impact (compile-time constant assignment)

#### NFR2: Data Integrity
- Minimum sample size enforced (10 outcomes) — never report stats from insufficient data
- Brier score uses standard formula (no custom modifications)
- Auto-tuned weights validated: sum < 1.0, each in [0.05, 0.35], risk excluded
- Calibration buckets use standard binning (0.0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0)

#### NFR3: Backward Compatibility
- Manual `AGENT_VOTE_WEIGHTS` remain the default
- Auto-tune is opt-in via config (`ARENA_DEBATE__AUTO_TUNE_WEIGHTS=true`)
- Prompt extraction preserves exact prompt text (no content changes in extraction step)
- Few-shot additions are a separate step after extraction (version bump v1.0 → v2.0)

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Agent accuracy visibility | All 6 agents have accuracy stats after 10+ outcomes | CLI `outcomes agent-accuracy` |
| Calibration data available | Confidence buckets populated for each agent | API endpoint returns non-empty data |
| Prompt extraction complete | 8/8 prompts in `agents/prompts/` | File count check |
| Prompt regression tests | 100% pass rate on structure + quality tests | `pytest tests/unit/agents/test_prompt_*` |
| Citation density improvement | Mean citation density > 30% (up from ~20% baseline) | `compute_citation_density()` on real debates |
| Auto-tune convergence | Auto-tuned weights differ from manual by < 0.15 per agent | CLI `outcomes agent-weights` |
| Test coverage | 50+ new tests across calibration + prompt regression | Test count |

## Constraints & Assumptions

- **Minimum data requirement**: Auto-tune and calibration require at least 10 completed
  outcomes with agent predictions. New installations won't have calibration data immediately.
- **Groq-first**: Prompt optimization targets Llama 3.3 70B via Groq. Anthropic-specific
  prompt variants are deferred (separate epic when usage justifies it).
- **No UI dashboard**: CLI + API only for this epic. Vue dashboard components for
  calibration visualization are out of scope.
- **Existing test infrastructure**: Uses `TestModel` (PydanticAI) for prompt quality tests —
  no real LLM calls in CI.
- **Prompt token budget**: System prompts may grow from ~1500 to ~2000 tokens with few-shot
  examples. Context window (8192) has headroom.

## Out of Scope

- **Vue dashboard for calibration** — CLI + API only; dashboard is a follow-up epic
- **Anthropic/Claude prompt variants** — Groq-only optimization; multi-provider prompts later
- **Real-time A/B testing infrastructure** — Prompt versioning yes, live A/B switching no
- **Orchestrator refactor** — `build_market_context()` extraction is a separate epic (#3 from
  /pm:next targeting). This epic keeps the orchestrator structure as-is.
- **Dynamic agent selection** — Regime-based agent skipping is a strategic opportunity, not
  part of this epic
- **Backtesting dashboard** — The `backtesting-engine` PRD covers the full dashboard; this
  epic provides the agent-specific calibration data that feeds into it

## Dependencies

### Internal
- **`AgentPrediction` model + migration 025** — already shipped, persists per-agent outputs
- **`OutcomeCollector`** — already shipped, collects T+1/T+5/T+10/T+20 P&L
- **`extract_agent_predictions()`** — already shipped, extracts predictions from debate results
- **`compute_citation_density()`** — already shipped in `_parsing.py`
- **`AGENT_VOTE_WEIGHTS`** — existing manual weights in orchestrator
- **Repository layer** — `data/repository.py` for new calibration queries

### External
- None — all data is local (SQLite), no new external services

## Implementation Phases

### Phase 1: Prompt Extraction (Foundation)
Extract all 6 remaining inline prompts to `agents/prompts/`. Zero behavior change.
Enables all subsequent prompt work.

### Phase 2: Calibration Infrastructure
New models (`AgentAccuracyReport`, `CalibrationBucket`, `AgentCalibrationData`),
repository queries, migration for indexes. CLI `outcomes agent-accuracy` +
`outcomes calibration`. API endpoints.

### Phase 3: Prompt Quality Suite
Regression test suite for all 8 prompts. Token budget tests. Citation density
benchmarks. `TestModel`-based quality validation.

### Phase 4: Few-Shot Examples
Add golden examples to each prompt. Version bump to v2.0. Measure citation density
improvement.

### Phase 5: Auto-Tune Weights
Weight computation from rolling accuracy. Config toggle. `outcomes agent-weights`
CLI. Orchestrator integration (opt-in).

## Effort Estimate

**Total: XL (1.5-2 weeks)**
- Phase 1: S (2-3 hours) — mechanical extraction
- Phase 2: L (2-3 days) — models, queries, CLI, API
- Phase 3: M (1-2 days) — test suite
- Phase 4: M (1-2 days) — prompt crafting + measurement
- Phase 5: L (2-3 days) — weight computation, integration, testing
