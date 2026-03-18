# TUI UX Research Report — OpenBench

Date: 2026-03-18

## 1. Problem Statement

OpenBench's CLI had three "black hole" phases where the user saw no progress:

| Phase | Before |
|---|---|
| `openbench run` — experiment execution | Static text "Running experiment… (this may take a while)" then silent block |
| `autoloop` — Planning | No indicator while LLM call runs |
| `autoloop` — Running | `runner.run()` blocks; per-task results dumped only after all tasks finish |
| `autoloop` — Evaluation | No indicator while LLM judge runs |

---

## 2. UX Patterns Researched

### 2.1 Rich `Progress` for Determinate Tasks

Rich's `Progress` is the right primitive when you know total work units upfront.
Key design: use a callback to advance the bar from inside async/blocking execution.

```python
with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    MofNCompleteColumn(),
    TimeElapsedColumn(),
    console=console,
    transient=True,   # clears bar after done, cleaner output
) as progress:
    task = progress.add_task("Agent A", total=num_trials)

    def on_done(agent_name, task_index, ok):
        progress.advance(task)

    result = runner.run(experiment, on_trial_done=on_done)
```

**Thread safety**: Rich's `Progress` uses an internal `RLock` and a background refresh thread. Calling `progress.advance()` from any thread (including anyio's event loop thread) is safe.

### 2.2 Rich `console.status()` for Indeterminate Tasks

For LLM calls where duration is unknown, `console.status()` (a spinner) is preferred over a progress bar. It signals "working" without implying a known total.

```python
with console.status("[bold cyan]Planning[/bold cyan] — generating hypothesis…"):
    step = planner.plan_initial(program)
```

The status spinner is displayed while the `with` block runs; it disappears when done.

### 2.3 `transient=True` vs Persistent Bars

- `transient=True`: Progress bar erases itself after completion, leaving only the final summary. Cleaner for multi-phase workflows.
- `transient=False` (default): Bar stays visible as a record. Good for standalone commands like `openbench run`.

OpenBench uses `transient=True` inside `autoloop` (iterations repeat) and `transient=False` for the standalone `run` command.

### 2.4 Visual Hierarchy

Rich's `Rule` with embedded cost info provides a clear iteration separator:

```
──────── Iteration 2/3  $0.124/$2.00 (6%) ────────
```

Each phase uses `▶ Plan`, `▶ Run results`, `▶ Scores` prefix for consistent labeling.

### 2.5 Winner Panels

Rich `Panel` with colored border provides a strong visual anchor for the final verdict. Using `expand=False` keeps it compact:

```python
Panel(
    "Agent B: with-cot-v2\nSuccess 3/3 · Latency 1.24s vs 2.11s",
    title="Recommended Winner",
    border_style="blue",
    expand=False,
)
```

---

## 3. Changes Implemented

### `runner.py`
Added optional `on_trial_done(agent_name, task_index, ok)` callback to `ExperimentRunner.run()`. Called after each trial completes inside `_run_and_store`. Zero-overhead when not provided.

### `cli.py` — `run` command
Replaced static banner with a live `Progress` bar showing per-agent advance as trials complete. Uses `transient=False` so the final bar state is visible after run.

### `autoloop.py`
- **Planning phase**: wrapped with `console.status()` spinner.
- **Running phase**: full `Progress` bar with two rows (Agent A / Agent B), `transient=True`. Per-task summary printed after the bar closes.
- **Evaluation phase**: wrapped with `console.status()` spinner.
- **Iteration header**: `Rule` now includes `$spent/$max (pct%)` budget inline.
- **Scores line**: condensed to single line: `A=72.3  B=85.1  Winner=B: with-cot-v2 (+12.8pts, conf=0.85)`.

### `compare.py`
Added `_print_winner_banner()` using `Panel` with color-coded border at the end of every comparison report.

---

## 4. Before / After

### Before (autoloop running phase)
```
▶ Running — executing A/B experiment...
[... 45 seconds of silence ...]
  Task 1: 'Write a function that...'
    A [✓] 12.3s 1420tok  B [✓] 9.8s 980tok
  Task 2: 'Explain the concept of...'
    A [✓] 8.1s 890tok  B [✓] 7.2s 760tok
```

### After (autoloop running phase)
```
▶ Plan  "Hypothesis: concise CoT improves quality vs verbose baseline"
  Experiment: cot-prompt-v1  diff=system_prompt: adds chain-of-thought prefix
  baseline vs with-cot  —  3 task(s)

⠹ A: baseline task 1/3         ██████░░░░░░   2/6   0:00:12
⠸ B: with-cot  task 1/3        ████░░░░░░░░   2/6   0:00:12

▶ Run results
  T1 ✓12.3s 1420tok  ✓9.8s 980tok  'Write a function that...'
  T2 ✓8.1s 890tok   ✓7.2s 760tok  'Explain the concept of...'
  T3 ✓11.2s 1100tok ✓8.9s 820tok  'Debug this code...'

▶ Scores  A=72.3  B=85.1  Winner=B: with-cot (+12.8pts, conf=0.85)
  The chain-of-thought prompt consistently produced more structured outputs…
```

---

## 5. Key Findings

1. **Callback pattern is the cleanest bridge** between async runners and synchronous Rich displays. No shared state, no extra threads — just call `progress.advance()` from the trial completion hook.

2. **`console.status()` > `console.print()` for LLM calls**. Spinners communicate "waiting for external service" idiomatically. Users tolerate unknown waits better when there's motion.

3. **`transient=True` inside loops, `transient=False` for standalone**. Persistent bars inside a loop create visual noise; transient bars leave clean text output while still providing live feedback during the wait.

4. **Single-line phase summaries scale better** than multi-line blocks when iterations repeat. The before style printed 4–6 lines per task; the after compresses to 1 line per task.

5. **Budget visibility reduces anxiety**. Showing `$0.12/$2.00 (6%)` on each iteration header lets users decide to `Ctrl-C` early if cost is climbing fast.

---

## 6. Research Validation

The Rich source-level research confirms our implementation choices:

| Choice | Validated by |
|---|---|
| `progress.update()` called directly from `async def` (no bridging) | Rich `Progress` update is pure sync — just acquires `RLock`, no I/O. Safe from async coroutines. |
| `console.status()` for indeterminate LLM calls | Canonical pattern in Rich docs. `status.update()` lets you change the label mid-call. |
| `transient=True` in autoloop, `transient=False` in `run` | Rich docs: transient clears bar after `with` exits — right for repeating phases. |
| Separate `Progress` context per iteration | Avoids nested `Live` issues (prior to Rich 14.0 only one active `Live` at a time). |
| Callback advances bar, not the runner itself | Same thread-safety pattern as Rich's `downloader.py` example with `ThreadPoolExecutor`. |

**One future upgrade worth noting**: the `dynamic_progress.py` pattern (Phase bar + Step bar + Overall bar in a single `Live(Group(...))`) would provide an even richer display — but it requires keeping one `Live` context alive for the full autoloop, which is a bigger refactor. The current per-iteration `Progress` approach is simpler and correct.

---

## 7. Recommendations for Future Work

- **Ctrl-C graceful stop**: wrap the autoloop in a `try/except KeyboardInterrupt` and print a partial summary with best config found so far.
- **Live cost in progress description**: update progress description with `$cost` after each trial completes using `progress.update(task, description=f"… ${cost:.4f}")`.
- **`openbench watch` command**: a `Live` display that polls `results/` and auto-refreshes the latest experiment status — useful for long experiments left running in background.
