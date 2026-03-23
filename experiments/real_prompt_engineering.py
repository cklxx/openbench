"""
Real Decision: Which System Prompt Style Works Best?

Two prompts that real teams actually debate:

Agent A (Minimal): Brief, trusts the model to figure out its own workflow.
  "You are a software developer. Fix the bugs. Print test output."

Agent B (Structured): Gives a workflow and defensive review step.
  "You are a senior developer. Run tests → read code → fix → review → verify."

Neither is artificially bad. Both are prompts real teams use.
Same mixed-difficulty tasks, same generous turns (15).

Goal: does structured prompting help on harder tasks while being
unnecessary on easy ones? Or does minimal always win?

4 tasks (easy→hard) × 8 samples, max_turns=15.
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "rms", os.path.join(os.path.dirname(__file__), "real_model_selection.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

MINIMAL_PROMPT = """\
You are a software developer. Fix the bugs and make all tests pass.
Print the final test output.
"""

STRUCTURED_PROMPT = """\
You are a senior software developer. Follow this workflow:

1. Run the test suite to understand what's failing
2. Read the source code to understand the codebase
3. Identify the root cause of each failure
4. Fix all bugs
5. Review your changes — make sure you haven't introduced new issues
6. Run tests again to verify everything passes

Think carefully about edge cases before editing.
Print the final test output.
"""

experiment = Experiment(
    name="real_prompt_engineering",
    description=(
        "Real prompt decision: minimal ('fix the bugs') vs structured "
        "('run tests → read → fix → review → verify'). "
        "Mixed-difficulty tasks, generous turns. Both are reasonable prompts."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Minimal (trust the model) vs structured (explicit workflow + review step)",
    ),
    agent_a=AgentConfig(
        name="minimal",
        model="claude-haiku-4-5",
        system_prompt=MINIMAL_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    agent_b=AgentConfig(
        name="structured",
        model="claude-haiku-4-5",
        system_prompt=STRUCTURED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    tasks=_mod.TASKS,
    setup_files=_mod.SETUP_FILES,
    num_samples=8,
    tags=["prompt-engineering", "minimal-vs-structured", "realistic"],
)
