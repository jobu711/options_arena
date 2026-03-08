---
allowed-tools: Bash, Read, Glob, Grep
---

# Next: Development Target Brainstorm

Analyze recent project momentum and suggest the highest-alpha development targets.

## Usage
```
/pm:next
```

## Instructions

You are a strategic development advisor. Analyze the project's recent history, current state, and backlog to recommend the top 3-5 highest-value things to build next.

Do not bother the user with progress updates for each step. Gather context silently, then present the final ranked output.

### Step 1 — Git as Source of Truth

Git merge history is the ground truth for what's done. Run these bash commands:

```bash
# What epics/PRs actually shipped (ground truth for "done")
git log master --oneline --merges -15
```
```bash
# Recent commit themes on master
git log master --oneline -20 --no-merges
```
```bash
# What's actively in flight (unmerged branches)
git branch -a --no-merged master
```
```bash
# Recent velocity/themes (last 14 days)
git log master --oneline --since="14 days ago" --no-merges
```

For each unmerged branch found above, run:
```bash
git log master..<branch> --oneline
```

Build a "shipped" list from merge commits (epic names, PR titles) and an "in-flight" list from unmerged branches.

### Step 2 — Backlog Discovery (Cross-Referenced Against Git)

Discover what could be built next, but **cross-reference everything against the merge log from Step 1**.

1. Scan `.claude/prds/` — read frontmatter (first 10-15 lines) of each file. BUT: if an epic with the same name appears in the Step 1 merge log or in `.claude/epics/archived/`, that PRD is **done** regardless of its `status` field.
2. Read `.claude/context/progress.md` — use ONLY the "Future Work" section for idea discovery. Do NOT trust "Current State" or "In Progress" sections (derive those from git).
3. For active (unmerged) epics from Step 1, check actual commit content on the branch rather than task file statuses.
4. Check `web/src/views/` — verify whether suggested frontend features already exist as implemented pages.
5. Grep/glob the codebase briefly if needed to confirm whether a suggested capability already exists.

### Step 3 — Analyze & Rank (with Staleness Guard)

**Staleness guard — apply before ranking each target:**
- Check if the target's epic name appears in `git log --merges` from Step 1
- Check if related code/pages already exist (grep/glob the codebase)
- If already done, exclude it and note it in the "Filtered out" section of the output

Cross-reference git history against project state. Score potential targets on these criteria:

- **Momentum** (high weight): Does this build naturally on what was just completed? Is the team already in the right mental context?
- **Unblocking potential** (high weight): Does this open the door for multiple downstream features or remove a bottleneck?
- **Impact/Effort ratio** (medium weight): High user value relative to engineering cost? Prefer S/M efforts that deliver outsized value.
- **Freshness** (medium weight): Does recent work reveal gaps, bugs, or opportunities that weren't visible before?
- **Risk reduction** (lower weight): Does this fix correctness or reliability issues that should be addressed before adding new features?
- **User-facing value** (lower weight): Does this improve what end-users directly see and interact with?

Also consider:
- Avoid suggesting work that duplicates or conflicts with in-progress efforts
- Prefer targets with existing PRDs (less planning overhead)
- Flag if a target needs a PRD first vs. can start immediately

### Step 4 — Present Results

Output a ranked list of 3-5 development targets in this format:

```
## Development Targets (ranked by estimated alpha)

### 1. [One-line description]
**Why now:** [What recent work makes this timely — reference specific commits/PRs/epics]
**Effort:** [S / M / L / XL]
**Unblocks:** [What downstream work this enables]
**Reference:** [PRD/epic link if exists, or "Needs PRD"]
**Next command:** [e.g., `/pm:prd-new feature-name` or `/pm:epic-start feature-name`]

### 2. [One-line description]
...
```

After the ranked list, add:

```
---
**Filtered out (already shipped/in-flight):** [List targets you considered but excluded because git merge history or codebase grep confirmed they're done or actively in progress. This lets the user catch false positives.]
**Recent themes:** [2-3 word summary of what the last 2 weeks focused on]
**Suggested focus:** [1 sentence on what strategic direction these targets collectively point toward]
```

### Guidelines

- Be opinionated — rank decisively, don't hedge with "it depends"
- Ground every suggestion in concrete evidence from git history and project state
- If the backlog is empty or all PRDs are done, suggest genuinely new directions based on what the codebase enables
- Keep each suggestion to 3-5 lines — this is a brainstorm, not a design doc
- Always suggest actionable next commands so the user can immediately act on a choice
