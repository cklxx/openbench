"""
Error Recovery Strategy v2 — Extreme Behavioral Constraints

v1 finding: moderate prompts → identical behavior, 14/14 tie.
Model ignores soft recovery instructions (same as compute allocation v2).

v2 approach: Instead of "how to retry", test structurally different
fix strategies with extreme prompts:
- Agent A (incremental_fix): Fix ONE bug at a time. Run test after EACH fix.
  This maximizes feedback loops but risks running out of turns.
- Agent B (batch_fix): Read ALL code, identify ALL bugs, fix ALL at once.
  This minimizes test cycles but risks missing bugs.

This is a more fundamental question: iterative debugging vs comprehensive
analysis — the recovery equivalent of act-first vs plan-first.

Same cascading-bug tasks from v1 (where bugs interact).
Tighter budget: max_turns=6.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

INCREMENTAL_FIX_PROMPT = """\
STRICT RULES for fixing bugs:

1. Read the test file FIRST to understand what's expected
2. Read ONE source file
3. Find the FIRST bug you see
4. Fix ONLY that one bug
5. Run the test immediately
6. If the test still fails, go back to step 2 and find the NEXT bug
7. Repeat: fix ONE bug → test → fix NEXT bug → test

CRITICAL CONSTRAINTS:
- NEVER fix more than one bug per Edit call
- ALWAYS run the test between each fix
- You are FORBIDDEN from fixing multiple bugs before testing
- Each fix-then-test cycle gives you feedback for the next fix

This incremental approach ensures each fix is validated before moving on.
"""

BATCH_FIX_PROMPT = """\
STRICT RULES for fixing bugs:

1. Read ALL source files in the task directory (not test files)
2. Read the test file to understand expected behavior
3. Identify EVERY bug across all files — list them all
4. Fix ALL bugs in a single pass (one Edit per file, but fix everything)
5. Run the test ONCE at the end to verify

CRITICAL CONSTRAINTS:
- You MUST read every .py file before making ANY edit
- You are FORBIDDEN from running the test before all fixes are applied
- Do NOT run partial tests — fix EVERYTHING first, test ONCE at the end
- Your first Bash call should be the final verification test

