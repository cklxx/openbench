"""
Context Efficiency: Guided Navigation vs Unguided Exploration

RESEARCH QUESTION:
When an agent works in a large codebase, does providing a "context map"
(file descriptions, bug location hints) improve efficiency compared to
letting the agent explore freely? This simulates the effect of trajectory
compression — a compressed trajectory retains key navigation pointers
while discarding verbose intermediate states.

Literature gap:
- AgentDiet achieves 40-60% input token savings via trajectory compression
- But no controlled study compares HOW MUCH guidance to retain
- The question: is a "compressed context" (pointers only) better than
  either full context or no context?

Design:
- Agent A (unguided): No hints. Must explore the codebase to find bugs.
  System prompt just says "fix bugs, run tests."
- Agent B (guided): System prompt includes a "context map" listing each
  file's purpose and which files are likely buggy.
  This simulates a compressed trajectory: key pointers without full content.
- Same model (haiku), tools, max_turns=6
- Tasks: 8-12 file projects where bugs could be anywhere
- The key metric: does guidance save enough exploration turns to enable
  more fix turns?

n=5 per task for pass@k.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

UNGUIDED_PROMPT = """\
You are a developer fixing bugs in a project. The project has multiple files.
Run the tests, find the bugs, fix them. You have very limited turns.
"""

GUIDED_PROMPT = """\
You are a developer fixing bugs in a project. Here is a map of the codebase:

PROJECT STRUCTURE:
- models.py: Data models (User, Product, Order). Likely correct.
- validators.py: Input validation functions. POSSIBLY BUGGY — check carefully.
- services.py: Business logic (OrderService, UserService). POSSIBLY BUGGY.
- repository.py: Data storage layer. Likely correct.
- utils.py: Helper functions (formatting, calculations). POSSIBLY BUGGY.
- test_app.py: Test suite. Treat as ground truth.

