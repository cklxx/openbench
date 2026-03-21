"""
Inference-Time Compute Allocation Strategy:
  Plan-First vs Act-First under fixed turn budget.

RESEARCH QUESTION:
Given a fixed turn budget, should an agent front-load analysis/planning
or start acting immediately and iterate? No controlled A/B study exists.

Literature gap:
- Inference-time scaling (2026 hot topic) focuses on *amount* of compute,
  not *allocation strategy* within a fixed budget.
- Self-correction studies show 30% error reduction (Google Research 2025),
  but don't compare plan-first vs act-first as strategies.
- ICLR 2026 Workshop on Recursive Self-Improvement covers refinement loops
  but not the planning-vs-acting tradeoff.

Design:
- Agent A (act_first): System prompt instructs to start coding immediately,
  iterate and fix as you go. Bias toward action.
- Agent B (plan_first): System prompt instructs to spend first turns reading
  and analyzing before any code changes. Bias toward understanding.
- Same model (haiku), same tools, same max_turns=15, same tasks.
- DiffSpec: system_prompt only.

Tasks: 8 multi-step problems requiring both understanding and implementation.
  Mix of debugging (need to find root cause) and building (need design).
  Difficulty: 2 easy, 3 medium, 3 hard.
  All have objective check_fn for automated evaluation.

n=5 for pass@k statistics.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

ACT_FIRST_PROMPT = """\
You are a fast, action-oriented developer. Your strategy:

1. Start writing code or making changes IMMEDIATELY
2. Run tests early and often to get feedback
3. Fix errors as they appear — iterate rapidly
4. Don't overthink — let the test results guide you

Speed is your advantage. The faster you get to a running state, the more
iterations you can fit. Trust your instincts, write code, run it, fix it.
"""

PLAN_FIRST_PROMPT = """\
You are a methodical, analysis-driven developer. Your strategy:

1. FIRST: Read ALL relevant files before making any changes
2. THEN: Identify the root cause or design requirements thoroughly
3. THEN: Form a clear plan of what to change and why
4. ONLY THEN: Implement your changes in one precise pass
5. Finally: Run tests to verify

