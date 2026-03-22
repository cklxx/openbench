"""
Real-Time Context Update v4 — Observation Masking

v1-v3 finding: format barely matters; the model understands timestamps;
the real optimization is reducing data VOLUME, not tweaking format.

v4 question: how much history can we drop (replace with a placeholder)
while maintaining accuracy — and for which QUERY TYPES does masking fail?

Design: 50 timestamped entries, 3 fields + 1 rare event.
5 masking levels × 5 query types = 25 cells.

Masking levels (tournament):
- full:      all 50 entries
- last_20:   "[30 earlier updates omitted]" + entries 31-50
- last_10:   "[40 earlier updates omitted]" + entries 41-50
- last_5:    "[45 earlier updates omitted]" + entries 46-50
- summary_10: statistical summary of 1-40 + entries 41-50

Query types (tasks):
- T1: "What are the CURRENT values?" (latest — all levels should work)
- T2: "What was the PEAK cpu value?" (needs full or summary)
- T3: "How many times did cpu exceed 80%?" (counting — needs full)
- T4: "Was there ever an alert? If so, what?" (needle at entry #15)
- T5: "What were the values 2 hours ago?" (entry #26 — needs last_20+)
"""

import random

from openbench.types import AgentConfig, TaskItem, TournamentConfig

N_UPDATES = 50
FIELDS = ["cpu", "memory", "requests"]
SEED = 4000
ALERT_POSITION = 14  # 0-indexed, entry #15
BASE_HOUR = 10
INTERVAL_MIN = 5


def _gen_timestamps(n: int) -> list[str]:
    return [
        f"2024-03-21 {BASE_HOUR + (i * INTERVAL_MIN) // 60:02d}:"
        f"{(i * INTERVAL_MIN) % 60:02d}"
        for i in range(n)
    ]


def _gen_values(n: int, field: str, seed: int) -> list[str]:
    rng = random.Random(seed)
    gens = {
        "cpu": lambda: f"{rng.uniform(10.0, 95.0):.1f}%",
        "memory": lambda: f"{rng.uniform(20.0, 90.0):.1f}%",
        "requests": lambda: str(rng.randint(1000, 9999)),
    }
    return [gens[field]() for _ in range(n)]


def _build_full_data() -> tuple[list[str], dict[str, list[str]], list[str]]:
    """Build 50 entries with timestamps, field values, and alert column."""
    timestamps = _gen_timestamps(N_UPDATES)
    fields = {
        f: _gen_values(N_UPDATES, f, SEED + i)
        for i, f in enumerate(FIELDS)
    }
    alerts = ["none"] * N_UPDATES
    alerts[ALERT_POSITION] = "disk_failure_sector_7742"
    return timestamps, fields, alerts


def _format_entries(
    timestamps: list[str],
    fields: dict[str, list[str]],
    alerts: list[str],
    start: int,
    end: int,
) -> str:
    lines = []
    for i in range(start, end):
        parts = " ".join(f"{f}={fields[f][i]}" for f in FIELDS)
        alert_part = f" alert={alerts[i]}" if alerts[i] != "none" else ""
        lines.append(f"[{timestamps[i]}] {parts}{alert_part}")
    return "\n".join(lines)


def _compute_summary(
    timestamps: list[str],
    fields: dict[str, list[str]],
    alerts: list[str],
    start: int,
    end: int,
) -> str:
    """Pre-computed statistical summary (simulates LLM compaction)."""
    parts = []
    for f in FIELDS:
        vals = []
        for i in range(start, end):
            raw = fields[f][i].rstrip("%")
            vals.append(float(raw))
        unit = "%" if "%" in fields[f][0] else ""
        peak_i = start + vals.index(max(vals))
        parts.append(
            f"{f}: range {min(vals):.1f}{unit}-{max(vals):.1f}{unit}, "
            f"avg {sum(vals)/len(vals):.1f}{unit}, "
            f"peak at {timestamps[peak_i]}"
        )

    alert_events = [
        f"{alerts[i]} at {timestamps[i]}"
        for i in range(start, end)
        if alerts[i] != "none"
    ]
    alert_line = (
        f"Alerts: {'; '.join(alert_events)}"
        if alert_events
        else "Alerts: none"
    )

    period = f"{timestamps[start]} to {timestamps[end - 1]}"
    return (
        f"Summary of updates {start + 1}-{end} ({period}):\n"
        + "\n".join(f"  {p}" for p in parts)
        + f"\n  {alert_line}"
    )


