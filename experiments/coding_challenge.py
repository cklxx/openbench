"""
Experiment: Coding Challenge — Implement from Spec, Verify with Tests

Unlike code_fix (find and fix bugs), this requires agents to IMPLEMENT
algorithms from scratch given a spec + test suite. The agent must:
1. Read the spec and tests
2. Write the implementation
3. Run tests to verify

Tests whether haiku vs sonnet differ when implementation requires
multi-step reasoning, not just pattern matching known bugs.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ── Challenge 1: Matrix spiral traversal ─────────────────────────────
    "spec_spiral.py": '''\
"""
Implement spiral_order(matrix) that returns elements in spiral order.

Example:
  Input:  [[1,2,3],
           [4,5,6],
           [7,8,9]]
  Output: [1,2,3,6,9,8,7,4,5]

  Input:  [[1,2,3,4],
           [5,6,7,8],
           [9,10,11,12]]
  Output: [1,2,3,4,8,12,11,10,9,5,6,7]
"""
def spiral_order(matrix):
    raise NotImplementedError("Implement this")
''',
    "test_spiral.py": '''\
from spec_spiral import spiral_order

assert spiral_order([[1,2,3],[4,5,6],[7,8,9]]) == [1,2,3,6,9,8,7,4,5]
assert spiral_order([[1,2,3,4],[5,6,7,8],[9,10,11,12]]) == [1,2,3,4,8,12,11,10,9,5,6,7]
assert spiral_order([[1]]) == [1]
assert spiral_order([[1,2],[3,4]]) == [1,2,4,3]
assert spiral_order([]) == []
assert spiral_order([[1,2,3]]) == [1,2,3]  # single row
assert spiral_order([[1],[2],[3]]) == [1,2,3]  # single column
print("spiral: ALL PASSED")
''',

    # ── Challenge 2: Run-length encoding/decoding ────────────────────────
    "spec_rle.py": '''\
"""
Implement:
  encode(s) -> list of (char, count) tuples
  decode(pairs) -> string

Example:
  encode("aaabbc") -> [("a",3), ("b",2), ("c",1)]
  decode([("a",3), ("b",2), ("c",1)]) -> "aaabbc"

Edge cases: empty string, single char, no consecutive repeats.
"""
def encode(s):
    raise NotImplementedError

def decode(pairs):
    raise NotImplementedError
''',
    "test_rle.py": '''\
from spec_rle import encode, decode

assert encode("aaabbc") == [("a",3), ("b",2), ("c",1)]
assert encode("") == []
assert encode("a") == [("a",1)]
assert encode("abcabc") == [("a",1),("b",1),("c",1),("a",1),("b",1),("c",1)]
assert decode([("a",3), ("b",2)]) == "aaabb"
assert decode([]) == ""
assert decode(encode("hello world")) == "hello world"
print("rle: ALL PASSED")
''',

    # ── Challenge 3: Balanced parentheses generator ──────────────────────
    "spec_parens.py": '''\
"""
Implement generate_parens(n) that returns all valid combinations
of n pairs of parentheses, sorted lexicographically.

Example:
  generate_parens(1) -> ["()"]
  generate_parens(2) -> ["(())", "()()"]
  generate_parens(3) -> ["((()))", "(()())", "(())()", "()(())", "()()()"]
"""
def generate_parens(n):
    raise NotImplementedError
''',
    "test_parens.py": '''\
from spec_parens import generate_parens

assert generate_parens(0) == [""]
assert generate_parens(1) == ["()"]
assert generate_parens(2) == ["(())", "()()"]
assert generate_parens(3) == ["((()))", "(()())", "(())()", "()(())", "()()()"]
assert len(generate_parens(4)) == 14  # Catalan number C(4) = 14
print("parens: ALL PASSED")
''',

    # ── Challenge 4: Trie with prefix search ─────────────────────────────
    "spec_trie.py": '''\
"""
Implement a Trie (prefix tree) with:
  insert(word)        — add a word
  search(word) -> bool — exact match
  starts_with(prefix) -> list[str] — all words with this prefix, sorted

Example:
  t = Trie()
  t.insert("apple")
  t.insert("app")
  t.insert("application")
  t.insert("banana")
  t.search("app") -> True
  t.search("ap") -> False
  t.starts_with("app") -> ["app", "apple", "application"]
  t.starts_with("ban") -> ["banana"]
  t.starts_with("xyz") -> []
