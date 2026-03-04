# Analysis: #251 — Orchestrator Wiring V2

## Single stream — wire existing v2 local variables into DebateResult + persistence

## Key Files
| File | What to change |
|------|---------------|
| `src/options_arena/agents/orchestrator.py` | _run_v2_agents() populates 5 new DebateResult fields; _persist_result() serializes v2 JSON to save_debate() |
| `tests/unit/agents/test_orchestrator_v2.py` | NEW — 5 tests |

## Key Points
- Local variables flow_output, fundamental_output, risk_v2_output, contrarian_output ALREADY EXIST
- Just pass them through to DebateResult constructor and save_debate()
- _persist_result(): flow_json=result.flow_response.model_dump_json() if result.flow_response else None
- Set debate_protocol="v2" on v2 debate results
- save_debate() now accepts: flow_thesis, fundamental_thesis, risk_v2_assessment, contrarian_thesis, debate_protocol params (from #250)
