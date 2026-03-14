---
name: mathematical-computation-audit
description: Repeatable hybrid audit framework — deterministic tests (correctness, stability, performance) plus agent-driven discovery — covering all 66+ mathematical functions with CI gate
status: backlog
created: 2026-03-14T14:14:37Z
---

# PRD: mathematical-computation-audit

## Executive Summary

Build a repeatable mathematical computation audit framework that validates all 66+ mathematical functions in Options Arena against academic references and QuantLib cross-validation, stress-tests numerical stability with property-based testing, detects performance regressions via benchmarking, and uses the quant-analyst agent as a discovery layer to surface issues that deterministic tests miss. Findings from agent discovery get codified into the permanent test suite. The audit runs in CI as a gate.

## Problem Statement

### What problem are we solving?

Options Arena contains 66+ mathematical functions spanning BSM/BAW pricing, 40+ technical indicators, composite scoring, and log-odds confidence pooling. These functions have academic citations and NaN/Inf guards, but there is no systematic verification that:

1. Formula implementations actually match their cited papers (a transcription error in BAW critical price Newton-Raphson would silently produce wrong prices)
2. Edge cases are exhaustively covered (what happens at S=0.01, σ=4.99, T=1 hour?)
3. Performance hasn't regressed as the codebase evolves

The existing test suite covers happy paths and some edge cases, but lacks cross-validation against an independent oracle (QuantLib), property-based exhaustive input testing (Hypothesis), and performance regression detection.

### Why is this important now?

The AI agency evolution will add auto-tuned weights and self-improving prompts based on outcome data. If the underlying math is wrong, the feedback loop amplifies errors — the system "learns" from incorrect computations. A comprehensive audit before the agency evolution ensures the mathematical foundation is sound.

Additionally, the native quant epic (2026-03-13) just added second-order Greeks, HV estimators, and vol surface analysis — new mathematical surface area that hasn't been cross-validated yet.

## User Stories

- **As a developer**, I want to run `options-arena audit math` and see a report showing which functions pass correctness/stability/performance checks, so I can identify and fix mathematical issues before they affect recommendations.
  - *Acceptance*: Command produces a markdown report covering all 66+ functions. Failures show expected vs actual with tolerance.

- **As a CI pipeline**, I want mathematical correctness and stability tests to run automatically on every PR, so formula regressions are caught before merge.
  - *Acceptance*: `pytest -m "audit_correctness or audit_stability"` runs in CI. Failures block merge.

- **As a quant reviewer**, I want to run `/math-audit` to have the quant-analyst agent read each formula's source code, cross-reference the cited paper, and flag potential issues, so I can discover problems that deterministic tests miss.
  - *Acceptance*: Agent produces a findings report with severity levels. CRITICAL/WARNING findings include proposed test cases.

- **As a maintainer**, I want performance benchmarks to flag when a function slows down by >20%, so I catch performance regressions before they affect scan pipeline throughput.
  - *Acceptance*: `pytest -m audit_performance` compares against stored baselines. Weekly CI run.

## Architecture & Design

### Chosen Approach: Hybrid B+C

Three deterministic test layers (correctness, stability, performance) form the permanent infrastructure. The quant-analyst agent serves as a discovery accelerator — it finds issues that get codified into the deterministic suite. Agent discovers, tests enshrine.

### Module Changes

| Module | Change | Boundary Compliance |
|--------|--------|-------------------|
| `tests/audit/` | New directory: correctness/, stability/, performance/, reference_data/ | Yes — tests only |
| `tools/` | `math_audit_report.py` (report generator), `generate_quantlib_baselines.py` (baseline script) | Yes — tooling |
| `cli/` | New `audit` subcommand group with `math` command | Yes — top of stack |
| `.claude/agents/` | Enhanced quant-analyst prompt for `/math-audit` skill | Yes — agent config |

No changes to `pricing/`, `indicators/`, `scoring/`, or `agents/` source code. This is a read-only audit framework.

### Data Models

```python
class AuditSeverity(StrEnum):
    CRITICAL = "critical"    # Formula produces wrong results
    WARNING = "warning"      # Edge case not handled, silent degradation
    INFO = "info"            # Approximation documented but unquantified

class AuditLayer(StrEnum):
    CORRECTNESS = "correctness"
    STABILITY = "stability"
    PERFORMANCE = "performance"
    DISCOVERY = "discovery"   # Agent findings

class AuditFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    layer: AuditLayer
    severity: AuditSeverity
    function_name: str
    module_path: str
    description: str
    expected: str | None = None
    actual: str | None = None
    tolerance: str | None = None
    proposed_test: str | None = None  # Agent-proposed test code

class AuditReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime  # UTC validated
    total_functions: int
    layers: dict[str, AuditLayerSummary]
    findings: list[AuditFinding]

class AuditLayerSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    tests_run: int
    passed: int
    failed: int
    coverage_pct: float  # Functions covered / total functions
```

### Core Logic

#### Layer 1 — Correctness (`pytest -m audit_correctness`)

