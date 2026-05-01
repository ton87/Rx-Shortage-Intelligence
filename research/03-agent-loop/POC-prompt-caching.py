"""
POC: prompt caching with cache_control on system blocks.

Run: ANTHROPIC_API_KEY=... python research/03-agent-loop/POC-prompt-caching.py

Demonstrates:
- cache_control: {"type": "ephemeral"} on system blocks
- usage.cache_creation_input_tokens (write cost) on first call
- usage.cache_read_input_tokens (cheap reads) on subsequent calls
- Cost difference visible in output
"""

import os
import anthropic

MODEL = "claude-sonnet-4-6"

# A long system block — ≥2048 tokens to qualify for caching on Sonnet 4.6
LONG_SYSTEM = (
    "You are a clinical pharmacist briefing assistant. "
    "Your job is to surface drug shortages affecting a hospital's formulary, "
    "classify severity, and recommend therapeutic alternatives. "
    + ("Detailed rules for severity classification follow. " * 200)  # padding to hit token threshold
)


def call(user_msg: str, client: anthropic.Anthropic) -> tuple[str, dict]:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=[
            {
                "type": "text",
                "text": LONG_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "\n".join(b.text for b in resp.content if b.type == "text")
    return text, dict(resp.usage)


def fmt_usage(u: dict) -> str:
    return (
        f"input={u.get('input_tokens', 0)} | "
        f"cache_write={u.get('cache_creation_input_tokens', 0)} | "
        f"cache_read={u.get('cache_read_input_tokens', 0)} | "
        f"output={u.get('output_tokens', 0)}"
    )


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY first.")
        exit(1)

    client = anthropic.Anthropic()

    print("=== Call 1 (cache write) ===")
    _, u1 = call("Briefly: what are you?", client)
    print(fmt_usage(u1))

    print("\n=== Call 2 (cache read expected) ===")
    _, u2 = call("Briefly: what tools would you typically have?", client)
    print(fmt_usage(u2))

    print("\n=== Call 3 (cache read expected) ===")
    _, u3 = call("Briefly: what's a 'shortage briefing'?", client)
    print(fmt_usage(u3))

    print("\n=== Cost math (Sonnet 4.6) ===")
    write_tokens = u1.get("cache_creation_input_tokens", 0)
    read_tokens = sum(u.get("cache_read_input_tokens", 0) for u in (u2, u3))
    output_tokens = sum(u.get("output_tokens", 0) for u in (u1, u2, u3))

    write_cost = write_tokens * 1.25 * 3 / 1_000_000
    read_cost = read_tokens * 0.1 * 3 / 1_000_000
    output_cost = output_tokens * 15 / 1_000_000
    total = write_cost + read_cost + output_cost

    print(f"Cache writes:  {write_tokens} tok × 1.25 × $3/M  = ${write_cost:.5f}")
    print(f"Cache reads:   {read_tokens} tok × 0.1 × $3/M    = ${read_cost:.5f}")
    print(f"Output:        {output_tokens} tok × $15/M       = ${output_cost:.5f}")
    print(f"Total:                                            ${total:.5f}")
