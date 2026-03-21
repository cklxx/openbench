"""
Inference-Time Compute Allocation Strategy v2:
  Plan-First vs Act-First under TIGHT turn budget.

v1 finding: 15 turns was too generous — both strategies hit 100%.
v2 changes:
- Tighter budget: max_turns=8 (forces real tradeoff)
- Harder tasks: multi-file bugs, subtle interactions, cross-module issues
- Better check_fn: use setup_script to run tests and capture exit code
- Each task has a test script that agent must make pass

The key insight being tested: with only 8 turns, do you spend 3 reading
and 5 acting (plan-first) or all 8 acting with fast feedback (act-first)?
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

ACT_FIRST_PROMPT = """\
You are a fast, action-oriented developer. Your strategy:

1. Start writing code or making changes IMMEDIATELY
2. Run tests early and often to get feedback
3. Fix errors as they appear — iterate rapidly
4. Don't overthink — let the test results guide you

Speed is your advantage. The faster you get to a running state, the more
iterations you can fit within your limited turns. Trust your instincts,
write code, run it, fix it. Every turn spent reading without changing
something is a turn wasted.
"""

PLAN_FIRST_PROMPT = """\
You are a methodical, analysis-driven developer. Your strategy:

1. FIRST: Read ALL relevant source files before making any changes
2. THEN: Trace the data flow and identify every root cause
3. THEN: Form a complete fix plan — list every file and line to change
4. ONLY THEN: Implement all fixes in as few edits as possible
5. Finally: Run tests to verify

