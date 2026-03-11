# Research: agent-intelligence-loop

## PRD Summary

Three tracks: (1) activate auto-tune weights from outcome accuracy data, (2) web UI
weight tuning tab on Analytics page, (3) close FinancialDatasets GitHub issues #394-#399.

## Critical Finding: ALREADY IMPLEMENTED

**This entire epic has already been implemented, verified, and archived.**

Evidence: `.claude/epics/archived/agent-intelligence-loop/` contains:
- `verification-report.md` — PASS verdict, 19/19 requirements verified
- `epic.md` — full epic decomposition (7 issues: #453-#459)
- 7 issue files (453-459), each with implementation details
- `retro.md` — post-epic retrospective
- `checkpoint.json` — completed state

### Verification Summary (from archived report)

| Track | Status | Evidence |
|-------|--------|----------|
| Auto-tune orchestration | DONE | `agents/orchestrator.py:948` — `auto_tune_weights()` |
| CLI `outcomes auto-tune` | DONE | `cli/outcomes.py:425` — with `--dry-run`, `--window` |
| `WeightSnapshot` model | DONE | `models/analytics.py:1136` — frozen, UTC validated |
| `get_weight_history()` | DONE | `data/_debate.py:468` — groups by created_at DESC |
| API endpoints | DONE | `POST /api/analytics/weights/auto-tune`, `GET /api/analytics/weights/history` |
| Web UI Weight Tuning tab | DONE | `WeightTuningPanel.vue`, `weights.ts` store, `weights.ts` types |
| FD issues #390,#394-#399 | DONE | All 7 issues CLOSED on GitHub |

### Test Coverage (from archived report)

| Test File | Tests |
|-----------|-------|
| `test_analytics_weight_snapshot.py` | 7 |
| `test_weight_history.py` | 6 |
| `test_auto_tune_orchestration.py` | 8 |
| `test_outcomes_auto_tune.py` | 10 |
| `test_analytics_auto_tune.py` | 10 |
| `weight-tuning.spec.ts` (E2E) | 7 |
| **Total** | **48** |

### Git Commits

- `71cdf88` — feat: add WeightSnapshot model and get_weight_history()
- `e7040c8` — feat: add auto_tune_weights() orchestration function
- `f23c517` — feat: add outcomes auto-tune CLI subcommand
- `09c9ea3` — feat: add auto-tune API endpoints
- `3a12d0b` — feat: add Weight Tuning tab to Analytics page
- `a0315ae` — test: add E2E test for Weight Tuning tab

## Relevant Existing Modules

- `agents/orchestrator.py` — `auto_tune_weights()`, `compute_auto_tune_weights()`, `AGENT_VOTE_WEIGHTS`
- `data/_debate.py` — `save_auto_tune_weights()`, `get_latest_auto_tune_weights()`, `get_weight_history()`, `get_agent_accuracy()`
- `models/analytics.py` — `AgentWeightsComparison`, `WeightSnapshot`, `AgentAccuracyReport`
- `cli/outcomes.py` — `auto-tune` subcommand (lines 425-505)
- `api/routes/analytics.py` — POST + GET weight endpoints
- `web/src/components/analytics/WeightTuningPanel.vue` — tab content
- `web/src/stores/weights.ts` — Pinia store
- `web/src/types/weights.ts` — TypeScript interfaces

## Existing Patterns to Reuse

N/A — all patterns were already applied during implementation.

## Existing Code to Extend

N/A — no further extensions needed.

## Potential Conflicts

None — epic is complete and merged to master.

## Open Questions

1. Should the PRD status be updated to `completed`?
2. Should this research redirect to a new PRD if the user intended something different?

## Recommended Architecture

No new architecture needed — everything is built and tested.

## Test Strategy Preview

48 tests already exist and pass (41 unit + 7 E2E).

## Estimated Complexity

**N/A** — already implemented. Zero remaining work.
