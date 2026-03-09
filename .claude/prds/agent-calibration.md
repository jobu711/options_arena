---
name: agent-calibration
description: Per-agent accuracy tracking, confidence calibration metrics, and auto-tuned vote weights from rolling outcome data
status: planned
created: 2026-03-09T17:30:00Z
parent: ai-agent-tune
---

# PRD: agent-calibration

## Executive Summary

Build a closed-loop calibration system that measures per-agent prediction accuracy
against real outcomes, exposes calibration metrics via CLI and API, and auto-adjusts
`AGENT_VOTE_WEIGHTS` based on empirical performance. The existing infrastructure already
collects outcome data (T+1/T+5/T+10/T+20 via `OutcomeCollector`) and persists per-agent
predictions (`AgentPrediction` model, migration 025). This epic closes the feedback loop.

Split from the `ai-agent-tune` PRD. This epic has zero file overlap with its sibling
`prompt-engineering-v2` and can be developed fully in parallel.

## Problem Statement

Options Arena's 6 debate agents operate without knowing if they're right. The system
collects outcome data and per-agent predictions but never analyzes them:

- **Which agents are accurate?** No per-agent direction hit rate or confidence calibration.
- **Are vote weights optimal?** `AGENT_VOTE_WEIGHTS` are hand-tuned constants (trend=0.25,
  volatility=0.20, flow=0.20, fundamental=0.15, contrarian=0.05, risk=0.0) with no
  empirical basis.
- **Is confidence calibrated?** An agent saying "0.8 confidence" should be right ~80% of
  the time. No way to verify this.

Every debate run generates data that could improve the next one, but that data is wasted.

## User Stories

### US1: Analyst reviews agent track record
**As** an options analyst using the debate tool,
**I want** to see which agents are most accurate over time,
**So that** I can weight their opinions appropriately when making trading decisions.

**Acceptance criteria:**
- CLI `outcomes agent-accuracy` shows per-agent accuracy table
- Columns: Agent, Direction Hit Rate, Mean Confidence, Brier Score, Sample Size
- `--window 30` and `--window 90` for time filtering, no flag = all-time
- API `GET /api/analytics/agent-accuracy` returns structured data
- Minimum 10 outcomes before showing agent stats (avoid small-sample noise)

### US2: Analyst views confidence calibration
**As** an analyst evaluating debate quality,
**I want** to see if agent confidence predictions match reality,
**So that** I can trust (or discount) high-confidence recommendations.

**Acceptance criteria:**
- Calibration buckets: 0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0
- Per-agent and aggregate views
- CLI `outcomes calibration` with optional `--agent` filter
- API `GET /api/analytics/agent-calibration` endpoint

### US3: System auto-tunes vote weights
**As** the system operator,
**I want** vote weights to adapt based on observed agent accuracy,
**So that** more accurate agents have more influence on the verdict.

**Acceptance criteria:**
- Auto-tuned weights computed from rolling 90-day accuracy window
- `outcomes agent-weights` CLI shows manual vs auto-tuned comparison
- Config toggle: `DebateConfig.auto_tune_weights: bool = False` (opt-in)
- Manual weights remain the default; auto-tune is opt-in
- Weights sum intentionally < 1.0 (maintain Bordley 1982 constraint at 0.85)
- Risk agent excluded from directional voting (always 0.0)
- Each weight floored at 0.05, capped at 0.35

## Requirements

### Functional Requirements

#### FR1: Per-Agent Accuracy Tracking
- Compute direction hit rate per agent (predicted direction vs actual stock price move)
- Compute mean confidence per agent
- Compute Brier score per agent: `mean((confidence - outcome)^2)` where outcome is 0 or 1
- JOIN `agent_predictions` with outcomes via: `agent_predictions.debate_id` -> `ai_theses.id`
  -> `recommended_contracts.thesis_id` -> `contract_outcomes.recommended_contract_id`
- Support time-window filtering (30d, 90d, all-time) via `agent_predictions.created_at`
- Minimum sample size: 10 outcomes before reporting stats
- Models: `AgentAccuracyReport` (frozen, validated)

#### FR2: Confidence Calibration
- Standard 5-bucket binning: [0.0-0.2), [0.2-0.4), [0.4-0.6), [0.6-0.8), [0.8-1.0]
- Per-agent and aggregate (agent_name=None) views
- Models: `CalibrationBucket`, `AgentCalibrationData` (frozen, validated)

#### FR3: Auto-Tune Vote Weights
- Rolling 90-day accuracy window for weight computation
- Weight formula: normalized inverse Brier score (`1.0 - brier_score`)
- Floor weight: 0.05 per agent (no agent gets zero influence)
- Cap weight: 0.35 per agent (no single agent dominates)
- Risk agent: always 0.0 (excluded from directional voting)
- Agents with < 10 samples: keep manual weight from `AGENT_VOTE_WEIGHTS`
- Normalize to sum = 0.85 (maintain Bordley 1982 log-odds pooling constraint)
- Store computed weights in `auto_tune_weights` SQLite table
- Config: `DebateConfig.auto_tune_weights: bool = False` (opt-in)
- Orchestrator reads auto-tuned weights when enabled, falls back to manual

