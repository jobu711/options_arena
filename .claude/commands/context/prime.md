---
allowed-tools: Bash, Read, LS
---

# Prime Context

Load incremental context not already provided by CLAUDE.md auto-loaded `@` references.

## Preflight

- Run: `ls .claude/context/ 2>/dev/null`
- If directory missing: tell user "No context found. Run /context:create first." and stop.

## Load Incremental Context

CLAUDE.md already auto-loads `tech-context.md`, `progress.md`, and `system-patterns.md`.
`project-brief.md` and `project-style-guide.md` duplicate CLAUDE.md content. Skip all five.

Read only files with unique content not covered by CLAUDE.md:
1. Read `.claude/context/product-context.md` — CLI/API reference, capabilities, constraints

## Active Epic Check

Detect the active epic from the current git branch:
1. Run: `git branch --show-current`
2. If branch matches `epic/*`, extract the epic name (e.g., `epic/data-completeness` → `data-completeness`)
3. If `.claude/epics/{epic-name}/execution-status.md` exists, read it
4. If `.claude/epics/{epic-name}/epic.md` exists, read the first 30 lines (title + summary)

## Git State

Run: `git log --oneline -5` for recent commits.
Run: `git diff --stat HEAD` for uncommitted changes summary.

## Output

Provide a compact summary:

```
Context Primed

Branch: {branch}
Epic: {epic name or "none"}
Epic status: {brief status from execution-status.md or "N/A"}
Uncommitted changes: {count of modified files or "clean"}

Ready for development.
```

No emoji. No file counts. No frontmatter validation.
