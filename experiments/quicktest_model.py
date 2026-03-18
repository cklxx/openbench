"""Quick end-to-end test experiment: compare two system prompts with Haiku.

Uses claude-haiku-4-5 and no tools for fast, cheap validation.

Run with:
    openbench run experiments/quicktest_model.py
"""

from openbench.types import AgentConfig, DiffSpec, Experiment

experiment = Experiment(
    name="quicktest_system_prompt",
    description=(
        "Quick E2E test: concise vs verbose system prompt with Haiku. "
        "No tools, 2 turns max, 2 simple tasks."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="no system prompt vs 'be very brief' system prompt",
    ),
    agent_a=AgentConfig(
        name="no_system_prompt",
        model="claude-haiku-4-5",
        system_prompt=None,
        allowed_tools=[],
        max_turns=2,
        extra_options={},
    ),
    agent_b=AgentConfig(
        name="brief_system_prompt",
        model="claude-haiku-4-5",
        system_prompt="Reply in one sentence only. Be extremely concise.",
        allowed_tools=[],
        max_turns=2,
        extra_options={},
    ),
    tasks=[
        "What is the capital of France?",
        "What is 7 times 8?",
    ],
    tags=["quicktest", "system_prompt", "haiku"],
)
