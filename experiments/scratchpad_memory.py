"""
Experiment: Scratchpad Working Memory — Does externalized state help?

No A/B test exists for coding agents with vs without a scratchpad file.
Hypothesis: on multi-step tasks requiring state tracking across tool calls,
a persistent scratch file prevents "forgetting" and improves coherence.

Agent A: No scratchpad — relies on context window
Agent B: Instructed to use _scratch.md for tracking plan, findings, state

Same model (haiku), deliberately complex multi-step tasks.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # A complex multi-file project where the agent needs to track state
    "project/app.py": '''\
"""Main application — imports and uses all modules."""
from project.auth import Authenticator
from project.cache import Cache
from project.logger import Logger

class App:
    def __init__(self):
        self.auth = Authenticator(secret="app-secret-key")
        self.cache = Cache(max_size=100)
        self.logger = Logger("app")
        self._request_count = 0

    def handle_request(self, method, path, headers=None, body=None):
        self._request_count += 1
        self.logger.info(f"{method} {path}")

        # Auth check
        token = (headers or {}).get("Authorization", "").replace("Bearer ", "")
        user = self.auth.validate_token(token) if token else None

        # Cache check for GET
        if method == "GET":
            cached = self.cache.get(path)
            if cached is not None:
                self.logger.debug(f"Cache hit: {path}")
                return {"status": 200, "body": cached, "cached": True}

        # Route
        if path == "/status":
            result = {"requests": self._request_count, "cache_size": self.cache.size()}
        elif path == "/protected" and user is None:
            return {"status": 401, "body": "Unauthorized"}
        elif path == "/protected":
            result = {"user": user, "message": "Welcome"}
        else:
            return {"status": 404, "body": "Not Found"}

        # Cache SET for successful GET responses
        if method == "GET":
            self.cache.set(path, result)

        return {"status": 200, "body": result}
''',

    "project/__init__.py": "",

    "project/auth.py": '''\
"""Authentication module."""
import hashlib
import time

class Authenticator:
    def __init__(self, secret="default"):
        self.secret = secret
        self.tokens = {}  # token -> {user, expires}

    def create_token(self, username, ttl=3600):
        raw = f"{username}:{time.time()}:{self.secret}"
        token = hashlib.sha256(raw.encode()).hexdigest()[:32]
        self.tokens[token] = {
            "user": username,
            "expires": time.time() + ttl,
        }
        return token

    def validate_token(self, token):
        entry = self.tokens.get(token)
        if entry is None:
            return None
        if time.time() > entry["expires"]:
            del self.tokens[token]
            return None
        return entry["user"]

    def revoke_token(self, token):
        self.tokens.pop(token, None)
''',

    "project/cache.py": '''\
"""In-memory cache with size limit and LRU eviction."""
from collections import OrderedDict

class Cache:
    def __init__(self, max_size=100):
        self.max_size = max_size
        self.store = OrderedDict()

    def get(self, key):
        if key in self.store:
            self.store.move_to_end(key)
            return self.store[key]
        return None

    def set(self, key, value):
        if key in self.store:
            self.store.move_to_end(key)
        self.store[key] = value
        if len(self.store) > self.max_size:
            self.store.popitem(last=False)

    def invalidate(self, key):
        self.store.pop(key, None)

    def clear(self):
        self.store.clear()

    def size(self):
        return len(self.store)
''',

    "project/logger.py": '''\
"""Simple logger."""
import datetime

class Logger:
    def __init__(self, name):
        self.name = name
        self.entries = []

    def _log(self, level, msg):
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "level": level,
            "logger": self.name,
            "message": msg,
        }
        self.entries.append(entry)

    def info(self, msg): self._log("INFO", msg)
    def debug(self, msg): self._log("DEBUG", msg)
    def error(self, msg): self._log("ERROR", msg)
    def warning(self, msg): self._log("WARNING", msg)

    def get_entries(self, level=None, limit=100):
        entries = self.entries
        if level:
            entries = [e for e in entries if e["level"] == level]
        return entries[-limit:]
''',

    "tests/__init__.py": "",
    "tests/test_integration.py": '''\
"""Integration tests for the full app."""
import sys, time
sys.path.insert(0, ".")
from project.app import App

def test_status_endpoint():
    app = App()
    r = app.handle_request("GET", "/status")
    assert r["status"] == 200
    assert r["body"]["requests"] == 1
    print("  test_status: OK")

def test_caching():
    app = App()
    r1 = app.handle_request("GET", "/status")
    r2 = app.handle_request("GET", "/status")
    assert r2.get("cached") == True, f"Second request should be cached: {r2}"
    print("  test_caching: OK")

def test_auth_flow():
    app = App()
    # Without token
    r1 = app.handle_request("GET", "/protected")
    assert r1["status"] == 401

    # With valid token
    token = app.auth.create_token("alice")
    r2 = app.handle_request("GET", "/protected", headers={"Authorization": f"Bearer {token}"})
    assert r2["status"] == 200
    assert r2["body"]["user"] == "alice"
    print("  test_auth: OK")

def test_404():
    app = App()
    r = app.handle_request("GET", "/nonexistent")
    assert r["status"] == 404
    print("  test_404: OK")

def test_logging():
    app = App()
    app.handle_request("GET", "/status")
    app.handle_request("GET", "/nonexistent")
    entries = app.logger.get_entries()
    assert len(entries) >= 2
    print("  test_logging: OK")

def test_cache_invalidation():
    """After POST, cached GET should be invalidated (if implemented)."""
    app = App()
    app.handle_request("GET", "/status")
    # TODO: POST to /status should invalidate cache
    # For now, just verify cache is working
    assert app.cache.size() >= 1
    app.cache.invalidate("/status")
    assert app.cache.get("/status") is None
    print("  test_cache_invalidation: OK")

if __name__ == "__main__":
    passed = failed = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                func()
                passed += 1
            except Exception as e:
                print(f"  {name}: FAIL — {e}")
                failed += 1
    print(f"\\nResults: {passed}/{passed+failed}")
    if failed == 0:
        print("ALL TESTS PASSED")
''',
}

MULTI_STEP_TASK = (
    "This project has several issues to investigate and fix. "
    "Do the following in order:\n\n"
    "1. Run tests/test_integration.py to see which tests pass and which fail\n"
    "2. Read all source files in project/ to understand the architecture\n"
    "3. Fix any failing tests by modifying the source code (not tests)\n"
    "4. Add a new feature: POST requests to any path should invalidate "
    "the cache for that path. Update handle_request() in app.py.\n"
    "5. Add a test for the new cache invalidation feature in test_integration.py\n"
    "6. Run all tests to verify everything passes\n"
    "7. Report: which modules you changed, what you fixed, and what you added"
)

experiment = Experiment(
    name="scratchpad_memory",
    description=(
        "Scratchpad working memory vs no scratchpad on multi-step project task. "
        "Same model (haiku). Tests whether externalized state helps coherence."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="No scratchpad vs explicit scratchpad for tracking state",
    ),
    agent_a=AgentConfig(
        name="no_scratchpad",
        model="claude-haiku-4-5",
        system_prompt=(
            "You are a senior developer working on a Python project. "
            "Complete all the tasks described in the prompt."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=25,
    ),
    agent_b=AgentConfig(
        name="with_scratchpad",
        model="claude-haiku-4-5",
        system_prompt=(
            "You are a senior developer working on a Python project.\n\n"
            "IMPORTANT: Use _scratch.md as your working memory. Before starting:\n"
            "1. Create _scratch.md\n"
            "2. Write your plan there\n"
            "3. As you investigate, update it with findings\n"
            "4. Track which files you've read and what you've learned\n"
            "5. Check off completed steps\n\n"
            "This scratchpad helps you stay organized across many tool calls."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=25,
    ),
    tasks=[
        TaskItem(
            prompt=MULTI_STEP_TASK,
            expected="ALL TESTS PASSED",
            check_fn='"pass" in output.lower()',
            difficulty="very_hard",
            tags=["multi-step", "investigation", "feature-add"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["scratchpad", "working-memory", "agent-optimization"],
)
