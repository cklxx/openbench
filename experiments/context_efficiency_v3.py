"""
Context Efficiency v3 — Extreme Turn Pressure on Large Codebase

v2 finding: guided +14% overall, but only meaningful on larger codebases.
Small codebases (2-3 files) — model explores efficiently on its own.

v3 approach:
- Only use large codebases (6+ files) where exploration is expensive
- max_turns=4 (extreme pressure — every wasted turn is fatal)
- More samples (n=10) for statistical power
- Multiple 6-file tasks to test reproducibility

Hypothesis: at max_turns=4 with 6-file projects, guidance should save
1-2 exploration turns → convert to edit turns → higher success rate.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

UNGUIDED_PROMPT = """\
Fix the bugs. Run the test, find what's wrong, fix it.
You have extremely limited turns — be very efficient.
"""

GUIDED_T1 = """\
CODEBASE MAP for tasks/t1/:
- validators.py line ~8: stock check is `stock < 0` but should be `quantity > stock`
- services.py line ~37: cancel_order does `stock -= qty` but should `+= qty`
- utils.py line ~3: format_currency uses abs() losing negative sign
- models.py, repository.py: NO BUGS
- test_app.py: ground truth

Go directly to the 3 buggy files, fix them, run test once.
"""

GUIDED_T2 = """\
CODEBASE MAP for tasks/t2/:
- auth.py line ~12: stores hash as .upper() but verify compares lowercase
- session.py line ~18: validate() has condition inverted (> should be <)
- hasher.py, test_auth.py: NO BUGS

Go directly to auth.py and session.py, fix both, run test once.
"""

GUIDED_T3 = """\
CODEBASE MAP for tasks/t3/:
- engine.py line ~15: apply_tax called with wrong argument order (rate, amount instead of amount, rate)
- inventory.py line ~20: restock() adds to wrong field (reserved instead of available)
- shipping.py line ~10: calculate_shipping uses weight threshold backwards (> should be <)
- models.py, test_warehouse.py: NO BUGS

