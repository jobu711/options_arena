---
name: token-optimize
status: backlog
created: 2026-03-23T17:14:33Z
progress: 0%
prd: .claude/prds/token-optimize.md
github: https://github.com/jobu711/options_arena/issues/746
---

# Epic: token-optimize

## Overview

Restructure the `.claude/` context system from "load everything always" (~1,878 lines
auto-injected per session) to a three-tier architecture where only ~300 lines are always
loaded. Tier 1 (architecture, product, algorithms) is read on-demand via a router table.
Tier 2 (module CLAUDE.md files) is compressed 50%. Agent/skill/prompt definitions are
audited and trimmed. No application code changes — config files only.

## Architecture Decisions

- **Tier 0 (<300 lines, always loaded)**: Project identity, boundary table, code pattern
  one-liners, context router, current state, verification commands, common mistakes list.
  Plus 7 rules files (~156 lines). Total ~300 lines.
- **Tier 1 (<400 lines, on-demand)**: Consolidated from 5 removed context files into 3 new
  files (architecture.md, product.md, algorithms.md) + slimmed progress.md.
- **Tier 2 (compressed 50%)**: 14 module CLAUDE.md files reduced from 3,972 to ~2,000 lines
  by removing file listings, import examples, and pattern duplication with Tier 0/1.
- **Router pattern**: CLAUDE.md contains a task-type → file mapping table that tells Claude
  which Tier 1/2 files to read before working. Replaces the current approach of `@`-referencing
  everything.
- **Rules stay**: All 7 `.claude/rules/` files remain auto-loaded — they prevent recurring bugs.
- **No `@`-references in CLAUDE.md**: The rewritten CLAUDE.md has zero `@`-references to context
  files. Claude reads Tier 1 files explicitly via the router when needed.

## Technical Approach

### Tier 0: Root CLAUDE.md Rewrite

Rewrite CLAUDE.md from 311 lines to ~250 lines. Remove:
- Verbose pattern examples (keep 1-liner summaries)
- Full Pydantic/config/CLI code blocks (keep constraint descriptions only)
- `@`-references to 6 context files (replace with router table)
- Duplicated content that also exists in context files

Keep:
- Project identity and tech stack (terse)
- Module boundary table (critical — prevents architecture violations)
- Context router table (new — maps task types to files)
- Common mistakes list (terse "don't do X", no code examples)
- Verification commands
- Git discipline

### Tier 1: Context File Consolidation

| New File | Lines | Sources |
|----------|-------|---------|
| `architecture.md` | ~200 | system-patterns.md (257) + module-summaries.md (125) — deduplicated |
| `product.md` | ~80 | product-context.md (139) — compress CLI/API tables, remove detail |
| `algorithms.md` | ~60 | system-patterns-reference.md (74) — already concise, light trim |
| `progress.md` | ~30 | progress.md (46) — current state only, trim completed/future sections |

Files removed after consolidation:
- `system-patterns.md` (257 lines)
- `system-patterns-reference.md` (74 lines)
- `product-context.md` (139 lines)
- `tech-context.md` (65 lines)
- `module-summaries.md` (125 lines)

### Tier 2: Module CLAUDE.md Compression

Compression strategy applied to all 14 files:
1. Remove file-by-file listings (Claude can use Glob/LS)
2. Remove import path examples (Claude can read the actual code)
3. Remove pattern examples that duplicate Tier 0/1 content
4. Remove re-export listings (Claude can read `__init__.py`)
5. Keep: critical constraints, gotchas, field name mappings, boundary rules

Priority targets (largest files):
- `cli/CLAUDE.md`: 598 → ~250 lines
- `models/CLAUDE.md`: 562 → ~250 lines
- `api/CLAUDE.md`: 490 → ~200 lines
- `services/CLAUDE.md`: 485 → ~200 lines
- `scan/CLAUDE.md`: 456 → ~200 lines
- `data/CLAUDE.md`: 446 → ~200 lines
- `pricing/CLAUDE.md`: 346 → ~150 lines

Smaller files (already concise, light trim):
- `agents/CLAUDE.md`: 197 → ~120 lines
- `indicators/CLAUDE.md`: 160 → ~100 lines
- `agents/prompts/CLAUDE.md`: 72 → ~50 lines
- `scoring/CLAUDE.md`: 62 → ~50 lines
- `analysis/CLAUDE.md`: 44 → ~35 lines
- `learning/CLAUDE.md`: 32 → ~25 lines
- `reporting/CLAUDE.md`: 22 → ~20 lines

### Subagent & Skill Audit

Agent definitions (19 files in `.claude/agents/`):
- Read each definition, check if the agent is actively used
- Remove agents that duplicate built-in capabilities or are never invoked
- Compress remaining agent descriptions (verbose → 2-3 line summaries)

Prompts (28 files in `.claude/prompts/`):
- Identify stale prompts that reference deleted features (old debate system, etc.)
- Remove stale prompts
- No compression needed (not auto-loaded)

Skills:
- Audit registered skills list for redundancy
- PRD/epic workflow skills (pm:*) are preserved — constraint
- Remove or consolidate unused skills

## Tasks Created

- [ ] #747 - Baseline measurement (parallel: false)
- [ ] #749 - Rewrite CLAUDE.md as Tier 0 router (parallel: false)
- [ ] #751 - Create architecture.md — consolidate system-patterns + module-summaries (parallel: true)
- [ ] #753 - Create product.md + algorithms.md (parallel: true)
- [ ] #755 - Trim progress.md to current-state-only (parallel: true)
- [ ] #748 - Remove obsolete context files (parallel: false)
- [ ] #750 - Compress top 7 module CLAUDE.md files (parallel: true)
- [ ] #752 - Compress remaining 7 module CLAUDE.md files (parallel: true)
- [ ] #754 - Audit and trim agent definitions + stale prompts (parallel: true)
- [ ] #756 - After-measurement and validation smoke tests (parallel: false)

Total tasks: 10
Parallel tasks: 6
Sequential tasks: 4
Estimated total effort: ~16.5 hours

## Test Coverage Plan

Total test files planned: 0 (config-only epic — no Python code changes)
Total validation checks planned: 15+ (line counts, file existence, grep checks, test suite run)

## Dependencies

- No external dependencies
- No package changes
- Tasks 3-5 depend on Task 2 (router references Tier 1 file paths)
- Task 6 depends on Tasks 3-5 (don't delete until replacements exist)
- Tasks 7-8 depend on Task 2 (need to know what moved to Tier 0 to avoid duplication)
- Task 9 is independent (can run in parallel with 7-8)
- Task 10 depends on all others

## Success Criteria (Technical)

1. `wc -l CLAUDE.md` < 260 lines (no `@`-references)
2. `wc -l .claude/rules/*.md` stays ~156 lines (unchanged)
3. Total auto-loaded (CLAUDE.md + rules) < 420 lines
4. `wc -l .claude/context/architecture.md .claude/context/product.md .claude/context/algorithms.md .claude/context/progress.md` < 400 lines
5. Sum of all 14 module CLAUDE.md files < 2,000 lines
6. Full test suite passes (no code changes)
7. Representative smoke tests show Claude finding correct context via router

## Estimated Effort

- 10 tasks, small-to-medium each
- Critical path: Tasks 1 → 2 → 3-5 → 6 → 7-8 → 10
- Task 9 parallelizable with 7-8
- Estimated: 1-2 sessions to complete
