"""
Experiment: Turn Budget Scaling — How many turns does an agent actually need?

Same hard task, 4 agents identical except max_turns: 5, 10, 20, 40.
Tests where diminishing returns kick in and whether more turns = more correct.

Task: Build a complete URL shortener service (in-memory) with:
- Shorten URL → returns short code
- Expand short code → returns original URL
- Click tracking (count expansions)
- Collision-free short codes
- Input validation
- Stats endpoint
Must pass a comprehensive test suite.
"""
from openbench.types import AgentConfig, TaskItem, TournamentConfig

SETUP_FILES = {
    "test_shortener.py": '''\
"""Comprehensive test suite for URL shortener."""
import sys
sys.path.insert(0, ".")

from shortener import URLShortener

def test_basic():
    s = URLShortener()
    code = s.shorten("https://example.com")
    assert isinstance(code, str) and len(code) >= 4, f"Bad code: {code}"
    assert s.expand(code) == "https://example.com"
    print("  basic: OK")

def test_deterministic():
    s = URLShortener()
    c1 = s.shorten("https://example.com")
    c2 = s.shorten("https://example.com")
    assert c1 == c2, "Same URL should return same code"
    print("  deterministic: OK")

def test_different_urls():
    s = URLShortener()
    c1 = s.shorten("https://a.com")
    c2 = s.shorten("https://b.com")
    assert c1 != c2, "Different URLs must have different codes"
    print("  different_urls: OK")

def test_expand_unknown():
    s = URLShortener()
    result = s.expand("nonexistent")
    assert result is None, f"Unknown code should return None, got {result}"
    print("  expand_unknown: OK")

def test_click_tracking():
    s = URLShortener()
    code = s.shorten("https://tracked.com")
    assert s.get_clicks(code) == 0
    s.expand(code)
    s.expand(code)
    s.expand(code)
    assert s.get_clicks(code) == 3, f"Expected 3 clicks, got {s.get_clicks(code)}"
    print("  click_tracking: OK")

def test_stats():
    s = URLShortener()
    s.shorten("https://a.com")
    s.shorten("https://b.com")
    code = s.shorten("https://c.com")
    s.expand(code)
    stats = s.stats()
    assert stats["total_urls"] == 3
    assert stats["total_clicks"] == 1
    print("  stats: OK")

def test_validation():
    s = URLShortener()
    try:
        s.shorten("")
        assert False, "Empty URL should raise ValueError"
    except ValueError:
        pass
    try:
        s.shorten("not-a-url")
        assert False, "Invalid URL should raise ValueError"
    except ValueError:
        pass
    print("  validation: OK")

def test_many_urls():
    s = URLShortener()
    codes = set()
    for i in range(100):
        code = s.shorten(f"https://example.com/page/{i}")
        codes.add(code)
    assert len(codes) == 100, f"Expected 100 unique codes, got {len(codes)}"
    # Verify all expand correctly
    for i in range(100):
        code = s.shorten(f"https://example.com/page/{i}")
        assert s.expand(code) == f"https://example.com/page/{i}"
    print("  many_urls: OK")

def test_custom_code():
    """Optional: custom alias support."""
    s = URLShortener()
    try:
        code = s.shorten("https://custom.com", custom_code="myalias")
        assert code == "myalias"
        assert s.expand("myalias") == "https://custom.com"
        # Custom code collision
        try:
            s.shorten("https://other.com", custom_code="myalias")
            assert False, "Duplicate custom code should raise ValueError"
        except ValueError:
            pass
        print("  custom_code: OK")
    except TypeError:
        print("  custom_code: SKIP (not implemented)")

if __name__ == "__main__":
    passed = 0
    failed = 0
    for name, func in list(globals().items()):
        if name.startswith("test_"):
            try:
                func()
                passed += 1
            except Exception as e:
                print(f"  {name}: FAIL — {e}")
                failed += 1
    total = passed + failed
    print(f"\\nResults: {passed}/{total} passed")
    if failed == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"{failed} FAILED")
''',
}

TASK = TaskItem(
    prompt=(
        "Build a URL shortener in shortener.py. Requirements:\n"
        "- URLShortener class with methods: shorten(url, custom_code=None), "
        "expand(code), get_clicks(code), stats()\n"
        "- shorten() returns a short alphanumeric code (≥4 chars)\n"
        "- Same URL always returns same code (idempotent)\n"
        "- expand() returns original URL or None, increments click count\n"
        "- get_clicks() returns click count for a code\n"
        "- stats() returns dict with total_urls and total_clicks\n"
        "- Validate URLs (must start with http:// or https://)\n"
        "- Optional: custom_code parameter for custom aliases\n"
        "Run test_shortener.py to verify. All tests must pass."
    ),
    expected="ALL TESTS PASSED",
    check_fn='"ALL TESTS PASSED" in output or ("passed" in output.lower() and "fail" not in output.lower())',
    difficulty="hard",
    tags=["multi-turn", "implementation", "url-shortener"],
)

SYSTEM_PROMPT = (
    "You are building a Python module. Read the test file first to understand "
    "all requirements, then implement the module and run tests to verify."
)

tournament = TournamentConfig(
    name="turn_budget_scaling",
    description=(
        "Same URL shortener task with max_turns 5/10/20/40. "
        "Tests where diminishing returns kick in."
    ),
    configs=[
        AgentConfig(
            name="turns_05",
            model="claude-haiku-4-5",
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
            max_turns=5,
        ),
        AgentConfig(
            name="turns_10",
            model="claude-haiku-4-5",
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
            max_turns=10,
        ),
        AgentConfig(
            name="turns_20",
            model="claude-haiku-4-5",
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
            max_turns=20,
        ),
        AgentConfig(
            name="turns_40",
            model="claude-haiku-4-5",
            system_prompt=SYSTEM_PROMPT,
            allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
            max_turns=40,
        ),
    ],
    tasks=[TASK],
    num_samples=3,  # 3 samples for statistical signal
    setup_files=SETUP_FILES,
    tags=["turn-budget", "scaling", "multi-turn"],
)
