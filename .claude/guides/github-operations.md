# GitHub Operations Guide

## Repository Protection

Before any write operation (`gh issue create/edit`, `gh pr create`), verify remote:

```bash
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
if [[ "$remote_url" == *"automazeio/ccpm"* ]]; then
  echo "ERROR: Operating on CCPM template repo. Update remote origin first."; exit 1
fi
```

## Patterns

- Don't pre-check auth: `gh {command} || echo "GitHub CLI failed. Run: gh auth login"`
- Specify repo on creates: derive from `git remote get-url origin`
- Use `--json` for structured output: `gh issue view {N} --json state,title,labels,body`
- One `gh` command per action. Don't retry automatically.
- Check remote origin before ANY write operation to GitHub

## Create Issue

```bash
remote_url=$(git remote get-url origin 2>/dev/null || echo "")
REPO=$(echo "$remote_url" | sed 's|.*github.com[:/]||' | sed 's|\.git$||')
[ -z "$REPO" ] && REPO="user/repo"
gh issue create --repo "$REPO" --title "{title}" --body-file {file} --label "{labels}"
```

## Error Handling

If any gh command fails: show clear error with exact solution, suggest `gh auth login`,
don't retry automatically.
