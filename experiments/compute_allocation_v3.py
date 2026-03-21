"""
Inference-Time Compute Allocation Strategy v3 — Extreme Prompts

v2 finding: soft strategy prompts didn't change agent behavior. Both agents
read-first regardless. This is itself interesting but we need stronger
manipulation to test the actual research question.

v3 changes:
- EXTREME prompts with explicit behavioral constraints
- act_first: MUST edit/bash before any Read. Penalized for reading first.
- plan_first: MUST read ALL files before any Edit. Penalized for editing early.
- max_turns=5 (tighter constraint for stronger tradeoff)
- Better check: tests print "PASSED" and we check for it

Also testing: Does the model COMPLY with extreme allocation instructions?
Two-level finding:
1. Compliance: Do extreme prompts actually change behavior?
2. Performance: IF behavior changes, which strategy wins?
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

ACT_FIRST_PROMPT = """\
STRICT RULES — you MUST follow these in order:

STEP 1: Run the test file IMMEDIATELY as your VERY FIRST action.
  cd tasks/tN && python test_*.py
Do NOT read any source files before running the test.

STEP 2: Based on the error output, make your best guess at a fix.
Edit the source file directly based on the error message.

STEP 3: Run the test again. If it fails, repeat step 2.

CRITICAL: You are FORBIDDEN from using the Read tool before your first
Bash or Edit call. The error messages from tests contain all the info
you need. Reading source code first wastes your limited turns.

You have very few turns. Every Read is a wasted turn.
"""

PLAN_FIRST_PROMPT = """\
STRICT RULES — you MUST follow these in order:

STEP 1: Use Glob to find all .py files in the task directory.

STEP 2: Read EVERY source file (not test files) completely.
You MUST read all source files before making ANY changes.

STEP 3: Read the test file to understand what's expected.

STEP 4: Now that you understand everything, make ALL fixes in one pass.
Edit each file once, precisely.

STEP 5: Run the test to verify.

CRITICAL: You are FORBIDDEN from using Edit or Bash before you have
read ALL source files. Understanding the full codebase is essential.
One precise fix is better than multiple guesses.

