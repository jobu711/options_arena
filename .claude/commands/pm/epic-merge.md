---
allowed-tools: Bash, Read, Write, LS
---

# Epic Merge

Merge completed epic branch/worktree back to main, or close an epic without git ops.

## Usage
```
/pm:epic-merge <epic_name>
/pm:epic-merge <epic_name> --no-branch
```

- **Default**: full git merge + cleanup + archive + GitHub close
- **`--no-branch`**: skip all git operations, only update progress/status, close GitHub issues, and archive. Use when the epic was worked on directly in main or the branch was already merged.

## Quick Check

1. **Parse flags:** Check if `$ARGUMENTS` contains `--no-branch`. Strip to get `<epic_name>`.
2. **Verify epic exists:** `test -f .claude/epics/$ARGUMENTS/epic.md`
3. **If default mode:** Check worktree/branch exists:
   ```bash
   git worktree list | grep "epic-$ARGUMENTS" || git branch -a | grep "epic/$ARGUMENTS"
   ```
4. **Check for active agents:** Read `.claude/epics/$ARGUMENTS/execution-status.md` if it exists.

## Instructions

### 0. Check Verification Report (soft gate)

- If `.claude/epics/$ARGUMENTS/verification-report.md` does NOT exist:
  - Display: "No verification report found. Consider running /pm:epic-verify $ARGUMENTS first."
  - Ask user: "Continue without verification? (yes/no)"
- If it DOES exist:
  - Read frontmatter for `passed`, `warned`, `failed`, `coverage`
  - Display: "Verification: {passed}/{total} PASS, {warned} WARN, {failed} FAIL ({coverage}% coverage)"
  - If `failed > 0`: warn user before proceeding

### 1. Refresh Epic Progress (absorbs epic-refresh)

Scan all task files in `.claude/epics/$ARGUMENTS/`:
- Count total tasks, closed tasks, open tasks
- Calculate progress: `(closed / total) * 100`, round to integer
- Determine status: 0% = backlog, 0-100% = in-progress, 100% = completed

Update epic.md frontmatter:
```yaml
status: {calculated_status}
progress: {calculated_progress}%
updated: {current ISO datetime}
```

If epic has GitHub issue, sync task checkboxes:
```bash
epic_issue={from frontmatter github: field}
# Update checkbox state for each task in the epic body
gh issue edit $epic_issue --body-file /tmp/epic-body.md
```

### 2. Pre-Merge Validation (skip if --no-branch)

```bash
# Find epic location (worktree or branch)
if git worktree list | grep -q "epic-$ARGUMENTS"; then
  cd ../epic-$ARGUMENTS
else
  git checkout epic/$ARGUMENTS
fi

# Check for uncommitted changes
if [[ $(git status --porcelain) ]]; then
  echo "Uncommitted changes detected. Commit or stash before merging."
  exit 1
fi

git fetch origin
git status -sb
```

### 3. Run Tests (skip if --no-branch)

```bash
uv run pytest -m "not exhaustive" -n auto -q
```

### 4. Attempt Merge (skip if --no-branch)

```bash
cd {main-repo-path}
git checkout main && git pull origin main
git merge epic/$ARGUMENTS --no-ff -m "Merge epic: $ARGUMENTS"
```

If merge conflicts: show conflicted files and options (resolve, abort).

### 5. Post-Merge Cleanup (skip if --no-branch)

```bash
git push origin main

# Remove worktree if it exists
if git worktree list | grep -q "epic-$ARGUMENTS"; then
  git worktree remove ../epic-$ARGUMENTS
fi

# Delete branch
git branch -d epic/$ARGUMENTS
git push origin --delete epic/$ARGUMENTS 2>/dev/null || true
```

### 6. Update Epic Status (absorbs epic-close)

Get current datetime. Update `.claude/epics/$ARGUMENTS/epic.md`:
```yaml
status: completed
progress: 100%
updated: {current ISO datetime}
completed: {current ISO datetime}
```

If epic references a PRD, update its status to "complete".

### 7. Close GitHub Issues

```bash
# Close epic issue
gh issue close $epic_issue -c "Epic completed and merged to main"

# Close all task issues
for task_file in .claude/epics/$ARGUMENTS/[0-9]*.md; do
  issue_num={extract from github: field}
  gh issue close $issue_num -c "Completed in epic merge"
done
```

### 8. Archive

```bash
mkdir -p .claude/epics/archived/
mv .claude/epics/$ARGUMENTS .claude/epics/archived/
```

### 9. Output

```
Epic Merged: $ARGUMENTS

{If default mode}:
  Branch: epic/$ARGUMENTS -> main
  Commits merged: {count}
  Files changed: {count}

Progress: {progress}% ({closed}/{total} tasks)
Issues closed: {count}
Worktree/branch: cleaned up
Epic: archived to .claude/epics/archived/$ARGUMENTS

Next: /pm:prd-new {feature} or /pm:next
```

## Important Notes

- `--no-branch` mode runs steps 0, 1, 6, 7, 8 only (skips git merge/cleanup)
- Progress refresh (step 1) runs in both modes — this replaces the old `epic-refresh` command
- Epic close logic (step 6) runs in both modes — this replaces the old `epic-close` command
- Use `--no-ff` to preserve epic history in merge commits
- Archive epic data instead of deleting