Understanding is your advantage. The more you understand before acting,
the fewer mistakes you'll make. Read first, think deeply, act once.
"""

# ── Setup files: 8 independent task directories ─────────────────────────

SETUP_FILES = {
    # ── Task 1 (easy): Off-by-one in pagination ──────────────────────────
    "tasks/t1/paginator.py": '''\
def paginate(items, page, per_page=10):
    """Return a page of items (1-indexed) and metadata."""
    total = len(items)
    total_pages = total // per_page + (1 if total % per_page else 0)
    start = page * per_page  # Bug: should be (page-1) * per_page for 1-indexed
    end = start + per_page
    return {
        "items": items[start:end],
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }
''',
    "tasks/t1/test_paginator.py": '''\
from paginator import paginate
items = list(range(1, 26))  # 1..25
# Page 1 should be first 10 items
p1 = paginate(items, page=1, per_page=10)
assert p1["items"] == list(range(1, 11)), f"Page 1 wrong: {p1['items']}"
assert p1["total_pages"] == 3
# Page 2 should be next 10
p2 = paginate(items, page=2, per_page=10)
assert p2["items"] == list(range(11, 21)), f"Page 2 wrong: {p2['items']}"
# Page 3 should be last 5
p3 = paginate(items, page=3, per_page=10)
assert p3["items"] == list(range(21, 26)), f"Page 3 wrong: {p3['items']}"
# Edge: empty page
p4 = paginate(items, page=4, per_page=10)
assert p4["items"] == [], f"Page 4 should be empty: {p4['items']}"
print("test_paginator: PASSED")
''',

    # ── Task 2 (easy): String template engine missing escape ─────────────
    "tasks/t2/template.py": '''\
def render(template, context):
    """Simple {{key}} template renderer.
    Supports {{key}} replacement and {{key|upper}} filter.
    """
    import re
    def replace_match(m):
        expr = m.group(1).strip()
        if '|' in expr:
            key, filt = expr.split('|', 1)
            key = key.strip()
            filt = filt.strip()
            value = context.get(key, '')
            if filt == 'upper':
                return str(value).upper()
            elif filt == 'lower':
                return str(value).lower()
            elif filt == 'title':
                return str(value).title()
            return str(value)
        else:
            return str(context.get(expr, ''))  # Bug: missing keys become empty string, no error
    # Bug: regex doesn't handle nested braces or escaped braces
    result = re.sub(r'\\{\\{(.+?)\\}\\}', replace_match, template)
    return result
''',
    "tasks/t2/test_template.py": '''\
from template import render
# Basic
assert render("Hello {{name}}!", {"name": "World"}) == "Hello World!"
# Filters
assert render("{{name|upper}}", {"name": "alice"}) == "ALICE"
assert render("{{name|lower}}", {"name": "BOB"}) == "bob"
assert render("{{name|title}}", {"name": "hello world"}) == "Hello World"
# Multiple replacements
assert render("{{a}} + {{b}} = {{c}}", {"a": "1", "b": "2", "c": "3"}) == "1 + 2 = 3"
# Missing key should raise KeyError, not silently return empty
try:
    render("Hello {{missing}}!", {})
    assert False, "Missing key should raise KeyError"
except KeyError:
    pass
# Numeric values
assert render("Count: {{n}}", {"n": 42}) == "Count: 42"
print("test_template: PASSED")
''',

    # ── Task 3 (medium): Event emitter with ordering + once bug ──────────
    "tasks/t3/events.py": '''\
class EventEmitter:
    def __init__(self):
        self._handlers = {}  # event -> [(priority, fn, once)]

    def on(self, event, fn, priority=0):
        """Register handler. Higher priority runs first."""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append((priority, fn, False))

    def once(self, event, fn, priority=0):
        """Register handler that fires only once."""
        if event not in self._handlers:
            self._handlers[event] = []
        self._handlers[event].append((priority, fn, True))

    def emit(self, event, *args, **kwargs):
        """Fire all handlers for event in priority order."""
        if event not in self._handlers:
            return
        # Bug 1: sort is ascending, should be descending for "higher priority first"
        handlers = sorted(self._handlers[event], key=lambda h: h[0])
        for priority, fn, once in handlers:
            fn(*args, **kwargs)
        # Bug 2: removing once-handlers while iterating would fail,
        # but current code doesn't remove them at all
        # Need to filter out once-handlers AFTER calling them
''',
    "tasks/t3/test_events.py": '''\
from events import EventEmitter
# Basic emit
results = []
em = EventEmitter()
em.on("click", lambda: results.append("a"))
em.on("click", lambda: results.append("b"))
em.emit("click")
assert results == ["a", "b"], f"Basic emit: {results}"

# Priority ordering (higher priority first)
order = []
em2 = EventEmitter()
em2.on("load", lambda: order.append("low"), priority=1)
em2.on("load", lambda: order.append("high"), priority=10)
em2.on("load", lambda: order.append("mid"), priority=5)
em2.emit("load")
assert order == ["high", "mid", "low"], f"Priority order wrong: {order}"

# Once handler
count = []
em3 = EventEmitter()
em3.once("save", lambda: count.append(1))
em3.emit("save")
em3.emit("save")
em3.emit("save")
assert len(count) == 1, f"Once fired {len(count)} times instead of 1"

# Once + regular mixed
mixed = []
em4 = EventEmitter()
em4.on("x", lambda: mixed.append("always"))
em4.once("x", lambda: mixed.append("once"))
em4.emit("x")
em4.emit("x")
assert mixed == ["always", "once", "always"], f"Mixed wrong: {mixed}"

print("test_events: PASSED")
''',

    # ── Task 4 (medium): CSV parser with quoted fields bug ───────────────
    "tasks/t4/csv_parser.py": '''\
def parse_csv(text, delimiter=','):
    """Parse CSV text into list of lists. Handles quoted fields."""
    rows = []
    for line in text.strip().split('\\n'):
        row = []
        current = ''
        in_quotes = False
        for char in line:
            if char == '"':
                in_quotes = not in_quotes
            elif char == delimiter and not in_quotes:
                row.append(current)
                current = ''
            else:
                current += char
        row.append(current)
        rows.append(row)
    return rows

def to_dicts(text, delimiter=','):
    """Parse CSV with header row into list of dicts."""
    rows = parse_csv(text, delimiter)
    if not rows:
        return []
    headers = rows[0]
    # Bug: doesn't strip whitespace from headers
    return [{h: row[i] if i < len(row) else '' for i, h in enumerate(headers)}
            for row in rows[1:]]
''',
    "tasks/t4/test_csv.py": '''\
from csv_parser import parse_csv, to_dicts

# Basic parsing
rows = parse_csv("a,b,c\\n1,2,3\\n4,5,6")
assert rows == [["a", "b", "c"], ["1", "2", "3"], ["4", "5", "6"]]

# Quoted fields with commas
rows2 = parse_csv('name,bio\\nAlice,"Loves cats, dogs"\\nBob,"Says ""hi"""')
assert rows2[1][1] == "Loves cats, dogs", f"Quoted comma: {rows2[1][1]}"
# Escaped quotes inside quoted field: ""hi"" should become "hi"
assert rows2[2][1] == 'Says "hi"', f"Escaped quotes: {rows2[2][1]}"

