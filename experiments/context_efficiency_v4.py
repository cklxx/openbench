"""
Context Efficiency v4 — Properly Calibrated

Previous versions failed at calibration:
- v1/v3: tasks too hard (0% both sides)
- v2: most tasks too easy (80% baseline), only 6-file task hit sweet spot (40%)

v4 design principles:
1. ALL tasks use 5-8 file projects — exploration is genuinely expensive
2. Bugs are in UNEXPECTED files — error traceback MISLEADS to wrong file
   This is key: if the traceback points to the right file, guidance is useless
   because the agent can just follow the traceback.
3. max_turns=8 — proven sweet spot from v2
4. 4 tasks × n=8 — better statistical power
5. Guided agent gets EXACT root cause file+description
   (simulates perfect trajectory compression that preserves causal info)

Target: unguided 40-60% baseline, guided 70-80%
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

UNGUIDED_PROMPT = """\
You are a developer fixing bugs in a multi-file project.
Run the test, read the error, find and fix the root cause.
You have limited turns — be efficient.
"""

GUIDED_PROMPT = """\
You are a developer fixing bugs. You have insider knowledge of where bugs are:

TASK T1 (web app): The test fails in routes.py with a wrong response,
but the REAL bug is in middleware.py — the auth middleware modifies the
request object incorrectly before the route handler sees it. Also
utils.py has a URL encoding bug that affects path matching.

TASK T2 (data pipeline): The test fails with wrong aggregation results.
The REAL bug is in transforms.py — the groupby function mutates shared
state between groups. Also loader.py silently drops rows with empty
fields instead of treating them as valid empty strings.

TASK T3 (notification system): The test fails saying notifications weren't
sent. The REAL bug is in scheduler.py — the cron expression parser treats
"*/5" (every 5 min) as "at minute 5 only". Also filters.py has an
off-by-one in the rate limit window calculation.

TASK T4 (build system): The test fails with wrong dependency order.
The REAL bug is in resolver.py — the cycle detection marks nodes as
"visited" too early, before all their children are processed. Also
config_parser.py doesn't handle comments inside quoted strings.

