"""
Parallel Sampling vs Sequential Depth: Same Compute, Different Allocation

Research (Large Language Monkeys, Stanford 2024):
- Coverage scales as power law with number of samples
- With verifier (tests), parallel sampling scales to extraordinary levels
- DeepSeek-Coder: 15.9% (1 sample) → 56% (250 samples) on SWE-bench

Research (RISE, NeurIPS 2024):
- Sequential multi-turn refinement outperforms parallel sampling at equal samples
- 5-turn sequential > 5x parallel at same total samples

Question: For bug fixing (where tests = verifier), is it better to:
- Give 1 attempt with 20 turns (deep sequential)
- Give many short attempts of 5 turns each (broad parallel)

Both use roughly the same total compute. But:
- Deep: agent can iterate and refine within one session
- Broad: each attempt is independent, but pass@k increases with samples

Design: Both agents use same system prompt. Diff is max_turns.
- Agent A: max_turns=5 (short attempts — relies on pass@k)
- Agent B: max_turns=20 (deep attempt — relies on iteration)
num_samples=8 to compute pass@k up to pass@8.

Key comparison:
- Agent A pass@4 (4 short attempts = 20 turn-equivalents)
- Agent B pass@1 (1 deep attempt = 20 turn-equivalents)

4 hard tasks × 8 samples = 32 trials per agent.
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "dh", os.path.join(os.path.dirname(__file__), "task_decomposition_hard.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

PROMPT = """\
You are debugging Python code. Fix all bugs and make all tests pass.
Print the final test output.
"""

experiment = Experiment(
    name="parallel_vs_sequential",
    description=(
        "Same total compute, different allocation: many short attempts (5 turns × k) "
        "vs one deep attempt (20 turns × 1). Bug fixing has a verifier (tests), "
        "so parallel sampling should benefit. 4 hard tasks × 8 samples."
    ),
    diff=DiffSpec(
        field="max_turns",
        description="Shallow+broad (5 turns, rely on pass@k) vs deep+narrow (20 turns, rely on iteration)",
    ),
    agent_a=AgentConfig(
        name="shallow_5turns",
        model="claude-haiku-4-5",
        system_prompt=PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=5,
    ),
    agent_b=AgentConfig(
        name="deep_20turns",
        model="claude-haiku-4-5",
        system_prompt=PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=20,
    ),
    tasks=_mod.TASKS,
    setup_files=_mod.SETUP_FILES,
    num_samples=8,
    tags=["parallel-vs-sequential", "pass-at-k", "compute-allocation"],
)