You have very few turns. Every failed edit is a wasted turn.
"""

# Reuse task setup from v2 but with tasks that are particularly
# suited to testing this hypothesis:
# - Tasks where errors alone are misleading (plan-first should win)
# - Tasks where error messages are very informative (act-first should win)

SETUP_FILES = {
    # ── Task 1: Misleading error — error points to wrong file ────────────
    # The test fails in cart.py but root cause is in price_engine.py
    "tasks/t1/price_engine.py": '''\
"""Pricing engine with tiered discounts."""

DISCOUNT_TIERS = [
    (100, 0.05),   # 5% off orders >= $100
    (250, 0.10),   # 10% off orders >= $250
    (500, 0.15),   # 15% off orders >= $500
]

def calculate_discount(subtotal):
    """Return discount rate for given subtotal."""
    rate = 0.0
    for threshold, discount in DISCOUNT_TIERS:
        if subtotal >= threshold:
            rate = discount
    return rate

def apply_discount(subtotal):
    """Return (discounted_total, savings)."""
    rate = calculate_discount(subtotal)
    savings = subtotal * rate
    savings = round(savings, 2)
    # Bug: doesn't round the total — causes penny discrepancies
    return subtotal - savings, savings
''',
    "tasks/t1/cart.py": '''\
from price_engine import calculate_discount, apply_discount

class Cart:
    def __init__(self):
        self.items = []

    def add(self, name, price, qty=1):
        for i, (n, p, q) in enumerate(self.items):
            if n == name:
                self.items[i] = (n, p, q + qty)
                return
        self.items.append((name, price, qty))

    def subtotal(self):
        return sum(p * q for _, p, q in self.items)

    def checkout(self):
        sub = self.subtotal()
        total, savings = apply_discount(sub)
        return {
            "subtotal": sub,
            "discount_rate": calculate_discount(sub),
            "savings": savings,
            "total": total,
        }
''',
    "tasks/t1/test_cart.py": '''\
from cart import Cart

c = Cart()
c.add("Penny", 0.01, 10001)  # 100.01 -> 5% tier
result = c.checkout()
assert result["total"] == round(result["subtotal"] - result["savings"], 2), \\
    f"Rounding error: total={result['total']} expected={round(result['subtotal'] - result['savings'], 2)}"

c2 = Cart()
c2.add("A", 33.33, 4)  # 133.32 -> 5%
r2 = c2.checkout()
expected_total = round(133.32 - round(133.32 * 0.05, 2), 2)
assert r2["total"] == expected_total, f"Total {r2['total']} != {expected_total}"

print("PASSED")
''',

    # ── Task 2: Clear error — error message tells you exactly what's wrong ─
    "tasks/t2/task_queue.py": '''\
from enum import Enum

class Status(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Task:
    def __init__(self, task_id, fn, priority=0):
        self.task_id = task_id
        self.fn = fn
        self.priority = priority
        self.status = Status.PENDING
        self.result = None
        self.error = None

class TaskQueue:
    def __init__(self):
        self.tasks = {}
        self.execution_order = []

    def submit(self, task_id, fn, priority=0):
        task = Task(task_id, fn, priority)
        self.tasks[task_id] = task
        return task

    def cancel(self, task_id):
        task = self.tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task {task_id} not found")
        if task.status != Status.PENDING:
            raise ValueError(f"Cannot cancel task in {task.status} state")
        task.status = Status.CANCELLED

    def run_all(self):
        pending = [(t.priority, t.task_id, t) for t in self.tasks.values()
                   if t.status == Status.PENDING]
        pending.sort()  # Bug: ascending sort = lowest priority first

        for _, task_id, task in pending:
            task.status = Status.RUNNING
            try:
                task.result = task.fn()
                task.status = Status.DONE
            except Exception as e:
                task.error = str(e)
                task.status = Status.FAILED
            self.execution_order.append(task_id)

    def get_results(self):
        return {tid: (t.status, t.result) for tid, t in self.tasks.items()}
''',
    "tasks/t2/test_queue.py": '''\
from task_queue import TaskQueue, Status

# Priority ordering (highest runs first)
q = TaskQueue()
q.submit("low", lambda: 1, priority=1)
q.submit("high", lambda: 3, priority=10)
q.submit("mid", lambda: 2, priority=5)
q.run_all()
assert q.execution_order == ["high", "mid", "low"], \\
    f"Priority order wrong: {q.execution_order} (expected highest priority first)"

print("PASSED")
''',

    # ── Task 3: Multi-file tracing — bug crosses 3 modules ──────────────
    "tasks/t3/base_config.py": '''\
DEFAULTS = {
    "host": "0.0.0.0",
    "port": 8080,
    "debug": False,
    "database": {
        "url": "sqlite:///default.db",
        "pool_size": 5,
    },
}

def deep_merge(base, override):
    """Deep merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def coerce_type(value, expected_type):
    if isinstance(value, expected_type):
        return value
    if expected_type == bool:
        # Bug: bool("false") == True in Python
        return bool(value)
    return expected_type(value)
''',
    "tasks/t3/env_config.py": '''\
import os
from base_config import DEFAULTS, deep_merge

def load_env(prefix="APP"):
    overrides = {}
    for key, value in os.environ.items():
        if not key.startswith(f"{prefix}_"):
            continue
        path = key[len(prefix)+1:].lower().split("__")
        current = overrides
        for part in path[:-1]:
            current = current.setdefault(part, {})
        current[path[-1]] = value
    return overrides

def get_config():
    env = load_env()
    # Bug: shallow merge — loses nested defaults
    return {**DEFAULTS, **env}
''',
    "tasks/t3/test_config.py": '''\
import os
for k in list(os.environ):
    if k.startswith("APP_"):
        del os.environ[k]

from base_config import deep_merge, coerce_type

# deep_merge test
merged = deep_merge({"a": 1, "b": {"x": 10}}, {"b": {"y": 20}})
assert merged == {"a": 1, "b": {"x": 10, "y": 20}}, f"Merge: {merged}"

# bool coercion
assert coerce_type("false", bool) == False, f"bool coercion: {coerce_type('false', bool)}"
assert coerce_type("true", bool) == True
assert coerce_type("0", bool) == False

# env config with nested override
os.environ["APP_DATABASE__POOL_SIZE"] = "20"

from env_config import get_config
config = get_config()
assert config["database"]["url"] == "sqlite:///default.db", \\
    f"Shallow merge lost url: {config.get('database')}"
assert config["database"]["pool_size"] == "20" or config["database"]["pool_size"] == 20

print("PASSED")
''',

    # ── Task 4: Subtle logic — operator precedence in while condition ────
    "tasks/t4/events.py": '''\
