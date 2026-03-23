---
name: agent-infrastructure-evolution
status: backlog
created: 2026-03-22T16:13:36Z
progress: 0%
prd: .claude/prds/agent-infrastructure-evolution.md
type: parent
branch: epic/agent-infrastructure-evolution
child_epics:
  - agent-infra-eval-harness
  - agent-infra-tool-response
  - agent-infra-model-routing
  - agent-infra-learning-decay
github: null
---

# Epic: agent-infrastructure-evolution (Parent)

## Overview

Quality infrastructure for the 7-agent recommendation pipeline. Four independent child
epics covering evaluation, tool reliability, cost optimization, and learning maturity.
All depend on the unified agent system being complete (orchestrator + cutover). No
cross-dependencies between children — all can execute in parallel.

## Architecture Decisions

- **No new external dependencies** — all patterns reimplemented using existing stack (PydanticAI, Pydantic v2, aiosqlite, pytest)
- **Additive changes only** — no breaking changes to existing models, agents, or APIs
- **ToolResponse keeps `str` return type** (Option A from PRD) — `model_dump_json()` preserves existing tool signatures
- **Migration numbering starts at 038** — orchestrator epic reserves 037
- **Eval fixtures dual-stored** — git-tracked JSON for reproducibility + SQLite for history
- **Confidence decay is outcome-triggered** — runs when `outcomes collect` processes new data, not on a timer
- **Model grader uses different provider** than debate agents to avoid "grading your own homework"

## Child Epic Summary

| Epic | Scope | Dependencies | Est. Tasks |
|------|-------|-------------|------------|
| agent-infra-eval-harness | Eval framework (3 grader types, pass@k, baselines) + regression test fixtures | unified-agent-system | 8-10 |
| agent-infra-tool-response | `ToolResponse` model, refactor 23 tools, update desk prompts | unified-agent-system | 4-5 |
| agent-infra-model-routing | `ModelTier`, per-desk complexity routing, `DeskMetrics`, cost tracking | unified-agent-system | 4-5 |
| agent-infra-learning-decay | Confidence decay on `StrategyRule`, auto-promote/demote, rules-distill skill | unified-agent-system | 4-5 |

## Dependency Graph

```
unified-agent-system (prerequisite)
        |
        v
  ┌─────┼─────────┬──────────────┐
  v     v         v              v
eval  tool-     model-       learning-
harness response  routing      decay
```

All four child epics are independent and can execute in any order or in parallel.

## Shared Branch: `epic/agent-infrastructure-evolution`

All 4 child epics commit to the **same branch**. Coordination rules:

### Migration Number Assignments (No Conflicts)

| Migration | Epic | File |
|-----------|------|------|
| 038 | agent-infra-learning-decay | `038_confidence_decay.sql` |
| 039 | agent-infra-eval-harness | `039_eval_runs.sql` |
| 040 | agent-infra-model-routing | reserved (cost tracking, if needed) |

### File Ownership (No Overlapping Edits)

| File | Owner Epic | Others: Read Only |
|------|-----------|-------------------|
| `agents/_toolsets.py` | tool-response | — |
| `agents/prompts/recommend_*.py` | tool-response | — |
| `models/tool_response.py` (NEW) | tool-response | — |
| `models/eval.py` (NEW) | eval-harness | — |
| `models/enums.py` | tool-response (ToolStatus) | learning-decay (no conflict — different enums) |
| `models/recommendation.py` | model-routing (DeskMetrics, RecommendationCost) | — |
| `models/strategy.py` | learning-decay (confidence fields) | — |
| `agents/model_config.py` | model-routing | — |
| `learning/strategy_book.py` | learning-decay | — |
| `data/_eval.py` (NEW) | eval-harness | — |
| `data/_learning.py` | learning-decay | — |
| `data/repository.py` | eval-harness + learning-decay (both add mixins — coordinate) |
| `cli/` | eval-harness (eval subcommand) | learning-decay (learn subcommand updates) |
| `api/` | eval-harness (eval routes) | model-routing (cost routes) |

### Merge Coordination

- Each child epic creates atomic commits with `Issue #NNN:` prefix
- No force-pushes on shared branch
- Run `uv run pytest -m "not exhaustive" -n auto -q` after each task to catch cross-epic regressions
- One PR from `epic/agent-infrastructure-evolution` → `master` when all 4 children complete

## Success Criteria (Technical)

1. `options-arena eval check` runs 10+ evals and reports pass@k metrics
2. Eval baselines exist for all 6 desks + synthesis agent
3. All 23 tools in `_toolsets.py` return `ToolResponse` JSON with status + next_actions
4. `route_model_tier()` correctly routes 3 tiers based on `MarketContext` complexity
5. Batch recommendations show measurable cost reduction (>30%) with routing enabled
6. Strategy rules show confidence scores and decay status in `learn playbook`
7. Auto-promotion/demotion fires at threshold boundaries
8. Regression test suite has 5+ fixtures from historical wrong recommendations
9. All tests pass: `ruff check`, `pytest`, `mypy --strict`

## Estimated Effort

- **Total tasks**: ~21-25 across 4 child epics
- **Total LOC**: ~2,400-3,300 (1,500-2,200 new + 900-1,100 modified)
- **Critical path**: None — all epics parallel. Recommended order: eval-harness first (establishes measurement), then tool-response + model-routing in parallel, then learning-decay
