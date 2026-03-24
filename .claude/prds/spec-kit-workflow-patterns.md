---
name: spec-kit-workflow-patterns
description: Integrate 3 cherry-picked workflow patterns from github/spec-kit — ambiguity taxonomy for spec analysis, [P] parallel task markers in epics, and NEEDS CLARIFICATION structured placeholders
status: complete
created: 2026-03-22T17:43:57Z
revised: 2026-03-22T18:30:00Z
revision_notes: Context7 audit — fixed category count (10+1), question limit (5 not 10), task ID attribution, removed unverified star count, noted gate strength divergence
source_audit: https://github.com/github/spec-kit (MIT license)
depends_on: []
---

# PRD: Spec-Kit Workflow Patterns — Development Infrastructure Improvements

## Executive Summary

Integrate three cherry-picked patterns from GitHub's spec-kit repository (MIT) into
Options Arena's `.claude/` development infrastructure. These are "port the idea"
adaptations — no code is copied, only workflow conventions are adopted into existing
agent prompts and epic templates. All three are prompt/convention changes with zero
Python code impact:

1. **Ambiguity taxonomy** for the `spec-analyzer` agent — structured 10+1 category scan
   (10 from spec-kit + 1 OA-specific) with `Impact x Uncertainty` prioritization
   replaces unstructured gap discovery
2. **`[P]` parallel task markers** in epic task files — machine-readable parallelism
   annotation replaces prose convention
3. **`NEEDS CLARIFICATION` structured placeholders** in PRDs and epics — explicit
   greppable markers replace vague prose for unresolved design decisions

Combined, these reduce spec debt (ambiguities that surface as bugs during implementation),
make wave-execution patterns explicit, and ensure open questions are tracked rather than
forgotten.

## Problem Statement

### What problem are we solving?

Options Arena's Claude Code infrastructure has matured across 39+ epics and 638+ issues,
but three workflow friction points persist:

1. **Unstructured ambiguity discovery**: The `spec-analyzer` agent uses a 4-phase protocol
   (flow tracing, permutation discovery, gap identification, question formulation) that is
   thorough but unstructured. Phase 3's 10-point checklist covers correctness and testing
   concerns but misses entire categories — terminology consistency, non-functional quality
   attributes (latency, observability), completion signals (testability of acceptance
   criteria), and placeholder detection (TODO markers, vague adjectives). There is no
   prioritization formula — gaps are classified as blocking/non-blocking/deferred by
   judgment, not by scored criteria.

2. **Implicit parallelism in epic tasks**: Epic task files use plain `- [ ]` checkboxes.
   The wave-execution convention ("foundation first, then parallel where safe") is
   documented in `MEMORY.md` as prose but is not machine-readable. When resuming an
   epic after context loss, the orchestrating agent must re-derive which tasks can
   run concurrently. The `parallel-worker` agent has no formal marker to consume —
   it relies on the invoker to specify which tasks are independent.

3. **Vague unresolved questions**: PRDs and epic files express uncertainty in free text
   ("this needs to be decided", "TBD", "we should figure this out"). These are not
   greppable, not trackable, and frequently forgotten until implementation surfaces the
   gap as a blocking question. The unified-agent-system PRD handled this well via explicit
   design sections, but there is no enforced convention.

### Why is this important now?

Three remaining unified-agent-system sub-epics (desk-recommend, orchestrator, cutover)
represent the largest remaining implementation effort. Each will be decomposed into 5-8
tasks with complex dependency chains. The orchestrator epic in particular requires careful
parallelism planning (6 desk agents run concurrently, synthesis is sequential). Adopting
these conventions before decomposition means:

- Ambiguity scanning catches gaps in the desk-recommend and orchestrator PRD sections
  before task decomposition begins
- Parallel markers in task files prevent the orchestrating agent from accidentally
  serializing independent work
- NEEDS CLARIFICATION markers ensure the remaining open questions (should_recommend
  threshold, spread passthrough rules, paid-provider parallelism) are tracked to resolution

### What does success look like?

