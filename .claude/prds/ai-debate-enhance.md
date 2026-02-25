---
name: ai-debate-enhance
description: Enhance the AI debate system with expanded context, confidence calibration, volatility agent, rebuttal round, multi-ticker debate, and export formats
status: backlog
created: 2026-02-24T21:33:36Z
---

# PRD: AI Debate System Enhancements

## Executive Summary

The Options Arena AI debate system (Phase 9) is functional but operates with significant
information loss and structural limitations. Only 3 of 14 computed indicators reach agents
via `MarketContext`, all Greeks beyond delta are invisible, confidence outputs are uncalibrated,
and the system cannot express non-directional (volatility) trade ideas. Additionally, there
is no way to debate multiple tickers from a scan run or export results for offline analysis.

This PRD defines 11 enhancements across three phases to close these gaps:

- **Phase A** (Data Quality): Expand `MarketContext` with all indicators and Greeks, add
  confidence calibration and data citation rules to prompts, add a strategy decision tree.
- **Phase B** (Structural): Add a Volatility Agent with structured `VolatilityThesis`
  output, add a Bull Rebuttal round, and add pre-debate screening.
- **Phase C** (Usability): Multi-ticker batch debate from scan results, and markdown/PDF
  export of debate results.

**Value proposition**: Transform the debate system from a single-ticker, direction-only tool
with limited context into a comprehensive analysis engine that leverages all computed data,
supports volatility strategies, produces calibrated confidence, and scales across scan runs.

## Problem Statement

### Information Loss in Agent Context

`build_market_context()` maps only `rsi`, `iv_rank`, `iv_percentile`, and `put_call_ratio`
from 14 available indicators. The remaining 10 (ADX, SMA alignment, Bollinger Band width,
ATR%, Stochastic RSI, relative volume, OBV, SuperTrend, Williams %R, Keltner width) are
computed by the scan pipeline but never reach agents. Similarly, only `target_delta` is
exposed from the computed Greeks — gamma, theta, vega, and rho are invisible.

### Uncalibrated Confidence

Agents produce confidence values between 0.0 and 1.0 but have no calibration guidance.
A composite score of 35/100 might produce confidence of 0.8 because the LLM has no anchor.
Without calibration rules tied to quantitative data, confidence values are arbitrary.

### No Volatility Strategy Support

The system is purely directional (bull vs bear). When IV Rank is 85+ (premium is expensive),
the correct trade is often non-directional (iron condor, short strangle). The current system
has no mechanism to express this — it forces every ticker into a directional framework.

### Single-Ticker Limitation

Users must manually run `options-arena debate TICKER` for each ticker. After a scan producing
8+ recommendations, running individual debates is tedious. There is no batch mode.

### No Export Capability

Debate results are displayed in the terminal via Rich panels and persisted to SQLite. There
is no way to generate a portable report (markdown or PDF) for offline analysis or sharing.

## User Stories

### US-1: Rich Agent Context
**As a** user reviewing debate output,
**I want** agents to cite all available indicators and Greeks (not just RSI and delta),
**So that** the analysis is comprehensive and I can trust agents have full context.

**Acceptance criteria:**
- `MarketContext` includes composite score, direction signal, ADX, SMA alignment, BB width,
  ATR%, Stochastic RSI, relative volume, gamma, theta, vega, rho, and contract mid price
- `render_context_block()` displays all new fields (omitting `None` values)
- Agents reference new data points in their arguments

### US-2: Calibrated Confidence
**As a** trader interpreting debate results,
**I want** confidence values to be anchored to quantitative data,
**So that** 0.3 vs 0.7 confidence has consistent meaning across debates.

**Acceptance criteria:**
- All agent prompts include calibration guidelines (0.0-0.2 = weak, etc.)
- Prompts include data anchors (e.g., composite < 40 caps confidence at 0.5)
- Data citation rules require exact values from the context block

### US-3: Volatility Analysis
**As a** trader looking at a high-IV-Rank ticker,
**I want** a Volatility Agent to assess whether IV is mispriced and recommend vol strategies,
**So that** I get non-directional trade ideas when premium selling is optimal.

**Acceptance criteria:**
- New Volatility Agent produces a `VolatilityThesis` with IV assessment, strategy, and strikes
- Agent activates when `enable_volatility_agent=True` in config
- Risk Agent receives vol analysis and incorporates it into the final verdict
- Cyan-colored Rich panel appears in CLI output between Bear and Verdict

