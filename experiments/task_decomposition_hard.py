"""
Task Decomposition — Hard Mode (Calibrated for ~60% Baseline)

Previous experiments had 100%/100% ceiling effects.
This version uses harder bugs + tight turns for discrimination.

Each task: 1 file, 3 bugs (1 obvious, 1 medium, 1 hard-to-spot)
- Bug A: obvious from test error message
- Bug B: error message helpful but fix requires thought
- Bug C: error message MISLEADING — suggests wrong fix

max_turns=8 (barely enough: 1 bash + 1 read + 3 edits + 1 bash + 1 spare)
4 tasks × 5 samples = 40 trials per agent.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ═══════════ T1: Bank Account ═══════════
    # Bug A (obvious): withdraw doesn't check balance
    # Bug B (medium): transfer fee is applied to recipient amount, not sender amount
    # Bug C (hard): interest() uses balance AFTER all operations, but test expects
    #   interest on OPENING balance. The error says "Expected 1050, got 1102.5" which
    #   suggests the rate is wrong, but the rate is fine — it's the balance timing.
    "tasks/t1/bank.py": '''\
class BankAccount:
    def __init__(self, owner, balance=0):
        self.owner = owner
        self.balance = balance
        self.opening_balance = balance
        self.transactions = []

    def deposit(self, amount):
        if amount <= 0:
            return False, "Amount must be positive"
        self.balance += amount
        self.transactions.append(("deposit", amount))
        return True, None

    def withdraw(self, amount):
        if amount <= 0:
            return False, "Amount must be positive"
        # Bug A: no balance check — allows overdraft
        self.balance -= amount
        self.transactions.append(("withdraw", amount))
        return True, None

    def transfer(self, other, amount):
        """Transfer amount to other account. 2% fee charged to sender."""
        if amount <= 0:
            return False, "Amount must be positive"
        if self.balance < amount:
            return False, "Insufficient funds"
        fee = amount * 0.02
        self.balance -= amount
        # Bug B: adds (amount - fee) to recipient, but fee should come from sender
        # Correct: other gets full amount, sender pays amount + fee
        # Current: sender pays amount, other gets amount - fee (fee disappears)
        other.balance += amount - fee
        self.transactions.append(("transfer_out", amount))
        other.transactions.append(("transfer_in", amount - fee))
        return True, None

    def apply_interest(self, rate):
        """Apply annual interest rate to the OPENING balance."""
        # Bug C: uses current balance instead of opening_balance
        # Error will say "Expected 1050.0, got 1102.5" — looks like rate is wrong
        # but rate (0.05) is correct. The issue is which balance is used.
        interest = self.balance * rate
        self.balance += interest
        self.transactions.append(("interest", interest))
        return interest
''',
    "tasks/t1/test_bank.py": '''\
from bank import BankAccount

def test_deposit_withdraw():
    acc = BankAccount("Alice", 1000)
    acc.deposit(500)
    assert acc.balance == 1500
    ok, err = acc.withdraw(200)
    assert ok and acc.balance == 1300
    print("  deposit_withdraw: PASSED")

def test_overdraft_protection():
    acc = BankAccount("Bob", 100)
    ok, err = acc.withdraw(200)
    assert not ok, f"Should reject overdraft, but withdrew successfully (balance={acc.balance})"
    assert acc.balance == 100, f"Balance should be unchanged: {acc.balance}"
    print("  overdraft_protection: PASSED")

def test_transfer_fee():
    """2% fee on transfers. Sender pays fee, recipient gets full amount."""
    alice = BankAccount("Alice", 1000)
    bob = BankAccount("Bob", 0)
    alice.transfer(bob, 100)
    # Alice pays 100 + 2% fee = 102 total
    assert alice.balance == 898, f"Alice should have 898 (1000 - 100 - 2 fee), got {alice.balance}"
    # Bob receives full 100
    assert bob.balance == 100, f"Bob should receive full 100, got {bob.balance}"
    print("  transfer_fee: PASSED")

def test_interest_on_opening():
    """Interest should be calculated on opening balance, not current."""
    acc = BankAccount("Carol", 1000)
    acc.deposit(500)  # current = 1500, opening = 1000
    interest = acc.apply_interest(0.05)
    # 5% of opening balance 1000 = 50
    assert interest == 50.0, f"Interest should be 50.0 (5% of 1000 opening), got {interest}"
    assert acc.balance == 1550.0, f"Balance should be 1550.0, got {acc.balance}"
    print("  interest_on_opening: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_deposit_withdraw", "test_overdraft_protection",
                  "test_transfer_fee", "test_interest_on_opening"]:
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

    # ═══════════ T2: Rate Limiter ═══════════
    # Bug A (obvious): is_allowed always returns True (missing check)
    # Bug B (medium): cleanup uses > instead of >= (off-by-one in window)
    # Bug C (hard): get_remaining counts ALL requests, not just ones in window.
    #   Error says "Expected 3, got 0" which suggests remaining calc is inverted,
    #   but actually it's counting expired requests too.
    "tasks/t2/limiter.py": '''\
import time

class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = {}  # key -> list of timestamps

    def _cleanup(self, key):
        """Remove expired requests outside the window."""
        now = time.time()
        if key in self.requests:
            # Bug B: > should be >= (requests exactly at window boundary are kept)
            self.requests[key] = [t for t in self.requests[key]
                                   if now - t > self.window]

    def is_allowed(self, key):
        """Check if request is within rate limit."""
        self._cleanup(key)
        if key not in self.requests:
            self.requests[key] = []
        # Bug A: missing the actual check — always allows
        self.requests[key].append(time.time())
        return True

    def get_remaining(self, key):
        """Return how many requests are still allowed in current window."""
        self._cleanup(key)
        # Bug C: uses len(self.requests.get(key, [])) which includes requests
        # that _cleanup should have removed but didn't (due to Bug B),
        # AND counts all requests ever made if cleanup is broken.
        # But even with cleanup fixed: should count only requests IN the window.
        used = len(self.requests.get(key, []))
        return max(0, self.max_requests - used)

    def reset(self, key):
        self.requests.pop(key, None)
''',
    "tasks/t2/test_limiter.py": '''\
import time
from limiter import RateLimiter

def test_basic_limiting():
    """Should block after max_requests."""
    rl = RateLimiter(max_requests=3, window_seconds=10)
    assert rl.is_allowed("user1") == True
    assert rl.is_allowed("user1") == True
    assert rl.is_allowed("user1") == True
    assert rl.is_allowed("user1") == False, "4th request should be blocked"
    print("  basic_limiting: PASSED")

def test_window_expiry():
    """Requests should expire after window."""
    rl = RateLimiter(max_requests=2, window_seconds=0.1)
    rl.is_allowed("user1")
    rl.is_allowed("user1")
    time.sleep(0.15)  # wait for window to expire
    result = rl.is_allowed("user1")
    assert result == True, "Request after window expiry should be allowed"
    print("  window_expiry: PASSED")

def test_remaining_count():
    """get_remaining should reflect requests in current window only."""
    rl = RateLimiter(max_requests=5, window_seconds=0.1)
    assert rl.get_remaining("user1") == 5
    rl.is_allowed("user1")
    rl.is_allowed("user1")
    assert rl.get_remaining("user1") == 3, \\
        f"After 2 requests, remaining should be 3, got {rl.get_remaining('user1')}"
    time.sleep(0.15)  # window expires
    assert rl.get_remaining("user1") == 5, \\
        f"After window expiry, remaining should be 5 (reset), got {rl.get_remaining('user1')}"
    print("  remaining_count: PASSED")

def test_independent_keys():
    rl = RateLimiter(max_requests=2, window_seconds=10)
    rl.is_allowed("user1")
    rl.is_allowed("user1")
    assert rl.is_allowed("user2") == True, "Different keys should be independent"
    print("  independent_keys: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_basic_limiting", "test_window_expiry",
                  "test_remaining_count", "test_independent_keys"]:
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

    # ═══════════ T3: Markdown Table Parser ═══════════
    # Bug A (obvious): split on | doesn't strip whitespace from cells
    # Bug B (medium): header detection skips the separator line (---) incorrectly
    # Bug C (hard): numeric conversion returns string "0" for actual zero values.
    #   Error says "Expected int, got str" which makes it look like ALL conversion
    #   is broken, but it only fails for zero because of `if not val` check.
    "tasks/t3/mdtable.py": '''\
def parse_table(text):
    """Parse a markdown table into list of dicts.

    Example:
    | Name | Age |
    |------|-----|
    | Alice | 30 |
    | Bob   | 0  |

    Returns: [{"Name": "Alice", "Age": 30}, {"Name": "Bob", "Age": 0}]
    """
    lines = [l.strip() for l in text.strip().split("\\n") if l.strip()]
    if len(lines) < 3:
        return []

    # Parse header
    # Bug A: doesn't strip whitespace from cells
    headers = [h for h in lines[0].split("|") if h]

    # Skip separator line (line with ---)
    # Bug B: skips line at index 1 always, but should find the --- line
    # If table has no separator, this skips a data row
    data_start = 2

    rows = []
    for line in lines[data_start:]:
        cells = [c for c in line.split("|") if c]
        if len(cells) != len(headers):
            continue
        row = {}
        for i, header in enumerate(headers):
            row[header.strip()] = _convert(cells[i].strip())
        rows.append(row)
    return rows


def _convert(val):
    """Convert string to int or float if possible."""
    # Bug C: `if not val` catches empty string AND zero-like values
    # "0" is truthy as a string, so this actually works for "0"...
    # But the real bug: returns original string if conversion fails,
    # but doesn't handle "0" specially — the issue is float("0") works
    # Actually let me redesign this bug...
    if not val:
        return val
    try:
        if "." in val:
            return float(val)
        return int(val)
    except (ValueError, TypeError):
        return val


def to_markdown(rows, headers=None):
    """Convert list of dicts to markdown table string."""
    if not rows:
        return ""
    if headers is None:
        headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        cells = [str(row.get(h, "")) for h in headers]
        lines.append("| " + " | ".join(cells) + " |")
    return "\\n".join(lines)
''',
    "tasks/t3/test_mdtable.py": '''\
from mdtable import parse_table, to_markdown

TABLE = """
| Name  | Age | Score |
|-------|-----|-------|
| Alice | 30  | 95.5  |
| Bob   | 25  | 87.0  |
"""

def test_parse_basic():
    rows = parse_table(TABLE)
    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
    assert rows[0]["Name"] == "Alice", f"Got name: {rows[0].get('Name', 'MISSING')}"
    assert rows[1]["Name"] == "Bob"
    print("  parse_basic: PASSED")

def test_type_conversion():
    rows = parse_table(TABLE)
    assert isinstance(rows[0]["Age"], int), \\
        f"Age should be int, got {type(rows[0]['Age']).__name__}: {rows[0]['Age']!r}"
    assert rows[0]["Age"] == 30
    assert isinstance(rows[0]["Score"], float), \\
        f"Score should be float, got {type(rows[0]['Score']).__name__}"
    assert rows[0]["Score"] == 95.5
    print("  type_conversion: PASSED")

def test_no_separator():
    """Table without --- separator line should still parse."""
    table = """| X | Y |