This comprehensive approach ensures you understand ALL interactions
between bugs before touching any code.
"""

# Reuse same setup files from v1 — they're designed for cascading bugs
SETUP_FILES = {
    # Task 1: Inventory — Bug A reveals Bug B
    "tasks/t1/inventory.py": '''\
"""Inventory management with auto-reorder."""

class Product:
    def __init__(self, name, stock, reserved=0, reorder_point=10):
        self.name = name
        self.stock = stock
        self.reserved = reserved
        self.reorder_point = reorder_point

class Inventory:
    def __init__(self):
        self.products = {}
        self.reorder_queue = []

    def add_product(self, product):
        self.products[product.name] = product

    def available(self, name):
        p = self.products[name]
        return p.reserved - p.stock  # Bug A: operands swapped

    def reserve(self, name, qty):
        avail = self.available(name)
        if qty > avail:
            return False
        self.products[name].reserved += qty
        self._check_reorder(name)
        return True

    def _check_reorder(self, name):
        p = self.products[name]
        available = p.stock - p.reserved
        if available > p.reorder_point:  # Bug B: > should be <
            if name not in self.reorder_queue:
                self.reorder_queue.append(name)

    def fulfill(self, name, qty):
        p = self.products[name]
        if qty > p.reserved:
            raise ValueError(f"Cannot fulfill {qty}, only {p.reserved} reserved")
        p.stock -= qty
        p.reserved -= qty
        self._check_reorder(name)
''',
    "tasks/t1/test_inventory.py": '''\
from inventory import Inventory, Product

inv = Inventory()
inv.add_product(Product("Widget", stock=50, reserved=0, reorder_point=10))
assert inv.available("Widget") == 50, f"Available: {inv.available('Widget')}"
assert inv.reserve("Widget", 20) == True
assert inv.available("Widget") == 30, f"After reserve: {inv.available('Widget')}"
assert inv.reserve("Widget", 35) == False

inv.fulfill("Widget", 10)
assert inv.available("Widget") == 20

inv2 = Inventory()
inv2.add_product(Product("Gadget", stock=15, reserved=0, reorder_point=10))
inv2.reserve("Gadget", 8)
assert "Gadget" in inv2.reorder_queue, f"Should reorder: avail=7 < 10, queue={inv2.reorder_queue}"

inv3 = Inventory()
inv3.add_product(Product("Thing", stock=100, reserved=0, reorder_point=10))
inv3.reserve("Thing", 1)
assert "Thing" not in inv3.reorder_queue, f"Should NOT reorder: avail=99 > 10"

print("PASSED")
''',

    # Task 2: Rate limiter — interacting bugs
    "tasks/t2/limiter.py": '''\
class RateLimiter:
    def __init__(self, rate, burst, now=0):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_time = now

    def _refill(self, now):
        elapsed = now - self.last_time
        self.tokens += elapsed * self.rate  # Bug A: no burst cap
        self.last_time = now

    def allow(self, now, cost=1):
        # Bug B: doesn't call _refill!
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def wait_time(self, now, cost=1):
        self._refill(now)
        if self.tokens >= cost:
            return 0.0
        return (cost - self.tokens) / self.rate
''',
    "tasks/t2/test_limiter.py": '''\
from limiter import RateLimiter

rl = RateLimiter(rate=10, burst=5, now=0)
for i in range(5):
    assert rl.allow(now=0), f"Should allow {i+1}"
assert not rl.allow(now=0), "Should deny when empty"

rl2 = RateLimiter(rate=10, burst=5, now=0)
for _ in range(5):
    rl2.allow(now=0)
assert rl2.allow(now=1), "Should allow after refill"

rl3 = RateLimiter(rate=10, burst=5, now=0)
for _ in range(5):
    rl3.allow(now=0)
for i in range(5):
    assert rl3.allow(now=10), f"Should allow {i+1} after long wait"
assert not rl3.allow(now=10), "Burst cap: only 5 even after 10s"

rl4 = RateLimiter(rate=10, burst=5, now=0)
for _ in range(5):
    rl4.allow(now=0)
wt = rl4.wait_time(now=0, cost=3)
assert abs(wt - 0.3) < 0.01, f"Wait: {wt}"

print("PASSED")
''',

    # Task 3: LRU + stats — cascading direction bugs
    "tasks/t3/lru_cache.py": '''\
from collections import OrderedDict

class LRUCache:
    def __init__(self, max_size=3):
        self.max_size = max_size
        self._store = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key):
        if key in self._store:
            self._hits += 1
            self._store.move_to_end(key)
            return self._store[key]
        self._misses += 1
        return None

    def put(self, key, value):
        if key in self._store:
            self._store[key] = value
            self._store.move_to_end(key)
            return
        if len(self._store) >= self.max_size:
            self._store.popitem(last=True)  # Bug A: removes MRU not LRU
        self._store[key] = value

    def stats(self):
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._store),
            "hit_rate": self._misses / total if total > 0 else 0.0,  # Bug B: misses/total not hits/total
        }
''',
    "tasks/t3/test_lru.py": '''\
from lru_cache import LRUCache

c = LRUCache(max_size=3)
c.put("a", 1)
c.put("b", 2)
c.put("c", 3)
assert c.get("a") == 1
assert c.get("b") == 2

c.put("d", 4)
assert c.get("c") is None, f"c should be evicted (LRU), got {c.get('c')}"
assert c.get("a") == 1, "a should survive"
assert c.get("b") == 2, "b should survive"
assert c.get("d") == 4, "d should exist"

c2 = LRUCache(max_size=2)
c2.put("x", 1)
c2.get("x")
c2.get("x")
c2.get("y")
s = c2.stats()
assert s["hits"] == 2
assert s["misses"] == 1
assert abs(s["hit_rate"] - 2/3) < 0.01, f"Hit rate: {s['hit_rate']}"

print("PASSED")
''',

    # Task 4: Calculator — 3 interacting bugs
    "tasks/t4/calc.py": '''\
import math

class Calculator:
    def __init__(self):
        self.variables = {}
        self.functions = {"abs": abs, "sqrt": math.sqrt, "max": max, "min": min}

    def evaluate(self, expr):
        tokens = self._tokenize(expr)
        pos = [0]
        result = self._parse_expr(tokens, pos)
        if pos[0] < len(tokens):
            raise SyntaxError(f"Unexpected: {tokens[pos[0]]}")
        return result

    def _tokenize(self, expr):
        tokens = []
        i = 0
        while i < len(expr):
            if expr[i].isspace():
                i += 1
            elif expr[i].isdigit() or expr[i] == '.':
                j = i
                while j < len(expr) and (expr[j].isdigit() or expr[j] == '.'):
                    j += 1
                tokens.append(("NUM", float(expr[i:j])))
                i = j
            elif expr[i].isalpha() or expr[i] == '_':
                j = i
                while j < len(expr) and (expr[j].isalnum() or expr[j] == '_'):
                    j += 1
                tokens.append(("NAME", expr[i:j]))
                i = j
            elif expr[i] in '+-*/(),':
                tokens.append(("OP", expr[i]))
                i += 1
            else:
                raise SyntaxError(f"Unknown: {expr[i]}")
        return tokens

    def _parse_expr(self, tokens, pos):
        left = self._parse_term(tokens, pos)
        while pos[0] < len(tokens) and tokens[pos[0]][1] in ('+', '-'):
            op = tokens[pos[0]][1]
            pos[0] += 1
            right = self._parse_term(tokens, pos)
            left = left + right if op == '+' else left - right
        return left

    def _parse_term(self, tokens, pos):
        left = self._parse_factor(tokens, pos)
        while pos[0] < len(tokens) and tokens[pos[0]][1] in ('*', '/'):
            op = tokens[pos[0]][1]
            pos[0] += 1
            right = self._parse_factor(tokens, pos)
            left = left * right if op == '*' else left / right
        return left

    def _parse_factor(self, tokens, pos):
        if pos[0] >= len(tokens):
            raise SyntaxError("Unexpected end")
        tok = tokens[pos[0]]
        if tok == ("OP", "-"):
            pos[0] += 1
            return -self._parse_factor(tokens, pos)
        if tok == ("OP", "("):
            pos[0] += 1
            result = self._parse_expr(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]] != ("OP", ")"):
                raise SyntaxError("Missing )")
            pos[0] += 1
            return result
        if tok[0] == "NUM":
            pos[0] += 1
            return tok[1]
        if tok[0] == "NAME":
            name = tok[1]
            pos[0] += 1
            if pos[0] < len(tokens) and tokens[pos[0]] == ("OP", "("):
                pos[0] += 1
                args = []
                if pos[0] < len(tokens) and tokens[pos[0]] != ("OP", ")"):
                    args.append(self._parse_expr(tokens, pos))
                    while pos[0] < len(tokens) and tokens[pos[0]] == ("OP", ","):
                        pos[0] += 1
                        args.append(self._parse_expr(tokens, pos))
                if pos[0] >= len(tokens) or tokens[pos[0]] != ("OP", ")"):
                    raise SyntaxError("Missing )")
                # Bug B: doesn't consume closing paren
                if name not in self.functions:
                    raise NameError(f"Unknown function: {name}")
                return self.functions[name](*args)
            # Bug A: variable=0 treated as undefined
            val = self.variables.get(name)
            if val is None:
                raise NameError(f"Undefined: {name}")
            return val
        raise SyntaxError(f"Unexpected: {tok}")

    def set_var(self, name, value):
        self.variables[name] = value
''',
    "tasks/t4/test_calc.py": '''\
from calc import Calculator

c = Calculator()
assert c.evaluate("2 + 3 * 4") == 14
assert c.evaluate("(2 + 3) * 4") == 20

c.set_var("x", 10)
assert c.evaluate("x + 5") == 15
c.set_var("y", 0)
assert c.evaluate("y + 1") == 1, f"Zero var: {c.evaluate('y + 1')}"

assert c.evaluate("abs(-5)") == 5
assert c.evaluate("sqrt(16)") == 4.0
assert c.evaluate("max(3, 7)") == 7
assert c.evaluate("abs(-3) + sqrt(4)") == 5.0, f"Func in expr: {c.evaluate('abs(-3) + sqrt(4)')}"
assert c.evaluate("abs(min(-5, -3))") == 5

try:
    c.evaluate("undefined_var")
    assert False, "Should raise NameError"
except NameError:
    pass

print("PASSED")
''',

    # Task 5: Transaction — deep copy + reference preservation
    "tasks/t5/transaction.py": '''\
class Transaction:
    def __init__(self, data):
        self._data = data
        self._savepoints = []
        self._active = False

    def begin(self):
        self._savepoints.append(dict(self._data))  # Bug A: shallow copy
        self._active = True

    def commit(self):
        if not self._savepoints:
            raise RuntimeError("No active transaction")
        self._savepoints.pop()
        if not self._savepoints:
            self._active = False

    def rollback(self):
        if not self._savepoints:
            raise RuntimeError("No active transaction")
        saved = self._savepoints.pop()
        self._data = saved  # Bug B: loses external reference
        if not self._savepoints:
            self._active = False

    @property
    def data(self):
        return self._data

    @property
    def active(self):
        return self._active
''',
    "tasks/t5/test_transaction.py": '''\
from transaction import Transaction

data = {"balance": 100, "name": "Alice"}
tx = Transaction(data)
tx.begin()
tx.data["balance"] = 200
tx.commit()
assert tx.data["balance"] == 200

data2 = {"balance": 100}
tx2 = Transaction(data2)
tx2.begin()
tx2.data["balance"] = 0
tx2.rollback()
assert tx2.data["balance"] == 100, f"Rollback: {tx2.data}"

data3 = {"balance": 100, "items": ["a", "b"]}
tx3 = Transaction(data3)
tx3.begin()
tx3.data["balance"] = 999
tx3.data["items"].append("c")
tx3.rollback()
assert data3["balance"] == 100, f"External ref: {data3}"
assert data3["items"] == ["a", "b"], f"Deep: {data3['items']}"

data4 = {"x": 1}
tx4 = Transaction(data4)
tx4.begin()
tx4.data["x"] = 2
tx4.begin()
tx4.data["x"] = 3
tx4.rollback()
assert tx4.data["x"] == 2, f"Nested: {tx4.data}"
tx4.commit()
assert tx4.data["x"] == 2

print("PASSED")
''',

    # Task 6: Markdown parser — regex + inline formatting
    "tasks/t6/markdown.py": '''\
import re

def parse_markdown(text):
    lines = text.split("\\n")
    html_parts = []
    in_list = False
    for line in lines:
        heading = re.match(r'^(#{2,6})\\s+(.+)$', line)  # Bug A: misses h1
        if heading:
            level = len(heading.group(1))
            html_parts.append(f"<h{level}>{heading.group(2)}</h{level}>")
            continue
        list_match = re.match(r'^-\\s+(.+)$', line)
        if list_match:
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            content = list_match.group(1)
            # Bug B: no inline formatting in list items
            html_parts.append(f"<li>{content}</li>")
            continue
        if in_list and not line.strip().startswith("-"):
            html_parts.append("</ul>")
            in_list = False
        line = re.sub(r'\\*\\*(.+?)\\*\\*', r'<strong>\\1</strong>', line)
        line = re.sub(r'\\*(.+?)\\*', r'<em>\\1</em>', line)
        if line.strip():
            html_parts.append(f"<p>{line}</p>")
    if in_list:
        html_parts.append("</ul>")
    return "\\n".join(html_parts)
''',
    "tasks/t6/test_markdown.py": '''\
from markdown import parse_markdown

html = parse_markdown("# Hello World")
assert "<h1>Hello World</h1>" in html, f"H1: {html}"

html2 = parse_markdown("## Sub\\n### Section")
assert "<h2>Sub</h2>" in html2
assert "<h3>Section</h3>" in html2

html3 = parse_markdown("This is **bold** and *italic*")
assert "<strong>bold</strong>" in html3
assert "<em>italic</em>" in html3

html4 = parse_markdown("- **bold item**\\n- *italic item*\\n- plain")
assert "<strong>bold item</strong>" in html4, f"Bold in list: {html4}"
assert "<em>italic item</em>" in html4, f"Italic in list: {html4}"

print("PASSED")
''',
}

experiment = Experiment(
    name="error_recovery_v2",
    description=(
        "Error recovery v2: incremental fix (one bug at a time, test between) "
        "vs batch fix (find ALL bugs, fix ALL at once). Extreme prompts with "
        "FORBIDDEN constraints. Tight 6-turn budget, cascading bug tasks."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="incremental (fix-test-fix-test) vs batch (read-all, fix-all, test-once)",
    ),
    agent_a=AgentConfig(
        name="incremental_fix",
        model="claude-haiku-4-5",
        system_prompt=INCREMENTAL_FIX_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=6,
    ),
    agent_b=AgentConfig(
        name="batch_fix",
        model="claude-haiku-4-5",
        system_prompt=BATCH_FIX_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=6,
    ),
    tasks=[
        TaskItem(
            prompt="Fix all bugs in tasks/t1/ (inventory.py). Run `cd tasks/t1 && python test_inventory.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["cascading", "operand-swap"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t2/ (limiter.py). Run `cd tasks/t2 && python test_limiter.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["interacting", "missing-call"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t3/ (lru_cache.py). Run `cd tasks/t3 && python test_lru.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["cascading", "direction"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t4/ (calc.py). Run `cd tasks/t4 && python test_calc.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["multi-bug", "parser"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t5/ (transaction.py). Run `cd tasks/t5 && python test_transaction.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["deep-copy", "reference"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t6/ (markdown.py). Run `cd tasks/t6 && python test_markdown.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["cascading", "regex"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["error-recovery", "incremental-vs-batch", "extreme-prompts", "research"],
)
