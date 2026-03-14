---
allowed-tools: Read, Glob, Grep, Bash, Write
description: "Audit CI/CD, agents, hooks, config, and devops gaps"
---

<role>
You are the devops infrastructure auditor for Options Arena. You run direct checks
(no dedicated agent) against CI/CD pipelines, build configuration, hooks, agent
coordination, and external service readiness. You produce a structured report at
`.claude/audits/AUDIT_DEVOPS.md` using the standard YAML preamble + P1-P4 findings
format, compatible with the `/full-audit` consolidation pipeline.
</role>

<context>
Options Arena has 7 T1 auditor agents with non-overlapping scopes, orchestrated by
`/full-audit`. This devops-audit command covers infrastructure concerns that NO existing
auditor addresses:

- Agent ecosystem health (registry, scopes, parallel safety, coordination)
- CI/CD pipeline configuration and gate verification
- Build config drift from CLAUDE.md standards (ruff, mypy, pytest)
- Hook integrity and registration
- Version synchronization across pyproject.toml, web/package.json, progress.md
- Context budget compliance

Existing auditors and their scopes (do NOT duplicate these):
- `security-auditor` — OWASP, secrets, injection, input sanitization
- `bug-auditor` — async correctness, resource lifecycle, concurrency, error handling
- `code-reviewer` — typed models, NaN defense, type annotations, Pydantic conventions
- `architect-reviewer` — module boundaries, dependency direction, pattern consistency
- `db-auditor` — SQL injection, queries, migrations, serialization, data integrity
- `dep-auditor` — CVEs, outdated packages, unused deps, license compliance
- `oa-python-reviewer` — pricing math, scoring rules, indicator correctness, financial precision

Reference files for checks:
- `CLAUDE.md` — boundary table, ruff/mypy specs, context budget limits
- `.claude/guides/agent-coordination.md` — agent tiers, module-to-agent mapping
- `.claude/settings.json` — hook registrations
- `pyproject.toml` — build config, tool settings
- `.github/workflows/ci.yml` — CI pipeline gates
</context>

<task>
Run a comprehensive devops infrastructure audit covering 39 static analysis checks
across 7 categories. Accumulate all findings in a consistent format, then write the
report to `.claude/audits/AUDIT_DEVOPS.md`.

This command takes no arguments. It always performs a full devops audit.
</task>

<instructions>

## Setup

1. Create `.claude/audits/` directory if it doesn't exist:
   ```
   mkdir -p .claude/audits
   ```
2. Note the current UTC timestamp for the report header.
3. Initialize an empty findings list. Each finding is a structured entry:
   ```
   [CATEGORY] file:line — Description. Impact: ... Fix: ...
   ```
4. Initialize counters: `critical=0, high=0, medium=0, low=0`.

## Phase 1: Static Analysis (39 checks)

Execute each check sequentially. For each failing check, add a finding to the list with
the specified severity and increment the corresponding counter.

---

### A. Agent Registry & Inventory (checks 1-5)

**Check 1: Agent census**
- **Action**: Glob `.claude/agents/*.md` to list all agent definition files.
- **For each file**: Read the file and extract: agent name (filename), tools listed,
  model tier, and tier classification (T1-T5).
- **Pass**: All agent files are readable and contain a recognizable role/scope section.
- **Fail**: Any agent file is empty, missing, or has no discernible scope description.
- **Severity**: P3
- **Finding**: `[REGISTRY] .claude/agents/{name}.md — Agent file has no scope description. Impact: Cannot verify non-overlap or coverage. Fix: Add scope description with IN/OUT columns.`

**Check 2: Skill census**
- **Action**: Glob `.claude/commands/*.md` and `.claude/commands/**/*.md` to list all
  slash command files (skills).
- **For each file**: Read the frontmatter to extract `allowed-tools` and `description`.
- **Pass**: All command files have valid frontmatter with `allowed-tools` and `description`.
- **Fail**: Any command file is missing frontmatter or required fields.
- **Severity**: P3
- **Finding**: `[REGISTRY] .claude/commands/{name}.md — Missing frontmatter field: {field}. Impact: Command may not function correctly. Fix: Add {field} to YAML frontmatter.`

