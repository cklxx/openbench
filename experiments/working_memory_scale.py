"""
Working Memory Scale Test — 8 Files, 3 Bugs

v2/v3 found scratchpad is harmful on 3-file tasks (overhead > benefit).
Hypothesis: at larger scale (8+ files), scratchpad becomes valuable because
tracking cross-file dependencies exceeds what the model can hold implicitly.

Design: A coherent web app with 8 source files + 1 test file.
3 bugs scattered across different files, each requiring knowledge of 2+ files.
max_turns=25, num_samples=5.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    "app/config.py": '''\
"""Application configuration."""

DATABASE_URL = "sqlite:///app.db"
MAX_CACHE_SIZE = 5  # Bug: should be 50 — tests expect cache to hold 20+ items
SECRET_KEY = "dev-secret-key"
SESSION_TIMEOUT = 3600
DEBUG = True
DEFAULT_PAGE_SIZE = 10
''',

    "app/models.py": '''\
"""Data models."""

class User:
    def __init__(self, username, email, role="viewer"):
        self.username = username
        self.email = email
        self.role = role
        self.active = True

    def to_dict(self):
        return {
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "active": self.active,
        }

class Product:
    def __init__(self, name, price, category, stock=0):
        self.name = name
        self.price = price
        self.category = category
        self.stock = stock

    def to_dict(self):
        return {
            "name": self.name,
            "price": self.price,
            "category": self.category,
            "stock": self.stock,
        }
''',

    "app/validators.py": '''\
"""Input validation."""
import re

def validate_email(email):
    """Validate email format. Returns (is_valid, error_message)."""
    if not email or not isinstance(email, str):
        return False, "Email is required"
    # Bug: regex doesn't allow + in local part (alice+tag@example.com should be valid)
    pattern = r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
    if re.match(pattern, email):
        return True, None
    return False, f"Invalid email format: {email}"

def validate_price(price):
    """Validate price is a positive number."""
    if not isinstance(price, (int, float)):
        return False, "Price must be a number"
    if price < 0:
        return False, "Price must be non-negative"
    return True, None

def validate_username(username):
    """Validate username: 3-20 chars, alphanumeric + underscore."""
    if not username or len(username) < 3:
        return False, "Username must be at least 3 characters"
    if len(username) > 20:
        return False, "Username must be at most 20 characters"
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return False, "Username must be alphanumeric with underscores"
    return True, None
''',

    "app/cache.py": '''\
"""Simple in-memory cache with LRU eviction."""
from collections import OrderedDict

class Cache:
    def __init__(self, max_size):
        self.max_size = max_size
        self.store = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        if key in self.store:
            self.hits += 1
            self.store.move_to_end(key)
            return self.store[key]
        self.misses += 1
        return None

    def set(self, key, value):
        if key in self.store:
            self.store.move_to_end(key)
        self.store[key] = value
        while len(self.store) > self.max_size:
            self.store.popitem(last=False)

    def invalidate(self, key):
        self.store.pop(key, None)

    def clear(self):
        self.store.clear()
        self.hits = 0
        self.misses = 0

    def stats(self):
        total = self.hits + self.misses
        return {
            "size": len(self.store),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 2) if total > 0 else 0,
        }
''',

    "app/auth.py": '''\
"""Authentication module."""
import hashlib

class AuthService:
    def __init__(self, secret_key):
        self.secret_key = secret_key
        self.credentials = {}  # username -> password_hash
        self.sessions = {}

    def hash_password(self, password):
        return hashlib.sha256((password + self.secret_key).encode()).hexdigest()

    def register(self, username, password):
        """Store hashed password for user."""
        # Bug: lowercases password before hashing — makes passwords case-insensitive
        self.credentials[username] = self.hash_password(password.lower())

    def authenticate(self, username, password):
        """Check if password matches. Returns (success, error)."""
        stored = self.credentials.get(username)
        if not stored:
            return False, "No credentials"
        # Also lowercases — consistent with register but wrong (case-insensitive)
        if stored == self.hash_password(password.lower()):
            return True, None
        return False, "Invalid password"

    def create_session(self, username):
        token = hashlib.sha256(
            f"{username}:{self.secret_key}".encode()
        ).hexdigest()[:32]
        self.sessions[token] = username
        return token

    def validate_session(self, token):
        return self.sessions.get(token)
''',

    "app/services.py": '''\
"""Business logic / service layer."""
from validators import validate_email, validate_price, validate_username
from cache import Cache
from config import MAX_CACHE_SIZE

class UserService:
    def __init__(self):
        self.users = {}
        self.cache = Cache(MAX_CACHE_SIZE)

    def create_user(self, username, email, role="viewer"):
        valid, err = validate_username(username)
        if not valid:
            return None, err
        valid, err = validate_email(email)
        if not valid:
            return None, err
        if username in self.users:
            return None, "Username already exists"
        from models import User
        user = User(username, email, role)
        self.users[username] = user
        self.cache.set(f"user:{username}", user.to_dict())
        return user, None

    def get_user(self, username):
        cached = self.cache.get(f"user:{username}")
        if cached:
            return cached, None
        user = self.users.get(username)
        if not user:
            return None, "User not found"
        data = user.to_dict()
        self.cache.set(f"user:{username}", data)
        return data, None

    def update_email(self, username, new_email):
        valid, err = validate_email(new_email)
        if not valid:
            return None, err
        user = self.users.get(username)
        if not user:
            return None, "User not found"
        user.email = new_email
        # Bug: doesn't invalidate cache after update — stale data
        return user.to_dict(), None


class ProductService:
    def __init__(self):
        self.products = {}
        self.cache = Cache(MAX_CACHE_SIZE)

    def create_product(self, name, price, category, stock=0):
        valid, err = validate_price(price)
        if not valid:
            return None, err
        if name in self.products:
            return None, "Product already exists"
        from models import Product
        product = Product(name, price, category, stock)
        self.products[name] = product
        self.cache.set(f"product:{name}", product.to_dict())
        return product, None

    def get_product(self, name):
        cached = self.cache.get(f"product:{name}")
        if cached:
            return cached, None
        product = self.products.get(name)
        if not product:
            return None, "Product not found"
        data = product.to_dict()
        self.cache.set(f"product:{name}", data)
        return data, None

    def list_by_category(self, category):
        return [p.to_dict() for p in self.products.values() if p.category == category]
''',

    "app/handlers.py": '''\
"""Request handler — dispatches to services."""
from services import UserService, ProductService
from auth import AuthService
from config import SECRET_KEY

user_svc = UserService()
product_svc = ProductService()
auth_svc = AuthService(SECRET_KEY)

def handle(action, **kwargs):
    """Simple action dispatcher."""
    if action == "create_user":
        return user_svc.create_user(kwargs["username"], kwargs["email"],
                                     kwargs.get("role", "viewer"))
    elif action == "get_user":
        return user_svc.get_user(kwargs["username"])
    elif action == "update_email":
        return user_svc.update_email(kwargs["username"], kwargs["email"])
    elif action == "create_product":
        return product_svc.create_product(
            kwargs["name"], kwargs["price"], kwargs["category"],
            kwargs.get("stock", 0))
    elif action == "get_product":
        return product_svc.get_product(kwargs["name"])
    elif action == "list_products":
        return product_svc.list_by_category(kwargs["category"]), None
    elif action == "register":
        auth_svc.register(kwargs["username"], kwargs["password"])
        return True, None
    elif action == "login":
        return auth_svc.authenticate(kwargs["username"], kwargs["password"])
    else:
        return None, f"Unknown action: {action}"
''',

    "app/utils.py": '''\
"""Utility functions."""

def paginate(items, page=1, page_size=10):
    """Return a page of items."""
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": items[start:end],
        "total": len(items),
        "page": page,
        "pages": (len(items) + page_size - 1) // page_size,
    }

def format_price(price):
    """Format price as string with 2 decimal places."""
    return f"${price:.2f}"

def slugify(text):
    """Convert text to URL-friendly slug."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")
