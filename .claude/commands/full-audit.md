---
allowed-tools: Read, Glob, Grep, Bash, Agent, Write
description: "Spawn all 6 auditors in parallel, consolidate into prioritized report"
---

<role>
You are the audit orchestrator for Options Arena. You launch all 6 specialized auditor
agents in parallel, collect their structured findings, deduplicate, assign unified
priority levels, and produce a single consolidated report.
</role>

<context>
Options Arena has 6 auditor agents with non-overlapping scopes:
- `security-auditor` — OWASP, secrets, injection, input sanitization
- `bug-auditor` — async correctness, resource lifecycle, concurrency, error handling
- `code-reviewer` — typed models, NaN defense, type annotations, Pydantic conventions
- `architect-reviewer` — module boundaries, dependency direction, pattern consistency
- `db-auditor` — SQL injection, queries, migrations, serialization, data integrity
- `dep-auditor` — CVEs, outdated packages, unused deps, license compliance

Each agent emits a YAML preamble with finding counts and writes to `.claude/audits/`.
</context>

<task>
Run a comprehensive audit of the specified scope (or `src/` by default), then
consolidate all findings into a single prioritized report.

Arguments: `$ARGUMENTS` may contain:
- `<path>` — audit a specific path
- `--commit <hash>` — audit only files changed in a specific commit
- `--epic <name>` — audit only files changed on the `epic/<name>` branch vs master
</task>

<instructions>
## Phase 1: Setup

1. Parse `$ARGUMENTS`:
   - `--commit <hash>` → run `git diff-tree --no-commit-id --name-only -r <hash>` to get
     changed files, use those as the audit scope
   - `--epic <name>` → run `git diff --name-only master...epic/<name>` to get all files
     changed on the epic branch, use those as the audit scope
   - `<path>` → use that path as audit scope
   - Empty → default to `src/options_arena/`
2. Create `.claude/audits/` directory if it doesn't exist: `mkdir -p .claude/audits`
3. Note the current UTC timestamp for report header.

## Phase 2: Parallel Audit — Launch ALL 6 agents in ONE message

Launch all 6 agents in a SINGLE message (parallel fan-out). Each agent receives the
same scope. Each agent writes its report to `.claude/audits/AUDIT_<NAME>.md`.

**Agent launch prompts** (adapt scope from Phase 1):

### security-auditor
```
Audit the following scope for security issues: {scope}
Write your full report (including YAML preamble) to .claude/audits/AUDIT_SECURITY.md
Follow all instructions in your agent prompt. Be thorough but stay in scope.
```

### bug-auditor
```
Audit the following scope for runtime bugs and async issues: {scope}
Write your full report (including YAML preamble) to .claude/audits/AUDIT_BUG.md
Follow all instructions in your agent prompt. Be thorough but stay in scope.
```

### code-reviewer
```
Review the following scope for code quality and conventions: {scope}
Write your full report (including YAML preamble) to .claude/audits/AUDIT_CODE.md
Follow all instructions in your agent prompt. Be thorough but stay in scope.
```

### architect-reviewer
```
Review the following scope for architectural integrity: {scope}
Write your full report (including YAML preamble) to .claude/audits/AUDIT_ARCHITECT.md
Follow all instructions in your agent prompt. Be thorough but stay in scope.
```

### db-auditor
```
Audit the database layer for query safety, migrations, and data integrity: {scope}
Write your full report (including YAML preamble) to .claude/audits/AUDIT_DB.md
Follow all instructions in your agent prompt. Be thorough but stay in scope.
```

### dep-auditor
```
Audit dependency health, CVEs, and license compliance.
Write your full report (including YAML preamble) to .claude/audits/AUDIT_DEP.md
Follow all instructions in your agent prompt. Be thorough but stay in scope.
```

## Phase 3: Consolidate

After all 6 agents complete:

1. Read all 6 report files from `.claude/audits/AUDIT_*.md`
2. Parse the YAML preamble from each to get finding counts and status
3. Collect all findings across all reports
4. **Deduplicate**: If two agents flag the same `file:line`, keep the finding from the
   agent whose scope owns that check (per scope boundary definitions)
5. **Assign unified priority**:

### Priority Mapping
- **P1 (Security/Data)**: security-auditor Critical+High, db-auditor Critical, bug-auditor Critical
- **P2 (Bugs/Correctness)**: bug-auditor High, code-reviewer Critical, db-auditor High
- **P3 (Quality/Architecture)**: architect-reviewer all, code-reviewer High+Medium, dep-auditor High
- **P4 (Cosmetic)**: remaining Low/Informational findings from any agent

6. Write the consolidated report to `.claude/audits/FULL_AUDIT.md`

### Consolidated Report Format

```markdown
# Full Audit Report

**Scope**: {scope}
**Timestamp**: {UTC timestamp}
**Agents**: 6/6 completed (or N/6 if partial)

## Summary

| Agent | Status | Critical | High | Medium | Low |
|-------|--------|----------|------|--------|-----|
| security-auditor | ... | ... | ... | ... | ... |
| bug-auditor | ... | ... | ... | ... | ... |
| code-reviewer | ... | ... | ... | ... | ... |
| architect-reviewer | ... | ... | ... | ... | ... |
| db-auditor | ... | ... | ... | ... | ... |
| dep-auditor | ... | ... | ... | ... | ... |
| **Total** | — | **N** | **N** | **N** | **N** |

## P1 — Security & Data Integrity (fix immediately)
- [agent] [file:line] Description → Fix

## P2 — Bugs & Correctness (fix before merge)
- [agent] [file:line] Description → Fix

## P3 — Quality & Architecture (plan for next sprint)
- [agent] [file:line] Description → Fix

## P4 — Cosmetic & Informational
- [agent] [file:line] Description → Fix

## Deferred / Out of Scope
- [Items that couldn't be assessed, with reason]
```

## Phase 4: Report to User

Display the summary table and P1 count to the user. If P1 > 0, recommend running
`/fix-loop` to address critical issues. Provide the path to the full report.
</instructions>

<constraints>
1. ALL 6 agents MUST be launched in a SINGLE message — never sequentially
2. Never modify application source code — this is an audit-only command
3. If an agent errors, note it in the report but don't block other agents
4. Deduplicate before reporting — same file:line should not appear twice
5. The consolidated report must be machine-parseable (consistent markdown structure)
6. If scope is very large (all of src/), warn user it may take several minutes
</constraints>
