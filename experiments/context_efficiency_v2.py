"""
Context Efficiency v2: Navigation Guidance in Large Codebases

v1 finding: single 3-bug task too hard for both (0/10 tie).
Interesting: guided used 20% fewer tools though.

v2 changes:
- Multiple tasks with varying codebase sizes (2-file, 4-file, 6-file)
- max_turns=8 (more room)
- More extreme guidance: exact file + line hints vs zero context
- 4 independent tasks to get per-task signal

The core question remains: does providing navigation context
(simulating compressed trajectory) improve fix rate?
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

UNGUIDED_PROMPT = """\
Fix the bugs in the project. Run the test to see what fails, then fix it.
You have limited turns — be efficient.
"""

GUIDED_PROMPT = """\
Fix the bugs in the project. Here is navigation guidance to save you time:

FOR TASK T1 (2 files):
- Bug in converter.py: the Celsius-to-Fahrenheit formula is wrong
- test_converter.py is the test (ground truth)

FOR TASK T2 (3 files):
- Bug in stats.py: median calculation is wrong for even-length lists
- Bug in formatter.py: percentage formatting rounds incorrectly
- test_stats.py is the test

FOR TASK T3 (4 files):
- Bug in auth.py: password hash comparison is case-sensitive when it shouldn't be
- Bug in session.py: session expiry check uses wrong comparison operator
- test_auth.py is the test

FOR TASK T4 (6 files):
- Bug in validators.py: stock validation checks wrong condition
- Bug in services.py: cancel_order subtracts stock instead of adding
- Bug in utils.py: format_currency loses negative sign
- test_app.py is the test

Use this map to go directly to the buggy files. Don't waste turns exploring.
"""

SETUP_FILES = {
    # ── Task 1: Simple 2-file project (easy) ─────────────────────────────
    "tasks/t1/converter.py": '''\
def celsius_to_fahrenheit(c):
    return c * 9/5 + 32

def fahrenheit_to_celsius(f):
    return (f - 32) * 9/5  # Bug: should be * 5/9

def km_to_miles(km):
    return km * 0.621371

def miles_to_km(miles):
    return miles / 0.621371
''',
    "tasks/t1/test_converter.py": '''\
from converter import *
assert celsius_to_fahrenheit(0) == 32
assert celsius_to_fahrenheit(100) == 212
assert abs(fahrenheit_to_celsius(212) - 100) < 0.01, f"F->C: {fahrenheit_to_celsius(212)}"
assert abs(fahrenheit_to_celsius(32) - 0) < 0.01
assert abs(km_to_miles(1) - 0.621371) < 0.001
assert abs(miles_to_km(1) - 1.60934) < 0.01
print("PASSED")
''',

    # ── Task 2: 3-file project (medium) ──────────────────────────────────
    "tasks/t2/stats.py": '''\
def mean(data):
    return sum(data) / len(data)

def median(data):
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n % 2 == 1:
        return sorted_data[n // 2]
    else:
        # Bug: integer division gives wrong index for even-length
        mid = n // 2
        return (sorted_data[mid] + sorted_data[mid + 1]) / 2  # Bug: should be mid-1 and mid

def std_dev(data):
    avg = mean(data)
    variance = sum((x - avg) ** 2 for x in data) / len(data)
    return variance ** 0.5
''',
    "tasks/t2/formatter.py": '''\
def format_pct(value, decimals=1):
    """Format as percentage string."""
    # Bug: multiplies by 100 twice (once here, once by caller expectation)
    return f"{value * 100:.{decimals}f}%"

def format_table(headers, rows):
    """Format as aligned text table."""
    widths = [max(len(str(h)), max(len(str(r[i])) for r in rows))
              for i, h in enumerate(headers)]
    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    separator = "-+-".join("-" * w for w in widths)
    data_lines = [" | ".join(str(r[i]).ljust(w) for i, w in enumerate(widths))
                  for r in rows]
    return "\\n".join([header_line, separator] + data_lines)
''',
    "tasks/t2/test_stats.py": '''\
from stats import mean, median, std_dev
from formatter import format_pct, format_table

# Mean
assert mean([1, 2, 3, 4, 5]) == 3.0

# Median odd
assert median([3, 1, 2]) == 2

# Median even
assert median([1, 2, 3, 4]) == 2.5, f"Median even: {median([1, 2, 3, 4])}"

# Std dev
assert abs(std_dev([2, 4, 4, 4, 5, 5, 7, 9]) - 2.0) < 0.01

# format_pct: 0.15 should be "15.0%"
assert format_pct(0.15) == "15.0%", f"Pct: {format_pct(0.15)}"
assert format_pct(0.5) == "50.0%", f"Pct: {format_pct(0.5)}"
assert format_pct(1.0) == "100.0%", f"Pct: {format_pct(1.0)}"

# format_table
table = format_table(["Name", "Score"], [["Alice", 95], ["Bob", 87]])
assert "Alice" in table
assert "Bob" in table

print("PASSED")
''',

    # ── Task 3: 4-file auth system (hard) ────────────────────────────────
    "tasks/t3/hasher.py": '''\
import hashlib

def hash_password(password):
    """Hash password with SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    """Verify password against hash."""
    return hash_password(password) == hashed
