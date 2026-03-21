"""
Experiment: TDD Workflow — Write Tests First vs Implement First

TDFlow (Oct 2025) showed +27.8% on SWE-Bench Lite with TDD. But that gave
agents human-written tests. The open question: does AGENT-WRITTEN TDD still
help? Does writing tests first force better spec understanding?

Design:
- Agent A (implement_first): "Read spec, implement, then write tests to verify"
- Agent B (tdd): "Read spec, write failing tests FIRST, then implement to pass them"
- Same model (haiku), same tools, same tasks
- 6 implementation tasks, num_samples=3

The holy grail: if TDD haiku beats naive sonnet, workflow > model.
"""
from openbench.types import AgentConfig, Experiment, DiffSpec, TaskItem

SETUP_FILES = {
    # Specs only — no starter code, no tests. Agent must create everything.

    "spec_stack.md": """\
# Stack with Min/Max

Implement `MinMaxStack` in `stack.py`:
- `push(val)` — push value onto stack
- `pop()` — remove and return top value (raise IndexError if empty)
- `peek()` — return top value without removing (raise IndexError if empty)
- `get_min()` — return current minimum in O(1) (raise IndexError if empty)
- `get_max()` — return current maximum in O(1) (raise IndexError if empty)
- `size()` — return number of elements
- All operations must be O(1) time complexity.
""",

    "spec_lru.md": """\
# LRU Cache

Implement `LRUCache` in `lru.py`:
- `__init__(capacity)` — create cache with given max capacity
- `get(key)` — return value if exists, else -1. Marks as recently used.
- `put(key, value)` — insert/update. If at capacity, evict least recently used.
- Both get and put must be O(1) average time.
""",

    "spec_interval.md": """\
# Interval Scheduler

Implement in `interval.py`:
- `merge_intervals(intervals)` — merge overlapping intervals
  Input: list of [start, end], Output: merged list
- `insert_interval(intervals, new)` — insert a new interval into sorted non-overlapping list, merging if needed
- `can_attend_all(intervals)` — return True if no intervals overlap

All intervals are [start, end] where start <= end.
""",

    "spec_graph.md": """\
# Graph Utilities

Implement in `graph.py`:
- `has_cycle(adj_list)` — return True if directed graph has a cycle
  adj_list: dict mapping node -> list of neighbors
- `shortest_path(adj_list, start, end)` — return shortest path as list of nodes, or None
  Uses BFS (unweighted graph)
- `topological_sort(adj_list)` — return topological ordering, or None if cycle exists
""",

    "spec_tokenizer.md": """\
# Expression Tokenizer

Implement in `tokenizer.py`:
- `tokenize(expr)` — convert math expression string to list of tokens
- Token types: NUMBER (int or float), OPERATOR (+,-,*,/), LPAREN, RPAREN
- Each token is a dict: {"type": "NUMBER", "value": 42} or {"type": "OPERATOR", "value": "+"}
- Handle: whitespace (ignore), negative numbers (-3), decimal numbers (3.14)
- Raise ValueError on invalid characters
""",

    "spec_csv.md": """\
# CSV Parser

Implement in `csv_parser.py`:
- `parse_csv(text)` — parse CSV string to list of dicts
  First row is header. Return list of {column_name: value} dicts.
- `to_csv(records, columns=None)` — convert list of dicts to CSV string
  If columns not specified, use keys from first record.
- Handle: quoted fields with commas, escaped quotes, empty fields, newlines in quoted fields
""",
}

experiment = Experiment(
    name="tdd_workflow",
    description=(
        "TDD (write tests first) vs implement-first workflow. "
        "Same model (haiku), same tools. Tests whether TDD forces "
        "better spec understanding."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="implement-first vs TDD (write tests then implement)",
    ),
    agent_a=AgentConfig(
        name="implement_first",
        model="claude-haiku-4-5",
        system_prompt=(
            "You are implementing Python modules from spec files.\n"
            "Workflow: Read the spec → implement the module → "
            "write a test file (test_<module>.py) → run tests → fix any failures.\n"
            "Focus on getting the implementation right first."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=20,
    ),
    agent_b=AgentConfig(
        name="tdd",
        model="claude-haiku-4-5",
        system_prompt=(
            "You are implementing Python modules from spec files.\n"
            "Workflow — STRICT TDD:\n"
            "1. Read the spec carefully\n"
            "2. Write test file FIRST (test_<module>.py) with comprehensive tests\n"
            "3. Run tests — they should all FAIL (since module doesn't exist yet)\n"
            "4. Implement the module to make tests pass\n"
            "5. Run tests again — iterate until all pass\n"
            "IMPORTANT: Write tests BEFORE any implementation."
        ),
        allowed_tools=["Read", "Write", "Bash", "Glob", "Edit"],
        max_turns=20,
    ),
    tasks=[
        TaskItem(
            prompt="Read spec_stack.md. Implement MinMaxStack in stack.py with tests.",
            expected="pass",
            check_fn='"pass" in output.lower() and "fail" not in output.lower().split("pass")[0]',
            difficulty="medium",
            tags=["stack", "data-structure"],
        ),
        TaskItem(
            prompt="Read spec_lru.md. Implement LRUCache in lru.py with tests.",
            expected="pass",
            check_fn='"pass" in output.lower() and "fail" not in output.lower().split("pass")[0]',
            difficulty="hard",
            tags=["lru", "data-structure"],
        ),
        TaskItem(
            prompt="Read spec_interval.md. Implement interval functions in interval.py with tests.",
            expected="pass",
            check_fn='"pass" in output.lower() and "fail" not in output.lower().split("pass")[0]',
            difficulty="medium",
            tags=["interval", "algorithm"],
        ),
        TaskItem(
            prompt="Read spec_graph.md. Implement graph utilities in graph.py with tests.",
            expected="pass",
            check_fn='"pass" in output.lower() and "fail" not in output.lower().split("pass")[0]',
            difficulty="hard",
            tags=["graph", "algorithm"],
        ),
        TaskItem(
            prompt="Read spec_tokenizer.md. Implement tokenize() in tokenizer.py with tests.",
            expected="pass",
            check_fn='"pass" in output.lower() and "fail" not in output.lower().split("pass")[0]',
            difficulty="medium",
            tags=["parser", "tokenizer"],
        ),
        TaskItem(
            prompt="Read spec_csv.md. Implement CSV parser in csv_parser.py with tests.",
            expected="pass",
            check_fn='"pass" in output.lower() and "fail" not in output.lower().split("pass")[0]',
            difficulty="hard",
            tags=["parser", "csv"],
        ),
    ],
    setup_files=SETUP_FILES,
    num_samples=3,
    tags=["tdd", "workflow", "agent-optimization"],
)
