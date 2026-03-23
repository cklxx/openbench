"""
Real Prompt Engineering v2: On Genuinely Hard Tasks

Same reasoning-hard tasks from real_model_selection_v2.
Both use Haiku (to see where prompting helps at the model's capability edge).

Minimal vs Structured prompt. 15 turns. 4 tasks × 8 samples.
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "v2", os.path.join(os.path.dirname(__file__), "real_model_selection_v2.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, Experiment, DiffSpec

MINIMAL = """\
You are a software developer. Fix the bugs and make all tests pass.
Print the final test output.
"""

STRUCTURED = """\
You are a senior software developer. Follow this workflow:

1. Run the test suite to understand what's failing
2. Read the source code carefully — pay attention to operator precedence,
   data types, and Python-specific semantics
3. Identify the root cause of each failure
4. Fix all bugs — think about edge cases before editing
5. Run tests again to verify

Print the final test output.
"""

experiment = Experiment(
    name="real_prompt_v2",
    description=(
        "Minimal vs structured prompt on reasoning-hard tasks. "
        "Both Haiku, 15 turns. Tests if structured prompting helps "
        "at the model's capability edge."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Minimal vs structured prompt on reasoning-hard tasks",
    ),
    agent_a=AgentConfig(
        name="minimal",
        model="claude-haiku-4-5",
        system_prompt=MINIMAL,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    agent_b=AgentConfig(
        name="structured",
        model="claude-haiku-4-5",
        system_prompt=STRUCTURED,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    tasks=_mod.TASKS,
    setup_files=_mod.SETUP_FILES,
    num_samples=8,
    tags=["prompt-engineering", "reasoning-hard", "realistic"],
)
