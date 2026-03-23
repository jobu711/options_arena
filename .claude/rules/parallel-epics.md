# Parallel Epic Safety

Multiple Claude Code sessions share the same working directory. Switching from
one `epic/*` branch to another changes the branch for ALL sessions, causing
commits to land on the wrong epic.

## Rules

1. **NEVER** run `git checkout epic/Y` or `git switch epic/Y` when already on `epic/X`
2. **ALWAYS** check current branch before any checkout: `git branch --show-current`
3. Use `--worktree` mode for parallel epics — each gets an isolated directory

## Allowed Transitions

| Current Branch | Target | Allowed? |
|----------------|--------|----------|
| `epic/foo` | `epic/bar` | NO — use worktree |
| `epic/foo` | `epic/foo` | Yes (no-op) |
| `epic/foo` | `master` | Yes |
| `master` | `epic/foo` | Yes |
| `epic/foo` | `-b epic/bar` | Yes (creation) |
| `epic/foo` | `-- path/file` | Yes (file checkout) |

## When You Need Another Epic

```bash
# WRONG — contaminates shared directory
git checkout epic/other-epic

# RIGHT — isolated worktree
/pm:epic-start other-epic --worktree
# Or manually:
git worktree add ../epic-other-epic -b epic/other-epic
```

A `branch-guard.py` hook enforces this — epic-to-epic switches are denied automatically.
