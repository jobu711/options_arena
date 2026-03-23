---
title: "Groq rejects Pydantic Decimal JSON schema pattern (negative lookahead)"
date: 2026-03-22
module: options_arena.models.recommendation
problem_type: pydantic_pattern
severity: critical
symptoms:
  - "Synthesis agent fails with 400 error from Groq"
  - "Error: 'pattern' does not validate ... is not valid 'regex'"
  - "PositionRecommendation structured output rejected by Groq"
  - "Desk agents succeed but synthesis always falls back"
tags:
  - groq
  - decimal
  - json-schema
  - pydantic-ai
  - structured-output
  - synthesis-agent
  - llm-compatibility
root_cause: "Pydantic generates a regex pattern with negative lookahead for Decimal fields that Groq's JSON schema validator rejects"
---

## Problem

The synthesis agent failed with a 400 error from Groq when producing `PositionRecommendation`:

```
invalid JSON schema for tool final_result,
tools[2].function.parameters: jsonschema compilation failed:
'/properties/entry_price/anyOf/1/pattern' does not validate with
...pattern/format: '^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$' is not valid 'regex'
```

All 6 desk recommendation agents succeeded (they return `DomainAssessment` subclasses
without Decimal fields), but synthesis always fell back because `PositionRecommendation`
has `entry_price: Decimal`, `stop_loss: Decimal | None`, `take_profit: Decimal | None`.

## Root Cause

Pydantic v2 generates this JSON schema for `Decimal` fields:

```json
{
  "anyOf": [
    {"type": "number"},
    {"type": "string", "pattern": "^(?!^[-+.]*$)[+-]?0*\\d*\\.?\\d*$"}
  ]
}
```

The pattern uses `(?!...)` negative lookahead, which is valid ECMA-262 regex but NOT
supported by Groq's JSON schema validator (likely uses a stricter regex dialect).
PydanticAI sends the model's JSON schema to Groq as a tool schema for structured output,
so the invalid pattern causes a 400 rejection before the LLM even processes the request.

## Solution

Created `LLMDecimal` type alias using Pydantic's `WithJsonSchema` to override the
schema for LLM-facing Decimal fields:

```python
from pydantic import WithJsonSchema
from typing import Annotated
from decimal import Decimal

_LLM_DECIMAL_SCHEMA = WithJsonSchema(
    {"type": "string", "description": "Decimal number as string"}
)
LLMDecimal = Annotated[Decimal, _LLM_DECIMAL_SCHEMA]
```

Applied to `PositionRecommendation`:
```python
entry_price: LLMDecimal       # was: Decimal
stop_loss: LLMDecimal | None   # was: Decimal | None
take_profit: LLMDecimal | None # was: Decimal | None
```

The LLM returns a string, Pydantic parses it to `Decimal`, `field_serializer` converts
back to string for JSON output. Full precision preserved, schema is Groq-compatible.

## Prevention Rule

When using Pydantic models as PydanticAI agent output types:
- **Never use bare `Decimal` fields** — Groq rejects the generated regex pattern
- Use `LLMDecimal` (from `models/recommendation.py`) for any price/monetary field
- Test agent output schemas with `Model.model_json_schema()` and verify no `(?!` patterns
- Other LLM providers may have different schema restrictions — test with all providers
- This does NOT affect internal models (not used as agent output) — only agent `output_type`

## Related

- `src/options_arena/models/recommendation.py` — `LLMDecimal`, `PositionRecommendation`
- `src/options_arena/agents/synthesis_agent.py` — uses `PositionRecommendation` as output type
- Anthropic does NOT have this issue (supports negative lookahead in JSON schema patterns)
