"""
Anthropic tool-use loop for Rx Shortage Intelligence.

run_agent(system, user_msg, tools, call_tool_fn) → (final_text, tool_calls_log)

- system: list of {"type": "text", "text": ..., "cache_control": {...}} blocks
- tools: Anthropic-format tool schemas (from MCPBridge.list_tools())
- call_tool_fn: async callable (name, args) → str
- Returns: (str, list[dict]) — final assistant text + audit log of tool calls made
"""

import json
import anthropic

MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 20


async def run_agent(
    system: list[dict],
    user_msg: str,
    tools: list[dict],
    call_tool_fn,  # async (name: str, args: dict) -> str
) -> tuple[str, list[dict]]:
    """
    Run the Anthropic tool-use loop until end_turn or iteration cap.
    Returns (final_text, tool_call_log).
    """
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user_msg}]
    tool_call_log = []

    for _ in range(MAX_ITERATIONS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            tools=tools,
            messages=messages,
        )

        if resp.stop_reason == "end_turn":
            # Extract final text
            text = ""
            for block in resp.content:
                if hasattr(block, "text"):
                    text += block.text
            return text, tool_call_log

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    try:
                        result = await call_tool_fn(block.name, block.input)
                    except Exception as e:
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
        else:
            # max_tokens, stop_sequence, etc. — break to avoid loop
            break

    # Iteration cap hit — return whatever we have
    return "", tool_call_log