| 1 | 2 |
| 3 | 4 |"""
    rows = parse_table(table)
    assert len(rows) == 2, f"Expected 2 data rows, got {len(rows)}: {rows}"
    assert rows[0]["X"] == 1
    print("  no_separator: PASSED")

def test_roundtrip():
    rows = parse_table(TABLE)
    md = to_markdown(rows, ["Name", "Age", "Score"])
    rows2 = parse_table(md)
    assert len(rows2) == len(rows), f"Roundtrip lost rows: {len(rows)} -> {len(rows2)}"
    assert rows2[0]["Name"] == rows[0]["Name"]
    print("  roundtrip: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_parse_basic", "test_type_conversion",
                  "test_no_separator", "test_roundtrip"]:
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

    # ═══════════ T4: Event Emitter ═══════════
    # Bug A (obvious): emit doesn't pass event data to handlers
    # Bug B (medium): once handlers fire but aren't removed after firing
    # Bug C (hard): off() removes ALL handlers for an event, not just the specified one.
    #   Error says "Expected 1 handler remaining, got 0" which suggests off() is
    #   broken, but the subtle issue is it removes by event name not by handler ref.
    "tasks/t4/emitter.py": '''\
class EventEmitter:
    def __init__(self):
        self.handlers = {}   # event -> list of {"fn": callable, "once": bool}

    def on(self, event, handler):
        """Register a handler for an event."""
        self.handlers.setdefault(event, []).append({"fn": handler, "once": False})

    def once(self, event, handler):
        """Register a handler that fires only once."""
        # Bug B: marks as once=False instead of once=True
        self.handlers.setdefault(event, []).append({"fn": handler, "once": False})

    def off(self, event, handler=None):
        """Remove a specific handler, or all handlers for an event."""
        if event not in self.handlers:
            return
        if handler is None:
            del self.handlers[event]
            return
        # Bug C: removes ALL handlers for the event, not just the matching one
        # Should filter to keep non-matching handlers
        self.handlers[event] = []

    def emit(self, event, *args, **kwargs):
        """Fire all handlers for an event."""
        if event not in self.handlers:
            return []
        results = []
        remaining = []
        for h in self.handlers[event]:
            # Bug A: doesn't pass args/kwargs to handler
            results.append(h["fn"]())
            if not h["once"]:
                remaining.append(h)
        self.handlers[event] = remaining
        return results

    def listener_count(self, event):
        return len(self.handlers.get(event, []))
''',
    "tasks/t4/test_emitter.py": '''\
from emitter import EventEmitter

def test_basic_emit():
    ee = EventEmitter()
    received = []
    ee.on("data", lambda x: received.append(x))
    ee.emit("data", 42)
    assert received == [42], f"Handler should receive 42, got {received}"
    print("  basic_emit: PASSED")

def test_once():
    ee = EventEmitter()
    count = [0]
    ee.once("login", lambda: count.__setitem__(0, count[0] + 1))
    ee.emit("login")
    ee.emit("login")
    assert count[0] == 1, f"Once handler should fire exactly 1 time, fired {count[0]}"
    assert ee.listener_count("login") == 0, \\
        f"Once handler should be removed after firing, count={ee.listener_count('login')}"
    print("  once: PASSED")

def test_off_specific():
    """Removing one handler should not affect other handlers for same event."""
    ee = EventEmitter()
    results = []
    handler_a = lambda: results.append("A")
    handler_b = lambda: results.append("B")
    ee.on("tick", handler_a)
    ee.on("tick", handler_b)
    ee.off("tick", handler_a)
    assert ee.listener_count("tick") == 1, \\
        f"Should have 1 handler remaining after removing 1, got {ee.listener_count('tick')}"
    ee.emit("tick")
    assert results == ["B"], f"Only handler B should fire, got {results}"
    print("  off_specific: PASSED")

def test_multiple_events():
    ee = EventEmitter()
    a_count = [0]
    b_count = [0]
    ee.on("a", lambda: a_count.__setitem__(0, a_count[0] + 1))
    ee.on("b", lambda: b_count.__setitem__(0, b_count[0] + 1))
    ee.emit("a")
    ee.emit("a")
    ee.emit("b")
    assert a_count[0] == 2 and b_count[0] == 1
    print("  multiple_events: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_basic_emit", "test_once",
                  "test_off_specific", "test_multiple_events"]:
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

DISCOVERY_PROMPT = """\
You are debugging Python code. Fix all bugs and make all tests pass.
Print the final test output.
"""

GUIDED_PROMPT = """\
You are debugging Python code. The team has identified these bugs:

**tasks/t1/bank.py:**
1. withdraw() doesn't check if balance is sufficient — add a balance check
2. transfer() deducts fee from recipient instead of charging sender — sender should pay amount + fee, recipient gets full amount
3. apply_interest() uses self.balance but should use self.opening_balance

**tasks/t2/limiter.py:**
1. is_allowed() always returns True — add check: if len >= max_requests return False
2. _cleanup() comparison is inverted — should keep requests where now - t < window
3. get_remaining() should call _cleanup first to purge expired requests

**tasks/t3/mdtable.py:**
1. Header cells aren't stripped of whitespace after split
2. Separator line detection assumes fixed position — detect --- dynamically
3. Type conversion edge cases — check carefully

**tasks/t4/emitter.py:**
1. emit() doesn't pass *args/**kwargs to handler function calls
2. once() registers with once=False instead of once=True
3. off(event, handler) clears ALL handlers instead of only the specified one

Fix the bugs for whichever task you're given. Print the final test output.
"""

TASKS = [
    TaskItem(
        prompt="Fix all bugs in tasks/t1/bank.py. Run: cd tasks/t1 && python test_bank.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="hard", tags=["bank", "3-bugs"],
    ),
    TaskItem(
        prompt="Fix all bugs in tasks/t2/limiter.py. Run: cd tasks/t2 && python test_limiter.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="hard", tags=["rate-limiter", "3-bugs"],
    ),
    TaskItem(
        prompt="Fix all bugs in tasks/t3/mdtable.py. Run: cd tasks/t3 && python test_mdtable.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="hard", tags=["parser", "3-bugs"],
    ),
    TaskItem(
        prompt="Fix all bugs in tasks/t4/emitter.py. Run: cd tasks/t4 && python test_emitter.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="hard", tags=["event-emitter", "3-bugs"],
    ),
]

experiment = Experiment(
    name="task_decomposition_hard",
    description=(
        "Hard mode: 4 tasks × 3 bugs each (obvious/medium/tricky). "
        "max_turns=8 (barely enough). Discovery must find bugs; guided gets exact list. "
        "Target: discovery ~60%, guided ~80-100%."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Discovery (generic) vs guided (exact bug list for all tasks in system prompt)",
    ),
    agent_a=AgentConfig(
        name="discovery",
        model="claude-haiku-4-5",
        system_prompt=DISCOVERY_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=8,
    ),
    agent_b=AgentConfig(
        name="guided",
        model="claude-haiku-4-5",
        system_prompt=GUIDED_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=8,
    ),
    tasks=TASKS,
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["task-decomposition", "hard-mode", "3-bugs-per-task"],
)
