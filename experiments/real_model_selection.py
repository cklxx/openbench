"""
Real Decision: Haiku vs Sonnet at Equal Turns on Mixed Tasks

Real question agent builders face: which model to use?
Both get generous turns (15). Tasks have GENUINE difficulty range:
- T1-T2: tasks within Haiku's capability (clear bugs, standard patterns)
- T3-T4: tasks that push model reasoning (subtle logic, tricky edge cases)

Both configs are GOOD — neither is artificially handicapped.
The goal: find WHERE Sonnet's extra capability matters.

4 tasks (easy→hard) × 8 samples, max_turns=15.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ═══════ T1: String Utils — Easy (1 clear bug) ═══════
    "tasks/t1/strutil.py": '''\
def truncate(text, max_len, suffix="..."):
    """Truncate text to max_len, adding suffix if truncated."""
    if len(text) <= max_len:
        return text
    # Should truncate to (max_len - len(suffix)) then add suffix
    return text[:max_len] + suffix  # Bug: doesn't account for suffix length

def title_case(text):
    """Capitalize first letter of each word."""
    return " ".join(w.capitalize() for w in text.split())

def count_words(text):
    """Count words in text, ignoring extra whitespace."""
    return len(text.split())
''',
    "tasks/t1/test_strutil.py": '''\
from strutil import truncate, title_case, count_words

def test_truncate():
    assert truncate("Hello", 10) == "Hello"
    result = truncate("Hello World!", 8)
    assert len(result) <= 8, f"Truncated should be <= 8 chars, got {len(result)}: '{result}'"
    assert result.endswith("..."), f"Should end with ...: '{result}'"
    assert result == "Hello...", f"Expected 'Hello...' (5+3=8), got '{result}'"
    print("  truncate: PASSED")

def test_truncate_custom_suffix():
    result = truncate("Long text here", 10, suffix="..")
    assert len(result) <= 10
    assert result.endswith("..")
    print("  truncate_custom_suffix: PASSED")

def test_title_case():
    assert title_case("hello world") == "Hello World"
    assert title_case("ALREADY CAPS") == "Already Caps"
    print("  title_case: PASSED")

def test_count_words():
    assert count_words("hello world") == 2
    assert count_words("  spaced  out  ") == 2
    print("  count_words: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_truncate", "test_truncate_custom_suffix",
                  "test_title_case", "test_count_words"]:
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

    # ═══════ T2: Data Aggregator — Medium (2 bugs, clear from tests) ═══════
    "tasks/t2/aggregator.py": '''\
from collections import defaultdict

class Aggregator:
    def __init__(self):
        self.data = defaultdict(list)

    def add(self, group, value):
        self.data[group].append(value)

    def mean(self, group):
        values = self.data.get(group, [])
        if not values:
            return None
        return sum(values) / len(values)

    def median(self, group):
        values = sorted(self.data.get(group, []))
        if not values:
            return None
        n = len(values)
        mid = n // 2
        if n % 2 == 0:
            # Bug: returns only values[mid] instead of average of two middle
            return values[mid]
        return values[mid]

    def percentile(self, group, p):
        """Return the p-th percentile (0-100) using nearest-rank method."""
        values = sorted(self.data.get(group, []))
        if not values:
            return None
        # Bug: doesn't clamp p to 0-100 range, and uses wrong index formula
        # Nearest rank: index = ceil(p/100 * n) - 1
        import math
        index = int(p / 100 * len(values))  # should be ceil, then -1
        return values[min(index, len(values) - 1)]

    def groups(self):
        return list(self.data.keys())
''',
    "tasks/t2/test_aggregator.py": '''\
from aggregator import Aggregator

def test_mean():
    a = Aggregator()
    for v in [10, 20, 30]:
        a.add("sales", v)
    assert a.mean("sales") == 20.0
    assert a.mean("empty") is None
    print("  mean: PASSED")

def test_median_odd():
    a = Aggregator()
    for v in [3, 1, 2]:
        a.add("x", v)
    assert a.median("x") == 2, f"Median of [1,2,3] should be 2, got {a.median('x')}"
    print("  median_odd: PASSED")

def test_median_even():
    a = Aggregator()
    for v in [1, 2, 3, 4]:
        a.add("x", v)
    result = a.median("x")
    assert result == 2.5, f"Median of [1,2,3,4] should be 2.5, got {result}"
    print("  median_even: PASSED")

def test_percentile():
    a = Aggregator()
    for v in [15, 20, 35, 40, 50]:
        a.add("scores", v)
    # 90th percentile of [15,20,35,40,50]: nearest rank = ceil(0.9*5) = 5 → index 4 → 50
    result = a.percentile("scores", 90)
    assert result == 50, f"90th percentile should be 50, got {result}"
    # 20th percentile: ceil(0.2*5) = 1 → index 0 → 15
    result = a.percentile("scores", 20)
    assert result == 15, f"20th percentile should be 15, got {result}"
    print("  percentile: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_mean", "test_median_odd", "test_median_even", "test_percentile"]:
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

    # ═══════ T3: Expression Parser — Hard (2 subtle bugs) ═══════
    # Requires understanding operator precedence and recursive descent
    "tasks/t3/expr.py": '''\
class ExprParser:
    """Simple arithmetic expression parser: +, -, *, /, parentheses.
    Respects precedence: * and / bind tighter than + and -.
    """
    def __init__(self, text):
        self.text = text.replace(" ", "")
        self.pos = 0

    def parse(self):
        result = self._expr()
        if self.pos < len(self.text):
            raise ValueError(f"Unexpected char at {self.pos}: '{self.text[self.pos]}'")
        return result

    def _expr(self):
        """Handle + and - (lowest precedence)."""
        left = self._term()
        while self.pos < len(self.text) and self.text[self.pos] in "+-":
            op = self.text[self.pos]
            self.pos += 1
            right = self._term()
            if op == "+":
                left = left + right
            else:
                left = left - right
        return left

    def _term(self):
        """Handle * and / (higher precedence)."""
        left = self._factor()
        while self.pos < len(self.text) and self.text[self.pos] in "*/":
            op = self.text[self.pos]
            self.pos += 1
            right = self._factor()
            if op == "*":
                left = left * right
            else:
                # Bug A: integer division instead of float division
                left = left // right
        return left

    def _factor(self):
        """Handle numbers and parentheses."""
        if self.pos < len(self.text) and self.text[self.pos] == "(":
            self.pos += 1  # skip (
            result = self._expr()
            if self.pos < len(self.text) and self.text[self.pos] == ")":
                self.pos += 1  # skip )
            return result

        # Parse number (int or float)
        start = self.pos
        # Bug B: doesn't handle negative numbers like (-3)
        while self.pos < len(self.text) and (self.text[self.pos].isdigit() or self.text[self.pos] == "."):
            self.pos += 1
        if self.pos == start:
            raise ValueError(f"Expected number at {self.pos}")
        return float(self.text[start:self.pos])


def evaluate(expression):
    """Evaluate a math expression string."""
    return ExprParser(expression).parse()
''',
    "tasks/t3/test_expr.py": '''\
from expr import evaluate

def test_basic_arithmetic():
    assert evaluate("2 + 3") == 5.0
    assert evaluate("10 - 4") == 6.0
    assert evaluate("3 * 4") == 12.0
    print("  basic_arithmetic: PASSED")

def test_precedence():
    assert evaluate("2 + 3 * 4") == 14.0, f"Got {evaluate('2 + 3 * 4')}"
    assert evaluate("10 - 2 * 3") == 4.0
    print("  precedence: PASSED")

def test_float_division():
    result = evaluate("7 / 2")
    assert result == 3.5, f"7/2 should be 3.5, got {result}"
    result = evaluate("10 / 4")
    assert result == 2.5, f"10/4 should be 2.5, got {result}"
    print("  float_division: PASSED")

def test_parentheses():
    assert evaluate("(2 + 3) * 4") == 20.0
    assert evaluate("2 * (3 + 4)") == 14.0
    print("  parentheses: PASSED")

def test_negative_in_parens():
    """Negative numbers in parentheses should work."""
    result = evaluate("5 + (-3)")
    assert result == 2.0, f"5 + (-3) should be 2.0, got {result}"
    result = evaluate("(-2) * 3")
    assert result == -6.0, f"(-2) * 3 should be -6.0, got {result}"
    print("  negative_in_parens: PASSED")

def test_complex():
    result = evaluate("(10 + 5) / 2 + 3 * (4 - 1)")
    # (10+5)/2 + 3*(4-1) = 15/2 + 3*3 = 7.5 + 9 = 16.5
    assert result == 16.5, f"Expected 16.5, got {result}"
    print("  complex: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_basic_arithmetic", "test_precedence", "test_float_division",
                  "test_parentheses", "test_negative_in_parens", "test_complex"]:
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

    # ═══════ T4: Dependency Resolver — Very Hard (topological sort + cycle detection) ═══════
    # Requires graph algorithm understanding
    "tasks/t4/deps.py": '''\
class DependencyResolver:
    """Resolve dependencies in topological order with cycle detection."""

    def __init__(self):
        self.deps = {}  # node -> set of dependencies

    def add(self, node, depends_on=None):
        if node not in self.deps:
            self.deps[node] = set()
        if depends_on:
            if depends_on not in self.deps:
                self.deps[depends_on] = set()
            self.deps[node].add(depends_on)

    def resolve(self):
        """Return nodes in dependency order (dependencies first).
        Raises ValueError on circular dependency."""
        resolved = []
        seen = set()
        visiting = set()

        def visit(node):
            if node in resolved:
                return
            if node in visiting:
                raise ValueError(f"Circular dependency: {node}")
            visiting.add(node)
            for dep in self.deps.get(node, set()):
                visit(dep)
            visiting.remove(node)
            # Bug A: adds to seen but checks resolved — should use same set
            seen.add(node)
            resolved.append(node)

        for node in self.deps:
            visit(node)
        return resolved

    def depends_on(self, node):
        """Return ALL dependencies (transitive) for a node."""
        result = set()
        stack = list(self.deps.get(node, set()))
        while stack:
            dep = stack.pop()
            if dep not in result:
                result.add(dep)
                # Bug B: extends with deps.get(dep, []) but deps values are sets
                # This works but doesn't recurse — only gets direct deps
                # Actually the stack-based approach should work... let me make a real bug
                stack.extend(self.deps.get(dep, set()))
        return result

    def install_order(self):
        """Return (node, [its_direct_deps]) pairs in install order."""
        order = self.resolve()
        return [(n, sorted(self.deps.get(n, set()))) for n in order]
''',
    "tasks/t4/test_deps.py": '''\
from deps import DependencyResolver

def test_simple_chain():
    r = DependencyResolver()
    r.add("app", depends_on="framework")
    r.add("framework", depends_on="stdlib")
    r.add("stdlib")
    order = r.resolve()
    assert order.index("stdlib") < order.index("framework") < order.index("app"), \\
        f"Wrong order: {order}"
    print("  simple_chain: PASSED")

def test_diamond():
    """A depends on B and C, both depend on D."""
    r = DependencyResolver()
    r.add("A", depends_on="B")
    r.add("A", depends_on="C")
    r.add("B", depends_on="D")
    r.add("C", depends_on="D")
    r.add("D")
    order = r.resolve()
    assert order.index("D") < order.index("B"), f"D before B: {order}"
    assert order.index("D") < order.index("C"), f"D before C: {order}"
    assert order.index("B") < order.index("A"), f"B before A: {order}"
    assert order.index("C") < order.index("A"), f"C before A: {order}"
    print("  diamond: PASSED")

def test_circular():
    r = DependencyResolver()
    r.add("A", depends_on="B")
    r.add("B", depends_on="C")
    r.add("C", depends_on="A")
    try:
        r.resolve()
        assert False, "Should raise ValueError for circular dependency"
    except ValueError as e:
        assert "Circular" in str(e) or "circular" in str(e)
    print("  circular: PASSED")

def test_transitive_deps():
    r = DependencyResolver()
    r.add("app", depends_on="web")
    r.add("web", depends_on="http")
    r.add("http", depends_on="socket")
    r.add("socket")
    all_deps = r.depends_on("app")
    assert all_deps == {"web", "http", "socket"}, \\
        f"app's transitive deps should be {{web, http, socket}}, got {all_deps}"
    print("  transitive_deps: PASSED")

def test_no_duplicate_in_order():
    """Each node should appear exactly once in the resolved order."""
    r = DependencyResolver()
    r.add("A", depends_on="C")
    r.add("B", depends_on="C")
    r.add("C")
    order = r.resolve()
    assert len(order) == len(set(order)), f"Duplicates in order: {order}"
    assert len(order) == 3, f"Expected 3 nodes, got {len(order)}: {order}"
    print("  no_duplicate: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_simple_chain", "test_diamond", "test_circular",
                  "test_transitive_deps", "test_no_duplicate_in_order"]:
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

PROMPT = """\
You are a software developer. Fix the bugs and make all tests pass.
Print the final test output.
"""

TASKS = [
    TaskItem(
        prompt="Fix the bug in tasks/t1/strutil.py. Run: cd tasks/t1 && python test_strutil.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="easy", tags=["string-utils", "1-bug"],
    ),
    TaskItem(
        prompt="Fix the bugs in tasks/t2/aggregator.py. Run: cd tasks/t2 && python test_aggregator.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="medium", tags=["aggregator", "2-bugs"],
    ),
    TaskItem(
        prompt="Fix the bugs in tasks/t3/expr.py. Run: cd tasks/t3 && python test_expr.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="hard", tags=["parser", "2-bugs"],
    ),
    TaskItem(
        prompt="Fix the bugs in tasks/t4/deps.py. Run: cd tasks/t4 && python test_deps.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="hard", tags=["graph-algorithm", "2-bugs"],
    ),
]

experiment = Experiment(
    name="real_model_selection",
    description=(
        "Real decision: Haiku vs Sonnet on mixed-difficulty tasks. "
        "Both get generous turns (15). Tasks range from easy (string utils) "
        "to hard (expression parser, dependency resolver). "
        "Goal: find WHERE Sonnet's extra capability matters."
    ),
    diff=DiffSpec(
        field="model",
        description="Haiku vs Sonnet — both with 15 turns, mixed-difficulty tasks",
    ),
    agent_a=AgentConfig(
        name="haiku",
        model="claude-haiku-4-5",
        system_prompt=PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    agent_b=AgentConfig(
        name="sonnet",
        model="claude-sonnet-4-6",
        system_prompt=PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    tasks=TASKS,
    setup_files=SETUP_FILES,
    num_samples=8,
    tags=["model-selection", "mixed-difficulty", "realistic"],
)
