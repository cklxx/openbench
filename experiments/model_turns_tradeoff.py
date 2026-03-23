"""
Model × Turns Tradeoff: Haiku+20 vs Sonnet+8

Research (Snell et al., DeepMind 2024):
- Smaller model + more test-time compute CAN outperform 14x larger model
- But this breaks down on hard problems outside the base model's capability

SWE-bench data:
- Haiku 4.5 High: 44% at ~$1.31/task
- Sonnet 4.5 High: 72% at ~$9.28/task

Question: On our hard tasks, is it better to:
- Use Haiku with generous turns (cheap per turn, more iterations)
- Use Sonnet with tight turns (expensive per turn, fewer iterations needed)

Design: Same D-Hard tasks (4 × 3 bugs, genuine difficulty).
- Agent A: Haiku, max_turns=20 (generous, ~$0.04/trial)
- Agent B: Sonnet, max_turns=8 (tight, but Sonnet may need fewer turns)

4 tasks × 5 samples. If roughly cost-matched, which wins?
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
    name="model_turns_tradeoff",
    description=(
        "Haiku with generous turns (20) vs Sonnet with tight turns (8). "
        "Tests whether more turns of a cheaper model beats fewer turns of a better model. "
        "Same hard tasks (4 × 3 bugs). 4 tasks × 5 samples."
    ),
    diff=DiffSpec(
        field="model",
        description="Haiku@20turns (cheap+generous) vs Sonnet@8turns (expensive+tight)",
    ),
    agent_a=AgentConfig(
        name="haiku_20turns",
        model="claude-haiku-4-5",
        system_prompt=PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=20,
    ),
    agent_b=AgentConfig(
        name="sonnet_8turns",
        model="claude-sonnet-4-6",
        system_prompt=PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=8,
    ),
    tasks=_mod.TASKS,
    setup_files=_mod.SETUP_FILES,
    num_samples=5,
    tags=["model-tradeoff", "haiku-vs-sonnet", "turn-budget"],
)