Use this knowledge to go DIRECTLY to the root cause files.
Do NOT waste turns reading files that aren't buggy.
"""

SETUP_FILES = {
    # ══════════════════════════════════════════════════════════════════════
    # TASK 1: Web app — error in routes.py but root cause in middleware.py
    # 6 files. The traceback shows routes.py returning wrong data,
    # but the bug is middleware.py corrupting the request + utils.py URL bug
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t1/app.py": '''\
"""Web application setup."""
from routes import handle_request
from middleware import apply_middleware

class App:
    def __init__(self):
        self.middlewares = []
        self.routes = {}

    def use(self, mw):
        self.middlewares.append(mw)

    def route(self, path, handler):
        self.routes[path] = handler

    def handle(self, request):
        # Apply middleware chain
        for mw in self.middlewares:
            request = apply_middleware(mw, request)
            if request is None:
                return {"status": 403, "body": "Forbidden"}
        # Find route
        handler = self.routes.get(request.get("path"))
        if not handler:
            return {"status": 404, "body": "Not Found"}
        return handler(request)
''',
    "tasks/t1/middleware.py": '''\
"""Request middleware."""

def auth_middleware(request):
    """Check auth token and add user info."""
    token = request.get("headers", {}).get("Authorization", "")
    if token.startswith("Bearer "):
        user = token[7:]  # Extract user from token
        request["user"] = user
        # Bug: overwrites the entire headers dict instead of just adding to it
        request["headers"] = {"X-User": user}
        return request
    return None  # Reject unauthenticated

def logging_middleware(request):
    """Log request (no-op in test)."""
    request["logged"] = True
    return request

def apply_middleware(mw, request):
    return mw(request)
''',
    "tasks/t1/routes.py": '''\
"""Route handlers."""
from utils import normalize_path, format_response

def user_profile(request):
    """Return user profile."""
    user = request.get("user", "anonymous")
    return format_response(200, {"name": user, "role": "member"})

def user_settings(request):
    """Return user settings."""
    user = request.get("user", "anonymous")
    # Uses a header that middleware might have removed
    content_type = request.get("headers", {}).get("Accept", "application/json")
    return format_response(200, {"user": user, "format": content_type})

def search(request):
    """Search endpoint — uses query params from path."""
    path = request.get("path", "")
    query = normalize_path(path)
    return format_response(200, {"query": query, "results": []})
''',
    "tasks/t1/utils.py": '''\
"""Utility functions."""

def normalize_path(path):
    """Normalize URL path — decode %20 etc."""
    # Bug: doesn't actually decode, just strips slashes
    return path.strip("/")

def format_response(status, body):
    return {"status": status, "body": body}

def parse_query_string(qs):
    """Parse 'key=val&key2=val2' into dict."""
    if not qs:
        return {}
    params = {}
    for pair in qs.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k] = v
    return params
''',
    "tasks/t1/config.py": '''\
"""App configuration — no bugs here."""
DEFAULT_CONFIG = {
    "host": "0.0.0.0",
    "port": 8080,
    "debug": False,
    "max_body_size": 1024 * 1024,
}

def get_config(overrides=None):
    config = dict(DEFAULT_CONFIG)
    if overrides:
        config.update(overrides)
    return config
''',
    "tasks/t1/test_app.py": '''\
from app import App
from middleware import auth_middleware, logging_middleware

app = App()
app.use(logging_middleware)
app.use(auth_middleware)

from routes import user_profile, user_settings, search
app.route("/profile", user_profile)
app.route("/settings", user_settings)
app.route("/search", search)

# Test 1: Profile endpoint
resp = app.handle({
    "path": "/profile",
    "headers": {"Authorization": "Bearer alice", "Accept": "text/html"},
})
assert resp["status"] == 200, f"Profile status: {resp}"
assert resp["body"]["name"] == "alice", f"Profile body: {resp['body']}"

# Test 2: Settings should preserve Accept header
resp2 = app.handle({
    "path": "/settings",
    "headers": {"Authorization": "Bearer bob", "Accept": "text/html"},
})
assert resp2["status"] == 200
# The Accept header should survive middleware
assert resp2["body"]["format"] == "text/html", \\
    f"Accept header lost: {resp2['body']['format']} (middleware overwrote headers?)"

# Test 3: URL with encoded spaces
resp3 = app.handle({
    "path": "/search",
    "headers": {"Authorization": "Bearer carol"},
    "query": "hello%20world",
})
assert resp3["status"] == 200

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # TASK 2: Data pipeline — error in aggregator but root cause in transforms
    # 5 files. Test shows wrong aggregation, but bug is in transforms.py
    # mutating shared state + loader.py dropping valid rows
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t2/loader.py": '''\
"""Data loader — reads CSV-like data."""

def load_records(text):
    """Parse text data into list of dicts."""
    lines = text.strip().split("\\n")
    if not lines:
        return []
    headers = [h.strip() for h in lines[0].split(",")]
    records = []
    for line in lines[1:]:
        values = [v.strip() for v in line.split(",")]
        # Bug: skips rows where any field is empty — should keep them
        if not all(values):
            continue
        record = dict(zip(headers, values))
        records.append(record)
    return records
''',
    "tasks/t2/transforms.py": '''\
"""Data transformations."""

def groupby(records, key):
    """Group records by a key field. Returns dict of key_value -> [records]."""
    groups = {}
    for record in records:
        k = record.get(key, "")
        if k not in groups:
            groups[k] = []
        groups[k].append(record)
    return groups

def aggregate(groups, field, func="sum"):
    """Aggregate a numeric field within each group."""
    result = {}
    for key, records in groups.items():
        values = []
        for r in records:
            val = r.get(field, "0")
            try:
                # Bug: modifies the original record dict!
                r[field] = float(val)
                values.append(r[field])
            except (ValueError, TypeError):
                continue
        if func == "sum":
            result[key] = sum(values)
        elif func == "avg":
            result[key] = sum(values) / len(values) if values else 0
        elif func == "count":
            result[key] = len(values)
    return result
''',
    "tasks/t2/aggregator.py": '''\
"""High-level aggregation pipeline."""
from loader import load_records
from transforms import groupby, aggregate

def summarize(data_text, group_key, agg_field, agg_func="sum"):
    """Load data, group it, and aggregate."""
    records = load_records(data_text)
    groups = groupby(records, group_key)
    return aggregate(groups, agg_field, agg_func)
''',
    "tasks/t2/formatter.py": '''\
"""Output formatting — no bugs here."""

def format_summary(summary, title="Summary"):
    lines = [title, "=" * len(title)]
    for key, value in sorted(summary.items()):
        if isinstance(value, float):
            lines.append(f"  {key}: {value:.2f}")
        else:
            lines.append(f"  {key}: {value}")
    return "\\n".join(lines)
''',
    "tasks/t2/test_pipeline.py": '''\
from aggregator import summarize
from loader import load_records

DATA = """department,name,salary
Engineering,Alice,90000
Engineering,Bob,85000
Marketing,Carol,70000
Marketing,,65000
Engineering,Eve,95000"""

# Test 1: Row with empty name should still be counted
records = load_records(DATA)
assert len(records) == 5, f"Should have 5 records (empty name is valid): got {len(records)}"

# Test 2: Sum salaries by department
result = summarize(DATA, "department", "salary", "sum")
assert result.get("Engineering") == 270000, f"Eng sum: {result.get('Engineering')}"
assert result.get("Marketing") == 135000, f"Mkt sum: {result.get('Marketing')}"

# Test 3: Running summarize twice should give same results (no mutation)
result2 = summarize(DATA, "department", "salary", "sum")
assert result2 == result, f"Second run differs: {result2} != {result}"

# Test 4: Average
avg_result = summarize(DATA, "department", "salary", "avg")
assert avg_result.get("Engineering") == 90000, f"Eng avg: {avg_result.get('Engineering')}"

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # TASK 3: Notification system — error says "not sent" but root cause
    # is in scheduler's cron parsing + filter's rate limit window
    # 6 files.
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t3/notification.py": '''\
"""Notification types and sending."""

class Notification:
    def __init__(self, user, message, channel="email"):
        self.user = user
        self.message = message
        self.channel = channel
        self.sent = False

    def send(self):
        self.sent = True
        return True
''',
    "tasks/t3/scheduler.py": '''\
"""Schedule-based notification triggering."""

def parse_cron(expr):
    """Parse simple cron-like expression.
    Supports: number, */N (every N), * (every)
    Returns a function that checks if a given minute matches.
    """
    if expr == "*":
        return lambda minute: True
    if expr.startswith("*/"):
        # Bug: "*/5" should match 0,5,10,15... but this checks == instead of %
        interval = int(expr[2:])
        return lambda minute: minute == interval
    try:
        n = int(expr)
        return lambda minute: minute == n
    except ValueError:
        return lambda minute: False

class ScheduledTask:
    def __init__(self, name, cron_expr, action):
        self.name = name
        self.matcher = parse_cron(cron_expr)
        self.action = action

    def should_run(self, minute):
        return self.matcher(minute)

    def run(self, minute):
        if self.should_run(minute):
            return self.action()
        return None
''',
    "tasks/t3/filters.py": '''\
"""Notification filtering — rate limits, preferences."""

class RateLimiter:
    def __init__(self, max_per_window, window_minutes=60):
        self.max = max_per_window
        self.window = window_minutes
        self.history = {}  # user -> [timestamps]

    def allow(self, user, current_minute):
        if user not in self.history:
            self.history[user] = []
        # Clean old entries
        # Bug: off-by-one — uses > instead of >= for window boundary
        cutoff = current_minute - self.window
        self.history[user] = [t for t in self.history[user] if t > cutoff]
        if len(self.history[user]) >= self.max:
            return False
        self.history[user].append(current_minute)
        return True

class PreferenceFilter:
    def __init__(self, preferences=None):
        self.prefs = preferences or {}

    def allows(self, user, channel):
        user_prefs = self.prefs.get(user, {})
        return user_prefs.get(channel, True)  # Default: allow
''',
    "tasks/t3/dispatcher.py": '''\
"""Dispatch notifications through filters."""
from filters import RateLimiter, PreferenceFilter

class Dispatcher:
    def __init__(self, rate_limit=5, window=60, preferences=None):
        self.limiter = RateLimiter(rate_limit, window)
        self.pref_filter = PreferenceFilter(preferences)
        self.sent = []
        self.blocked = []

    def dispatch(self, notification, current_minute=0):
        if not self.pref_filter.allows(notification.user, notification.channel):
            self.blocked.append(("preference", notification))
            return False
        if not self.limiter.allow(notification.user, current_minute):
            self.blocked.append(("rate_limit", notification))
            return False
        notification.send()
        self.sent.append(notification)
        return True
''',
    "tasks/t3/engine.py": '''\
"""Notification engine — ties scheduler + dispatcher together."""
from scheduler import ScheduledTask
from dispatcher import Dispatcher
from notification import Notification

class NotificationEngine:
    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        self.tasks = []

    def add_scheduled(self, name, cron_expr, user, message, channel="email"):
        def action():
            n = Notification(user, message, channel)
            return self.dispatcher.dispatch(n)
        self.tasks.append(ScheduledTask(name, cron_expr, action))

    def tick(self, minute):
        """Process one minute tick."""
        results = []
        for task in self.tasks:
            result = task.run(minute)
            if result is not None:
                results.append((task.name, result))
        return results
''',
    "tasks/t3/test_notifications.py": '''\
from engine import NotificationEngine
from dispatcher import Dispatcher
from scheduler import parse_cron

# Test cron parsing
every5 = parse_cron("*/5")
assert every5(0) == True, "*/5 should match minute 0"
assert every5(5) == True, "*/5 should match minute 5"
assert every5(10) == True, "*/5 should match minute 10"
assert every5(3) == False, "*/5 should not match minute 3"

at_15 = parse_cron("15")
assert at_15(15) == True
assert at_15(16) == False

# Test notification engine with scheduled tasks
dispatcher = Dispatcher(rate_limit=3, window=60)
engine = NotificationEngine(dispatcher)
engine.add_scheduled("health_check", "*/10", "ops-team", "System OK")

# Run for 30 minutes — should fire at 0, 10, 20
for minute in range(30):
    engine.tick(minute)

assert len(dispatcher.sent) == 3, \\
    f"Should send 3 notifications (at min 0,10,20): got {len(dispatcher.sent)}"

# Test rate limiting
dispatcher2 = Dispatcher(rate_limit=2, window=10)
engine2 = NotificationEngine(dispatcher2)
engine2.add_scheduled("alert", "*/1", "admin", "Alert!")

# Run for 5 minutes — every minute, but rate limited to 2 per 10min window
for minute in range(5):
    engine2.tick(minute)

assert len(dispatcher2.sent) == 2, \\
    f"Rate limit should cap at 2: got {len(dispatcher2.sent)}"
assert len(dispatcher2.blocked) == 3, \\
    f"Should block 3: got {len(dispatcher2.blocked)}"

print("PASSED")
''',

    # ══════════════════════════════════════════════════════════════════════
    # TASK 4: Build system — error in builder but root cause in resolver
    # 5 files. Traceback shows wrong build order, but cycle detection is buggy
    # + config parser doesn't handle edge case
    # ══════════════════════════════════════════════════════════════════════
    "tasks/t4/config_parser.py": '''\
"""Build configuration parser."""

def parse_config(text):
    """Parse build config file.
    Format:
      [target_name]
      deps = dep1, dep2
      command = build_command
      # comment lines
    """
    targets = {}
    current = None
    for line in text.strip().split("\\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            targets[current] = {"deps": [], "command": ""}
            continue
        if current and "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key == "deps":
                # Bug: doesn't handle empty deps (splits "" into [""])
                deps = [d.strip() for d in value.split(",")]
                targets[current]["deps"] = deps
            elif key == "command":
                targets[current]["command"] = value
    return targets
''',
    "tasks/t4/resolver.py": '''\
"""Dependency resolver with topological sort."""

def resolve_order(targets):
    """Return build order respecting dependencies.
    Raises ValueError on circular dependencies.
    """
    order = []
    state = {}  # name -> "unvisited", "visiting", "visited"

    for name in targets:
        state[name] = "unvisited"

    def visit(name):
        if name not in state:
            return  # External dependency, skip
        if state[name] == "visited":
            return
        if state[name] == "visiting":
            raise ValueError(f"Circular dependency involving {name}")

        state[name] = "visiting"
        for dep in targets[name]["deps"]:
            visit(dep)
        # Bug: sets to "visited" but doesn't add to order here
        # Instead adds to order first, THEN marks visited
        # This means if A depends on B and C, and B also depends on C,
        # C might appear twice in the order
        order.append(name)
        state[name] = "visited"

    for name in targets:
        visit(name)

    return order
''',
    "tasks/t4/builder.py": '''\
"""Build executor."""
from resolver import resolve_order

class Builder:
    def __init__(self, targets):
        self.targets = targets
        self.built = []
        self.log = []

    def build_all(self):
        try:
            order = resolve_order(self.targets)
        except ValueError as e:
            return False, str(e)

        for name in order:
            if name not in self.targets:
                continue  # Skip external deps
            cmd = self.targets[name].get("command", "")
            self.log.append(f"Building {name}: {cmd}")
            self.built.append(name)

        return True, self.built

    def build_target(self, name):
        if name not in self.targets:
            return False, f"Unknown target: {name}"
        # Build deps first
        for dep in self.targets[name]["deps"]:
            if dep in self.targets and dep not in self.built:
                self.build_target(dep)
        self.built.append(name)
        return True, name
''',
    "tasks/t4/cache.py": '''\
"""Build cache — no bugs here."""

class BuildCache:
    def __init__(self):
        self._cache = {}

    def is_cached(self, target, deps_hash):
        return self._cache.get(target) == deps_hash

    def update(self, target, deps_hash):
        self._cache[target] = deps_hash

    def invalidate(self, target):
        self._cache.pop(target, None)

    def clear(self):
        self._cache.clear()
''',
    "tasks/t4/test_build.py": '''\
from config_parser import parse_config
from builder import Builder
from resolver import resolve_order

# Test config parsing
config_text = """
[app]
deps = lib, utils
command = gcc -o app main.c