''',
    "tasks/t3/auth.py": '''\
from hasher import hash_password, verify_password

class AuthService:
    def __init__(self):
        self.users = {}  # username -> hashed_password

    def register(self, username, password):
        if username in self.users:
            return False, "Username taken"
        # Bug: stores hash in uppercase, but verify compares lowercase
        self.users[username] = hash_password(password).upper()
        return True, None

    def login(self, username, password):
        if username not in self.users:
            return False, "User not found"
        stored = self.users[username]
        if not verify_password(password, stored):
            return False, "Wrong password"
        return True, None
''',
    "tasks/t3/session.py": '''\
import time

class SessionManager:
    def __init__(self, ttl=3600):
        self.sessions = {}  # token -> (username, expires_at)
        self.ttl = ttl

    def create(self, username, now=None):
        now = now or time.time()
        token = f"sess_{username}_{int(now)}"
        self.sessions[token] = (username, now + self.ttl)
        return token

    def validate(self, token, now=None):
        now = now or time.time()
        if token not in self.sessions:
            return None, "Invalid session"
        username, expires = self.sessions[token]
        # Bug: > should be < (session is valid when now < expires)
        if now > expires:
            return username, None  # This returns valid for expired sessions!
        del self.sessions[token]
        return None, "Session expired"

    def revoke(self, token):
        self.sessions.pop(token, None)
''',
    "tasks/t3/test_auth.py": '''\
from auth import AuthService
from session import SessionManager

# Registration and login
auth = AuthService()
ok, err = auth.register("alice", "secret123")
assert ok, f"Register failed: {err}"

ok2, err2 = auth.login("alice", "secret123")
assert ok2, f"Login failed: {err2}"

ok3, err3 = auth.login("alice", "wrong")
assert not ok3, "Wrong password should fail"

# Duplicate registration
ok4, err4 = auth.register("alice", "other")
assert not ok4, "Duplicate should fail"

# Sessions
sm = SessionManager(ttl=3600)
token = sm.create("alice", now=1000)
assert token is not None

# Valid session (not expired)
user, err = sm.validate(token, now=2000)
assert user == "alice", f"Valid session failed: user={user}, err={err}"

# Expired session
token2 = sm.create("bob", now=1000)
user2, err2 = sm.validate(token2, now=5000)
assert user2 is None, f"Expired session should fail: user={user2}"

print("PASSED")
''',

    # ── Task 4: 6-file e-commerce (very hard) — same as v1 ──────────────
    "tasks/t4/models.py": '''\
from dataclasses import dataclass, field
from enum import Enum

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"

@dataclass
class User:
    id: int
    name: str
    email: str
    is_premium: bool = False

@dataclass
class Product:
    id: int
    name: str
    price: float
    stock: int

@dataclass
class OrderItem:
    product: Product
    quantity: int

    @property
    def subtotal(self):
        return self.product.price * self.quantity

@dataclass
class Order:
    id: int
    user: User
    items: list = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    discount_pct: float = 0.0

    def add_item(self, product, quantity):
        self.items.append(OrderItem(product, quantity))

    @property
    def subtotal(self):
        return sum(item.subtotal for item in self.items)

    @property
    def total(self):
        return round(self.subtotal * (1 - self.discount_pct / 100), 2)
''',
    "tasks/t4/repository.py": '''\