# to_dicts with header whitespace
data = to_dicts(" name , age \\nAlice,30\\nBob,25")
assert data[0]["name"] == "Alice", f"Header whitespace not stripped: {data[0]}"
assert data[1]["age"] == "25"

# Empty fields
rows3 = parse_csv("a,,c\\n1,,3")
assert rows3[0] == ["a", "", "c"]
assert rows3[1] == ["1", "", "3"]

print("test_csv: PASSED")
''',

    # ── Task 5 (medium): Dependency resolver with cycle detection ────────
    "tasks/t5/resolver.py": '''\
def resolve(deps):
    """Resolve dependency order. deps = {name: [dependencies]}.
    Returns list in installation order (dependencies first).
    Raises ValueError on circular dependency.
    """
    resolved = []
    seen = set()

    def _resolve(name, path=None):
        if path is None:
            path = set()
        if name in resolved:
            return
        if name in path:
            # Bug: doesn't include the cycle in error message
            raise ValueError("Circular dependency")
        path.add(name)
        for dep in deps.get(name, []):
            _resolve(dep, path)
        # Bug: doesn't add to 'seen' set — 'seen' is unused
        resolved.append(name)

    for name in deps:
        _resolve(name)
    return resolved
''',
    "tasks/t5/test_resolver.py": '''\
from resolver import resolve

# Simple chain: a -> b -> c
result = resolve({"c": [], "b": ["c"], "a": ["b"]})
assert result.index("c") < result.index("b") < result.index("a"), f"Chain: {result}"

# Diamond: a -> b,c -> d
result2 = resolve({"d": [], "b": ["d"], "c": ["d"], "a": ["b", "c"]})
assert result2.index("d") < result2.index("b")
assert result2.index("d") < result2.index("c")
assert result2.index("b") < result2.index("a")
assert result2.index("c") < result2.index("a")

# No deps
result3 = resolve({"x": [], "y": [], "z": []})
assert set(result3) == {"x", "y", "z"}

# Circular dependency detection
try:
    resolve({"a": ["b"], "b": ["c"], "c": ["a"]})
    assert False, "Should raise ValueError for circular dependency"
except ValueError as e:
    # Error message should contain the cycle
    assert "a" in str(e) and "c" in str(e), f"Cycle not in error: {e}"

# Self-dependency
try:
    resolve({"a": ["a"]})
    assert False, "Self-dep should raise ValueError"
except ValueError:
    pass

print("test_resolver: PASSED")
''',

    # ── Task 6 (hard): State machine with transition guards ──────────────
    "tasks/t6/fsm.py": '''\
"""Finite state machine with guards and actions."""

class StateMachine:
    def __init__(self, initial_state):
        self.state = initial_state
        self.transitions = {}  # (from_state, event) -> [(guard, to_state, action)]
        self.history = [initial_state]

    def add_transition(self, from_state, event, to_state, guard=None, action=None):
        """Add transition. Guard is a callable returning bool. Action is a callable."""
        key = (from_state, event)
        if key not in self.transitions:
            self.transitions[key] = []
        self.transitions[key].append((guard, to_state, action))

    def trigger(self, event, context=None):
        """Trigger event. Returns True if transition occurred."""
        key = (self.state, event)
        if key not in self.transitions:
            return False

        for guard, to_state, action in self.transitions[key]:
            if guard is None or guard(context):
                if action:
                    action(context)
                self.state = to_state
                # Bug: history not updated
                return True
        return False

    def can_trigger(self, event, context=None):
        """Check if event can be triggered without actually triggering."""
        key = (self.state, event)
        if key not in self.transitions:
            return False
        for guard, to_state, action in self.transitions[key]:
            if guard is None or guard(context):
                return True
        return False

    def reset(self):
        """Reset to initial state."""
        # Bug: doesn't know initial state — only has current state
        self.history = [self.state]  # Should reset to history[0]
''',
    "tasks/t6/test_fsm.py": '''\
from fsm import StateMachine

