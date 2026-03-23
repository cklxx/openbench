"""
Context Pressure — Hard Mode (Calibrated for ~60% Baseline)

Previous experiments: implicit always gets 100% because agents use test output
to skip irrelevant files (only reads ~10 of 30 files).

This version forces the agent to read MORE files:
- End-to-end integration tests that don't point to specific files
- Bugs that require tracing through 3-4 file chains
- 6 bugs (not 4) — more to find and fix
- max_turns=18 (tight for 15 files + 6 bugs)

Target: implicit ~60%, scratchpad ~40-60% (or maybe scratchpad finally helps).
"""
import importlib.util, os
_spec = importlib.util.spec_from_file_location(
    "cpb", os.path.join(os.path.dirname(__file__), "context_pressure_boundary.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

# Start with 15-file codebase, add 2 more bugs via modified files
SETUP_FILES = dict(_mod.SETUP_FILES)

# Override services.py to add a SECOND bug: create() doesn't validate duplicate email
SETUP_FILES["app/services.py"] = '''\
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
        # Bug 5: doesn't check for duplicate email across users
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
        # Bug 6 (from original): doesn't invalidate cache
        return u.to_dict(), None

    def find_by_email(self, email):
        for u in self.users.values():
            if u.email == email:
                return u.to_dict(), None
        return None, "Not found"
'''

# Override handlers to add duplicate email check endpoint
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
    elif action == "update_email":
        return user_svc.update_email(kw["username"], kw["email"])
    elif action == "find_by_email":
        return user_svc.find_by_email(kw["email"])
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
'''

# End-to-end tests: exercise full flows, don't point to specific files
SETUP_FILES["test_app.py"] = '''\
"""End-to-end integration tests for e-commerce application.
Each test exercises a complete user flow across multiple modules."""
import sys
sys.path.insert(0, "app")
from handlers import handle, analytics

def test_complete_purchase_flow():
    """User registers, browses products, places order, gets taxed correctly."""
    # Setup
    handle("create_user", username="flow_user", email="flow@shop.com")
    handle("add_product", name="FlowItem", price=50.00, category="test", stock=100)

    # Place order
    order, err = handle("create_order", username="flow_user",
                        items=[{"product": "FlowItem", "qty": 2}])
    assert err is None, f"Order creation failed: {err}"

    # Check tax: 2 × $50 = $100, 10% tax = $110
    total, err = handle("order_total_with_tax", order_id=order.order_id)
    assert total == 110.00, \\
        f"Complete purchase: expected $110.00 (10% tax on $100), got ${total}"
    print("  complete_purchase_flow: PASSED")

def test_order_notification_flow():
    """Create order and verify notification contains correct username."""
    handle("create_user", username="notif_user", email="notif@shop.com")
    handle("add_product", name="NotifItem", price=30.00, category="test", stock=50)
    order, _ = handle("create_order", username="notif_user",
                      items=[{"product": "NotifItem", "qty": 1}])
    msg, err = handle("notify_order", order_id=order.order_id)
    assert err is None, f"Notification flow failed: {err}"
    assert "notif_user" in msg, \\
        f"Notification should contain username 'notif_user': {msg}"
    print("  order_notification_flow: PASSED")

def test_cache_consistency_flow():
    """Update user email and verify subsequent reads return updated data."""
    handle("create_user", username="cache_user", email="old@shop.com")
    # Read to populate cache
    handle("get_user", username="cache_user")
    # Update email
    handle("update_email", username="cache_user", email="new@shop.com")
    # Read again — should get new email, not stale cache
    data, _ = handle("get_user", username="cache_user")
    assert data["email"] == "new@shop.com", \\
        f"After email update, expected new@shop.com, got {data['email']} (stale cache?)"
    print("  cache_consistency_flow: PASSED")

def test_zero_quantity_order_flow():
    """Ordering zero items should be rejected at validation layer."""
    handle("create_user", username="zero_user", email="zero@shop.com")
    handle("add_product", name="ZeroItem", price=5.00, category="test", stock=200)
    order, err = handle("create_order", username="zero_user",
                        items=[{"product": "ZeroItem", "qty": 0}])
    assert order is None, \\
        f"Zero quantity order should be rejected, got order={order}"
    print("  zero_quantity_order_flow: PASSED")

def test_analytics_ranking_flow():
    """Track events and verify top events returns most frequent first."""
    analytics.counters.clear()
    # Simulate activity
    for _ in range(20):
        analytics.track("browse")
    for _ in range(8):
        analytics.track("search")
    for _ in range(2):
        analytics.track("purchase")

    top, _ = handle("top_events", n=3)
    assert top[0][0] == "browse", \\
        f"Most tracked event should be 'browse' (20), got {top[0]}"
    assert top[0][1] >= top[1][1] >= top[2][1], \\
        f"Events should be sorted by frequency descending: {top}"
    print("  analytics_ranking_flow: PASSED")

def test_unique_email_flow():
    """Two users should not share the same email address."""
    handle("create_user", username="email_user1", email="shared@shop.com")
    user2, err = handle("create_user", username="email_user2", email="shared@shop.com")
    assert user2 is None, \\
        f"Duplicate email should be rejected, but user2 was created: {user2}"
    print("  unique_email_flow: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    tests = [
        "test_complete_purchase_flow",
        "test_order_notification_flow",
        "test_cache_consistency_flow",
        "test_zero_quantity_order_flow",
        "test_analytics_ranking_flow",
        "test_unique_email_flow",
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
# 6 bugs across 15 files:
# 1. config.py: TAX_RATE = 0.08 → 0.10 (test_complete_purchase_flow)
# 2. validators.py: validate_quantity allows qty=0 (test_zero_quantity_order_flow)
# 3. notifications.py: order["user"] → "username" (test_order_notification_flow)
# 4. analytics.py: top_events ascending → descending (test_analytics_ranking_flow)
# 5. services.py: create() doesn't check duplicate email (test_unique_email_flow)
# 6. services.py: update_email() missing cache invalidation (test_cache_consistency_flow)
#
# Tests are END-TO-END — they don't name the buggy file.
# Agent must trace: test → handler → service → config/validator/notification
# ═══════════════════════════════════════════════════════════

IMPLICIT_PROMPT = """\
You are a senior developer debugging a Python e-commerce application.
The code is in app/ with 15 source files.
Fix all bugs and make all tests pass.
Print the final test output.
"""

SCRATCHPAD_PROMPT = """\
You are a senior developer debugging a Python e-commerce application.
The code is in app/ with 15 source files.

This is a large codebase. You SHOULD maintain _notes.md to track:
- Which tests fail and what the errors suggest
- File dependencies you discover
- Bug hypotheses and diagnosis

You can re-read files whenever needed. Notes are recommended, not mandatory.

Fix all bugs and make all tests pass.
Print the final test output.
"""

experiment = Experiment(
    name="context_pressure_hard",
    description=(
        "Hard context pressure: 15 files, 6 bugs, end-to-end tests. "
        "Tests don't point to files — agent must trace through call chains. "
        "max_turns=18, target ~60% baseline."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Implicit memory vs recommended (not forced) scratchpad on hard 15-file task",
    ),
    agent_a=AgentConfig(
        name="implicit",
        model="claude-haiku-4-5",
        system_prompt=IMPLICIT_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=18,
    ),
    agent_b=AgentConfig(
        name="scratchpad",
        model="claude-haiku-4-5",
        system_prompt=SCRATCHPAD_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=18,
    ),
    tasks=[
        TaskItem(
            prompt=(
                "Fix all bugs in this e-commerce application. The code is in app/. "
                "Run: python test_app.py\n"
                "Print the final test output."
            ),
            expected="PASSED",
            check_fn='"PASSED" in output or "pass" in output.lower()',
            difficulty="very_hard",
            tags=["15-files", "6-bugs", "end-to-end"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["context-pressure", "hard-mode", "end-to-end-tests"],
)