Fix the 3 bugs, run test once.
"""

SETUP_FILES = {
    # ── Task 1: E-commerce (6 files, 3 bugs) ────────────────────────────
    "tasks/t1/models.py": '''\
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
    def add_item(self, p, q):
        self.items.append(OrderItem(p, q))
    @property
    def subtotal(self):
        return sum(i.subtotal for i in self.items)
    @property
    def total(self):
        return round(self.subtotal * (1 - self.discount_pct/100), 2)
''',
    "tasks/t1/repository.py": '''\
class Repository:
    def __init__(self):
        self.orders = {}
        self._oid = 1
    def next_id(self):
        oid = self._oid; self._oid += 1; return oid
    def save(self, order):
        self.orders[order.id] = order
''',
    "tasks/t1/validators.py": '''\
def validate_order(order):
    errors = []
    if not order.items:
        errors.append("Empty order")
    for item in order.items:
        if item.quantity <= 0:
            errors.append(f"Bad qty: {item.product.name}")
        if item.product.stock < 0:  # Bug: should be item.quantity > item.product.stock
            errors.append(f"No stock: {item.product.name}")
    return len(errors) == 0, errors
''',
    "tasks/t1/services.py": '''\
from models import OrderStatus, Order
from validators import validate_order

class OrderService:
    def __init__(self, repo):
        self.repo = repo
    def create(self, user, items):
        order = Order(id=self.repo.next_id(), user=user)
        for p, q in items:
            order.add_item(p, q)
        if user.is_premium:
            order.discount_pct = 10
        return order
    def confirm(self, order):
        ok, errs = validate_order(order)
        if not ok:
            return False, errs
        for i in order.items:
            i.product.stock -= i.quantity
        order.status = OrderStatus.CONFIRMED
        self.repo.save(order)
        return True, []
    def cancel(self, order):
        if order.status != OrderStatus.CONFIRMED:
            return False, ["Not confirmed"]
        for i in order.items:
            i.product.stock -= i.quantity  # Bug: -= should be +=
        order.status = OrderStatus.CANCELLED
        self.repo.save(order)
        return True, []
''',
    "tasks/t1/utils.py": '''\
def format_currency(amount):
    return f"${abs(amount):.2f}"  # Bug: abs() loses negative sign

def calculate_tax(amount, rate=0.08):
    return round(amount * rate, 2)
''',
    "tasks/t1/test_app.py": '''\
from models import User, Product, OrderStatus
from services import OrderService
from repository import Repository
from utils import format_currency

repo = Repository()
svc = OrderService(repo)
user = User(1, "Alice")
laptop = Product(1, "Laptop", 999.99, stock=10)
kbd = Product(2, "Kbd", 79.99, stock=5)

order = svc.create(user, [(laptop, 2)])
ok, e = svc.confirm(order)
assert ok, f"Confirm: {e}"
assert laptop.stock == 8

big = svc.create(user, [(kbd, 10)])
ok2, e2 = svc.confirm(big)
assert not ok2, "Should fail: 10 > 5 stock"

pre = laptop.stock
svc.cancel(order)
assert laptop.stock == pre + 2, f"Stock: {laptop.stock} != {pre+2}"

assert format_currency(-5.50) == "-$5.50", f"Neg: {format_currency(-5.50)}"
print("PASSED")
''',

    # ── Task 2: Auth system (4 files, 2 bugs) ───────────────────────────
    "tasks/t2/hasher.py": '''\
import hashlib
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()
def verify_pw(pw, hashed):
    return hash_pw(pw) == hashed
''',
    "tasks/t2/auth.py": '''\
from hasher import hash_pw, verify_pw

class AuthService:
    def __init__(self):
        self.users = {}
    def register(self, user, pw):
        if user in self.users:
            return False
        self.users[user] = hash_pw(pw).upper()  # Bug: .upper() breaks verify
        return True
    def login(self, user, pw):
        if user not in self.users:
            return False
        return verify_pw(pw, self.users[user])
''',
    "tasks/t2/session.py": '''\
class SessionMgr:
    def __init__(self, ttl=3600):
        self.sessions = {}
        self.ttl = ttl
    def create(self, user, now=0):
        token = f"s_{user}_{now}"
        self.sessions[token] = (user, now + self.ttl)
        return token
    def validate(self, token, now=0):
        if token not in self.sessions:
            return None
        user, exp = self.sessions[token]
        if now > exp:  # Bug: returns user for expired, None for valid
            return user
        return None
''',
    "tasks/t2/test_auth.py": '''\
from auth import AuthService
from session import SessionMgr

auth = AuthService()
assert auth.register("alice", "pass123")
assert auth.login("alice", "pass123"), "Login should work"
assert not auth.login("alice", "wrong")

sm = SessionMgr(ttl=100)
tok = sm.create("alice", now=0)
assert sm.validate(tok, now=50) == "alice", f"Valid session: {sm.validate(tok, now=50)}"
assert sm.validate(tok, now=200) is None, "Expired should be None"

print("PASSED")
''',

    # ── Task 3: Warehouse system (6 files, 3 bugs) ──────────────────────
    "tasks/t3/models.py": '''\
from dataclasses import dataclass

@dataclass
class Item:
    sku: str
    name: str
    weight: float  # kg
    available: int = 0
    reserved: int = 0

@dataclass
class Shipment:
    items: list
    destination: str
    total_weight: float = 0.0
    shipping_cost: float = 0.0
    tax: float = 0.0
''',
    "tasks/t3/inventory.py": '''\
class InventoryManager:
    def __init__(self):
        self.items = {}
    def add_item(self, item):
        self.items[item.sku] = item
    def check_stock(self, sku, qty):
        item = self.items.get(sku)
        if not item:
            return False
        return item.available >= qty
    def reserve(self, sku, qty):
        item = self.items[sku]
        if item.available < qty:
            return False
        item.available -= qty
        item.reserved += qty
        return True
    def restock(self, sku, qty):
        item = self.items[sku]
        item.reserved += qty  # Bug: should be item.available += qty
''',
    "tasks/t3/shipping.py": '''\
def calculate_shipping(items, destination):
    total_weight = sum(i.weight * (i.reserved if hasattr(i, "reserved") else 1) for i in items)
    # Base rate
    if destination == "domestic":
        if total_weight > 10:  # Bug: > should be < (light packages cost less)
            rate = 5.0  # light
        else:
            rate = 5.0 + (total_weight - 10) * 1.5  # heavy
    else:
        rate = 15.0 + total_weight * 2.0
    return round(rate, 2), round(total_weight, 2)
''',
    "tasks/t3/engine.py": '''\
def apply_tax(amount, rate=0.08):
    return round(amount * rate, 2)

def process_shipment(inventory, items_qty, destination):
    from models import Shipment
    reserved_items = []
    for sku, qty in items_qty:
        if not inventory.reserve(sku, qty):
            return None, f"Cannot reserve {qty} of {sku}"
        reserved_items.append(inventory.items[sku])

    from shipping import calculate_shipping
    cost, weight = calculate_shipping(reserved_items, destination)

    # Bug: arguments in wrong order (should be apply_tax(cost, 0.08))
    tax = apply_tax(0.08, cost)

    return Shipment(
        items=reserved_items,
        destination=destination,
        total_weight=weight,
        shipping_cost=cost,
        tax=tax,
    ), None
''',
    "tasks/t3/test_warehouse.py": '''\
from models import Item
from inventory import InventoryManager
from engine import process_shipment, apply_tax

inv = InventoryManager()
inv.add_item(Item("A1", "Widget", weight=2.0, available=100))
inv.add_item(Item("B2", "Gadget", weight=5.0, available=50))

# Reserve and ship
shipment, err = process_shipment(inv, [("A1", 3), ("B2", 2)], "domestic")
assert err is None, f"Error: {err}"
assert shipment is not None

# Weight: 3*2 + 2*5 = 16kg
assert shipment.total_weight == 16.0, f"Weight: {shipment.total_weight}"

# Shipping: heavy (>10kg) = 5 + (16-10)*1.5 = 14.0
assert shipment.shipping_cost == 14.0, f"Shipping: {shipment.shipping_cost}"

# Tax on shipping cost
expected_tax = round(14.0 * 0.08, 2)
assert shipment.tax == expected_tax, f"Tax: {shipment.tax} != {expected_tax}"

# Restock
inv.restock("A1", 10)
assert inv.items["A1"].available == 107, f"Restock: {inv.items['A1'].available}"

# Stock check after reserve
assert inv.items["A1"].available == 107  # was 100, -3 reserved, +10 restocked
assert inv.items["A1"].reserved == 3

print("PASSED")
''',
}

experiment = Experiment(
    name="context_efficiency_v3",
    description=(
        "Context efficiency v3: extreme turn pressure (max_turns=4) on "
        "large codebases (4-6 files). Guided agent gets exact file+line "
        "bug descriptions. Tests navigation guidance value when "
        "exploration budget is near-zero."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="unguided (no codebase info) vs guided (exact file+line bug locations per task)",
    ),
    agent_a=AgentConfig(
        name="unguided",
        model="claude-haiku-4-5",
        system_prompt=UNGUIDED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=4,
    ),
    agent_b=AgentConfig(
        name="guided",
        model="claude-haiku-4-5",
        system_prompt=None,  # Will be set per-task via task prompt
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=4,
    ),
    tasks=[
        TaskItem(
            prompt="Fix all bugs in tasks/t1/ (6-file e-commerce). Run `cd tasks/t1 && python test_app.py`. Print test output.\n\n" + GUIDED_T1,
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["6-file", "3-bugs"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t2/ (4-file auth). Run `cd tasks/t2 && python test_auth.py`. Print test output.\n\n" + GUIDED_T2,
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["4-file", "2-bugs"],
        ),
        TaskItem(
            prompt="Fix all bugs in tasks/t3/ (6-file warehouse). Run `cd tasks/t3 && python test_warehouse.py`. Print test output.\n\n" + GUIDED_T3,
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["6-file", "3-bugs"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=10,
    tags=["context-efficiency", "extreme-pressure", "navigation", "research"],
)

# Override: agent_a gets plain prompt, agent_b gets guided prompt embedded in task
# But since DiffSpec requires system_prompt diff, restructure:
# Actually both agents get the SAME task prompt (with guidance).
# The diff is: agent_a's system prompt says "ignore the codebase map"
# No — cleaner: put guidance ONLY in agent_b's system prompt.

# Restructure: use different system prompts, same task prompts
experiment.agent_b.system_prompt = (
    "You have navigation guidance for each task. "
    "Use the CODEBASE MAP in the task description to go directly to buggy files. "
    "Do NOT waste turns exploring — fix bugs and test."
)

# Plain task prompts without guidance for agent_a
experiment.tasks = [
    TaskItem(
        prompt="Fix all bugs in tasks/t1/ (6-file e-commerce). Run `cd tasks/t1 && python test_app.py`. Print test output.",
        expected="PASSED",
        check_fn='"PASSED" in output',
        difficulty="hard",
        tags=["6-file", "3-bugs"],
    ),
    TaskItem(
        prompt="Fix all bugs in tasks/t2/ (4-file auth). Run `cd tasks/t2 && python test_auth.py`. Print test output.",
        expected="PASSED",
        check_fn='"PASSED" in output',
        difficulty="hard",
        tags=["4-file", "2-bugs"],
    ),
    TaskItem(
        prompt="Fix all bugs in tasks/t3/ (6-file warehouse). Run `cd tasks/t3 && python test_warehouse.py`. Print test output.",
        expected="PASSED",
        check_fn='"PASSED" in output',
        difficulty="hard",
        tags=["6-file", "3-bugs"],
    ),
]

# Put all guidance in agent_b's system prompt
experiment.agent_b.system_prompt = f"""\
You have exact bug locations for each task. Use them to skip exploration:

{GUIDED_T1}

{GUIDED_T2}

{GUIDED_T3}

Go directly to the buggy files listed above. Fix them. Run test once. Done.
You have extremely limited turns — do NOT explore or read files not listed.
"""