"""
class Trie:
    def __init__(self):
        raise NotImplementedError

    def insert(self, word):
        raise NotImplementedError

    def search(self, word):
        raise NotImplementedError

    def starts_with(self, prefix):
        raise NotImplementedError
''',
    "test_trie.py": '''\
from spec_trie import Trie

t = Trie()
t.insert("apple")
t.insert("app")
t.insert("application")
t.insert("banana")
t.insert("band")

assert t.search("app") == True
assert t.search("apple") == True
assert t.search("ap") == False
assert t.search("") == False
assert t.starts_with("app") == ["app", "apple", "application"]
assert t.starts_with("ban") == ["banana", "band"]
assert t.starts_with("xyz") == []
assert t.starts_with("") == ["app", "apple", "application", "banana", "band"]
print("trie: ALL PASSED")
''',

    # ── Challenge 5: LCS (Longest Common Subsequence) ────────────────────
    "spec_lcs.py": '''\
"""
Implement lcs(s1, s2) that returns the longest common subsequence
(not substring!) of two strings. If multiple LCS exist, return any one.

Example:
  lcs("ABCBDAB", "BDCAB") -> "BCAB" (length 4)
  lcs("abc", "def") -> ""
  lcs("abc", "abc") -> "abc"
"""
def lcs(s1, s2):
    raise NotImplementedError
''',
    "test_lcs.py": '''\
from spec_lcs import lcs

# Check LCS correctness by verifying length and subsequence property
def is_subsequence(sub, s):
    it = iter(s)
    return all(c in it for c in sub)

r1 = lcs("ABCBDAB", "BDCAB")
assert len(r1) == 4 and is_subsequence(r1, "ABCBDAB") and is_subsequence(r1, "BDCAB"), f"Got {r1}"

assert lcs("abc", "def") == ""
assert lcs("abc", "abc") == "abc"
assert lcs("", "abc") == ""
assert lcs("a", "a") == "a"

r2 = lcs("AGGTAB", "GXTXAYB")
assert len(r2) == 4 and is_subsequence(r2, "AGGTAB") and is_subsequence(r2, "GXTXAYB"), f"Got {r2}"

print("lcs: ALL PASSED")
''',
}

experiment = Experiment(
    name="coding_challenge",
    description=(
        "Implement algorithms from spec + pass test suites. "
        "haiku vs sonnet: does model capability matter for implementation tasks?"
    ),
    diff=DiffSpec(
        field="model",
        description="claude-haiku-4-5 vs claude-sonnet-4-6 on coding challenges",
    ),
    agent_a=AgentConfig(
        name="haiku",
        model="claude-haiku-4-5",
        system_prompt=(
            "Implement the function/class in the spec file. Run the test file to verify. "
            "If tests fail, fix and re-run until all pass."
        ),
        allowed_tools=["Read", "Bash", "Glob", "Edit", "Write"],
        max_turns=20,
    ),
    agent_b=AgentConfig(
        name="sonnet",
        model="claude-sonnet-4-6",
        system_prompt=(
            "Implement the function/class in the spec file. Run the test file to verify. "
            "If tests fail, fix and re-run until all pass."
        ),
        allowed_tools=["Read", "Bash", "Glob", "Edit", "Write"],
        max_turns=20,
    ),
    tasks=[
        TaskItem(
            prompt="Implement spiral_order in spec_spiral.py and run test_spiral.py to verify.",
            expected="ALL PASSED",
            check_fn='"pass" in output.lower()',
            difficulty="medium",
            tags=["matrix", "traversal"],
        ),
        TaskItem(
            prompt="Implement encode and decode in spec_rle.py and run test_rle.py to verify.",
            expected="ALL PASSED",
            check_fn='"pass" in output.lower()',
            difficulty="easy",
            tags=["string", "encoding"],
        ),
        TaskItem(
            prompt="Implement generate_parens in spec_parens.py and run test_parens.py to verify.",
            expected="ALL PASSED",
            check_fn='"pass" in output.lower()',
            difficulty="medium",
            tags=["recursion", "backtracking"],
        ),
        TaskItem(
            prompt="Implement the Trie class in spec_trie.py and run test_trie.py to verify.",
            expected="ALL PASSED",
            check_fn='"pass" in output.lower()',
            difficulty="hard",
            tags=["data-structure", "trie"],
        ),
        TaskItem(
            prompt="Implement lcs in spec_lcs.py and run test_lcs.py to verify.",
            expected="ALL PASSED",
            check_fn='"pass" in output.lower()',
            difficulty="hard",
            tags=["dynamic-programming", "lcs"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=1,
    tags=["coding-challenge", "implementation", "model-comparison"],
)