**Check 3: Orphan detection**
- **Action**: For each agent in `.claude/agents/*.md`, Grep across all command files
  (`.claude/commands/**/*.md`) for references to that agent name (the filename stem
  without `.md`).
- **Pass**: Every agent is referenced by at least one command.
- **Fail**: Agent is defined but never referenced by any command.
- **Severity**: P2
- **Finding**: `[REGISTRY] .claude/agents/{name}.md — Orphaned agent: defined but never referenced by any command. Impact: Agent exists but is never invoked. Fix: Reference from a command or remove if obsolete.`

**Check 4: Phantom references**
- **Action**: Grep all command files (`.claude/commands/**/*.md`) for agent name
  patterns (look for backtick-quoted names matching known agent filenames, and any
  name that looks like an agent reference but does not correspond to a file in
  `.claude/agents/`).
- **Pass**: Every agent name referenced in commands exists in `.claude/agents/`.
- **Fail**: A command references an agent that has no definition file.
- **Severity**: P1
- **Finding**: `[REGISTRY] .claude/commands/{command}.md — Phantom reference to agent "{name}" which does not exist in .claude/agents/. Impact: Command will fail when trying to invoke this agent. Fix: Create the agent definition or fix the reference.`

**Check 5: New agent validation**
- **Action**: Read `.claude/guides/agent-coordination.md` (if it exists). Extract the
  list of agents mentioned in the coordination guide. Compare against the actual agent
  files from Check 1.
- **Pass**: Agent list in coordination guide matches actual agent files.
- **Fail (a)**: Agent exists in `.claude/agents/` but is not listed in the coordination guide.
- **Fail (b)**: Agent listed in the coordination guide but has no file in `.claude/agents/`.
- **Severity**: P2
- **Finding**: `[REGISTRY] .claude/agents/{name}.md — Agent {exists in/missing from} coordination guide but {missing from/exists in} agent directory. Impact: Coordination guide is out of sync. Fix: Update .claude/guides/agent-coordination.md to match actual agent inventory.`

---

### B. Scope Boundaries & Overlap (checks 6-10)

**Check 6: Scope extraction**
- **Action**: For each T1 auditor agent (architect-reviewer, code-reviewer,
  security-auditor, bug-auditor, db-auditor, dep-auditor, oa-python-reviewer), read
  its agent file and extract the IN scope and OUT scope descriptions.
- **Pass**: Each T1 auditor has clearly defined IN and OUT scope sections.
- **Fail**: A T1 auditor is missing IN scope, OUT scope, or both.
- **Severity**: P2
- **Finding**: `[SCOPE] .claude/agents/{name}.md — Missing {IN/OUT} scope definition. Impact: Cannot verify non-overlap guarantee. Fix: Add explicit IN scope and OUT scope sections.`

**Check 7: Overlap matrix**
- **Action**: Using the scope descriptions from Check 6, cross-compare all T1 auditor
  pairs. Look for keywords/concerns that appear in the IN scope of two different agents.
  Key concern domains to check: "async", "security", "SQL/database", "types/models",
  "boundaries/architecture", "dependencies", "pricing/scoring", "NaN".
- **Pass**: No two T1 auditors claim the same concern domain in their IN scope.
- **Fail**: Two or more T1 auditors have overlapping IN scope on the same concern.
- **Severity**: P2
- **Finding**: `[SCOPE] .claude/agents/{a}.md + .claude/agents/{b}.md — Overlapping scope: both claim "{concern}" in IN scope. Impact: Parallel execution may produce duplicate findings. Fix: Reassign "{concern}" to one agent and add it to the other's OUT scope.`

**Check 8: Module coverage map**
- **Action**: List all top-level modules under `src/options_arena/` using Glob
  `src/options_arena/*/`. Read the module-to-agent mapping from
  `.claude/guides/agent-coordination.md`. For each module, check if it has at least
  one assigned auditor in the mapping.
- **Pass**: Every module has at least one auditor assigned. No module has 2+ auditors
  covering the same concern type.
- **Fail (a)**: Module has zero auditors assigned.
- **Fail (b)**: Module has 2+ auditors assigned for the same concern.
- **Severity**: P2
- **Finding**: `[SCOPE] src/options_arena/{module}/ — {No auditor assigned | Multiple auditors ({names}) assigned for same concern}. Impact: {Gaps in audit coverage | Duplicate findings}. Fix: Update module-to-agent mapping in agent-coordination.md.`

