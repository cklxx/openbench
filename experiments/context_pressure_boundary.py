"""
Context Pressure Boundary: 15-File Codebase

Working memory v2/v3/scale showed scratchpad loses at 3-file and 8-file scale.
Hypothesis: at 15 files, the context window gets crowded enough that external
notes start to help — or does implicit memory STILL win?

Design: E-commerce app with 15 source files + 1 test file.
4 cross-file bugs requiring understanding of 2-3 files each.
max_turns=25, num_samples=5.

If implicit still wins at 15 files, the scratchpad break-even is very far out.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    "app/__init__.py": "",

    # ═══════════════════════════════════════════════════════
    # 1. config.py — application settings
    # ═══════════════════════════════════════════════════════
    "app/config.py": '''\
DATABASE_URL = "sqlite:///shop.db"
MAX_CACHE_SIZE = 100
SECRET_KEY = "shop-secret-key"
RATE_LIMIT = 60
RATE_WINDOW = 3600
DEFAULT_PAGE_SIZE = 10
TAX_RATE = 0.08  # Bug: should be 0.10 — tests expect 10% tax
MIN_PASSWORD_LENGTH = 8
FREE_SHIPPING_THRESHOLD = 50.0
CURRENCY = "USD"
''',

    # ═══════════════════════════════════════════════════════
    # 2. models.py — data classes
    # ═══════════════════════════════════════════════════════
    "app/models.py": '''\
class User:
    def __init__(self, username, email, role="viewer"):
        self.username = username
        self.email = email
        self.role = role
        self.active = True
    def to_dict(self):
        return {"username": self.username, "email": self.email,
                "role": self.role, "active": self.active}

class Product:
    def __init__(self, name, price, category, stock=0):
        self.name = name
        self.price = price
        self.category = category
        self.stock = stock
    def to_dict(self):
        return {"name": self.name, "price": self.price,
                "category": self.category, "stock": self.stock}

class Order:
    def __init__(self, order_id, username, items=None):
        self.order_id = order_id
        self.username = username
        self.items = items or []
        self.status = "pending"
    def total(self):
        return sum(i["qty"] * i["price"] for i in self.items)
    def to_dict(self):
        return {"order_id": self.order_id, "username": self.username,
                "items": self.items, "status": self.status, "total": self.total()}
''',

    # ═══════════════════════════════════════════════════════
    # 3. validators.py — input validation
    # ═══════════════════════════════════════════════════════
    "app/validators.py": '''\
import re

def validate_email(email):
    if not email:
        return False, "Email required"
    if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", email):
        return True, None
    return False, "Invalid email"

def validate_username(username):
    if not username or len(username) < 3:
        return False, "Too short"
    if len(username) > 20:
        return False, "Too long"
    return True, None

def validate_password(password):
    if not password or len(password) < 8:
        return False, "Too short"
    return True, None

def validate_quantity(qty):
    """Validate order quantity — must be a positive integer."""
    if not isinstance(qty, int):
        return False, "Must be integer"
    # Bug: allows qty=0. Should be qty < 1 (minimum order is 1)
    if qty < 0:
        return False, "Must be positive"
    return True, None

def validate_price(price):
    if not isinstance(price, (int, float)):
        return False, "Must be a number"
    if price < 0:
        return False, "Must be non-negative"
    return True, None
''',

    # ═══════════════════════════════════════════════════════
    # 4. cache.py — LRU cache
    # ═══════════════════════════════════════════════════════
    "app/cache.py": '''\
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
''',

    # ═══════════════════════════════════════════════════════
    # 5. auth.py — authentication
    # ═══════════════════════════════════════════════════════
    "app/auth.py": '''\
import hashlib

class AuthService:
    def __init__(self, secret):
        self.secret = secret
        self.credentials = {}

    def hash_pw(self, pw):
        return hashlib.sha256((pw + self.secret).encode()).hexdigest()

    def register(self, username, password):
        self.credentials[username] = self.hash_pw(password)

    def authenticate(self, username, password):
        stored = self.credentials.get(username)
        if not stored:
            return False, "Unknown user"
        if stored == self.hash_pw(password):
            return True, None
        return False, "Wrong password"
''',

    # ═══════════════════════════════════════════════════════
    # 6. permissions.py — role-based access control
    # ═══════════════════════════════════════════════════════
    "app/permissions.py": '''\
ROLE_HIERARCHY = {"admin": 3, "editor": 2, "viewer": 1}

def has_permission(user, required_role):
    user_level = ROLE_HIERARCHY.get(user.role, 0)
    required_level = ROLE_HIERARCHY.get(required_role, 0)
    return user_level >= required_level

def can_edit(user):
    return has_permission(user, "editor")

def can_delete(user):
    return has_permission(user, "admin")

def can_view(user):
    return has_permission(user, "viewer")
''',

    # ═══════════════════════════════════════════════════════
    # 7. services.py — user service
    # ═══════════════════════════════════════════════════════
    "app/services.py": '''\
from validators import validate_email, validate_username
from cache import Cache
from config import MAX_CACHE_SIZE

class UserService:
    def __init__(self):
        self.users = {}
        self.cache = Cache(MAX_CACHE_SIZE)

    def create(self, username, email, role="viewer"):
        valid, err = validate_username(username)
        if not valid:
            return None, err
        valid, err = validate_email(email)
        if not valid:
            return None, err
        if username in self.users:
            return None, "Already exists"
        from models import User
        u = User(username, email, role)
        self.users[username] = u
        self.cache.set(f"user:{username}", u.to_dict())
        return u, None

    def get(self, username):
        cached = self.cache.get(f"user:{username}")
        if cached:
            return cached, None
        u = self.users.get(username)
        if not u:
            return None, "Not found"
        d = u.to_dict()
        self.cache.set(f"user:{username}", d)
        return d, None

    def update_email(self, username, new_email):
        valid, err = validate_email(new_email)
        if not valid:
            return None, err
        u = self.users.get(username)
        if not u:
            return None, "Not found"
        u.email = new_email
        self.cache.invalidate(f"user:{username}")
        return u.to_dict(), None

    def deactivate(self, username):
        u = self.users.get(username)
        if not u:
            return None, "Not found"
        u.active = False
        self.cache.invalidate(f"user:{username}")
        return u.to_dict(), None
''',

    # ═══════════════════════════════════════════════════════
    # 8. product_service.py — product operations
    # ═══════════════════════════════════════════════════════
    "app/product_service.py": '''\
from validators import validate_price
from cache import Cache
from config import MAX_CACHE_SIZE

class ProductService:
    def __init__(self):
        self.products = {}
        self.cache = Cache(MAX_CACHE_SIZE)

    def add(self, name, price, category, stock=0):
        valid, err = validate_price(price)
        if not valid:
            return None, err
        from models import Product
        p = Product(name, price, category, stock)
        self.products[name] = p
        self.cache.set(f"prod:{name}", p.to_dict())
        return p, None

    def get(self, name):
        cached = self.cache.get(f"prod:{name}")
        if cached:
            return cached, None
        p = self.products.get(name)
        if not p:
            return None, "Not found"
        d = p.to_dict()
        self.cache.set(f"prod:{name}", d)
        return d, None

    def update_stock(self, name, delta):
        p = self.products.get(name)
        if not p:
            return None, "Not found"
        p.stock += delta
        self.cache.invalidate(f"prod:{name}")
        return p.to_dict(), None

    def list_by_category(self, category):
        return [p.to_dict() for p in self.products.values()
                if p.category == category]
''',

    # ═══════════════════════════════════════════════════════
    # 9. order_service.py — order operations
    # ═══════════════════════════════════════════════════════
    "app/order_service.py": '''\
from validators import validate_quantity
from config import TAX_RATE

class OrderService:
    def __init__(self, product_svc):
        self.product_svc = product_svc
        self.orders = {}
        self.next_id = 1

    def create_order(self, username, items):
        """items: list of {"product": name, "qty": int}"""
        order_items = []
        for item in items:
            valid, err = validate_quantity(item["qty"])
            if not valid:
                return None, f"Invalid qty for {item['product']}: {err}"
            prod, err = self.product_svc.get(item["product"])
            if err:
                return None, err
            order_items.append({
                "product": item["product"],
                "qty": item["qty"],
                "price": prod["price"],
            })
        from models import Order
        order = Order(self.next_id, username, order_items)
        self.orders[self.next_id] = order
        self.next_id += 1
        return order, None

    def get_order(self, order_id):
        o = self.orders.get(order_id)
        if not o:
            return None, "Not found"
        return o.to_dict(), None

    def calculate_total_with_tax(self, order_id):
        o = self.orders.get(order_id)
        if not o:
            return None, "Not found"
        return round(o.total() * (1 + TAX_RATE), 2), None
''',

    # ═══════════════════════════════════════════════════════
    # 10. search.py — product search
    # ═══════════════════════════════════════════════════════
    "app/search.py": '''\
class SearchService:
    def __init__(self, product_svc):
        self.product_svc = product_svc

    def by_category(self, category):
        return [p.to_dict() for p in self.product_svc.products.values()
                if p.category == category]

    def by_price_range(self, min_price, max_price):
        return [p.to_dict() for p in self.product_svc.products.values()
                if min_price <= p.price <= max_price]

    def by_name(self, query):
        q = query.lower()
        return [p.to_dict() for p in self.product_svc.products.values()
                if q in p.name.lower()]

    def in_stock(self):
        return [p.to_dict() for p in self.product_svc.products.values()
                if p.stock > 0]
''',

    # ═══════════════════════════════════════════════════════
    # 11. notifications.py — notification service
    # ═══════════════════════════════════════════════════════
    "app/notifications.py": '''\
class NotificationService:
    def __init__(self):
        self.sent = []

    def notify_order_created(self, order_dict):
        """Send notification when order is created."""
        # Bug: uses order_dict["user"] but Order.to_dict() has "username"
        msg = f"Order #{order_dict['order_id']} confirmed for {order_dict['user']}. " \\
              f"Total: ${order_dict['total']:.2f}"
        self.sent.append(msg)
        return msg

    def notify_shipped(self, order_dict):
        msg = f"Order #{order_dict['order_id']} shipped to {order_dict['username']}!"
        self.sent.append(msg)
        return msg

    def get_all(self):
        return list(self.sent)
''',

    # ═══════════════════════════════════════════════════════
    # 12. middleware.py — rate limiting and logging
    # ═══════════════════════════════════════════════════════
    "app/middleware.py": '''\
import time

class RateLimiter:
    def __init__(self, limit, window):
        self.limit = limit
        self.window = window
        self.requests = {}

    def check(self, username):
        now = time.time()
        if username not in self.requests:
            self.requests[username] = []
        self.requests[username] = [
            t for t in self.requests[username] if now - t < self.window
        ]
        if len(self.requests[username]) >= self.limit:
            return False, "Rate limited"
        self.requests[username].append(now)
        return True, None

class RequestLogger:
    def __init__(self):
        self.logs = []

    def log(self, action, username, success):
        self.logs.append({"action": action, "user": username, "ok": success})

    def get_logs(self, username=None):
        if username:
            return [l for l in self.logs if l["user"] == username]
        return list(self.logs)
''',

    # ═══════════════════════════════════════════════════════
    # 13. analytics.py — event tracking
    # ═══════════════════════════════════════════════════════
    "app/analytics.py": '''\
class Analytics:
    def __init__(self):
        self.counters = {}

    def track(self, event, username=None):
        key = f"{event}:{username}" if username else event
        self.counters[key] = self.counters.get(key, 0) + 1

    def get_count(self, event, username=None):
        key = f"{event}:{username}" if username else event
        return self.counters.get(key, 0)

    def top_events(self, n=5):
        """Return top N events by count, most frequent first."""
        # Bug: sorts ascending — returns LEAST common instead of most common
        sorted_events = sorted(self.counters.items(), key=lambda x: x[1])
        return sorted_events[:n]

    def get_all(self):
        return dict(self.counters)
''',

    # ═══════════════════════════════════════════════════════
    # 14. formatters.py — output formatting
    # ═══════════════════════════════════════════════════════
    "app/formatters.py": '''\
from config import CURRENCY

def format_price(price):
    if CURRENCY == "USD":
        return f"${price:.2f}"
    return f"{price:.2f} {CURRENCY}"

def format_order_summary(order_dict):
    lines = [f"Order #{order_dict['order_id']} — {order_dict['username']}"]
    for item in order_dict["items"]:
        lines.append(f"  {item['product']} x{item['qty']} @ {format_price(item['price'])}")
    lines.append(f"  Subtotal: {format_price(order_dict['total'])}")
    return "\\n".join(lines)

def format_user(user_dict):
    status = "Active" if user_dict["active"] else "Inactive"
    return f"{user_dict['username']} ({user_dict['role']}) [{status}]"
''',

    # ═══════════════════════════════════════════════════════
    # 15. inventory.py — stock management
    # ═══════════════════════════════════════════════════════
    "app/inventory.py": '''\
class InventoryManager:
    def __init__(self, product_svc):
        self.product_svc = product_svc
        self.reservations = {}

    def check_stock(self, product_name, qty):
        p = self.product_svc.products.get(product_name)
        if not p:
            return False, "Not found"
        if p.stock < qty:
            return False, f"Insufficient: {p.stock} < {qty}"
        return True, None

    def reserve(self, order_id, items):
        for item in items:
            ok, err = self.check_stock(item["product"], item["qty"])
            if not ok:
                return False, err
        for item in items:
            self.product_svc.products[item["product"]].stock -= item["qty"]
        self.reservations[order_id] = items
        return True, None

    def release(self, order_id):
        items = self.reservations.pop(order_id, None)
        if not items:
            return False, "No reservation"
        for item in items:
            self.product_svc.products[item["product"]].stock += item["qty"]
        return True, None
''',

    # ═══════════════════════════════════════════════════════
    # 16. handlers.py — request dispatcher (wires everything)
    # ═══════════════════════════════════════════════════════
    "app/handlers.py": '''\
from services import UserService
from product_service import ProductService
from order_service import OrderService
from search import SearchService
from notifications import NotificationService
from middleware import RateLimiter, RequestLogger
from analytics import Analytics
from inventory import InventoryManager
from auth import AuthService
from config import SECRET_KEY, RATE_LIMIT, RATE_WINDOW

user_svc = UserService()
product_svc = ProductService()
order_svc = OrderService(product_svc)
search_svc = SearchService(product_svc)
notif_svc = NotificationService()
rate_limiter = RateLimiter(RATE_LIMIT, RATE_WINDOW)
logger = RequestLogger()
analytics = Analytics()
inventory = InventoryManager(product_svc)
auth_svc = AuthService(SECRET_KEY)

def handle(action, **kw):
    analytics.track(action, kw.get("username"))
    if action == "create_user":
        return user_svc.create(kw["username"], kw["email"], kw.get("role", "viewer"))
    elif action == "get_user":
        return user_svc.get(kw["username"])
    elif action == "add_product":
        return product_svc.add(kw["name"], kw["price"], kw["category"], kw.get("stock", 0))
    elif action == "get_product":
        return product_svc.get(kw["name"])
    elif action == "create_order":
        return order_svc.create_order(kw["username"], kw["items"])
    elif action == "get_order":
        return order_svc.get_order(kw["order_id"])
    elif action == "order_total_with_tax":
        return order_svc.calculate_total_with_tax(kw["order_id"])
    elif action == "search_products":
        return search_svc.by_name(kw["query"]), None
    elif action == "notify_order":
        order, err = order_svc.get_order(kw["order_id"])
        if err:
            return None, err
        return notif_svc.notify_order_created(order), None
    elif action == "top_events":
        return analytics.top_events(kw.get("n", 5)), None
    elif action == "reserve_stock":
        return inventory.reserve(kw["order_id"], kw["items"])
    else:
        return None, f"Unknown action: {action}"
''',

    # ═══════════════════════════════════════════════════════
    # Test file — integration tests
    # ═══════════════════════════════════════════════════════
    "test_app.py": '''\
"""Integration tests for 15-file e-commerce application."""
import sys
sys.path.insert(0, "app")
from handlers import handle, analytics

def test_user_crud():
    """Basic user creation and retrieval."""
    user, err = handle("create_user", username="alice", email="alice@shop.com")
    assert err is None and user.username == "alice"
    data, err = handle("get_user", username="alice")
    assert data["email"] == "alice@shop.com"
    print("  user_crud: PASSED")

def test_product_crud():
    """Basic product operations."""
    prod, err = handle("add_product", name="Laptop", price=999.99,
                       category="electronics", stock=50)
    assert err is None and prod.name == "Laptop"
    data, err = handle("get_product", name="Laptop")
    assert data["price"] == 999.99
    print("  product_crud: PASSED")

def test_order_with_tax():
    """Order total should include 10% tax."""
    handle("add_product", name="Book", price=20.00, category="books", stock=100)
    order, err = handle("create_order", username="alice",
                        items=[{"product": "Book", "qty": 3}])
    assert err is None
    total, err = handle("order_total_with_tax", order_id=order.order_id)
    assert err is None
    # 3 * $20 = $60 + 10% tax = $66.00
    assert total == 66.00, f"Expected $66.00 (10% tax on $60), got ${total}"
    print("  order_with_tax: PASSED")

def test_zero_quantity_rejected():
    """Ordering 0 items should be rejected."""
    handle("add_product", name="Pen", price=2.00, category="office", stock=200)
    order, err = handle("create_order", username="alice",
                        items=[{"product": "Pen", "qty": 0}])
    assert order is None and err is not None, \\
        f"Zero quantity should be rejected, got order={order}"
    print("  zero_quantity_rejected: PASSED")

def test_order_notification():
    """Notification should include username from order."""
    handle("add_product", name="Mouse", price=25.00, category="electronics", stock=30)
    order, _ = handle("create_order", username="alice",
                      items=[{"product": "Mouse", "qty": 1}])
    msg, err = handle("notify_order", order_id=order.order_id)
    assert err is None, f"Notification failed: {err}"
    assert "alice" in msg, f"Notification should mention username: {msg}"
    print("  order_notification: PASSED")

def test_top_analytics():
    """Top events should return most frequent first."""
    # Reset analytics for clean test
    analytics.counters.clear()
    for _ in range(10):
        analytics.track("page_view")
    for _ in range(5):
        analytics.track("add_to_cart")
    for _ in range(1):
        analytics.track("checkout")

    top, _ = handle("top_events", n=3)
    assert len(top) == 3
    # First should be page_view (10), not checkout (1)
    assert top[0][0] == "page_view", \\
        f"Most frequent should be page_view (10), got {top[0]}"
    assert top[0][1] >= top[1][1] >= top[2][1], \\
        f"Should be sorted descending: {top}"
    print("  top_analytics: PASSED")

def test_search_products():
    """Search should find products by name."""
    handle("add_product", name="Wireless Keyboard", price=45.00,
           category="electronics", stock=20)
    results, _ = handle("search_products", query="wireless")
    assert len(results) >= 1
    assert any("Wireless" in r["name"] for r in results)
    print("  search_products: PASSED")

def test_stock_reservation():
    """Stock reservation should deduct from available stock."""
    handle("add_product", name="Headphones", price=79.99,
           category="electronics", stock=10)
    from handlers import inventory
    ok, err = inventory.reserve(999, [{"product": "Headphones", "qty": 3}])
    assert ok, f"Reservation failed: {err}"
    from handlers import product_svc
    assert product_svc.products["Headphones"].stock == 7
    print("  stock_reservation: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    tests = [
        "test_user_crud", "test_product_crud", "test_order_with_tax",
        "test_zero_quantity_rejected", "test_order_notification",
        "test_top_analytics", "test_search_products", "test_stock_reservation",
    ]
    for name in tests:
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

# ═══════════════════════════════════════════════════════════
# Bugs summary (for reference, NOT shown to agents):
#
# 1. config.py: TAX_RATE = 0.08 → should be 0.10
#    Test: test_order_with_tax expects $66 (10% of $60)
#    Trace: test → order_service.calculate_total_with_tax → config.TAX_RATE
#
# 2. validators.py: validate_quantity allows qty=0 (checks < 0, should be < 1)
#    Test: test_zero_quantity_rejected expects rejection
#    Trace: test → order_service.create_order → validators.validate_quantity
#
# 3. notifications.py: order_dict["user"] → should be order_dict["username"]
#    Test: test_order_notification expects KeyError or wrong field
#    Trace: test → handlers.notify_order → notifications.notify_order_created
#           → models.Order.to_dict (has "username", not "user")
#
# 4. analytics.py: top_events sorts ascending → should sort descending
#    Test: test_top_analytics expects most frequent first
#    Trace: test → handlers.top_events → analytics.top_events
# ═══════════════════════════════════════════════════════════

IMPLICIT_PROMPT = """\
You are a senior developer debugging a Python e-commerce application.

