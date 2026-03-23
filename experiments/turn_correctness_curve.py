"""
Turn-Correctness Curve: Mapping the Fundamental Relationship

Research shows coverage scales as exponentiated power law with samples
(Large Language Monkeys, Stanford 2024). We map this for agent TURNS.

Design: Same D-Hard tasks (4 × 3 bugs, genuine difficulty) run at
5 different turn budgets: 8, 11, 14, 17, 20.

This reveals:
- The sigmoid/step shape of the turn-correctness relationship
- The "knee" where adding turns stops helping
- The minimum viable turn budget for these tasks

Tournament: 5 agents × 4 tasks × 3 samples = 60 trials per agent.
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "dh", os.path.join(os.path.dirname(__file__), "task_decomposition_hard.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, TournamentConfig, TaskItem

PROMPT = """\
You are debugging Python code. Fix all bugs and make all tests pass.
Print the final test output.
"""

tournament = TournamentConfig(
    name="turn_correctness_curve",
    description=(
        "Map turn-correctness relationship on hard tasks. "
        "5 agents with turns={8,11,14,17,20} on 4 hard tasks (3 bugs each). "
        "Reveals the sigmoid curve and optimal turn budget."
    ),
    configs=[
        AgentConfig(
            name="turns_08",
            model="claude-haiku-4-5",
            system_prompt=PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
            max_turns=8,
        ),
        AgentConfig(
            name="turns_11",
            model="claude-haiku-4-5",
            system_prompt=PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
            max_turns=11,
        ),
        AgentConfig(
            name="turns_14",
            model="claude-haiku-4-5",
            system_prompt=PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
            max_turns=14,
        ),
        AgentConfig(
            name="turns_17",
            model="claude-haiku-4-5",
            system_prompt=PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
            max_turns=17,
        ),
        AgentConfig(
            name="turns_20",
            model="claude-haiku-4-5",
            system_prompt=PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
            max_turns=20,
        ),
    ],
    tasks=_mod.TASKS,
    setup_files=_mod.SETUP_FILES,
    num_samples=3,
    tags=["scaling-law", "turn-curve", "hard-tasks"],
)
