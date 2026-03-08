# Complex Reasoning Prompt Template for Claude

> A framework synthesized from Anthropic's official prompting best practices for Claude Opus 4.6, Sonnet 4.6, and Haiku 4.5. Use this template to craft prompts that maximize Claude's reasoning capabilities.

---

## The Optimal Structure

Claude performs best on complex reasoning tasks when prompts follow this **7-component architecture**. Each section uses XML tags for unambiguous parsing.

---

### The Template

```
<role>
You are a [specific expert role with domain context].
[1-2 sentences on WHY this role matters for the task — Claude
performs better when it understands the motivation behind instructions.
It generalizes from the explanation.]
</role>

<context>
[Background information Claude needs to reason about the problem.
Place long documents or data HERE — before the task instructions.
For inputs over 20K tokens, always put longform data at the top,
above your query, instructions, and examples. Queries placed at
the end of the prompt improve response quality by up to 30% in
tests, especially with complex, multi-document inputs.

For multiple documents, use structured metadata:
<documents>
  <document index="1">
    <source>source_file.pdf</source>
    <document_content>{{DOCUMENT_1}}</document_content>
  </document>
  <document index="2">
    <source>data_file.csv</source>
    <document_content>{{DOCUMENT_2}}</document_content>
  </document>
</documents>
]
</context>

<task>
[Clear, explicit statement of what you want Claude to accomplish.
Be specific about the deliverable and ambition level. If you want
"above and beyond" behavior, request it explicitly rather than
relying on Claude to infer this from vague prompts.

BAD:  "Analyze this data."
GOOD: "Analyze this dataset to identify the top 3 revenue-driving segments,
       explain the causal factors behind each, and recommend resource
       allocation changes. Go beyond surface-level observations to find
       non-obvious patterns."]
</task>

<instructions>
[How to approach the task. For complex reasoning, prefer high-level
guidance over prescriptive step-by-step instructions. A prompt like
"consider this thoroughly" often produces better reasoning than a
hand-written step-by-step plan — Claude's reasoning frequently
exceeds what a human would prescribe.

For tasks where order matters, use numbered steps:
1. First, [initial analysis step with rationale]
2. Then, [deeper reasoning step]
3. Next, [synthesis or comparison step]
4. Finally, [conclusion and validation step]

For very hard problems, prefer open-ended guidance:
"Consider this problem thoroughly and in great detail. Explore
multiple approaches and show your complete reasoning. If your
first approach has weaknesses, try alternative methods before
settling on a final answer."

For long-context tasks, ask Claude to ground its work in quotes:
"First, quote the relevant passages from the source materials,
then synthesize your analysis from those quotes."]
</instructions>

<constraints>
[Boundaries, rules, and non-negotiables.
Frame as what TO DO, not what NOT to do — positive instructions
produce more reliable behavior.

- Use only the data provided in <context> — flag any gaps explicitly
- Prioritize accuracy over speed; state confidence levels
- If uncertain, say so rather than speculating
- Keep reasoning grounded in evidence from the provided materials
- Before you finish, verify your answer against [specific criteria]]
</constraints>

<examples>
[Show, don't just tell. Include 3-5 examples for best results.
Make them relevant (mirror actual use cases), diverse (cover edge
cases), and structured (wrapped in tags so Claude distinguishes
them from instructions).

You can include <thinking> tags in examples to model the reasoning
pattern you want — Claude will generalize that style.]

<example>
<input>[Representative input]</input>
<thinking>[Model the thinking process you want]</thinking>
<output>[The gold-standard output]</output>
</example>

<example>
<input>[Edge case or harder input]</input>
<thinking>[Show how to handle complexity]</thinking>
<output>[How to handle the edge case]</output>
</example>

<example>
<input>[Different scenario for diversity]</input>
<thinking>[Another reasoning pattern]</thinking>
<output>[Expected output]</output>
</example>
</examples>

<output_format>
[Explicit specification of the desired response structure.
Tell Claude what to do, not what not to do. For example,
"Write in flowing prose paragraphs" instead of "Don't use
bullet points."]

Structure your response as follows:
1. **Executive Summary** — [2-3 sentence conclusion]
2. **Analysis** — [Detailed reasoning]
3. **Evidence** — [Supporting data points with quotes from source]
4. **Recommendation** — [Actionable next steps]
5. **Confidence & Caveats** — [What you're sure about vs. uncertain]
</output_format>
```

---

## Quick-Reference Cheat Sheet