Understanding is your advantage. With limited turns, you CANNOT afford
mistakes. One wasted edit means one fewer chance to get it right. Read
thoroughly, understand completely, then fix everything in one pass.
"""

SETUP_FILES = {
    # ══════════════════════════════════════════════════════════════════════
    # Task 1 (medium): Shopping cart with discount calculation bug
    # Bug spans 2 files: Cart applies discounts wrong + PriceEngine rounds wrong
    # ══════════════════════════════════════════════════════════════════════
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
    # Bug: rounds savings but not the final total, causing penny discrepancies
    savings = round(savings, 2)
    return subtotal - savings, savings
''',
    "tasks/t1/cart.py": '''\
"""Shopping cart that uses PriceEngine for totals."""
from price_engine import calculate_discount, apply_discount

class Cart:
    def __init__(self):
        self.items = []  # [(name, price, qty)]

    def add(self, name, price, qty=1):
        # Bug: doesn't check for existing item — duplicates allowed
        for i, (n, p, q) in enumerate(self.items):
            if n == name:
                self.items[i] = (n, p, q + qty)
                return
        self.items.append((name, price, qty))

    def remove(self, name):
        self.items = [(n, p, q) for n, p, q in self.items if n != name]

    def subtotal(self):
        return sum(p * q for _, p, q in self.items)

    def checkout(self):
        """Return checkout summary with discount applied."""
        sub = self.subtotal()
        total, savings = apply_discount(sub)
        return {
            "items": [(n, p, q, p*q) for n, p, q in self.items],
            "subtotal": sub,
            "discount_rate": calculate_discount(sub),
            "savings": savings,
            "total": total,  # Bug: total should also be rounded to 2 decimal places
        }
''',
    "tasks/t1/test_cart.py": '''\
from cart import Cart

# Basic add/remove
c = Cart()
c.add("Widget", 29.99, 3)
c.add("Gadget", 49.99, 2)
assert len(c.items) == 2
assert c.subtotal() == 29.99 * 3 + 49.99 * 2  # 189.95

# Duplicate add should merge
c.add("Widget", 29.99, 2)
assert len(c.items) == 2, f"Duplicate created: {c.items}"
assert c.items[0][2] == 5, f"Qty not merged: {c.items[0]}"

# Remove
c.remove("Gadget")
assert len(c.items) == 1

# Discount tiers
c2 = Cart()
c2.add("A", 50.00, 1)
result = c2.checkout()
assert result["discount_rate"] == 0.0, f"No discount expected: {result}"

c3 = Cart()
c3.add("A", 33.33, 4)  # subtotal = 133.32 -> 5% discount
result3 = c3.checkout()
assert result3["discount_rate"] == 0.05
assert result3["savings"] == round(133.32 * 0.05, 2)  # 6.67
assert result3["total"] == round(133.32 - 6.67, 2), f"Total: {result3['total']} != {round(133.32-6.67, 2)}"

# Higher tier
c4 = Cart()
c4.add("X", 99.99, 3)  # subtotal = 299.97 -> 10% discount
result4 = c4.checkout()
assert result4["discount_rate"] == 0.10
expected_savings = round(299.97 * 0.10, 2)  # 30.00
expected_total = round(299.97 - expected_savings, 2)
assert result4["total"] == expected_total, f"Total {result4['total']} != {expected_total}"

# Ensure totals are properly rounded (no floating point issues)
c5 = Cart()
c5.add("Penny", 0.01, 10001)  # 100.01 -> 5% tier
result5 = c5.checkout()
assert result5["total"] == round(result5["subtotal"] - result5["savings"], 2), \
    f"Rounding error: total={result5['total']} sub={result5['subtotal']} save={result5['savings']}"

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 2 (medium): Async task queue with race condition in completion
    # Bug: task completion doesn't check if task was already cancelled
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t2/task_queue.py": '''\
"""Simple task queue with status tracking."""
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
        """Cancel a pending task."""
        task = self.tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task {task_id} not found")
        if task.status != Status.PENDING:
            raise ValueError(f"Cannot cancel task in {task.status} state")
        task.status = Status.CANCELLED

    def run_all(self):
        """Execute all pending tasks in priority order (highest first)."""
        pending = [(t.priority, t.task_id, t) for t in self.tasks.values()
                   if t.status == Status.PENDING]
        # Bug: sort is ascending (lowest priority first)
        pending.sort()

        for _, task_id, task in pending:
            task.status = Status.RUNNING
            try:
                task.result = task.fn()
                # Bug: doesn't check if task was cancelled during execution
                task.status = Status.DONE
            except Exception as e:
                task.error = str(e)
                task.status = Status.FAILED
            self.execution_order.append(task_id)

    def get_results(self):
        """Return dict of task_id -> (status, result)."""
        return {tid: (t.status, t.result) for tid, t in self.tasks.items()}

    def stats(self):
        """Return count per status."""
        from collections import Counter
        return dict(Counter(t.status for t in self.tasks.values()))
''',
    "tasks/t2/test_queue.py": '''\
from task_queue import TaskQueue, Status

# Basic execution
q = TaskQueue()
q.submit("a", lambda: "hello")
q.submit("b", lambda: "world")
q.run_all()
results = q.get_results()
assert results["a"] == (Status.DONE, "hello")
assert results["b"] == (Status.DONE, "world")

# Priority ordering (highest runs first)
q2 = TaskQueue()
q2.submit("low", lambda: 1, priority=1)
q2.submit("high", lambda: 3, priority=10)
q2.submit("mid", lambda: 2, priority=5)
q2.run_all()
assert q2.execution_order == ["high", "mid", "low"], f"Priority order: {q2.execution_order}"

# Error handling
q3 = TaskQueue()
q3.submit("ok", lambda: 42)
q3.submit("fail", lambda: 1/0)
q3.run_all()
assert q3.tasks["ok"].status == Status.DONE
assert q3.tasks["fail"].status == Status.FAILED
assert "division" in q3.tasks["fail"].error.lower()

# Cancel
q4 = TaskQueue()
q4.submit("x", lambda: "x")
q4.submit("y", lambda: "y")
q4.cancel("y")
q4.run_all()
assert q4.tasks["x"].status == Status.DONE
assert q4.tasks["y"].status == Status.CANCELLED
assert q4.execution_order == ["x"], f"Cancelled task ran: {q4.execution_order}"

# Cannot cancel non-pending
q5 = TaskQueue()
q5.submit("z", lambda: "z")
q5.run_all()
try:
    q5.cancel("z")
    assert False, "Should not cancel completed task"
except ValueError:
    pass

# Stats
stats = q4.stats()
assert stats[Status.DONE] == 1
assert stats[Status.CANCELLED] == 1

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 3 (hard): Config system with inheritance + override chains
    # 3 files: base_config -> env_config -> runtime_config
    # Bugs: inheritance chain broken, type coercion wrong, merge is shallow
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t3/base_config.py": '''\
"""Base configuration with defaults and type validation."""

SCHEMA = {
    "host": str,
    "port": int,
    "debug": bool,
    "workers": int,
    "database": {
        "url": str,
        "pool_size": int,
        "timeout": int,
    },
    "logging": {
        "level": str,
        "file": str,
    },
}

DEFAULTS = {
    "host": "0.0.0.0",
    "port": 8080,
    "debug": False,
    "workers": 4,
    "database": {
        "url": "sqlite:///default.db",
        "pool_size": 5,
        "timeout": 30,
    },
    "logging": {
        "level": "INFO",
        "file": "/var/log/app.log",
    },
}

def deep_merge(base, override):
    """Deep merge override into base. Override wins on conflicts."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def validate_type(value, expected_type):
    """Validate and coerce value to expected type."""
    if isinstance(expected_type, dict):
        if not isinstance(value, dict):
            raise TypeError(f"Expected dict, got {type(value)}")
        return value
    if isinstance(value, expected_type):
        return value
    # Coercion
    try:
        if expected_type == bool:
            # Bug: bool("false") is True in Python! Need special handling
            return bool(value)
        return expected_type(value)
    except (ValueError, TypeError) as e:
        raise TypeError(f"Cannot coerce {value!r} to {expected_type}: {e}")