class Repository:
    def __init__(self):
        self.users = {}
        self.orders = {}
        self._uid = 1
        self._oid = 1

    def next_user_id(self):
        uid = self._uid; self._uid += 1; return uid

    def next_order_id(self):
        oid = self._oid; self._oid += 1; return oid

    def save_user(self, u): self.users[u.id] = u
    def save_order(self, o): self.orders[o.id] = o
''',
    "tasks/t4/validators.py": '''\
def validate_order(order):
    errors = []
    if not order.items:
        errors.append("Empty order")
    for item in order.items:
        if item.quantity <= 0:
            errors.append(f"Bad qty: {item.product.name}")
        if item.product.stock < 0:  # Bug: should check quantity > stock
            errors.append(f"No stock: {item.product.name}")
    return len(errors) == 0, errors
''',
    "tasks/t4/services.py": '''\
from models import OrderStatus, Order
from validators import validate_order

class OrderService:
    def __init__(self, repo):
        self.repo = repo

    def create_order(self, user, items):
        order = Order(id=self.repo.next_order_id(), user=user)
        for prod, qty in items:
            order.add_item(prod, qty)
        if user.is_premium:
            order.discount_pct = 10
        return order

    def confirm(self, order):
        ok, errs = validate_order(order)
        if not ok:
            return False, errs
        for item in order.items:
            item.product.stock -= item.quantity
        order.status = OrderStatus.CONFIRMED
        self.repo.save_order(order)
        return True, []

    def cancel(self, order):
        if order.status != OrderStatus.CONFIRMED:
            return False, ["Not confirmed"]
        for item in order.items:
            item.product.stock -= item.quantity  # Bug: should += to restore
        order.status = OrderStatus.CANCELLED
        self.repo.save_order(order)
        return True, []
''',
    "tasks/t4/utils.py": '''\
def format_currency(amount):
    return f"${abs(amount):.2f}"  # Bug: loses negative sign
''',
    "tasks/t4/test_app.py": '''\
from models import User, Product, OrderStatus
from services import OrderService
from repository import Repository
from utils import format_currency

repo = Repository()
svc = OrderService(repo)
user = User(1, "Alice", "a@b.com")
laptop = Product(1, "Laptop", 999.99, stock=10)
kbd = Product(2, "Keyboard", 79.99, stock=5)

# Create + confirm
order = svc.create_order(user, [(laptop, 2)])
ok, errs = svc.confirm(order)
assert ok, f"Confirm: {errs}"
assert laptop.stock == 8

# Stock validation
big = svc.create_order(user, [(kbd, 10)])
ok2, errs2 = svc.confirm(big)
assert not ok2, "Should fail: 10 > 5 stock"

# Cancel restores stock
pre = laptop.stock
svc.cancel(order)
assert laptop.stock == pre + 2, f"Stock: {laptop.stock} != {pre+2}"

# Currency
assert format_currency(19.99) == "$19.99"
assert format_currency(-5.50) == "-$5.50", f"Neg: {format_currency(-5.50)}"

print("PASSED")
''',
}

experiment = Experiment(
    name="context_efficiency_v2",
    description=(
        "Context efficiency v2: navigation guidance (file map + bug hints) "
        "vs unguided exploration. 4 tasks from 2-file to 6-file projects. "
        "Tests whether compressed context saves exploration turns."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="unguided (no info) vs guided (file map + exact bug descriptions)",
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
            prompt="Fix bugs in tasks/t1/. Run `cd tasks/t1 && python test_converter.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="easy",
            tags=["2-file", "simple"],
        ),
        TaskItem(
            prompt="Fix bugs in tasks/t2/ (check stats.py and formatter.py). Run `cd tasks/t2 && python test_stats.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="medium",
            tags=["3-file", "dual-bug"],
        ),
        TaskItem(
            prompt="Fix bugs in tasks/t3/ (4-file auth system). Run `cd tasks/t3 && python test_auth.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["4-file", "auth", "dual-bug"],
        ),
        TaskItem(
            prompt="Fix bugs in tasks/t4/ (6-file e-commerce). Run `cd tasks/t4 && python test_app.py` to verify. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="very_hard",
            tags=["6-file", "three-bugs"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["context-efficiency", "navigation", "codebase-size", "research"],
)
