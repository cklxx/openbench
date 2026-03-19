# Experiment Report: Multi-File Project — Expression Calculator

**Date:** 2026-03-19
**Run ID:** e673fb26-f669-42b3-91b3-b6001d6965fd
**Experiment:** `multi_file_project` (max_turns=30, 2 samples)

---

## Setup

Build a complete expression calculator from scratch: tokenizer, recursive-descent
parser, evaluator, variable support, error handling. Must pass 11 test cases.

---

## Results

| Metric | haiku | sonnet |
|--------|-------|--------|
| **Actual correctness** | **4/4 all pass** | **4/4 all pass** |
| Reported correctness* | 2/2 | 0/2 |
| Avg turns used | 18 | 9 |
| Avg tool calls | 6.0 | 5.0 |
| Avg tokens | 4,134 | 2,828 |
| Avg cost | $0.046 | $0.092 |

*check_fn false negatives: "tests pass" vs "tests passed" — see below.

### check_fn Bug

The check_fn searched for "passed" in output, but sonnet wrote "tests pass"
(present tense). Both agents successfully built the calculator and passed all
11/11 tests. The reported 0/2 for sonnet is a **false negative**.

**Lesson**: check_fn should use `.lower()` matching with multiple verb forms,
or better yet, check the actual test execution output rather than agent prose.

---

## Actual Analysis (all 4 runs passed 11/11 tests)

### Implementation Patterns

**haiku** (2 samples):
- Run 1: 21 turns, 7 tools — Read test → failed first attempt → Read test again
  → Write fixed impl → Run tests → Fix more → Run tests → Pass
- Run 2: 15 turns, 5 tools — Read test → Bash (inspect) → Read test → Write impl
  → Run tests → Pass first time

**sonnet** (2 samples):
- Run 1: 9 turns, 5 tools — Bash inspect → Read test → Read test → Write impl
  → Run tests → Pass first time
- Run 2: 9 turns, 5 tools — identical pattern, pass first time

### Sonnet is 2× more efficient
Sonnet consistently completes in 9 turns / 5 tool calls. Haiku varies from
15-21 turns / 5-7 tool calls. Sonnet generates the recursive-descent parser
correctly on first attempt; haiku sometimes needs iteration.

### Both produce high-quality implementations
All 4 implementations use proper recursive-descent parsing with correct
operator precedence. Both handle edge cases (negative numbers, variables,
error handling). The architectures are essentially identical — the difference
is that sonnet gets there in one shot.

### Haiku is 2× cheaper
haiku: $0.046/run vs sonnet: $0.092/run. Despite more tokens, haiku's
lower per-token price makes it the cost-effective choice.

---

## Verdict

**Both build fully functional expression calculators. Sonnet is 2× faster
(9 vs 18 turns) and 32% fewer tokens. Haiku is 2× cheaper.**

For implementation tasks at this complexity level (~11 test cases, single
file, well-defined spec), both models are equally capable. The choice is
speed (sonnet) vs cost (haiku).

---

## Next Experiment

Test with genuinely harder tasks that might differentiate models on correctness:
- Multi-file with import dependencies
- Concurrent/async code
- Complex state machines
- Tasks requiring architectural decisions (not just implementation)