| Principle | What to Do | Why It Works |
|-----------|-----------|--------------|
| **Be Explicit** | State exactly what you want, including ambition level | Claude follows precise instructions closely; vague prompts get vague results |
| **Provide Context First** | Place long documents before the query | Queries at the end improve quality by up to 30% in multi-document tests |
| **Explain the WHY** | Give rationale behind rules and constraints | Claude generalizes better when it understands motivation |
| **Use XML Tags** | Wrap each section in semantic tags | Prevents mixing up instructions, context, and examples |
| **Show 3-5 Examples** | Include diverse input/output demonstrations | Few-shot prompting clarifies subtle requirements words can't capture |
| **Quote-Ground Long Context** | Ask Claude to quote sources before analyzing | Cuts through document noise; improves accuracy on long inputs |
| **High-Level for Hard Problems** | Say "consider deeply" not "step 1, step 2" | Claude's reasoning often exceeds prescribed processes |
| **Affirm, Don't Negate** | "Write in formal prose" not "Don't use slang" | Positive instructions produce more reliable behavior |
| **Add Self-Verification** | "Before finishing, verify against [criteria]" | Catches errors reliably, especially for math, logic, and code |
| **Use Moderate Language** | "Use this tool when..." not "CRITICAL: You MUST..." | Claude 4.6 models overtrigger on aggressive prompting language |

---

## Complexity-Scaled Patterns

### Level 1 — Single Reasoning Task
Use when the problem has one clear path.

```
<role>You are a [domain] expert.</role>

<context>[Relevant information]</context>

<task>[Clear objective]</task>

<instructions>
Consider this problem carefully. Analyze the key factors,
weigh the evidence, and provide a well-reasoned conclusion.
</instructions>
```

### Level 2 — Multi-Step Analysis
Use when the task requires breaking down into sub-problems.

```
<role>You are a [domain] expert specializing in [sub-domain].
Your analysis will inform [specific decision], so rigor matters.</role>

<context>[All relevant data and background]</context>

<task>[Compound objective with clear deliverable]</task>

<instructions>
Approach this in phases:
Phase 1: [Decompose the problem — identify key variables]
Phase 2: [Analyze each variable independently]
Phase 3: [Synthesize findings — look for interactions and non-obvious patterns]
Phase 4: [Stress-test your conclusions — what could invalidate them?]
Phase 5: [Formulate final recommendation with confidence levels]
</instructions>

<constraints>
[Guardrails and quality standards]
</constraints>

<examples>
[3-5 examples showing expected depth and format]
</examples>

<output_format>
[Detailed structure specification]
</output_format>
```

### Level 3 — Deep Research / Adversarial Reasoning
Use for the hardest problems where you want Claude's full capability.

```
<role>You are a [domain] expert with decades of experience.
You're known for finding flaws others miss and seeing connections
across disciplines.</role>

<context>[Comprehensive background materials]</context>

<task>[High-stakes objective requiring deep analysis]</task>

<instructions>
Take your time with this problem. Consider it thoroughly and in
great detail. Explore multiple approaches and frameworks before
settling on an answer.

Specifically:
- Consider at least 3 different analytical frameworks
- Actively look for evidence that contradicts your initial hypothesis
- Identify assumptions that, if wrong, would change your conclusion
- If your first approach reveals weaknesses, try alternative methods

Show your complete reasoning process.
</instructions>

<examples>
[Gold-standard examples showing depth expected, including
<thinking> tags to model the reasoning pattern]
</examples>

<constraints>
- Flag uncertainty explicitly with confidence percentages
- Distinguish between "I'm confident because of evidence X"
  and "I believe this but evidence is limited"
- If you reach a conclusion too easily, deliberately challenge it
- Before finalizing, verify your answer against [specific test criteria]
</constraints>

<output_format>
1. **Conclusion** — Your best answer with confidence level
2. **Key Evidence** — The 3-5 most important supporting points
3. **Counterarguments** — Strongest challenges to your conclusion
4. **Remaining Unknowns** — What additional info would change your answer
</output_format>
```

---

## Thinking and Reasoning

Claude's latest models offer powerful thinking capabilities. Understanding when and how to leverage them is critical for complex reasoning tasks.

### Adaptive Thinking (Claude Opus 4.6 / Sonnet 4.6)

Claude Opus 4.6 uses **adaptive thinking** by default, where Claude dynamically decides when and how much to think based on query complexity and the `effort` parameter. In internal evaluations, adaptive thinking reliably outperforms manual extended thinking.

