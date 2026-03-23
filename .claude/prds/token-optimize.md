---
name: token-optimize
description: Tiered context architecture to reduce Claude Code session token usage by 80%
status: planned
created: 2026-03-22T18:00:00Z
revised: 2026-03-23T17:09:11Z
---

# PRD: Token Optimization — Tiered Context Architecture

## Executive Summary

Restructure the `.claude/` context system from "load everything always" to a three-tier
architecture (Tier 0: always / Tier 1: on-demand reference / Tier 2: deep module reference).
Reduces auto-loaded context from ~1,878 lines to ~300 lines (84% reduction). Compresses
module CLAUDE.md files by 50%. Audits and trims subagent/skill definitions. Targets 80%
reduction in per-session token usage for typical cross-module feature work and audit sessions.

## Problem Statement

### What problem are we solving?

Token consumption grows with project complexity. At v3.0.0 with 14 module CLAUDE.md files,
7 rules files, 6 auto-loaded context files, 19 agent definitions, and 28+ skills, every
conversation injects
~1,878 lines of context before Claude reads a single line of code. Cross-module feature work
and audit sessions hit usage limits prematurely.

### Why is this important now?

Version 3.0.0 shipped with unified agent system, model routing, eval harness, and learning
framework. The `.claude/` infrastructure grew organically across 42 epics and 695+ issues.
Context files contain significant duplication (system-patterns.md restates CLAUDE.md boundary
table, module-summaries.md restates module CLAUDE.md constraints, tech-context.md restates
CLAUDE.md tech stack). Further development will only add more context.

## User Stories

### Developer working on cross-module features
- **As a developer**, I want sessions to load only the context relevant to my current task
  so that token budget is spent on actual code work, not redundant reference material.
  - *Acceptance*: A cross-module feature session uses 70-80% fewer tokens on context loading
    than the current baseline.

### Developer running audits/reviews
- **As a developer**, I want audit sessions to load architectural context without product
  documentation, CLI command lists, or algorithm details that auditors don't need.
  - *Acceptance*: `/full-audit` sessions consume measurably fewer tokens.

### Developer doing simple bug fixes
- **As a developer**, I want a single-module bug fix to load only Tier 0 + that module's
  CLAUDE.md, not the entire project knowledge base.
  - *Acceptance*: Bug fix session loads <400 lines of context total.

## Architecture & Design

### Chosen Approach: Tiered Context Architecture (Approach B)

Three-tier model where CLAUDE.md becomes a slim router that tells Claude *where* to find
information instead of *providing* it all upfront. Critical bug-prevention rules stay in
Tier 0 (always loaded). Everything else moves to on-demand tiers.

### Current State (Baseline)

| Layer | Lines | Always Loaded? |
|-------|-------|----------------|
| Root CLAUDE.md | 311 | Yes |
| 6 `@`-referenced context files | 1,411 | Yes |
| 7 rules files | 156 | Yes |
| **Auto-loaded total** | **~1,878** | **Yes** |
| 14 module CLAUDE.md | 3,972 | On module touch |
| 14 guides + 19 agents | 4,054 | On demand |
| 28 prompts | ~5,200 | On demand |
| 155 TLDR cache files | 7,460 | On demand |

### Target State — Three Tiers

| Tier | Purpose | Budget | When Loaded |
|------|---------|--------|-------------|
| **Tier 0** | Identity + critical rules + router | <300 lines | Always (every conversation) |
| **Tier 1** | Architecture + product reference | <400 lines | Claude reads on-demand via router |
| **Tier 2** | Deep module reference | ~2,000 lines (compressed from 3,972) | Only when editing specific modules |

**Projected auto-loaded: ~300 lines (84% reduction from ~1,878)**

### Tier 0 Contents (<300 lines, always loaded)

| Section | Lines | Content |
|---------|-------|---------|
| Project identity | ~20 | What this is, tech stack summary |
| Module boundary table | ~20 | "Can Access / Cannot Access" table |
| Code patterns summary | ~30 | 1-liner per pattern (no examples) |
| Context router | ~30 | Task-type → which Tier 1/2 files to read |
| Current state | ~20 | Version, in-progress work, blockers |
| Verification commands | ~10 | Lint, test, typecheck commands |
| Common mistakes | ~20 | Terse "don't do X" list (no examples) |
| Git discipline | ~5 | Commit message format |

Plus 7 rules files (~156 lines) = **~300 lines total auto-loaded**.

### Tier 1 Files (on-demand reference)

| File | Lines | Consolidated From |
|------|-------|-------------------|
| `.claude/context/architecture.md` | ~200 | system-patterns.md + module-summaries.md |
| `.claude/context/product.md` | ~80 | product-context.md (compressed) |
| `.claude/context/algorithms.md` | ~60 | system-patterns-reference.md (compressed) |
| `.claude/context/progress.md` | ~30 | progress.md (current state only) |

### Context Router Pattern

The router in CLAUDE.md directs Claude to the right Tier 1/2 files:

```markdown
## Context Router — Read Before Working

| Task Type | Read These First |
|-----------|-----------------|
| Bug fix in single module | That module's CLAUDE.md |
| Cross-module feature | architecture.md + affected module CLAUDE.md files |
| Pricing/scoring/indicators | algorithms.md + module CLAUDE.md |
| PRD / brainstorming / design | product.md |
| New to project / onboarding | architecture.md + product.md |
| Audit / review | architecture.md |
```

### Module Changes

**Files rewritten:**
- `CLAUDE.md` — slim Tier 0 router (~250 lines, down from 311)

**Files created (consolidated from existing):**
- `.claude/context/architecture.md` — from system-patterns.md + module-summaries.md
- `.claude/context/product.md` — compressed product-context.md
- `.claude/context/algorithms.md` — compressed system-patterns-reference.md

