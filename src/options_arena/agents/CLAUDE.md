<claude_instructions>
# CLAUDE.md — AI Debate Agents (Anthropic + Ollama)

## Purpose
Two agents argue opposing sides on an options position. One uses the Anthropic Claude API,
the other uses a local Ollama model. A moderator synthesizes the verdict.

## Files
- `base.py` — `DebateAgent` Protocol (shared interface)
- `claude_agent.py` — Anthropic Messages API
- `ollama_agent.py` — Ollama chat API
- `debate.py` — Orchestrator (multi-round loop)
- `moderator.py` — Verdict synthesis
- `schemas.py` — `DebateArgument`, `DebateVerdict`, `MarketContext`

## Anthropic SDK Rules

### Client
- `client = Anthropic()` — reads `ANTHROPIC_API_KEY` from env automatically. Never hardcode keys.
- Use `AsyncAnthropic()` in async modules. Don't mix sync/async.
- Pin model: `"claude-sonnet-4-5-20250929"` — never vague names.
- Increase retries if needed: `Anthropic(max_retries=5)`. Don't add your own retry wrapper on top — the SDK already retries 429s and 5xx.

### Messages API — The ONLY API to Use
```python
response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=4096,                    # REQUIRED — no default, will error without it
    system="You are a bearish options analyst...",  # top-level kwarg, NOT in messages
    messages=[{"role": "user", "content": prompt}],
)
text = response.content[0].text         # content is a LIST of blocks, not a string
```
- `system` is a **kwarg**, not a message. `{"role": "system"}` in messages will error.
- `max_tokens` has **no default**. Omitting it is an instant error.
- `response.content` is a **list** of `TextBlock` objects. Always index: `.content[0].text`.
- Check `response.stop_reason` — if `"max_tokens"`, the argument was truncated. Handle it.

### Streaming
```python
async with client.messages.stream(model=..., max_tokens=..., messages=...) as stream:
    async for text in stream.text_stream:
        yield text
```
For long requests (>10 min), always stream — networks drop idle connections.

### Error Handling
```python
except anthropic.APIConnectionError as e:   # network — retry with backoff
except anthropic.RateLimitError as e:        # 429 — SDK auto-retries, just log
except anthropic.APIStatusError as e:        # 4xx/5xx — log e.status_code, e.response
```
Log `response._request_id` for Anthropic support debugging.

### Cost Tracking
Log `response.usage.input_tokens` and `response.usage.output_tokens` every call. Accumulate per debate session. Expose in report metadata.

## Ollama SDK Rules

### Client
- `client = Client(host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))`
- Validate model exists before debate: catch `ollama.ResponseError` with `status_code == 404`.

### Chat API
```python
response = client.chat(model=model_name, messages=messages)
text = response.message.content
```
- Ollama DOES accept `{"role": "system"}` in messages — opposite of Anthropic.
- Set `options={"num_ctx": 8192}` for long debate contexts.

### Streaming — Known Bugs
- SDK defaults to `stream=False` (opposite of REST API).
- **Streaming + tool calling is broken** — buffers entire response. Use `stream=False` with tools.
- Without tools, streaming works:
  ```python
  for chunk in client.chat(model=..., messages=..., stream=True):
      print(chunk.message.content, end="", flush=True)
  ```

### Error Handling
```python
except ollama.ResponseError as e:   # model not found, bad request
except httpx.ConnectError:          # Ollama server not running
```
Ollama has **no built-in retry**. Implement your own backoff for `ConnectError` and timeouts.

### Model Quirks
- Small models (<13B) often ignore structured output instructions. Validate all parsed output.
- Some models emit `<think>` tags. Strip them before parsing.
- Test every prompt change against both Claude and your Ollama model — adherence varies wildly.

## Debate Protocol

### Shared Interface
Both agents implement `DebateAgent`:
```python
class DebateAgent(Protocol):
    async def argue_position(
        self, ticker: str, option_type: str, position: str,
        market_context: MarketContext, opponent_argument: str | None,
    ) -> DebateArgument: ...
```

### Options-Specific Debate Rules
- Agents must reference specific **strikes, expirations, and Greeks** — not just "the stock will go up."
- Bull case must address: theta decay risk, max loss, breakeven price.
- Bear case must address: unlimited risk (for short calls), assignment risk, IV crush.
- Both sides must cite IV Rank/Percentile to justify whether options are cheap or expensive.
- Both sides must acknowledge the strongest counter-argument.

### Orchestration
- 3 rounds default (configurable). Each round: Agent A → Agent B → swap.
- Full transcript visible to both agents every round.
- Hard timeout per turn: 60s Claude, 120s Ollama. Use `asyncio.wait_for()`.
- If one agent errors/times out, the other wins by default. Log the failure.
- Moderator receives full transcript → produces `DebateVerdict`.

## What Claude Gets Wrong Here (Fix These)
- Don't use raw dicts anywhere in agents — all agent inputs and outputs must be typed Pydantic models. Parse LLM text responses into `DebateArgument` / `DebateVerdict` models immediately. Never pass `dict[str, Any]` between the orchestrator, agents, and moderator.
- Don't put `role: "system"` in Anthropic messages — it goes in `system=` kwarg.
- Don't forget `max_tokens` on Anthropic calls — no default, instant error.
- Don't parse `response.content` as a string — it's a list. Use `.content[0].text`.
- Don't assume Ollama streaming works with tools — it doesn't. Use `stream=False`.
- Don't retry on top of Anthropic SDK's built-in retries.
- Don't let debate rounds run without timeouts.
- Don't let agents produce vague arguments — enforce data-backed claims about specific contracts.
- Don't hardcode model names — use env vars or config.
</claude_instructions>
