"""
Task Decomposition v4: Structural Guidance (Agentless-style Phases)

Research insight (Agentless, UIUC 2024):
- Simple 3-phase pipeline (localize → repair → validate) beats autonomous agents
- Phase boundaries prevent compounding errors over 30-40 turns
- Hierarchical narrowing (repo → files → functions → lines) is the key mechanism

Previous results:
- discovery: 5/5 at 20 turns, $0.064
- guided_correct: 5/5 at 20 turns, $0.038 (exact bug list)

Question: Does STRUCTURAL guidance (phases, not answers) capture some of
guided's efficiency without requiring pre-knowledge of bugs?

Agent A (discovery): "Fix all bugs" — no structure, no hints
Agent B (phased): Agentless-style 3 phases — localize, repair, validate
  - Tells agent HOW to work, not WHAT to fix
  - No bug locations, no file hints — just workflow structure

max_turns=20, num_samples=5. 8-file codebase (4 bugs).
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "wm_scale", os.path.join(os.path.dirname(__file__), "working_memory_scale.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

DISCOVERY_PROMPT = """\
You are a senior developer debugging a Python web application.

1. Run the tests to see what's failing
2. Read source files to understand the codebase
3. Fix all bugs you find
4. Run tests again to verify

Print the final test output.
"""

PHASED_PROMPT = """\
You are a senior developer debugging a Python web application.
Follow this 3-phase workflow STRICTLY:

═══ PHASE 1: LOCALIZE ═══
1. Run the test suite to see ALL failures
2. For EACH failing test, identify:
   - What the test expects vs what it gets
   - Which source file and function is responsible
3. List all bug locations before proceeding

═══ PHASE 2: REPAIR ═══
4. Read ONLY the files you identified as buggy (skip unrelated files)
5. Fix ALL bugs in a single pass — do not run tests between fixes
6. Use minimal edits — change only what's broken

═══ PHASE 3: VALIDATE ═══
7. Run the full test suite ONCE to verify all fixes
8. If any test still fails, go back to Phase 2 for that specific failure

CONSTRAINTS:
- Complete each phase fully before moving to the next
- In Phase 2, do NOT read files you didn't identify in Phase 1
- Do NOT run intermediate tests during Phase 2

Print the final test output.
"""

TASK_PROMPT = (
    "Fix all bugs in this web application. The code is in app/. "
    "Run: python test_app.py\n"
    "There are multiple bugs across different files. "
    "Print the final test output."
)

experiment = Experiment(
    name="task_decomposition_v4",
    description=(
        "Structural guidance (Agentless-style phases) vs free discovery. "
        "Phased agent gets localize→repair→validate workflow structure "
        "but NO bug locations or hints. 8-file codebase, 4 bugs."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Free discovery vs Agentless-style 3-phase structural guidance",
    ),
    agent_a=AgentConfig(
        name="discovery",
        model="claude-haiku-4-5",
        system_prompt=DISCOVERY_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=20,
    ),
    agent_b=AgentConfig(
        name="phased",
        model="claude-haiku-4-5",
        system_prompt=PHASED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=20,
    ),
    tasks=[
        TaskItem(
            prompt=TASK_PROMPT,
            expected="PASSED",
            check_fn='"PASSED" in output or "pass" in output.lower()',
            difficulty="hard",
            tags=["multi-file", "4-bugs", "8-files"],
        ),
    ],
    setup_files=_mod.SETUP_FILES,
    num_samples=5,
    tags=["task-decomposition", "structural-guidance", "agentless-style"],
)