''',

    "app/__init__.py": "",

    "test_app.py": '''\
"""Integration tests for the full application stack."""
import sys
sys.path.insert(0, "app")
from handlers import handle

def test_create_and_get_user():
    """Basic user CRUD."""
    user, err = handle("create_user", username="alice", email="alice@example.com")
    assert err is None and user.username == "alice", f"Create failed: {err}"

    data, err = handle("get_user", username="alice")
    assert err is None and data["email"] == "alice@example.com"
    print("  create_and_get_user: PASSED")

def test_email_with_plus():
    """Email addresses with + should be valid (e.g., user+tag@domain.com)."""
    user, err = handle("create_user", username="bob_plus",
                       email="bob+newsletter@example.com")
    assert err is None, f"Plus-address should be valid: {err}"
    assert user.email == "bob+newsletter@example.com"
    print("  email_with_plus: PASSED")

def test_update_email_cache():
    """After updating email, get_user should return new email (not stale cache)."""
    handle("create_user", username="carol", email="carol@old.com")
    # First get (caches the result)
    data1, _ = handle("get_user", username="carol")
    assert data1["email"] == "carol@old.com"

    # Update email
    handle("update_email", username="carol", email="carol@new.com")

    # Second get should return NEW email, not cached old one
    data2, _ = handle("get_user", username="carol")
    assert data2["email"] == "carol@new.com", \\
        f"Expected carol@new.com, got {data2['email']} (stale cache?)"
    print("  update_email_cache: PASSED")

