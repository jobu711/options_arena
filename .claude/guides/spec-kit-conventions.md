# Spec-Kit Conventions -- Quick Reference

Consolidated reference for the three spec-kit workflow patterns adopted by Options Arena.
Covers ambiguity taxonomy, parallel task markers, and NEEDS CLARIFICATION placeholders.

Load this guide when: encountering `[P]` markers, `[NEEDS CLARIFICATION: ...]` placeholders,
or ambiguity scoring in spec-analyzer output.

## Source Attribution

All patterns adapted from [github/spec-kit](https://github.com/github/spec-kit) (MIT license).
Context7-verified 2026-03-22.

### Notable Divergences from Source

| Divergence | spec-kit | Options Arena |
|-----------|----------|---------------|
| Ambiguity categories | 10 categories | 11 categories (adds Priority & Sequencing) |
| Max prioritized questions | 5 | 5 (same) |
| Task IDs | Sequential (`T001`) | Phase-scoped (`T{phase}.{seq}`) |
| Gate behavior | Hard gate (blocks progression without justified exception) | Soft gate (user-overridable warning) |

### Pattern Source Mapping

| Pattern | Source File | Adaptation |
|---------|-----------|------------|
| Ambiguity taxonomy | `templates/commands/clarify.md` | 10 categories adopted, 1 OA-specific added |
| Impact x Uncertainty scoring | `templates/commands/clarify.md` | Same formula, same max-5 limit |
| Recommended-option questions | `templates/commands/clarify.md` | Same format |
| `[P]` parallel markers | `templates/commands/tasks.md`, `templates/tasks-template.md` | Same convention |
| Task IDs (`T{phase}.{seq}`) | `templates/tasks-template.md` | Adapted format (source uses `T001` sequential) |
| NEEDS CLARIFICATION markers | `templates/plan-template.md`, `spec-driven.md` | Same convention |
| Soft gate on unresolved markers | `templates/commands/implement.md` | Softened from hard gate to user-overridable warning |

---

## 1. Ambiguity Taxonomy (spec-analyzer)

The spec-analyzer agent (`.claude/agents/spec-analyzer.md`) uses an 11-category taxonomy to
classify gaps found during requirements analysis. Run the spec-analyzer before `/pm:prd-parse`
on non-trivial PRDs.

### Categories (11)

| # | Category | What to Look For |
|---|----------|-----------------|
| 1 | Functional Scope & Behavior | Missing happy paths, undefined state machines, unclear triggers |
| 2 | Domain & Data Model | Undefined fields, missing relationships, unclear cardinality |
| 3 | Interaction & UX Flow | Undefined user journeys, missing CLI output specs, unclear API contracts |
| 4 | Non-Functional Quality | Missing latency targets, undefined scaling limits, no observability spec |
| 5 | Integration & Dependencies | Undefined service interactions, missing fallback behavior, unclear auth |
| 6 | Edge Cases & Failure Handling | Missing error paths, undefined retry behavior, no graceful degradation |
| 7 | Constraints & Tradeoffs | Unstated assumptions, hidden coupling, unacknowledged tech debt |
| 8 | Terminology & Consistency | Inconsistent naming across sections, domain terms used differently |
| 9 | Completion Signals | Untestable acceptance criteria, vague "should work" statements |
| 10 | Placeholders & TODOs | TBD markers, vague adjectives without metrics, incomplete sections |
| 11 | Priority & Sequencing (OA addition) | Unclear dependencies between features, missing phasing guidance |

Categories 1-10 are adopted from spec-kit. Category 11 is an OA-specific addition.

### Scoring: Impact x Uncertainty

Each gap receives two scores:

- **Impact** (1-3): 1 = cosmetic/deferred, 2 = affects implementation decisions, 3 = blocks correct implementation
- **Uncertainty** (1-3): 1 = reasonable default exists, 2 = multiple valid options, 3 = no basis for choosing

**Priority = Impact x Uncertainty** (range 1-9). All gaps are sorted by priority descending.
The **top 5** gaps are surfaced as prioritized questions. Remaining gaps appear in the
taxonomy coverage table but are not elevated to questions.

### Question Format

Each of the top 5 gaps is formulated as a structured question with six fields:

```
[Blocking/Non-blocking/Deferred] Q{N} (Impact:{I} x Uncertainty:{U} = {P}): {specific question}
  Category: {taxonomy category name}
  Context: {why this matters in OA's architecture}
  Recommended: {best option} -- {reasoning}
  Alternatives:
    A) {option} -- {tradeoff}
    B) {option} -- {tradeoff}
  Impact if unanswered: {what breaks or degrades}
```

Classification types:
- **Blocking** -- Cannot proceed with implementation without an answer
- **Non-blocking** -- Reasonable default exists; proceed but document assumption
- **Deferred** -- Edge case that can be addressed in a follow-up issue

### Backward Compatibility

The previous 10-point checklist is fully subsumed by the 11-category taxonomy:

| Old # | Old Checklist Item | New Category |
|-------|-------------------|-------------|
| 1 | Happy path fully specified? | 1 -- Functional Scope & Behavior |
| 2 | Error path handling specified? | 6 -- Edge Cases & Failure Handling |
| 3 | Boundary conditions? | 6 -- Edge Cases & Failure Handling |
| 4 | Unexpected state transitions? | 1 -- Functional Scope & Behavior |
| 5 | Concurrency considerations? | 4 -- Non-Functional Quality |
| 6 | Rollback on mid-failure? | 6 -- Edge Cases & Failure Handling |
| 7 | Observability? | 4 -- Non-Functional Quality |
| 8 | Testability? | 9 -- Completion Signals |
| 9 | Migration required? | 5 -- Integration & Dependencies |
| 10 | Documentation updates? | 10 -- Placeholders & TODOs |

New categories not covered by the old checklist: 2 (Domain & Data Model),
3 (Interaction & UX Flow), 7 (Constraints & Tradeoffs), 8 (Terminology & Consistency),
11 (Priority & Sequencing).

---

## 2. Parallel Task Markers ([P])

Task files and epic summaries use `[P]` markers to annotate parallelizable work. Defined
in `.claude/agents/parallel-worker.md` and emitted by `/pm:epic-decompose`.

### Convention Rules

| Marker | Meaning |
|--------|---------|
| `[P]` present | Task can run concurrently with other `[P]` tasks in the same phase |
| No `[P]` | Sequential barrier -- all preceding `[P]` tasks must complete first |
| Phase boundary | Always a sequential barrier, regardless of markers |

### Source of Truth: depends_on

`depends_on` in task frontmatter is the **single source of truth** for execution ordering.
Both `parallel: true` in frontmatter and `[P]` in markdown are derived views.

A task gets `[P]` if and only if:
- Its `depends_on` list is empty, OR
- All entries in `depends_on` resolve to tasks in earlier phases

| Signal | Location | Consumer | Purpose |
|--------|----------|----------|---------|
| `depends_on: [N]` | Task frontmatter | `epic-start` | **Source of truth** -- execution ordering |
| `parallel: true` | Task frontmatter | `epic-sync`, `epic-status` | Derived -- PM command statistics |
| `[P]` | Task list markdown | `parallel-worker`, humans | Derived -- visual scanning + agent fan-out |

### Derivation Rule (epic-decompose)

When `/pm:epic-decompose` writes the `## Tasks Created` section, it scans each task's
`depends_on` list. If empty or all dependencies are in earlier phases, the task line is
prefixed with `[P]`. Otherwise, `[P]` is omitted (sequential barrier).

### Examples

```
## Tasks Created
- [ ] [P] 001.md - Add GICSSector StrEnum (parallel: true)
- [ ] [P] 002.md - Add sector filter to scan config (parallel: true)
- [ ] 003.md - Wire sector filter into pipeline (parallel: false, depends on 001, 002)
- [ ] [P] 004.md - Add CLI --sectors flag (parallel: true)
- [ ] 005.md - Integration tests (parallel: false, depends on 003)

Total tasks: 5
Parallel tasks: 3
Sequential tasks: 2
```

In this example, tasks 001 and 002 run in parallel, task 003 waits for both, task 004
can run alongside 001/002 (no dependencies), and task 005 waits for 003.

### Parsing Rules (for parallel-worker agent)

1. Scan task lists for lines matching `- [ ] [P]` prefix
2. Extract task IDs (e.g., `001.md`) from those lines
3. All `[P]` tasks in the same phase can be spawned simultaneously
4. Non-`[P]` tasks are sequential barriers -- wait for all prior `[P]` tasks to finish

### Fallback

If no `[P]` markers are present (e.g., older task files), fall back to reading each task's
`depends_on` frontmatter to derive parallelism. The markers are a convenience, not a
requirement.

---

## 3. NEEDS CLARIFICATION Placeholders

Unresolved design questions are tracked inline using `[NEEDS CLARIFICATION: ...]` markers.
Defined in `/pm:prd-parse` and `/pm:epic-decompose`.

### Marker Format

```
[NEEDS CLARIFICATION: {specific question}]
```

The question inside must be specific and answerable -- not vague. Example:

```
[NEEDS CLARIFICATION: Should sector filtering apply before or after liquidity scoring?]
```

### Resolution Format

When a marker is resolved, replace it with the answer and add an HTML comment annotation:

```
Sector filtering applies before liquidity scoring to reduce the candidate set early.
<!-- Resolved 2026-03-24: confirmed with architecture review -->
```

### Where Markers Are Valid

Markers are only valid in planning documents:
- `.claude/prds/*.md` -- Product Requirements Documents
- `.claude/epics/*/*.md` -- Epic files and task files

Markers are **not valid** in Python source code, test files, or any non-planning document.

### Gate Behavior

Two PM commands scan for unresolved markers:

**`/pm:prd-parse`** scans the PRD before epic creation:
```
Scanning PRD for unresolved questions...
Found {N} unresolved NEEDS CLARIFICATION markers:

  1. [NEEDS CLARIFICATION: {question}]
     Location: line {N}
  2. [NEEDS CLARIFICATION: {question}]
     Location: line {N}

{N} unresolved questions found. Options:
  - Proceed anyway (questions documented but unresolved)
  - Resolve now (provide answers inline)
  - Stop and edit the PRD first
```

**`/pm:epic-decompose`** scans the epic file before task creation, with the same
display format and options.

Both are **soft gates** -- the user can always override and proceed. If no markers are
found, the scan completes silently (no output).

The quality validation step in `/pm:epic-decompose` also checks that no unresolved
`[NEEDS CLARIFICATION: ...]` markers remain in generated task descriptions.

---

## Divergences from spec-kit

Summary of all OA-specific adaptations in one place:

| Convention | spec-kit Original | OA Adaptation | Rationale |
|-----------|-------------------|---------------|-----------|
| Category count | 10 ambiguity categories | 11 (adds Priority & Sequencing) | OA epics have complex dependency chains that need explicit phasing guidance |
| Max questions | 5 prioritized questions | 5 (unchanged) | Matches source -- keeps output focused |
| Task IDs | Sequential (`T001`, `T002`) | Phase-scoped (`T{phase}.{seq}`) | Better reflects OA's phase-based pipeline architecture |
| Gate type | Hard gate (blocks without justified exception) | Soft gate (user-overridable warning) | OA's workflow is iterative -- blocking kills velocity on exploratory PRDs |
| `[P]` markers | Present in task templates | Adopted unchanged | Convention works as-is for OA's parallel-worker agent |
| NEEDS CLARIFICATION | Present in plan templates | Adopted unchanged | Convention works as-is for OA's PM command chain |
| Scoring formula | Impact x Uncertainty | Adopted unchanged | Produces intuitive 1-9 priority range |
