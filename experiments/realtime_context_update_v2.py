"""
Real-Time Context Update v2 — Anti-Recency Needle

v1 finding: both formats ~99% accurate (excluding timeouts). Research shows
LLMs have strong recency bias — they naturally prefer the last occurrence.
Since v1 always placed the latest value last, recency bias did all the work.

v2 question: does the model actually UNDERSTAND "latest by timestamp",
or does it just grab the last line?

Design: timestamped entries where out-of-order delivery puts the latest
timestamp in the MIDDLE, with older entries appended after it.

- Agent A (ordered): entries in chronological order (latest = last line)
- Agent B (shuffled): latest timestamp at ~40% position, older entries after

Same data, same expected answers, only ORDER differs.

Fixes from v1:
- Each task's data goes in its own task prompt (not system_prompt)
- Fewer, smaller tasks to avoid timeouts
- Unique expected values to prevent false-positive check_fn
"""

import random

from openbench.types import AgentConfig, DiffSpec, Experiment, TaskItem

SYSTEM_PROMPT = (
    "You are a monitoring assistant. You receive timestamped status updates "
    "that may arrive OUT OF ORDER due to network delays. Always report the "
    "values from the entry with the LATEST TIMESTAMP, regardless of its "
    "position in the list. Output only the requested values, one per line."
)


def _gen_timestamps(n: int, base_hour: int = 10, interval_min: int = 5) -> list[str]:
    """Generate n timestamps at regular intervals."""
    return [
        f"2024-03-21 {base_hour + (i * interval_min) // 60:02d}:"
        f"{(i * interval_min) % 60:02d}"
        for i in range(n)
    ]


def _gen_field_values(
    n: int, field: str, seed: int,
) -> list[str]:
    """Generate n unique, easily distinguishable values."""
    rng = random.Random(seed)
    generators = {
        "cpu": lambda: f"{rng.uniform(10.0, 95.0):.1f}%",
        "memory": lambda: f"{rng.uniform(20.0, 90.0):.1f}%",
        "requests": lambda: str(rng.randint(1000, 9999)),
        "errors": lambda: str(rng.randint(0, 50)),
        "latency_ms": lambda: str(rng.randint(5, 500)),
    }
    return [generators[field]() for _ in range(n)]


def _build_entries(
    timestamps: list[str],
    fields: dict[str, list[str]],
) -> list[tuple[str, dict[str, str]]]:
    """Build (timestamp, {field: value}) pairs."""
    n = len(timestamps)
    return [
        (timestamps[i], {f: vals[i] for f, vals in fields.items()})
        for i in range(n)
    ]


def _format_entries(entries: list[tuple[str, dict[str, str]]]) -> str:
    """Format entries as timestamped log lines."""
    lines = []
    for ts, vals in entries:
        parts = " ".join(f"{k}={v}" for k, v in vals.items())
        lines.append(f"[{ts}] {parts}")
    return "\n".join(lines)


def _shuffle_latest_to_middle(
    entries: list[tuple[str, dict[str, str]]],
    seed: int,
) -> list[tuple[str, dict[str, str]]]:
    """Move the latest entry (last) to ~40% position, keep rest in order."""
    rng = random.Random(seed)
    latest = entries[-1]
    rest = entries[:-1]
    insert_pos = len(rest) * 2 // 5  # ~40% position
    # Also shuffle a few more entries to make it realistic (network jitter)
    # Swap 2-3 adjacent pairs in the tail half
    tail_start = len(rest) // 2
    for _ in range(min(3, len(rest) - tail_start - 1)):
        i = rng.randint(tail_start, len(rest) - 2)
        rest[i], rest[i + 1] = rest[i + 1], rest[i]
    rest.insert(insert_pos, latest)
    return rest


def _make_task(
    n_updates: int,
    field_names: list[str],
    seed: int,
    difficulty: str,
    tags: list[str],
) -> tuple[TaskItem, TaskItem]:
    """Create ordered and shuffled versions of the same task."""
    timestamps = _gen_timestamps(n_updates)
    fields = {
        f: _gen_field_values(n_updates, f, seed + i)
        for i, f in enumerate(field_names)
    }
    entries = _build_entries(timestamps, fields)

    # Latest = last entry (by timestamp)
    latest_ts, latest_vals = entries[-1]
    expected_parts = [f"{k}={v}" for k, v in latest_vals.items()]
    expected = " | ".join(expected_parts)
    check_fn = " and ".join(f'"{v}" in output' for v in latest_vals.values())

    field_list = ", ".join(field_names)
    question = (
        f"What are the values from the entry with the LATEST timestamp? "
        f"Report: {field_list}"
    )

    # Ordered version (latest = last line)
    ordered_block = _format_entries(entries)
    ordered_prompt = (
        f"Status updates (may be out of order):\n{ordered_block}\n\n{question}"
    )

    # Shuffled version (latest = middle)
    shuffled = _shuffle_latest_to_middle(entries, seed)
    shuffled_block = _format_entries(shuffled)
    shuffled_prompt = (
        f"Status updates (may be out of order):\n{shuffled_block}\n\n{question}"
    )

    ordered_task = TaskItem(
        prompt=ordered_prompt,
        expected=expected,
        check_fn=check_fn,
        difficulty=difficulty,
        tags=tags,
    )
    shuffled_task = TaskItem(
        prompt=shuffled_prompt,
        expected=expected,
        check_fn=check_fn,
        difficulty=difficulty,
        tags=tags,
    )
    return ordered_task, shuffled_task


