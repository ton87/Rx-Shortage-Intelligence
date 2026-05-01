"""
POC: minimal Anthropic tool use loop with mock tools.

Run: ANTHROPIC_API_KEY=... python research/03-agent-loop/POC-tool-use-loop.py

Demonstrates:
- while-loop on stop_reason
- tool_use → tool_result append cycle
- max-iteration safety cap
- Final assistant text extraction
"""

import os
import anthropic

MODEL = "claude-sonnet-4-6"
MAX_ITERATIONS = 10

# Mock tools — would normally come from MCP bridge
TOOLS = [
    {
        "name": "get_weather",
        "description": "Get current weather for a city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
    {
        "name": "get_population",
        "description": "Get population for a city.",
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
]


def execute_tool(name: str, args: dict) -> str:
    """Mock tool implementations."""
    if name == "get_weather":
        return f"Weather in {args['city']}: 72°F, sunny."
    if name == "get_population":
        return f"Population of {args['city']}: 8.4M (2024)."
    return f"Error: unknown tool {name}"


def run(user_message: str) -> str:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return "Set ANTHROPIC_API_KEY first."

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": user_message}]

    for iteration in range(MAX_ITERATIONS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOLS,
            messages=messages,
        )
        print(f"\n--- iteration {iteration} | stop_reason={resp.stop_reason} ---")

        if resp.stop_reason == "end_turn":
            text_blocks = [b.text for b in resp.content if b.type == "text"]
            return "\n".join(text_blocks)

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use":
                    print(f"  → {block.name}({block.input})")
                    result = execute_tool(block.name, block.input)
                    print(f"  ← {result}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})
        else:
            # max_tokens, stop_sequence, refusal — bail
            return f"Loop ended with stop_reason={resp.stop_reason}"

    return f"Hit max iterations ({MAX_ITERATIONS}) without end_turn."


if __name__ == "__main__":
    answer = run("What's the weather and population of New York?")
    print("\n=== Final answer ===")
    print(answer)
