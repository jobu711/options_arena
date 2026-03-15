---
allowed-tools: Bash, Read, Glob, LS
---

# Project Status

Show project-wide status: epics, active issues, recent git activity.

## Usage
```
/pm:status
/pm:status --standup
```

## Instructions

### 1. Gather Data

**Epics**: Read all `.claude/epics/*/epic.md` frontmatters. Extract `name`, `status`, `progress`, `github`.

**Active GitHub issues** (open, assigned or labeled):
```bash
gh issue list --state open --limit 20 --json number,title,state,labels,assignees,updatedAt
```

**Recent commits**:
```bash
git log --oneline -10
```

**Current branch**:
```bash
git branch --show-current
```

**Blocked items**: Check task files for `status: blocked` or `depends_on` referencing open issues.

### 2. Default Output (full overview)

```
Project Status

Branch: {current_branch}

Epics:
  {status_icon} {name} — {progress}% ({closed}/{total} tasks) [#{github_issue}]
  {status_icon} {name} — {progress}% ({closed}/{total} tasks) [#{github_issue}]
  ...

{For each in-progress epic}:
  Active in {epic_name}:
    - #{issue}: {title} ({state})
    ...

Open Issues ({count}):
  #{num} {title} [{labels}] — updated {relative_time}
  ...

Recent Commits:
  {hash} {message}
  ...

{If blocked items found}:
Blocked:
  #{issue}: {title} — waiting on #{dep1}, #{dep2}

Next: /pm:next for task recommendations
```

Status icons: completed, in-progress, backlog.

### 3. Standup Output (`--standup`)

If `$ARGUMENTS` contains `--standup`, use this compact format instead:

```
Standup — {today's date}

Yesterday:
  {List closed issues/commits from last 24h}
  - Closed #{num}: {title}
  - Committed: {hash} {message}

Today:
  {List open issues assigned or in-progress}
  - #{num}: {title} ({epic_name})

Blocked:
  {List items with unmet dependencies, or "None"}
```

Use `git log --since="24 hours ago" --oneline` for yesterday's work.
Use task files with `status: open` or `status: in-progress` for today's plan.

### 4. Error Handling

- No epics found: "No epics found in .claude/epics/. Start with: /pm:prd-new"
- gh CLI not authenticated: show data from local files only, note "GitHub data unavailable"
