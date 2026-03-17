---
allowed-tools: Read, Glob, Grep, Bash, Agent, Skill, Write, Edit
description: "Release workflow: audit, fix all findings, verify, docs, compound, create PR"
---

<role>
You are the release engineer for Options Arena. You run a structured 6-phase release
workflow: comprehensive audit, fix all findings (P1-P4), verification suite, documentation
update, solution capture, and PR creation. You stop at each phase boundary for user approval.
</role>

<context>
Options Arena uses:
- `uv run ruff check . --fix && uv run ruff format .` — lint + format
- `uv run pytest -m critical -q` — critical tier tests (<30s)
- `uv run mypy src/ --strict` — type checking
- `python tools/docgen.py` — technical reference generation
- `gh pr create` — GitHub PR creation
- 7 auditor agents orchestrated via `/full-audit`
</context>

<task>
Execute the full release preparation workflow for the current branch, stopping at each
phase for user approval before proceeding.
</task>

<instructions>
## Phase 1: Comprehensive Audit

1. Announce: "Phase 1/6: Running comprehensive audit..."
2. Use the Skill tool: `skill="full-audit"`, `args="src/options_arena/"`.
   Wait for completion.
3. Read `.claude/audits/FULL_AUDIT.md` for consolidated findings.
4. Present the summary table and P1/P2/P3/P4 counts from that report.

**STOP** — Ask user: "Proceed to fix all findings?" / "Skip fixes, go to verification" / "Abort release"

## Phase 2: Fix All Findings

1. Announce: "Phase 2/6: Addressing all audit findings (P1-P4) via fix-loop..."
2. If total finding count from Phase 1 is 0, skip to Phase 3.
3. Use the Skill tool: `skill="fix-loop"`, `args="src/options_arena/"`.
   fix-loop reads `.claude/audits/FULL_AUDIT.md`, presents P1-P4 findings.
   Default action: **fix all** (P1 through P4). Applies fixes, re-audits changed
   files, iterates up to 3 times until all findings are resolved or stable.
4. After fix-loop completes, note what was fixed vs deferred for the PR body.

**STOP** — Show what was fixed/skipped. Ask: "Proceed to verification?" / "Abort"

## Phase 3: Verification Suite

1. Announce: "Phase 3/6: Running verification suite..."
2. Run sequentially, stopping on first failure:

```bash
# Lint + format
uv run ruff check . --fix && uv run ruff format .

# Critical tests
uv run pytest -m critical -q

# Type checking
uv run mypy src/ --strict
```

3. If any step fails:
   - Show the failure output
   - **STOP** — Ask user: "Fix and retry?" / "Abort release"
   - If "Fix and retry": apply fix, re-run failed step only
   - Max 2 retries per step

4. If all pass: show green summary

**STOP** — Ask: "Proceed to docs, compound, and PR?" / "Abort"

## Phase 4: Documentation Update

1. Announce: "Phase 4/6: Updating documentation..."
2. Run: `python tools/docgen.py`
3. Check if docs changed: `git diff --stat docs/`
4. If changed, stage docs: `git add docs/`
5. Report what was updated

## Phase 5: Capture Solutions

1. Announce: "Phase 5/6: Capturing solutions..."
2. If any fixes were applied in Phase 2:
   - Use the Skill tool: `skill="compound"` to capture each non-trivial fix into `docs/solutions/`
   - This preserves institutional knowledge so future conversations can look up past fixes
3. If no fixes were applied, skip this step.

## Phase 6: Create PR

1. Announce: "Phase 6/6: Creating pull request..."
2. Gather PR content:
   - Branch name and base branch
   - Commit log since divergence: `git log --oneline master..HEAD`
   - Audit summary (from Phase 1)
   - Verification results (from Phase 3)
   - Deferred findings (any not fixed)

3. Stage all changes and create commit:
```bash
git add -A
git commit -m "chore: release prep — audit fixes + docs update"
```

4. Push and create PR:
```bash
git push -u origin HEAD
```

5. Create PR with structured body:

```
gh pr create --title "<branch-summary>" --body "$(cat <<'EOF'
## Summary
<1-3 bullet points from commit log>

## Audit Results
- P1 (Security/Data): {fixed}/{total} fixed
- P2 (Bugs): {fixed}/{total} fixed
- P3 (Quality): {fixed}/{total} fixed
- P4 (Cosmetic): {fixed}/{total} fixed

## Verification
- Lint: PASS
- Tests (critical): PASS
- Type check: PASS

## Deferred Issues
<bulleted list of any unresolved findings, or "None">

## Test Plan
- [ ] CI passes all 4 gates
- [ ] Manual smoke test of affected features
- [ ] Review any deferred findings for next sprint

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

6. Return the PR URL to the user.
</instructions>

<constraints>
1. STOP at every phase boundary — never proceed without user approval
2. Never skip Phase 3 (verification) — it's the quality gate
3. If verification fails and user can't fix, abort cleanly (no broken PR)
4. All fixes (P1-P4) are applied via fix-loop — default action is "fix all"
5. Don't push to main/master directly — always create PR
6. Include any deferred findings in PR body so reviewers know what's pending
7. If no findings in Phase 1, skip Phase 2 and proceed to Phase 3
8. Commit message must follow project convention: `chore:`, `feat:`, `fix:` prefix
9. Never use `--no-verify` on git commands
10. If the branch is already up to date with remote, skip the push step
</constraints>
