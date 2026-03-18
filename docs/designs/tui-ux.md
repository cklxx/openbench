# Design: TUI UX Improvements

Generated from CEO review on 2026-03-18.
Branch: main | Mode: SELECTIVE EXPANSION

---

## Problem

Three dead spots where the user sees no progress:

1. `openbench run` — says "Running experiment…" then blocks silently until done.
2. `autoloop` Planning phase — LLM call with no spinner.
3. `autoloop` Running phase — per-task summary only appears **after** everything completes.
4. `autoloop` Evaluation phase — LLM judge call with no spinner.

## 12-Month Vision

A live experiment dashboard: each trial streams token output in a side panel,
a latency heatmap builds in real-time, the diff between A and B outputs is
highlighted as trials complete, and a confidence interval updates live so you
know when you've seen enough. The terminal becomes an experiment IDE.

Practical path: Textual-based TUI with streaming SDK output piped to a viewport
and persistent run history browsable with arrow keys.

---

## This Plan (Shipped / In Progress)

### Core changes (committed or working tree)

| File | Change |
|------|--------|
| `runner.py` | Add `on_trial_done(agent_name, task_index, ok)` callback |
| `cli.py` | Live `Progress` bars (A/B) in `openbench run` |
| `autoloop.py` | Three-layer `Live` display: phase spinners, trial bars, overall bar |
| `compare.py` | Winner banner at end of compare output |
| `planner.py` | Adversarial critique pass (`_critique_and_revise`) on initial plan |

### Accepted scope additions (cherry-picks from review)

1. **ETA in progress bar** — `TimeRemainingColumn` in cli.py and autoloop.py
2. **Critique on plan_next** — `_critique_and_revise()` called for all iterations, not just initial
3. **All-failures guard** — Winner banner shows "No clear winner" when all trials error
4. **Decision signal note** — Winner banner explains which signal was used (success rate / latency / cost)
5. **Live cost in `openbench run`** — Expand `on_trial_done` signature to include `cost_usd`; show running cost in progress description
6. **Tests** — Unit tests for: `on_trial_done` call count, winner banner logic, `_critique_and_revise` revisions

### Inline fix

- Update `_PLAN_COST_EST = 0.06` → `0.12` in autoloop.py (two Opus calls per plan now)

---

## Architecture

```
openbench run experiment.py
     │
     ├─▶ Progress(SpinnerColumn, BarColumn, MofNComplete, TimeElapsed, ETA)
     │        task_a, task_b
     │
     ├─▶ ExperimentRunner.run(experiment, on_trial_done=cb)
     │        │
     │        └─▶ anyio.run(_run_async, experiment, cb)
     │                  │
     │                  └─▶ for each task:
     │                            anyio task group:
     │                              _run_and_store(agent_a, ..., cb)
     │                              _run_and_store(agent_b, ..., cb)
     │                                     │
     │                                     └─▶ cb(name, idx, ok, cost_usd)
     │                                              │
     │                                              └─▶ progress.advance + update description
     │
     └─▶ compare(result)
               └─▶ _print_winner_banner()
                         ├─▶ succ_a > succ_b → A wins
                         ├─▶ succ_b > succ_a → B wins
                         ├─▶ tie → latency tiebreak + signal note
                         └─▶ all zero → "No clear winner"
```

## Winner Banner States

```
NORMAL (clear winner):
┌─ Recommended Winner ──────────────────────────────┐
│ Agent A: baseline                                  │
│ Success 3/3 vs 2/3 · Latency 4.2s vs 5.1s        │
│ Decision: A won on success rate                   │
└────────────────────────────────────────────────────┘

TIE (equal success):
┌─ Recommended Winner ──────────────────────────────┐
│ Agent A: baseline                                  │
│ Success 3/3 vs 3/3 · Latency 4.2s vs 4.5s        │
│ Tie on success · A edges on latency               │
└────────────────────────────────────────────────────┘

ALL-ERRORS:
┌─ No Clear Winner ─────────────────────────────────┐
│ All trials errored — check your experiment config  │
└────────────────────────────────────────────────────┘
```

---

## Known Gaps / Future Work

- **Streaming token output** during trials (requires SDK streaming support)
- **Textual TUI** for interactive experiment browsing (Phase 2)
- **Per-trial adaptive ETA** (vs. simple linear projection from first trial)
- **Run history browser** — compare across multiple runs with arrow keys
- **Diff viewer** — highlight what changed between A and B outputs inline

---

## Critical Issues to Fix Before Committing

1. `on_trial_done` exception propagation: if `progress.advance()` raises,
   it cancels all running trials. Wrap the callback invocation in a try/except
   in `_run_and_store`.
2. `_critique_and_revise` empty tasks: if the LLM returns `revised_tasks: []`,
   the plan's tasks are silently cleared. Guard: only apply if list is non-empty.
3. All-failures winner banner: shows misleading winner (cherry-pick #3 fixes this).
