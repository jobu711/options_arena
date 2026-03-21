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
`name`, `status`, `progress`, `github`, `created`, `updated`, `type`, `child_epics`, `parent_epic`.

Count tasks per epic: `ls .claude/epics/{name}/[0-9]*.md | wc -l`

**Parent epic handling**: If `type: parent` in frontmatter, show it as a group header
with its children indented below. Don't count tasks on the parent — aggregate from children.

Output as a table:

```
Epics ({count}):

  Name                    Status       Progress   Tasks    GitHub   Updated
  ──────────────────────────────────────────────────────────────────────────
  {name} (parent)         {status}     {pct}%     —        #{num}   {date}
    └ {child-1}           {status}     {pct}%     {n}/{t}  #{num}   {date}
    └ {child-2}           {status}     {pct}%     {n}/{t}  #{num}   {date}
  {standalone-epic}       {status}     {pct}%     {n}/{t}  #{num}   {date}
  ...

Archived: {count} in .claude/epics/archived/

Actions:
  Detail:  /pm:epic-status <name>
  New:     /pm:prd-new <feature>
  Start:   /pm:epic-start <name>
```

### Mode 2: With argument — Epic Detail

Read `.claude/epics/$ARGUMENTS/epic.md` fully. Extract all frontmatter + body.

**If `type: parent`** — show parent rollup view:

- Read each child epic's `epic.md` frontmatter for status/progress
- For each child, count its tasks and their statuses
- Compute aggregate progress: `sum(child_closed_tasks) / sum(child_total_tasks) * 100`

```
Epic: $ARGUMENTS (Parent)
  Status: {status}  Progress: {aggregate}%  GitHub: #{issue}
  PRD: {prd_path}

Child Epics ({completed}/{total}):

  {child-1}     {status}   {pct}%   {closed}/{total} tasks   #{github}
  {child-2}     {status}   {pct}%   {closed}/{total} tasks   #{github}
  ...

Dependency Chain:
  {child-1} --> {child-2} --> {child-3}

Next actionable child: {first child with status != completed}

Actions:
  Detail child: /pm:epic-status {child-name}
  Decompose:    /pm:epic-decompose {next-child}
  Start:        /pm:epic-start {next-child}
```

**If `parent_epic` in frontmatter** — show child epic detail (standard view + parent context):

Read all task files in `.claude/epics/$ARGUMENTS/`:
- Parse each task's `name`, `status`, `github`, `depends_on`, `parallel`
- Group by status: closed, in-progress, open, blocked

Check for related files:
- `execution-status.md` — active agents
- `verification-report.md` — verification results
- `checkpoint.json` — last checkpoint
- `research.md` — research notes (also check parent's research.md)

```bash
# Get recent branch commits if branch exists
git log epic/$ARGUMENTS --oneline -5 2>/dev/null || echo "No branch found"
```

```
Epic: $ARGUMENTS (child of {parent_epic})
  Status: {status}  Progress: {progress}%  GitHub: #{issue}
  Created: {date}  Updated: {date}
  Depends on: {depends_on list or "none"}

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
  Parent:  /pm:epic-status {parent_epic}
  Start:   /pm:epic-start $ARGUMENTS
  Verify:  /pm:epic-verify $ARGUMENTS
  Merge:   /pm:epic-merge $ARGUMENTS
```

**If standalone epic** (no `type: parent`, no `parent_epic`) — standard view:

Same as the child view above but without parent references.

### Error Handling

- Epic not found: "Epic '$ARGUMENTS' not found. Run /pm:epic-status (no args) to list all epics."
- No epics exist: "No epics found. Start with: /pm:prd-new <feature>"
