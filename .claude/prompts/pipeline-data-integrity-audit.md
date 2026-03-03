<role>
You are a data reliability engineer who has debugged financial
data pipelines at scale. You've seen every way data gets
silently corrupted: NaN propagation, timezone mismatches,
float precision loss in serialization, off-by-one in date
arithmetic, stale cache poisoning, race conditions in async
writes, and schema drift after migrations. You treat every
data path as guilty until proven innocent.
</role>

<context>
{{CLAUDE.md from project root — especially NaN/Inf defense pattern}}
{{src/options_arena/models/ — all Pydantic models with validators}}
{{src/options_arena/scoring/ — normalize, composite, direction, contracts}}
{{src/options_arena/services/ — market_data, options_data, fred, cache}}
{{src/options_arena/data/ — database.py, repository.py}}
{{src/options_arena/scan/pipeline.py — 4-phase orchestration}}
{{src/options_arena/indicators/ — 18+ indicator functions}}
{{data/migrations/ — all .sql files}}

### Known Defense Patterns
- `math.isfinite()` validators on all numeric Pydantic fields
- `_normalize_non_finite()` model validator replaces NaN/Inf with None
- UTC enforcement on all datetime fields
- `Decimal` for prices (constructed from strings, never floats)
- `field_serializer` on Decimal fields for JSON round-trip
- Parameterized SQL (no f-strings)
- `asyncio.gather(return_exceptions=True)` for batch isolation
- Service cache TTL with market-hours awareness
</context>

<task>
Trace every data value from creation to storage to retrieval
and identify paths where silent corruption can occur.

"Silent" is the key word — errors that raise exceptions are
fine (they're caught). The dangerous failures are values that
change meaning without anyone noticing: NaN in a composite
score, a timezone-naive datetime used for earnings proximity,
a float where a Decimal should be, or a cache serving stale
data past its logical validity window.
</task>

<instructions>
### Framework 1 — NaN/Inf Propagation Tracing
NaN is the silent killer in numerical pipelines.
Trace every arithmetic operation that could produce NaN:
- Division by zero (volume=0, open_interest=0, spread=0)
- Log of zero or negative (any log-transformed indicator)
- Square root of negative (volatility calculations)
- scipy.stats functions with degenerate inputs
- numpy operations on all-NaN arrays (nanmean of empty = NaN)

For each source:
- Is there a guard BEFORE the operation?
- If NaN is produced, does it propagate into composite_score?
- Does the `_normalize_non_finite()` validator catch it?
- Is there a test that reproduces this exact NaN path?

### Framework 2 — Serialization Round-Trip Integrity
Data crosses serialization boundaries at:
- Pydantic → JSON → SQLite TEXT → JSON → Pydantic (signals_json)
- Decimal → str → TEXT → str → Decimal (prices)
- datetime → isoformat → TEXT → fromisoformat → datetime
- StrEnum → .value → TEXT → Enum() → StrEnum
- float → JSON number → TEXT → JSON parse → float

For each boundary:
- Is there a test verifying round-trip fidelity?
- Are edge cases covered? (Decimal("0.00"), Decimal("NaN"),
  datetime with microseconds, StrEnum with spaces)
- Does JSON serialization preserve Decimal precision?
  (e.g., Decimal("1.05") → "1.05" → Decimal("1.05") ✓,
  but Decimal("1.05") → 1.05 → "1.0500000000000000444..." ✗)

### Framework 3 — Temporal Integrity
Time is the hardest thing to get right in financial data:
- Are all datetimes UTC? Find any `datetime.now()` without `UTC`
- Is `next_earnings` (date) compared correctly with `started_at` (datetime)?
  (date vs datetime comparison in Python is a TypeError)
- Is DTE computed as `(expiration - today).days` or
  `(expiration - scan_date).days`? Which is correct?
- Does the cache TTL use monotonic time or wall clock?
  (Wall clock can jump backwards due to NTP)
- Are market hours checks timezone-correct?
  (NYSE is ET, not UTC — does the system handle DST?)

### Framework 4 — Cache Coherence
The two-tier cache (in-memory LRU + SQLite) creates
consistency risks:
- Can stale memory cache serve after SQLite cache expires?
- Can SQLite cache serve after the underlying data changes?
  (e.g., option chain cached for 6 hours, but price moved 10%)
- Are cache keys unique enough?
  (If two different API call patterns produce the same key,
  the wrong data is served)
- Is there a stampede problem?
  (Multiple concurrent requests for the same uncached key
  all hit the API simultaneously)

### Framework 5 — Schema Drift & Migration Safety
- Do all `ALTER TABLE ADD COLUMN` migrations have DEFAULT values?
  (Without defaults, existing rows get NULL — is that handled?)
- Are foreign key constraints enforced?
  (`PRAGMA foreign_keys=ON` is set in Database.connect(),
  but is it set BEFORE any queries run?)
- Can a crash between `save_scan_run()` and `save_ticker_scores()`
  leave orphaned scan_runs with no scores?
  (Is there a transaction wrapping both?)
- What happens if migration 010 fails halfway through?
  (`executescript` auto-commits — partial migration is possible)
</instructions>

<constraints>
- For every issue found, rate severity:
  CRITICAL (data corruption in production), HIGH (data loss risk),
  MEDIUM (edge case that could cause incorrect analysis),
  LOW (cosmetic or theoretical)
- For every issue, provide a specific reproduction scenario
- Don't report issues that are already defended against
  (e.g., NaN validators that are working correctly)
- Focus on SILENT failures — loud failures (exceptions, crashes)
  are lower priority because they're visible
</constraints>

<output_format>
1. **Critical Findings** — Issues that could corrupt data in production today
2. **High-Risk Paths** — Data flows with inadequate guards
3. **Serialization Audit** — Round-trip integrity per boundary
4. **Temporal Bugs** — Time/date/timezone issues
5. **Cache Risks** — Staleness and coherence issues
6. **Migration Safety** — Schema evolution risks
7. **Recommended Fixes** — Ordered by severity, with code snippets
</output_format>
