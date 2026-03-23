"""
Real Model Selection v2: Genuinely Hard Tasks

v1 tasks were too easy (97-100% for both models). No differentiation.

v2 uses tasks that challenge MODEL REASONING, not turn budgets:
- T1: Regex edge cases (LLMs notoriously bad at regex)
- T2: Floating point precision (IEEE 754 gotchas)
- T3: Closure variable capture in loops (classic Python gotcha)
- T4: Bit manipulation codec (proven hard from earlier experiments)

These are tasks where the BUG is hard to understand, not hard to find.
Both models get 15 turns. Target: Haiku ~50-70%, Sonnet ~70-90%.

4 tasks × 8 samples, max_turns=15.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ═══════ T1: Regex URL Validator — regex is hard for LLMs ═══════
    "tasks/t1/urlparse.py": '''\
import re

def is_valid_url(url):
    """Validate URL format. Must have scheme, host, optional port/path/query."""
    # Bug: regex doesn't handle URLs with port numbers correctly
    # e.g., http://localhost:8080/path should be valid
    pattern = r"^https?://[a-zA-Z0-9.-]+(/[a-zA-Z0-9._~:/?#@!$&\'()*+,;=-]*)?$"
    return bool(re.match(pattern, url))

def extract_domain(url):
    """Extract domain from URL, stripping www. prefix."""
    # Bug: greedy match captures port as part of domain
    match = re.match(r"^https?://(www\\.)?([^/]+)", url)
    if not match:
        return None
    domain = match.group(2)
    return domain

def extract_query_params(url):
    """Extract query parameters as dict from URL."""
    match = re.search(r"\\?(.+?)(?:#|$)", url)
    if not match:
        return {}
    params = {}
    for pair in match.group(1).split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            params[key] = value
    return params
''',
    "tasks/t1/test_urlparse.py": '''\
from urlparse import is_valid_url, extract_domain, extract_query_params

def test_valid_urls():
    assert is_valid_url("http://example.com")
    assert is_valid_url("https://example.com/path")
    assert is_valid_url("https://example.com/path?q=1")
    print("  valid_urls: PASSED")

def test_url_with_port():
    assert is_valid_url("http://localhost:8080"), "URL with port should be valid"
    assert is_valid_url("https://api.example.com:443/v1"), "URL with port+path should be valid"
    print("  url_with_port: PASSED")

def test_invalid_urls():
    assert not is_valid_url("not-a-url")
    assert not is_valid_url("ftp://example.com")
    assert not is_valid_url("")
    print("  invalid_urls: PASSED")

def test_extract_domain():
    assert extract_domain("https://www.example.com/path") == "example.com"
    assert extract_domain("http://api.example.com") == "api.example.com"
    print("  extract_domain: PASSED")

def test_extract_domain_with_port():
    """Domain extraction should NOT include the port number."""
    result = extract_domain("http://localhost:8080/path")
    assert result == "localhost", f"Expected 'localhost', got '{result}'"
    result = extract_domain("https://api.example.com:443/v1")
    assert result == "api.example.com", f"Expected 'api.example.com', got '{result}'"
    print("  extract_domain_with_port: PASSED")

def test_query_params():
    params = extract_query_params("http://example.com?name=alice&age=30")
    assert params == {"name": "alice", "age": "30"}
    assert extract_query_params("http://example.com") == {}
    print("  query_params: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_valid_urls", "test_url_with_port", "test_invalid_urls",
                  "test_extract_domain", "test_extract_domain_with_port", "test_query_params"]:
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

    # ═══════ T2: Float precision — IEEE 754 gotchas ═══════
    "tasks/t2/money.py": '''\
class Money:
    """Money arithmetic that avoids floating-point errors."""

    def __init__(self, amount):
        # Store as float (this is the root design issue)
        self.amount = float(amount)

    def add(self, other):
        # Bug: floating point accumulation error
        # 0.1 + 0.2 = 0.30000000000000004 in IEEE 754
        return Money(self.amount + other.amount)

    def multiply(self, factor):
        return Money(self.amount * factor)

    def equals(self, other, precision=2):
        """Compare with rounding to given decimal places."""
        # Bug: rounds each side independently, which can give wrong results
        # round(2.675, 2) = 2.67 in Python (banker's rounding), not 2.68
        return round(self.amount, precision) == round(other.amount, precision)

    def to_cents(self):
        """Convert to integer cents."""
        # Bug: int() truncates instead of rounding
        # Money(19.99).to_cents() = 1998 instead of 1999
        return int(self.amount * 100)

    def format(self):
        return f"${self.amount:.2f}"

    def __repr__(self):
        return f"Money({self.amount})"
''',
    "tasks/t2/test_money.py": '''\
from money import Money

def test_basic_arithmetic():
    a = Money(10.50)
    b = Money(3.25)
    result = a.add(b)
    assert result.format() == "$13.75"
    print("  basic_arithmetic: PASSED")

def test_accumulation():
    """Adding 0.10 ten times should equal 1.00."""
    total = Money(0)
    for _ in range(10):
        total = total.add(Money(0.10))
    assert total.to_cents() == 100, \\
        f"10 × $0.10 should be 100 cents, got {total.to_cents()} (amount={total.amount})"
    print("  accumulation: PASSED")

def test_to_cents():
    assert Money(19.99).to_cents() == 1999, \\
        f"$19.99 = 1999 cents, got {Money(19.99).to_cents()}"
    assert Money(0.01).to_cents() == 1
    assert Money(100.00).to_cents() == 10000
    print("  to_cents: PASSED")

def test_equals():
    assert Money(10.00).equals(Money(10.00))
    assert Money(10.001).equals(Money(10.002))  # same at 2 decimal places
    assert not Money(10.01).equals(Money(10.02))
    print("  equals: PASSED")

def test_multiply():
    result = Money(10.00).multiply(1.08)  # 8% tax
    assert result.to_cents() == 1080, \\
        f"$10 × 1.08 should be 1080 cents, got {result.to_cents()}"
    print("  multiply: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_basic_arithmetic", "test_accumulation",
                  "test_to_cents", "test_equals", "test_multiply"]:
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

    # ═══════ T3: Closure capture — classic Python gotcha ═══════
    "tasks/t3/hooks.py": '''\
class HookManager:
    """Register and run hooks with arguments."""

    def __init__(self):
        self.hooks = {}

    def register_batch(self, names):
        """Register a hook for each name that returns the name when called."""
        for name in names:
            # Bug: closure captures loop variable by reference, not by value
            # All hooks will return the LAST name in the list
            self.hooks[name] = lambda: name

    def register(self, name, fn):
        self.hooks[name] = fn

    def run(self, name, *args, **kwargs):
        if name not in self.hooks:
            return None
        return self.hooks[name](*args, **kwargs)

    def run_all(self):
        """Run all hooks and return {name: result} dict."""
        return {name: fn() for name, fn in self.hooks.items()}

    def create_counter(self, name):
        """Create a hook that counts how many times it's been called."""
        count = [0]
        def counter():
            count[0] += 1
            return count[0]
        self.hooks[name] = counter

    def create_pipeline(self, name, *fns):
        """Create a hook that runs functions in sequence, passing result forward."""
        def pipeline(value):
            result = value
            for fn in fns:
                result = fn(result)
            return result
        self.hooks[name] = pipeline
