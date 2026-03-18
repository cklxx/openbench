"""Thin wrapper for single-turn LLM calls via claude_agent_sdk.

Uses the same subscription auth as the agent runner — no ANTHROPIC_API_KEY needed.
"""
from __future__ import annotations

import anyio


def sdk_call(prompt: str, model: str = "claude-haiku-4-5") -> str:
    """Make a single-turn, no-tools LLM call and return the result text.

    Starts a new event loop. Use sdk_call_async() when already inside an
    async context (e.g. inside anyio.run()).
    """
    return anyio.run(_run_once, prompt, model)


async def sdk_call_async(prompt: str, model: str = "claude-haiku-4-5") -> str:
    """Async version of sdk_call — awaits _run_once directly.

    Must be called from within an existing async context. Avoids the
    anyio.run() overhead of creating a new event loop per call.
    """
    return await _run_once(prompt, model)


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
