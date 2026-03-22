"""
Real-Time Status Update Format — Repeated Key vs Indexed Log

When injecting real-time state into LLM context (append-only, KV-cache friendly),
which format gives the model better recognition accuracy for the LATEST values?

- Agent A (repeated_key): `Current time: 10:00` → `Current time: 10:05`
- Agent B (indexed_log):  `[1] time=10:00` → `[2] time=10:05`

Both are append-only (no prefix mutation). The question is whether indexing
helps the model anchor to the most recent entry.

6 tasks, easy→hard, testing single/multi-field, varying update counts,
distractors, and a needle-in-haystack scenario.
"""

import random

from openbench.types import AgentConfig, DiffSpec, Experiment, TaskItem

SYSTEM_INTRO = (
    "You are a monitoring assistant. Read the status updates provided below "
    "and answer questions about the CURRENT (latest) state. Be precise — "
    "output only the requested values, one per line, in the exact format shown "
    "in the updates.\n\n"
)

DISTRACTOR_LINES = [
    "[DEBUG] GC pause 12ms, heap 482MB",
    "[INFO] Health check passed (endpoint=/health)",
    "[WARN] Slow query detected: SELECT * FROM logs (340ms)",
    "[DEBUG] Cache hit ratio: 0.87",
    "[INFO] Connection pool: 8/20 active",
    "[WARN] Disk I/O latency spike: 45ms",
    "[DEBUG] Worker thread #3 idle for 2.1s",
    "[INFO] Upstream DNS resolved in 3ms",
    "[WARN] Rate limiter: 890/1000 requests this window",
    "[DEBUG] TLS handshake completed in 18ms",
    "[INFO] Backup shard replica in sync",
    "[WARN] Memory fragmentation: 12.4%",
    "[DEBUG] Event loop lag: 2ms",
    "[INFO] Certificate expires in 42 days",
    "[WARN] Retry queue depth: 7",
]


def _generate_values(n: int, field_name: str, seed: int) -> list[str]:
    """Generate n plausible values for a monitoring field."""
    rng = random.Random(seed)
    generators = {
        "time": lambda i: f"{10 + i // 60:02d}:{i % 60:02d}",
        "temp": lambda _: f"{rng.uniform(18.0, 35.0):.1f}",
        "status": lambda _: rng.choice(["healthy", "degraded", "critical"]),
        "price": lambda _: f"{rng.uniform(100.0, 999.0):.2f}",
        "cpu": lambda _: f"{rng.uniform(5.0, 99.0):.1f}%",
        "memory": lambda _: f"{rng.uniform(20.0, 95.0):.1f}%",
        "requests": lambda _: str(rng.randint(100, 9999)),
        "disk": lambda _: f"{rng.uniform(30.0, 90.0):.1f}%",
        "connections": lambda _: str(rng.randint(10, 500)),
    }
    gen = generators[field_name]
    return [gen(i) for i in range(n)]


def _build_repeated_key(fields: dict[str, list[str]], distractors: int) -> str:
    """Build repeated-key format block. Each update overwrites the same label."""
    n = len(next(iter(fields.values())))
    rng = random.Random(42)
    lines: list[str] = []
    for i in range(n):
        for name, vals in fields.items():
            lines.append(f"Current {name}: {vals[i]}")
        for _ in range(distractors):
            lines.append(rng.choice(DISTRACTOR_LINES))
    return "\n".join(lines)


def _build_indexed_log(fields: dict[str, list[str]], distractors: int) -> str:
    """Build indexed-log format block. Each update has a sequence number."""
    n = len(next(iter(fields.values())))
    rng = random.Random(42)
    lines: list[str] = []
    for i in range(n):
        parts = " ".join(f"{name}={vals[i]}" for name, vals in fields.items())
        lines.append(f"[{i + 1}] {parts}")
        for _ in range(distractors):
            lines.append(rng.choice(DISTRACTOR_LINES))
    return "\n".join(lines)


