"""
Experiment: Competitive Programming — Algorithmic Insight Required

Problems where:
- Naive brute-force is obvious but O(n²) or worse → TLE on large inputs
- Correct solution requires a specific algorithmic insight
- Edge cases are tricky
- Must pass both correctness AND performance tests

Tests whether model capability (haiku vs sonnet) matters when algorithmic
insight — not just implementation — is the bottleneck.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ── Problem 1: Maximum Subarray with Exactly K Distinct Elements ─────
    "p1_subarray.py": '''\
"""
Find the length of the longest contiguous subarray with EXACTLY k distinct elements.

Input: nums (list of ints), k (int)
Output: length of longest such subarray, or 0 if impossible

Constraints: 1 ≤ len(nums) ≤ 100,000; 1 ≤ k ≤ len(nums)

Example: nums=[1,2,1,2,3], k=2 → 4 (subarray [1,2,1,2])
Example: nums=[1,2,1,3,4], k=3 → 3 (subarray [2,1,3] or [1,3,4])
Example: nums=[1,1,1], k=2 → 0
"""
def longest_subarray_k_distinct(nums, k):
    raise NotImplementedError
''',
    "test_p1.py": '''\
import time
from p1_subarray import longest_subarray_k_distinct as solve

# Correctness tests
assert solve([1,2,1,2,3], 2) == 4
assert solve([1,2,1,3,4], 3) == 3
assert solve([1,1,1], 2) == 0
assert solve([1], 1) == 1
assert solve([1,2,3,4,5], 5) == 5
assert solve([1,2,3,4,5], 1) == 1
assert solve([1,1,2,2,3,3], 2) == 4
assert solve([1,2,1,2,1,2], 2) == 6
assert solve([], 1) == 0
assert solve([4,3,2,1,4,3,2,1], 4) == 8
print("Correctness: PASSED")

# Performance test: must handle 100k elements in < 1 second
import random
random.seed(42)
big = [random.randint(1, 50) for _ in range(100_000)]
start = time.time()
result = solve(big, 25)
elapsed = time.time() - start
assert elapsed < 1.0, f"Too slow: {elapsed:.2f}s (must be < 1s)"
assert result > 0, f"Expected positive result, got {result}"
print(f"Performance: PASSED ({elapsed:.3f}s)")
print("ALL PASSED")
''',

    # ── Problem 2: Minimum Number of Jumps ───────────────────────────────
    "p2_jumps.py": '''\
"""
Given an array of non-negative integers where each element represents the
maximum jump length from that position, find the minimum number of jumps
to reach the last index from the first index.

Input: nums (list of non-negative ints, len ≥ 1)
Output: minimum jumps, or -1 if impossible

Constraints: 1 ≤ len(nums) ≤ 100,000

Example: nums=[2,3,1,1,4] → 2 (jump 1→2, then 2→5)
Example: nums=[2,3,0,1,4] → 2
Example: nums=[1,1,1,1,1] → 4
Example: nums=[0,1,2] → -1 (stuck at index 0)
"""
def min_jumps(nums):
    raise NotImplementedError
''',
    "test_p2.py": '''\
import time
from p2_jumps import min_jumps as solve

# Correctness
assert solve([2,3,1,1,4]) == 2
assert solve([2,3,0,1,4]) == 2
assert solve([1,1,1,1,1]) == 4
assert solve([0,1,2]) == -1
assert solve([1]) == 0
assert solve([5,4,3,2,1,0,0]) == -1  # can reach end? 5→5(idx5), val=0, stuck. But 5 can jump to idx5. idx5=0. Can't reach idx6. So -1.
assert solve([5,4,3,2,1,1,0]) == 2  # 0→5→6
assert solve([1,2,3]) == 2  # 0→1→3
assert solve([10,0,0,0,0,0,0,0,0,0,1]) == 1  # jump straight to end
assert solve([3,2,1,0,4]) == -1  # stuck at index 3
print("Correctness: PASSED")

# Performance
import random
random.seed(123)
big = [random.randint(1, 10) for _ in range(100_000)]
start = time.time()
result = solve(big)
elapsed = time.time() - start
assert elapsed < 1.0, f"Too slow: {elapsed:.2f}s"
assert result > 0
print(f"Performance: PASSED ({elapsed:.3f}s)")
print("ALL PASSED")
''',

    # ── Problem 3: Count Inversions (merge sort variant) ─────────────────
    "p3_inversions.py": '''\
"""
Count the number of inversions in an array. An inversion is a pair (i, j)
where i < j but nums[i] > nums[j].

Input: nums (list of ints)
Output: number of inversions (int)

Constraints: 1 ≤ len(nums) ≤ 100,000

Example: [2,4,1,3,5] → 3 inversions: (2,1), (4,1), (4,3)
Example: [5,4,3,2,1] → 10 inversions (all pairs)
Example: [1,2,3,4,5] → 0

