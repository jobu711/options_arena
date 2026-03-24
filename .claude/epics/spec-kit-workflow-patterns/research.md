# Research: spec-kit-workflow-patterns

## PRD Summary

Integrate three cherry-picked workflow patterns from GitHub's spec-kit (MIT) into
Options Arena's `.claude/` development infrastructure. All changes are markdown/prompt
only — zero Python code impact:

1. **Ambiguity taxonomy** — replace spec-analyzer's Phase 3 10-point checklist with 11-category
   taxonomy (10 from spec-kit + 1 OA-specific) with Impact x Uncertainty scoring, top 5 questions
2. **`[P]` parallel task markers** — machine-readable parallelism annotation in epic task files
3. **`NEEDS CLARIFICATION` placeholders** — greppable structured markers for unresolved design
   decisions with soft gate in epic-decompose

## Relevant Existing Modules

- `.claude/agents/spec-analyzer.md` — 4-phase protocol; Phase 3 has 10-point unstructured
  checklist that will be replaced with 11-category taxonomy + scoring
- `.claude/agents/parallel-worker.md` — spawns sub-agents for parallel work streams; currently
  consumes task lists from issue-analysis, NOT from `[P]` markers in task files
- `.claude/commands/pm/epic-decompose.md` — creates task files with frontmatter including
  `parallel: true/false`; needs `[P]` marker emission + NEEDS CLARIFICATION gate
- `.claude/commands/pm/epic-status.md` — shows epic/task status; needs parallel vs sequential
  task count reporting
- `.claude/commands/pm/prd-parse.md` — converts PRD to epic; needs NEEDS CLARIFICATION scanning
- `.claude/commands/pm/epic-start.md` — launches parallel agents; needs `[P]` marker consumption
- `.claude/commands/pm/issue-analyze.md` — analyzes issues for parallel work streams; related
  to `[P]` marker work
- `.claude/guides/` — 14 existing guides; no spec-kit conventions guide exists yet

## Existing Patterns to Reuse

- **Task file frontmatter**: Already uses `parallel: true/false`, `depends_on: []`,
  `conflicts_with: []` — the `[P]` markdown markers complement (not replace) this
- **Phase-based task organization**: Epic task files already use phase headers
  (`### Phase 1: Foundation`) — `[P]` markers slot into existing format
- **4-phase spec-analyzer protocol**: Phases 1, 2, 4 remain unchanged; only Phase 3
  is enhanced — backward compatible
- **Checkpoint JSON format**: Well-established with `completed_phases`, `tasks_completed`,
  `blockers` arrays — no changes needed
- **PM command conventions**: Consistent frontmatter validation, status transitions, and
  directory structure across all 29 PM commands

## Existing Code to Extend

- `.claude/agents/spec-analyzer.md` — Replace Phase 3's 10-point checklist (lines ~56-69)
  with 11-category taxonomy table, add Impact x Uncertainty scoring, add question format
  template with Category/Context/Recommended/Alternatives/Impact
- `.claude/agents/parallel-worker.md` — Add `[P]` marker parsing section; currently reads
  task lists from issue-analysis, needs to also parse `[P]` from task file markdown
- `.claude/commands/pm/epic-decompose.md` — Add `[P]` marker emission on parallelizable
  tasks; add NEEDS CLARIFICATION pre-scan with soft gate warning
- `.claude/commands/pm/epic-status.md` — Add parallel/sequential task count to status output
- `.claude/commands/pm/prd-parse.md` — Add NEEDS CLARIFICATION scan before epic creation
- `.claude/commands/pm/epic-start.md` — Add `[P]` marker consumption for fan-out decisions

## Potential Conflicts

- **Question count cap**: Current spec-analyzer Phase 4 has no cap; new taxonomy caps at 5
  questions. **Mitigation**: PRD explicitly matches spec-kit's max-5 convention. Additional
  gaps still appear in taxonomy coverage table, just not as prioritized questions.

## Resolved Design Questions

### Q1: `[P]` markers vs `parallel: true` frontmatter — RESOLVED

**Answer: `depends_on` is the single source of truth. Both are derived views.**

