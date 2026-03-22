"""
Real-Time Context Update v3 — Serialization Format Token Efficiency

v1 finding: repeated-key and indexed-log have same accuracy (~99%).
Research finding: TOON format saves 30-60% tokens vs JSON on uniform arrays.

v3 question: across 4 serialization formats, which gives the best
accuracy-per-token for status update recognition?

Formats (all append-only, all contain the same data):
1. key_value:  `cpu: 72.3% | memory: 90.5% | requests: 1946`
2. indexed:    `[1] cpu=72.3% memory=90.5% requests=1946`
3. json:       `{"cpu": "72.3%", "memory": "90.5%", "requests": "1946"}`
4. toon:       header row + CSV-like data rows

Tournament format: 4 agents, same tasks, compare accuracy and token counts.
"""

import random

from openbench.types import AgentConfig, TaskItem, TournamentConfig

SYSTEM_PROMPT = (
    "You are a monitoring assistant. Read the status updates below and "
    "answer questions about the CURRENT (latest) state. Be precise — "
    "output only the requested values, one per line."
)


def _gen_values(n: int, field: str, seed: int) -> list[str]:
    rng = random.Random(seed)
    gens = {
        "cpu": lambda: f"{rng.uniform(10.0, 95.0):.1f}%",
        "memory": lambda: f"{rng.uniform(20.0, 90.0):.1f}%",
        "requests": lambda: str(rng.randint(1000, 9999)),
        "errors": lambda: str(rng.randint(0, 50)),
        "latency_ms": lambda: str(rng.randint(5, 500)),
    }
    return [gens[field]() for _ in range(n)]


def _build_data(
    n: int, field_names: list[str], seed: int,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    fields = {
        f: _gen_values(n, f, seed + i)
        for i, f in enumerate(field_names)
    }
    expected = {f: vals[-1] for f, vals in fields.items()}
    return fields, expected


# --- Format builders ---

def _fmt_key_value(fields: dict[str, list[str]]) -> str:
    n = len(next(iter(fields.values())))
    lines = []
    for i in range(n):
        parts = " | ".join(f"{f}: {vals[i]}" for f, vals in fields.items())
        lines.append(parts)
    return "\n".join(lines)


def _fmt_indexed(fields: dict[str, list[str]]) -> str:
    n = len(next(iter(fields.values())))
    lines = []
    for i in range(n):
        parts = " ".join(f"{f}={vals[i]}" for f, vals in fields.items())
        lines.append(f"[{i + 1}] {parts}")
    return "\n".join(lines)


def _fmt_json(fields: dict[str, list[str]]) -> str:
    import json
    n = len(next(iter(fields.values())))
    lines = []
    for i in range(n):
        obj = {f: vals[i] for f, vals in fields.items()}
        lines.append(json.dumps(obj))
    return "\n".join(lines)


def _fmt_toon(fields: dict[str, list[str]]) -> str:
    """TOON format: header row + CSV-like data rows."""
    n = len(next(iter(fields.values())))
    header = ", ".join(fields.keys())
    rows = []
    for i in range(n):
        row = ", ".join(vals[i] for vals in fields.values())
        rows.append(row)
    return header + "\n" + "\n".join(rows)


FORMATTERS = {
    "key_value": _fmt_key_value,
    "indexed": _fmt_indexed,
    "json_lines": _fmt_json,
    "toon": _fmt_toon,
}


# --- Task definitions ---

TASK_SPECS = [
    {"n": 10, "fields": ["cpu", "memory", "requests"],
     "difficulty": "easy", "tags": ["10-updates", "3-fields"]},
    {"n": 30, "fields": ["cpu", "memory", "requests", "errors"],
     "difficulty": "medium", "tags": ["30-updates", "4-fields"]},
    {"n": 50, "fields": ["cpu", "memory", "requests", "errors", "latency_ms"],
     "difficulty": "hard", "tags": ["50-updates", "5-fields"]},
]


def _make_configs() -> tuple[list[AgentConfig], list[TaskItem]]:
    """Build 4 agent configs (one per format) and shared tasks."""
    # For each format, the system_prompt embeds ALL task data blocks
    # (labeled TASK 1, TASK 2, TASK 3)
    format_blocks: dict[str, list[str]] = {name: [] for name in FORMATTERS}
    tasks: list[TaskItem] = []

    for ti, spec in enumerate(TASK_SPECS):
        seed = 3000 + ti * 100
        fields, expected = _build_data(spec["n"], spec["fields"], seed)

        for name, fmt_fn in FORMATTERS.items():
            block = f"--- TASK {ti + 1} ---\n{fmt_fn(fields)}"
            format_blocks[name].append(block)

        field_list = ", ".join(expected.keys())
        question = (
            f"Look at TASK {ti + 1}. "
            f"What are the current (latest) values of: {field_list}?"
        )
        check_fn = " and ".join(f'"{v}" in output' for v in expected.values())

        tasks.append(TaskItem(
            prompt=question,
            expected=" | ".join(f"{k}={v}" for k, v in expected.items()),
            check_fn=check_fn,
            difficulty=spec["difficulty"],
            tags=spec["tags"],
        ))

    configs = []
    for name in FORMATTERS:
        data_block = "\n\n".join(format_blocks[name])
        configs.append(AgentConfig(
            name=name,
            model="claude-haiku-4-5",
            system_prompt=f"{SYSTEM_PROMPT}\n\n{data_block}",
            allowed_tools=[],
            max_turns=1,
        ))

    return configs, tasks


configs, tasks = _make_configs()

tournament = TournamentConfig(
    name="realtime_context_update_v3",
    description=(
        "Compare 4 serialization formats (key_value, indexed, json_lines, toon) "
        "for status update recognition. Same data, different encoding. "
        "Measures accuracy AND token efficiency."
    ),
    configs=configs,
    tasks=tasks,
    num_samples=8,
    tags=["format-comparison", "token-efficiency", "toon", "research"],
)