def _make_task_data(
    n_updates: int,
    field_names: list[str],
    distractors_per_update: int,
    seed: int,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Generate field values and expected latest answers."""
    fields = {
        name: _generate_values(n_updates, name, seed + i)
        for i, name in enumerate(field_names)
    }
    expected = {name: vals[-1] for name, vals in fields.items()}
    return fields, expected


# --- Task definitions ---

TASK_SPECS = [
    {  # T1: simple single-field
        "n": 5, "fields": ["time"], "distractors": 0,
        "difficulty": "easy", "tags": ["single-field", "5-updates"],
    },
    {  # T2: multi-field few updates
        "n": 5, "fields": ["time", "temp", "status"], "distractors": 0,
        "difficulty": "easy", "tags": ["multi-field", "5-updates"],
    },
    {  # T3: single-field many updates
        "n": 20, "fields": ["price"], "distractors": 1,
        "difficulty": "medium", "tags": ["single-field", "20-updates"],
    },
    {  # T4: multi-field many updates
        "n": 20, "fields": ["cpu", "memory", "requests"], "distractors": 2,
        "difficulty": "medium", "tags": ["multi-field", "20-updates"],
    },
    {  # T5: dense multi-field
        "n": 50, "fields": ["time", "cpu", "memory", "disk", "connections"],
        "distractors": 3, "difficulty": "hard",
        "tags": ["multi-field", "50-updates", "dense"],
    },
    {  # T6: needle-in-haystack (handled specially below)
        "n": 30, "fields": ["cpu", "memory", "requests"],
        "distractors": 3, "difficulty": "hard",
        "tags": ["needle-in-haystack", "30-updates"],
    },
]


def _build_needle_fields(seed: int) -> tuple[dict[str, list[str]], dict[str, str]]:
    """T6: 3 fields update 30 times, plus 1 field changes only at update #7."""
    fields, expected = _make_task_data(30, ["cpu", "memory", "requests"], 0, seed)
    # Add a field that only changes once, at update 7
    alert_vals = ["none"] * 30
    alert_vals[6] = "disk_warning_sector_42"
    fields["alert"] = alert_vals
    expected["alert"] = "none"  # latest is "none" — the needle is that it reverted
    return fields, expected


def _build_question(expected: dict[str, str]) -> str:
    """Build the question asking for latest values."""
    field_list = ", ".join(expected.keys())
    return f"What are the current (latest) values of: {field_list}?"


def _build_check_fn(expected: dict[str, str]) -> str:
    """Build a check_fn expression that verifies all expected values in output."""
    checks = [f'"{v}" in output' for v in expected.values()]
    return " and ".join(checks)


def _build_system_prompts() -> tuple[str, str, list[TaskItem]]:
    """Build both system prompts and the shared task list."""
    repeated_sections: list[str] = []
    indexed_sections: list[str] = []
    tasks: list[TaskItem] = []

    for i, spec in enumerate(TASK_SPECS):
        seed = 1000 + i * 100

        if i == 5:  # T6 needle-in-haystack
            fields, expected = _build_needle_fields(seed)
        else:
            fields, expected = _make_task_data(
                spec["n"], spec["fields"], 0, seed,
            )

        distractors = spec["distractors"]
        label = f"--- TASK {i + 1} STATUS FEED ---"

        repeated_block = f"{label}\n{_build_repeated_key(fields, distractors)}"
        indexed_block = f"{label}\n{_build_indexed_log(fields, distractors)}"

        repeated_sections.append(repeated_block)
        indexed_sections.append(indexed_block)

        question = _build_question(expected)
        prompt = f"Look at TASK {i + 1} STATUS FEED. {question}"
        if i == 5:
            prompt += (
                " Note: for 'alert', report the LATEST value "
                "(not the most interesting one)."
            )

        tasks.append(TaskItem(
            prompt=prompt,
            expected=" | ".join(f"{k}={v}" for k, v in expected.items()),
            check_fn=_build_check_fn(expected),
            difficulty=spec["difficulty"],
            tags=spec["tags"],
        ))

    repeated_prompt = SYSTEM_INTRO + "\n\n".join(repeated_sections)
    indexed_prompt = SYSTEM_INTRO + "\n\n".join(indexed_sections)
    return repeated_prompt, indexed_prompt, tasks


repeated_prompt, indexed_prompt, tasks = _build_system_prompts()

experiment = Experiment(
    name="realtime_context_update",
    description=(
        "Compare two append-only status update formats for LLM context: "
        "repeated-key (same label each update) vs indexed-log (numbered entries). "
        "Tests recognition accuracy across 6 difficulty levels."
    ),
    diff=DiffSpec(
        field="system_prompt",
        description="repeated-key format vs indexed-log format for status updates",
    ),
    agent_a=AgentConfig(
        name="repeated_key",
        model="claude-haiku-4-5",
        system_prompt=repeated_prompt,
        allowed_tools=[],
        max_turns=1,
    ),
    agent_b=AgentConfig(
        name="indexed_log",
        model="claude-haiku-4-5",
        system_prompt=indexed_prompt,
        allowed_tools=[],
        max_turns=1,
    ),
    tasks=tasks,
    num_samples=8,
    tags=["realtime-context", "format-comparison", "kv-cache", "research"],
)
