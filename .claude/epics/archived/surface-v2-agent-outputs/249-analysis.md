# Analysis: #249 — DebateResult Model Extension + Migration

## Ready: YES (no dependencies)

## Key Files

| File | Line(s) | What to change |
|------|---------|---------------|
| `src/options_arena/agents/_parsing.py` | 334-353 | Add 5 fields to `DebateResult` |
| `data/migrations/019_add_v2_agent_columns.sql` | NEW | 5 ALTER TABLE ADD COLUMN |
| `tests/test_agents/test_parsing_v2.py` | NEW | 5 model tests |
| `tests/test_data/test_migration_019.py` | NEW | 2 migration tests |

## CORRECTION: Migration is 019, NOT 018
- Migration 018 (`018_add_scan_source.sql`) already exists from epic 19
- This epic's migration must be **019**

## DebateResult Current Shape (line 334)
```python
class DebateResult(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    context: MarketContext
    bull_response: AgentResponse
    bear_response: AgentResponse
    thesis: TradeThesis
    total_usage: RunUsage
    duration_ms: int
    is_fallback: bool
    bull_rebuttal: AgentResponse | None = None
    vol_response: VolatilityThesis | None = None
    citation_density: float = 0.0
```

## 5 New Fields to Add
1. `flow_response: FlowThesis | None = None`
2. `fundamental_response: FundamentalThesis | None = None`
3. `risk_v2_response: RiskAssessment | None = None`
4. `contrarian_response: ContrarianThesis | None = None`
5. `debate_protocol: str = "v1"`

## Imports Already Present
Lines 19-30 already import FlowThesis, FundamentalThesis, RiskAssessment, ContrarianThesis.

## Migration 019 Columns
```sql
ALTER TABLE ai_theses ADD COLUMN flow_json TEXT;
ALTER TABLE ai_theses ADD COLUMN fundamental_json TEXT;
ALTER TABLE ai_theses ADD COLUMN risk_v2_json TEXT;
ALTER TABLE ai_theses ADD COLUMN contrarian_json TEXT;
ALTER TABLE ai_theses ADD COLUMN debate_protocol TEXT DEFAULT 'v1';
```

## Single Stream — no parallelism needed
