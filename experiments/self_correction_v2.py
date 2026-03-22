"""
Self-Correction v2: Deceptive Bugs — Pivot Should Win

v1 finding: refine > pivot (+29%) on tasks with independent bugs.
But v1 bugs were independent — Phase 1 fix was partial, not WRONG.

v2 hypothesis: When Phase 1 fix is fundamentally WRONG (wrong mental model),
pivot (revert + fresh start) should outperform refine (build on wrong fix).

Design: 4 tasks where the error message strongly suggests fix X,
but fix X makes the code WORSE. The correct fix Y is different.

- T1: scale_scores — reversed output → obvious fix: reverse list (WRONG)
- T2: merge_sorted — duplicates in output → obvious fix: dedup (WRONG)
- T3: parse_config — key lookup fails → obvious fix: change lookup (WRONG)
- T4: csv_format — separators mixed up → obvious fix: swap in format string (WRONG, subtly)

max_turns=10, num_samples=5. git init for pivot revert.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # ═══════════════ T1: Scale Scores (swapped normalize args) ═══════════════
    # Bug: normalize(s, src_max, src_min) — args swapped
    # Symptom: output is reversed [100, 50, 0] instead of [0, 50, 100]
    # Wrong fix: reverse the output list (passes test 1, fails test 2)
    # Right fix: swap src_max/src_min in normalize call
    "tasks/t1/scores.py": '''\
def normalize(value, min_val, max_val):
    """Normalize value to 0.0-1.0 range."""
    if max_val == min_val:
        return 0.0
    return (value - min_val) / (max_val - min_val)

def scale_scores(scores, target_min=0, target_max=100):
    """Scale scores to target range using min-max normalization."""
    if not scores:
        return []
    src_min = min(scores)
    src_max = max(scores)
    if src_min == src_max:
        mid = (target_min + target_max) / 2
        return [round(mid, 1)] * len(scores)
    return [
        round(normalize(s, src_max, src_min) * (target_max - target_min) + target_min, 1)
        for s in scores
    ]
''',
    "tasks/t1/test_scores.py": '''\
from scores import scale_scores

def test_basic_scale():
    """Scale [0, 50, 100] to 0-100 should preserve values."""
    result = scale_scores([0, 50, 100])
    assert result == [0.0, 50.0, 100.0], f"Expected [0, 50, 100], got {result}"
    print("  basic_scale: PASSED")

def test_custom_range():
    """Scale to 10-20 range."""
    result = scale_scores([0, 50, 100], target_min=10, target_max=20)
    assert result == [10.0, 15.0, 20.0], f"Expected [10, 15, 20], got {result}"
    print("  custom_range: PASSED")

def test_uneven_input():
    """Non-uniform input distribution."""
    result = scale_scores([20, 60, 80], target_min=0, target_max=100)
    # (20-20)/(80-20)=0, (60-20)/(80-20)=0.667, (80-20)/(80-20)=1
    assert result[0] == 0.0, f"Min should map to 0, got {result[0]}"
    assert result[2] == 100.0, f"Max should map to 100, got {result[2]}"
    assert 60 < result[1] < 70, f"Middle should be ~66.7, got {result[1]}"
    print("  uneven_input: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_basic_scale", "test_custom_range", "test_uneven_input"]:
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

    # ═══════════════ T2: Merge Sorted (swapped extend indices) ═══════════════
    # Bug: a[j:] and b[i:] — indices swapped
    # Symptom: duplicates in output [1, 2, 3, 3] instead of [1, 2, 3, 4]
    # Wrong fix: deduplicate the result (passes test 1, fails test 2 with legit dupes)
    # Right fix: swap i/j in extend calls
    "tasks/t2/merge.py": '''\
def merge_sorted(a, b):
    """Merge two sorted lists into one sorted list (preserving duplicates)."""
    result = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            result.append(a[i])
            i += 1
        else:
            result.append(b[j])
            j += 1
    result.extend(a[j:])
    result.extend(b[i:])
    return result
''',
    "tasks/t2/test_merge.py": '''\
from merge import merge_sorted

def test_basic_merge():
    result = merge_sorted([1, 3], [2, 4])
    assert result == [1, 2, 3, 4], f"Expected [1, 2, 3, 4], got {result}"
    print("  basic_merge: PASSED")

def test_with_duplicates():
    """Legitimate duplicates must be preserved."""
    result = merge_sorted([1, 1, 3], [1, 2, 3])
    assert result == [1, 1, 1, 2, 3, 3], f"Expected [1, 1, 1, 2, 3, 3], got {result}"
    print("  with_duplicates: PASSED")

def test_uneven_lengths():
    result = merge_sorted([1], [2, 3, 4, 5])
    assert result == [1, 2, 3, 4, 5], f"Expected [1, 2, 3, 4, 5], got {result}"
    print("  uneven_lengths: PASSED")

def test_empty():
    assert merge_sorted([], [1, 2]) == [1, 2]
    assert merge_sorted([3, 4], []) == [3, 4]
    assert merge_sorted([], []) == []
    print("  empty: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_basic_merge", "test_with_duplicates", "test_uneven_lengths", "test_empty"]:
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

    # ═══════════════ T3: Parse Config (key/value swapped in dict) ═══════════════
    # Bug: stores {value: key} instead of {key: value}
    # Symptom: config.get("host") returns None
    # Wrong fix: change the lookup to use the value → breaks for multiple keys with same format
    # Right fix: swap key/value in the dict construction
    "tasks/t3/config_parser.py": '''\
def parse_config(text):
    """Parse 'key = value' config text into a dict.

    Lines starting with # are comments. Empty lines are skipped.
    Keys and values are stripped of whitespace.
    """
    config = {}
    for line in text.strip().split("\\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[value.strip()] = key.strip()  # Bug: key/value swapped
    return config

def get_config_value(text, key, default=None):
    """Parse config and return a specific key's value."""
    config = parse_config(text)
    return config.get(key, default)
