"""
Experiment: Multi-File Order Processing System

Build a complete order processing system with:
- State machine (PENDING → CONFIRMED → SHIPPED → DELIVERED, or CANCELLED)
- Inventory management (check stock, decrement on confirm, restore on cancel)
- Payment processing (validate, charge, refund)
- Event log (all state transitions recorded)
- Error handling (invalid transitions, insufficient stock, payment failure)

Multiple files must work together. Requires architectural decisions.
This is significantly harder than single-file tasks.

haiku vs sonnet at max_turns=30, num_samples=2.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    "test_orders.py": '''\
"""Comprehensive test suite for order processing system."""
import sys
sys.path.insert(0, ".")

from orders import OrderSystem

def test_create_order():
    sys = OrderSystem()
    sys.add_product("WIDGET", price=10.00, stock=100)
    order_id = sys.create_order("alice", [("WIDGET", 3)])
    assert order_id is not None
    order = sys.get_order(order_id)
    assert order["status"] == "PENDING"
    assert order["customer"] == "alice"
    assert order["total"] == 30.00
    print("  create_order: OK")

def test_confirm_order():
    sys = OrderSystem()
    sys.add_product("WIDGET", price=10.00, stock=100)
    oid = sys.create_order("bob", [("WIDGET", 5)])
    sys.confirm_order(oid)
    order = sys.get_order(oid)
    assert order["status"] == "CONFIRMED"
    # Stock should be decremented
    assert sys.get_stock("WIDGET") == 95
    print("  confirm_order: OK")

def test_full_lifecycle():
    sys = OrderSystem()
    sys.add_product("A", price=5.00, stock=50)
    oid = sys.create_order("carol", [("A", 2)])
    sys.confirm_order(oid)
    sys.ship_order(oid)
    sys.deliver_order(oid)
    order = sys.get_order(oid)
    assert order["status"] == "DELIVERED"
    print("  full_lifecycle: OK")

def test_cancel_pending():
    sys = OrderSystem()
    sys.add_product("B", price=20.00, stock=10)
    oid = sys.create_order("dave", [("B", 3)])
    sys.cancel_order(oid)
    assert sys.get_order(oid)["status"] == "CANCELLED"
    # Stock should NOT be affected (wasn't confirmed)
    assert sys.get_stock("B") == 10
    print("  cancel_pending: OK")

def test_cancel_confirmed():
    sys = OrderSystem()
    sys.add_product("C", price=15.00, stock=20)
    oid = sys.create_order("eve", [("C", 5)])
    sys.confirm_order(oid)
    assert sys.get_stock("C") == 15  # decremented
    sys.cancel_order(oid)
    assert sys.get_order(oid)["status"] == "CANCELLED"
    assert sys.get_stock("C") == 20  # restored
    print("  cancel_confirmed: OK")

def test_invalid_transition():
    sys = OrderSystem()
    sys.add_product("D", price=10.00, stock=10)
    oid = sys.create_order("frank", [("D", 1)])
    # Can't ship a PENDING order
    try:
        sys.ship_order(oid)
        assert False, "Should raise error"
    except (ValueError, Exception):
        pass
    # Can't deliver a PENDING order
    try:
        sys.deliver_order(oid)
        assert False, "Should raise error"
    except (ValueError, Exception):
        pass
    # Can't cancel a DELIVERED order
    sys.confirm_order(oid)
    sys.ship_order(oid)
    sys.deliver_order(oid)
    try:
        sys.cancel_order(oid)
        assert False, "Should raise error"
    except (ValueError, Exception):
        pass
    print("  invalid_transition: OK")

def test_insufficient_stock():
    sys = OrderSystem()
    sys.add_product("E", price=5.00, stock=3)
    oid = sys.create_order("grace", [("E", 5)])
    try:
        sys.confirm_order(oid)
        assert False, "Should raise error for insufficient stock"
    except (ValueError, Exception):
        pass
    assert sys.get_order(oid)["status"] == "PENDING"  # stays PENDING
    assert sys.get_stock("E") == 3  # stock unchanged
    print("  insufficient_stock: OK")

def test_multi_item_order():
    sys = OrderSystem()
    sys.add_product("X", price=10.00, stock=50)
    sys.add_product("Y", price=25.00, stock=30)
    sys.add_product("Z", price=5.00, stock=100)
    oid = sys.create_order("hank", [("X", 2), ("Y", 1), ("Z", 3)])
    order = sys.get_order(oid)
    assert order["total"] == 10*2 + 25*1 + 5*3  # 60.00
    sys.confirm_order(oid)
    assert sys.get_stock("X") == 48
    assert sys.get_stock("Y") == 29
    assert sys.get_stock("Z") == 97
    print("  multi_item_order: OK")

def test_event_log():
    sys = OrderSystem()
    sys.add_product("F", price=10.00, stock=10)
    oid = sys.create_order("ivan", [("F", 1)])
    sys.confirm_order(oid)
    sys.ship_order(oid)
    log = sys.get_event_log(oid)
    assert len(log) >= 3  # created, confirmed, shipped
    # Each event should have at least: event type and timestamp
    for event in log:
        assert "event" in event or "type" in event or "status" in event
    print("  event_log: OK")

def test_unknown_product():
    sys = OrderSystem()
    try:
        sys.create_order("judy", [("NONEXISTENT", 1)])
        assert False, "Should raise error"
    except (ValueError, KeyError, Exception):
        pass
    print("  unknown_product: OK")

def test_unknown_order():
    sys = OrderSystem()
    try:
        sys.get_order("FAKE_ID")
        assert False, "Should raise error"
    except (ValueError, KeyError, Exception):
        pass
    print("  unknown_order: OK")

def test_concurrent_stock():
    """Two orders competing for limited stock."""
    sys = OrderSystem()
    sys.add_product("RARE", price=100.00, stock=5)
    oid1 = sys.create_order("alice", [("RARE", 3)])
    oid2 = sys.create_order("bob", [("RARE", 3)])
    sys.confirm_order(oid1)  # 5→2
    assert sys.get_stock("RARE") == 2
    try:
        sys.confirm_order(oid2)  # only 2 left, need 3 → fail
        assert False, "Should fail: insufficient stock"
    except (ValueError, Exception):
        pass
    assert sys.get_stock("RARE") == 2  # unchanged
    print("  concurrent_stock: OK")

if __name__ == "__main__":
    passed = 0
    failed = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                func()
                passed += 1
            except Exception as e:
                print(f"  {name}: FAIL - {e}")
                failed += 1
    total = passed + failed
    print(f"\\nResults: {passed}/{total} passed")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"{failed} FAILED")
''',
}

experiment = Experiment(
    name="order_system",
    description=(
        "Build multi-component order processing system: state machine, "
        "inventory, payments, event log. 12 test cases. haiku vs sonnet."
    ),
    diff=DiffSpec(
        field="model",
        description="haiku vs sonnet on multi-component system design",
    ),
    agent_a=AgentConfig(
        name="haiku",
        model="claude-haiku-4-5",
        system_prompt=(
            "Build an order processing system in orders.py. Read test_orders.py first. "
            "Implement OrderSystem class with: create_order, confirm_order, ship_order, "
            "deliver_order, cancel_order, get_order, get_stock, get_event_log, add_product. "
            "State machine: PENDING→CONFIRMED→SHIPPED→DELIVERED (or CANCELLED from PENDING/CONFIRMED). "
            "Run tests to verify."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=30,
    ),
    agent_b=AgentConfig(
        name="sonnet",
        model="claude-sonnet-4-6",
        system_prompt=(
            "Build an order processing system in orders.py. Read test_orders.py first. "
            "Implement OrderSystem class with: create_order, confirm_order, ship_order, "
            "deliver_order, cancel_order, get_order, get_stock, get_event_log, add_product. "
            "State machine: PENDING→CONFIRMED→SHIPPED→DELIVERED (or CANCELLED from PENDING/CONFIRMED). "
            "Run tests to verify."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=30,
    ),
    tasks=[
        TaskItem(
            prompt=(
                "Build a complete order processing system in orders.py.\n"
                "Read test_orders.py for all requirements (12 test cases).\n"
                "Must handle: state machine transitions, inventory management, "
                "multi-item orders, cancellation with stock restore, event logging, "
                "error handling for invalid transitions and insufficient stock.\n"
                "Run test_orders.py to verify all tests pass."
            ),
            expected="ALL TESTS PASSED",
            check_fn='"ALL TESTS PASSED" in output or "all tests passed" in output.lower() or ("12/12" in output)',
            difficulty="very_hard",
            tags=["state-machine", "multi-component", "system-design"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=3,
    tags=["system-design", "multi-file", "complex"],
)