''',
    "tasks/t3/env_config.py": '''\
"""Load config overrides from environment variables."""
import os
from base_config import DEFAULTS, deep_merge, validate_type, SCHEMA

def load_env_config(prefix="APP"):
    """Load config from env vars. Supports nested keys via double underscore.
    e.g., APP_DATABASE__POOL_SIZE=10 -> {"database": {"pool_size": 10}}
    """
    overrides = {}
    prefix_with_sep = f"{prefix}_"

    for key, value in os.environ.items():
        if not key.startswith(prefix_with_sep):
            continue
        # Strip prefix and convert to config path
        config_key = key[len(prefix_with_sep):].lower()
        parts = config_key.split("__")

        # Build nested dict
        current = overrides
        for i, part in enumerate(parts[:-1]):
            if part not in current:
                current[part] = {}
            current = current[part]
        # Bug: doesn't validate type against schema before storing
        current[parts[-1]] = value  # Always stores as string!

    return overrides

def get_config(prefix="APP"):
    """Get full config: defaults + env overrides."""
    env_overrides = load_env_config(prefix)
    # Bug: shallow merge — nested dicts from env override entire sections
    config = {**DEFAULTS, **env_overrides}
    return config
''',
    "tasks/t3/test_config.py": '''\
import os
import sys

# Clean env before tests
for key in list(os.environ.keys()):
    if key.startswith("APP_"):
        del os.environ[key]

from base_config import deep_merge, validate_type, DEFAULTS

# Test deep_merge
merged = deep_merge(
    {"a": 1, "b": {"x": 10, "y": 20}},
    {"b": {"y": 99, "z": 30}, "c": 3}
)
assert merged == {"a": 1, "b": {"x": 10, "y": 99, "z": 30}, "c": 3}, f"Merge: {merged}"

# Test type validation
assert validate_type(42, int) == 42
assert validate_type("hello", str) == "hello"
assert validate_type("42", int) == 42
# Critical: bool coercion
assert validate_type("false", bool) == False, f"bool('false') should be False"
assert validate_type("true", bool) == True
assert validate_type("0", bool) == False
assert validate_type("1", bool) == True

# Test env config loading
os.environ["APP_PORT"] = "9090"
os.environ["APP_DEBUG"] = "true"
os.environ["APP_DATABASE__POOL_SIZE"] = "20"
os.environ["APP_DATABASE__TIMEOUT"] = "60"

from env_config import get_config
config = get_config()

# Top-level override
assert config["port"] == 9090 or config["port"] == "9090", f"Port: {config['port']}"
# Env vars should be type-coerced to match schema
assert isinstance(config["port"], int), f"Port should be int: {type(config['port'])}"
assert config["debug"] == True, f"Debug: {config['debug']}"
assert isinstance(config["debug"], bool), f"Debug should be bool: {type(config['debug'])}"

# Nested overrides should NOT destroy sibling keys
assert config["database"]["pool_size"] == 20 or config["database"]["pool_size"] == "20"
assert isinstance(config["database"]["pool_size"], int), f"pool_size type: {type(config['database']['pool_size'])}"
# This is the critical test: url should survive even though we only overrode pool_size and timeout
assert config["database"]["url"] == "sqlite:///default.db", \
    f"Nested merge destroyed url: {config.get('database', {})}"