Investigation revealed that `parallel: true` is currently write-only metadata — epic-decompose
writes it, epic-sync counts it for statistics, but **nothing uses it for execution decisions**.
The actual execution blocker is `depends_on: []`, which `epic-start` uses to build the
dependency graph and classify tasks as Ready vs Blocked.

A task is parallelizable within its phase iff all its `depends_on` entries resolve to earlier
phases (or it has none). epic-decompose computes this once and emits both signals consistently:

| Signal | Location | Consumer | Purpose |
|--------|----------|----------|---------|
| `depends_on: [N]` | Task frontmatter | `epic-start` | **Source of truth** — execution ordering |
| `parallel: true` | Task frontmatter | `epic-sync`, `epic-status` | Derived — PM command statistics |
| `[P]` | Task list markdown | `parallel-worker`, humans | Derived — visual scanning + agent fan-out |

No conflict is possible because both derived signals are computed from the same dependency
data. No "which is authoritative?" question arises — `depends_on` always wins.

### Q2: Where does NEEDS CLARIFICATION gate go? — RESOLVED

**Answer: Both `prd-parse` and `epic-decompose`, scanning different documents.**

The lifecycle has natural document boundaries. Each phase should scan its **input document**:

| Phase | Scans | Gate Meaning |
|-------|-------|-------------|
| `prd-parse` | PRD (`.claude/prds/*.md`) | "Your requirements have open questions" |
| `epic-decompose` | Epic (`.claude/epics/*/epic.md`) | "Your architecture decisions have open questions" |

Same mechanism at both boundaries. Both are soft gates (user can override). This is natural
because PRDs are authored by humans (requirements ambiguity), while epic.md is authored by
prd-parse (architecture ambiguity). Each phase catches the class of ambiguity introduced by
its predecessor.

## Recommended Architecture

### Implementation Approach

Since all changes are markdown-only, the implementation is straightforward file editing:

1. **spec-analyzer.md enhancement** (Issue 1): Replace Phase 3 checklist with taxonomy
   table + scoring formula + question format template. Preserve Phases 1, 2, 4 unchanged.
   Add taxonomy coverage table to output format.

2. **`[P]` marker convention** (Issue 2): Add parsing section to parallel-worker.md.
   Update epic-decompose.md to derive `[P]` markers from `depends_on` analysis
   (alongside existing `parallel: true` frontmatter — both derived from same dependency
   graph). Update epic-status.md to report parallel/sequential counts. Update
   epic-start.md to consume `[P]` markers.

3. **NEEDS CLARIFICATION convention** (Issue 3): Add scan-and-warn logic to both
   prd-parse.md (scans PRD for requirement ambiguity) and epic-decompose.md (scans
   epic.md for architecture ambiguity). Same soft gate mechanism at both boundaries.
   Document format and resolution protocol.

4. **Reference guide** (Issue 4): Create `.claude/guides/spec-kit-conventions.md`
   documenting all three conventions with examples, rules, and resolution protocols.

5. **Verification** (Issue 5): Run spec-analyzer on an existing PRD, validate 11-category
   output format.

### Dependency Graph

```
Issues 1, 2, 3  →  [P] all independent
Issue 4          →  depends on 1, 2, 3 (reference guide consolidates all)
Issue 5          →  depends on 1 (verification of taxonomy output)
```

## Test Strategy Preview

- **No automated tests** — all changes are `.claude/` markdown files, not Python code
- **Manual verification**:
  - Run `spec-analyzer` on `unified-agent-system` PRD → validate taxonomy table output
  - Create sample task file with `[P]` markers → validate parallel-worker parses them
  - Add `[NEEDS CLARIFICATION: ...]` to a test PRD → validate epic-decompose warns
  - Run `grep -r "NEEDS CLARIFICATION" .claude/` → verify greppability
- **Regression check**: Run existing PM commands on existing epics to ensure no breakage

## Estimated Complexity

**S (Small)** — All changes are markdown prompt/convention edits in `.claude/`. No Python
code, no tests, no migrations, no API changes. Five issues, all small effort. Total: 1-2 days.
Issues 1-3 are fully independent and parallelizable.