[lib]
deps =
command = gcc -c lib.c

[utils]
deps = lib
command = gcc -c utils.c
"""

targets = parse_config(config_text)
assert "app" in targets
assert "lib" in targets
assert "utils" in targets
# lib has no deps — should be empty list, not [""]
assert targets["lib"]["deps"] == [] or targets["lib"]["deps"] == [""], \\
    f"Lib deps: {targets['lib']['deps']}"
assert targets["lib"]["deps"] == [], \\
    f"Empty deps should be [] not ['']: {targets['lib']['deps']}"

# Test dependency resolution
order = resolve_order(targets)
assert order.index("lib") < order.index("utils"), f"lib before utils: {order}"
assert order.index("utils") < order.index("app"), f"utils before app: {order}"
# No duplicates
assert len(order) == len(set(order)), f"Duplicates in order: {order}"

# Test builder
builder = Builder(targets)
ok, built = builder.build_all()
assert ok, f"Build failed: {built}"
assert len(built) == 3, f"Should build 3 targets: {built}"
assert built.index("lib") < built.index("app"), f"Wrong order: {built}"

# Test circular dependency detection
circular = {
    "a": {"deps": ["b"], "command": ""},
    "b": {"deps": ["c"], "command": ""},
    "c": {"deps": ["a"], "command": ""},
}
try:
    resolve_order(circular)
    assert False, "Should detect circular dependency"
except ValueError:
    pass

print("PASSED")
''',
}

experiment = Experiment(
    name="context_efficiency_v4",
    description=(
        "Context efficiency v4: properly calibrated. All tasks use 5-6 file "
        "projects where error tracebacks MISLEAD to wrong files. "
        "Guided agent gets exact root cause locations. Tests whether "
        "navigation guidance helps when exploration is genuinely expensive."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="unguided (no codebase info) vs guided (exact root cause file+description per task)",
    ),
    agent_a=AgentConfig(
        name="unguided",
        model="claude-haiku-4-5",
        system_prompt=UNGUIDED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    agent_b=AgentConfig(
        name="guided",
        model="claude-haiku-4-5",
        system_prompt=GUIDED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=8,
    ),
    tasks=[
        TaskItem(
            prompt="Fix bugs in tasks/t1/ (web app, 6 files). Run `cd tasks/t1 && python test_app.py`. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["6-file", "misleading-traceback", "middleware"],
        ),
        TaskItem(
            prompt="Fix bugs in tasks/t2/ (data pipeline, 5 files). Run `cd tasks/t2 && python test_pipeline.py`. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["5-file", "mutation-bug", "data"],
        ),
        TaskItem(
            prompt="Fix bugs in tasks/t3/ (notification system, 6 files). Run `cd tasks/t3 && python test_notifications.py`. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["6-file", "cron-parsing", "rate-limit"],
        ),
        TaskItem(
            prompt="Fix bugs in tasks/t4/ (build system, 5 files). Run `cd tasks/t4 && python test_build.py`. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["5-file", "topo-sort", "parser"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=8,
    tags=["context-efficiency", "misleading-errors", "calibrated", "research"],
)