Note: O(n²) brute force will TLE. Need O(n log n) solution.
"""
def count_inversions(nums):
    raise NotImplementedError
''',
    "test_p3.py": '''\
import time
from p3_inversions import count_inversions as solve

# Correctness
assert solve([2,4,1,3,5]) == 3
assert solve([5,4,3,2,1]) == 10
assert solve([1,2,3,4,5]) == 0
assert solve([1]) == 0
assert solve([2,1]) == 1
assert solve([3,1,2]) == 2
assert solve([1,5,3,2,4]) == 4
print("Correctness: PASSED")

# Performance: 100k elements in < 2 seconds
import random
random.seed(777)
big = list(range(100_000, 0, -1))  # worst case: fully reversed
start = time.time()
result = solve(big)
elapsed = time.time() - start
expected = 100_000 * 99_999 // 2  # n*(n-1)/2
assert result == expected, f"Expected {expected}, got {result}"
assert elapsed < 2.0, f"Too slow: {elapsed:.2f}s (must be < 2s)"
print(f"Performance: PASSED ({elapsed:.3f}s)")

# Random case
big2 = random.sample(range(100_000), 100_000)
start = time.time()
result2 = solve(big2)
elapsed2 = time.time() - start
assert elapsed2 < 2.0, f"Random case too slow: {elapsed2:.2f}s"
assert 0 <= result2 <= 100_000 * 99_999 // 2
print(f"Random perf: PASSED ({elapsed2:.3f}s)")
print("ALL PASSED")
''',

    # ── Problem 4: Trapping Rain Water ───────────────────────────────────
    "p4_water.py": '''\
"""
Given n non-negative integers representing an elevation map where the width
of each bar is 1, compute how much water can be trapped after raining.

Input: height (list of non-negative ints)
Output: total units of trapped water

Constraints: 1 ≤ len(height) ≤ 100,000

Example: height=[0,1,0,2,1,0,1,3,2,1,2,1] → 6
Example: height=[4,2,0,3,2,5] → 9
"""
def trap(height):
    raise NotImplementedError
''',
    "test_p4.py": '''\
import time
from p4_water import trap as solve

# Correctness
assert solve([0,1,0,2,1,0,1,3,2,1,2,1]) == 6
assert solve([4,2,0,3,2,5]) == 9
assert solve([]) == 0
assert solve([3]) == 0
assert solve([3,0,3]) == 3
assert solve([0,0,0]) == 0
assert solve([5,4,3,2,1]) == 0  # descending, no trap
assert solve([1,2,3,4,5]) == 0  # ascending, no trap
assert solve([5,2,1,2,1,5]) == 14
assert solve([2,0,2]) == 2
print("Correctness: PASSED")

# Performance
import random
random.seed(456)
big = [random.randint(0, 10000) for _ in range(100_000)]
start = time.time()
result = solve(big)
elapsed = time.time() - start
assert elapsed < 1.0, f"Too slow: {elapsed:.2f}s"
assert result >= 0
print(f"Performance: PASSED ({elapsed:.3f}s)")
print("ALL PASSED")
''',
}

experiment = Experiment(
    name="competitive_programming",
    description=(
        "4 competitive programming problems requiring algorithmic insight. "
        "Naive O(n²) solutions will TLE. haiku vs sonnet at max_turns=20."
    ),
    diff=DiffSpec(
        field="model",
        description="haiku vs sonnet on competitive programming",
    ),
    agent_a=AgentConfig(
        name="haiku",
        model="claude-haiku-4-5",
        system_prompt=(
            "Solve competitive programming problems. Read the problem spec and tests. "
            "Implement an EFFICIENT solution (naive brute-force will be too slow for "
            "large inputs). Run tests to verify both correctness and performance."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=20,
    ),
    agent_b=AgentConfig(
        name="sonnet",
        model="claude-sonnet-4-6",
        system_prompt=(
            "Solve competitive programming problems. Read the problem spec and tests. "
            "Implement an EFFICIENT solution (naive brute-force will be too slow for "
            "large inputs). Run tests to verify both correctness and performance."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=20,
    ),
    tasks=[
        TaskItem(
            prompt="Solve p1_subarray.py (longest subarray with exactly k distinct elements). Run test_p1.py.",
            expected="ALL PASSED",
            check_fn='"ALL PASSED" in output or "all passed" in output.lower()',
            difficulty="hard",
            tags=["sliding-window", "hashmap"],
        ),
        TaskItem(
            prompt="Solve p2_jumps.py (minimum jumps to reach end). Run test_p2.py.",
            expected="ALL PASSED",
            check_fn='"ALL PASSED" in output or "all passed" in output.lower()',
            difficulty="hard",
            tags=["greedy", "dp"],
        ),
        TaskItem(
            prompt="Solve p3_inversions.py (count inversions in O(n log n)). Run test_p3.py.",
            expected="ALL PASSED",
            check_fn='"ALL PASSED" in output or "all passed" in output.lower()',
            difficulty="very_hard",
            tags=["merge-sort", "divide-conquer"],
        ),
        TaskItem(
            prompt="Solve p4_water.py (trapping rain water). Run test_p4.py.",
            expected="ALL PASSED",
            check_fn='"ALL PASSED" in output or "all passed" in output.lower()',
            difficulty="hard",
            tags=["two-pointer", "stack"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=3,
    tags=["competitive-programming", "algorithmic", "performance"],
)
