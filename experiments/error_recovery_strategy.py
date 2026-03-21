"""
Error Recovery Strategy: Blind Retry vs Structured Reflection

RESEARCH QUESTION:
When a coding agent's first fix attempt fails, which recovery strategy
produces better outcomes — simply trying again, or pausing to analyze
the failure before retrying?

Literature gap:
- Failure taxonomies are well-established (MAST: 14 modes, κ=0.88;
  Tool invocation: 12 categories across 1980 instances)
- But NO controlled study tests which RECOVERY STRATEGY works best
  for each failure type. This bridges taxonomy → intervention.

Design:
- Agent A (blind_retry): On failure, immediately try a different fix.
  No structured reflection. "If it doesn't work, try something else."
- Agent B (reflect_retry): On failure, MUST re-read error + code,
  explicitly state what went wrong, form hypothesis, THEN retry.
- Same model (haiku), tools, max_turns=8 (enough for ~2 fix cycles)
- Tasks: multi-bug problems where first attempt typically fails
  and produces a DIFFERENT error than the original.
- n=5 for statistical power

Key insight: the tasks are designed so that fixing Bug A reveals Bug B,
and the error from Bug B is misleading unless you understand the full code.
This is where reflection should shine over blind retry.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

BLIND_RETRY_PROMPT = """\
You are a developer fixing bugs. Follow this workflow:

1. Read the relevant files
2. Run the test to see what fails
3. Fix the bug you see
4. Run the test again

IF THE TEST STILL FAILS after your fix:
- Try a different fix immediately
- Don't spend time analyzing — just try another approach
- Speed matters: the faster you try alternatives, the more chances you get
- If one approach doesn't work, switch to something completely different

You have limited turns. Maximize attempts, not analysis.
"""

REFLECT_RETRY_PROMPT = """\
You are a developer fixing bugs. Follow this workflow:

1. Read the relevant files
2. Run the test to see what fails
3. Fix the bug you see
4. Run the test again

IF THE TEST STILL FAILS after your fix:
- STOP. Do NOT immediately try another fix.
- Re-read the FULL error message and traceback carefully
- Re-read the source code around the failure point
- State explicitly: "The fix failed because [reason]. My hypothesis was \
wrong because [explanation]. The actual root cause is [new theory]."
- Only THEN implement your revised fix