# Logging section should be untouched
assert config["logging"]["level"] == "INFO"

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 4 (hard): Permission system with role inheritance
    # Bugs: cyclic role check, missing transitive permission, cache invalidation
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t4/permissions.py": '''\
"""Role-based permission system with inheritance."""

class PermissionSystem:
    def __init__(self):
        self.roles = {}          # role_name -> {"permissions": set, "parents": list}
        self.user_roles = {}     # user_id -> set of role names
        self._cache = {}         # (user_id, permission) -> bool

    def define_role(self, name, permissions=None, parents=None):
        """Define a role with direct permissions and parent roles."""
        self.roles[name] = {
            "permissions": set(permissions or []),
            "parents": list(parents or []),
        }
        self._cache.clear()  # Invalidate cache on role change

    def assign_role(self, user_id, role_name):
        """Assign role to user."""
        if role_name not in self.roles:
            raise KeyError(f"Role {role_name} not defined")
        if user_id not in self.user_roles:
            self.user_roles[user_id] = set()
        self.user_roles[user_id].add(role_name)
        # Bug: doesn't invalidate cache when user roles change
        # self._cache.clear()  # Missing!

    def revoke_role(self, user_id, role_name):
        """Remove role from user."""
        if user_id in self.user_roles:
            self.user_roles[user_id].discard(role_name)
            # Bug: doesn't invalidate cache

    def get_permissions(self, role_name, visited=None):
        """Get all permissions for a role, including inherited ones."""
        if visited is None:
            visited = set()
        if role_name in visited:
            return set()  # Cycle protection
        visited.add(role_name)

        role = self.roles.get(role_name)
        if not role:
            return set()

        perms = set(role["permissions"])
        for parent in role["parents"]:
            # Bug: should pass visited set to recursive call to detect cycles
            parent_perms = self.get_permissions(parent)  # Missing visited!
            perms.update(parent_perms)
        return perms

    def check(self, user_id, permission):
        """Check if user has permission (directly or via role inheritance)."""
        cache_key = (user_id, permission)
        if cache_key in self._cache:
            return self._cache[cache_key]

        user_roles = self.user_roles.get(user_id, set())
        result = False
        for role_name in user_roles:
            if permission in self.get_permissions(role_name):
                result = True
                break

        self._cache[cache_key] = result
        return result
''',
    "tasks/t4/test_permissions.py": '''\
from permissions import PermissionSystem

ps = PermissionSystem()

# Define role hierarchy: viewer < editor < admin
ps.define_role("viewer", permissions=["read"])
ps.define_role("editor", permissions=["write", "delete"], parents=["viewer"])
ps.define_role("admin", permissions=["manage_users", "configure"], parents=["editor"])

# Test direct permissions
assert "read" in ps.get_permissions("viewer")
assert "write" in ps.get_permissions("editor")

# Test inherited permissions (transitive)
editor_perms = ps.get_permissions("editor")
assert "read" in editor_perms, f"Editor missing inherited 'read': {editor_perms}"

admin_perms = ps.get_permissions("admin")
assert "read" in admin_perms, f"Admin missing transitive 'read': {admin_perms}"
assert "write" in admin_perms
assert "manage_users" in admin_perms

# Test user permission check
ps.assign_role("alice", "editor")
assert ps.check("alice", "read") == True
assert ps.check("alice", "write") == True
assert ps.check("alice", "manage_users") == False

# Test role assignment + cache invalidation
ps.assign_role("alice", "admin")
assert ps.check("alice", "manage_users") == True, "Cache not invalidated on assign"

# Test role revocation + cache invalidation
ps.revoke_role("alice", "admin")
assert ps.check("alice", "manage_users") == False, "Cache not invalidated on revoke"

# Test cycle protection: roles that inherit from each other
ps.define_role("role_a", permissions=["perm_a"], parents=["role_b"])
ps.define_role("role_b", permissions=["perm_b"], parents=["role_a"])
# Should not infinite loop
perms_a = ps.get_permissions("role_a")
assert "perm_a" in perms_a
assert "perm_b" in perms_a, f"Cycle broke inheritance: {perms_a}"

# No user, no permissions
assert ps.check("nonexistent", "read") == False

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 5 (hard): Pipeline processor with error recovery
    # 3-stage pipeline: validate -> transform -> output
    # Bugs: error recovery skips items, transform mutates shared state,
    #        output doesn't flush
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t5/pipeline.py": '''\
"""Data pipeline with stages: validate -> transform -> output."""

class ValidationError(Exception):
    pass

class PipelineError(Exception):
    def __init__(self, stage, item, original_error):
        self.stage = stage
        self.item = item
        self.original_error = original_error
        super().__init__(f"{stage}: {original_error}")

class Pipeline:
    def __init__(self, validators=None, transformers=None, on_error="skip"):
        """
        on_error: "skip" (skip bad items), "collect" (collect errors), "fail" (raise immediately)
        """
        self.validators = validators or []
        self.transformers = transformers or []
        self.on_error = on_error
        self.errors = []
        self.processed = []
        self._stats = {"input": 0, "validated": 0, "transformed": 0, "output": 0, "skipped": 0}

    def validate(self, item):
        """Run all validators. Return True if valid."""
        for v in self.validators:
            try:
                v(item)
            except Exception as e:
                error = PipelineError("validate", item, e)
                if self.on_error == "fail":
                    raise error
                self.errors.append(error)
                self._stats["skipped"] += 1
                return False
        self._stats["validated"] += 1
        return True

    def transform(self, item):
        """Apply all transformers sequentially."""
        result = item  # Bug: if item is a dict, this is a reference not a copy
        for t in self.transformers:
            try:
                result = t(result)
            except Exception as e:
                error = PipelineError("transform", item, e)
                if self.on_error == "fail":
                    raise error
                self.errors.append(error)
                self._stats["skipped"] += 1
                return None
        self._stats["transformed"] += 1
        return result

    def process(self, items):
        """Process all items through the pipeline."""
        self._stats["input"] = len(items)
        for item in items:
            if not self.validate(item):
                continue
            result = self.transform(item)
            if result is not None:
                self.processed.append(result)
                self._stats["output"] += 1
        return self.processed

    def stats(self):
        return dict(self._stats)
''',
    "tasks/t5/test_pipeline.py": '''\
from pipeline import Pipeline, PipelineError

# Basic pipeline
p = Pipeline(
    validators=[lambda x: None if isinstance(x, dict) else (_ for _ in ()).throw(ValueError("not a dict"))],
    transformers=[
        lambda x: {**x, "processed": True},
        lambda x: {**x, "name": x.get("name", "").upper()},
    ],
)

items = [
    {"name": "alice", "age": 30},
    {"name": "bob", "age": 25},
    "not a dict",  # Should be skipped
    {"name": "carol", "age": 35},
]

results = p.process(items)
assert len(results) == 3, f"Expected 3 results: {len(results)}"
assert results[0]["name"] == "ALICE"
assert results[0]["processed"] == True
assert len(p.errors) == 1  # "not a dict" error

# Stats
stats = p.stats()
assert stats["input"] == 4
assert stats["validated"] == 3
assert stats["skipped"] == 1
assert stats["output"] == 3

# CRITICAL: Transform must not mutate original items
original = {"name": "test", "value": 42}
original_copy = dict(original)
p2 = Pipeline(
    transformers=[lambda x: {**x, "extra": True}]
)
p2.process([original])
assert original == original_copy, f"Original mutated: {original} != {original_copy}"

# Error collection mode
p3 = Pipeline(
    validators=[lambda x: None],
    transformers=[lambda x: x["missing_key"]],  # Will KeyError
    on_error="collect",
)
p3.process([{"a": 1}, {"a": 2}])
assert len(p3.errors) == 2
assert p3._stats["skipped"] == 2

# Fail mode
p4 = Pipeline(
    validators=[lambda x: None],
    transformers=[lambda x: x["missing"]],
    on_error="fail",
)
try:
    p4.process([{"a": 1}])
    assert False, "Should raise PipelineError"
except PipelineError as e:
    assert e.stage == "transform"

# Multiple items - ensure no cross-contamination between items
p5 = Pipeline(
    transformers=[lambda x: {**x, "order": len(x)}]
)
items5 = [{"a": 1}, {"a": 1, "b": 2}, {"a": 1, "b": 2, "c": 3}]
results5 = p5.process(items5)
assert results5[0]["order"] == 1, f"Cross-contamination: {results5}"
assert results5[1]["order"] == 2
assert results5[2]["order"] == 3

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # Task 6 (very hard): Mini ORM with query builder + relationship loading
    # Multiple interacting bugs across 2 files
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t6/query_builder.py": '''\
"""Simple SQL query builder."""

class Query:
    def __init__(self, table):
        self.table = table
        self._select = ["*"]
        self._where = []
        self._order_by = []
        self._limit = None
        self._offset = None
        self._joins = []
        self._params = []

    def select(self, *columns):
        self._select = list(columns)
        return self

    def where(self, condition, *params):
        self._where.append(condition)
        self._params.extend(params)
        return self

    def order_by(self, column, desc=False):
        direction = "DESC" if desc else "ASC"
        self._order_by.append(f"{column} {direction}")
        return self

    def limit(self, n):
        self._limit = n
        return self

    def offset(self, n):
        self._offset = n
        return self

    def join(self, table, on):
        self._joins.append(f"JOIN {table} ON {on}")
        return self

    def build(self):
        """Build SQL string and params."""
        parts = [f"SELECT {', '.join(self._select)} FROM {self.table}"]

        for j in self._joins:
            parts.append(j)

        if self._where:
            parts.append(f"WHERE {' AND '.join(self._where)}")

        if self._order_by:
            parts.append(f"ORDER BY {', '.join(self._order_by)}")

        # Bug: LIMIT and OFFSET in wrong order (OFFSET should come after LIMIT in SQL)
        if self._offset is not None:
            parts.append(f"OFFSET {self._offset}")
        if self._limit is not None:
            parts.append(f"LIMIT {self._limit}")

        return ' '.join(parts), self._params

    def count(self):
        """Build COUNT query."""
        parts = [f"SELECT COUNT(*) FROM {self.table}"]
        for j in self._joins:
            parts.append(j)
        if self._where:
            parts.append(f"WHERE {' AND '.join(self._where)}")
        return ' '.join(parts), self._params
''',
    "tasks/t6/mini_orm.py": '''\
"""Mini ORM that uses QueryBuilder for data access."""
import sqlite3
from query_builder import Query

class Model:
    _table = None
    _db = None

    @classmethod
    def set_db(cls, db_path):
        cls._db = sqlite3.connect(db_path)
        cls._db.row_factory = sqlite3.Row

    @classmethod
    def query(cls):
        return Query(cls._table)

    @classmethod
    def find(cls, **kwargs):
        """Find records matching kwargs."""
        q = cls.query()
        for key, value in kwargs.items():
            q.where(f"{key} = ?", value)
        sql, params = q.build()
        cursor = cls._db.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def find_one(cls, **kwargs):
        results = cls.find(**kwargs)
        return results[0] if results else None

    @classmethod
    def create(cls, **kwargs):
        """Insert a new record."""
        columns = ', '.join(kwargs.keys())
        placeholders = ', '.join(['?'] * len(kwargs))
        sql = f"INSERT INTO {cls._table} ({columns}) VALUES ({placeholders})"
        cursor = cls._db.execute(sql, list(kwargs.values()))
        cls._db.commit()
        return cursor.lastrowid

    @classmethod
    def all(cls, order_by=None, limit=None, offset=None):
        """Get all records with optional ordering and pagination."""
        q = cls.query()
        if order_by:
            desc = order_by.startswith("-")
            col = order_by.lstrip("-")
            q.order_by(col, desc=desc)
        if limit:
            q.limit(limit)
        if offset:
            q.offset(offset)
        sql, params = q.build()
        cursor = cls._db.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


class User(Model):
    _table = "users"

class Post(Model):
    _table = "posts"

    @classmethod
    def for_user(cls, user_id):
        """Get all posts by a user."""
        return cls.find(user_id=user_id)
''',
    "tasks/t6/test_orm.py": '''\
import os, sqlite3
from mini_orm import User, Post, Model

# Setup test database
DB_PATH = "test.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
conn = sqlite3.connect(DB_PATH)
conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
conn.execute("CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, body TEXT)")
# Insert test data
for i, (name, email) in enumerate([
    ("Alice", "alice@test.com"),
    ("Bob", "bob@test.com"),
    ("Carol", "carol@test.com"),
], 1):
    conn.execute("INSERT INTO users VALUES (?, ?, ?)", (i, name, email))
for i, (uid, title) in enumerate([
    (1, "First Post"),
    (1, "Second Post"),
    (2, "Bob's Post"),
    (1, "Third Post"),
], 1):
    conn.execute("INSERT INTO posts VALUES (?, ?, ?, ?)", (i, uid, title, f"Body {i}"))
conn.commit()
conn.close()

# Connect ORM
Model.set_db(DB_PATH)

# Basic find
alice = User.find_one(name="Alice")
assert alice is not None
assert alice["email"] == "alice@test.com"

# Find multiple
all_users = User.find()
assert len(all_users) == 3

# Create
new_id = User.create(name="Dave", email="dave@test.com")
assert new_id == 4
dave = User.find_one(name="Dave")
assert dave["email"] == "dave@test.com"

# Relationship
alice_posts = Post.for_user(1)
assert len(alice_posts) == 3, f"Alice posts: {alice_posts}"

# Ordering
users_desc = User.all(order_by="-name")
assert users_desc[0]["name"] == "Dave", f"Order desc: {users_desc}"

# Pagination (LIMIT then OFFSET in SQL)
page1 = User.all(order_by="name", limit=2)
assert len(page1) == 2
assert page1[0]["name"] == "Alice"
assert page1[1]["name"] == "Bob"

page2 = User.all(order_by="name", limit=2, offset=2)
assert len(page2) == 2, f"Page 2 should have 2 results: {page2}"
assert page2[0]["name"] == "Carol", f"Page 2 first: {page2}"
assert page2[1]["name"] == "Dave"

# Query builder directly
q = User.query().select("name", "email").where("name LIKE ?", "%a%").order_by("name")
sql, params = q.build()
assert "SELECT name, email" in sql
assert "WHERE" in sql
assert "ORDER BY" in sql

# Count
count_sql, count_params = Post.query().where("user_id = ?", 1).count()
cursor = Model._db.execute(count_sql, count_params)
assert cursor.fetchone()[0] == 3

# Cleanup
os.remove(DB_PATH)
print("PASSED")
''',
}

experiment = Experiment(
    name="compute_allocation_v2",
    description=(
        "Inference-time compute allocation v2: plan-first vs act-first "
        "under TIGHT 8-turn budget. Multi-file bugs requiring cross-module "
        "understanding. Tests whether front-loading analysis or rapid "
        "iteration wins when turns are scarce."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="act-first (iterate fast, 8 turns) vs plan-first (read-analyze-act, 8 turns)",
    ),
    agent_a=AgentConfig(
        name="act_first",
        model="claude-haiku-4-5",
        system_prompt=ACT_FIRST_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    agent_b=AgentConfig(
        name="plan_first",
        model="claude-haiku-4-5",
        system_prompt=PLAN_FIRST_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    tasks=[
        TaskItem(
            prompt="Fix all bugs in tasks/t1/ (cart.py + price_engine.py). Run `cd tasks/t1 && python test_cart.py` to verify.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["multi-file", "rounding", "cart"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t2/ (task_queue.py). Run `cd tasks/t2 && python test_queue.py` to verify.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["priority-sort", "state-machine", "queue"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t3/ (base_config.py + env_config.py). Run `cd tasks/t3 && python test_config.py` to verify. There are bugs in type coercion (bool) and in how configs are merged.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["multi-file", "config", "deep-merge", "type-coercion"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t4/ (permissions.py). Run `cd tasks/t4 && python test_permissions.py` to verify. Issues with cache invalidation and cycle handling in role inheritance.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["cache", "recursion", "permissions"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t5/ (pipeline.py). Run `cd tasks/t5 && python test_pipeline.py` to verify. The pipeline has issues with mutable state and item isolation.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["mutation", "pipeline", "error-handling"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t6/ (query_builder.py + mini_orm.py). Run `cd tasks/t6 && python test_orm.py` to verify. There's a SQL generation bug in the query builder affecting pagination.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["multi-file", "sql", "orm", "pagination"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["compute-allocation", "inference-time", "plan-vs-act", "tight-budget", "research"],
)
