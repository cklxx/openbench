"""
Working Memory v2 — Forced Scratchpad in Multi-File Debugging

scratchpad_memory used SOFT prompts (no expected behavioral change).
This version uses EXTREME FORBIDDEN constraints to force real divergence.

Hypothesis: Explicit working memory (forced _notes.md file) improves correctness
on multi-file debugging tasks where information from file A is needed to fix file C.

Agent A (implicit): Standard debugging prompt — relies on context window
Agent B (scratchpad): MUST maintain _notes.md, FORBIDDEN from editing source
files without first writing observations to _notes.md

Same model (haiku), max_turns=12, num_samples=5.
DiffSpec: system_prompt only.

4 tasks, each 3 source files + 1 test file, 2 bugs per task.
Bugs require cross-file understanding to fix correctly.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ═══════════════ T1: Config Cascade ═══════════════
    # Bug 1: config.py POOL_SIZE=5 (should be 10)
    # Bug 2: client.py connect() doesn't return on success (retries even after accepted)
    # Cross-file: config.py value affects server.py pool behavior which affects client tests
    "tasks/t1/config.py": '''\
"""Application configuration."""
DATABASE_POOL_SIZE = 5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
''',
    "tasks/t1/server.py": '''\
"""Server — connection pool using config."""
from config import DATABASE_POOL_SIZE, REQUEST_TIMEOUT

class Server:
    def __init__(self):
        self.pool_size = DATABASE_POOL_SIZE
        self.timeout = REQUEST_TIMEOUT
        self.connections = []

    def accept_connection(self, client_id):
        if len(self.connections) >= self.pool_size:
            return {"status": "rejected", "reason": "pool_full"}
        self.connections.append({"id": client_id, "active": True})
        return {"status": "accepted", "id": client_id}

    def get_stats(self):
        return {
            "pool_size": self.pool_size,
            "active": len(self.connections),
            "available": self.pool_size - len(self.connections),
        }
''',
    "tasks/t1/client.py": '''\
"""Client — connects with retry logic."""
from config import MAX_RETRIES

class Client:
    def __init__(self, server):
        self.server = server
        self.max_retries = MAX_RETRIES
        self.log = []

    def connect(self, client_id):
        for attempt in range(self.max_retries):
            result = self.server.accept_connection(client_id)
            self.log.append({"attempt": attempt + 1, "result": result["status"]})
            # Bug: missing early return on success — retries even after accepted
        return result

    def get_log(self):
        return self.log
''',
    "tasks/t1/test_system.py": '''\
import sys; sys.path.insert(0, ".")
from server import Server
from client import Client

def test_pool_capacity():
    server = Server()
    accepted = sum(1 for i in range(10) if server.accept_connection(f"c{i}")["status"] == "accepted")
    assert accepted == 10, f"Expected 10 accepted, got {accepted} (pool_size={server.pool_size})"
    print("  pool_capacity: PASSED")

def test_pool_overflow():
    server = Server()
    for i in range(10):
        server.accept_connection(f"c{i}")
    assert server.accept_connection("overflow")["status"] == "rejected"
    print("  pool_overflow: PASSED")

def test_client_stops_on_success():
    """Client should stop retrying after first successful connection."""
    server = Server()
    client = Client(server)
    result = client.connect("user1")
    assert result["status"] == "accepted"
    assert len(client.get_log()) == 1, f"Should stop after 1 attempt, got {len(client.get_log())}"
    print("  client_stops_on_success: PASSED")

def test_client_retries_on_full():
    server = Server()
    for i in range(10):
        server.accept_connection(f"filler{i}")
    client = Client(server)
    result = client.connect("late")
    assert result["status"] == "rejected"
    assert len(client.get_log()) == 3
    print("  client_retries_on_full: PASSED")

def test_stats():
    server = Server()
    server.accept_connection("c1")
    server.accept_connection("c2")
    s = server.get_stats()
    assert s["pool_size"] == 10 and s["active"] == 2 and s["available"] == 8, f"Stats: {s}"
    print("  stats: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_pool_capacity", "test_pool_overflow",
                  "test_client_stops_on_success", "test_client_retries_on_full", "test_stats"]:
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

    # ═══════════════ T2: Data Pipeline ═══════════════
    # Bug 1: parser.py uses int() instead of float() for values
    # Bug 2: pipeline.py filter uses > instead of >= (excludes boundary values)
    # Cross-file: parser type error affects pipeline aggregation
    "tasks/t2/parser.py": '''\
"""Parse CSV-like input into records."""

def parse_records(text):
    records = []
    for line in text.strip().split("\\n"):
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) != 3:
            continue
        name = parts[0].strip()
        try:
            value = int(parts[1].strip())
        except ValueError:
            continue
        category = parts[2].strip()
        records.append({"name": name, "value": value, "category": category})
    return records
''',
    "tasks/t2/pipeline.py": '''\
"""Data pipeline: filter and summarize."""

def filter_records(records, min_value=0):
    return [r for r in records if r["value"] > min_value]

def summarize(records):
    result = {}
    for r in records:
        cat = r["category"]
        if cat not in result:
            result[cat] = {"total": 0, "count": 0}
        result[cat]["total"] += r["value"]
        result[cat]["count"] += 1
    for cat in result:
        result[cat]["average"] = result[cat]["total"] / result[cat]["count"]
    return result

def run_pipeline(text, min_value=0):
    from parser import parse_records
    records = parse_records(text)
    filtered = filter_records(records, min_value)
    return summarize(filtered)
''',
    "tasks/t2/formatter.py": '''\
"""Output formatting for pipeline results."""

def format_report(summary):
    lines = []
    for cat in sorted(summary):
        s = summary[cat]
        lines.append(f"{cat}: total={s['total']:.2f}, count={s['count']}, avg={s['average']:.2f}")
    return "\\n".join(lines)
''',
    "tasks/t2/test_pipeline.py": '''\
import sys; sys.path.insert(0, ".")
from parser import parse_records
from pipeline import filter_records, run_pipeline

DATA = """Alice,100,engineering
Bob,75.5,marketing
Carol,100,engineering
Dave,50,marketing
Eve,200.75,engineering
Frank,0,support"""

def test_parse_decimals():
    records = parse_records(DATA)
    bob = [r for r in records if r["name"] == "Bob"][0]
    assert bob["value"] == 75.5, f"Bob should be 75.5, got {bob['value']} (type: {type(bob['value']).__name__})"
    print("  parse_decimals: PASSED")

def test_filter_inclusive():
    records = parse_records(DATA)
    filtered = filter_records(records, min_value=0)
    names = [r["name"] for r in filtered]
    assert "Frank" in names, f"Frank (value=0) missing with min_value=0: {names}"
    print("  filter_inclusive: PASSED")

def test_pipeline_averages():
    result = run_pipeline(DATA, min_value=0)
    eng_avg = result["engineering"]["average"]
    expected = (100 + 100 + 200.75) / 3
    assert abs(eng_avg - expected) < 0.01, f"Eng avg: expected {expected:.2f}, got {eng_avg}"
    print("  pipeline_averages: PASSED")

def test_filter_boundary():
    records = parse_records(DATA)
    filtered = filter_records(records, min_value=50)
    names = sorted(r["name"] for r in filtered)
    assert "Dave" in names, f"Dave (value=50) should be included at min_value=50: {names}"
    print("  filter_boundary: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_parse_decimals", "test_filter_inclusive",
                  "test_pipeline_averages", "test_filter_boundary"]:
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

    # ═══════════════ T3: Event System ═══════════════
    # Bug 1: events.py defaults unknown types to CRITICAL (should be NORMAL)
    # Bug 2: dispatcher.py fallback triggers on >= HIGH (should be > HIGH, CRITICAL only)
    # Cross-file: events.py priority assignment affects dispatcher.py fallback behavior
    "tasks/t3/events.py": '''\
"""Event types and factory."""

CRITICAL = 3
HIGH = 2
NORMAL = 1
LOW = 0

class Event:
    def __init__(self, type, payload=None, priority=0):
        self.type = type
        self.payload = payload or {}
        self.priority = priority

def create_event(type, payload=None):
    priorities = {"error": CRITICAL, "warning": HIGH, "info": NORMAL, "debug": LOW}
    prio = priorities.get(type, CRITICAL)  # Bug: should default to NORMAL
    return Event(type, payload, prio)
''',
    "tasks/t3/dispatcher.py": '''\
"""Event dispatcher."""
from events import HIGH

class Dispatcher:
    def __init__(self):
        self.handlers = {}
        self.processed = []

    def register(self, event_type, handler):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)

    def dispatch(self, event):
        self.processed.append(event)
        handlers = self.handlers.get(event.type, [])
        if not handlers and event.priority >= HIGH:  # Bug: should be > HIGH (only CRITICAL)
            handlers = self.handlers.get("error", [])
        results = []
        for h in handlers:
            results.append(h(event))
        return results

    def stats(self):
        by_type = {}
        for e in self.processed:
            by_type[e.type] = by_type.get(e.type, 0) + 1
        return {"total": len(self.processed), "by_type": by_type}
''',
    "tasks/t3/handlers.py": '''\
"""Event handlers."""

def error_handler(event):
    return {"handled": True, "action": "alert", "type": event.type}

def info_handler(event):
    return {"handled": True, "action": "log", "type": event.type}
''',
    "tasks/t3/test_events.py": '''\
import sys; sys.path.insert(0, ".")
from events import create_event, CRITICAL, HIGH, NORMAL
from dispatcher import Dispatcher
from handlers import error_handler, info_handler

def test_known_priorities():
    assert create_event("error").priority == CRITICAL
    assert create_event("info").priority == NORMAL
    print("  known_priorities: PASSED")

def test_unknown_priority():
    e = create_event("custom_metric")
    assert e.priority == NORMAL, f"Unknown should be NORMAL ({NORMAL}), got {e.priority}"
    print("  unknown_priority: PASSED")

def test_dispatch_registered():
    d = Dispatcher()
    d.register("error", error_handler)
    results = d.dispatch(create_event("error"))
    assert len(results) == 1 and results[0]["action"] == "alert"
    print("  dispatch_registered: PASSED")

def test_fallback_critical_only():
    """Only CRITICAL (not HIGH) should fall back to error handler."""
    d = Dispatcher()
    d.register("error", error_handler)
    r = d.dispatch(create_event("warning"))
    assert len(r) == 0, f"HIGH should NOT fall back: {r}"
    print("  fallback_critical_only: PASSED")

def test_fallback_for_critical():
    d = Dispatcher()
    d.register("error", error_handler)
    from events import Event
    e = Event("system_crash", priority=CRITICAL)
    results = d.dispatch(e)
    assert len(results) == 1, f"CRITICAL should fall back: {results}"
    print("  fallback_for_critical: PASSED")

def test_no_fallback_low():
    d = Dispatcher()
    d.register("error", error_handler)
    r = d.dispatch(create_event("debug"))
    assert len(r) == 0
    print("  no_fallback_low: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_known_priorities", "test_unknown_priority",
                  "test_dispatch_registered", "test_fallback_critical_only",
                  "test_fallback_for_critical", "test_no_fallback_low"]:
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

    # ═══════════════ T4: Auth Roles ═══════════════
    # Bug 1: roles.py admin missing "read" permission
    # Bug 2: roles.py get_permissions returns mutable reference (no copy)
    # Cross-file: middleware relies on roles being immutable
    "tasks/t4/users.py": '''\
"""User store."""

class UserStore:
    def __init__(self):
        self.users = {}

    def create_user(self, username, role="viewer"):
        self.users[username] = {"username": username, "role": role}
        return self.users[username]

    def get_user(self, username):
        return self.users.get(username)
''',
    "tasks/t4/roles.py": '''\
"""Role-based permissions."""

ROLE_PERMISSIONS = {
    "viewer": ["read"],
    "editor": ["read", "write"],
    "admin": ["write", "delete", "manage_users"],
}

def get_permissions(role):
    return ROLE_PERMISSIONS.get(role, [])

def has_permission(role, permission):
    return permission in get_permissions(role)
''',
    "tasks/t4/middleware.py": '''\
"""Permission checking."""
from roles import has_permission

class AuthMiddleware:
    def __init__(self, user_store):
        self.user_store = user_store

    def check_access(self, username, required_permission):
        user = self.user_store.get_user(username)
        if user is None:
            return {"allowed": False, "reason": "user_not_found"}
        role = user["role"]
        if has_permission(role, required_permission):
            return {"allowed": True, "role": role}
        return {"allowed": False, "reason": f"role '{role}' lacks '{required_permission}'"}
''',
    "tasks/t4/test_auth.py": '''\
import sys; sys.path.insert(0, ".")
from users import UserStore
from roles import get_permissions, has_permission
from middleware import AuthMiddleware

def test_admin_has_read():
    perms = get_permissions("admin")
    assert "read" in perms, f"Admin should have read, got: {perms}"
    print("  admin_has_read: PASSED")

def test_admin_has_all():
    for perm in ["read", "write", "delete", "manage_users"]:
        assert has_permission("admin", perm), f"Admin missing '{perm}'"
    print("  admin_has_all: PASSED")

def test_permission_isolation():
    """Getting permissions should not allow modifying role definitions."""
    perms = get_permissions("viewer")
    perms.append("delete")
    assert "delete" not in get_permissions("viewer"), "Permissions leaked via mutation"
    print("  permission_isolation: PASSED")

def test_middleware_admin():
    store = UserStore()
    store.create_user("root", role="admin")
    mw = AuthMiddleware(store)
    for perm in ["read", "write", "delete"]:
        r = mw.check_access("root", perm)
        assert r["allowed"], f"Admin should have {perm}: {r}"
    print("  middleware_admin: PASSED")

def test_middleware_denied():
    store = UserStore()
    store.create_user("bob", role="viewer")
    mw = AuthMiddleware(store)
    assert not mw.check_access("bob", "write")["allowed"]
    print("  middleware_denied: PASSED")

def test_unknown_user():
    store = UserStore()
    mw = AuthMiddleware(store)
    r = mw.check_access("nobody", "read")
    assert not r["allowed"] and r["reason"] == "user_not_found"
    print("  unknown_user: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_admin_has_read", "test_admin_has_all", "test_permission_isolation",
                  "test_middleware_admin", "test_middleware_denied", "test_unknown_user"]:
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

IMPLICIT_PROMPT = """\
You are a senior developer debugging a Python project.