#### FR4: Orchestrator Integration
- Add `vote_weights: dict[str, float] | None = None` parameter to `synthesize_verdict()`
- If None, use existing `AGENT_VOTE_WEIGHTS` (backward compatible)
- `run_debate()` loads auto-tuned weights from repository when `config.auto_tune_weights=True`
- `synthesize_verdict()` remains a pure function (weights injected, not fetched)

#### FR5: CLI Subcommands
- `outcomes agent-accuracy [--window DAYS]` — per-agent accuracy Rich table
- `outcomes calibration [--agent NAME]` — confidence calibration Rich table
- `outcomes agent-weights` — manual vs auto-tuned comparison Rich table
- All use sync Typer commands with `asyncio.run()` wrappers

#### FR6: API Endpoints
- `GET /api/analytics/agent-accuracy?window=90` -> `list[AgentAccuracyReport]`
- `GET /api/analytics/agent-calibration?agent=trend` -> `AgentCalibrationData`
- `GET /api/analytics/agent-weights` -> `list[AgentWeightsComparison]`
- Rate-limited (60/minute), returns typed Pydantic models

### Non-Functional Requirements

#### NFR1: Performance
- Add composite index on `agent_predictions(agent_name, created_at)` (migration 026)
- Accuracy queries: < 500ms for 1000 predictions
- Auto-tune weight computation: < 1s for 90-day window

#### NFR2: Data Integrity
- Minimum sample size enforced (10 outcomes) — never report stats from insufficient data
- Brier score uses standard formula (no custom modifications)
- Auto-tuned weights validated: sum ~0.85, each in [0.05, 0.35], risk=0.0
- `math.isfinite()` on all computed floats

#### NFR3: Backward Compatibility
- Manual `AGENT_VOTE_WEIGHTS` remain the default
- Auto-tune is opt-in via config (`ARENA_DEBATE__AUTO_TUNE_WEIGHTS=true`)
- `synthesize_verdict()` with no `vote_weights` arg behaves identically to current
- All existing orchestrator tests pass unchanged

## Implementation Phases

### Wave 1: Foundation (3 parallel issues)
New models, migration 026 (index), DebateConfig field.

### Wave 2: Repository Queries
JOIN logic for accuracy computation, Brier score, calibration buckets. 10-sample minimum.

### Wave 3: CLI + API (3 parallel issues)
`agent-accuracy`, `calibration` CLI commands. 3 API endpoints.

### Wave 4: Auto-Tune (4 issues)
Migration 027, weight computation, orchestrator integration, `agent-weights` CLI.

### Wave 5: Integration Tests
Comprehensive test coverage for the auto-tune path.

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Agent accuracy visibility | All 6 agents have accuracy stats after 10+ outcomes | `outcomes agent-accuracy` |
| Calibration data | Buckets populated per agent | API returns non-empty |
| Auto-tune convergence | Weights differ from manual by < 0.15 per agent | `outcomes agent-weights` |
| Minimum sample guard | No stats shown for < 10 outcomes | Test + manual verification |
| Weight constraints | sum ~0.85, each in [0.05, 0.35], risk=0.0 | Unit tests |
| Test coverage | 35+ new tests | Test count |

## Constraints

- **Minimum data requirement**: Auto-tune and calibration require at least 10 completed
  outcomes with agent predictions. New installations start with manual weights.
- **No UI dashboard**: CLI + API only. Vue dashboard is a follow-up epic.
- **Existing test infrastructure**: Uses mock database and in-memory data for tests.

## Out of Scope

- Prompt extraction and optimization (sibling epic: `prompt-engineering-v2`)
- Few-shot examples and citation density (sibling epic: `prompt-engineering-v2`)
- Vue dashboard for calibration visualization
- Dynamic agent selection / regime-based agent skipping
- Backtesting dashboard (separate PRD: `backtesting-engine`)

## Dependencies

### Internal (all already shipped)
- `AgentPrediction` model + migration 025 — persists per-agent outputs
- `OutcomeCollector` — collects T+1/T+5/T+10/T+20 P&L
- `extract_agent_predictions()` — extracts predictions from debate results
- `AGENT_VOTE_WEIGHTS` — existing manual weights in orchestrator
- Repository layer — `data/repository.py` for new queries
- `ContractOutcome` model — outcome records with `is_winner`, returns

### External
- None — all data is local (SQLite), no new external services

## Effort Estimate

**Total: L (5-6 days)**
- Wave 1: S (1-2 hours) — models, migration, config field
- Wave 2: L (1-2 days) — repository queries with JOIN logic, 10+ tests
- Wave 3: M (1 day) — 3 CLI commands + 3 API endpoints
- Wave 4: L (2 days) — weight computation, orchestrator integration
- Wave 5: M (1 day) — integration test suite