**You do NOT need to prompt for `<thinking>` tags when adaptive thinking is active.** Claude handles reasoning internally. Instead, guide the quality of thinking:

```
After receiving new information, carefully reflect on its quality
and determine optimal next steps before proceeding.
```

### Effort Parameter

Control thinking depth with `effort`: `low`, `medium`, `high`, or `max`.

- **Low**: High-volume or latency-sensitive workloads
- **Medium**: Most applications (good default)
- **High**: Complex reasoning, agentic coding, multi-step research
- **Max**: Hardest problems requiring full exploration

### Manual Chain-of-Thought (Fallback)

When adaptive thinking is disabled, you can still encourage step-by-step reasoning manually using structured tags:

```
Use <thinking> tags for your detailed reasoning process,
then provide your final answer in <answer> tags.
```

This is a fallback technique, not the primary approach for Claude 4.6 models.

### Controlling Overthinking

Claude Opus 4.6 does significantly more upfront exploration than previous models. If this causes excessive latency or token usage:

```
When deciding how to approach a problem, choose an approach and
commit to it. Avoid revisiting decisions unless you encounter new
information that directly contradicts your reasoning. If you're
weighing two approaches, pick one and see it through.
```

---

## Prompt Chaining

With adaptive thinking and subagent orchestration, Claude handles most multi-step reasoning internally. Explicit prompt chaining -- breaking a task into sequential API calls -- is still useful when you need to **inspect intermediate outputs** or **enforce a specific pipeline structure**.

```
+---------------+    +----------------+    +---------------+    +----------------+
|  Prompt 1:    |--->|  Prompt 2:     |--->|  Prompt 3:    |--->|  Prompt 4:     |
|  Research &   |    |  Analyze &     |    |  Synthesize   |    |  Review &      |
|  Extract      |    |  Compare       |    |  & Recommend  |    |  Refine        |
+---------------+    +----------------+    +---------------+    +----------------+
```

**The most common chaining pattern is self-correction:** generate a draft, have Claude review it against criteria, then have Claude refine based on the review. Each step is a separate API call so you can log, evaluate, or branch at any point.

**Each prompt in the chain should:**
- Have a single, clear objective
- Use XML tags to pass outputs between steps
- Include only the context needed for that step
- Be independently testable

---

## Anti-Patterns to Avoid

| Don't Do This | Do This Instead |
|--------------|----------------|
| "Don't use jargon" | "Write in plain language accessible to a general audience" |
| Vague: "Analyze this" | Specific: "Identify the top 3 factors driving X and rank by impact" |
| Overlong instructions with 20+ steps | High-level guidance + 3-5 examples |
| Putting the question before 20K tokens of context | Context first, question after |
| Asking for both brevity and exhaustive detail | Pick one priority, or specify per section |
| No examples for non-obvious formats | 3-5 examples showing exact expected output |
| "CRITICAL: You MUST use this tool when..." | "Use this tool when..." (4.6 models overtrigger on aggressive language) |
| Relying on prefilled assistant responses | Use direct instructions or structured outputs (prefills deprecated in 4.6) |
| Prescribing every reasoning step for hard problems | Give high-level guidance; let Claude reason freely |

---

## API Configuration for Claude 4.6

When using the API, the thinking and effort parameters replace the older `budget_tokens` approach:

```python
# Adaptive thinking (recommended for Opus 4.6)
client.messages.create(
    model="claude-opus-4-6",
    max_tokens=64000,
    thinking={"type": "adaptive"},
    output_config={"effort": "high"},
    messages=[{"role": "user", "content": "..."}],
)

# For Sonnet 4.6 with manual extended thinking
client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=16384,
    thinking={"type": "enabled", "budget_tokens": 16384},
    output_config={"effort": "medium"},
    messages=[{"role": "user", "content": "..."}],
)
```

**Note:** Prefilled responses on the last assistant turn are no longer supported starting with Claude 4.6 models. Use direct instructions, structured outputs, or tool calling instead.

---

## Sources

- [Anthropic Prompting Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [Prompt Engineering Overview](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview)
- [Extended Thinking](https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking)
- [Adaptive Thinking](https://docs.anthropic.com/en/docs/build-with-claude/adaptive-thinking)
- [Effort Parameter](https://docs.anthropic.com/en/docs/build-with-claude/effort)
- [Structured Outputs](https://docs.anthropic.com/en/docs/build-with-claude/structured-outputs)
