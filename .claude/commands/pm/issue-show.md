---
allowed-tools: Bash, Read, LS
---

# Issue Show

Display issue details. Use `--brief` for a compact summary or batch view.

## Usage
```
/pm:issue-show <issue_number>
/pm:issue-show <issue_number> --brief
/pm:issue-show --brief 123,124,125
```

## Instructions

Parse `$ARGUMENTS` for `--brief` flag and issue number(s). Support comma-separated list with `--brief`.

---

### Full View (default, single issue)

#### 1. Fetch Issue Data
- `gh issue view $ARGUMENTS --json number,title,state,labels,assignees,createdAt,updatedAt,body`
- Look for local task file: `.claude/epics/*/$ARGUMENTS.md` or search frontmatter `github:.*issues/$ARGUMENTS`

#### 2. Issue Overview
```
Issue #{number}: {title}
  Status: {open/closed}
  Labels: {labels}
  Assignee: {assignee}
  Created: {date}  Updated: {date}

Description:
{body preview, first 10 lines}
```

#### 3. Local File Mapping
If local task file found:
```
Local Files:
  Task: .claude/epics/{epic}/{file}
  Updates: .claude/epics/{epic}/updates/$ARGUMENTS/
```

#### 4. Dependencies & Relations
```
Related:
  Parent Epic: #{epic_issue}
  Dependencies: #{dep1}, #{dep2}
  Blocking: #{blocked1}
```

#### 5. Recent Activity
```
Recent Activity:
  {timestamp} - {author}: {comment_preview}
  Full thread: gh issue view #{number} --comments
```

#### 6. Acceptance Criteria
If task file has acceptance criteria, show progress with checkmarks.

#### 7. Quick Actions
```
Actions:
  Start: /pm:issue-start $ARGUMENTS
  Sync:  /pm:issue-sync $ARGUMENTS
  Close: /pm:issue-close $ARGUMENTS
  Web:   gh issue view #$ARGUMENTS --web
```

---

### Brief View (`--brief`, supports batch)

For each issue number in the comma-separated list:

```bash
gh issue view {num} --json number,title,state,labels,assignees,updatedAt
```

Output 6-line compact summary per issue:

```
#{number} {title}
  State: {OPEN/CLOSED}  Labels: {labels}
  Assignee: {assignee}  Updated: {date}
  Epic: {epic_name or "none"}
  Local: {task file path or "not found"}
  Next: /pm:issue-start {number}
```

When batch (multiple issues), output them sequentially separated by a blank line.

## Error Handling

- Invalid issue numbers: "Issue #{num} not found on GitHub"
- Network errors: show gh error and suggest `gh auth status`
- Missing local files: show GitHub data only, note "No local task file"
