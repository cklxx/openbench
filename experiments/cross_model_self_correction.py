"""
Cross-Model: Self-Correction Strategy on Sonnet vs Haiku

Haiku finding: refine > pivot (+29%) on independent bugs.
Question: Does Sonnet show the same pattern, or does a stronger model
make pivot more viable (better at fresh analysis)?

Uses the same tasks as self_correction_strategy (v1 — independent bugs).
DiffSpec: model (haiku vs sonnet), with refine prompt for both.

Also tests: refine_sonnet vs refine_haiku — is the strategy gap
larger or smaller than the model gap?
"""
from openbench.types import AgentConfig, TournamentConfig, TaskItem

import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "sc_v1", os.path.join(os.path.dirname(__file__), "self_correction_strategy.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
SETUP_FILES = _mod.SETUP_FILES
PIVOT_PROMPT = _mod.PIVOT_PROMPT
REFINE_PROMPT = _mod.REFINE_PROMPT

tournament = TournamentConfig(
    name="cross_model_self_correction",
    description=(
        "Cross-model self-correction: haiku vs sonnet on pivot and refine strategies. "
        "4 agents in round-robin. Same tasks as self_correction_strategy."
    ),
    configs=[
        AgentConfig(
            name="haiku_pivot",
            model="claude-haiku-4-5",
            system_prompt=PIVOT_PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
            max_turns=10,
        ),
        AgentConfig(
            name="haiku_refine",
            model="claude-haiku-4-5",
            system_prompt=REFINE_PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
            max_turns=10,
        ),
        AgentConfig(
            name="sonnet_pivot",
            model="claude-sonnet-4-6",
            system_prompt=PIVOT_PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
            max_turns=10,
        ),
        AgentConfig(
            name="sonnet_refine",
            model="claude-sonnet-4-6",
            system_prompt=REFINE_PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
            max_turns=10,
        ),
    ],
    tasks=[
        TaskItem(
            prompt="Fix all bugs in tasks/t1/inventory.py. Run: cd tasks/t1 && python test_inventory.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="medium", tags=["arithmetic", "comparison"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t2/textstats.py. Run: cd tasks/t2 && python test_textstats.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="medium", tags=["string-processing"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t3/pqueue.py. Run: cd tasks/t3 && python test_pqueue.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="medium", tags=["data-structure"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t4/grades.py. Run: cd tasks/t4 && python test_grades.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="medium", tags=["math", "boundary"],
        ),
    ],
    setup_files=SETUP_FILES,
    setup_script="cd tasks/t1 && git init -q && git add -A && git commit -q -m init && cd ../t2 && git init -q && git add -A && git commit -q -m init && cd ../t3 && git init -q && git add -A && git commit -q -m init && cd ../t4 && git init -q && git add -A && git commit -q -m init",
    num_samples=3,
    tags=["cross-model", "self-correction", "haiku-vs-sonnet"],
)
