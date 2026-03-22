"""
Self-Correction Strategy — Pivot vs Refine After Failed Fix

Research question: When a batch fix partially fails, should the agent
revert everything and restart (pivot) or keep working fixes and adjust (refine)?

Builds on error_recovery_v2 findings (batch > incremental). Both agents use
the batch approach for Phase 1. The difference is Phase 2 recovery.

Design:
- 4 single-file tasks, each with 2 bugs (1 obvious + 1 subtle)
- Phase 1 likely fixes the obvious bug but misses the subtle one
- Phase 2 tests which recovery strategy handles the remaining bug better
- git init in setup_script so pivot agent can revert cleanly

max_turns=10, num_samples=5.
Extreme FORBIDDEN constraints on both agents.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ═══════════════ T1: Inventory Tracker ═══════════════
    # Bug A (obvious): total_value uses + instead of *
    # Bug B (subtle): most_valuable compares qty instead of qty*price
    "tasks/t1/inventory.py": '''\
class Inventory:
    def __init__(self):
        self.items = {}

    def add(self, name, qty, price):
        if name in self.items:
            self.items[name]["qty"] += qty
            self.items[name]["price"] = price
        else:
            self.items[name] = {"qty": qty, "price": price}

    def sell(self, name, qty):
        if name not in self.items or self.items[name]["qty"] < qty:
            return None
        self.items[name]["qty"] -= qty
        return qty * self.items[name]["price"]

    def total_value(self):
        """Total value of all inventory (qty * price per item)."""
        return sum(d["qty"] + d["price"] for d in self.items.values())

    def most_valuable(self):
        """Return name of the item with highest total value (qty * price)."""
        if not self.items:
            return None
        return max(self.items.items(), key=lambda x: x[1]["qty"])[0]
''',
    "tasks/t1/test_inventory.py": '''\
from inventory import Inventory

def test_total_value():
    inv = Inventory()
    inv.add("widget", 10, 5)
    inv.add("gadget", 3, 20)
    total = inv.total_value()
    # 10*5 + 3*20 = 50 + 60 = 110
    assert total == 110, f"Expected 110, got {total}"
    print("  total_value: PASSED")

def test_sell():
    inv = Inventory()
    inv.add("widget", 10, 5)
    revenue = inv.sell("widget", 3)
    assert revenue == 15, f"Expected 15, got {revenue}"
    assert inv.items["widget"]["qty"] == 7
    print("  sell: PASSED")

def test_most_valuable():
    inv = Inventory()
    inv.add("cheap_bulk", 100, 1)    # value = 100
    inv.add("expensive_few", 2, 200)  # value = 400
    best = inv.most_valuable()
    assert best == "expensive_few", f"Expected expensive_few (val=400), got {best}"
    print("  most_valuable: PASSED")

def test_most_valuable_equal_qty():
    inv = Inventory()
    inv.add("A", 5, 10)   # value = 50
    inv.add("B", 5, 100)  # value = 500
    best = inv.most_valuable()
    assert best == "B", f"Expected B (val=500), got {best}"
    print("  most_valuable_equal_qty: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_total_value", "test_sell",
                  "test_most_valuable", "test_most_valuable_equal_qty"]:
        try:
            globals()[name]()
            passed += 1
        except Exception as e:
            print(f"  {name}: FAILED -- {e}")
            failed += 1
    print(f"\\nResults: {passed}/{passed+failed}")
    if failed == 0:
        print("PASSED")
''',

    # ═══════════════ T2: Text Statistics ═══════════════
    # Bug A (obvious): word_count counts characters, not words
    # Bug B (subtle): most_common_word returns LEAST common (min vs max)
    "tasks/t2/textstats.py": '''\
def word_count(text):
    """Return the number of words in the text."""
    return len(text)

def most_common_word(text):
    """Return the most frequently occurring word (case-insensitive)."""
    words = text.lower().split()
    if not words:
        return None
    counts = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return min(counts, key=counts.get)

def unique_words(text):
    """Return sorted list of unique words (case-insensitive)."""
    return sorted(set(text.lower().split()))
''',
    "tasks/t2/test_textstats.py": '''\
from textstats import word_count, most_common_word, unique_words

def test_word_count():
    assert word_count("hello world") == 2, f"Got {word_count('hello world')}"
    assert word_count("one") == 1
    assert word_count("a b c d e") == 5
    print("  word_count: PASSED")

def test_most_common():
    text = "the cat sat on the mat the"
    result = most_common_word(text)
    assert result == "the", f"Expected 'the' (3 times), got '{result}'"
    print("  most_common: PASSED")

def test_most_common_tie():
    text = "a b a b c"
    result = most_common_word(text)
    assert result in ("a", "b"), f"Expected 'a' or 'b' (2 each), got '{result}'"
    print("  most_common_tie: PASSED")

def test_unique_words():
    result = unique_words("The the THE cat Cat")
    assert result == ["cat", "the"], f"Got {result}"
    print("  unique_words: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_word_count", "test_most_common",
                  "test_most_common_tie", "test_unique_words"]:
        try:
            globals()[name]()
            passed += 1
        except Exception as e:
            print(f"  {name}: FAILED -- {e}")
            failed += 1
    print(f"\\nResults: {passed}/{passed+failed}")
    if failed == 0:
        print("PASSED")
''',

    # ═══════════════ T3: Priority Queue ═══════════════
    # Bug A (obvious): sorts ascending instead of descending (highest priority first)
    # Bug B (subtle): size() returns len - 1
    "tasks/t3/pqueue.py": '''\
class PriorityQueue:
    def __init__(self):
        self.tasks = []

    def push(self, name, priority):
        """Add a task with given priority. Higher number = higher priority."""
        self.tasks.append({"name": name, "priority": priority})
        self.tasks.sort(key=lambda t: t["priority"])

    def pop(self):
        """Remove and return the highest-priority task."""
        if not self.tasks:
            return None
        return self.tasks.pop(0)

    def peek(self):
        """Return the highest-priority task without removing it."""
        if not self.tasks:
            return None
        return self.tasks[0]["name"]

    def size(self):
        """Return number of tasks in queue."""
        return len(self.tasks) - 1
''',
    "tasks/t3/test_pqueue.py": '''\
from pqueue import PriorityQueue

def test_priority_order():
    pq = PriorityQueue()
    pq.push("low", 1)
    pq.push("high", 10)
    pq.push("medium", 5)
    result = pq.pop()
    assert result["name"] == "high", f"Expected highest priority first, got {result}"
    print("  priority_order: PASSED")

def test_peek():
    pq = PriorityQueue()
    pq.push("A", 3)
    pq.push("B", 7)
    assert pq.peek() == "B", f"Expected B (priority 7), got {pq.peek()}"
    # peek should not remove
    assert pq.size() == 2, f"peek removed item, size={pq.size()}"
    print("  peek: PASSED")

def test_size():
    pq = PriorityQueue()
    assert pq.size() == 0, f"Empty queue size: {pq.size()}"
    pq.push("A", 1)
    assert pq.size() == 1, f"After 1 push, size: {pq.size()}"
    pq.push("B", 2)
    assert pq.size() == 2, f"After 2 pushes, size: {pq.size()}"
    pq.pop()
    assert pq.size() == 1, f"After pop, size: {pq.size()}"
    print("  size: PASSED")

def test_empty_pop():
    pq = PriorityQueue()
    assert pq.pop() is None
    assert pq.peek() is None
    print("  empty_pop: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_priority_order", "test_peek", "test_size", "test_empty_pop"]:
        try:
            globals()[name]()
            passed += 1
        except Exception as e:
            print(f"  {name}: FAILED -- {e}")
            failed += 1
    print(f"\\nResults: {passed}/{passed+failed}")
    if failed == 0:
        print("PASSED")
''',

    # ═══════════════ T4: Score Calculator ═══════════════
    # Bug A (obvious): apply_curve adds curve instead of multiplying
    # Bug B (subtle): letter_grade boundaries use > instead of >= (90 should be A)
    "tasks/t4/grades.py": '''\
def apply_curve(scores, curve):
    """Apply a multiplicative curve to all scores. E.g., curve=1.1 adds 10%."""
    return [s + curve for s in scores]

def average(scores):
    """Return the average of a list of scores."""
    if not scores:
        return 0
    return sum(scores) / len(scores)

def letter_grade(score):
    """Convert numeric score to letter grade."""
    if score > 90:
        return "A"
    elif score > 80:
        return "B"
    elif score > 70:
        return "C"
    elif score > 60:
        return "D"
    else:
        return "F"

def class_report(scores, curve=1.0):
    """Generate a report with curved scores, average, and grade distribution."""
    curved = apply_curve(scores, curve)
    avg = average(curved)
    grades = {}
    for s in curved:
        g = letter_grade(s)
        grades[g] = grades.get(g, 0) + 1
    return {"curved_scores": curved, "average": avg, "grades": grades}
''',
    "tasks/t4/test_grades.py": '''\
from grades import apply_curve, average, letter_grade, class_report

def test_apply_curve():
    scores = [80, 70, 90]
    curved = apply_curve(scores, 1.1)
    # 80*1.1=88, 70*1.1=77, 90*1.1=99
    assert curved == [88.0, 77.0, 99.0], f"Expected [88, 77, 99], got {curved}"
    print("  apply_curve: PASSED")

def test_curve_identity():
    scores = [85, 92]
    curved = apply_curve(scores, 1.0)
    assert curved == [85.0, 92.0], f"Curve 1.0 should preserve scores: {curved}"
    print("  curve_identity: PASSED")

def test_letter_grade_boundaries():
    assert letter_grade(90) == "A", f"90 should be A, got {letter_grade(90)}"
    assert letter_grade(80) == "B", f"80 should be B, got {letter_grade(80)}"
    assert letter_grade(70) == "C", f"70 should be C, got {letter_grade(70)}"
    assert letter_grade(60) == "D", f"60 should be D, got {letter_grade(60)}"
    assert letter_grade(59) == "F"
    print("  letter_grade_boundaries: PASSED")

def test_class_report():
    scores = [80, 70, 90]
    report = class_report(scores, curve=1.1)
    assert report["average"] == 88.0, f"Average: {report['average']}"
    assert report["grades"].get("A") == 1  # 99 -> A
    print("  class_report: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_apply_curve", "test_curve_identity",
                  "test_letter_grade_boundaries", "test_class_report"]:
        try:
            globals()[name]()
            passed += 1
        except Exception as e:
            print(f"  {name}: FAILED -- {e}")
            failed += 1
    print(f"\\nResults: {passed}/{passed+failed}")
    if failed == 0:
        print("PASSED")
''',
}

PIVOT_PROMPT = """\
STRICT RULES for fixing bugs:

PHASE 1 — First attempt:
1. Read the source file
2. Read the test file
3. Identify all bugs
4. Fix all bugs in one pass
5. Run the test

PHASE 2 — If any test still fails:
6. REVERT all your changes: run `git checkout -- .` to restore original files
7. Re-read the test output from step 5 carefully
8. Re-read the source file with fresh eyes
9. Identify ALL bugs (including ones you missed before)
10. Fix ALL bugs from scratch in one pass
11. Run the test again

CRITICAL CONSTRAINTS:
- After a failed test, you are FORBIDDEN from making incremental edits
- You MUST run `git checkout -- .` before your second attempt
- You MUST re-read the source file after reverting
- Your first analysis was incomplete — start fresh with full knowledge
- "Revert everything, rethink everything"

Print the final test output.
"""

REFINE_PROMPT = """\
STRICT RULES for fixing bugs:

PHASE 1 — First attempt:
1. Read the source file
2. Read the test file
3. Identify all bugs
4. Fix all bugs in one pass
5. Run the test

PHASE 2 — If any test still fails:
6. Do NOT revert your changes — your existing fixes may be correct
7. Read ONLY the new test output to identify which tests still fail
8. Make MINIMAL additional edits to fix just the remaining failures
9. Run the test again

CRITICAL CONSTRAINTS:
- After a failed test, you are FORBIDDEN from reverting previous changes
- You are FORBIDDEN from running `git checkout` or `git restore`
- You are FORBIDDEN from re-reading the source file — use only the test output
- Your first fixes were partially right — build on them, don't restart
- "Keep what works, fix what's still broken"

