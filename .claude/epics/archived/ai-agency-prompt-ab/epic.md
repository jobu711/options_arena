---
name: ai-agency-prompt-ab
status: backlog
created: 2026-03-17T14:37:45Z
progress: 0%
prd: .claude/prds/ai-agency-evolution.md
parent_epic: ai-agency-evolution
epic_number: 5
dependencies: [ai-agency-weight-tuning]
parallelizable_with: [ai-agency-analysis-tools, ai-agency-ml-tools]
github: [Will be updated when synced to GitHub]
---

# Epic 5: Self-Improvement P2 — Prompt A/B Testing

## Overview

Implement prompt versioning, A/B testing for desk agent prompts, and accuracy tracking. Desk prompts become DB-backed (via `PromptVersion` model) with round-robin variant assignment and Wilcoxon signed-rank comparison after sufficient samples.

## Architecture Decisions

- Scope: Desk agent prompts ONLY. Debate agent prompts remain static module-level constants.
- Desk prompts use `dynamic=True` system prompt with text loaded from DB via `PromptVersion`
- Initial prompt text seeded from `desk_*.py` files into `prompt_versions` table during first-run
- Round-robin assignment ensures balanced sampling across variants
- Wilcoxon signed-rank test after 30+ samples per variant for statistical comparison
- Auto-revert if new prompt degrades below baseline
- Accuracy metric: citation density (define precisely during implementation — see PRD "Design Decisions to Finalize" #3)

## Technical Approach

### Models
- `PromptVersion` frozen model: version_id, agent_name, prompt_hash, prompt_text, is_active, sample_count, accuracy
- `RuleStatus` StrEnum (candidate, approved, rejected) — shared with Epic 6

### Data Layer
- Migration 035: `prompt_versions` table (version_id, agent_name, prompt_hash, prompt_text, is_active, sample_count, accuracy, created_at)
- Repository methods: `save_prompt_version()`, `get_active_prompt()`, `get_prompt_variants()`, `update_prompt_accuracy()`, `promote_prompt()`

### Learning Module
- `learning/prompt_lab.py`:
  - `seed_initial_prompts()` — load from `desk_*.py` files into DB on first run
  - `assign_prompt_variant()` — round-robin selection for A/B split
  - `record_query_quality()` — compute citation density, update sample_count/accuracy
  - `compare_variants()` — Wilcoxon signed-rank test, promote winner or revert
  - `rollback_prompt()` — auto-revert to previous active version

### Desk Agent Integration
- Modify desk agents to load prompt text from DB via `_routing.py` at query time
- Pass loaded prompt via `instructions=` parameter at `run()` time
- Tag each query with `prompt_version_id` for tracking

### API & CLI
- `GET /api/learning/prompts` — list prompt versions by agent
- `POST /api/learning/prompts/{id}/promote` — manual promotion
- CLI: `agency learn prompts`
- LearningDashboard.vue — prompt comparison tab

## Task Breakdown Preview

- [ ] PromptVersion model + migration 035 + repository methods
- [ ] prompt_lab.py (seeding, assignment, comparison, rollback) + tests
- [ ] Desk agent integration (dynamic prompt loading, query tagging)
- [ ] API/CLI endpoints + LearningDashboard prompt tab

## Dependencies

- Epic 4 (Weight Tuning) — `learning/` module must exist
- Epics 1-3 (all desks online for prompt variant testing)

## Success Criteria

- Prompt variants tracked in SQLite with sample counts and accuracy
- Round-robin assignment balances queries across variants
- Wilcoxon test identifies winner after 30+ samples per variant
- Auto-revert works when new prompt degrades
- ~25+ new tests

## Estimated Effort

3-4 issues, ~2 implementation sessions
