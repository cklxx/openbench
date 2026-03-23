"""
Posture vs Procedure on Sonnet — Testing at the Capability Edge

On Haiku, T4 (bit codec) is beyond capability — no prompt helps.
On Sonnet, T4 IS solvable — does posture vs procedure matter here?

This tests whether prompt philosophy affects performance on tasks
that are WITHIN capability but require careful reasoning.

Same hard tasks. Sonnet. 15 turns. n=8.
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "pp", os.path.join(os.path.dirname(__file__), "posture_vs_procedure.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_spec2 = importlib.util.spec_from_file_location(
    "v2", os.path.join(os.path.dirname(__file__), "real_model_selection_v2.py"))
_mod2 = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(_mod2)

from openbench.types import AgentConfig, Experiment, DiffSpec

experiment = Experiment(
    name="posture_vs_procedure_sonnet",
    description=(
        "Posture vs procedure on Sonnet where ALL tasks are solvable. "
        "Tests if prompt philosophy matters when the model CAN solve everything."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Posture vs procedure on Sonnet (all tasks within capability)",
    ),
    agent_a=AgentConfig(
        name="posture",
        model="claude-sonnet-4-6",
        system_prompt=_mod.POSTURE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    agent_b=AgentConfig(
        name="procedure",
        model="claude-sonnet-4-6",
        system_prompt=_mod.PROCEDURE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    tasks=_mod2.TASKS,
    setup_files=_mod2.SETUP_FILES,
    num_samples=8,
    tags=["prompt-philosophy", "posture-vs-procedure", "sonnet"],
)