NEVER make two fix attempts without a reflection step in between.
Understanding WHY a fix failed is more valuable than trying more fixes.
"""

SETUP_FILES = {
    # ══════════════════════════════════════════════════════════════════════
    # Task 1: Cascading bugs — fixing bug A reveals different bug B
    # Inventory system: stock calculation + reorder logic
    # Bug A: stock count uses wrong field (visible)
    # Bug B: reorder threshold comparison is inverted (hidden until A fixed)
    # ══════════════════════════════════════════════════════════════════════
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
        """Return available stock (total - reserved)."""
        p = self.products[name]
        return p.reserved - p.stock  # Bug A: operands swapped

    def reserve(self, name, qty):
        """Reserve stock for an order. Returns True if successful."""
        avail = self.available(name)
        if qty > avail:
            return False
        self.products[name].reserved += qty
        self._check_reorder(name)
        return True

    def _check_reorder(self, name):
        """Add to reorder queue if stock is low."""
        p = self.products[name]
        available = p.stock - p.reserved
        # Bug B: comparison inverted — reorders when ABOVE threshold
        if available > p.reorder_point:
            if name not in self.reorder_queue:
                self.reorder_queue.append(name)

    def fulfill(self, name, qty):
        """Ship reserved items, reducing both stock and reserved."""
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

# Available should be stock - reserved
assert inv.available("Widget") == 50, f"Available: {inv.available('Widget')}"

# Reserve some
assert inv.reserve("Widget", 20) == True
assert inv.available("Widget") == 30, f"After reserve: {inv.available('Widget')}"

# Can't reserve more than available
assert inv.reserve("Widget", 35) == False

# Fulfill
inv.fulfill("Widget", 10)
assert inv.available("Widget") == 20  # stock=40, reserved=10

# Reorder: after fulfilling down to low stock
inv2 = Inventory()
inv2.add_product(Product("Gadget", stock=15, reserved=0, reorder_point=10))
inv2.reserve("Gadget", 8)  # available = 7, below reorder_point=10
assert "Gadget" in inv2.reorder_queue, f"Should reorder: available=7 < threshold=10, queue={inv2.reorder_queue}"

# High stock should NOT trigger reorder
inv3 = Inventory()
inv3.add_product(Product("Thing", stock=100, reserved=0, reorder_point=10))
inv3.reserve("Thing", 1)  # available = 99, well above threshold
assert "Thing" not in inv3.reorder_queue, f"Should NOT reorder: available=99 > threshold=10, queue={inv3.reorder_queue}"

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 2: Red herring error — first error points to test code, not source
    # Markdown parser: heading detection + list parsing
    # Bug A: heading regex misses single # (obvious from error)
    # Bug B: list items don't handle nested content (only appears after A fixed)
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t2/markdown.py": '''\
"""Simple markdown to HTML converter."""
import re

def parse_markdown(text):
    """Convert markdown text to HTML."""
    lines = text.split("\\n")
    html_parts = []
    in_list = False

    for line in lines:
        # Headings: ## Title -> <h2>Title</h2>
        heading_match = re.match(r'^(#{2,6})\\s+(.+)$', line)  # Bug A: {2,6} misses single #
        if heading_match:
            level = len(heading_match.group(1))
            html_parts.append(f"<h{level}>{heading_match.group(2)}</h{level}>")
            continue

        # Unordered lists: - item -> <li>item</li>
        list_match = re.match(r'^-\\s+(.+)$', line)
        if list_match:
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            content = list_match.group(1)
            # Bug B: doesn't process inline bold/italic within list items
            html_parts.append(f"<li>{content}</li>")
            continue

        # Close list if we're no longer in list items
        if in_list and not line.strip().startswith("-"):
            html_parts.append("</ul>")
            in_list = False

        # Bold: **text** -> <strong>text</strong>
        line = re.sub(r'\\*\\*(.+?)\\*\\*', r'<strong>\\1</strong>', line)
        # Italic: *text* -> <em>text</em>
        line = re.sub(r'\\*(.+?)\\*', r'<em>\\1</em>', line)

        if line.strip():
            html_parts.append(f"<p>{line}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\\n".join(html_parts)
''',
    "tasks/t2/test_markdown.py": '''\
from markdown import parse_markdown

# Single # heading (h1)
html = parse_markdown("# Hello World")
assert "<h1>Hello World</h1>" in html, f"H1 missing: {html}"

# Multi-level headings
html2 = parse_markdown("## Subtitle\\n### Section")
assert "<h2>Subtitle</h2>" in html2
assert "<h3>Section</h3>" in html2

# Bold and italic
html3 = parse_markdown("This is **bold** and *italic*")
assert "<strong>bold</strong>" in html3
assert "<em>italic</em>" in html3

# List with inline formatting
html4 = parse_markdown("- **bold item**\\n- *italic item*\\n- plain item")
assert "<strong>bold item</strong>" in html4, f"Bold in list missing: {html4}"
assert "<em>italic item</em>" in html4, f"Italic in list missing: {html4}"
assert "<ul>" in html4
assert "</ul>" in html4

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 3: Interacting bugs — fix for A breaks the fix for B
    # Token bucket rate limiter
    # Bug A: refill doesn't cap at burst (easy to spot)
    # Bug B: allow() doesn't refill before checking (hidden interaction)
    # Naive fix for A (add min()) can mask B, leading to confusing test failures
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t3/limiter.py": '''\
"""Token bucket rate limiter."""

class RateLimiter:
    def __init__(self, rate, burst, now=0):
        self.rate = rate        # tokens per second
        self.burst = burst      # max tokens
        self.tokens = burst     # start full
        self.last_time = now

    def _refill(self, now):
        elapsed = now - self.last_time
        self.tokens += elapsed * self.rate  # Bug A: no cap at burst
        self.last_time = now

    def allow(self, now, cost=1):
        """Check if request is allowed, consuming tokens if so."""
        # Bug B: doesn't call _refill before checking!
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def wait_time(self, now, cost=1):
        """Seconds until cost tokens are available."""
        self._refill(now)
        if self.tokens >= cost:
            return 0.0
        deficit = cost - self.tokens
        return deficit / self.rate
''',
    "tasks/t3/test_limiter.py": '''\
from limiter import RateLimiter

# Basic: start full, allow burst requests
rl = RateLimiter(rate=10, burst=5, now=0)
for i in range(5):
    assert rl.allow(now=0), f"Should allow request {i+1} from full bucket"
assert not rl.allow(now=0), "Should deny when empty"

# Refill: after waiting, tokens should replenish but not exceed burst
rl2 = RateLimiter(rate=10, burst=5, now=0)
for _ in range(5):
    rl2.allow(now=0)  # drain bucket
# Wait 1 second -> should have min(0+10, 5) = 5 tokens (capped at burst)
assert rl2.allow(now=1), "Should allow after refill"
# Verify burst cap: after 10 seconds we should still only have burst=5 tokens
rl3 = RateLimiter(rate=10, burst=5, now=0)
for _ in range(5):
    rl3.allow(now=0)
# Wait 10 seconds = 100 tokens generated, but capped at burst=5
for i in range(5):
    assert rl3.allow(now=10), f"Should allow request {i+1} after long wait"
assert not rl3.allow(now=10), "Should deny: only burst=5 tokens even after long wait"

# Wait time
rl4 = RateLimiter(rate=10, burst=5, now=0)
for _ in range(5):
    rl4.allow(now=0)
wt = rl4.wait_time(now=0, cost=3)
assert abs(wt - 0.3) < 0.01, f"Wait time: {wt}"

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 4: Misleading stack trace — error in utility used by multiple callers
    # LRU Cache with stats tracking
    # Bug A: eviction removes wrong item (MRU instead of LRU)
    # Bug B: stats.hit_rate divides wrong way (appears after A is fixed)
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t4/lru_cache.py": '''\
"""LRU Cache with size limit and hit/miss statistics."""
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
            self._store.move_to_end(key)  # Mark as recently used
            return self._store[key]
        self._misses += 1
        return None

    def put(self, key, value):
        if key in self._store:
            self._store[key] = value
            self._store.move_to_end(key)
            return
        if len(self._store) >= self.max_size:
            # Bug A: popitem(last=True) removes MOST recently used!
            # Should be popitem(last=False) for LRU eviction
            self._store.popitem(last=True)
        self._store[key] = value

    def stats(self):
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._store),
            # Bug B: hit_rate is misses/total instead of hits/total
            "hit_rate": self._misses / total if total > 0 else 0.0,
        }
''',
    "tasks/t4/test_lru.py": '''\
from lru_cache import LRUCache

# Basic get/put
c = LRUCache(max_size=3)
c.put("a", 1)
c.put("b", 2)
c.put("c", 3)
assert c.get("a") == 1
assert c.get("b") == 2

# LRU eviction: adding 4th item should evict LEAST recently used
# Access order: a, b were accessed via get; c was not
# So c is least recently used and should be evicted
c.put("d", 4)
assert c.get("c") is None, f"c should be evicted (LRU), but got {c.get('c')}"
assert c.get("a") == 1, "a should survive (recently accessed)"
assert c.get("b") == 2, "b should survive (recently accessed)"
assert c.get("d") == 4, "d should exist (just added)"

# Stats
c2 = LRUCache(max_size=2)
c2.put("x", 1)
c2.get("x")  # hit
c2.get("x")  # hit
c2.get("y")  # miss
s = c2.stats()
assert s["hits"] == 2, f"Hits: {s['hits']}"
assert s["misses"] == 1, f"Misses: {s['misses']}"
assert abs(s["hit_rate"] - 2/3) < 0.01, f"Hit rate should be ~0.67: {s['hit_rate']}"

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 5: Multi-symptom failure — three bugs produce one confusing error
    # Expression parser with variables and functions
    # Bug A: variable lookup doesn't check None vs undefined
    # Bug B: function call parsing doesn't consume closing paren
    # Bug C: operator precedence in chained comparisons
    # First fix typically addresses wrong root cause
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t5/calc.py": '''\
"""Calculator with variables and built-in functions."""
import math

class Calculator:
    def __init__(self):
        self.variables = {}
        self.functions = {
            "abs": abs,
            "sqrt": math.sqrt,
            "max": max,
            "min": min,
        }

    def evaluate(self, expr):
        """Evaluate expression string. Supports: +, -, *, /, (), variables, functions."""
        tokens = self._tokenize(expr)
        pos = [0]
        result = self._parse_expr(tokens, pos)
        if pos[0] < len(tokens):
            raise SyntaxError(f"Unexpected token: {tokens[pos[0]]}")
        return result

    def _tokenize(self, expr):
        tokens = []
        i = 0
        while i < len(expr):
            if expr[i].isspace():
                i += 1
            elif expr[i].isdigit() or (expr[i] == '.' and i+1 < len(expr) and expr[i+1].isdigit()):
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
                raise SyntaxError(f"Unknown character: {expr[i]}")
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

        # Unary minus
        if tok == ("OP", "-"):
            pos[0] += 1
            return -self._parse_factor(tokens, pos)

        # Parenthesized expr
        if tok == ("OP", "("):
            pos[0] += 1
            result = self._parse_expr(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]] != ("OP", ")"):
                raise SyntaxError("Missing )")
            pos[0] += 1
            return result

        # Number
        if tok[0] == "NUM":
            pos[0] += 1
            return tok[1]

        # Name: could be variable or function call
        if tok[0] == "NAME":
            name = tok[1]
            pos[0] += 1

            # Check for function call: name(args)
            if pos[0] < len(tokens) and tokens[pos[0]] == ("OP", "("):
                pos[0] += 1  # consume (
                args = []
                if pos[0] < len(tokens) and tokens[pos[0]] != ("OP", ")"):
                    args.append(self._parse_expr(tokens, pos))
                    while pos[0] < len(tokens) and tokens[pos[0]] == ("OP", ","):
                        pos[0] += 1
                        args.append(self._parse_expr(tokens, pos))
                # Bug B: doesn't consume closing paren!
                if pos[0] >= len(tokens) or tokens[pos[0]] != ("OP", ")"):
                    raise SyntaxError("Missing ) in function call")
                # Missing: pos[0] += 1  # consume )

                if name not in self.functions:
                    raise NameError(f"Unknown function: {name}")
                return self.functions[name](*args)

            # Variable lookup
            # Bug A: can't distinguish "variable is None" from "variable not set"
            val = self.variables.get(name)
            if val is None:  # Bug: what if variable IS None or 0?
                raise NameError(f"Undefined variable: {name}")
            return val

        raise SyntaxError(f"Unexpected: {tok}")

    def set_var(self, name, value):
        self.variables[name] = value
''',
    "tasks/t5/test_calc.py": '''\
from calc import Calculator

c = Calculator()

# Basic arithmetic
assert c.evaluate("2 + 3 * 4") == 14
assert c.evaluate("(2 + 3) * 4") == 20

# Variables
c.set_var("x", 10)
assert c.evaluate("x + 5") == 15
c.set_var("y", 0)
assert c.evaluate("y + 1") == 1, f"Zero variable broken: {c.evaluate('y + 1')}"

# Functions
assert c.evaluate("abs(-5)") == 5
assert c.evaluate("sqrt(16)") == 4.0
assert c.evaluate("max(3, 7)") == 7

# Function in expression
assert c.evaluate("abs(-3) + sqrt(4)") == 5.0, f"Function in expr: {c.evaluate('abs(-3) + sqrt(4)')}"

# Nested functions
assert c.evaluate("abs(min(-5, -3))") == 5

# Undefined variable error
try:
    c.evaluate("undefined_var")
    assert False, "Should raise NameError"
except NameError:
    pass

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 6: State-dependent bug — only manifests in specific sequence
    # Transaction log with rollback
    # Bug A: rollback doesn't restore all fields
    # Bug B: nested transactions lose parent state
    # Error after fixing A looks like A wasn't fixed (discourages blind retry)
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t6/transaction.py": '''\
"""Transaction manager with savepoints and rollback."""

class Transaction:
    def __init__(self, data):
        self._data = data
        self._savepoints = []
        self._active = False

    def begin(self):
        """Start a transaction (or nested savepoint)."""
        # Bug A: only saves top-level keys, not a deep copy
        self._savepoints.append(dict(self._data))
        self._active = True

    def commit(self):
        """Commit current transaction level."""
        if not self._savepoints:
            raise RuntimeError("No active transaction")
        self._savepoints.pop()
        if not self._savepoints:
            self._active = False

    def rollback(self):
        """Rollback to last savepoint."""
        if not self._savepoints:
            raise RuntimeError("No active transaction")
        saved = self._savepoints.pop()
        # Bug B: replaces the dict object instead of updating in place
        # This means external references to self._data won't see the rollback
        self._data = saved
        if not self._savepoints:
            self._active = False

    @property
    def data(self):
        return self._data

    @property
    def active(self):
        return self._active
''',
    "tasks/t6/test_transaction.py": '''\
from transaction import Transaction

# Basic transaction + commit
data = {"balance": 100, "name": "Alice"}
tx = Transaction(data)
tx.begin()
tx.data["balance"] = 200
tx.commit()
assert tx.data["balance"] == 200

# Rollback restores state
data2 = {"balance": 100, "name": "Bob"}
tx2 = Transaction(data2)
tx2.begin()
tx2.data["balance"] = 0
tx2.rollback()
assert tx2.data["balance"] == 100, f"Rollback failed: {tx2.data}"

# External reference should see rollback
data3 = {"balance": 100, "items": ["a", "b"]}
tx3 = Transaction(data3)
tx3.begin()
tx3.data["balance"] = 999
tx3.data["items"].append("c")
tx3.rollback()
assert data3["balance"] == 100, f"External ref not updated: {data3}"
assert data3["items"] == ["a", "b"], f"Deep state not restored: {data3['items']}"

# Nested transactions
data4 = {"x": 1}
tx4 = Transaction(data4)
tx4.begin()          # savepoint 1
tx4.data["x"] = 2
tx4.begin()          # savepoint 2
tx4.data["x"] = 3
tx4.rollback()       # back to savepoint 1
assert tx4.data["x"] == 2, f"Nested rollback: {tx4.data}"
tx4.commit()         # commit savepoint 1
assert tx4.data["x"] == 2

print("PASSED")
''',
}

experiment = Experiment(
    name="error_recovery_strategy",
    description=(
        "Error recovery: blind retry vs structured reflection. "
        "Tasks have cascading/interacting bugs where first fix often fails. "
        "Tests whether pausing to analyze failure improves recovery rate."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="blind retry (try different fix fast) vs reflect-then-retry (analyze failure before fixing)",
    ),
    agent_a=AgentConfig(
        name="blind_retry",
        model="claude-haiku-4-5",
        system_prompt=BLIND_RETRY_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    agent_b=AgentConfig(
        name="reflect_retry",
        model="claude-haiku-4-5",
        system_prompt=REFLECT_RETRY_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    tasks=[
        TaskItem(
            prompt="Fix all bugs in tasks/t1/ (inventory.py). Run `cd tasks/t1 && python test_inventory.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["cascading-bugs", "operand-swap"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t2/ (markdown.py). Run `cd tasks/t2 && python test_markdown.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["cascading-bugs", "regex"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t3/ (limiter.py). Run `cd tasks/t3 && python test_limiter.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["interacting-bugs", "missing-call"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t4/ (lru_cache.py). Run `cd tasks/t4 && python test_lru.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["cascading-bugs", "wrong-direction"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t5/ (calc.py). Run `cd tasks/t5 && python test_calc.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["multi-symptom", "parser", "three-bugs"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t6/ (transaction.py). Run `cd tasks/t6 && python test_transaction.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["state-dependent", "deep-copy", "rollback"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["error-recovery", "reflection", "cascading-bugs", "research"],
)
