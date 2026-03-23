"""
Budget Awareness: Does Knowing Your Turn Limit Help?

Research (BATS, Google 2025):
- Standard agents hit a performance ceiling regardless of extra budget
- Budget-aware agents achieve comparable accuracy with 31% fewer tool calls
- Problem isn't budget SIZE but budget AWARENESS

Design: Same hard tasks, same turn budget (12 turns — tight but not impossible).
- Agent A (unaware): "Fix all bugs" — no budget info
- Agent B (aware): "Fix all bugs. You have exactly 12 tool calls. Plan carefully."

If awareness helps: the agent allocates turns more efficiently
If awareness hurts: the agent becomes overly cautious or wastes time planning

4 tasks × 5 samples, max_turns=12.
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "dh", os.path.join(os.path.dirname(__file__), "task_decomposition_hard.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

UNAWARE_PROMPT = """\
You are debugging Python code. Fix all bugs and make all tests pass.
Print the final test output.
"""

AWARE_PROMPT = """\
You are debugging Python code. Fix all bugs and make all tests pass.

BUDGET: You have exactly 12 tool calls available. After 12 tool calls,
your session ends — whether or not you're done. Plan your workflow to
maximize your chances within this budget.

Suggested allocation:
- 1 call to run tests (see what fails)
- 1 call to find/read source file
- 1 call to read test file
- 3 calls to edit bugs
- 1 call to verify
= 7 calls minimum, 5 spare for iteration

Be efficient. Every tool call counts.
Print the final test output.
"""

experiment = Experiment(
    name="budget_awareness",
    description=(
        "Does telling agents their exact turn budget improve efficiency? "
        "Unaware (generic prompt) vs aware (explicit budget + allocation guide). "
        "4 hard tasks, max_turns=12, n=5."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Unaware (no budget info) vs budget-aware (explicit turn limit + allocation)",
    ),
    agent_a=AgentConfig(
        name="unaware",
        model="claude-haiku-4-5",
        system_prompt=UNAWARE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=12,
    ),
    agent_b=AgentConfig(
        name="budget_aware",
        model="claude-haiku-4-5",
        system_prompt=AWARE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=12,
    ),
    tasks=_mod.TASKS,
    setup_files=_mod.SETUP_FILES,
    num_samples=5,
    tags=["budget-awareness", "turn-efficiency", "BATS"],
)
