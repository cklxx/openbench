"""Thin wrapper for single-turn LLM calls via claude_agent_sdk.

Uses the same subscription auth as the agent runner — no ANTHROPIC_API_KEY needed.
"""
from __future__ import annotations

import anyio


def sdk_call(prompt: str, model: str = "claude-haiku-4-5") -> str:
    """Make a single-turn, no-tools LLM call and return the result text."""
    return anyio.run(_run_once, prompt, model)


async def _run_once(prompt: str, model: str) -> str:
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

    result = ""
    async for msg in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            model=model,
            allowed_tools=[],
            max_turns=1,
        ),
    ):
        if isinstance(msg, ResultMessage):
            result = msg.result or ""
    return result