def test_cache_capacity():
    """Cache should hold at least 20 items without evicting recent ones."""
    for i in range(25):
        handle("create_product", name=f"item_{i}", price=10.0 + i,
               category="test", stock=i)

    # Access items 5 through 24 to put them in cache
    for i in range(5, 25):
        handle("get_product", name=f"item_{i}")

    # Now access item_5 — with cache size >= 20 it should still be cached
    # With cache size 5, it would have been evicted
    from handlers import product_svc
    hits_before = product_svc.cache.hits
    data, err = handle("get_product", name="item_5")
    hits_after = product_svc.cache.hits
    assert err is None and data["name"] == "item_5"
    # Should be a cache HIT (not miss) if cache is large enough
    assert hits_after > hits_before, \\
        f"item_5 should be a cache hit (cache size={product_svc.cache.stats()['max_size']}, need >= 20)"
    print("  cache_capacity: PASSED")

def test_auth_case_sensitive():
    """Passwords should be case-sensitive."""
    handle("create_user", username="dave", email="dave@example.com")
    handle("register", username="dave", password="Secret123")

    # Correct password should work
    ok, err = handle("login", username="dave", password="Secret123")
    assert ok, f"Correct password should work: {err}"

    # Wrong case should FAIL
    ok, err = handle("login", username="dave", password="secret123")
    assert not ok, "Different case password should fail (case-sensitive)"
    print("  auth_case_sensitive: PASSED")

def test_product_crud():
    """Basic product operations."""
    prod, err = handle("create_product", name="Gadget", price=29.99,
                       category="electronics", stock=100)
    assert err is None and prod.name == "Gadget"

    data, err = handle("get_product", name="Gadget")
    assert data["price"] == 29.99
    print("  product_crud: PASSED")

def test_list_by_category():
    handle("create_product", name="Phone", price=999, category="electronics", stock=5)
    handle("create_product", name="Shirt", price=25, category="clothing", stock=50)
    results, _ = handle("list_products", category="electronics")
    names = [p["name"] for p in results]
    assert "Phone" in names
    assert "Shirt" not in names
    print("  list_by_category: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_create_and_get_user", "test_email_with_plus",
                  "test_update_email_cache", "test_cache_capacity",
                  "test_auth_case_sensitive", "test_product_crud",
                  "test_list_by_category"]:
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
You are a senior developer debugging a Python web application.

1. Run test_app.py to see failures
2. Read source files in app/ to understand the architecture
3. Fix the bugs (there are multiple bugs across different files)
4. Run the tests again to verify

Print the final test output.
"""

FORCED_SCRATCHPAD_PROMPT = """\
You are a senior developer debugging a Python web application.

STRICT RULES — follow these EXACTLY:

STEP 1: Create _notes.md as your FIRST action.

STEP 2: Run test_app.py to see failures. Update _notes.md with:
  - Which tests failed and error messages

STEP 3: Read each source file in app/. After reading EACH file, update _notes.md:
  - File name, purpose, imports
  - Key functions/classes and what they do
  - Suspicious code — potential bugs
  - Dependencies: which other files this one imports/uses

STEP 4: Review _notes.md. Write a "DIAGNOSIS" section:
  - List each bug: file, line, what's wrong, what it should be
  - Note cross-file dependencies for each bug

STEP 5: Fix all bugs based on your diagnosis.

STEP 6: Run tests to verify. Print the output.

CRITICAL CONSTRAINTS:
- You are FORBIDDEN from using Edit on any .py source file unless
  _notes.md exists AND has been updated within your last 2 tool calls
- After reading each source file, you MUST update _notes.md BEFORE
  reading the next file or making any edit
- Your notes are essential for tracking 8 files of dependencies
"""

experiment = Experiment(
    name="working_memory_scale",
    description=(
        "Working memory at scale: 8 source files + 3 bugs. "
        "Tests whether scratchpad helps when there are many files to track. "
        "max_turns=25, 1 task × 5 samples."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Implicit vs forced scratchpad on 8-file codebase",
    ),
    agent_a=AgentConfig(
        name="implicit_memory",
        model="claude-haiku-4-5",
        system_prompt=IMPLICIT_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=25,
    ),
    agent_b=AgentConfig(
        name="forced_scratchpad",
        model="claude-haiku-4-5",
        system_prompt=FORCED_SCRATCHPAD_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=25,
    ),
    tasks=[
        TaskItem(
            prompt=(
                "Fix all bugs in this web application. The code is in app/. "
                "Run: python test_app.py\n"
                "There are multiple bugs across different files. "
                "Print the final test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="very_hard",
            tags=["multi-file", "cross-dependency", "8-files"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["working-memory", "scale-test", "8-file-codebase"],
)
