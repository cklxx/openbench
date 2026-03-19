# Experiment Report: Turn Budget Scaling

**Date:** 2026-03-19
**Experiment:** `turn_budget_scaling` (4-way tournament, 1 task × 3 samples)

---

## Setup

Same URL shortener task (9 test cases), same model (haiku), only max_turns differs.

| Agent | max_turns |
|-------|-----------|
| turns_05 | 5 |
| turns_10 | 10 |
| turns_20 | 20 |
| turns_40 | 40 |

3 independent samples per pair for statistical signal.

---

## Leaderboard

| Rank | Agent | Correctness % | Consistency |
|------|-------|--------------|-------------|
| 1 | **turns_20** | **100%** (9/9 across 3 pairs) | 3/3 all correct |
| 2 | **turns_40** | **100%** (9/9 across 3 pairs) | 3/3 all correct |
| 3 | turns_10 | 89% (8/9) | 2/3 — failed once vs turns_40 |
| 4 | turns_05 | 67% (6/9) | Inconsistent — 1/3, 2/3, 3/3 depending on run |

---

## Key Findings

### 1. Diminishing returns start at max_turns=20
turns_20 and turns_40 are identical in correctness (both 100%). The extra 20
turns are never used. **20 turns is sufficient** for this task complexity.

### 2. max_turns=5 is a gamble (67% success)
With only 5 turns, the agent sometimes can't complete the read-write-test-fix
cycle. Typical flow needs ~7-10 tool calls, so 5 turns is cutting it close.
When it works, it's the fastest and cheapest. When it fails, the output is
incomplete (agent runs out of turns mid-fix).

### 3. max_turns=10 is the sweet spot for this task
88.9% correctness, roughly half the cost of turns_20/40. The one failure was
a borderline case where the agent needed one more iteration.

### 4. The URL shortener is solvable in ~10-15 turns
Actual turn usage (from SDK reports):
- Read test file: 2-3 turns
- Write implementation: 1-2 turns
- Run tests: 1 turn
- Fix failures: 2-4 turns
- Re-run tests: 1 turn
Total: 7-12 turns typically

### 5. turns_40 doesn't use extra turns
The agent naturally stops after solving the task (~12 turns). Extra budget
is unused. However, the safety margin prevents failures on harder runs.

---

## Cost Comparison

| Agent | Avg Cost | Relative |
|-------|----------|----------|
| turns_05 | ~$0.02 | 1x |
| turns_10 | ~$0.04 | 2x |
| turns_20 | ~$0.05 | 2.5x |
| turns_40 | ~$0.05 | 2.5x (same as 20!) |

Turns 20 and 40 cost the same because the agent stops early.

---

## Verdict

**max_turns=20 is optimal**: 100% correctness, same cost as 40, enough
headroom for hard iterations. For cost-sensitive use, max_turns=10 gives
~90% success at half the cost.

**Rule of thumb**: Set max_turns to 2× the expected number of tool calls.
For a task requiring ~10 tool interactions, 20 turns is the right budget.