1. `spec-analyzer` produces findings categorized across all 11 taxonomy categories
   (10 from spec-kit + 1 OA-specific) with scored priorities — no more unstructured
   gap lists
2. Epic task files contain `[P]` markers that the `parallel-worker` agent can parse to
   determine concurrency without human guidance
3. All PRDs and epic files use `[NEEDS CLARIFICATION: question]` for open questions, and
   `/pm:epic-decompose` refuses to decompose a section that contains unresolved markers
   without explicit acknowledgment

## User Stories

### Structured Ambiguity Scanning
- **As the developer running spec-analyzer**, I want gaps categorized by domain (scope,
  data model, UX, non-functional, integration, edge cases, constraints, terminology,
  completion signals, placeholders, priorities) so I can address them systematically
  instead of reading an undifferentiated list.
  - *Acceptance*: spec-analyzer output includes a taxonomy coverage table showing which
    categories were scanned and how many gaps were found per category.

### Prioritized Questions
- **As the developer reviewing spec-analyzer output**, I want gaps scored by
  `Impact x Uncertainty` so the most dangerous ambiguities surface first, not the
  most obvious ones.
  - *Acceptance*: Each gap has an explicit Impact (1-3) and Uncertainty (1-3) score.
    Output is sorted by `Impact x Uncertainty` descending. Maximum 5 questions surfaced
    (matches spec-kit convention; prevents analysis paralysis).

### Parallel Task Markers
- **As the developer decomposing an epic**, I want to mark tasks as `[P]` (parallelizable)
  so that when I or the parallel-worker agent executes the epic, concurrency is explicit.
  - *Acceptance*: `/pm:epic-decompose` emits `[P]` markers on tasks that have no
    intra-phase dependencies. `parallel-worker` agent parses `[P]` markers to determine
    which tasks to fan out.

### Clarification Markers
- **As the PRD author**, I want a standard marker `[NEEDS CLARIFICATION: question]` for
  unresolved design decisions so they are greppable and trackable across all `.claude/`
  artifacts.
  - *Acceptance*: `grep -r "NEEDS CLARIFICATION" .claude/` finds all open questions.
    `/pm:epic-decompose` warns when a PRD section contains unresolved markers and asks
    whether to proceed or resolve first.

### Recommended-Option Questions
- **As the developer answering spec-analyzer questions**, I want each question to include
  a recommended answer (with reasoning) so I can accept or override rather than research
  from scratch.
  - *Acceptance*: Each blocking question includes `Recommended: [option] — [reasoning]`
    followed by 2-4 alternatives.

## Architecture & Design

### No Python Code Changes

All changes are to markdown files in `.claude/`. No changes to `src/options_arena/`,
`tests/`, `web/`, or any Python source code.

**Files modified:**
- `.claude/agents/spec-analyzer.md` — enhanced prompt with 10+1 category taxonomy
- `.claude/agents/parallel-worker.md` — `[P]` marker parsing instructions
- `.claude/commands/` — PM skills updated for marker conventions
- `.claude/guides/` — new guide documenting conventions

**Files created:**
- `.claude/guides/spec-kit-conventions.md` — reference guide for all three conventions

### Pattern 1: Ambiguity Taxonomy (spec-analyzer enhancement)

Extend the existing 4-phase protocol in `.claude/agents/spec-analyzer.md`:

