"""
Task Decomposition v2: Discovery vs Guided with Generous Turns

v1 found guided wins 5/5 vs 0/5 with max_turns=12 — discovery hit turn limit.
v2 increases to max_turns=20 so both can finish. The question becomes:
when both CAN complete, does guided still win (faster/cheaper) or do they tie?

If guided still wins: pre-knowledge helps even with enough turns
If they tie: pre-knowledge only matters under turn pressure
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

GUIDED_PROMPT = """\
You are a senior developer debugging a Python web application.

The team has identified these 4 bugs. Fix each one:

1. **app/config.py line 3** — MAX_CACHE_SIZE is 5 but should be 50.
   The cache needs to hold 20+ items without eviction.

2. **app/validators.py line 9** — Email regex doesn't allow '+' in local part.
   Add '+' to the character class: [a-zA-Z0-9._+-]

3. **app/services.py line 21** — UserService.update_email() doesn't invalidate
   the cache after update. Add: self.cache.invalidate(f"user:{username}")

4. **app/auth.py lines 13,20** — register() and authenticate() both call
   password.lower() before hashing, making passwords case-insensitive.
   Remove both .lower() calls.

After fixing all 4, run the tests to verify.
Print the final test output.
"""

TASK_PROMPT = (
    "Fix all bugs in this web application. The code is in app/. "
    "Run: python test_app.py\n"
    "There are multiple bugs across different files. "
    "Print the final test output."
)

experiment = Experiment(
    name="task_decomposition_v2",
    description=(
        "Discovery vs guided with generous turns (max_turns=20). "
        "v1 showed guided wins under pressure (12 turns). "
        "v2 tests whether guided still wins when both can finish."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Generic discovery vs exact bug list — generous turn budget",
    ),
    agent_a=AgentConfig(
        name="discovery",
        model="claude-haiku-4-5",
        system_prompt=DISCOVERY_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=20,
    ),
    agent_b=AgentConfig(
        name="guided",
        model="claude-haiku-4-5",
        system_prompt=GUIDED_PROMPT,
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
    tags=["task-decomposition", "discovery-vs-guided", "generous-turns"],
)
