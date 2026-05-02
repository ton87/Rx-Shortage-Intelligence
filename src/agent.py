"""
Anthropic tool-use loop for Rx Shortage Intelligence.

run_agent(system, user_msg, tools, call_tool_fn) → (final_text, tool_calls_log, tokens_used)

- system: list of {"type": "text", "text": ..., "cache_control": {...}} blocks
- tools: Anthropic-format tool schemas (from MCPBridge.list_tools())
- call_tool_fn: async callable (name, args) → str
- Returns: (str, list[dict], int) — final assistant text + audit log + total token usage
"""

import json
import sys
import traceback
import anthropic

MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 8


async def run_agent(
    system: list[dict],
    user_msg: str,
    tools: list[dict],
    call_tool_fn,  # async (name: str, args: dict) -> str
) -> tuple[str, list[dict], int]:
    """
    Run the Anthropic tool-use loop until end_turn or iteration cap.
    Returns (final_text, tool_call_log, tokens_used).
    On non-end_turn termination (max_tokens, stop_sequence, refusal, iteration cap),
    logs stop_reason to stderr and returns whatever text was already produced.
    """
    client = anthropic.AsyncAnthropic(max_retries=2)
    messages = [{"role": "user", "content": user_msg}]
    tool_call_log: list[dict] = []
    tokens_used = 0
    last_text = ""
    last_stop_reason = "unknown"

    for iter_idx in range(MAX_ITERATIONS):
        kwargs: dict = dict(model=MODEL, max_tokens=4096, system=system, messages=messages)
        if tools:
            kwargs["tools"] = tools
        resp = await client.messages.create(**kwargs)

        usage = getattr(resp, "usage", None)
        if usage:
            tokens_used += (getattr(usage, "input_tokens", 0) or 0)
            tokens_used += (getattr(usage, "output_tokens", 0) or 0)

        last_stop_reason = resp.stop_reason

        # Capture any text emitted this turn even if not end_turn — useful when stop_reason=max_tokens
        turn_text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                turn_text += block.text
        if turn_text:
            last_text = turn_text

        if resp.stop_reason == "end_turn":
            return last_text, tool_call_log, tokens_used

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    try:
                        result = await call_tool_fn(block.name, block.input)
                    except Exception as e:
                        # Log full traceback to stderr so operator sees it
                        print(
                            f"[agent] tool {block.name}({block.input}) raised:",
                            file=sys.stderr, flush=True,
                        )
                        traceback.print_exc(file=sys.stderr)
                        result = json.dumps({"error": str(e)})
                    tool_call_log.append({
                        "tool": block.name,
                        "args": block.input,
                        "result_preview": result[:200],
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        # Non-terminal, non-tool-use stop_reason (max_tokens, stop_sequence, refusal, pause_turn).
        print(
            f"[agent] non-end_turn stop_reason={resp.stop_reason!r} at iter {iter_idx}; "
            f"returning partial text (len={len(last_text)}).",
            file=sys.stderr, flush=True,
        )
        return last_text, tool_call_log, tokens_used

    # Iteration cap hit
    print(
        f"[agent] hit MAX_ITERATIONS={MAX_ITERATIONS} cap; last stop_reason={last_stop_reason!r}; "
        f"returning partial text (len={len(last_text)}).",
        file=sys.stderr, flush=True,
    )
    return last_text, tool_call_log, tokens_used