**Check 9: Boundary table sync**
- **Action**: Read the "Architecture Boundaries" table from `CLAUDE.md` (the table with
  Module, Responsibility, Can Access, Cannot Access columns). Read the module-to-agent
  mapping from `.claude/guides/agent-coordination.md`. Verify every module in the
  boundary table appears in the agent mapping, and vice versa.
- **Pass**: Both tables cover the same set of modules.
- **Fail**: A module appears in one table but not the other.
- **Severity**: P3
- **Finding**: `[SCOPE] {module} — Present in {CLAUDE.md boundary table | agent-coordination.md} but missing from {the other}. Impact: Inconsistent documentation. Fix: Sync both tables.`

**Check 10: Concern deduplication**
- **Action**: Grep all agent files and all command files for common check patterns
  (e.g., "ruff", "mypy", "NaN", "isfinite", "frozen=True", "UTC validator"). If the
  same specific validation check appears in both an agent definition AND a command
  definition, it is a redundant check.
- **Pass**: No specific validation check is duplicated between agents and commands.
- **Fail**: Same check logic appears in multiple places.
- **Severity**: P3
- **Finding**: `[SCOPE] {file1} + {file2} — Both check for "{pattern}". Impact: Redundant validation wastes execution time. Fix: Assign check to one location only.`

---

### C. Parallel Execution Safety (checks 11-15)

**Check 11: Read-only enforcement**
- **Action**: For each T1 auditor agent file, read the file and look for tool
  declarations. Check whether any T1 auditor has Write, Edit, Bash (with write
  commands), or NotebookEdit in its allowed tools or instructions.
- **Also check**: `.claude/commands/full-audit.md` for how agents are launched. If agent
  launch prompts instruct agents to write to `.claude/audits/AUDIT_*.md`, that is
  acceptable (audit output). Any other write target is a violation.
- **Pass**: T1 auditors have only read-only tools (Read, Glob, Grep) plus write access
  limited to their own audit report file.
- **Fail**: A T1 auditor has Write/Edit tools that could modify application source code.
- **Severity**: P1
- **Finding**: `[PARALLEL] .claude/agents/{name}.md — T1 auditor has write-capable tool: {tool}. Impact: Parallel execution could corrupt source code. Fix: Remove write tools or restrict to audit output files only.`

**Check 12: Write-agent isolation**
- **Action**: Identify all T3+ agents (write-capable). Check if any command launches
  two or more write-capable agents in parallel on overlapping file patterns.
- **Pass**: No two write-capable agents operate on the same files in parallel.
- **Fail**: Two write agents could modify the same files simultaneously.
- **Severity**: P1
- **Finding**: `[PARALLEL] .claude/commands/{command}.md — Launches write agents {a} and {b} in parallel on overlapping scope {files}. Impact: Race condition and file corruption. Fix: Serialize write agents on shared files.`

**Check 13: Fan-out pattern**
- **Action**: Read `.claude/commands/full-audit.md`. Verify that ALL T1 auditors
  (from the agent-coordination guide) are launched. Check if they are launched in a
  single message (parallel fan-out) or sequentially.
- **Pass**: `/full-audit` launches all T1 auditors in one message.
- **Fail (a)**: Not all T1 auditors are launched.
- **Fail (b)**: Agents are launched sequentially instead of in parallel.
- **Severity**: P2
- **Finding**: `[PARALLEL] .claude/commands/full-audit.md — {Missing T1 auditor "{name}" from launch | Agents launched sequentially instead of parallel fan-out}. Impact: {Incomplete audit coverage | Slow execution}. Fix: {Add missing agent to fan-out | Launch all agents in ONE message}.`

**Check 14: Gather pattern**
- **Action**: Read commands that launch multiple agents (`.claude/commands/full-audit.md`
  and any others found in Check 2). Verify they handle agent failures independently
  (one agent failing should not block others).
- **Pass**: Error handling isolates each agent's execution.
- **Fail**: No error isolation — one agent failure could crash the entire command.
- **Severity**: P2
- **Finding**: `[PARALLEL] .claude/commands/{command}.md — No error isolation for multi-agent launch. Impact: Single agent failure blocks all other agents. Fix: Add per-agent error handling and continue-on-failure logic.`