# Simple traffic light
sm = StateMachine("red")
sm.add_transition("red", "next", "green")
sm.add_transition("green", "next", "yellow")
sm.add_transition("yellow", "next", "red")

assert sm.state == "red"
assert sm.trigger("next")
assert sm.state == "green"
assert sm.trigger("next")
assert sm.state == "yellow"
assert sm.trigger("next")
assert sm.state == "red"

# History tracking
assert sm.history == ["red", "green", "yellow", "red"], f"History: {sm.history}"

# Guard-based transitions
sm2 = StateMachine("locked")
sm2.add_transition("locked", "coin", "unlocked", guard=lambda ctx: ctx.get("amount", 0) >= 25)
sm2.add_transition("locked", "coin", "locked")  # Fallback: insufficient coin
sm2.add_transition("unlocked", "push", "locked")

# Insufficient coin
assert sm2.trigger("coin", {"amount": 10}) == True
assert sm2.state == "locked"  # Stayed locked (fell through to fallback)

# Sufficient coin
assert sm2.trigger("coin", {"amount": 25})
assert sm2.state == "unlocked"

# can_trigger
assert sm2.can_trigger("push")
assert not sm2.can_trigger("coin")  # No transition from unlocked on coin

# Reset
sm.reset()
assert sm.state == "red", f"Reset failed: {sm.state}"
assert sm.history == ["red"], f"Reset history: {sm.history}"

print("test_fsm: PASSED")
''',

    # ── Task 7 (hard): Expression evaluator with operator precedence ─────
    "tasks/t7/expr.py": '''\
"""Simple arithmetic expression evaluator.
Supports: +, -, *, /, parentheses, unary minus, variables.
"""

def tokenize(expr):
    """Convert expression string to list of tokens."""
    tokens = []
    i = 0
    while i < len(expr):
        if expr[i].isspace():
            i += 1
        elif expr[i].isdigit() or expr[i] == '.':
            j = i
            while j < len(expr) and (expr[j].isdigit() or expr[j] == '.'):
                j += 1
            tokens.append(('NUM', float(expr[i:j])))
            i = j
        elif expr[i].isalpha():
            j = i
            while j < len(expr) and expr[j].isalnum():
                j += 1
            tokens.append(('VAR', expr[i:j]))
            i = j
        elif expr[i] in '+-*/()':
            tokens.append(('OP', expr[i]))
            i += 1
        else:
            raise SyntaxError(f"Unexpected character: {expr[i]}")
    return tokens

def evaluate(expr, variables=None):
    """Evaluate arithmetic expression string."""
    variables = variables or {}
    tokens = tokenize(expr)
    pos = [0]  # mutable index

    def parse_expr():
        """Handle + and - (lowest precedence)."""
        left = parse_term()
        while pos[0] < len(tokens) and tokens[pos[0]] == ('OP', '+') or \
              pos[0] < len(tokens) and tokens[pos[0]] == ('OP', '-'):
            op = tokens[pos[0]][1]
            pos[0] += 1
            right = parse_term()
            if op == '+':
                left = left + right
            else:
                left = left - right
        return left

    def parse_term():
        """Handle * and / (higher precedence)."""
        left = parse_factor()
        while pos[0] < len(tokens) and tokens[pos[0]] == ('OP', '*') or \
              pos[0] < len(tokens) and tokens[pos[0]] == ('OP', '/'):
            op = tokens[pos[0]][1]
            pos[0] += 1
            right = parse_factor()
            if op == '*':
                left = left * right
            else:
                if right == 0:
                    raise ZeroDivisionError("Division by zero")
                left = left / right
        return left

    def parse_factor():
        """Handle unary minus, numbers, variables, parentheses."""
        if pos[0] >= len(tokens):
            raise SyntaxError("Unexpected end of expression")

        token = tokens[pos[0]]

        # Unary minus
        if token == ('OP', '-'):
            pos[0] += 1
            return -parse_factor()

        # Parenthesized expression
        if token == ('OP', '('):
            pos[0] += 1
            result = parse_expr()
            if pos[0] >= len(tokens) or tokens[pos[0]] != ('OP', ')'):
                raise SyntaxError("Missing closing parenthesis")
            pos[0] += 1
            return result

        # Number
        if token[0] == 'NUM':
            pos[0] += 1
            return token[1]

        # Variable
        if token[0] == 'VAR':
            pos[0] += 1
            name = token[1]
            if name not in variables:
                raise NameError(f"Undefined variable: {name}")
            return variables[name]

        raise SyntaxError(f"Unexpected token: {token}")

    result = parse_expr()
    if pos[0] < len(tokens):
        raise SyntaxError(f"Unexpected token after expression: {tokens[pos[0]]}")
    return result
