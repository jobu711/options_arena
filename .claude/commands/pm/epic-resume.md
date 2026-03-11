---
allowed-tools: Read, LS
---

# Epic Resume

Restore context from a previous session checkpoint.

## Usage
```
/pm:epic-resume <epic_name>
```

## Preflight Checklist

Do not bother the user with preflight checks progress. Just do them and move on.

1. **Verify epic name was provided:**
   - If not, tell user: "❌ Epic name required. Usage: /pm:epic-resume <epic_name>"

2. **Verify epic directory exists:**
   - Check if `.claude/epics/$ARGUMENTS/` exists
   - If not found, tell user: "❌ Epic not found: $ARGUMENTS. Check available epics with: ls .claude/epics/"

## Instructions

This command is **read-only** — it never modifies files.

### 1. Load Checkpoint

Check for `.claude/epics/$ARGUMENTS/checkpoint.json`:
- If exists: parse it and use the stored state
- If missing: reconstruct state from files (same detection logic as `/pm:epic-checkpoint`)

### 2. Reconstruct State (if no checkpoint)

If checkpoint.json is missing, determine phase by scanning the directory:
- Only PRD exists → `prd-created`
- Has `research.md` → `research`
- Has `epic.md` → `planning`
- Has numbered task files → `decomposition`
- Has `github-mapping.md` → `synced`
- Has `execution-status.md` → `executing`
- All tasks closed → `complete`

### 3. Load Key Context Files

Read and summarize the following files (if they exist):
- `.claude/epics/$ARGUMENTS/epic.md` — overview and architecture decisions
- `.claude/epics/$ARGUMENTS/research.md` — codebase research findings
- `.claude/epics/$ARGUMENTS/execution-status.md` — active agents and progress

For each file, provide a 2-3 line summary of key content.

### 4. Display Status

```
Epic: $ARGUMENTS
Phase: {phase}
Last updated: {checkpoint.last_updated or "unknown"}

Tasks: {completed}/{total} complete
  In progress: {list or "none"}
  Blocked: {list or "none"}

Notes: {checkpoint.notes or "none"}

Key files loaded:
  - epic.md: {summary}
  - research.md: {summary or "not found"}
  - execution-status.md: {summary or "not found"}
```

### 5. Suggest Next Command

Based on the current phase, suggest the appropriate next command:

| Phase | Suggestion |
|-------|-----------|
| `prd-created` | "Next: /pm:prd-research $ARGUMENTS" |
| `research` | "Next: /pm:prd-parse $ARGUMENTS" |
| `planning` | "Next: /pm:epic-decompose $ARGUMENTS" |
| `decomposition` | "Next: /pm:epic-sync $ARGUMENTS" |
| `synced` | "Next: /pm:epic-start $ARGUMENTS" |
| `executing` | "Next: /pm:epic-status $ARGUMENTS — or start a task with /pm:issue-start {task}" |
| `complete` | "Next: /pm:epic-close $ARGUMENTS" |

If there are blockers, mention them before the suggestion.

## Error Recovery

- If checkpoint.json is malformed, fall back to directory-based reconstruction
- If epic directory is empty, suggest starting with `/pm:prd-parse $ARGUMENTS`
- This command never fails fatally — always show whatever state can be determined