**Phase 3 replacement** — replace the current 10-point checklist with an 11-category
taxonomy scan (10 from spec-kit's `clarify.md` + 1 OA-specific addition). Each
category is scanned independently:

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

**Scoring formula**: Each gap receives:
- **Impact** (1-3): 1 = cosmetic/deferred, 2 = affects implementation decisions, 3 = blocks correct implementation
- **Uncertainty** (1-3): 1 = reasonable default exists, 2 = multiple valid options, 3 = no basis for choosing

Priority = `Impact x Uncertainty` (range 1-9). Top 5 gaps surfaced as questions
(matching spec-kit's max-5 convention).

**Question format** (enhanced from current):
```
[Blocking/Non-blocking/Deferred] Q{N} (Impact:{I} x Uncertainty:{U} = {P}): {question}
  Category: {taxonomy category name}
  Context: {why this matters in OA's architecture}
  Recommended: {best option} — {reasoning}
  Alternatives:
    A) {option} — {tradeoff}
    B) {option} — {tradeoff}
  Impact if unanswered: {what breaks or degrades}
```

**Backward compatibility**: The existing 10-point checklist from Phase 3 is subsumed —
items 1-10 map cleanly into the taxonomy categories:
- Happy path → Category 1 (Functional Scope)
- Error paths → Category 6 (Edge Cases)
- Boundary conditions → Category 6
- State transitions → Category 1
- Concurrency → Category 4 (Non-Functional)
- Rollback → Category 6
- Observability → Category 4
- Testability → Category 9 (Completion Signals)
- Migration → Category 5 (Integration)
- Documentation → Category 10 (Placeholders)

### Pattern 2: Parallel Task Markers

Convention for epic task files (`.claude/epics/*/NNN.md`):

```markdown
## Tasks

### Phase 1: Foundation
- [ ] [P] T1.1 Create FooModel in models/foo.py
- [ ] [P] T1.2 Create BarModel in models/bar.py
- [ ] T1.3 Add migration 038 (depends on T1.1, T1.2)

### Phase 2: Implementation
- [ ] [P] T2.1 Add foo_service.py (depends on T1.3)
- [ ] [P] T2.2 Add bar_handler.py (depends on T1.3)
- [ ] T2.3 Wire into pipeline (depends on T2.1, T2.2)
```

**Rules:**
- `[P]` means "this task can execute concurrently with other `[P]` tasks in the same phase"
- Tasks without `[P]` are sequential barriers — all preceding `[P]` tasks must complete first
- Phase boundaries are always sequential barriers (Phase 2 waits for all of Phase 1)
- `(depends on T{X}.{Y})` annotations are optional but recommended for cross-references
- Task IDs follow `T{phase}.{sequence}` format for stable cross-referencing

**Consumers:**
- `parallel-worker` agent: parse `[P]` markers to determine fan-out
- `/pm:epic-decompose`: emit `[P]` markers based on dependency analysis
- `/pm:epic-status`: show parallel vs sequential task counts
- Human developers: visual scan for parallelism at a glance

### Pattern 3: NEEDS CLARIFICATION Markers

Standard placeholder for unresolved design decisions:

```markdown
**Performance target**: [NEEDS CLARIFICATION: What is the acceptable latency for
a 50-ticker batch recommendation? Current scan takes ~3min for full universe.]
```

**Rules:**
- Format: `[NEEDS CLARIFICATION: {specific question}]`
- Appears inline in PRDs, epic files, and task descriptions
- Greppable: `grep -r "NEEDS CLARIFICATION" .claude/` finds all open questions
- Resolution: replace the marker with the answer and a `Resolved:` annotation:
  ```markdown
  **Performance target**: 60 seconds for 50-ticker batch
  <!-- Resolved 2026-03-25: 60s target based on Groq rate limits (30 RPM) -->
  ```
- Gate behavior: `/pm:epic-decompose` scans for unresolved markers before decomposing.
  If found, it displays them and asks: "N unresolved questions found. Proceed with
  defaults or resolve first?" This is a soft gate — the user can override.

**Where markers are valid:**
- `.claude/prds/*.md` — PRD sections with open design questions
- `.claude/epics/*/*.md` — Epic and task files with implementation ambiguity
- NOT in Python source code (use `# TODO:` for code-level questions)

## Non-Goals

- **No Python code changes**: This PRD modifies only `.claude/` markdown files
- **No new tools or scripts**: All patterns are convention-based, enforced by prompt instructions
- **No retroactive application**: Existing PRDs and epics are not modified (apply conventions
  going forward only)
- **No mandatory gates**: The NEEDS CLARIFICATION gate is soft (user can override). The
  parallel markers are advisory (agent can still serialize if unsure)
- **No spec-kit installation**: We adopt the ideas, not the tool. No `specify` CLI dependency.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Taxonomy overhead — 11 categories (10+1) is too many for simple PRDs | Medium | Low | Spec-analyzer skips categories with zero findings; output collapses empty categories |
| `[P]` markers become stale as tasks evolve | Low | Low | Markers are advisory; agent verifies independence before parallel execution |
| NEEDS CLARIFICATION markers accumulate without resolution | Medium | Medium | Periodic grep + report in `/pm:epic-status` |
| Convention drift — contributors forget markers | Low | Low | Prompt instructions enforce; no silent degradation |

## Verification Criteria

1. Run `spec-analyzer` on the existing `unified-agent-system` PRD — output should
   include the 11-category (10+1) taxonomy table with scored gaps
2. Run `/pm:epic-decompose` on a test PRD containing `[NEEDS CLARIFICATION: ...]` —
   should warn and ask before proceeding
3. Create a sample epic task file with `[P]` markers — `parallel-worker` should
   correctly identify parallelizable tasks
4. `grep -r "NEEDS CLARIFICATION" .claude/` returns zero results after all questions
   in this PRD's scope are resolved

## Epic Decomposition Guidance

This PRD is small enough for a single epic with 3-5 issues:

| Issue | Description | Effort | Dependencies |
|-------|-------------|--------|-------------|
| 1 | Enhance `spec-analyzer.md` with 10+1 category taxonomy and scoring | S | None |
| 2 | Add `[P]` marker convention to `parallel-worker.md` and PM skill prompts | S | None |
| 3 | Add NEEDS CLARIFICATION convention to PM skill prompts and guide | S | None |
| 4 | Create `.claude/guides/spec-kit-conventions.md` reference guide | S | 1, 2, 3 |
| 5 | Verify: run spec-analyzer on unified-agent-system PRD, validate output | S | 1 |

Issues 1-3 are independent (`[P]`). Issue 4 depends on all three. Issue 5 depends on 1.
Total effort: 1-2 days.

## Appendix: Source Attribution

All patterns adapted from [github/spec-kit](https://github.com/github/spec-kit) (MIT license).

**Notable divergences from source** (Context7-verified 2026-03-22):
- spec-kit uses 10 ambiguity categories; OA adds an 11th (Priority & Sequencing)
- spec-kit caps at 5 prioritized questions; OA matches this limit
- spec-kit uses sequential task IDs (`T001`); OA adapts to phase-scoped (`T{phase}.{seq}`)
- spec-kit's gates are hard ("prevent progression without passing or justified exceptions");
  OA deliberately softens to a user-overridable warning

| Pattern | Source File | Adaptation Type |
|---------|-----------|----------------|
| Ambiguity taxonomy | `templates/commands/clarify.md` | Port the idea — 10 categories adopted, 1 OA-specific added |
| Impact x Uncertainty scoring | `templates/commands/clarify.md` | Port the idea — same formula, same max-5 limit |
| Recommended-option questions | `templates/commands/clarify.md` | Port the idea — same format |
| `[P]` parallel markers | `templates/commands/tasks.md`, `templates/tasks-template.md` | Port the idea — same convention |
| Task IDs (`T{phase}.{seq}`) | `templates/tasks-template.md` | Port the idea — adapted format (source uses `T001` sequential) |
| NEEDS CLARIFICATION markers | `templates/plan-template.md`, `spec-driven.md` | Port the idea — same convention |
| Soft gate on unresolved markers | `templates/commands/implement.md` | Port the idea — softened from hard gate to user-overridable warning |

### Excluded from this PRD (already implemented or lower priority)

| Pattern | Reason for Exclusion |
|---------|---------------------|
| Severity-classified audit output | Already implemented — 7 audit agents emit YAML preambles with CRITICAL/HIGH/MEDIUM/LOW; `/full-audit` consolidates to P1-P4 |
| Handoffs frontmatter | B-tier — requires skill system enhancement to parse frontmatter |
| Structured retro template | B-tier — lower urgency than pre-implementation improvements |
| Marker-delimited context injection | B-tier — useful but not blocking any current work |
| Checklist-gated implementation | B-tier — partially covered by existing verification gates |