''',
    "tasks/t3/test_hooks.py": '''\
from hooks import HookManager

def test_register_and_run():
    hm = HookManager()
    hm.register("greet", lambda name: f"Hello, {name}!")
    assert hm.run("greet", "Alice") == "Hello, Alice!"
    assert hm.run("missing") is None
    print("  register_and_run: PASSED")

def test_register_batch():
    """Each hook should return its OWN name, not the last one."""
    hm = HookManager()
    hm.register_batch(["alpha", "beta", "gamma"])
    assert hm.run("alpha") == "alpha", f"Expected 'alpha', got '{hm.run('alpha')}'"
    assert hm.run("beta") == "beta", f"Expected 'beta', got '{hm.run('beta')}'"
    assert hm.run("gamma") == "gamma", f"Expected 'gamma', got '{hm.run('gamma')}'"
    print("  register_batch: PASSED")

def test_run_all():
    hm = HookManager()
    hm.register_batch(["x", "y", "z"])
    results = hm.run_all()
    assert results == {"x": "x", "y": "y", "z": "z"}, f"Got {results}"
    print("  run_all: PASSED")

def test_counter():
    hm = HookManager()
    hm.create_counter("clicks")
    assert hm.run("clicks") == 1
    assert hm.run("clicks") == 2
    assert hm.run("clicks") == 3
    print("  counter: PASSED")

