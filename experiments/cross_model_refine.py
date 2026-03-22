"""
Cross-Model: Haiku vs Sonnet on Refine Strategy

Direct A/B: same refine prompt, same tasks, different model.
Tests whether Sonnet's stronger reasoning makes refine even more effective,
or if the model gap matters more than the strategy gap.

Uses same tasks as self_correction_strategy (independent bugs).
num_samples=3 to keep Sonnet costs manageable.
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "sc_v1", os.path.join(os.path.dirname(__file__), "self_correction_strategy.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

experiment = Experiment(
    name="cross_model_refine",
    description=(
        "Haiku vs Sonnet on refine strategy. Same tasks, same prompt. "
        "Tests model capability gap on self-correction tasks."
    ),
    diff=DiffSpec(
        field="model",
        description="Haiku vs Sonnet on identical refine strategy",
    ),
    agent_a=AgentConfig(
        name="haiku_refine",
        model="claude-haiku-4-5",
        system_prompt=_mod.REFINE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=10,
    ),
    agent_b=AgentConfig(
        name="sonnet_refine",
        model="claude-sonnet-4-6",
        system_prompt=_mod.REFINE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=10,
    ),
    tasks=[
        TaskItem(
            prompt="Fix all bugs in tasks/t1/inventory.py. Run: cd tasks/t1 && python test_inventory.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="medium", tags=["arithmetic"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t2/textstats.py. Run: cd tasks/t2 && python test_textstats.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="medium", tags=["string"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t3/pqueue.py. Run: cd tasks/t3 && python test_pqueue.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="medium", tags=["data-structure"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t4/grades.py. Run: cd tasks/t4 && python test_grades.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="medium", tags=["math"],
        ),
    ],
    setup_files=_mod.SETUP_FILES,
    setup_script="cd tasks/t1 && git init -q && git add -A && git commit -q -m init && cd ../t2 && git init -q && git add -A && git commit -q -m init && cd ../t3 && git init -q && git add -A && git commit -q -m init && cd ../t4 && git init -q && git add -A && git commit -q -m init",
    num_samples=3,
    tags=["cross-model", "haiku-vs-sonnet", "refine"],
)