Print the final test output.
"""

experiment = Experiment(
    name="self_correction_strategy",
    description=(
        "Pivot (revert+restart) vs refine (keep+adjust) after failed batch fix. "
        "4 tasks × 5 samples. Each task has 1 obvious + 1 subtle bug. "
        "Tests which recovery strategy handles partial-fix failures better."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Pivot (revert all, fresh analysis) vs refine (keep fixes, adjust remaining)",
    ),
    agent_a=AgentConfig(
        name="pivot",
        model="claude-haiku-4-5",
        system_prompt=PIVOT_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=10,
    ),
    agent_b=AgentConfig(
        name="refine",
        model="claude-haiku-4-5",
        system_prompt=REFINE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=10,
    ),
    tasks=[
        TaskItem(
            prompt=(
                "Fix all bugs in tasks/t1/inventory.py. "
                "Run: cd tasks/t1 && python test_inventory.py\n"
                "Print the test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["arithmetic", "comparison"],
        ),
        TaskItem(
            prompt=(
                "Fix all bugs in tasks/t2/textstats.py. "
                "Run: cd tasks/t2 && python test_textstats.py\n"
                "Print the test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["string-processing", "aggregation"],
        ),
        TaskItem(
            prompt=(
                "Fix all bugs in tasks/t3/pqueue.py. "
                "Run: cd tasks/t3 && python test_pqueue.py\n"
                "Print the test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["data-structure", "off-by-one"],
        ),
        TaskItem(
            prompt=(
                "Fix all bugs in tasks/t4/grades.py. "
                "Run: cd tasks/t4 && python test_grades.py\n"
                "Print the test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["math", "boundary"],
        ),
    ],
    setup_files=SETUP_FILES,
    setup_script="cd tasks/t1 && git init -q && git add -A && git commit -q -m init && cd ../t2 && git init -q && git add -A && git commit -q -m init && cd ../t3 && git init -q && git add -A && git commit -q -m init && cd ../t4 && git init -q && git add -A && git commit -q -m init",
    num_samples=5,
    tags=["self-correction", "pivot-vs-refine", "recovery-strategy"],
)
