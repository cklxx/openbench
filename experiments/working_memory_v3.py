"""
Working Memory v3 — Fair Turn Budget for Scratchpad

v2 found scratchpad agent hit turn limit on ALL 20 trials (0% correctness).
Root cause: note-taking overhead consumed the entire turn budget (max_turns=12).

v3 gives BOTH agents max_turns=20 to test whether scratchpad helps when budget
isn't the bottleneck. If scratchpad still loses, the finding is confirmed:
externalized memory is pure overhead for LLM agents with sufficient context windows.

Same tasks, same prompts, only max_turns changed (12 → 20).
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "wm_v2", os.path.join(os.path.dirname(__file__), "working_memory_v2.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SETUP_FILES = _mod.SETUP_FILES
IMPLICIT_PROMPT = _mod.IMPLICIT_PROMPT
FORCED_SCRATCHPAD_PROMPT = _mod.FORCED_SCRATCHPAD_PROMPT
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

experiment = Experiment(
    name="working_memory_v3",
    description=(
        "Working memory v3: same as v2 but max_turns=20 (was 12). "
        "Tests whether scratchpad helps when turn budget isn't the bottleneck."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Implicit vs forced scratchpad with generous turn budget",
    ),
    agent_a=AgentConfig(
        name="implicit_memory",
        model="claude-haiku-4-5",
        system_prompt=IMPLICIT_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=20,
    ),
    agent_b=AgentConfig(
        name="forced_scratchpad",
        model="claude-haiku-4-5",
        system_prompt=FORCED_SCRATCHPAD_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=20,
    ),
    tasks=[
        TaskItem(
            prompt="Fix all bugs in tasks/t1/. Test: cd tasks/t1 && python test_system.py\nPrint the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["config-cascade", "cross-file"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t2/. Test: cd tasks/t2 && python test_pipeline.py\nPrint the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["data-pipeline", "type-error"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t3/. Test: cd tasks/t3 && python test_events.py\nPrint the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["event-system", "cross-file-dependency"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t4/. Test: cd tasks/t4 && python test_auth.py\nPrint the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["auth-roles", "mutation"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["working-memory", "scratchpad", "turn-budget"],
)
