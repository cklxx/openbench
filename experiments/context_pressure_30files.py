"""
Context Pressure: 30-File Scale (~68K tokens)

Research findings:
- LongCodeBench: Claude drops from 29% to 3% at 1M tokens on coding tasks
- BABILong: Models effectively use only 10-20% of context window
- Context Rot (Chroma): Degradation starts at ~50K for 200K models
- 30 files ≈ 68K tokens → 34% of 200K window → near degradation zone

Previous results:
- 3 files: implicit 100%, scratchpad 0-65%
- 8 files: implicit 100%, scratchpad 60%
- 15 files: implicit 100%, scratchpad 20% (strict) / 100% (relaxed)

At 30 files, does implicit memory finally start degrading?

Design: E-commerce app expanded to 30 source files + 1 test file.
5 cross-file bugs requiring understanding of 2-4 files each.
max_turns=30, num_samples=5.
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "cpb", os.path.join(os.path.dirname(__file__), "context_pressure_boundary.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

# Start with the 15-file codebase and add 15 more files
SETUP_FILES = dict(_mod.SETUP_FILES)

# ═══════════════ Additional 15 files ═══════════════

SETUP_FILES["app/discount_service.py"] = '''\
"""Discount and coupon management."""
from config import TAX_RATE

class DiscountService:
    def __init__(self):
        self.coupons = {}

    def create_coupon(self, code, percent_off, min_order=0):
        self.coupons[code] = {
            "percent_off": percent_off,
            "min_order": min_order,
            "uses": 0,
        }

    def apply_coupon(self, code, subtotal):
        coupon = self.coupons.get(code)
        if not coupon:
            return subtotal, "Invalid coupon"
        if subtotal < coupon["min_order"]:
            return subtotal, f"Min order ${coupon['min_order']}"
        discount = subtotal * (coupon["percent_off"] / 100)
        coupon["uses"] += 1
        return round(subtotal - discount, 2), None

    def get_coupon(self, code):
        return self.coupons.get(code)
'''

SETUP_FILES["app/shipping_service.py"] = '''\
"""Shipping cost calculation."""
from config import FREE_SHIPPING_THRESHOLD

class ShippingService:
    RATES = {"standard": 5.99, "express": 12.99, "overnight": 24.99}

    def calculate(self, subtotal, method="standard"):
        if subtotal >= FREE_SHIPPING_THRESHOLD:
            return 0.0
        rate = self.RATES.get(method)
        if rate is None:
            return None
        return rate

    def available_methods(self):
        return list(self.RATES.keys())
'''

SETUP_FILES["app/payment_service.py"] = '''\
"""Payment processing (simulated)."""

class PaymentService:
    def __init__(self):
        self.transactions = []

    def charge(self, username, amount, method="credit_card"):
        if amount <= 0:
            return None, "Invalid amount"
        txn = {
            "username": username,
            "amount": round(amount, 2),
            "method": method,
            "status": "completed",
        }
        self.transactions.append(txn)
        return txn, None

    def refund(self, username, amount):
        txn = {
            "username": username,
            "amount": -round(amount, 2),
            "method": "refund",
            "status": "completed",
        }
        self.transactions.append(txn)
        return txn, None

    def get_balance(self, username):
        return sum(t["amount"] for t in self.transactions
                   if t["username"] == username)
'''

SETUP_FILES["app/review_service.py"] = '''\
"""Product reviews."""

class ReviewService:
    def __init__(self):
        self.reviews = {}  # product_name -> list of reviews

    def add_review(self, product_name, username, rating, text=""):
        if rating < 1 or rating > 5:
            return None, "Rating must be 1-5"
        review = {"username": username, "rating": rating, "text": text}
        self.reviews.setdefault(product_name, []).append(review)
        return review, None

    def get_reviews(self, product_name):
        return self.reviews.get(product_name, [])

    def average_rating(self, product_name):
        reviews = self.reviews.get(product_name, [])
        if not reviews:
            return 0.0
        # Bug: uses len(self.reviews) instead of len(reviews)
        # This divides by total number of PRODUCTS with reviews, not review count
        return sum(r["rating"] for r in reviews) / len(self.reviews)
'''

SETUP_FILES["app/wishlist_service.py"] = '''\
"""User wishlists."""

class WishlistService:
    def __init__(self):
        self.wishlists = {}  # username -> set of product names

    def add(self, username, product_name):
        self.wishlists.setdefault(username, set()).add(product_name)
        return True

    def remove(self, username, product_name):
        wl = self.wishlists.get(username, set())
        wl.discard(product_name)
        return True

    def get(self, username):
        return sorted(self.wishlists.get(username, set()))

    def count(self, username):
        return len(self.wishlists.get(username, set()))
'''

SETUP_FILES["app/coupon_validator.py"] = '''\
"""Coupon validation rules."""
import re

def validate_coupon_code(code):
    """Coupon codes must be 4-20 chars, alphanumeric + dash."""
    if not code or len(code) < 4:
        return False, "Code too short"
    if len(code) > 20:
        return False, "Code too long"
    if not re.match(r"^[A-Z0-9-]+$", code):
        return False, "Code must be uppercase alphanumeric with dashes"
    return True, None

def validate_discount(percent):
    if not isinstance(percent, (int, float)):
        return False, "Must be a number"
    if percent <= 0 or percent > 100:
        return False, "Must be 1-100"
    return True, None
'''

SETUP_FILES["app/email_service.py"] = '''\
"""Email sending (simulated)."""

class EmailService:
    def __init__(self):
        self.outbox = []

    def send(self, to_email, subject, body):
        if not to_email or "@" not in to_email:
            return False, "Invalid email"
        msg = {"to": to_email, "subject": subject, "body": body}
        self.outbox.append(msg)
        return True, None

    def get_sent(self, to_email=None):
        if to_email:
            return [m for m in self.outbox if m["to"] == to_email]
        return list(self.outbox)

    def count(self):
        return len(self.outbox)
'''

SETUP_FILES["app/report_service.py"] = '''\
"""Sales and analytics reports."""

class ReportService:
    def __init__(self, order_svc, product_svc):
        self.order_svc = order_svc
        self.product_svc = product_svc

    def total_revenue(self):
        total = 0
        for order in self.order_svc.orders.values():
            total += order.total()
        return round(total, 2)

    def top_products(self, n=5):
        counts = {}
        for order in self.order_svc.orders.values():
            for item in order.items:
                name = item["product"]
                counts[name] = counts.get(name, 0) + item["qty"]
        sorted_items = sorted(counts.items(), key=lambda x: -x[1])
        return sorted_items[:n]

    def orders_by_status(self):
        statuses = {}
        for order in self.order_svc.orders.values():
            s = order.status
            statuses[s] = statuses.get(s, 0) + 1
        return statuses
'''

SETUP_FILES["app/admin_service.py"] = '''\
"""Admin operations."""
from permissions import can_delete, can_edit

class AdminService:
    def __init__(self, user_svc, product_svc):
        self.user_svc = user_svc
        self.product_svc = product_svc

    def deactivate_user(self, admin_user, target_username):
        if not can_delete(admin_user):
            return None, "Permission denied"
        return self.user_svc.deactivate(target_username)

    def update_product_price(self, editor_user, product_name, new_price):
        if not can_edit(editor_user):
            return None, "Permission denied"
        p = self.product_svc.products.get(product_name)
        if not p:
            return None, "Product not found"
        p.price = new_price
        self.product_svc.cache.invalidate(f"prod:{product_name}")
        return p.to_dict(), None
'''

SETUP_FILES["app/migration_service.py"] = '''\
"""Data migration utilities."""

class MigrationService:
    def __init__(self):
        self.migrations = []

    def record(self, name, description):
        self.migrations.append({"name": name, "desc": description, "applied": True})

    def is_applied(self, name):
        return any(m["name"] == name and m["applied"] for m in self.migrations)

    def pending(self, all_migrations):
        return [m for m in all_migrations if not self.is_applied(m)]

    def history(self):
        return list(self.migrations)
'''

SETUP_FILES["app/logger.py"] = '''\
"""Application logging."""
import datetime

class AppLogger:
    def __init__(self, name):
        self.name = name
        self.entries = []

    def log(self, level, message):
        entry = {
            "ts": datetime.datetime.now().isoformat(),
            "level": level,
            "logger": self.name,
            "msg": message,
        }
        self.entries.append(entry)
        return entry

    def info(self, msg): return self.log("INFO", msg)
    def error(self, msg): return self.log("ERROR", msg)
    def warn(self, msg): return self.log("WARNING", msg)

    def get_entries(self, level=None):
        if level:
            return [e for e in self.entries if e["level"] == level]
        return list(self.entries)
'''

SETUP_FILES["app/error_handler.py"] = '''\
"""Centralized error handling."""

class AppError(Exception):
    def __init__(self, message, code="UNKNOWN"):
        super().__init__(message)
        self.code = code

class NotFoundError(AppError):
    def __init__(self, resource, identifier):
        super().__init__(f"{resource} '{identifier}' not found", "NOT_FOUND")

class ValidationError(AppError):
    def __init__(self, field, message):
        super().__init__(f"Validation failed for {field}: {message}", "VALIDATION")

class PermissionError(AppError):
    def __init__(self, action):
        super().__init__(f"Permission denied for: {action}", "FORBIDDEN")

def format_error(err):
    if isinstance(err, AppError):
        return {"error": str(err), "code": err.code}
    return {"error": str(err), "code": "UNKNOWN"}
'''

SETUP_FILES["app/serializers.py"] = '''\
"""Data serialization helpers."""

def serialize_user(user_dict, include_email=True):
    data = {"username": user_dict["username"], "role": user_dict["role"]}
    if include_email:
        data["email"] = user_dict["email"]
    data["active"] = user_dict["active"]
    return data

def serialize_product(product_dict, include_stock=False):
    data = {
        "name": product_dict["name"],
        "price": product_dict["price"],
        "category": product_dict["category"],
    }
    if include_stock:
        data["stock"] = product_dict["stock"]
    return data

def serialize_order(order_dict, include_items=True):
    data = {
        "id": order_dict["order_id"],
        "username": order_dict["username"],
        "status": order_dict["status"],
        "total": order_dict["total"],
    }
    if include_items:
        data["items"] = order_dict["items"]
    return data
'''

SETUP_FILES["app/constants.py"] = '''\
"""Application-wide constants."""

# Order statuses
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_SHIPPED = "shipped"
STATUS_DELIVERED = "delivered"
STATUS_CANCELLED = "cancelled"

VALID_STATUSES = [STATUS_PENDING, STATUS_CONFIRMED, STATUS_SHIPPED,
                  STATUS_DELIVERED, STATUS_CANCELLED]

# Product categories
CATEGORIES = ["electronics", "clothing", "books", "home", "sports",
              "toys", "food", "office", "beauty", "automotive"]

# Pagination defaults
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100
DEFAULT_PAGE = 1
'''

SETUP_FILES["app/event_bus.py"] = '''\
"""Simple event bus for decoupled communication."""

class EventBus:
    def __init__(self):
        self.handlers = {}

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def emit(self, event_name, data=None):
        results = []
        for handler in self.handlers.get(event_name, []):
            results.append(handler(data))
        return results

    def off(self, event_name, handler=None):
        if handler:
            self.handlers.get(event_name, []).remove(handler)
        else:
            self.handlers.pop(event_name, None)
'''

# Update handlers.py to wire in new services
SETUP_FILES["app/handlers.py"] = '''\
from services import UserService
from product_service import ProductService
from order_service import OrderService
from search import SearchService
from notifications import NotificationService
from middleware import RateLimiter, RequestLogger
from analytics import Analytics
from inventory import InventoryManager
from auth import AuthService
from discount_service import DiscountService
from shipping_service import ShippingService
from payment_service import PaymentService
from review_service import ReviewService
from wishlist_service import WishlistService
from report_service import ReportService
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
discount_svc = DiscountService()
shipping_svc = ShippingService()
payment_svc = PaymentService()
review_svc = ReviewService()
wishlist_svc = WishlistService()
report_svc = ReportService(order_svc, product_svc)

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
    elif action == "apply_coupon":
        return discount_svc.apply_coupon(kw["code"], kw["subtotal"])
    elif action == "add_review":
        return review_svc.add_review(kw["product"], kw["username"],
                                      kw["rating"], kw.get("text", ""))
    elif action == "avg_rating":
        return review_svc.average_rating(kw["product"]), None
    elif action == "shipping_cost":
        return shipping_svc.calculate(kw["subtotal"], kw.get("method", "standard")), None
    elif action == "charge":
        return payment_svc.charge(kw["username"], kw["amount"])
    elif action == "wishlist_add":
        return wishlist_svc.add(kw["username"], kw["product"]), None
    elif action == "wishlist_get":
        return wishlist_svc.get(kw["username"]), None
    elif action == "total_revenue":
        return report_svc.total_revenue(), None
    else:
        return None, f"Unknown action: {action}"
'''

# Update test file — add tests for new bugs + keep original 4
SETUP_FILES["test_app.py"] = '''\
"""Integration tests for 30-file e-commerce application."""
import sys
sys.path.insert(0, "app")
from handlers import handle, analytics

def test_user_crud():
    user, err = handle("create_user", username="alice", email="alice@shop.com")
    assert err is None and user.username == "alice"
    data, err = handle("get_user", username="alice")
    assert data["email"] == "alice@shop.com"
    print("  user_crud: PASSED")

def test_product_crud():
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
    analytics.counters.clear()
    for _ in range(10):
        analytics.track("page_view")
    for _ in range(5):
        analytics.track("add_to_cart")
    for _ in range(1):
        analytics.track("checkout")

    top, _ = handle("top_events", n=3)
    assert len(top) == 3
    assert top[0][0] == "page_view", \\
        f"Most frequent should be page_view (10), got {top[0]}"
    assert top[0][1] >= top[1][1] >= top[2][1], \\
        f"Should be sorted descending: {top}"
    print("  top_analytics: PASSED")

def test_search_products():
    handle("add_product", name="Wireless Keyboard", price=45.00,
           category="electronics", stock=20)
    results, _ = handle("search_products", query="wireless")
    assert len(results) >= 1
    assert any("Wireless" in r["name"] for r in results)
    print("  search_products: PASSED")

def test_stock_reservation():
    handle("add_product", name="Headphones", price=79.99,
           category="electronics", stock=10)
    from handlers import inventory
    ok, err = inventory.reserve(999, [{"product": "Headphones", "qty": 3}])
    assert ok, f"Reservation failed: {err}"
    from handlers import product_svc
    assert product_svc.products["Headphones"].stock == 7
    print("  stock_reservation: PASSED")

def test_average_rating():
    """Average rating should divide by number of reviews, not products."""
    handle("add_product", name="Widget", price=10.00, category="toys", stock=50)
    handle("add_product", name="Gizmo", price=15.00, category="toys", stock=50)
    # Add 4 reviews to Widget
    handle("add_review", product="Widget", username="u1", rating=5)
    handle("add_review", product="Widget", username="u2", rating=4)
    handle("add_review", product="Widget", username="u3", rating=3)
    handle("add_review", product="Widget", username="u4", rating=4)
    # Add 1 review to Gizmo (so there are 2 products with reviews)
    handle("add_review", product="Gizmo", username="u1", rating=2)

    avg, _ = handle("avg_rating", product="Widget")
    # (5+4+3+4) / 4 = 4.0, NOT (5+4+3+4) / 2 = 8.0
    assert avg == 4.0, f"Expected 4.0 (16/4 reviews), got {avg}"
    print("  average_rating: PASSED")

def test_shipping_free():
    """Orders over threshold should have free shipping."""
    cost, _ = handle("shipping_cost", subtotal=100.0, method="standard")
    assert cost == 0.0, f"Expected free shipping over $50, got ${cost}"
    print("  shipping_free: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    tests = [
        "test_user_crud", "test_product_crud", "test_order_with_tax",
        "test_zero_quantity_rejected", "test_order_notification",
        "test_top_analytics", "test_search_products", "test_stock_reservation",
        "test_average_rating", "test_shipping_free",
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
'''

# ═══════════════════════════════════════════════════════════
# Bugs summary (5 bugs across 30 files):
#
# Original 4 from 15-file version:
# 1. config.py: TAX_RATE = 0.08 → 0.10
# 2. validators.py: validate_quantity allows qty=0
# 3. notifications.py: order_dict["user"] → "username"
# 4. analytics.py: top_events sorts ascending → descending
#
# New bug:
# 5. review_service.py: average_rating divides by len(self.reviews)
#    instead of len(reviews) — divides by number of products with reviews
#    instead of number of reviews for that product
# ═══════════════════════════════════════════════════════════

IMPLICIT_PROMPT = """\
You are a senior developer debugging a Python e-commerce application.