**Check 15: Resource contention**
- **Action**: Check if any agents write to the same output files, use the same temp
  directories, or bind to the same ports. Specifically check `.claude/audits/` output
  file naming to ensure each agent writes to a unique file.
- **Pass**: Each agent has unique output paths and no shared mutable resources.
- **Fail**: Two agents write to the same output file or share temp resources.
- **Severity**: P1
- **Finding**: `[PARALLEL] {agent_a} + {agent_b} — Both write to {path}. Impact: Output corruption from concurrent writes. Fix: Assign unique output file per agent.`

---

### D. Output Format Consistency (checks 16-19)

**Check 16: YAML preamble schema**
- **Action**: For each T1 auditor, check if its instructions or the `/full-audit`
  command define the expected output preamble. The standard schema requires these fields:
  `agent`, `status`, `timestamp`, `scope`, `findings` (with `critical`, `high`,
  `medium`, `low` subcounts).
- **Pass**: All auditors are instructed to emit the standard YAML preamble schema.
- **Fail**: An auditor's instructions omit required preamble fields.
- **Severity**: P3
- **Finding**: `[FORMAT] .claude/agents/{name}.md — Output instructions missing YAML preamble field: {field}. Impact: /full-audit consolidation cannot parse this agent's report. Fix: Add standard preamble schema to agent instructions.`

**Check 17: Severity alignment**
- **Action**: Grep all agent files for severity level terms. The standard levels are:
  `critical`, `high`, `medium`, `low` (case-insensitive). Check if any agent uses
  non-standard terms like `severe`, `warning`, `info`, `minor`, `major`, `blocker`.
- **Pass**: All agents use only the 4 standard severity levels.
- **Fail**: An agent uses non-standard severity terminology.
- **Severity**: P3
- **Finding**: `[FORMAT] .claude/agents/{name}.md — Uses non-standard severity "{term}" instead of critical/high/medium/low. Impact: Inconsistent severity classification across audit reports. Fix: Normalize to standard 4-level severity scale.`

**Check 18: Finding format**
- **Action**: Grep all agent files for the expected finding format pattern. Findings
  should follow: `[category] file:line -- Description. Impact: ... Fix: ...` or a
  close variant with the key components (category tag, file location, description,
  impact, and fix).
- **Pass**: All agents specify a structured finding format in their instructions.
- **Fail**: An agent has no defined finding format or uses a freeform format.
- **Severity**: P3
- **Finding**: `[FORMAT] .claude/agents/{name}.md — No structured finding format specified. Impact: Findings cannot be machine-parsed for deduplication. Fix: Add finding format: [category] file:line -- Description. Impact. Fix.`

**Check 19: Deduplication readiness**
- **Action**: Check that each agent's finding format includes file:line references.
  Without these, `/full-audit` cannot deduplicate findings across agents.
- **Pass**: All agents include file:line in their finding format.
- **Fail**: An agent's findings lack location references.
- **Severity**: P3
- **Finding**: `[FORMAT] .claude/agents/{name}.md — Finding format lacks file:line references. Impact: /full-audit cannot deduplicate overlapping findings. Fix: Include file:line location in every finding.`

---

### E. Coordination Efficiency (checks 20-25)

**Check 20: Redundant checks**
- **Action**: Compare the checks performed by `/devops-audit` (this command) against
  checks listed in agent definitions. Identify any case where both a command and an
  agent perform the same validation on the same files.
- **Also check**: `/daily-audit` and other audit-related commands for overlap with agent
  audit scopes.
- **Pass**: No command duplicates an agent's check.
- **Fail**: A command performs the same check that an agent already covers.
- **Severity**: P3
- **Finding**: `[EFFICIENCY] .claude/commands/{command}.md + .claude/agents/{agent}.md — Both perform "{check}" validation. Impact: Wasted execution time. Fix: Remove from command and rely on agent, or vice versa.`

**Check 21: Agent-to-module mapping completeness**
- **Action**: Read `.claude/guides/agent-coordination.md` and extract the module-to-agent
  mapping table. Glob all modules under `src/options_arena/*/`. Verify every module
  directory appears in the mapping.
