"""
Thin wrapper so orchestrate.py doesn't care which model backend does synthesis.
Defaults to calling the Anthropic API directly; swap for Composio's own
model-routing if preferred.
"""

import os


def call_llm(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")