### US-4: Bull Rebuttal
**As a** user wanting thorough debate,
**I want** the Bull agent to rebut the Bear's strongest points,
**So that** the Risk Agent has more nuanced input for its verdict.

**Acceptance criteria:**
- Optional rebuttal round (off by default, enabled via config)
- Bull receives Bear's key points and produces a focused 3-5 sentence rebuttal
- Risk Agent receives the rebuttal alongside original arguments
- Green italic Rich panel appears in CLI output

### US-5: Pre-Debate Screening
**As a** user running debate on a low-signal ticker,
**I want** the system to skip AI debate when signals are too weak,
**So that** I don't waste compute on tickers with no conviction.

**Acceptance criteria:**
- `should_debate()` checks direction (skip NEUTRAL) and composite score (skip < threshold)
- Returns a fallback result with explanatory summary
- Threshold configurable via `min_debate_score` (default 30.0)

### US-6: Multi-Ticker Batch Debate
**As a** user who just ran a scan,
**I want to** run `options-arena debate --batch` to debate all top-scored tickers,
**So that** I get comprehensive analysis without running individual commands.

**Acceptance criteria:**
- `--batch` flag debates all tickers from the latest scan run
- `--batch-limit N` caps the number of tickers (default: 5)
- Results displayed sequentially with a summary table at the end
- Each debate is persisted independently
- Graceful handling: one failed ticker doesn't stop the batch

### US-7: Export Debate Results
**As a** user who wants to share or archive analysis,
**I want to** export debate results as markdown or PDF,
**So that** I can review analysis offline or share with others.

**Acceptance criteria:**
- `options-arena debate AAPL --export md` produces `debate_AAPL_2026-02-24.md`
- `options-arena debate AAPL --export pdf` produces `debate_AAPL_2026-02-24.pdf`
- Export includes all agent panels, verdict, disclaimers, and metadata
- Works with `--batch` to produce per-ticker or combined reports
- `--export-dir DIR` controls output location (default: `./reports/`)

## Requirements

### Functional Requirements

#### Phase A: Data Quality & Prompt Enhancement

##### FR-A1: Expand MarketContext — Indicator Summary

Add fields to `MarketContext` in `models/analysis.py`:

```python
# Scoring context (from TickerScore)
composite_score: float = 0.0
direction_signal: SignalDirection = SignalDirection.NEUTRAL

# Key indicators (raw normalized values, 0-100)
adx: float | None = None
sma_alignment: float | None = None
bb_width: float | None = None
atr_pct: float | None = None
stochastic_rsi: float | None = None
relative_volume: float | None = None
```

All new fields have defaults — backward compatible. Existing `MarketContext(...)` calls
still work without modification.

Update `build_market_context()` in `orchestrator.py` to populate from `ticker_score.signals`.
Update `render_context_block()` in `_parsing.py` to display non-None indicators.

##### FR-A2: Expand MarketContext — Contract Greeks

Add fields to `MarketContext` in `models/analysis.py`:

```python
target_gamma: float | None = None
target_theta: float | None = None      # $/day time decay
target_vega: float | None = None       # $/1% IV change
target_rho: float | None = None
contract_mid: Decimal | None = None    # Mid price of recommended contract
```

Populated from `first_contract.greeks` in `build_market_context()`. Add
`field_serializer` for `contract_mid`.

##### FR-A3: Confidence Calibration in All Prompts

Append calibration block to each agent's system prompt constant:

```
Confidence calibration (MUST follow these guidelines):
- 0.0-0.2: Extremely weak case, minimal data support
- 0.2-0.4: Weak case, some data but significant contradictions
- 0.4-0.6: Moderate case, mixed signals in the data
- 0.6-0.8: Strong case, most indicators confirm thesis
- 0.8-1.0: Very strong case, overwhelming data support

Data anchors:
- If composite score < 40: your confidence MUST NOT exceed 0.5
- If composite score > 70 and direction matches: your confidence MUST be at least 0.4
- If RSI contradicts your thesis direction: reduce confidence by at least 0.1
```

##### FR-A4: Strategy Decision Tree for Risk Agent

Append to `RISK_SYSTEM_PROMPT`:

```
Strategy selection decision tree (use this to choose recommended_strategy):
- IF direction is "neutral" AND IV RANK > 70: recommend "iron_condor"
- IF direction is "neutral" AND IV RANK < 30: recommend "straddle"
- IF confidence > 0.7 AND IV RANK < 50: recommend "vertical"
- IF confidence 0.4-0.7 AND IV RANK > 50: recommend "calendar"
- IF confidence < 0.4 OR data is highly conflicting: recommend null (no trade)
- IF both bull_score and bear_score > 6.0: recommend "strangle"
```

##### FR-A5: Data Citation Format in All Prompts

Append to all three agent prompts:

```
Data citation rules (MANDATORY):
- When referencing data, use the EXACT label and value from the context block.
- WRONG: "The RSI is showing strength" or "momentum is bullish"
- RIGHT: "RSI(14): 65.3 is above the 50 midpoint, confirming bullish momentum"
- WRONG: "Volatility is elevated"
- RIGHT: "IV RANK: 85.0 places current IV in the top 15% of its 52-week range"
- Every claim MUST cite at least one specific number from the context.
```

#### Phase B: Structural Enhancements

##### FR-B1: Volatility Agent with VolatilityThesis

**New model** in `models/analysis.py`:

```python
class VolatilityThesis(BaseModel):
    """Structured output from the Volatility Agent."""
    model_config = ConfigDict(frozen=True)

    iv_assessment: str              # "overpriced", "underpriced", "fair"
    iv_rank_interpretation: str     # Human-readable IV rank context
    confidence: float               # 0.0 to 1.0
    recommended_strategy: SpreadType | None = None
    strategy_rationale: str         # Why this strategy fits the IV environment
    target_iv_entry: float | None = None   # IV level that would trigger entry
    target_iv_exit: float | None = None    # IV level that would trigger exit
    suggested_strikes: list[str]    # Specific strike recommendations
    key_vol_factors: list[str]      # Key factors driving the vol assessment
    model_used: str
```

**New agent** in `agents/volatility.py`:

- Module-level `Agent[DebateDeps, VolatilityThesis]` with `output_type=VolatilityThesis`
- Dynamic system prompt (receives bull + bear arguments)
- Same `clean_think_tags`-style output validator pattern
- Uses `<<<VOL_CONTEXT>>>` delimiters for opponent arguments
- Focuses on IV Rank, IV Percentile, ATM IV 30D, and historical vol analysis

**Config**: `enable_volatility_agent: bool = False` on `DebateConfig` (opt-in).

**Orchestrator flow**: Bull -> Bear -> **Volatility** -> Risk (when enabled).

**DebateDeps expansion**: Add `vol_response: VolatilityThesis | None = None`.

**DebateResult expansion**: Add `vol_response: VolatilityThesis | None = None`.

**Risk agent prompt update**: Inject `<<<VOL_CASE>>>...<<<END_VOL_CASE>>>` when present.

**CLI rendering**: Cyan-bordered Rich panel between Bear and Verdict.

##### FR-B2: Bull Rebuttal Round

**Flow change**: Bull -> Bear -> **Bull Rebuttal** -> [Volatility] -> Risk

**Bull agent refactoring**: Convert system prompt to `dynamic=True`. When
`ctx.deps.bear_counter_argument` is set, inject rebuttal instructions:

```python
BULL_REBUTTAL_PROMPT = """You are the bullish analyst. The bear has countered your argument.
Provide a BRIEF rebuttal addressing the bear's strongest 2-3 points.
Do not repeat your original argument -- focus only on defending against the bear's counter.
Keep this concise (3-5 sentences)."""
```

Rebuttal injects bear's `key_points` only (not full argument) to save tokens (~100 vs ~400).

**Config**: `enable_rebuttal: bool = False` on `DebateConfig`.

**DebateDeps expansion**: Add `bear_counter_argument: str | None = None`.

**DebateResult expansion**: Add `bull_rebuttal: AgentResponse | None = None`.

**Risk agent update**: `<<<BULL_REBUTTAL>>>...<<<END_BULL_REBUTTAL>>>` when present.

**CLI rendering**: Green-bordered italic Rich panel between Bear and Verdict/Vol panels.

##### FR-B3: Pre-Debate Screening

New function in `orchestrator.py`:

```python
def should_debate(ticker_score: TickerScore, config: DebateConfig) -> bool:
    """Return False if signal is too weak for meaningful debate."""
    if ticker_score.direction == SignalDirection.NEUTRAL:
        return False
    if ticker_score.composite_score < config.min_debate_score:
        return False
    return True
```

