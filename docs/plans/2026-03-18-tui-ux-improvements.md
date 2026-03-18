# Plan: TUI UX Improvements

Date: 2026-03-18

## Problem

Three dead spots where the user sees no progress:

1. `openbench run` — says "Running experiment…" then blocks silently until all tasks finish.
2. `autoloop` Planning phase — LLM call with no spinner.
3. `autoloop` Running phase — `runner.run()` blocks; per-task summary only appears **after** everything completes.
4. `autoloop` Evaluation phase — LLM judge call with no spinner.

## Goal

Real-time feedback at every blocking step. No more silent waits.

## Changes

### 1. `runner.py` — add `on_trial_done` callback

```python
def run(self, experiment, on_trial_done=None) -> ExperimentResult
```

Signature of callback: `on_trial_done(agent_name: str, task_index: int, ok: bool) -> None`
Called from `_run_and_store` after each trial completes.
Rich `Progress.advance()` is thread-safe so this works across anyio threads.

### 2. `cli.py` — live progress for `run` command

Replace static "Running experiment…" with a `Progress` that has two tasks (Agent A / Agent B),
each advancing as trials complete. Show latency once done.

### 3. `autoloop.py` — live feedback for all three phases

- **Planning**: wrap `self._planner.plan_*()` in `console.status("Planning…")`
- **Running**: pass a `Progress`-connected `on_trial_done` callback to `runner.run()`
- **Evaluating**: wrap `self._evaluator.evaluate()` in `console.status("Evaluating…")`
- **Iteration header**: upgrade from plain `Rule` to a `Rule` with budget inline
- **Budget bar**: show `$spent / $max` after each iteration

### 4. `compare.py` — winner banner

Add a prominent winner panel at the bottom of `compare()`.

## Files Changed

- `src/openbench/runner.py` (add callback)
- `src/openbench/autoloop.py` (spinners + progress)
- `src/openbench/cli.py` (live progress for `run`)
- `src/openbench/compare.py` (winner banner)

## Not Changing

- Storage, types, evaluator, planner, metrics — no logic changes.
- Experiment contract is unchanged.