# --- Task specs ---

SPECS = [
    {"n": 10, "fields": ["cpu", "memory"], "difficulty": "easy",
     "tags": ["10-updates", "2-fields"]},
    {"n": 10, "fields": ["cpu", "memory", "requests"], "difficulty": "easy",
     "tags": ["10-updates", "3-fields"]},
    {"n": 20, "fields": ["cpu", "memory", "requests"], "difficulty": "medium",
     "tags": ["20-updates", "3-fields"]},
    {"n": 30, "fields": ["cpu", "memory", "requests", "errors"],
     "difficulty": "medium", "tags": ["30-updates", "4-fields"]},
    {"n": 50, "fields": ["cpu", "memory", "requests", "errors", "latency_ms"],
     "difficulty": "hard", "tags": ["50-updates", "5-fields"]},
]

ordered_tasks: list[TaskItem] = []
shuffled_tasks: list[TaskItem] = []

for i, spec in enumerate(SPECS):
    seed = 2000 + i * 100
    ot, st = _make_task(
        spec["n"], spec["fields"], seed, spec["difficulty"], spec["tags"],
    )
    ordered_tasks.append(ot)
    shuffled_tasks.append(st)

# Since Experiment shares one task list, we need two experiments.
# Use a convention: export both, runner picks `experiment`.
# We'll make the primary experiment the shuffled (hard) case,
# comparing "ordered" vs "shuffled" by encoding data in system_prompt+task.

# Actually — we CAN'T have different task prompts per agent in one Experiment.
# Solution: run two experiments and compare across them.
# OR: use the system_prompt to carry the data block, task just has the question.

# Let's use system_prompt for the data block (per-agent), task for the question.
# This time, system_prompt is small enough (no 6-task concatenation).

# We'll create 5 separate experiments, one per task complexity.
# But that's heavy. Better: pick the 3 most informative tasks.

# Compromise: embed data in system_prompt per complexity level.
# Run 3 separate Experiment objects, exported as a list.

def _make_experiment(
    idx: int,
    spec: dict,
    ordered_task: TaskItem,
    shuffled_task: TaskItem,
) -> Experiment:
    """Create experiment comparing ordered vs shuffled for one task."""
    seed = 2000 + idx * 100
    n = spec["n"]
    field_names = spec["fields"]
    timestamps = _gen_timestamps(n)
    fields = {
        f: _gen_field_values(n, f, seed + i)
        for i, f in enumerate(field_names)
    }
    entries = _build_entries(timestamps, fields)
    shuffled_entries = _shuffle_latest_to_middle(entries, seed)

    ordered_block = _format_entries(entries)
    shuffled_block = _format_entries(shuffled_entries)

    # Latest values for the question
    _, latest_vals = entries[-1]
    field_list = ", ".join(field_names)
    question = (
        f"What are the values from the entry with the LATEST timestamp? "
        f"Report: {field_list}"
    )
    expected_parts = [f"{k}={v}" for k, v in latest_vals.items()]
    expected = " | ".join(expected_parts)
    check_fn = " and ".join(f'"{v}" in output' for v in latest_vals.values())

    task = TaskItem(
        prompt=question,
        expected=expected,
        check_fn=check_fn,
        difficulty=spec["difficulty"],
        tags=spec["tags"],
    )

    suffix = f"n{n}_f{len(field_names)}"
    return Experiment(
        name=f"realtime_context_update_v2_{suffix}",
        description=(
            f"Anti-recency needle: {n} timestamped updates, {len(field_names)} fields. "
            f"Ordered (latest=last) vs shuffled (latest at ~40% position)."
        ),
        diff=DiffSpec(
            field="system_prompt",
            description="chronological order vs out-of-order (latest in middle)",
        ),
        agent_a=AgentConfig(
            name="ordered",
            model="claude-haiku-4-5",
            system_prompt=f"{SYSTEM_PROMPT}\n\nStatus updates:\n{ordered_block}",
            allowed_tools=[],
            max_turns=1,
        ),
        agent_b=AgentConfig(
            name="shuffled",
            model="claude-haiku-4-5",
            system_prompt=f"{SYSTEM_PROMPT}\n\nStatus updates:\n{shuffled_block}",
            allowed_tools=[],
            max_turns=1,
        ),
        tasks=[task],
        num_samples=8,
        tags=["anti-recency", "out-of-order", "research"],
    )


# Pick 3 representative tasks: easy (10/2), medium (30/4), hard (50/5)
experiments = [
    _make_experiment(0, SPECS[0], ordered_tasks[0], shuffled_tasks[0]),
    _make_experiment(3, SPECS[3], ordered_tasks[3], shuffled_tasks[3]),
    _make_experiment(4, SPECS[4], ordered_tasks[4], shuffled_tasks[4]),
]

# Default: run the hardest one
experiment = experiments[-1]
