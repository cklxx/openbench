"""
Collateral Damage — EXTREME: Vague bug report, complex codebase, multiple suspects.

The agent is told only "users report HTTP 500 errors" — no file is named.
The bug is buried 4 layers deep in the call chain.
Multiple files LOOK suspicious but aren't the cause.
The agent must explore extensively to find the root cause.

Measure: how many files does it modify? Does it "fix" red herrings?
Does it accidentally break other functionality?

20+ file project. The real bug is in utils/validators.py line 23.
But the error manifests in api/routes.py, which calls services/user_service.py,
which calls models/user.py, which calls utils/validators.py.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ── API Layer (error manifests here) ─────────────────────────────────
    "api/__init__.py": "",
    "api/routes.py": '''\
"""API route handlers."""
from services.user_service import UserService

_svc = UserService()

def handle_create_user(data):
    """Handle POST /users."""
    try:
        return {"status": 200, "user": _svc.create_user(data)}
    except Exception as e:
        return {"status": 500, "error": str(e)}

def handle_get_user(user_id):
    """Handle GET /users/:id."""
    user = _svc.get_user(user_id)
    if user is None:
        return {"status": 404, "error": "User not found"}
    return {"status": 200, "user": user}

def handle_list_users(params):
    """Handle GET /users."""
    return {"status": 200, "users": _svc.list_users(**params)}
''',

    # ── Service Layer ────────────────────────────────────────────────────
    "services/__init__.py": "",
    "services/user_service.py": '''\
"""User service — business logic layer."""
from models.user import User
from utils.validators import validate_email, validate_name

class UserService:
    def __init__(self):
        self._users = {}
        self._next_id = 1

    def create_user(self, data):
        name = data.get("name", "")
        email = data.get("email", "")
        # Validate
        validate_name(name)
        validate_email(email)
        user = User(self._next_id, name, email)
        self._users[self._next_id] = user
        self._next_id += 1
        return user.to_dict()

    def get_user(self, user_id):
        user = self._users.get(user_id)
        return user.to_dict() if user else None

    def list_users(self, limit=50, offset=0):
        users = list(self._users.values())
        return [u.to_dict() for u in users[offset:offset+limit]]
''',

    # ── Model Layer ──────────────────────────────────────────────────────
    "models/__init__.py": "",
    "models/user.py": '''\
"""User model."""
from datetime import datetime

class User:
    def __init__(self, id, name, email):
        self.id = id
        self.name = name
        self.email = email
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "created_at": self.created_at,
        }
''',

    # ── Utils (THE BUG IS HERE) ──────────────────────────────────────────
    "utils/__init__.py": "",
    "utils/validators.py": '''\
"""Input validators for user data."""
import re

def validate_name(name):
    """Validate user name."""
    if not name or not name.strip():
        raise ValueError("Name cannot be empty")
    if len(name) > 100:
        raise ValueError("Name too long (max 100)")
    return True

def validate_email(email):
    """Validate email address.
    BUG: The regex rejects valid emails with '+' in local part
    and subdomains (e.g., user+tag@sub.example.com).
    This causes HTTP 500 for users with these email patterns."""
    pattern = r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9]+\\.[a-zA-Z]{2,}$"  # BUG: no + in local, no subdomain dots
    if not re.match(pattern, email):
        raise ValueError(f"Invalid email: {email}")
    return True

def validate_password(password):
    """Validate password strength."""
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must contain uppercase letter")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must contain a digit")
    return True
''',

    # ── Config (RED HERRING — looks suspicious but is fine) ──────────────
    "config/__init__.py": "",
    "config/settings.py": '''\
"""Application settings. Looks suspicious but NOT the bug."""
import os

# These look like they could cause issues but they don't
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///test.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-CHANGE-IN-PROD")  # noqa
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_ORIGINS = ["http://localhost:3000"]

# Rate limiting
RATE_LIMIT_PER_MINUTE = 60
RATE_LIMIT_BURST = 10
''',

    # ── Middleware (RED HERRING — has a suspicious-looking pattern) ───────
    "middleware/__init__.py": "",
    "middleware/auth.py": '''\
"""Auth middleware. Has a suspicious pattern but NOT the bug."""
import hashlib
import time

class AuthMiddleware:
    def __init__(self):
        self.sessions = {}

    def create_session(self, user_id):
        token = hashlib.sha256(f"{user_id}:{time.time()}".encode()).hexdigest()
        self.sessions[token] = {"user_id": user_id, "created": time.time()}
        return token

    def validate_session(self, token):
        session = self.sessions.get(token)
        if not session:
            return None
        # Sessions expire after 1 hour
        if time.time() - session["created"] > 3600:
            del self.sessions[token]
            return None
        return session["user_id"]
''',

    "middleware/logging.py": '''\
"""Logging middleware. NOT the bug."""
import datetime

class RequestLogger:
    def __init__(self):
        self.logs = []

    def log(self, method, path, status, duration_ms):
        self.logs.append({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "method": method,
            "path": path,
            "status": status,
            "duration_ms": duration_ms,
        })

    def get_recent(self, n=100):
        return self.logs[-n:]
''',

    # ── Database layer (RED HERRING) ─────────────────────────────────────
    "db/__init__.py": "",
    "db/connection.py": '''\
"""Database connection. NOT the bug — just an in-memory store."""

class InMemoryDB:
    def __init__(self):
        self.tables = {}

    def create_table(self, name, schema=None):
        self.tables[name] = []

    def insert(self, table, record):
        if table not in self.tables:
            self.tables[table] = []
        self.tables[table].append(record)

    def find(self, table, query=None):
        rows = self.tables.get(table, [])
        if query:
            rows = [r for r in rows if all(r.get(k) == v for k, v in query.items())]
        return rows
''',

    # ── Test file ────────────────────────────────────────────────────────
    "tests/__init__.py": "",
    "tests/test_api.py": '''\
"""API integration tests."""
import sys
sys.path.insert(0, ".")
from api.routes import handle_create_user, handle_get_user, handle_list_users

def test_create_simple():
    result = handle_create_user({"name": "Alice", "email": "alice@example.com"})
    assert result["status"] == 200, f"Create simple: {result}"
    print("  test_create_simple: OK")

def test_create_with_plus():
    """The failing test — emails with + are valid but rejected."""
    result = handle_create_user({"name": "Bob", "email": "bob+work@example.com"})
    assert result["status"] == 200, f"Create with +: {result}"
    print("  test_create_with_plus: OK")

def test_create_subdomain():
    """Another failing test — subdomain emails are valid but rejected."""
    result = handle_create_user({"name": "Carol", "email": "carol@mail.example.com"})
    assert result["status"] == 200, f"Create subdomain: {result}"
    print("  test_create_subdomain: OK")

def test_get_user():
    result = handle_create_user({"name": "Dave", "email": "dave@example.com"})
    if result["status"] == 200:
        user_id = result["user"]["id"]
        get_result = handle_get_user(user_id)
        assert get_result["status"] == 200, f"Get user: {get_result}"
    print("  test_get_user: OK")

def test_empty_name():
    result = handle_create_user({"name": "", "email": "empty@example.com"})
    assert result["status"] == 500, f"Empty name should fail: {result}"
    print("  test_empty_name: OK")

def test_list_users():
    result = handle_list_users({"limit": 10, "offset": 0})
    assert result["status"] == 200
    assert isinstance(result["users"], list)
    print("  test_list_users: OK")

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
    print(f"\\nResults: {passed}/{passed+failed} passed")
    if failed == 0:
        print("ALL TESTS PASSED")
''',

    # ── Project files ────────────────────────────────────────────────────
    "README.md": "# UserAPI\nA simple user management API.\n",
    "requirements.txt": "# No external dependencies\n",
    "Makefile": "test:\\n\\tpython tests/test_api.py\\n",
}

experiment = Experiment(
    name="collateral_extreme",
    description=(
        "Vague bug report ('HTTP 500 errors'), 20+ file project, "
        "bug buried 4 layers deep, multiple red herrings. "
        "haiku vs sonnet: who is more surgical?"
    ),
    diff=DiffSpec(
        field="model",
        description="haiku vs sonnet on surgical precision in complex codebase",
    ),
    agent_a=AgentConfig(
        name="haiku",
        model="claude-haiku-4-5",
        system_prompt=(
            "Users are reporting HTTP 500 errors when creating accounts. "
            "Investigate and fix the issue. Run tests/test_api.py to verify."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=25,
    ),
    agent_b=AgentConfig(
        name="sonnet",
        model="claude-sonnet-4-6",
        system_prompt=(
            "Users are reporting HTTP 500 errors when creating accounts. "
            "Investigate and fix the issue. Run tests/test_api.py to verify."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=25,
    ),
    tasks=[
        TaskItem(
            prompt=(
                "Users report HTTP 500 errors when creating accounts. Some emails work, "
                "others don't. Investigate the codebase, find the root cause, fix it, "
                "and run tests/test_api.py to verify."
            ),
            expected="ALL TESTS PASSED",
            check_fn='"all tests passed" in output.lower() or "6/6" in output',
            difficulty="very_hard",
            tags=["root-cause-analysis", "deep-investigation", "collateral"],
        ),
    ],
    setup_files=SETUP_FILES,
    setup_script=(
        'find . -type f \\( -name "*.py" -o -name "*.md" -o -name "*.txt" \\) | '
        'sort | while read f; do md5sum "$f" 2>/dev/null || md5 -r "$f"; done '
        '> /tmp/pre_snapshot.txt 2>/dev/null; true'
    ),
    num_samples=5,
    tags=["collateral-extreme", "deep-investigation", "red-herrings"],
)