- **Pass**: Every `src/options_arena/` subdirectory has a row in the mapping table.
- **Fail**: A module directory exists but has no mapping entry.
- **Severity**: P2
- **Finding**: `[EFFICIENCY] src/options_arena/{module}/ — Not listed in agent-coordination.md module-to-agent mapping. Impact: No agent is responsible for auditing this module. Fix: Add module row to mapping table.`

**Check 22: Tier classification**
- **Action**: For each agent in `.claude/agents/*.md`, check if it appears in the
  agent-coordination guide under a specific tier (T1-T5). Also verify the tier matches
  the agent's actual tool access (T1 should be read-only, T3+ should be write-capable).
- **Pass**: Every agent has a tier classification consistent with its tool access.
- **Fail (a)**: Agent has no tier classification.
- **Fail (b)**: Agent's tier contradicts its tool access (e.g., T1 with write tools).
- **Severity**: P4
- **Finding**: `[EFFICIENCY] .claude/agents/{name}.md — {No tier classification | Tier {tier} contradicts tool access: has {tools}}. Impact: Unclear execution model. Fix: Assign correct tier in agent-coordination.md.`

**Check 23: Model cost optimization**
- **Action**: For each agent, read its model assignment from the coordination guide.
  Flag cases where an expensive model (opus) is used for tasks that primarily run
  commands and summarize output (should use inherit) or follow explicit checklists
  (should use sonnet).
- **Pass**: Model assignments follow the cost optimization guidelines.
- **Fail**: An agent uses a more expensive model than its task complexity warrants.
- **Severity**: P4
- **Finding**: `[EFFICIENCY] .claude/agents/{name}.md — Uses {model} but task is primarily {command execution | checklist following}. Impact: Unnecessary cost. Fix: Consider downgrading to {recommended_model}.`

**Check 24: Skill-agent coupling**
- **Action**: For each command file, check if it spawns agents. Identify commands that
  spawn agents unnecessarily (the command could perform the check directly with its
  own tools) or commands that spawn too many agents for a simple task.
- **Pass**: Agent spawns are justified by task complexity.
- **Fail**: A command spawns an agent for a task it could do directly.
- **Severity**: P4
- **Finding**: `[EFFICIENCY] .claude/commands/{command}.md — Spawns agent "{name}" for a task achievable with direct tool calls. Impact: Unnecessary overhead. Fix: Perform check directly in command.`

**Check 25: Coverage gaps**
- **Action**: Enumerate all project concern domains: security, async/concurrency, code
  quality, architecture, database, dependencies, pricing/quant, devops/CI, testing,
  documentation, frontend. For each, verify at least one agent or command covers it.
- **Pass**: Every concern domain has coverage.
- **Fail**: A concern domain has no agent or command coverage.
- **Severity**: P2
- **Finding**: `[EFFICIENCY] — No agent or command covers concern domain: "{domain}". Impact: Blind spot in audit coverage. Fix: Create an agent or command for this domain.`

---

### F. Change Detection (checks 26-29)

**Check 26: Agent diff**
- **Action**: Run `git log --oneline -20 -- .claude/agents/` to see recent changes to
  agent definition files. Note added, removed, or modified agents.
- **Pass**: No unexpected changes (informational — always log results).
- **Fail**: N/A — this is informational. Record as P4 if any agents were recently
  added without corresponding coordination guide updates.
- **Severity**: P4
- **Finding**: `[CHANGE] .claude/agents/{name}.md — Recently {added|modified|deleted} ({commit_hash}) but coordination guide not updated. Impact: Documentation drift. Fix: Update agent-coordination.md.`

**Check 27: Skill diff**
- **Action**: Run `git log --oneline -20 -- .claude/commands/` to see recent changes to
  command files. Note added, removed, or modified commands.
- **Pass**: No unexpected changes (informational).
- **Fail**: N/A — informational. Record changes for the report.
- **Severity**: P4
- **Finding**: `[CHANGE] .claude/commands/{name}.md — Recently {added|modified|deleted} ({commit_hash}). Impact: Informational. Fix: Review if changes are intentional.`

