"""
Task Decomposition Mechanism Test: Why Hints Hurt on Hard Tasks

Trace analysis revealed the mechanism:
- Discovery: run tests → concrete errors → targeted fix → verify (feedback loop)
- Guided: parse hints → read code → match to hints → fix → verify last (NO feedback loop)

Hints DISPLACE the test-feedback loop. The agent trusts hints instead of running
tests, losing its error-correction mechanism.

Hypothesis: If we give hints BUT force the agent to run tests first,
we can recover the benefit of hints without losing the feedback loop.

3-way comparison (using DiffSpec on system_prompt):
- Agent A: discovery (no hints, run tests naturally)
- Agent B: guided_test_first (hints + MUST run tests before any edit)

Same 4 hard tasks, max_turns=8, n=5.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

# Import SETUP_FILES from the hard experiment
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "dh", os.path.join(os.path.dirname(__file__), "task_decomposition_hard.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

DISCOVERY_PROMPT = """\
You are debugging Python code. Fix all bugs and make all tests pass.
Print the final test output.
"""

# Hints + forced test-first: combines pre-knowledge with feedback loop
GUIDED_TEST_FIRST_PROMPT = """\
You are debugging Python code. The team has identified these bugs:

**tasks/t1/bank.py:**
1. withdraw() doesn't check if balance is sufficient — add a balance check
2. transfer() deducts fee from recipient instead of charging sender — sender should pay amount + fee, recipient gets full amount
3. apply_interest() uses self.balance but should use self.opening_balance

**tasks/t2/limiter.py:**
1. is_allowed() always returns True — add check: if len >= max_requests return False
2. _cleanup() comparison is inverted — should keep requests where now - t < window
3. get_remaining() should call _cleanup first to purge expired requests

**tasks/t3/mdtable.py:**
1. Header cells aren't stripped of whitespace after split
2. Separator line detection assumes fixed position — detect --- dynamically
3. Type conversion edge cases — check carefully

**tasks/t4/emitter.py:**
1. emit() doesn't pass *args/**kwargs to handler function calls
2. once() registers with once=False instead of once=True
3. off(event, handler) clears ALL handlers instead of only the specified one

CRITICAL WORKFLOW — you MUST follow this order:
1. FIRST: Run the test to see ACTUAL error messages
2. THEN: Read the source file
3. THEN: Fix all bugs in ONE pass (use hints above to guide your fixes)
4. FINALLY: Run tests again to verify

You are FORBIDDEN from using Edit before running the tests at least once.
The test output is your ground truth — use it to validate the hints above.

Print the final test output.
"""

experiment = Experiment(
    name="task_decomposition_mechanism",
    description=(
        "Mechanism test: can guided + forced test-first recover the feedback loop? "
        "Discovery (no hints, natural workflow) vs guided+test-first (hints + must run tests first). "
        "4 hard tasks × 8 turns × 5 samples."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Discovery vs guided with forced test-first workflow",
    ),
    agent_a=AgentConfig(
        name="discovery",
        model="claude-haiku-4-5",
        system_prompt=DISCOVERY_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=8,
    ),
    agent_b=AgentConfig(
        name="guided_test_first",
        model="claude-haiku-4-5",
        system_prompt=GUIDED_TEST_FIRST_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=8,
    ),
    tasks=_mod.TASKS,
    setup_files=_mod.SETUP_FILES,
    num_samples=5,
    tags=["task-decomposition", "mechanism-test", "hints-plus-feedback"],
)
