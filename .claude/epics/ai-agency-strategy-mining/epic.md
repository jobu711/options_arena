---
name: ai-agency-strategy-mining
status: backlog
created: 2026-03-17T14:37:45Z
progress: 0%
prd: .claude/prds/ai-agency-evolution.md
parent_epic: ai-agency-evolution
epic_number: 6
dependencies: [ai-agency-prompt-ab]
parallelizable_with: [ai-agency-analysis-tools, ai-agency-ml-tools]
github: https://github.com/jobu711/options_arena/issues/613
---

# Epic 6: Self-Improvement P3 — Strategy Mining

## Overview

Implement outcome pattern mining, strategy rule generation with human approval, and learned-pattern injection into desk agent prompts. Three-tier memory: short-term (recent debates), long-term (agent_memory table), reflective (StrategyRule candidates from dimensional grouping).

## Architecture Decisions

- Manual trigger only: CLI `agency learn mine` or `POST /api/learning/mine` — not automatic
- Minimum data: 100 total outcomes before mining available, 20 per pattern cell
- Dimensional grouping: sector × IV bucket × DTE bucket × direction
- Chi-squared test for pattern significance
- Rules require human approval before affecting recommendations (`RuleStatus` enum)
- Learned patterns injected into desk prompts via `<<<LEARNED_PATTERNS>>>` delimited blocks
- Evaluation metrics: Sharpe, Sortino, VaR, CVaR, Calmar per mined strategy (reference only, from existing `analysis/performance.py`)

## Technical Approach

### Models
- `StrategyCondition` frozen model: field, operator (ConditionOperator enum), value
- `StrategyRule` frozen model: rule_id, pattern, conditions, win_rate, avg_return, sample_size, status (RuleStatus)
- `AgentMemory` frozen model: memory_id, agent_name, scope, scope_type, content, sample_size, win_rate, created_at
- `ConditionOperator` StrEnum (eq, gt, lt, gte, lte, in)

### Data Layer
- Migration 036: `strategy_rules` table + `agent_memory` table
- Repository methods: `save_strategy_rule()`, `get_strategy_rules()`, `update_rule_status()`, `save_agent_memory()`, `get_agent_memories()`

### Learning Module
- `learning/strategy_book.py`:
  - `mine_patterns()` — group outcomes by dimensions, compute win rate/avg return per cell
  - `test_significance()` — chi-squared test, minimum 20 samples per cell
  - `generate_rules()` — create `StrategyRule` candidates from significant patterns
  - `render_learned_patterns()` — format approved rules as prompt-injectable text blocks

### Prompt Integration
- `agents/_parsing.py` or desk prompts: inject `<<<LEARNED_PATTERNS>>>` block from approved rules
- Only approved rules affect prompts — candidates and rejected rules are excluded

### API & CLI
- `POST /api/learning/mine` — trigger mining
- `GET /api/learning/playbook` — list strategy rules
- `PUT /api/learning/playbook/{id}` — approve/reject rule
- CLI: `agency learn mine`, `agency learn playbook`
- LearningDashboard.vue — playbook tab with approve/reject buttons

## Task Breakdown Preview

- [ ] StrategyRule + AgentMemory models + migration 036 + repository methods
- [ ] strategy_book.py (mining, chi-squared, rule generation) + tests
- [ ] Learned pattern injection into desk prompts + render_learned_patterns()
- [ ] API/CLI endpoints + LearningDashboard playbook tab

## Dependencies

- Epic 5 (Prompt A/B) — learning module and prompt versioning infrastructure
- Outcome tracking with sufficient historical data (100+ outcomes)

## Success Criteria

- Mining surfaces at least 3 actionable rules from 200+ historical outcomes
- Chi-squared test correctly identifies significant patterns (p < 0.05)
- Human approval workflow works (candidate → approved/rejected)
- Approved rules appear in desk agent prompts
- ~25+ new tests

## Estimated Effort

3-4 issues, ~2 implementation sessions

## Tasks Created
- [ ] #614 - StrategyRule + AgentMemory models, enums, migration 036, repository mixin (parallel: false)
- [ ] #615 - Strategy mining engine — mine_patterns, test_significance, generate_rules (parallel: false)
- [ ] #616 - Learned pattern injection into desk agent prompts (parallel: false)
- [ ] #617 - API endpoints, CLI commands, and LearningDashboard playbook tab (parallel: false)

Total tasks: 4
Parallel tasks: 0
Sequential tasks: 4
Estimated total effort: 16-24 hours

## Test Coverage Plan
Total test files planned: 5
Total test cases planned: ~40