1. Run the tests to see what's failing
2. Read source files in app/ to understand the architecture
3. Fix all bugs (there are multiple bugs across different files)
4. Run the tests again to verify

Print the final test output.
"""

RELAXED_SCRATCHPAD_PROMPT = """\
You are a senior developer debugging a Python e-commerce application.

Workflow:
1. Create _notes.md to track your findings
2. Run test_app.py to see failures — note them in _notes.md
3. Read source files, updating _notes.md with key observations
4. Write a diagnosis section in _notes.md
5. Fix all bugs, then run tests to verify

You SHOULD update _notes.md as you work — it helps track dependencies
across this large codebase. You CAN re-read files whenever needed.

Print the final test output.
"""

experiment = Experiment(
    name="context_pressure_30files",
    description=(
        "Context pressure at 30-file scale (~68K tokens). "
        "Does implicit memory start degrading? "
        "5 cross-file bugs, max_turns=30, 1 task × 5 samples."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Implicit memory vs relaxed scratchpad on 30-file codebase",
    ),
    agent_a=AgentConfig(
        name="implicit_memory",
        model="claude-haiku-4-5",
        system_prompt=IMPLICIT_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=30,
    ),
    agent_b=AgentConfig(
        name="relaxed_scratchpad",
        model="claude-haiku-4-5",
        system_prompt=RELAXED_SCRATCHPAD_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=30,
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
            tags=["multi-file", "cross-dependency", "30-files"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["working-memory", "context-pressure", "30-file-codebase"],
)