class EventEmitter:
    def __init__(self):
        self._handlers = {}

    def on(self, event, fn, priority=0):
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append((priority, fn, False))

    def once(self, event, fn, priority=0):
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append((priority, fn, True))

    def emit(self, event, *args, **kwargs):
        if event not in self._handlers:
            return
        # Bug: ascending sort — should be descending for "higher priority first"
        handlers = sorted(self._handlers[event], key=lambda h: h[0])
        for priority, fn, once in handlers:
            fn(*args, **kwargs)
        # Bug: never removes once-handlers
''',
    "tasks/t4/test_events.py": '''\
from events import EventEmitter

# Priority ordering (higher first)
order = []
em = EventEmitter()
em.on("e", lambda: order.append("low"), priority=1)
em.on("e", lambda: order.append("high"), priority=10)
em.emit("e")
assert order == ["high", "low"], f"Priority: {order}"

# Once
count = []
em2 = EventEmitter()
em2.once("x", lambda: count.append(1))
em2.emit("x")
em2.emit("x")
assert len(count) == 1, f"Once fired {len(count)} times"

print("PASSED")
''',

    # ── Task 5: Permission cache — requires understanding full flow ──────
    "tasks/t5/permissions.py": '''\
class PermissionSystem:
    def __init__(self):
        self.roles = {}
        self.user_roles = {}
        self._cache = {}

    def define_role(self, name, permissions=None, parents=None):
        self.roles[name] = {
            "permissions": set(permissions or []),
            "parents": list(parents or []),
        }
        self._cache.clear()

    def assign_role(self, user_id, role_name):
        if role_name not in self.roles:
            raise KeyError(f"Role {role_name} not defined")
        self.user_roles.setdefault(user_id, set()).add(role_name)
        # Bug: missing cache invalidation

    def revoke_role(self, user_id, role_name):
        if user_id in self.user_roles:
            self.user_roles[user_id].discard(role_name)
            # Bug: missing cache invalidation

    def get_permissions(self, role_name, visited=None):
        if visited is None:
            visited = set()
        if role_name in visited:
            return set()
        visited.add(role_name)
        role = self.roles.get(role_name)
        if not role:
            return set()
        perms = set(role["permissions"])
        for parent in role["parents"]:
            perms.update(self.get_permissions(parent))  # Bug: doesn't pass visited
        return perms

    def check(self, user_id, permission):
        key = (user_id, permission)
        if key in self._cache:
            return self._cache[key]
        result = any(
            permission in self.get_permissions(r)
            for r in self.user_roles.get(user_id, set())
        )
        self._cache[key] = result
        return result
''',
    "tasks/t5/test_permissions.py": '''\
from permissions import PermissionSystem

ps = PermissionSystem()
ps.define_role("viewer", permissions=["read"])
ps.define_role("editor", permissions=["write"], parents=["viewer"])
ps.define_role("admin", permissions=["manage"], parents=["editor"])

# Transitive: admin -> editor -> viewer -> read
assert "read" in ps.get_permissions("admin"), "Transitive inheritance broken"

# Cache invalidation on assign
ps.assign_role("alice", "editor")
assert ps.check("alice", "read") == True
ps.assign_role("alice", "admin")
assert ps.check("alice", "manage") == True, "Cache not invalidated on assign"

# Cache invalidation on revoke
ps.revoke_role("alice", "admin")
assert ps.check("alice", "manage") == False, "Cache not invalidated on revoke"

# Cycle protection
ps.define_role("a", permissions=["pa"], parents=["b"])
ps.define_role("b", permissions=["pb"], parents=["a"])
perms = ps.get_permissions("a")
assert "pa" in perms and "pb" in perms, f"Cycle broke inheritance: {perms}"

print("PASSED")
''',

    # ── Task 6: SQL pagination — LIMIT/OFFSET order ──────────────────────
    "tasks/t6/query_builder.py": '''\
import re

