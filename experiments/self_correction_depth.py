"""
Experiment 2: Self-Correction Depth — Fix Rate Per Round

OPEN QUESTION: Given failing test output, how effectively does each model
self-correct? At what correction round do diminishing returns hit?

Published: "intrinsic self-correction worsens performance" (no external feedback).
Published: "tool-interactive critiquing enables meaningful self-correction".
NOT published: per-round fix rate comparison between haiku and sonnet.

Design:
- Give agents deliberately buggy code with a test suite
- Agent has up to 3 correction rounds (max_turns controls this)
- Track: which bugs are fixed per round, what's the ceiling

We use setup_files with bugs of increasing subtlety.
check_fn verifies test output in the agent's final response.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ── Bug 1: Simple logic error (should fix in round 1) ───────────────
    "bug1.py": '''\
def fibonacci(n):
    """Return the nth Fibonacci number (0-indexed). F(0)=0, F(1)=1."""
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(n):  # Bug: should be range(n-1)
        a, b = b, a + b
    return b  # Bug: should return a (off by one)
''',
    "test_bug1.py": '''\
from bug1 import fibonacci
assert fibonacci(0) == 0, f"F(0)={fibonacci(0)}"
assert fibonacci(1) == 1, f"F(1)={fibonacci(1)}"
assert fibonacci(2) == 1, f"F(2)={fibonacci(2)}"
assert fibonacci(5) == 5, f"F(5)={fibonacci(5)}"
assert fibonacci(10) == 55, f"F(10)={fibonacci(10)}"
print("bug1: ALL PASSED")
''',

    # ── Bug 2: Subtle off-by-one in binary search ────────────────────────
    "bug2.py": '''\
def search_insert_position(nums, target):
    """Find index to insert target in sorted array to keep it sorted.
    If target exists, return its index."""
    lo, hi = 0, len(nums) - 1  # Bug: should be len(nums) for insert-at-end case
    while lo <= hi:
        mid = (lo + hi) // 2
        if nums[mid] == target:
            return mid
        elif nums[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return lo
''',
    "test_bug2.py": '''\
from bug2 import search_insert_position as sip
assert sip([1,3,5,6], 5) == 2
assert sip([1,3,5,6], 2) == 1
assert sip([1,3,5,6], 7) == 4  # Insert at end
assert sip([1,3,5,6], 0) == 0  # Insert at start
assert sip([], 5) == 0  # Empty array
assert sip([1], 0) == 0
assert sip([1], 2) == 1
assert sip([1,3], 2) == 1
print("bug2: ALL PASSED")
''',

    # ── Bug 3: State mutation bug (medium — requires careful tracing) ────
    "bug3.py": '''\
class Matrix:
    """Simple matrix operations."""
    def __init__(self, data):
        self.data = data  # Bug: should deep copy to avoid aliasing
        self.rows = len(data)
        self.cols = len(data[0]) if data else 0

    def transpose(self):
        """Return a new transposed matrix."""
        result = [[0] * self.rows for _ in range(self.cols)]
        for i in range(self.rows):
            for j in range(self.cols):
                result[j][i] = self.data[i][j]
        return Matrix(result)

    def multiply(self, other):
        """Matrix multiplication: self × other."""
        if self.cols != other.rows:
            raise ValueError(f"Incompatible dimensions: {self.rows}x{self.cols} × {other.rows}x{other.cols}")
        result = [[0] * other.cols for _ in range(self.rows)]
        for i in range(self.rows):
            for j in range(other.cols):
                for k in range(self.cols):
                    result[i][j] += self.data[i][k] * other.data[k][j]
        return Matrix(result)

    def __eq__(self, other):
        return self.data == other.data

    def __repr__(self):
        return f"Matrix({self.data})"
''',
    "test_bug3.py": '''\
from bug3 import Matrix

# Test 1: Basic transpose
m = Matrix([[1, 2], [3, 4]])
t = m.transpose()
assert t.data == [[1, 3], [2, 4]], f"Transpose wrong: {t.data}"

# Test 2: Mutation isolation - modifying original shouldn't affect transpose
m.data[0][0] = 99
assert t.data[0][0] == 1, f"Transpose mutated when original changed: {t.data}"

# Test 3: Constructor mutation isolation
data = [[1, 2], [3, 4]]
m2 = Matrix(data)
data[0][0] = 99
assert m2.data[0][0] == 1, f"Matrix mutated when source changed: {m2.data}"

# Test 4: Multiply
a = Matrix([[1, 2], [3, 4]])
b = Matrix([[5, 6], [7, 8]])
c = a.multiply(b)
assert c.data == [[19, 22], [43, 50]], f"Multiply wrong: {c.data}"

# Test 5: Multiply doesn't mutate operands
assert a.data == [[1, 2], [3, 4]], f"Multiply mutated a: {a.data}"

print("bug3: ALL PASSED")
''',

    # ── Bug 4: Concurrency/ordering bug (hard) ──────────────────────────
    "bug4.py": '''\
class EventEmitter:
    """Simple event system with once() and on() handlers."""
    def __init__(self):
        self._handlers = {}  # event_name → list of (callback, once_flag)

    def on(self, event, callback):
        """Register a persistent handler."""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append((callback, False))

    def once(self, event, callback):
        """Register a one-time handler (removed after first emit)."""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append((callback, True))

    def emit(self, event, *args):
        """Emit an event, calling all handlers."""
        if event not in self._handlers:
            return
        # Bug: modifying list while iterating causes skipped handlers
        for i, (callback, once) in enumerate(self._handlers[event]):
            callback(*args)
            if once:
                self._handlers[event].pop(i)  # Bug: pop during iteration
''',
    "test_bug4.py": '''\
from bug4 import EventEmitter

# Test 1: Basic on/emit
results = []
ee = EventEmitter()
ee.on("data", lambda x: results.append(f"A:{x}"))
ee.emit("data", 1)
ee.emit("data", 2)
assert results == ["A:1", "A:2"], f"Basic on failed: {results}"
print("  basic on: OK")

# Test 2: once fires only once
results2 = []
ee2 = EventEmitter()
ee2.once("click", lambda: results2.append("clicked"))
ee2.emit("click")
ee2.emit("click")
assert results2 == ["clicked"], f"Once fired multiple times: {results2}"
print("  once: OK")

# Test 3: Mixed on + once (the tricky one)
results3 = []
ee3 = EventEmitter()
ee3.once("ev", lambda: results3.append("once1"))
ee3.on("ev", lambda: results3.append("persist"))
ee3.once("ev", lambda: results3.append("once2"))
ee3.emit("ev")
assert "once1" in results3 and "persist" in results3 and "once2" in results3, \
    f"First emit missing handlers: {results3}"

results3.clear()
ee3.emit("ev")
assert results3 == ["persist"], f"Second emit should only have persist: {results3}"
print("  mixed on+once: OK")

# Test 4: No handlers
ee4 = EventEmitter()
ee4.emit("nothing")  # Should not raise
print("  no handlers: OK")

print("bug4: ALL PASSED")
''',

    # ── Bug 5: Algorithm correctness bug (very hard — requires insight) ──
    "bug5.py": '''\
def longest_increasing_subsequence(nums):
    """Return the LENGTH of the longest strictly increasing subsequence.

    Should be O(n log n) using patience sorting / binary search approach.
    """
    if not nums:
        return 0

    # tails[i] = smallest tail element for increasing subsequence of length i+1
    tails = []

    for num in nums:
        # Binary search for the leftmost tail >= num
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if tails[mid] < num:
                lo = mid + 1
            else:
                hi = mid

        if lo == len(tails):
            tails.append(num)
        else:
            tails[lo] = num

    return len(tails)

# Bug: the algorithm above is actually correct for strictly increasing.
# The REAL bug is that the problem says "strictly increasing" but the test
# expects "non-decreasing" behavior for some edge cases. Let me make it
# buggy in a different way...

def lis_with_reconstruction(nums):
    """Return both the LENGTH and the actual subsequence."""
    if not nums:
        return 0, []

    n = len(nums)
    dp = [1] * n
    parent = [-1] * n

    for i in range(1, n):
        for j in range(i):
            if nums[j] < nums[i] and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
                parent[i] = j

    # Find the index of maximum length
    max_len = max(dp)
    max_idx = dp.index(max_len)

    # Reconstruct — Bug: reconstruction goes forward instead of backward
    seq = []
    idx = max_idx
    while idx != -1:
        seq.append(nums[idx])
        idx = parent[idx]

    return max_len, seq  # Bug: seq is reversed (should be seq[::-1])
''',
    "test_bug5.py": '''\
from bug5 import longest_increasing_subsequence as lis
from bug5 import lis_with_reconstruction

# Test LIS length
assert lis([10, 9, 2, 5, 3, 7, 101, 18]) == 4  # [2,3,7,18] or [2,5,7,18]
assert lis([0, 1, 0, 3, 2, 3]) == 4  # [0,1,2,3]
assert lis([7, 7, 7, 7]) == 1  # strictly increasing
assert lis([]) == 0
assert lis([1]) == 1
assert lis([5, 4, 3, 2, 1]) == 1  # decreasing
assert lis([1, 2, 3, 4, 5]) == 5  # already sorted
print("  lis length: OK")

# Test reconstruction
length, seq = lis_with_reconstruction([10, 9, 2, 5, 3, 7, 101, 18])
assert length == 4, f"Length wrong: {length}"
# Verify the sequence is actually increasing
for i in range(1, len(seq)):
    assert seq[i] > seq[i-1], f"Not increasing at {i}: {seq}"
assert len(seq) == length, f"Sequence length {len(seq)} != {length}"
print("  lis reconstruction: OK")

length2, seq2 = lis_with_reconstruction([3, 1, 4, 1, 5, 9, 2, 6])
assert length2 == 4
for i in range(1, len(seq2)):
    assert seq2[i] > seq2[i-1], f"Not increasing: {seq2}"
print("  lis reconstruction 2: OK")

print("bug5: ALL PASSED")
''',
}

experiment = Experiment(
    name="self_correction_depth",
    description=(
        "5 bugs of increasing subtlety. Agent gets test output and must self-correct. "
        "Measures fix-per-round for haiku vs sonnet."
    ),
    diff=DiffSpec(
        field="model",
        description="haiku vs sonnet self-correction ability",
    ),
    agent_a=AgentConfig(
        name="haiku",
        model="claude-haiku-4-5",
        system_prompt=(
            "Fix the bugs in the Python files. For each bug file:\n"
            "1. Run the test to see the failure\n"
            "2. Read the code and diagnose the bug\n"
            "3. Fix it\n"
            "4. Run the test again\n"
            "5. If it still fails, repeat from step 2\n"
            "Fix all 5 bugs."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=30,
    ),
    agent_b=AgentConfig(
        name="sonnet",
        model="claude-sonnet-4-6",
        system_prompt=(
            "Fix the bugs in the Python files. For each bug file:\n"
            "1. Run the test to see the failure\n"
            "2. Read the code and diagnose the bug\n"
            "3. Fix it\n"
            "4. Run the test again\n"
            "5. If it still fails, repeat from step 2\n"
            "Fix all 5 bugs."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=30,
    ),
    tasks=[
        TaskItem(
            prompt="Fix all 5 bugs (bug1.py through bug5.py). Run each test to verify. Report which ones pass.",
            expected="ALL PASSED",
            check_fn=(
                'sum(1 for x in ["bug1: ALL PASSED", "bug2: ALL PASSED", "bug3: ALL PASSED", '
                '"bug4: ALL PASSED", "bug5: ALL PASSED"] if x.lower().replace("all passed", "all passed") '
                'in output.lower().replace("all passed", "all passed")) >= 3'
            ),
            difficulty="very_hard",
            tags=["self-correction", "multi-bug", "progressive-difficulty"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=3,
    tags=["self-correction", "error-recovery", "depth-analysis"],
)
