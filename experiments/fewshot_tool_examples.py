"""
Experiment: Few-Shot Tool Use Examples — Does showing good traces help?

LearnAct (2025) showed 19% → 52% with a single demonstration on GUI tasks.
Open question: does providing 2 concrete examples of good tool-use sequences
in the system prompt improve coding agent performance?

Agent A: Instructions only ("read before editing, run tests after changes")
Agent B: Same instructions + 2 worked examples showing the full tool-call flow

Same model (haiku), same tasks. Tests whether demonstrations anchor
behavior more reliably than instructions.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

INSTRUCTIONS = (
    "You are a coding assistant. When fixing bugs:\n"
    "1. Read the relevant files to understand the code\n"
    "2. Run the tests to see the failure\n"
    "3. Make minimal, precise edits\n"
    "4. Run tests again to verify\n"
    "Do not modify test files."
)

EXAMPLES = INSTRUCTIONS + """

## Example 1: Fixing an off-by-one error

Task: "Fix the bug in counter.py. Run test_counter.py."

Good tool sequence:
1. Read test_counter.py → understand expected behavior
2. Read counter.py → find the bug (range(n) should be range(n+1))
3. Edit counter.py → change line 5: range(n) to range(n+1)
4. Bash: python test_counter.py → verify all tests pass

## Example 2: Fixing a missing import

Task: "Fix the bug in utils.py. Run test_utils.py."

Good tool sequence:
1. Bash: python test_utils.py → see error: "NameError: name 'json' is not defined"
2. Read utils.py → see json.loads() used but no import
3. Edit utils.py → add "import json" at top
4. Bash: python test_utils.py → verify all tests pass