def _build_system_prompts() -> dict[str, str]:
    """Build system prompts for each masking level."""
    timestamps, fields, alerts = _build_full_data()
    base_instruction = (
        "You are a monitoring assistant. Read the status updates below and "
        "answer questions precisely. When data is summarized or omitted, "
        "work with what you have — say 'unknown' if the answer requires "
        "data you don't have.\n\n"
    )

    full_block = _format_entries(timestamps, fields, alerts, 0, 50)

    configs = {}

    # full
    configs["full"] = base_instruction + f"Status updates:\n{full_block}"

    # last_N variants
    for n in [20, 10, 5]:
        start = 50 - n
        omitted = start
        visible = _format_entries(timestamps, fields, alerts, start, 50)
        configs[f"last_{n}"] = (
            base_instruction
            + f"Status updates:\n"
            f"[...{omitted} earlier updates omitted...]\n"
            + visible
        )

    # summary + last 10
    summary = _compute_summary(timestamps, fields, alerts, 0, 40)
    recent = _format_entries(timestamps, fields, alerts, 40, 50)
    configs["summary_10"] = (
        base_instruction
        + f"{summary}\n\nRecent updates:\n{recent}"
    )

    return configs


# --- Build expected answers ---

def _build_expected() -> dict[str, tuple[str, str, str]]:
    """Return {task_name: (question, expected, check_fn)}."""
    timestamps, fields, alerts = _build_full_data()

    # T1: Current values (latest entry = index 49)
    latest = {f: fields[f][49] for f in FIELDS}
    t1_expected = ", ".join(f"{f}={v}" for f, v in latest.items())
    t1_check = " and ".join(f'"{v}" in output' for v in latest.values())

    # T2: Peak cpu
    cpu_vals = [float(v.rstrip("%")) for v in fields["cpu"]]
    peak_idx = cpu_vals.index(max(cpu_vals))
    peak_val = fields["cpu"][peak_idx]
    peak_ts = timestamps[peak_idx]

    # T3: Count cpu > 80%
    count_80 = sum(1 for v in cpu_vals if v > 80.0)

    # T4: Alert needle (entry #15, index 14)
    alert_val = alerts[ALERT_POSITION]
    alert_ts = timestamps[ALERT_POSITION]

    # T5: Values 2 hours ago = entry at 10:00 + 2h = 12:00
    # 12:00 is entry index 24 (24 * 5min = 120min = 2h)
    ts_2h_ago = timestamps[24]
    vals_2h = {f: fields[f][24] for f in FIELDS}
    t5_expected = ", ".join(f"{f}={v}" for f, v in vals_2h.items())
    t5_check = " and ".join(f'"{v}" in output' for v in vals_2h.values())

    return {
        "t1_current": (
            "What are the CURRENT (latest) values of cpu, memory, and requests?",
            t1_expected,
            t1_check,
        ),
        "t2_peak": (
            "What was the PEAK (highest) cpu value across all updates, "
            "and at what timestamp did it occur?",
            f"peak={peak_val} at {peak_ts}",
            f'"{peak_val}" in output',
        ),
        "t3_count": (
            "How many times did cpu EXCEED 80%? Give the exact count.",
            f"count={count_80}",
            f'"{count_80}" in output',
        ),
        "t4_alert": (
            "Was there ever a non-'none' alert in the updates? "
            "If yes, what was the alert value and when?",
            f"alert={alert_val} at {alert_ts}",
            '"disk_failure_sector_7742" in output',
        ),
        "t5_historical": (
            f"What were the cpu, memory, and requests values at timestamp "
            f"{ts_2h_ago}?",
            t5_expected,
            t5_check,
        ),
    }


# --- Assemble ---

prompts = _build_system_prompts()
expected = _build_expected()

configs = [
    AgentConfig(
        name=name,
        model="claude-haiku-4-5",
        system_prompt=prompts[name],
        allowed_tools=[],
        max_turns=1,
    )
    for name in ["full", "last_20", "last_10", "last_5", "summary_10"]
]

tasks = [
    TaskItem(
        prompt=q,
        expected=exp,
        check_fn=chk,
        difficulty=diff,
        tags=tags,
    )
    for (q, exp, chk), diff, tags in [
        (expected["t1_current"], "easy", ["latest-value"]),
        (expected["t2_peak"], "medium", ["aggregation", "peak"]),
        (expected["t3_count"], "medium", ["aggregation", "count"]),
        (expected["t4_alert"], "hard", ["needle-in-haystack"]),
        (expected["t5_historical"], "medium", ["historical-lookup"]),
    ]
]

tournament = TournamentConfig(
    name="realtime_context_update_v4",
    description=(
        "Observation masking: how much history can we drop? "
        "5 masking levels × 5 query types. Tests latest-value, peak, "
        "count, needle-in-haystack, and historical lookup."
    ),
    configs=configs,
    tasks=tasks,
    num_samples=8,
    tags=["observation-masking", "context-compression", "research"],
)
