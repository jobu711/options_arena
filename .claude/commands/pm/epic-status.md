---
allowed-tools: Bash, Read, Glob, LS
---

# Epic Status

Show all epics (no argument) or detailed status for one epic (with argument).

## Usage
```
/pm:epic-status
/pm:epic-status <epic_name>
```

## Instructions

### Mode 1: No argument — Epic List

Scan `.claude/epics/*/epic.md` (excluding `archived/`). For each, extract frontmatter:
`name`, `status`, `progress`, `github`, `created`, `updated`.

Count tasks per epic: `ls .claude/epics/{name}/[0-9]*.md | wc -l`

Output as a table:

```
Epics ({count}):

  Name              Status       Progress   Tasks    GitHub   Updated
  ─────────────────────────────────────────────────────────────────────
  {name}            {status}     {pct}%     {n}/{t}  #{num}   {date}
  {name}            {status}     {pct}%     {n}/{t}  #{num}   {date}
  ...

Archived: {count} in .claude/epics/archived/

Actions:
  Detail:  /pm:epic-status <name>
  New:     /pm:prd-new <feature>
  Start:   /pm:epic-start <name>
```

### Mode 2: With argument — Epic Detail

Read `.claude/epics/$ARGUMENTS/epic.md` fully. Extract all frontmatter + body.

Read all task files in `.claude/epics/$ARGUMENTS/`:
- Parse each task's `name`, `status`, `github`, `depends_on`, `parallel`
- Group by status: closed, in-progress, open, blocked

Check for related files:
- `execution-status.md` — active agents
- `verification-report.md` — verification results
- `checkpoint.json` — last checkpoint
- `research.md` — research notes

```bash
# Get recent branch commits if branch exists
git log epic/$ARGUMENTS --oneline -5 2>/dev/null || echo "No branch found"
```

Output:

```
Epic: $ARGUMENTS
  Status: {status}  Progress: {progress}%  GitHub: #{issue}
  Created: {date}  Updated: {date}

Tasks ({closed}/{total}):

  Closed:
    #{num} {name}
    ...

  In Progress:
    #{num} {name}
    ...

  Open:
    #{num} {name} {if depends_on: "(blocked by #{dep})"}
    ...

{If verification-report.md exists}:
Verification: {passed}/{total} PASS, {warned} WARN, {failed} FAIL

{If execution-status.md exists}:
Active Agents: {count}

Recent Commits:
  {hash} {message}
  ...

Actions:
  Start:  /pm:epic-start $ARGUMENTS
  Verify: /pm:epic-verify $ARGUMENTS
  Merge:  /pm:epic-merge $ARGUMENTS
```

### Error Handling

- Epic not found: "Epic '$ARGUMENTS' not found. Run /pm:epic-status (no args) to list all epics."
- No epics exist: "No epics found. Start with: /pm:prd-new <feature>"