1. Run the tests to see what's failing
2. Read source files in app/ to understand the architecture
3. Fix all bugs (there are multiple bugs across different files)
4. Run the tests again to verify

Print the final test output.
"""

FORCED_SCRATCHPAD_PROMPT = """\
You are a senior developer debugging a Python e-commerce application.

STRICT RULES — follow these EXACTLY:

STEP 1: Create _notes.md as your FIRST action.

STEP 2: Run test_app.py to see failures. Update _notes.md with:
  - Which tests failed and their error messages

STEP 3: Read each source file in app/. After reading EACH file, update _notes.md:
  - File purpose and key functions
  - Imports and dependencies (which other files it uses)
  - Suspicious code — potential bugs
  - How it connects to failing tests

STEP 4: Review _notes.md. Write a "DIAGNOSIS" section:
  - For each bug: file, function, what's wrong, what it should be
  - Cross-file dependency chain for each bug

STEP 5: Fix all bugs based on your diagnosis.

STEP 6: Run tests to verify. Print the output.

CRITICAL CONSTRAINTS:
- You are FORBIDDEN from using Edit on any .py source file unless
  _notes.md exists AND has been updated within your last 2 tool calls
- After reading each source file, you MUST update _notes.md BEFORE
  reading the next file or making any edit
- Your notes are essential for tracking 15 files of dependencies
"""

experiment = Experiment(
    name="context_pressure_boundary",
    description=(
        "Context pressure at 15-file scale: does scratchpad finally help? "
        "E-commerce app with 15 source files + 4 cross-file bugs. "
        "max_turns=25, 1 task × 5 samples."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Implicit memory vs forced scratchpad on 15-file codebase",
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
                "Fix all bugs in this e-commerce application. The code is in app/. "
                "Run: python test_app.py\n"
                "There are multiple bugs across different files. "
                "Print the final test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output or "pass" in output.lower()',
            difficulty="very_hard",
            tags=["multi-file", "cross-dependency", "15-files"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["working-memory", "context-pressure", "15-file-codebase"],
)
