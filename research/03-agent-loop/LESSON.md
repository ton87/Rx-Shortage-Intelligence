# Agent Loop — Lesson

## The pattern

Anthropic's tool-use loop is a `while` on `stop_reason`:

```python
messages = [{"role": "user", "content": user_input}]
while True:
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system_blocks,    # with cache_control
        tools=tools,
        messages=messages,
    )
    if resp.stop_reason == "end_turn":
        break
    if resp.stop_reason == "tool_use":
        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for block in resp.content:
            if block.type == "tool_use":
                result = call_tool_via_mcp_bridge(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "user", "content": tool_results})
    else:
        # max_tokens, stop_sequence, refusal → break to avoid infinite loop
        break
```

That's the entire agent. No LangChain. No LangGraph. No abstraction tax.

## Why native, not framework

PRD §12.4: "Native agent loop over abstraction libraries: transparency over abstraction." Two reasons:

1. **Drill-down auditability (FR-5)** is the trust UX. If reasoning traces hide behind 4 layers of framework code, customer can't audit. Native loop = code IS the trace.
2. **Hackathon time**: LangGraph install + DAG setup eats 30 min for zero functional benefit on a single-tool-loop pattern.

## System prompt structure

Three blocks, ordered static-to-dynamic for cache hits:

```python
system_blocks = [
    {
        "type": "text",
        "text": ROLE_AND_RULES,             # ~1500 tokens, never changes
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": SEVERITY_RUBRIC,            # ~800 tokens, rules of thumb for classification
        "cache_control": {"type": "ephemeral"},
    },
    {
        "type": "text",
        "text": json.dumps(formulary_subset),  # ~3000 tokens, this customer's formulary
        "cache_control": {"type": "ephemeral"},
    },
]
```

Each block ≥2048 tokens to qualify for caching on Sonnet 4.6. If under, combine.

## Per-drug user message

```python
user_msg = f"""
Drug: {drug.name} (RxCUI {drug.rxcui})
Today's shortage status: {today_status}
Yesterday's status: {yesterday_status}
Active orders last 30 days: {orders.count}
Departments affected: {orders.departments}

Generate a BriefingItem for this drug. Use the tools to retrieve label sections and class members. Return JSON matching the BriefingItem schema. Cite every claim.
"""
```

Keep dynamic content tight — bigger user msg = lower cache hit value.

## RAG over labels

7 sections per label. ~2-3K tokens each in raw form. Naive: pass full label = 15-18K tokens × 30 drugs = blows budget.

**Strategy**: chunk + keyword retrieve.

```python
def chunk_label(label: dict, max_tokens: int = 800) -> list[dict]:
    chunks = []
    for section_name, text in extract_relevant_sections(label).items():
        # Simple paragraph split
        paragraphs = text.split("\n\n")
        current = []
        current_size = 0
        for p in paragraphs:
            p_size = len(p) // 4  # rough token est
            if current_size + p_size > max_tokens:
                chunks.append({
                    "section": section_name,
                    "text": "\n\n".join(current),
                    "source_url": f"https://api.fda.gov/drug/label.json?search=openfda.rxcui:{rxcui}",
                })
                current = [p]
                current_size = p_size
            else:
                current.append(p)
                current_size += p_size
        if current:
            chunks.append({"section": section_name, "text": "\n\n".join(current), ...})
    return chunks


def keyword_retrieve(chunks: list[dict], query: str, k: int = 3) -> list[dict]:
    """BM25-lite: score by term overlap."""
    query_terms = set(query.lower().split())
    scored = []
    for c in chunks:
        text_terms = set(c["text"].lower().split())
        score = len(query_terms & text_terms)
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]
```

For v0.1, query = drug indication or active-order department. e.g., for cisplatin in oncology orders, query = "indications oncology contraindications". Returns top 3 chunks.

## Citations

Every chunk passed to the model carries a `source_url`. The system prompt instructs:

> When you make a clinical claim, cite the chunk by including its `source_url` in the `citations` array of your output. Never make a claim without a citation.

Output schema enforces this structurally:

```json
{
  "rxcui": "...",
  "severity": "Critical|Watch|Resolved",
  "summary": "one sentence",
  "rationale": "...",
  "citations": [{"claim": "...", "source_url": "..."}],
  "alternatives": [{"rxcui": "...", "name": "...", "rationale": "...", "source_url": "..."}],
  "confidence": "high|medium|low"
}
```

## Confidence scoring

Three buckets per PRD §13.1:
- **High (≥85%)**: tool calls returned exact RxCUI matches, label sections support claim, alternative is on-formulary preferred
- **Medium (60-85%)**: class-member alternative (not true equivalent), or some tool call had partial match
- **Low (<60%)**: name-fallback used, no alternative found, conflicting tool results

Agent self-reports confidence in output. UI gates one-click accept on `confidence == "high"`.

## Cost discipline

Target: <$0.05/briefing, ~30 drugs.

Sonnet 4.6: $3/M input, $15/M output.

Without caching:
- Per-drug: 6K input + 1K output = $0.033 → 30 drugs = $0.99 ❌

With caching (system blocks cached, per-drug user msg dynamic):
- First drug: 6K write (1.25× = $0.0225 input) + 1K output ($0.015) = $0.0375
- Drugs 2-30: 5.5K cache hit (0.1× = $0.0017) + 0.5K dynamic input ($0.0015) + 1K output = $0.018 each → 29 × $0.018 = $0.52 ❌

Still over. Need batching:
- Send 5 drugs per call, 6 calls total
- Each call: 5.5K cached (0.1× = $0.0017) + 2.5K dynamic input ($0.0075) + 4K output ($0.06) = ~$0.07
- 6 calls × $0.07 = $0.42 ❌ getting closer

Final discipline:
- Force `max_tokens=2K` per call
- Output schema is JSON — ~400 tokens × 5 drugs = 2K
- Cache hit: 5.5K × 0.1 × $3/M = $0.00165
- Dynamic per-call: 1K × $3/M = $0.003
- Output: 2K × $15/M = $0.03
- Per call: $0.035
- 6 calls = $0.21 ❌ still over

So target is aspirational. Realistic v0.1: ~$0.20/briefing. Document honestly. Production v0.2 can use Haiku 4.5 for screening pass + Sonnet for final composition (mixture-of-models pattern).

## What can go wrong

- **Infinite loop**: Claude keeps calling `tool_use`. Cap iterations: `for _ in range(20): if stop_reason != "tool_use": break`.
- **Bad JSON output**: parse fail. Mitigation: use `tools` with output schema or strict JSON mode if available.
- **Cache miss surprise**: cached blocks must be byte-identical. Don't include timestamps inside cached system text.
- **Tool error recovery**: if MCP returns `{"error": "..."}`, agent may keep retrying same tool. System prompt: "If a tool returns an error, do not retry. Surface in `confidence: low`."