Called at the top of `run_debate()`. When False, returns a special fallback with
`summary="Signal too weak for meaningful debate..."` and `is_fallback=True`.

**Config additions** to `DebateConfig`:
- `min_debate_score: float = 30.0` with validator: `>= 0.0`, `<= 100.0`, `math.isfinite()`

#### Phase C: Usability Enhancements

##### FR-C1: Multi-Ticker Batch Debate

New CLI flags on the `debate` command:

```python
@app.command()
def debate(
    ticker: str | None = typer.Argument(None, help="Ticker symbol (omit for batch)"),
    batch: bool = typer.Option(False, "--batch", help="Debate all top tickers from latest scan"),
    batch_limit: int = typer.Option(5, "--batch-limit", help="Max tickers in batch mode"),
    # ... existing flags ...
) -> None:
```

**Batch flow**:
1. Load latest `ScanRun` from repository
2. Load `TickerScore` records ordered by `composite_score` DESC
3. For each ticker (up to `batch_limit`):
   a. Fetch live `Quote` and `TickerInfo` from services
   b. Fetch option contracts from services
   c. Run `recommend_contracts()` for Greeks computation
   d. Call `run_debate()`
   e. Render result (individual panels)
4. Render summary table: ticker, direction, confidence, strategy, fallback?
5. Each debate persisted independently

**Error isolation**: One failed ticker logs a warning and continues to the next. Final
summary shows success/failure per ticker.

**Requires**: Recent scan run in database. If none, error: "No scan data. Run: options-arena scan"

##### FR-C2: Export Debate Results

New CLI flags on the `debate` command:

```python
export: str | None = typer.Option(None, "--export", help="Export format: md or pdf"),
export_dir: str = typer.Option("./reports", "--export-dir", help="Export directory"),
```

**New module**: `reporting/debate_export.py` (in the existing `reporting/` directory)

```python
def export_debate_markdown(result: DebateResult, path: Path) -> Path:
    """Export debate result as structured markdown."""

def export_debate_pdf(result: DebateResult, path: Path) -> Path:
    """Export debate result as PDF (requires weasyprint or equivalent)."""
```

**Markdown export format**:
```markdown
# Options Arena Debate Report: {TICKER}
**Date**: {date} | **Duration**: {duration}ms | **Model**: {model}

## Bull Case (Confidence: {confidence})
{argument}
### Key Points
- {point1}
- {point2}

## Bear Case (Confidence: {confidence})
...

## Volatility Assessment (if present)
...

## Verdict
**Direction**: {direction} | **Confidence**: {confidence}
**Recommended Strategy**: {strategy}
{summary}

### Risk Assessment
{risk_assessment}

---
*Disclaimer: This is AI-generated analysis for educational purposes only...*
```

**PDF support**: Use `weasyprint` (optional dependency). If not installed, warn and skip
PDF export. Add to `[project.optional-dependencies]` in `pyproject.toml`:
```toml
[project.optional-dependencies]
pdf = ["weasyprint>=63.0"]
```

**Batch export**: With `--batch --export md`, produces one file per ticker plus a combined
summary file: `debate_batch_2026-02-24.md`.

### Non-Functional Requirements

#### NFR-1: Performance
- Phase A changes add ~200 tokens to agent input — still well within 8192 ctx limit
- Phase B worst case (4 agents + rebuttal): ~2200 input tokens for Risk agent — within limit
- Batch debate: sequential execution per ticker (Ollama is single-threaded)
- Export: < 1s for markdown, < 5s for PDF per ticker

#### NFR-2: Backward Compatibility
- All new `MarketContext` fields have defaults — zero breaking changes
- All new `DebateConfig` fields have defaults — `AppSettings()` still valid
- `DebateResult` expansion uses `| None = None` — existing code unaffected
- Volatility agent and rebuttal are opt-in (disabled by default)

#### NFR-3: Testability
- All new agents testable via PydanticAI `TestModel`
- `should_debate()` is a pure function — easy to unit test
- Batch debate testable with mocked repository and services
- Export functions are pure (model -> file) — test with temp directories

#### NFR-4: Token Budget Analysis