Each function tested against two reference sources:

**Academic known-values** stored in `tests/audit/reference_data/pricing_known_values.json`:
```json
{
  "bsm_call": [
    {"S": 100, "K": 100, "T": 1.0, "r": 0.05, "q": 0, "sigma": 0.2,
     "expected": 10.4506, "source": "Hull Table 15.3", "tol_abs": 0.01}
  ],
  "american_call": [
    {"S": 100, "K": 100, "T": 0.25, "r": 0.08, "q": 0.04, "sigma": 0.2,
     "expected": 5.272, "source": "BAW 1987 Table 1", "tol_abs": 0.01}
  ]
}
```

**QuantLib cross-validation** stored in `tests/audit/reference_data/quantlib_baselines.json`:
- Pre-generated by `tools/generate_quantlib_baselines.py` (runs QuantLib, dumps results)
- QuantLib NOT required at test runtime — only for regenerating baselines
- Covers: prices, all Greeks (1st + 2nd order), IV round-trips
- 100+ parameter combinations per function (grid over S, K, T, r, q, σ)

Tolerances:

| Category | Absolute | Relative |
|----------|----------|----------|
| Option prices | 0.01 | 0.1% |
| Delta, Gamma | 0.001 | 0.5% |
| Theta, Vega, Rho | 0.01 | 1.0% |
| Vanna, Charm, Vomma | 0.01 | 2.0% |
| IV round-trip | 0.0001 | 0.1% |
| Indicators (vs textbook) | 0.01 | 0.5% |
| Composite score | 0.1 | 1.0% |
| Log-odds pooling | 0.001 | 0.1% |

#### Layer 2 — Stability (`pytest -m audit_stability`)

**Hypothesis property-based tests**: For each function, define a Hypothesis strategy that generates valid inputs within domain bounds. Assert:
- Output is finite (no NaN/Inf leakage)
- Output is within theoretical range (e.g., 0 ≤ delta ≤ 1 for calls, vega ≥ 0)
- Monotonicity where theory requires (call price increases with S, put price decreases with S)
- Put-call parity holds for BSM within tolerance

**Extreme input battery** (predefined, not random):

| Parameter | Stress Values |
|-----------|---------------|
| S (spot) | 0.01, 0.1, 1, 100, 10000, 100000 |
| K (strike) | 0.01, 0.1, 1, 100, 10000, 100000 |
| T (time) | 1/365/24 (1hr), 1/365 (1day), 7/365 (1wk), 1.0, 5.0, 10.0 |
| σ (vol) | 0.001, 0.01, 0.05, 0.5, 1.0, 3.0, 4.99 |
| r (rate) | -0.05, 0, 0.001, 0.05, 0.15, 0.50 |
| Moneyness | S/K = 0.01, 0.5, 0.95, 1.0, 1.05, 2.0, 10.0 |

**NaN/Inf injection**: For every function, inject `float('nan')` and `float('inf')` into each input position. Verify either:
- Clean `ValueError` raised, OR
- Documented fallback returned (e.g., `iv_rank` returns 50.0 on NaN input)
- NEVER silent NaN propagation to output

Hypothesis profiles:
- `ci`: 100 examples per test (< 30s total)
- `thorough`: 1000 examples per test (for manual runs)

#### Layer 3 — Performance (`pytest -m audit_performance`)

**pytest-benchmark** for each function with representative inputs (ATM, 30 DTE, σ=0.25).

Baseline stored in `tests/audit/reference_data/benchmarks/`. CI compares via `--benchmark-compare` and flags >20% regression.

Groups: `pricing` (14 functions), `indicators` (40+ functions), `scoring` (7 functions), `orchestration` (5 functions).

Weekly CI schedule (not per-commit — hardware variance makes per-commit noisy).

#### Agent Discovery Layer

**Skill: `/math-audit`** invokes `quant-analyst` agent with structured prompt:

1. Read each mathematical function in `pricing/`, `indicators/`, `scoring/`, `agents/orchestrator.py`
2. For each function:
   - Verify the formula matches the cited academic reference
   - Check for common transcription errors (sign flips, missing terms, wrong constants)
   - Identify undocumented approximations or assumptions
   - Check if edge case handling matches the paper's boundary conditions
3. Produce findings report with severity and proposed test cases
4. Human reviews findings → confirmed issues become new tests in `tests/audit/`

The agent is non-deterministic and requires LLM access. It is NOT a CI gate — it's a discovery tool run on-demand by developers.

### Feedback Loop

```
Developer changes a formula
  → CI runs correctness + stability (deterministic, fast)
  → If pass: merge
  → Periodically: developer runs /math-audit (agent discovery)
  → Agent finds issue → developer reviews
  → Confirmed → new test added to tests/audit/
  → CI now catches that class of error permanently
```

## Requirements

### Functional Requirements

