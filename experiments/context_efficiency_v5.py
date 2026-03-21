"""
Context Efficiency v5 — Focused Guidance (No Noise)

v4 finding: noisy guidance (75% irrelevant info about other tasks) HURTS
performance by 42%. But was it the noise, or is guidance fundamentally unhelpful?

v5 approach: Test focused, noise-free guidance on individual tasks.
- 4 separate task-specific experiments merged into one
- Each task's guidance is precise and minimal (~50 tokens, not ~300)
- System prompt ONLY contains info relevant to all tasks (no per-task noise)
- Task prompts give guided agent its specific navigation info
- max_turns=8, n=8 per task

PROBLEM: Both agents get the same task prompt.
SOLUTION: Put guidance in system_prompt, but make it short and precise.
Use ONLY the current task's bug info.

Actually — we CAN'T have different prompts per task in system_prompt.
So instead: use 4 mini-experiments (one Experiment per task pair).

COMPROMISE: Put ALL guidance in system prompt, but make each entry
very concise (1 line per task instead of 3 lines). Total ~80 tokens,
not 315. And prefix each with the task directory so agent can match.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

UNGUIDED_PROMPT = """\
Fix the bugs in the project. Run the test, find and fix the root cause.
"""

# Concise, focused guidance — ~100 tokens total, clear task→file mapping
GUIDED_PROMPT = """\
Bug locations (go directly to these files, skip everything else):
- tasks/t1/: middleware.py (overwrites headers dict) + utils.py (normalize_path doesn't decode)
- tasks/t2/: transforms.py (aggregate mutates original records) + loader.py (drops rows with empty fields)
- tasks/t3/: scheduler.py (*/N cron uses == instead of %) + filters.py (> should be >= in window cutoff)
- tasks/t4/: config_parser.py (empty deps becomes [""] not []) + resolver.py (duplicate entries in order)
"""

# Reuse v4's setup files — they're well-calibrated
# Import them to avoid duplication
import importlib.util, sys, os
_v4_path = os.path.join(os.path.dirname(__file__), "context_efficiency_v4.py")
_spec = importlib.util.spec_from_file_location("v4", _v4_path)
_v4 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v4)
SETUP_FILES = _v4.SETUP_FILES

experiment = Experiment(
    name="context_efficiency_v5",
    description=(
        "Context efficiency v5: focused guidance (~100 tokens, 1-line per task) "
        "vs unguided. Tests pure navigation value without noise overhead. "
        "Same tasks as v4 but minimal prompt footprint."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="unguided vs focused guidance (concise file+bug per task, ~100 tokens)",
    ),
    agent_a=AgentConfig(
        name="unguided",
        model="claude-haiku-4-5",
        system_prompt=UNGUIDED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    agent_b=AgentConfig(
        name="guided",
        model="claude-haiku-4-5",
        system_prompt=GUIDED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    tasks=[
        TaskItem(
            prompt="Fix bugs in tasks/t1/ (web app, 6 files). Run `cd tasks/t1 && python test_app.py`. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["6-file", "middleware"],
        ),
        TaskItem(
            prompt="Fix bugs in tasks/t2/ (data pipeline, 5 files). Run `cd tasks/t2 && python test_pipeline.py`. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["5-file", "mutation"],
        ),
        TaskItem(
            prompt="Fix bugs in tasks/t3/ (notification system, 6 files). Run `cd tasks/t3 && python test_notifications.py`. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["6-file", "cron"],
        ),
        TaskItem(
            prompt="Fix bugs in tasks/t4/ (build system, 5 files). Run `cd tasks/t4 && python test_build.py`. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["5-file", "parser"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=8,
    tags=["context-efficiency", "focused-guidance", "no-noise", "research"],
)