| Phase | Risk Agent Input Tokens | Within 8192? |
|-------|------------------------|--------------|
| Current | ~950-1350 | Yes |
| After Phase A (expanded context) | ~1200-1500 | Yes |
| After Phase B (4 agents + rebuttal) | ~1800-2200 | Yes |

Risk agent is most token-heavy: receives bull + bear + rebuttal + vol arguments. At ~2200
input tokens, still well under the 8192 limit.

## Success Criteria

- [ ] `build_market_context()` populates all 13 new `MarketContext` fields
- [ ] `render_context_block()` displays all non-None fields
- [ ] Agent prompts include calibration + citation + strategy rules
- [ ] `VolatilityThesis` model validates correctly (frozen, confidence [0,1])
- [ ] Volatility Agent produces valid `VolatilityThesis` via `TestModel`
- [ ] Bull Rebuttal round works when enabled, skipped when disabled
- [ ] `should_debate()` screens NEUTRAL and low-score tickers
- [ ] `options-arena debate --batch --batch-limit 3` debates top 3 tickers from latest scan
- [ ] `options-arena debate AAPL --export md` produces valid markdown file
- [ ] All existing 1262 tests still pass (zero regressions)
- [ ] ~60+ new tests for all enhancements
- [ ] `ruff check . --fix && ruff format .` — clean
- [ ] `mypy src/ --strict` — clean

## Constraints & Assumptions

### Assumptions
- Ollama/Groq infrastructure unchanged — same model configuration, same provider dispatch
- 8192 context window sufficient even with expanded context (verified via token budget)
- `VolatilityThesis` is simple enough for Llama 3.1 8B to produce reliably
- Batch debate runs sequentially (Ollama single-threaded, Groq has API rate limits)
- `weasyprint` is acceptable as an optional dependency for PDF export

### Technical Constraints
- All new `MarketContext` fields must have defaults (backward compatibility)
- Volatility Agent and rebuttal must be opt-in (disabled by default)
- Export module goes in `reporting/` per architecture boundaries
- No new external API dependencies (all data already computed by scan pipeline)
- Windows compatibility: no `loop.add_signal_handler()`, use `signal.signal()`

## Out of Scope

- Multi-round debate beyond single rebuttal (multiple rounds deferred)
- Real-time streaming of agent progress (Phase 11 / web UI)
- Automated debate triggers (user must manually invoke)
- Additional LLM providers beyond Ollama/Groq (Anthropic/OpenAI deferred)
- Web-based report viewer
- Strategy backtesting from debate recommendations
- Options chain visualization in export

## Dependencies

### Internal
- **Scan pipeline** (Phase 7): `TickerScore` with `IndicatorSignals` and recommended contracts
- **Data layer** (Phase 6): `Repository` for persistence, `Database` for batch query
- **Models** (Phase 1): `MarketContext`, `AgentResponse`, `TradeThesis`, enums
- **CLI** (Phase 8): `debate` command infrastructure
- **AI Debate** (Phase 9): Orchestrator, agent framework, `DebateDeps`, `DebateResult`
- **Services** (Phase 5): `OptionsDataService`, `MarketDataService` for batch debate

### External
- **pydantic-ai** (`>= 1.62.0`): Agent framework — already installed
- **ollama** (`>= 0.6.1`): Local LLM — already installed
- **weasyprint** (`>= 63.0`): PDF export — new optional dependency (Phase C only)

## Files To Create

| File | Phase | Purpose | Lines (est.) |
|------|-------|---------|-------------|
| `agents/volatility.py` | B | Volatility agent + prompt + validator | ~120 |
| `reporting/debate_export.py` | C | Markdown + PDF export functions | ~200 |
| `reporting/__init__.py` | C | Re-exports with `__all__` | ~10 |
| `reporting/CLAUDE.md` | C | Module conventions | ~50 |
| `tests/unit/agents/test_volatility.py` | B | Volatility agent tests | ~100 |
| `tests/unit/reporting/test_debate_export.py` | C | Export tests | ~80 |

## Files To Modify