''',
    "tasks/t7/test_expr.py": '''\
from expr import evaluate

# Basic arithmetic
assert evaluate("2 + 3") == 5
assert evaluate("10 - 3") == 7
assert evaluate("4 * 5") == 20
assert evaluate("15 / 3") == 5.0

# Precedence: * before +
assert evaluate("2 + 3 * 4") == 14, f"Precedence: {evaluate('2 + 3 * 4')}"
assert evaluate("2 * 3 + 4") == 10

# Parentheses override precedence
assert evaluate("(2 + 3) * 4") == 20
assert evaluate("2 * (3 + 4)") == 14

# Unary minus
assert evaluate("-5") == -5
assert evaluate("-5 + 3") == -2
assert evaluate("-(2 + 3)") == -5

# Variables
assert evaluate("x + 1", {"x": 10}) == 11
assert evaluate("x * y + z", {"x": 2, "y": 3, "z": 4}) == 10

# Nested parentheses
assert evaluate("((2 + 3) * (4 - 1))") == 15

# Division by zero
try:
    evaluate("5 / 0")
    assert False, "Should raise ZeroDivisionError"
except ZeroDivisionError:
    pass

# Complex expression
assert evaluate("2 + 3 * 4 - 6 / 2") == 11.0, f"Complex: {evaluate('2 + 3 * 4 - 6 / 2')}"

print("test_expr: PASSED")
''',

    # ── Task 8 (hard): Mini web framework router with path params ────────
    "tasks/t8/router.py": '''\
"""Minimal URL router with path parameters and middleware."""
import re

class Router:
    def __init__(self):
        self.routes = []
        self.middleware = []

    def add_middleware(self, fn):
        """Add middleware function. Called before handler with (request, next)."""
        self.middleware.append(fn)

    def route(self, method, pattern, handler):
        """Register a route. Pattern supports :param syntax.
        e.g., '/users/:id/posts/:post_id'
        """
        # Convert :param to named regex groups
        regex_pattern = re.sub(r':(\w+)', r'(?P<\\1>[^/]+)', pattern)
        regex_pattern = f'^{regex_pattern}$'
        self.routes.append((method.upper(), re.compile(regex_pattern), handler))

    def match(self, method, path):
        """Find matching route. Returns (handler, params) or (None, {})."""
        for route_method, pattern, handler in self.routes:
            if route_method != method.upper():
                continue
            m = pattern.match(path)
            if m:
                return handler, m.groupdict()
        return None, {}

    def handle(self, request):
        """Process request through middleware chain and handler.
        request = {"method": "GET", "path": "/users/123", "headers": {}, "body": None}
        """
        handler, params = self.match(request["method"], request["path"])
        if handler is None:
            return {"status": 404, "body": "Not Found"}

        request["params"] = params

        # Bug: middleware chain is broken — doesn't actually chain them
        # Each middleware should call next() to continue the chain
        for mw in self.middleware:
            result = mw(request)
            if result is not None:
                return result  # Short-circuit

        return handler(request)
''',
    "tasks/t8/test_router.py": '''\
from router import Router

# Basic routing
r = Router()
r.route("GET", "/hello", lambda req: {"status": 200, "body": "Hello!"})
r.route("GET", "/users/:id", lambda req: {"status": 200, "body": f"User {req['params']['id']}"})
r.route("POST", "/users", lambda req: {"status": 201, "body": "Created"})
r.route("GET", "/users/:user_id/posts/:post_id",
        lambda req: {"status": 200, "body": f"User {req['params']['user_id']} Post {req['params']['post_id']}"})

# Test basic match
resp = r.handle({"method": "GET", "path": "/hello", "headers": {}, "body": None})
assert resp["status"] == 200 and resp["body"] == "Hello!"

# Path params
resp2 = r.handle({"method": "GET", "path": "/users/42", "headers": {}, "body": None})
assert resp2["body"] == "User 42", f"Path param: {resp2}"

# Multiple path params
resp3 = r.handle({"method": "GET", "path": "/users/1/posts/99", "headers": {}, "body": None})
assert resp3["body"] == "User 1 Post 99", f"Multi params: {resp3}"