Key patterns:
- Always READ before EDIT (understand context first)
- Run tests BEFORE and AFTER changes
- Make the SMALLEST change that fixes the issue
"""

SETUP_FILES = {
    # ── 6 bug-fix tasks of varying complexity ────────────────────────────

    # Bug 1: Missing return
    "tasks/task1/calc.py": '''\
def calculate_total(items):
    """Calculate total price of items with tax."""
    subtotal = sum(item["price"] * item["qty"] for item in items)
    tax = subtotal * 0.08
    total = subtotal + tax
    # Bug: missing return statement
''',
    "tasks/task1/test_calc.py": '''\
from calc import calculate_total
items = [{"price": 10.0, "qty": 2}, {"price": 5.0, "qty": 3}]
result = calculate_total(items)
assert result is not None, "Function returned None"
assert abs(result - 37.8) < 0.01, f"Expected 37.8, got {result}"
print("test_calc: PASSED")
''',

    # Bug 2: Wrong operator
    "tasks/task2/validator.py": '''\
def is_valid_range(value, min_val, max_val):
    """Check if value is within [min_val, max_val] inclusive."""
    return min_val <= value or value <= max_val  # Bug: or should be and
''',
    "tasks/task2/test_validator.py": '''\
from validator import is_valid_range
assert is_valid_range(5, 1, 10) == True
assert is_valid_range(0, 1, 10) == False  # Below range
assert is_valid_range(11, 1, 10) == False  # Above range
assert is_valid_range(1, 1, 10) == True   # Boundary
assert is_valid_range(10, 1, 10) == True  # Boundary
print("test_validator: PASSED")
''',

    # Bug 3: Dict mutation during iteration
    "tasks/task3/registry.py": '''\
class Registry:
    def __init__(self):
        self.items = {}

    def register(self, name, value):
        self.items[name] = value

    def remove_expired(self, is_expired_fn):
        """Remove items where is_expired_fn(value) returns True."""
        for name, value in self.items.items():  # Bug: iterating while modifying
            if is_expired_fn(value):
                del self.items[name]
''',
    "tasks/task3/test_registry.py": '''\
from registry import Registry
r = Registry()
r.register("a", {"ts": 1})
r.register("b", {"ts": 100})
r.register("c", {"ts": 2})
r.remove_expired(lambda v: v["ts"] < 50)
assert "b" in r.items, f"b should remain: {r.items}"
assert "a" not in r.items
assert "c" not in r.items
assert len(r.items) == 1
print("test_registry: PASSED")
''',

    # Bug 4: String encoding issue
    "tasks/task4/encoder.py": '''\
def encode_url(url):
    """Simple URL encoding for special characters."""
    replacements = {
        " ": "%20",
        "&": "%26",
        "=": "%3D",
        "?": "%3F",
        "#": "%23",
    }
    result = url
    for char, encoded in replacements.items():
        result = result.replace(char, encoded)
    return result

def decode_url(encoded_url):
    """Decode URL-encoded string."""
    replacements = {
        "%20": " ",
        "%26": "&",
        "%3D": "=",
        "%3F": "?",
        "%23": "#",
    }
    result = encoded_url
    for encoded, char in replacements.items():
        result = result.replace(encoded, char)
    return result
''',
    "tasks/task4/test_encoder.py": '''\
from encoder import encode_url, decode_url
# Basic encoding
assert encode_url("hello world") == "hello%20world"
assert encode_url("a=1&b=2") == "a%3D1%26b%3D2"
# Roundtrip
original = "search?q=hello world&page=1#results"
assert decode_url(encode_url(original)) == original, f"Roundtrip failed: {decode_url(encode_url(original))}"
# Double encoding should NOT happen
assert encode_url("%20") == "%20", f"Double encoded: {encode_url('%20')}"
print("test_encoder: PASSED")
''',

    # Bug 5: Logic error in tree traversal
    "tasks/task5/tree.py": '''\
class TreeNode:
    def __init__(self, val, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

def max_depth(root):
    """Return the maximum depth of a binary tree."""
    if root is None:
        return 0
    return 1 + max(max_depth(root.left), max_depth(root.right))

def is_balanced(root):
    """Check if tree is height-balanced (depth of subtrees differs by at most 1)."""
    if root is None:
        return True
    left_depth = max_depth(root.left)
    right_depth = max_depth(root.right)
    # Bug: only checks root, not recursively
    return abs(left_depth - right_depth) <= 1
''',
    "tasks/task5/test_tree.py": '''\
from tree import TreeNode, max_depth, is_balanced
# Balanced tree
t1 = TreeNode(1, TreeNode(2, TreeNode(4), TreeNode(5)), TreeNode(3))
assert max_depth(t1) == 3
assert is_balanced(t1) == True

# Unbalanced at root — easy case
t2 = TreeNode(1, TreeNode(2, TreeNode(3, TreeNode(4), None), None), None)
assert is_balanced(t2) == False

# Tricky: balanced at root but unbalanced in subtree
t3 = TreeNode(1,
    TreeNode(2, TreeNode(4, TreeNode(6), None), TreeNode(5)),
    TreeNode(3, None, TreeNode(7))
)
# Left subtree depth: 3 (1->2->4->6). Right subtree depth: 2 (1->3->7).
# Root: |3-2|=1 OK. But left subtree: left=2 (4->6), right=1 (5). |2-1|=1 OK actually.
# Let me make it truly unbalanced in subtree:
t4 = TreeNode(1,
    TreeNode(2, TreeNode(4, TreeNode(6, TreeNode(8), None), None), TreeNode(5)),
    TreeNode(3, None, TreeNode(7))
)
# Root: left_depth=4, right_depth=2. |4-2|=2 > 1. Not balanced.
assert is_balanced(t4) == False

# But what about this one where root LOOKS balanced:
t5 = TreeNode(1,
    TreeNode(2, TreeNode(4, TreeNode(6, TreeNode(8), None), None), None),
    TreeNode(3, None, TreeNode(5, None, TreeNode(7, None, TreeNode(9))))
)
# Both sides have depth 4. Root: |4-4|=0. But each subtree is a chain (unbalanced).
assert is_balanced(t5) == False, "Subtrees are chains — not balanced"

print("test_tree: PASSED")
''',

    # Bug 6: Async-like callback ordering
    "tasks/task6/pipeline.py": '''\
class Pipeline:
    """Data processing pipeline with middleware-style transforms."""
    def __init__(self):
        self.steps = []

    def add_step(self, name, transform_fn):
        self.steps.append((name, transform_fn))

    def process(self, data):
        """Run data through all steps in order, collecting results."""
        results = {"input": data, "steps": [], "output": None}
        current = data
        for name, fn in self.steps:
            try:
                current = fn(current)
                results["steps"].append({"name": name, "status": "ok", "output": current})
            except Exception as e:
                results["steps"].append({"name": name, "status": "error", "error": str(e)})
                results["output"] = current  # Bug: should break on error, not continue
        results["output"] = current
        return results
''',
    "tasks/task6/test_pipeline.py": '''\
from pipeline import Pipeline

# Normal flow
p = Pipeline()
p.add_step("double", lambda x: x * 2)
p.add_step("add_one", lambda x: x + 1)
result = p.process(5)
assert result["output"] == 11, f"Expected 11, got {result['output']}"
assert len(result["steps"]) == 2
assert all(s["status"] == "ok" for s in result["steps"])

# Error should stop pipeline
p2 = Pipeline()
p2.add_step("parse", lambda x: int(x))
p2.add_step("double", lambda x: x * 2)  # Should NOT run
p2.add_step("format", lambda x: f"result={x}")  # Should NOT run
result2 = p2.process("abc")
assert result2["steps"][0]["status"] == "error"
# Pipeline should stop after error — only 1 step should have run
error_steps = [s for s in result2["steps"] if s["status"] == "error"]
ok_steps = [s for s in result2["steps"] if s["status"] == "ok"]
assert len(error_steps) == 1, f"Should have exactly 1 error step, got {len(error_steps)}"
assert len(ok_steps) == 0, f"No steps should succeed after error, got {len(ok_steps)}"
assert result2["output"] == "abc", f"Output should be last good value (input), got {result2['output']}"

print("test_pipeline: PASSED")
''',
}

experiment = Experiment(
    name="fewshot_tool_examples",
    description=(
        "Instructions-only vs instructions + 2 worked examples of good tool use. "
        "Same model (haiku), 6 bug-fix tasks."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Instructions-only vs instructions + few-shot tool-use examples",
    ),
    agent_a=AgentConfig(
        name="instructions_only",
        model="claude-haiku-4-5",
        system_prompt=INSTRUCTIONS,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=10,
    ),
    agent_b=AgentConfig(
        name="with_examples",
        model="claude-haiku-4-5",
        system_prompt=EXAMPLES,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=10,
    ),
    tasks=[
        TaskItem(
            prompt=f"Fix the bug in tasks/task{i}/. Run the test to verify.",
            expected="PASSED",
            check_fn='"passed" in output.lower()',
            difficulty=d,
            tags=["bug-fix", t],
        )
        for i, d, t in [
            (1, "easy", "missing-return"),
            (2, "easy", "wrong-operator"),
            (3, "medium", "dict-mutation"),
            (4, "medium", "double-encoding"),
            (5, "hard", "recursive-check"),
            (6, "hard", "error-propagation"),
        ]
    ],
    setup_files=SETUP_FILES,
    num_samples=3,
    tags=["few-shot", "tool-examples", "agent-optimization"],
)