| File | Phase | Changes |
|------|-------|---------|
| `models/analysis.py` | A | ~13 new optional fields on `MarketContext`, new `VolatilityThesis` model |
| `models/__init__.py` | A, B | Re-export `VolatilityThesis` |
| `models/config.py` | B | 3 new fields on `DebateConfig` + validators |
| `agents/_parsing.py` | A, B | Expand `render_context_block()`, expand `DebateDeps` and `DebateResult` |
| `agents/orchestrator.py` | A, B, C | Expand `build_market_context()`, add vol/rebuttal phases, `should_debate()` |
| `agents/bull.py` | A, B | Enhanced prompt, convert to `dynamic=True` for rebuttal |
| `agents/bear.py` | A | Enhanced prompt (calibration + citation) |
| `agents/risk.py` | A, B | Enhanced prompt, receive vol + rebuttal args |
| `agents/__init__.py` | B | Re-export volatility agent |
| `cli/commands.py` | B, C | `--batch`, `--batch-limit`, `--export`, `--export-dir` flags |
| `cli/rendering.py` | B | Volatility panel + rebuttal panel |

## Existing Code To Reuse (Not Modify)

| Function | Location | Used By |
|----------|----------|---------|
| `OptionsDataService` | `services/options_data.py` | C1 (batch debate fetches contracts) |
| `MarketDataService` | `services/market_data.py` | C1 (batch debate fetches quotes + info) |
| `FredService.fetch_risk_free_rate()` | `services/fred.py` | C1 (batch debate needs risk-free rate) |
| `recommend_contracts()` | `scoring/contracts.py` | C1 (batch debate computes Greeks) |
| `strip_think_tags()` | `agents/_parsing.py` | B1 (volatility agent validator) |
| `build_debate_model()` | `agents/model_config.py` | Unchanged, used by all agents |

## Implementation Phases

### Phase A: Data Quality (4 issues, ~2 days)
1. **FR-A1 + FR-A2**: MarketContext expansion (model + orchestrator + parsing)
2. **FR-A3**: Confidence calibration in all prompts
3. **FR-A4**: Strategy decision tree for Risk agent
4. **FR-A5**: Data citation rules in all prompts

Issues 2-4 can be parallelized (independent prompt changes). Issue 1 is the foundation.

### Phase B: Structural Enhancements (4 issues, ~3 days)
5. **FR-B3**: Pre-debate screening (orchestrator + config) — simple gate, do first
6. **FR-B1**: Volatility Agent (new model + agent + orchestrator + rendering)
7. **FR-B2**: Bull Rebuttal (bull.py refactor + orchestrator + rendering)
8. **Tests**: Unit tests for all Phase B features

Issue 5 is independent. Issues 6-7 modify the orchestrator and should be sequential.

### Phase C: Usability (3 issues, ~2 days)
9. **FR-C1**: Multi-ticker batch debate (CLI + orchestrator loop)
10. **FR-C2**: Export debate results (reporting module + CLI flags)
11. **Tests**: Unit tests for batch and export

Issues 9-10 are independent and can be parallelized.

## Testing Strategy

### New Unit Tests (~60+ tests)

**MarketContext expansion** (~8 tests):
- Construct with all new fields populated
- Construct with all new fields at defaults (backward compat)
- `render_context_block()` includes non-None indicators, omits None
- `contract_mid` Decimal serialization round-trip

**VolatilityThesis model** (~8 tests):
- Construction with valid data
- Frozen immutability
- Confidence [0.0, 1.0] validation
- JSON round-trip

**Volatility Agent** (~10 tests, using TestModel):
- Valid `VolatilityThesis` output
- Think-tag stripping on string fields
- Dynamic prompt includes opponent arguments when set
- Empty contracts handled gracefully

**Bull Rebuttal** (~8 tests):
- Rebuttal mode: dynamic prompt includes bear counter-argument
- Non-rebuttal mode: static prompt (backward compat)
- Rebuttal output is valid `AgentResponse`
- Token savings: key_points only (not full argument)

**Pre-debate screening** (~6 tests):
- NEUTRAL direction returns False
- Low composite score returns False
- Above threshold returns True
- Threshold edge cases (exactly at boundary)

**Batch debate** (~10 tests):
- Happy path: 3 tickers debated, all succeed
- Partial failure: 1 ticker fails, others continue
- No scan data: error message
- `--batch-limit` respected

**Export** (~10 tests):
- Markdown export contains all sections
- Markdown export with volatility thesis
- Markdown export with fallback result
- PDF export with `weasyprint` installed (skip if missing)
- Export directory creation

### Existing Tests (No Regressions)
- All 1262 existing tests must still pass
- `MarketContext` backward compatibility: existing construction calls unchanged
- `DebateResult` backward compatibility: existing field access unchanged
