"""
Posture vs Procedure: Two Prompt Philosophies

Two reasonable approaches to system prompts:

Agent A (posture/attitude): Describes HOW TO THINK — character, values, mindset.
  "You are careful and thorough. You understand code before changing it."

Agent B (procedure/steps): Describes WHAT TO DO — explicit workflow steps.
  "Step 1: Run tests. Step 2: Read code. Step 3: Fix. Step 4: Verify."

Both aim for the same outcome (good bug fixes). The difference:
- Posture sets a DISPOSITION — the agent decides its own actions
- Procedure prescribes ACTIONS — the agent follows the script

Same hard tasks (regex, float, closure, codec). 15 turns. n=8.
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "v2", os.path.join(os.path.dirname(__file__), "real_model_selection_v2.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, Experiment, DiffSpec

POSTURE_PROMPT = """\
You are a careful, methodical developer who values correctness.

Your approach:
- Understand the code's intent before changing anything
- Think about edge cases and type semantics
- Make minimal, targeted changes — don't over-engineer
- Verify your work before declaring it done

Fix the bugs and make all tests pass.
Print the final test output.
"""

PROCEDURE_PROMPT = """\
You are a software developer. Follow this workflow:

1. Run the test suite to identify failures
2. Read the source code to understand the codebase
3. Identify the root cause of each failure
4. Fix all bugs
5. Review your changes for correctness
6. Run tests again to verify

Fix the bugs and make all tests pass.
Print the final test output.
"""

experiment = Experiment(
    name="posture_vs_procedure",
    description=(
        "Posture (attitude/mindset prompt) vs procedure (step-by-step workflow). "
        "Both are reasonable prompts. Tests which mechanism produces better behavior. "
        "Hard tasks, 15 turns, n=8."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Posture (how to think) vs procedure (what to do)",
    ),
    agent_a=AgentConfig(
        name="posture",
        model="claude-haiku-4-5",
        system_prompt=POSTURE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    agent_b=AgentConfig(
        name="procedure",
        model="claude-haiku-4-5",
        system_prompt=PROCEDURE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    tasks=_mod.TASKS,
    setup_files=_mod.SETUP_FILES,
    num_samples=8,
    tags=["prompt-philosophy", "posture-vs-procedure", "realistic"],
)
