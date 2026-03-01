---
allowed-tools: Bash, Read, Write, LS
---

# Epic Checkpoint

Save current epic progress for session resumption.

## Usage
```
/pm:epic-checkpoint <epic_name> [notes]
```

Examples:
```
/pm:epic-checkpoint openbb-integration
/pm:epic-checkpoint openbb-integration "Left off at migration 009"
```

## Required Rules

**IMPORTANT:** Before executing this command, read and follow:
- `.claude/rules/datetime.md` - For getting real current date/time

## Preflight Checklist

Do not bother the user with preflight checks progress. Just do them and move on.

1. **Verify epic name was provided:**
   - If not, tell user: "❌ Epic name required. Usage: /pm:epic-checkpoint <epic_name>"

2. **Verify epic directory exists:**
   - Check if `.claude/epics/$ARGUMENTS/` exists (use the first word of $ARGUMENTS as epic name)
   - If not found, tell user: "❌ Epic not found: {name}. Check available epics with: ls .claude/epics/"

## Instructions

### 1. Parse Arguments

Split $ARGUMENTS into:
- `epic_name`: First word (the epic name)
- `notes`: Everything after the first word (optional user notes)

### 2. Auto-Detect Phase

Scan the epic directory to determine the current phase automatically:

```
Directory: .claude/epics/{epic_name}/

Phase detection (check in reverse order — last match wins):
1. Only PRD exists (.claude/prds/{epic_name}.md) → "prd-created"
2. Has research.md → "research"
3. Has epic.md → "planning"
4. Has numbered task files (*.md matching [0-9]*.md) → "decomposition"
5. Has github-mapping.md → "synced"
6. Has execution-status.md → "executing"
7. All task statuses are "completed"/"closed" → "complete"
```

### 3. Gather Task Statuses

For each numbered task file in the epic directory:
- Read frontmatter to extract `name` and `status`
- Categorize into: `tasks_completed`, `tasks_in_progress`, `tasks_pending`
- Identify any with `status: blocked` as blockers

### 4. Build Completed Phases List

Based on detected phase, build the list of completed phases:
- `prd-created` → `["prd-created"]`
- `research` → `["prd-created", "research"]`
- `planning` → `["prd-created", "research", "planning"]` (include research only if research.md exists)
- `decomposition` → `["prd-created", ..., "planning", "decomposition"]`
- `synced` → `["prd-created", ..., "decomposition", "synced"]`
- `executing` → `["prd-created", ..., "synced", "executing"]`
- `complete` → all phases

### 5. Write Checkpoint

Get REAL current datetime by running the appropriate command for the platform.

Write `.claude/epics/{epic_name}/checkpoint.json`:
```json
{
  "epic": "{epic_name}",
  "phase": "{detected_phase}",
  "last_command": "/pm:epic-checkpoint {epic_name}",
  "last_updated": "{current ISO datetime}",
  "completed_phases": ["{phase1}", "{phase2}"],
  "current_task": null,
  "tasks_completed": ["{task_name_1}"],
  "tasks_in_progress": ["{task_name_2}"],
  "blockers": [],
  "notes": "{user-provided notes or empty string}"
}
```

### 6. Output

```
✅ Checkpoint saved: .claude/epics/{epic_name}/checkpoint.json
  Phase: {phase}
  Tasks: {completed}/{total} complete, {in_progress} in progress
  Notes: {notes or "none"}

Resume later with: /pm:epic-resume {epic_name}
```

## Error Recovery

- If phase detection fails, default to "unknown" and warn user
- If task file parsing fails, skip that task and note it in output
- Checkpoint write failure is reported but does not fail the command