1. `options-arena audit math` runs all three layers and produces a markdown report
2. `--correctness`, `--stability`, `--performance` flags run individual layers
3. `--report` generates `docs/math-audit-report.md` from latest test results
4. `--discover` invokes quant-analyst agent for formula review
5. Reference data in JSON fixtures — no QuantLib required at test runtime
6. `tools/generate_quantlib_baselines.py` regenerates QuantLib baselines (dev-only)
7. Every mathematical function (66+) has at least one test in each layer
8. Coverage meta-test scans source modules and asserts audit coverage completeness
9. Report includes: summary table, per-function status, findings with severity, performance comparison
10. Agent discovery findings include proposed test code for human review

### Non-Functional Requirements

1. Correctness + stability layers complete in <60s (CI-compatible)
2. Performance layer completes in <120s
3. Agent discovery completes in <5 minutes per module
4. No new runtime dependencies (QuantLib, Hypothesis, pytest-benchmark are dev-only)
5. Windows compatible (no Unix-only test infrastructure)
6. Report is human-readable markdown with tables
7. Baselines are version-controlled (reproducible across environments)

## API / CLI Surface

```bash
# Full audit (all 3 deterministic layers + report)
options-arena audit math

# Individual layers
options-arena audit math --correctness
options-arena audit math --stability
options-arena audit math --performance

# Report generation only (from cached test results)
options-arena audit math --report

# Agent discovery mode (requires LLM)
options-arena audit math --discover

# Regenerate QuantLib baselines (dev only, requires QuantLib installed)
python tools/generate_quantlib_baselines.py
```

No API endpoints. No frontend components. This is a developer/CI tool.

## Testing Strategy

- **Self-testing meta-test**: `tests/audit/conftest.py` scans `pricing/`, `indicators/`, `scoring/`, `agents/orchestrator.py` for mathematical functions (by decorator, naming convention, or explicit registry) and asserts each has corresponding tests in all three layers
- **Report generation test**: `tools/math_audit_report.py` tested with mock pytest JSON output to verify report formatting
- **Baseline regeneration test**: Verify `generate_quantlib_baselines.py` produces valid JSON matching expected schema
- **Agent prompt test**: Verify `/math-audit` skill produces structured findings (TestModel)

## Success Criteria

1. All 66+ mathematical functions have correctness tests with academic + QuantLib references
2. Zero silent NaN propagation discovered by stability layer (all inputs produce finite output or clean error)
3. Performance baselines established for all functions with <5% variance between runs
4. Agent discovery surfaces at least 3 findings not caught by deterministic tests on first run
5. CI gate blocks PRs that introduce correctness or stability regressions
6. Report generation completes in <5s and produces valid markdown

## Constraints & Assumptions

- **QuantLib availability**: QuantLib wheels exist for Python 3.13 on Windows. If not, baseline generation runs in a Docker container or CI environment. Tests never require QuantLib at runtime.
- **Hypothesis determinism**: Hypothesis uses a seed database (`.hypothesis/`) for reproducibility. Committed to repo for CI consistency.
- **Performance baseline variance**: pytest-benchmark uses statistical comparison (min of N rounds). Baselines stored per-platform if CI runners differ from dev machines.
- **Agent findings are advisory**: Agent discovery is non-blocking. Findings require human review before becoming tests. The agent cannot modify the test suite directly.

## Out of Scope

- Modifying any mathematical function (this is an audit, not a fix)
- Web UI for audit results (CLI + markdown report only)
- Historical audit comparison (no tracking of audit results over time — just current state)
- Auditing non-mathematical code (services, CLI, API, frontend)
- Real-time monitoring of mathematical accuracy in production

## Dependencies

### Internal
- All mathematical modules: `pricing/`, `indicators/`, `scoring/`, `agents/orchestrator.py`
- Existing test infrastructure: `conftest.py`, pytest markers, `uv run pytest`
- `quant-analyst` agent (for discovery layer)
- `cli/` for `audit` subcommand registration

### External (dev-only)
| Package | Purpose | Install |
|---------|---------|---------|
| `QuantLib` | Cross-validation oracle (baseline generation only) | `uv add --dev QuantLib` |
| `hypothesis` | Property-based testing for stability layer | `uv add --dev hypothesis` |
| `pytest-benchmark` | Performance regression detection | `uv add --dev pytest-benchmark` |

### Implementation Phasing

| Epic | Scope | Est. Issues | Dependencies |
|------|-------|-------------|-------------|
| 1: Reference data + correctness tests | JSON fixtures (academic + QuantLib), correctness tests for all 66+ functions, QuantLib baseline generator | 4-5 | None |
| 2: Stability tests | Hypothesis strategies, extreme input battery, NaN/Inf injection for all 66+ functions | 3-4 | None (parallel with Epic 1) |
| 3: Performance benchmarks | pytest-benchmark setup, baselines for all functions, CI weekly schedule | 2-3 | Epic 1 (needs function inventory) |
| 4: CLI + report + agent discovery | `audit math` CLI command, report generator, `/math-audit` skill, coverage meta-test | 3-4 | Epics 1-3 |

**Total: ~12-16 issues across 4 epics.** Epics 1 and 2 can run in parallel.