**Files removed (absorbed into Tier 0/1):**
- `.claude/context/system-patterns.md` → architecture.md + CLAUDE.md
- `.claude/context/system-patterns-reference.md` → algorithms.md
- `.claude/context/product-context.md` → product.md
- `.claude/context/tech-context.md` → CLAUDE.md identity section
- `.claude/context/module-summaries.md` → architecture.md

**Files compressed (Tier 2, 50% target):**
- All 14 module CLAUDE.md files (3,972 → ~2,000 lines)
- Compression strategy: remove file listings (use Glob), remove import examples (read code),
  remove pattern examples already in Tier 0/1, keep constraints/gotchas/field mappings

**Files audited and trimmed:**
- 19 agent definition files — remove unused, compress descriptions
- Skills list — remove/consolidate unused (preserve PRD/epic workflow)
- 28 prompt files — flag stale/unused for removal

**Files unchanged:**
- 7 rules files (auto-loaded, critical)
- Hooks and settings.json
- TLDR cache (on-demand, already compressed)
- All PRD/epic workflow infrastructure
- 2 MCP servers (sequential-thinking, sqlite)

### Data Models

No Pydantic models or code changes. This is purely a `.claude/` configuration restructure.

### Core Logic

No application logic changes. All changes are to Claude Code configuration files that
control what context is injected into conversations.

## Requirements

### Functional Requirements

1. **FR-1**: Root CLAUDE.md auto-loads <300 lines (including `@`-references and rules)
2. **FR-2**: CLAUDE.md contains a context router mapping task types to Tier 1/2 files
3. **FR-3**: Tier 1 files consolidate all duplicated content into <400 lines total
4. **FR-4**: All 14 module CLAUDE.md files compressed by >=50% (3,972 → <2,000 lines)
5. **FR-5**: Critical rules (financial-precision, nan-defense, no-raw-dicts, yfinance-no-greeks)
   remain in Tier 0 (always loaded)
6. **FR-6**: Module boundary table remains in Tier 0
7. **FR-7**: Agent definitions audited — unused agents removed, remaining compressed
8. **FR-8**: Skills audited — unused skills removed, PRD/epic workflow preserved
9. **FR-9**: No application code changes — only `.claude/` and module CLAUDE.md files

### Non-Functional Requirements

1. **NFR-1**: 80% reduction in per-session token usage for cross-module feature work
2. **NFR-2**: Claude still finds and applies correct rules when editing any module
3. **NFR-3**: No maintenance tooling required — set and forget
4. **NFR-4**: Restructure preserves all institutional knowledge (nothing deleted, only
   consolidated or moved to appropriate tier)

## API / CLI Surface

N/A — no code changes, no new commands.

## Testing Strategy

### Before/After Measurement
- Baseline: measure token count for two representative sessions:
  1. "Fix a bug in scoring/contracts.py" (single-module)
  2. "Run /full-audit" (audit/review)
- After: same tasks, compare auto-loaded context lines and total session tokens
- Target: 70-80% reduction in auto-loaded context; 40-60% reduction in total session tokens

### Validation
- After restructure, run representative tasks across all task types:
  - Single-module bug fix
  - Cross-module feature (touching 3+ modules)
  - `/full-audit`
  - PRD/brainstorming session
  - Simple question ("how does scan pipeline work?")
- Verify Claude still reads the right context for each task type
- Run full test suite to confirm no code breakage (pure config change)
- Verify module boundary violations still caught (rules in Tier 0)

### Edge Cases
- New contributor onboarding: router directs to Tier 1 architecture.md + product.md
- Complex cross-module work: loads multiple Tier 1 files, still far less than current
- Rare algorithm work (pricing/BSM): router directs to algorithms.md (Tier 1)

## Success Criteria

1. Auto-loaded context drops from ~1,878 lines to <300 lines (measured by `wc -l`)
2. Cross-module feature session token usage drops by >=70% (measured by token count)
3. All existing test suite passes (no code changes means no regressions)
4. Claude correctly applies financial-precision, nan-defense, no-raw-dicts rules in post-restructure sessions
5. PRD/epic workflow operates identically

## Constraints & Assumptions

- **Constraint**: PRD/epic workflow (pm:* skills, task management) must remain unchanged
- **Constraint**: All 7 rules files stay as auto-loaded rules
- **Constraint**: No application code changes — `.claude/` and module CLAUDE.md only
- **Constraint**: Set-and-forget — no ongoing maintenance tooling
- **Assumption**: Claude's context router instructions are sufficient to direct it to the
  right Tier 1/2 files (validated during testing)
- **Assumption**: Module CLAUDE.md files can lose 50% of content without losing critical
  constraints (file listings, import examples, pattern duplications are safe to remove)

## Out of Scope

- Automated token usage monitoring/alerting tools
- Prompt cache optimization (provider-dependent, may shift)
- Dynamic context loading based on git diff analysis
- CI gates for context budget enforcement
- Application code refactoring

## Dependencies

- No external dependencies
- No package changes
- Requires reading all 14 module CLAUDE.md files to identify compression targets
- Requires understanding which agent definitions are actively used vs dormant

## Epic Decomposition (Suggested)

| # | Epic | Scope | Effort |
|---|------|-------|--------|
| 1 | Tier 0 Rewrite | Rewrite CLAUDE.md to ~250 lines with router pattern | Small |
| 2 | Tier 1 Consolidation | Create architecture.md, product.md, algorithms.md; remove originals | Medium |
| 3 | Module CLAUDE.md Compression | Compress all 14 module files by 50% | Medium |
| 4 | Subagent & Skill Audit | Audit, remove, compress agent/skill definitions | Small |
| 5 | Validation & Baseline | Before/after token measurement, smoke testing across task types | Small |
