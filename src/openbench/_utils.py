"""Shared internal utilities."""
from __future__ import annotations

import json
import re
from typing import Any


def _resolve_system_prompt(sp: Any) -> str | None:
    """Resolve SkillConfig or str to a plain string for SDK consumption."""
    if sp is None or isinstance(sp, str):
        return sp
    # SkillConfig: has a system_prompt attribute
    return sp.system_prompt


def _resolve_model(
    model: Any,
    task: str,
    system_prompt: str | None = None,
    difficulty: str | None = None,
) -> str:
    """Resolve str | ModelRouter → concrete model string for the SDK.

    When model is a ModelRouter, uses multiple signals:
    - Estimated input tokens (task + system_prompt)
    - Task difficulty tag (from TaskItem)
    - Keyword detection in task text
    """
    if isinstance(model, str):
        return model
    # ModelRouter — multi-signal complexity estimation
    text = task + (system_prompt or "")
    estimated_tokens = max(1, len(text) // 4)  # ~4 chars/token heuristic
    return model.resolve(estimated_tokens, difficulty=difficulty, task_text=task)


def _resolve_task(task: Any) -> tuple[str, Any]:
    """Resolve str | TaskItem → (prompt_str, task_item_or_None).

    Returns the prompt string and the original TaskItem (if applicable)
    so callers can access metadata like expected answers.
    """
    if isinstance(task, str):
        return task, None
    # TaskItem
    return task.prompt, task


def check_correctness(output: str, expected: str | None, check_fn: str | None = None) -> bool | None:
    """Check if agent output matches the expected answer.

    Returns True/False for objective check, None if no expected answer provided.

    Uses a multi-strategy approach (first match wins):
    1. If check_fn is provided, evaluate it with `output` in scope
    2. If expected is provided, check for case-insensitive substring match
    3. If output is empty, return False when any check is configured
    """
    if expected is None and check_fn is None:
        return None

    # Empty output always fails
    if not output or not output.strip():
        return False

    if check_fn is not None:
        try:
            return bool(eval(check_fn, {"__builtins__": {}}, {"output": output}))  # noqa: S307
        except Exception:  # noqa: BLE001
            return False

    if expected is not None:
        # Normalize whitespace and case for comparison
        norm_output = " ".join(output.lower().split())
        norm_expected = " ".join(expected.lower().split())
        return norm_expected in norm_output

    return None


def _parse_json(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise ValueError(f"Cannot parse JSON from: {text[:300]}")