**Check 28: Scope drift**
- **Action**: For agents modified in the last 20 commits (from Check 26), read the
  current file and compare its scope keywords against the coordination guide's scope
  description. Flag if the agent's scope has expanded into another agent's territory.
- **Pass**: Modified agents' scopes still match the coordination guide.
- **Fail**: An agent's scope has drifted from its coordination guide description.
- **Severity**: P2
- **Finding**: `[CHANGE] .claude/agents/{name}.md — Scope has drifted: now includes "{concern}" which belongs to {other_agent}. Impact: Scope overlap introduced. Fix: Revert scope expansion or update coordination guide to reassign concern.`

**Check 29: New module coverage**
- **Action**: Run `git log --oneline -20 -- src/options_arena/` and look for new
  directories (modules) added. Cross-reference against the module-to-agent mapping.
- **Pass**: All recently added modules have agent coverage.
- **Fail**: A new module was added without being assigned to any agent.
- **Severity**: P2
- **Finding**: `[CHANGE] src/options_arena/{module}/ — New module added ({commit_hash}) but not in agent-coordination.md mapping. Impact: No audit coverage for new module. Fix: Add module to mapping table.`

---

### G. CI/Config/Hook Checks (checks 30-39)

**Check 30: CI workflow gates**
- **Action**: Read `.github/workflows/ci.yml`. Verify it contains all 4 required gates:
  1. Lint & Format (ruff check + ruff format)
  2. Type Check (mypy --strict)
  3. Python Tests (pytest)
  4. Frontend (vue-tsc + npm build)
- **Pass**: All 4 gates present as separate jobs.
- **Fail**: One or more gates missing.
- **Severity**: P1
- **Finding**: `[CI] .github/workflows/ci.yml — Missing CI gate: "{gate_name}". Impact: {gate_purpose} not enforced on PRs. Fix: Add {gate_name} job to ci.yml.`

**Check 31: Nightly workflow**
- **Action**: Check if `.github/workflows/nightly.yml` exists. If it does, verify it
  runs exhaustive tests (look for `-m exhaustive` or `not exhaustive` negation absence).
- **Pass**: Nightly workflow exists and runs exhaustive tests.
- **Fail (a)**: Nightly workflow does not exist.
- **Fail (b)**: Nightly workflow exists but does not run exhaustive tests.
- **Severity**: P2
- **Finding**: `[CI] .github/workflows/nightly.yml — {Does not exist | Exists but does not run exhaustive tests}. Impact: Exhaustive test coverage not validated regularly. Fix: {Create nightly workflow | Add exhaustive test job}.`

**Check 32: Ruff config drift**
- **Action**: Read `[tool.ruff]` and `[tool.ruff.lint]` sections from `pyproject.toml`.
  Compare against CLAUDE.md spec:
  - `target-version` must be `"py313"`
  - `line-length` must be `99`
  - `select` must include `["E", "F", "I", "UP", "B", "SIM", "ANN"]`
- **Pass**: All ruff settings match CLAUDE.md spec.
- **Fail**: Any setting differs from spec.
- **Severity**: P2
- **Finding**: `[CONFIG] pyproject.toml:[tool.ruff] — Ruff {setting} is "{actual}" but CLAUDE.md specifies "{expected}". Impact: Linting rules inconsistent with project standards. Fix: Update pyproject.toml to match CLAUDE.md.`

**Check 33: Mypy config drift**
- **Action**: Read `[tool.mypy]` section from `pyproject.toml`. Verify:
  - `strict = true`
  - `warn_return_any = true`
  - `warn_unused_configs = true`
- **Pass**: All mypy settings match CLAUDE.md spec.
- **Fail**: Any setting missing or incorrect.
- **Severity**: P2
- **Finding**: `[CONFIG] pyproject.toml:[tool.mypy] — Mypy {setting} is {actual} but should be {expected}. Impact: Type checking not enforcing project standards. Fix: Set {setting} = {expected} in [tool.mypy].`

**Check 34: Test config**
- **Action**: Read `[tool.pytest.ini_options]` from `pyproject.toml`. Verify:
  - `asyncio_mode = "auto"`
  - `timeout` present in addopts (e.g., `--timeout=60`)
  - `markers` list includes at least: `critical`, `exhaustive`, `integration`, `db`