''',
    "tasks/t3/test_config.py": '''\
from config_parser import parse_config, get_config_value

SAMPLE_CONFIG = """
# Database settings
host = localhost
port = 5432
database = myapp

# App settings
debug = true
workers = 4
"""

def test_parse_basic():
    config = parse_config(SAMPLE_CONFIG)
    assert config.get("host") == "localhost", f"host: {config.get('host')}, config: {config}"
    assert config.get("port") == "5432", f"port: {config.get('port')}"
    print("  parse_basic: PASSED")

def test_parse_all_keys():
    config = parse_config(SAMPLE_CONFIG)
    expected_keys = {"host", "port", "database", "debug", "workers"}
    assert set(config.keys()) == expected_keys, f"Keys: {set(config.keys())}"
    print("  parse_all_keys: PASSED")

def test_get_value():
    val = get_config_value(SAMPLE_CONFIG, "database")
    assert val == "myapp", f"Expected 'myapp', got '{val}'"
    print("  get_value: PASSED")

def test_get_default():
    val = get_config_value(SAMPLE_CONFIG, "missing", default="fallback")
    assert val == "fallback", f"Expected 'fallback', got '{val}'"
    print("  get_default: PASSED")

def test_comments_skipped():
    config = parse_config("# comment\\nkey = val")
    assert len(config) == 1, f"Comments should be skipped, got {config}"
    assert config.get("key") == "val"
    print("  comments_skipped: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_parse_basic", "test_parse_all_keys", "test_get_value",
                  "test_get_default", "test_comments_skipped"]:
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

    # ═══════════════ T4: Report Formatter (args order in f-string) ═══════════════
    # Bug: format_row uses (name, value) but template has {value}: {name}
    # Symptom: "100: Alice" instead of "Alice: 100"
    # Wrong fix: swap the format string → passes test 1, fails test 2 (different format)
    # Right fix: fix the argument order in format_row
    "tasks/t4/formatter.py": '''\
def format_row(name, value, template="{}: {}"):
    """Format a single data row using template."""
    return template.format(value, name)  # Bug: args swapped

def format_table(data, template="{}: {}"):
    """Format list of (name, value) pairs into a table string."""
    rows = []
    for name, value in data:
        rows.append(format_row(name, value, template))
    return "\\n".join(rows)

def format_summary(data):
    """Create a summary with total."""
    table = format_table(data)
    total = sum(v for _, v in data)
    return f"{table}\\nTotal: {total}"
''',
    "tasks/t4/test_formatter.py": '''\
from formatter import format_row, format_table, format_summary

def test_format_row():
    result = format_row("Alice", 100)
    assert result == "Alice: 100", f"Expected 'Alice: 100', got '{result}'"
    print("  format_row: PASSED")

def test_format_row_custom_template():
    """Custom template should work correctly."""
    result = format_row("Bob", 200, template="{} scored {}")
    assert result == "Bob scored 200", f"Expected 'Bob scored 200', got '{result}'"
    print("  format_row_template: PASSED")

def test_format_table():
    data = [("Alice", 100), ("Bob", 200)]
    result = format_table(data)
    assert result == "Alice: 100\\nBob: 200", f"Got '{result}'"
    print("  format_table: PASSED")

def test_format_summary():
    data = [("X", 10), ("Y", 20)]
    result = format_summary(data)
    assert "Total: 30" in result
    assert "X: 10" in result
    print("  format_summary: PASSED")

if __name__ == "__main__":
    passed = failed = 0
    for name in ["test_format_row", "test_format_row_custom_template",
                  "test_format_table", "test_format_summary"]:
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

PIVOT_PROMPT = """\
STRICT RULES for fixing bugs:

PHASE 1 — First attempt:
1. Read the source file
2. Read the test file
3. Identify all bugs
4. Fix all bugs in one pass
5. Run the test

PHASE 2 — If any test still fails:
6. REVERT all your changes: run `git checkout -- .` to restore original files
7. Re-read the test output from step 5 carefully
8. Re-read the source file with fresh eyes — your first diagnosis was WRONG
9. Find the REAL bug (not what you thought before)
10. Fix it correctly
11. Run the test again

CRITICAL CONSTRAINTS:
- After a failed test, you are FORBIDDEN from making incremental edits
- You MUST run `git checkout -- .` before your second attempt
- You MUST re-read the source file after reverting
- Your first fix was WRONG — you need a completely different analysis
- "Revert everything, rethink everything"

Print the final test output.
"""

REFINE_PROMPT = """\
STRICT RULES for fixing bugs:

PHASE 1 — First attempt:
1. Read the source file
2. Read the test file
3. Identify all bugs
4. Fix all bugs in one pass
5. Run the test

PHASE 2 — If any test still fails:
6. Do NOT revert your changes — your existing fix may be partially right
7. Read ONLY the new test output to identify remaining failures
8. Make MINIMAL additional edits to fix the remaining tests
9. Run the test again

CRITICAL CONSTRAINTS:
- After a failed test, you are FORBIDDEN from reverting previous changes
- You are FORBIDDEN from running `git checkout` or `git restore`
- You are FORBIDDEN from re-reading the source file — use only the test output
- Build on your existing fix — adjust, don't restart
- "Keep what works, fix what's still broken"

Print the final test output.
"""

experiment = Experiment(
    name="self_correction_v2",
    description=(
        "Deceptive bugs where the obvious fix is WRONG. "
        "Pivot should win by reverting wrong fixes and finding the real bug. "
        "4 tasks × 5 samples."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="Pivot (revert wrong fix, fresh analysis) vs refine (build on wrong fix)",
    ),
    agent_a=AgentConfig(
        name="pivot",
        model="claude-haiku-4-5",
        system_prompt=PIVOT_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=10,
    ),
    agent_b=AgentConfig(
        name="refine",
        model="claude-haiku-4-5",
        system_prompt=REFINE_PROMPT,
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit", "Grep"],
        max_turns=10,
    ),
    tasks=[
        TaskItem(
            prompt="Fix the bug in tasks/t1/scores.py. Run: cd tasks/t1 && python test_scores.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="hard", tags=["deceptive", "swapped-args"],
        ),
        TaskItem(
            prompt="Fix the bug in tasks/t2/merge.py. Run: cd tasks/t2 && python test_merge.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="hard", tags=["deceptive", "swapped-indices"],
        ),
        TaskItem(
            prompt="Fix the bug in tasks/t3/config_parser.py. Run: cd tasks/t3 && python test_config.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="hard", tags=["deceptive", "swapped-kv"],
        ),
        TaskItem(
            prompt="Fix the bug in tasks/t4/formatter.py. Run: cd tasks/t4 && python test_formatter.py\nPrint the test output.",
            expected="PASSED", check_fn='"PASSED" in output',
            difficulty="hard", tags=["deceptive", "swapped-format-args"],
        ),
    ],
    setup_files=SETUP_FILES,
    setup_script="cd tasks/t1 && git init -q && git add -A && git commit -q -m init && cd ../t2 && git init -q && git add -A && git commit -q -m init && cd ../t3 && git init -q && git add -A && git commit -q -m init && cd ../t4 && git init -q && git add -A && git commit -q -m init",
    num_samples=5,
    tags=["self-correction", "deceptive-bugs", "pivot-favored"],
)