class Query:
    def __init__(self, table):
        self.table = table
        self._select = ["*"]
        self._where = []
        self._order_by = []
        self._limit = None
        self._offset = None
        self._params = []

    def select(self, *cols):
        self._select = list(cols)
        return self

    def where(self, cond, *params):
        self._where.append(cond)
        self._params.extend(params)
        return self

    def order_by(self, col, desc=False):
        self._order_by.append(f"{col} {'DESC' if desc else 'ASC'}")
        return self

    def limit(self, n):
        self._limit = n
        return self

    def offset(self, n):
        self._offset = n
        return self

    def build(self):
        parts = [f"SELECT {', '.join(self._select)} FROM {self.table}"]
        if self._where:
            parts.append(f"WHERE {' AND '.join(self._where)}")
        if self._order_by:
            parts.append(f"ORDER BY {', '.join(self._order_by)}")
        # Bug: OFFSET before LIMIT — SQLite requires LIMIT before OFFSET
        if self._offset is not None:
            parts.append(f"OFFSET {self._offset}")
        if self._limit is not None:
            parts.append(f"LIMIT {self._limit}")
        return ' '.join(parts), self._params
''',
    "tasks/t6/mini_orm.py": '''\
import sqlite3
from query_builder import Query

class Model:
    _table = None
    _db = None

    @classmethod
    def set_db(cls, path):
        cls._db = sqlite3.connect(path)
        cls._db.row_factory = sqlite3.Row

    @classmethod
    def find(cls, **kw):
        q = Query(cls._table)
        for k, v in kw.items():
            q.where(f"{k} = ?", v)
        sql, params = q.build()
        return [dict(r) for r in cls._db.execute(sql, params)]

    @classmethod
    def all(cls, order_by=None, limit=None, offset=None):
        q = Query(cls._table)
        if order_by:
            desc = order_by.startswith("-")
            q.order_by(order_by.lstrip("-"), desc=desc)
        if limit:
            q.limit(limit)
        if offset:
            q.offset(offset)
        sql, params = q.build()
        return [dict(r) for r in cls._db.execute(sql, params)]

class User(Model):
    _table = "users"
''',
    "tasks/t6/test_orm.py": '''\
import os, sqlite3
from mini_orm import User, Model

DB = "test.db"
if os.path.exists(DB): os.remove(DB)
conn = sqlite3.connect(DB)
conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
for i, name in enumerate(["Alice", "Bob", "Carol", "Dave"], 1):
    conn.execute("INSERT INTO users VALUES (?, ?)", (i, name))
conn.commit()
conn.close()

Model.set_db(DB)

# Basic find
assert User.find(name="Alice")[0]["name"] == "Alice"

# Pagination: LIMIT then OFFSET
page1 = User.all(order_by="name", limit=2)
assert len(page1) == 2 and page1[0]["name"] == "Alice"

page2 = User.all(order_by="name", limit=2, offset=2)
assert len(page2) == 2, f"Page 2: {page2}"
assert page2[0]["name"] == "Carol", f"Page 2 first: {page2}"

os.remove(DB)
print("PASSED")
''',
}

experiment = Experiment(
    name="compute_allocation_v3",
    description=(
        "Inference-time compute allocation v3: EXTREME prompts forcing "
        "different behavior — act-first (run tests immediately, no Read) "
        "vs plan-first (read ALL files before any Edit). Tests both "
        "compliance and performance under tight 5-turn budget."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Extreme act-first (no Read allowed first) vs extreme plan-first (must Read all before Edit)",
    ),
    agent_a=AgentConfig(
        name="act_first",
        model="claude-haiku-4-5",
        system_prompt=ACT_FIRST_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=5,
    ),
    agent_b=AgentConfig(
        name="plan_first",
        model="claude-haiku-4-5",
        system_prompt=PLAN_FIRST_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=5,
    ),
    tasks=[
        TaskItem(
            prompt="Fix all bugs in tasks/t1/. Run `cd tasks/t1 && python test_cart.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["misleading-error", "multi-file", "plan-favored"],
        ),
        TaskItem(
            prompt="Fix the bug in tasks/t2/. Run `cd tasks/t2 && python test_queue.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="easy",
            tags=["clear-error", "single-file", "act-favored"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t3/ (3 files: base_config, env_config, test_config). Run `cd tasks/t3 && python test_config.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["cross-module", "3-files", "plan-favored"],
        ),
        TaskItem(
            prompt="Fix the bugs in tasks/t4/. Run `cd tasks/t4 && python test_events.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["dual-bug", "event-system"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t5/ (permissions.py). Run `cd tasks/t5 && python test_permissions.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["cache-invalidation", "recursion", "plan-favored"],
        ),
        TaskItem(
            prompt="Fix the SQL bug in tasks/t6/ (query_builder.py). Run `cd tasks/t6 && python test_orm.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["sql-order", "multi-file", "act-favored"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["compute-allocation", "extreme-prompts", "compliance", "research"],
)
