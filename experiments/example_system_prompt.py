"""Example experiment: compare verbose vs concise system prompts.

Run with:
    openbench run experiments/example_system_prompt.py

This experiment tests whether a concise system prompt leads to shorter,
cheaper responses while still being correct — keeping the model, tools,
and max_turns identical so the system_prompt is the only variable.
"""

from openbench.types import AgentConfig, DiffSpec, Experiment

experiment = Experiment(
    name="system_prompt_brevity",
    description=(
        "Test whether a concise system prompt performs better than a verbose one. "
        "Everything else (model, tools, max_turns) is held constant."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="verbose instructions vs concise instructions",
    ),
    agent_a=AgentConfig(
        name="verbose_prompt",
        model="claude-opus-4-6",
        system_prompt=(
            "You are a helpful AI assistant. "
            "Always be thorough and detailed in your responses. "
            "Make sure to cover all edge cases. "
            "Provide examples when helpful. "
            "Be comprehensive."
        ),
        allowed_tools=["Read", "Bash"],
        max_turns=10,
        extra_options={},
    ),
    agent_b=AgentConfig(
        name="concise_prompt",
        model="claude-opus-4-6",
        system_prompt="You are a concise assistant. Be direct and brief.",
        allowed_tools=["Read", "Bash"],
        max_turns=10,
        extra_options={},
    ),
    tasks=[
        "Write a Python function to reverse a string",
        "What is 2+2? Just give the number",
        "List 3 benefits of exercise in one sentence each",
    ],
    tags=["system_prompt", "brevity"],
)