- **Pass**: All test config settings present and correct.
- **Fail**: Missing or incorrect settings.
- **Severity**: P2
- **Finding**: `[CONFIG] pyproject.toml:[tool.pytest.ini_options] — {Setting} {missing | incorrect}: {details}. Impact: Test infrastructure not configured per standards. Fix: {specific fix}.`

**Check 35: Hook integrity**
- **Action**:
  1. Read `.claude/settings.json` and extract all hook registrations (PreToolUse,
     PostToolUse matchers and commands).
  2. For each registered hook command, extract the Python script path and verify the
     file exists using Glob.
  3. For each existing hook script, run `python -c "import ast; ast.parse(open(r'{path}').read())"` via Bash to verify valid Python syntax.
- **Pass**: All registered hooks exist and have valid Python syntax.
- **Fail (a)**: A hook is registered but the script file doesn't exist.
- **Fail (b)**: A hook script exists but has invalid Python syntax.
- **Fail (c)**: A hook script exists but is not registered in settings.json.
- **Severity**: P1
- **Finding**: `[HOOKS] {path} — {Hook registered but file missing | Hook file has syntax error: {error} | Hook file exists but not registered in settings.json}. Impact: {Hook will fail silently | Hook never runs}. Fix: {Create missing file | Fix syntax error | Add registration to settings.json}.`

**Check 36: Version sync**
- **Action**: Extract version from three sources:
  1. `pyproject.toml` — `version = "X.Y.Z"` under `[project]`
  2. `web/package.json` — `"version": "X.Y.Z"`
  3. `.claude/context/progress.md` — `**Version**: X.Y.Z` line
- **Compare all three versions.**
- **Pass**: All three versions are identical.
- **Fail**: Any version mismatch.
- **Severity**: P1
- **Finding**: `[CONFIG] Version mismatch — pyproject.toml={v1}, package.json={v2}, progress.md={v3}. Impact: Inconsistent version reporting across build artifacts. Fix: Sync all three files to the same version.`

**Check 37: Entry point**
- **Action**: Read `[project.scripts]` from `pyproject.toml`. Verify the entry point
  `options-arena = "options_arena.cli:app"` exists.
- **Pass**: Entry point is correctly defined.
- **Fail**: Entry point missing or pointing to wrong module.
- **Severity**: P1
- **Finding**: `[CONFIG] pyproject.toml:[project.scripts] — Entry point "options-arena" {missing | points to "{actual}" instead of "options_arena.cli:app"}. Impact: CLI command will not work after install. Fix: Set options-arena = "options_arena.cli:app".`

**Check 38: Build system**
- **Action**: Read `[build-system]` from `pyproject.toml`. Verify:
  - `build-backend = "hatchling.build"`
  - `requires = ["hatchling"]`
  - `requires-python = ">=3.13"` in `[project]`
- **Pass**: Build system correctly configured.
- **Fail**: Build backend or Python version requirement incorrect.
- **Severity**: P1
- **Finding**: `[CONFIG] pyproject.toml:[build-system] — {setting} is "{actual}" but should be "{expected}". Impact: Package build will use wrong backend or target wrong Python version. Fix: Set {setting} to {expected}.`

**Check 39: Context budget**
- **Action**: Count lines in auto-loaded context files:
  1. `wc -l CLAUDE.md` (max 350 lines)
  2. `wc -l .claude/context/progress.md` (part of @-referenced, max 300 combined)
  3. `wc -l .claude/context/system-patterns.md` (part of @-referenced)
  4. `wc -l .claude/context/tech-context.md` (part of @-referenced)
  5. Count total lines in `.claude/rules/*.md` (max 400 lines)
  6. Sum grand total (max 1050 lines)
- **Pass**: All individual and grand total limits are within budget.
- **Fail**: Any limit exceeded.
- **Severity**: P3
- **Finding**: `[CONFIG] Context budget exceeded — {file}: {actual} lines (max {limit}). Grand total: {total}/1050. Impact: Auto-loaded context consumes excessive attention on all tasks. Fix: Move content to guides or archive completed progress.`

---

## Priority Mapping Reference

Use these severity levels when recording findings:

- **P1 (Critical)**: Write tools on T1 auditors, phantom agent references, parallel
  writers on same files, CI gates broken/missing, version mismatch, broken hooks,
  missing entry point, wrong build system
- **P2 (High)**: Scope overlap between agents, unmapped modules, orphaned agents,
  agents defined but not launched by `/full-audit`, broken fan-out pattern, config
  drift from CLAUDE.md, missing nightly workflow
- **P3 (Medium)**: Inconsistent output formats, stale coordination guide, redundant
  checks, context budget overruns, missing scope descriptions, missing frontmatter
- **P4 (Low)**: Suboptimal model selection, missing tier classification, documentation
  drift, cost optimization suggestions, informational change detection

---

## Phase 2: Dynamic Probes -- Added separately

Phase 2 covers dynamic probes that require network access or running application commands
(CI run status, dependency freshness, dependency security, external service health, test
tier coverage). These checks will be added in a subsequent task.

## Phase 3: Gap Analysis & Report -- Added separately

Phase 3 covers gap analysis and final report generation (missing practices detection,
stale audit reports, broken guide references, health check completeness, and the final
consolidated `AUDIT_DEVOPS.md` report writing). These checks will be added in a
subsequent task.

---

## Report Output

After completing all Phase 1 checks, write the findings to `.claude/audits/AUDIT_DEVOPS.md`
using this format:

```markdown
---
agent: devops-audit
status: COMPLETE
timestamp: {UTC ISO 8601}
scope: agents, commands, CI, config, hooks
phase: 1
findings:
  critical: {count}
  high: {count}
  medium: {count}
  low: {count}
---

# DevOps Audit Report (Phase 1: Static Analysis)

**Timestamp**: {UTC timestamp}
**Checks executed**: 39
**Checks passed**: {count}
**Checks failed**: {count}

## Summary

| Category | Checks | Passed | Failed | P1 | P2 | P3 | P4 |
|----------|--------|--------|--------|----|----|----|----|
| A. Agent Registry | 5 | ... | ... | ... | ... | ... | ... |
| B. Scope Boundaries | 5 | ... | ... | ... | ... | ... | ... |
| C. Parallel Safety | 5 | ... | ... | ... | ... | ... | ... |
| D. Output Format | 4 | ... | ... | ... | ... | ... | ... |
| E. Coordination | 6 | ... | ... | ... | ... | ... | ... |
| F. Change Detection | 4 | ... | ... | ... | ... | ... | ... |
| G. CI/Config/Hooks | 10 | ... | ... | ... | ... | ... | ... |
| **Total** | **39** | **N** | **N** | **N** | **N** | **N** | **N** |

## P1 -- Critical (fix immediately)

{P1 findings or "No P1 findings."}

## P2 -- High (fix before merge)

{P2 findings or "No P2 findings."}

## P3 -- Medium (plan for next sprint)

{P3 findings or "No P3 findings."}

## P4 -- Low (informational)

{P4 findings or "No P4 findings."}

## Phase 2: Dynamic Probes

_Not yet executed. Run `/devops-audit` with Phase 2 enabled._

## Phase 3: Gap Analysis

_Not yet executed. Run `/devops-audit` with Phase 3 enabled._
```

After writing the report, display to the user:
1. The summary table with finding counts by severity
2. If P1 > 0, recommend running `/fix-loop` to address critical issues
3. The path to the full report: `.claude/audits/AUDIT_DEVOPS.md`

</instructions>

<constraints>
1. NEVER modify application source code — this is a read-only audit command
2. Each finding MUST include: category tag, file location, description, impact, and fix
3. Use numbered check identifiers (1-39) for traceability in the report
4. All file reads and searches use only the allowed tools: Read, Glob, Grep, Bash
5. Write is used ONLY for the final report output to `.claude/audits/AUDIT_DEVOPS.md`
6. If a file referenced by a check does not exist, record that as a finding — do not error out
7. If `.claude/guides/agent-coordination.md` does not exist, record it as a P2 finding and
   skip checks that depend on it (checks 5, 8, 9, 21, 22, 23, 28, 29)
8. Bash commands must have timeouts — no unbounded waits
9. Git commands (checks 26-29) should use `--oneline` and limit output with `-20`
10. The report file is overwritten on each run (idempotent), never appended
</constraints>
