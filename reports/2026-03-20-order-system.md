# Experiment Report: Order Processing System (12 test cases × 3 samples)

**Date:** 2026-03-20
**Run ID:** 9f1e03fc-d093-4d63-a69c-990428a4be19
**Model:** haiku vs sonnet at max_turns=30

---

## Task

Build a complete order processing system from scratch:
- State machine (PENDING → CONFIRMED → SHIPPED → DELIVERED, or CANCELLED)
- Inventory management (check/decrement/restore stock)
- Multi-item orders with price calculation
- Event logging for all transitions
- Error handling (invalid transitions, insufficient stock, unknown products)
- 12 comprehensive test cases

---

## Results (corrected check — all outputs say "12/12 passed")

| Agent | Pass Rate | Avg Turns | Avg Tokens | Avg Cost |
|-------|-----------|-----------|------------|----------|
| **haiku** | **3/3 (100%)** | 16.3 | 4,340 | $0.047 |
| **sonnet** | **3/3 (100%)** | 8.0 | 2,968 | $0.093 |

**Both agents pass all 12 tests in every sample.** The check_fn false negatives
(reported as 1/3 vs 3/3) were due to matching "ALL TESTS PASSED" literally when
agents write "All 12 tests passed!" or "12/12 tests pass".

---

## Efficiency Comparison

| Metric | haiku | sonnet | Winner |
|--------|-------|--------|--------|
| Turns | 16.3 | **8.0** | sonnet (-51%) |
| Tokens | 4,340 | **2,968** | sonnet (-32%) |
| Tool calls | 5.7 | **4.0** | sonnet (-30%) |
| Cost | **$0.047** | $0.093 | haiku (-49%) |
| Latency | **34.8s** | 49.3s | haiku (-30%) |

---

## Key Findings

### 1. Both models handle multi-component system design
The order system requires understanding state machines, inventory atomicity,
error handling, and event logging. Both haiku and sonnet implement all 12 test
cases correctly on every attempt.

### 2. Sonnet is the one-shot architect
Sonnet reads the test file once, writes a complete implementation, runs tests,
passes. 8 turns, 4 tool calls. Clean, correct, first try.

### 3. Haiku iterates to the same result
Haiku reads tests, writes a first attempt, runs tests, finds 1-2 failures
(usually event log format or cancel-after-confirm stock restore), fixes, re-runs.
16 turns, 6 tool calls. Same end result.

### 4. System design doesn't differentiate models on correctness
Unlike competitive programming (where algorithm selection matters), system design
is more about completeness and attention to detail. Both models handle it equally
well — sonnet just does it in fewer iterations.

---

## Verdict

**Tied on correctness (both 100%). Haiku wins on cost (-49%), sonnet wins on
efficiency (-51% turns).** For system design tasks at this complexity level,
model choice is purely about cost vs speed.