# Method mismatch
resp4 = r.handle({"method": "DELETE", "path": "/hello", "headers": {}, "body": None})
assert resp4["status"] == 404

# 404
resp5 = r.handle({"method": "GET", "path": "/nonexistent", "headers": {}, "body": None})
assert resp5["status"] == 404

# Middleware: auth check
r2 = Router()
call_order = []

def auth_middleware(request):
    call_order.append("auth")
    if not request.get("headers", {}).get("token"):
        return {"status": 401, "body": "Unauthorized"}
    return None  # Continue

def logging_middleware(request):
    call_order.append("log")
    return None  # Continue

r2.add_middleware(logging_middleware)
r2.add_middleware(auth_middleware)
r2.route("GET", "/secret", lambda req: (call_order.append("handler"), {"status": 200, "body": "Secret"})[-1])

# Without token: should hit logging then auth and stop
resp6 = r2.handle({"method": "GET", "path": "/secret", "headers": {}, "body": None})
assert resp6["status"] == 401
assert call_order == ["log", "auth"], f"Middleware order: {call_order}"

# With token: should hit all middleware then handler
call_order.clear()
resp7 = r2.handle({"method": "GET", "path": "/secret", "headers": {"token": "valid"}, "body": None})
assert resp7["status"] == 200
assert call_order == ["log", "auth", "handler"], f"Full chain: {call_order}"

print("test_router: PASSED")
''',
}

experiment = Experiment(
    name="compute_allocation_strategy",
    description=(
        "Inference-time compute allocation: plan-first (read→analyze→act) vs "
        "act-first (code→test→iterate) under fixed 15-turn budget. "
        "Tests whether front-loading analysis beats rapid iteration."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="act-first (iterate fast) vs plan-first (analyze then act once)",
    ),
    agent_a=AgentConfig(
        name="act_first",
        model="claude-haiku-4-5",
        system_prompt=ACT_FIRST_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=15,
    ),
    agent_b=AgentConfig(
        name="plan_first",
        model="claude-haiku-4-5",
        system_prompt=PLAN_FIRST_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=15,
    ),
    tasks=[
        TaskItem(
            prompt="Fix the bug(s) in tasks/t1/. Run the test to verify.",
            expected="PASSED",
            check_fn='"passed" in output.lower()',
            difficulty="easy",
            tags=["off-by-one", "pagination"],
        ),
        TaskItem(
            prompt="Fix the bug(s) in tasks/t2/. Run the test to verify.",
            expected="PASSED",
            check_fn='"passed" in output.lower()',
            difficulty="easy",
            tags=["string-processing", "error-handling"],
        ),
        TaskItem(
            prompt="Fix the bug(s) in tasks/t3/. Run the test to verify.",
            expected="PASSED",
            check_fn='"passed" in output.lower()',
            difficulty="medium",
            tags=["event-system", "multiple-bugs"],
        ),
        TaskItem(
            prompt="Fix the bug(s) in tasks/t4/. Run the test to verify.",
            expected="PASSED",
            check_fn='"passed" in output.lower()',
            difficulty="medium",
            tags=["csv-parsing", "edge-cases"],
        ),
        TaskItem(
            prompt="Fix the bug(s) in tasks/t5/. Run the test to verify.",
            expected="PASSED",
            check_fn='"passed" in output.lower()',
            difficulty="medium",
            tags=["dependency-resolution", "cycle-detection"],
        ),
        TaskItem(
            prompt="Fix the bug(s) in tasks/t6/. Run the test to verify.",
            expected="PASSED",
            check_fn='"passed" in output.lower()',
            difficulty="hard",
            tags=["state-machine", "multiple-bugs"],
        ),
        TaskItem(
            prompt=(
                "The expression evaluator in tasks/t7/ has a subtle operator precedence bug. "
                "Run the test first to see which cases fail, then fix the code. Verify all tests pass."
            ),
            expected="PASSED",
            check_fn='"passed" in output.lower()',
            difficulty="hard",
            tags=["parser", "precedence"],
        ),
        TaskItem(
            prompt=(
                "The router in tasks/t8/ has a broken middleware chain. "
                "The middleware should form a chain where each calls next() to continue, "
                "but the current implementation just runs them sequentially. "
                "Fix the middleware execution so it works as a proper chain. Run the test to verify."
            ),
            expected="PASSED",
            check_fn='"passed" in output.lower()',
            difficulty="hard",
            tags=["middleware", "chain-pattern"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=5,
    tags=["compute-allocation", "inference-time", "plan-vs-act", "research"],
)