GUIDANCE:
- Start by running the test to see what fails
- Focus on files marked "POSSIBLY BUGGY"
- The bugs are in logic, not syntax — code runs but produces wrong results
- You have very limited turns — use the map above to skip exploration
"""

# A realistic 6-file mini-application with bugs scattered across 3 files
SETUP_FILES = {
    "models.py": '''\
"""Data models for the e-commerce system."""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class OrderStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
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
    category: str = "general"

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
        discount = self.subtotal * (self.discount_pct / 100)
        return round(self.subtotal - discount, 2)
''',

    "validators.py": '''\
"""Input validation for orders and users."""

def validate_order(order):
    """Validate order before confirmation. Returns (is_valid, errors)."""
    errors = []

    if not order.items:
        errors.append("Order must have at least one item")

    for item in order.items:
        if item.quantity <= 0:
            errors.append(f"Invalid quantity for {item.product.name}")
        # Bug: checks stock BEFORE quantity, should be quantity > stock
        if item.product.stock < 0:
            errors.append(f"Insufficient stock for {item.product.name}")

    if order.discount_pct < 0 or order.discount_pct > 100:
        errors.append("Discount must be between 0 and 100")

    return len(errors) == 0, errors

def validate_email(email):
    """Basic email validation."""
    if not email or "@" not in email:
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    if not local or not domain or "." not in domain:
        return False
    return True
''',

    "services.py": '''\
"""Business logic services."""
from models import OrderStatus

class OrderService:
    def __init__(self, repository):
        self.repo = repository

    def create_order(self, user, items_with_qty):
        """Create a new order with given items.
        items_with_qty: list of (product, quantity) tuples
        """
        from models import Order
        order_id = self.repo.next_order_id()
        order = Order(id=order_id, user=user)
        for product, qty in items_with_qty:
            order.add_item(product, qty)

        # Apply premium discount
        if user.is_premium:
            order.discount_pct = 10  # 10% for premium users

        return order

    def confirm_order(self, order):
        """Confirm order: validate, deduct stock, save."""
        from validators import validate_order
        is_valid, errors = validate_order(order)
        if not is_valid:
            return False, errors

        # Deduct stock
        for item in order.items:
            item.product.stock -= item.quantity

        order.status = OrderStatus.CONFIRMED
        self.repo.save_order(order)
        return True, []

    def cancel_order(self, order):
        """Cancel order and restore stock."""
        if order.status != OrderStatus.CONFIRMED:
            return False, ["Only confirmed orders can be cancelled"]

        # Bug: restores stock with wrong sign (subtracts instead of adds)
        for item in order.items:
            item.product.stock -= item.quantity

        order.status = OrderStatus.CANCELLED
        self.repo.save_order(order)
        return True, []

class UserService:
    def __init__(self, repository):
        self.repo = repository

    def register(self, name, email):
        """Register a new user."""
        from validators import validate_email
        if not validate_email(email):
            return None, "Invalid email"
        from models import User
        user_id = self.repo.next_user_id()
        user = User(id=user_id, name=name, email=email)
        self.repo.save_user(user)
        return user, None

    def upgrade_to_premium(self, user):
        user.is_premium = True
        self.repo.save_user(user)
''',

    "repository.py": '''\
"""In-memory data storage."""

class Repository:
    def __init__(self):
        self.users = {}
        self.orders = {}
        self._next_user_id = 1
        self._next_order_id = 1

    def next_user_id(self):
        uid = self._next_user_id
        self._next_user_id += 1
        return uid

    def next_order_id(self):
        oid = self._next_order_id
        self._next_order_id += 1
        return oid

    def save_user(self, user):
        self.users[user.id] = user

    def save_order(self, order):
        self.orders[order.id] = order

    def get_user(self, user_id):
        return self.users.get(user_id)

    def get_order(self, order_id):
        return self.orders.get(order_id)

    def get_user_orders(self, user_id):
        return [o for o in self.orders.values() if o.user.id == user_id]
''',

    "utils.py": '''\
"""Utility functions."""

def format_currency(amount):
    """Format amount as currency string."""
    # Bug: negative amounts lose the minus sign
    return f"${abs(amount):.2f}"

def calculate_tax(amount, rate=0.08):
    """Calculate tax on amount."""
    return round(amount * rate, 2)

def generate_receipt(order):
    """Generate text receipt for order."""
    from utils import format_currency, calculate_tax
    lines = [f"Order #{order.id}"]
    lines.append(f"Customer: {order.user.name}")
    lines.append("-" * 30)
    for item in order.items:
        lines.append(f"  {item.product.name} x{item.quantity}: {format_currency(item.subtotal)}")
    lines.append("-" * 30)
    lines.append(f"Subtotal: {format_currency(order.subtotal)}")
    if order.discount_pct > 0:
        lines.append(f"Discount: {order.discount_pct}%")
    tax = calculate_tax(order.total)
    lines.append(f"Tax: {format_currency(tax)}")
    lines.append(f"Total: {format_currency(order.total + tax)}")
    return "\\n".join(lines)
''',

    "test_app.py": '''\
"""Integration tests for the e-commerce system."""
from models import User, Product, Order, OrderStatus
from services import OrderService, UserService
from repository import Repository
from validators import validate_order, validate_email
from utils import format_currency, calculate_tax, generate_receipt

repo = Repository()
order_svc = OrderService(repo)
user_svc = UserService(repo)

# ── User registration ────────────────────────────────────────────
user, err = user_svc.register("Alice", "alice@example.com")
assert user is not None and err is None, f"Registration failed: {err}"
assert user.id == 1

# Invalid email
_, err2 = user_svc.register("Bob", "invalid-email")
assert err2 is not None, "Should reject invalid email"

# ── Product setup ────────────────────────────────────────────────
laptop = Product(1, "Laptop", 999.99, stock=10)
mouse = Product(2, "Mouse", 29.99, stock=50)
keyboard = Product(3, "Keyboard", 79.99, stock=5)

# ── Order creation and confirmation ──────────────────────────────
order = order_svc.create_order(user, [(laptop, 2), (mouse, 3)])
assert order.subtotal == 2 * 999.99 + 3 * 29.99  # 2089.95
assert order.discount_pct == 0  # Not premium

# Confirm order
ok, errs = order_svc.confirm_order(order)
assert ok, f"Confirm failed: {errs}"
assert order.status == OrderStatus.CONFIRMED
assert laptop.stock == 8  # Deducted 2
assert mouse.stock == 47  # Deducted 3

# ── Stock validation ─────────────────────────────────────────────
# Try to order more than available stock
big_order = order_svc.create_order(user, [(keyboard, 10)])  # Only 5 in stock
ok2, errs2 = order_svc.confirm_order(big_order)
assert not ok2, f"Should fail: only 5 keyboards in stock but ordering 10"
assert any("stock" in e.lower() for e in errs2), f"Should mention stock: {errs2}"

# ── Cancellation restores stock ──────────────────────────────────
pre_cancel_laptop = laptop.stock  # 8
ok3, _ = order_svc.cancel_order(order)
assert ok3, "Cancel should succeed"
assert order.status == OrderStatus.CANCELLED
assert laptop.stock == pre_cancel_laptop + 2, \\
    f"Cancel should restore stock: {laptop.stock} != {pre_cancel_laptop + 2}"
assert mouse.stock == 47 + 3, \\
    f"Cancel should restore mouse stock: {mouse.stock} != 50"

# ── Premium discount ─────────────────────────────────────────────
user_svc.upgrade_to_premium(user)
premium_order = order_svc.create_order(user, [(mouse, 2)])
assert premium_order.discount_pct == 10
assert premium_order.total == round(59.98 * 0.9, 2)  # 53.98

# ── Currency formatting ──────────────────────────────────────────
assert format_currency(19.99) == "$19.99"
assert format_currency(0) == "$0.00"
assert format_currency(-5.50) == "-$5.50", f"Negative: {format_currency(-5.50)}"

# ── Tax calculation ──────────────────────────────────────────────
assert calculate_tax(100) == 8.00
assert calculate_tax(53.98) == round(53.98 * 0.08, 2)

# ── Receipt generation ───────────────────────────────────────────
receipt = generate_receipt(premium_order)
assert "Order #" in receipt
assert "Mouse" in receipt
assert "Discount: 10%" in receipt

print("PASSED")
''',
}

experiment = Experiment(
    name="context_efficiency",
    description=(
        "Context efficiency: guided navigation (codebase map + bug hints) "
        "vs unguided exploration in a 6-file project. Tests whether "
        "compressed context pointers save enough exploration turns to "
        "improve fix rate. Simulates trajectory compression."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="unguided (no codebase info) vs guided (file map + bug location hints)",
    ),
    agent_a=AgentConfig(
        name="unguided",
        model="claude-haiku-4-5",
        system_prompt=UNGUIDED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=6,
    ),
    agent_b=AgentConfig(
        name="guided",
        model="claude-haiku-4-5",
        system_prompt=GUIDED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=6,
    ),
    tasks=[
        TaskItem(
            prompt="This project has bugs in multiple files. Run `python test_app.py` to see failures, then fix all bugs to make tests pass. Print the test output.",
            expected="PASSED",
            check_fn='"PASSED" in output',
            difficulty="hard",
            tags=["multi-file", "exploration", "3-bugs"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=10,  # More samples for single task
    tags=["context-efficiency", "trajectory-compression", "navigation", "research"],
)