def test_pipeline():
    hm = HookManager()
    hm.create_pipeline("transform",
                        lambda x: x * 2,
                        lambda x: x + 10,
                        lambda x: str(x))
    assert hm.run("transform", 5) == "20", f"Got {hm.run('transform', 5)}"
    print("  pipeline: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_register_and_run", "test_register_batch", "test_run_all",
                  "test_counter", "test_pipeline"]:
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

    # ═══════ T4: Bit manipulation codec — proven hard ═══════
    "tasks/t4/codec.py": '''\
def encode(data):
    """Simple encoding: shift each byte left by 2 and XOR with 0xAA."""
    result = []
    for b in data:
        shifted = (b << 3) & 0xFF  # Bug: should be << 2
        result.append(shifted ^ 0xAA)
    return bytes(result)

def decode(encoded):
    """Reverse the encoding."""
    result = []
    for b in encoded:
        unxored = b ^ 0xAA
        shifted = (unxored >> 3) & 0xFF  # Bug: should be >> 2
        result.append(shifted)
    return bytes(result)

def encode_string(text):
    return encode(text.encode("utf-8"))

def decode_string(encoded):
    return decode(encoded).decode("utf-8", errors="replace")
''',
    "tasks/t4/test_codec.py": '''\
from codec import encode, decode, encode_string, decode_string

def test_encode_known():
    """Encoding byte 65 (A): (65 << 2) & 0xFF = 4, 4 ^ 0xAA = 0xAE."""
    result = encode(b"A")
    expected = bytes([0x04 ^ 0xAA])
    assert result == expected, f"encode(b'A') = {result.hex()}, expected {expected.hex()}"
    print("  encode_known: PASSED")

def test_roundtrip():
    original = b"Hello, World!"
    assert decode(encode(original)) == original, "Roundtrip failed"
    print("  roundtrip: PASSED")

def test_string_roundtrip():
    original = "Testing 123!"
    assert decode_string(encode_string(original)) == original
    print("  string_roundtrip: PASSED")

def test_all_bytes():
    original = bytes(range(256))
    assert decode(encode(original)) == original, "Not all bytes survived"
    print("  all_bytes: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_encode_known", "test_roundtrip",
                  "test_string_roundtrip", "test_all_bytes"]:
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

PROMPT = """\
You are a software developer. Fix the bugs and make all tests pass.
Print the final test output.
"""

TASKS = [
    TaskItem(
        prompt="Fix the bugs in tasks/t1/urlparse.py. Run: cd tasks/t1 && python test_urlparse.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="medium", tags=["regex", "url-parsing"],
    ),
    TaskItem(
        prompt="Fix the bugs in tasks/t2/money.py. Run: cd tasks/t2 && python test_money.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="hard", tags=["floating-point", "precision"],
    ),
    TaskItem(
        prompt="Fix the bug in tasks/t3/hooks.py. Run: cd tasks/t3 && python test_hooks.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="hard", tags=["closure", "python-gotcha"],
    ),
    TaskItem(
        prompt="Fix the bugs in tasks/t4/codec.py. Run: cd tasks/t4 && python test_codec.py\nPrint the test output.",
        expected="PASSED", check_fn='"PASSED" in output or "pass" in output.lower()',
        difficulty="very_hard", tags=["bit-manipulation", "codec"],
    ),
]

experiment = Experiment(
    name="real_model_selection_v2",
    description=(
        "Haiku vs Sonnet on GENUINELY hard tasks: regex, float precision, "
        "closure capture, bit manipulation. Both get 15 turns. "
        "Tasks challenge model reasoning, not turn budget."
    ),
    diff=DiffSpec(
        field="model",
        description="Haiku vs Sonnet on reasoning-hard tasks (regex, float, closure, bits)",
    ),
    agent_a=AgentConfig(
        name="haiku",
        model="claude-haiku-4-5",
        system_prompt=PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    agent_b=AgentConfig(
        name="sonnet",
        model="claude-sonnet-4-6",
        system_prompt=PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=15,
    ),
    tasks=TASKS,
    setup_files=SETUP_FILES,
    num_samples=8,
    tags=["model-selection", "reasoning-hard", "realistic"],
)