1. Run the test file to see failures
2. Read source files to understand the code
3. Fix the bugs
4. Run the tests again to verify

Print the final test output.
"""

FORCED_SCRATCHPAD_PROMPT = """\
You are a senior developer debugging a Python project.

STRICT RULES — follow these EXACTLY:

STEP 1: Create _notes.md in the task directory as your FIRST action.

STEP 2: Run the test file to see failures. Update _notes.md with:
  - Which tests failed and the error messages

STEP 3: Read each source file. After reading EACH file, update _notes.md with:
  - File name and what it does
  - Key variables, values, or formulas
  - Anything suspicious — potential bugs
  - How this file connects to other files you've read

STEP 4: Review _notes.md. Write a "DIAGNOSIS" section listing all bugs
you've identified and which file each is in.

STEP 5: Fix all bugs based on your diagnosis.

STEP 6: Run the test to verify. Print the output.

CRITICAL CONSTRAINTS:
- You are FORBIDDEN from using Edit on any .py source file unless
  _notes.md exists AND has been updated within your last 2 tool calls
- After reading each source file, you MUST update _notes.md BEFORE
  reading the next file or making any edit
- Your notes prevent forgetting what you learned in earlier files
- Every fact you discover must be written down, not held in your head
"""

experiment = Experiment(
    name="working_memory_v2",
    description=(
        "Forced scratchpad vs implicit memory in multi-file debugging. "
        "Extreme FORBIDDEN constraints. 4 tasks × 5 samples. "
        "Tests whether externalized notes help track cross-file dependencies."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Implicit context-window memory vs forced scratchpad notes",
    ),
    agent_a=AgentConfig(
        name="implicit_memory",
        model="claude-haiku-4-5",
        system_prompt=IMPLICIT_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=12,
    ),
    agent_b=AgentConfig(
        name="forced_scratchpad",
        model="claude-haiku-4-5",
        system_prompt=FORCED_SCRATCHPAD_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=12,
    ),
    tasks=[
        TaskItem(
            prompt=(
                "Fix all bugs in tasks/t1/. Test: cd tasks/t1 && python test_system.py\n"
                "Print the test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["config-cascade", "cross-file"],
        ),
        TaskItem(
            prompt=(
                "Fix all bugs in tasks/t2/. Test: cd tasks/t2 && python test_pipeline.py\n"
                "Print the test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["data-pipeline", "type-error"],
        ),
        TaskItem(
            prompt=(
                "Fix all bugs in tasks/t3/. Test: cd tasks/t3 && python test_events.py\n"
                "Print the test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["event-system", "cross-file-dependency"],
        ),
        TaskItem(
            prompt=(
                "Fix all bugs in tasks/t4/. Test: cd tasks/t4 && python test_auth.py\n"
                "Print the test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["auth-roles", "mutation"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["working-memory", "scratchpad", "multi-file-debugging"],
)
