# Experiment Report: Competitive Programming (4 problems × 3 samples)

**Date:** 2026-03-20
**Run ID:** 39104c1b-08f9-457d-929c-a726b5101da8
**Model:** haiku vs sonnet at max_turns=20

---

## Problems

| # | Problem | Algorithm Required | Difficulty |
|---|---------|-------------------|------------|
| P1 | Longest subarray with exactly k distinct | Sliding window + hashmap | hard |
| P2 | Minimum jumps to reach end | Greedy O(n) | hard |
| P3 | Count inversions | Merge sort O(n log n) | very_hard |
| P4 | Trapping rain water | Two-pointer O(n) | hard |

All problems have performance tests (100k elements, must complete in <1-2s).
Naive O(n²) solutions will TLE.

---

## Results (corrected check_fn — original was too strict)

| Problem | haiku (3 samples) | sonnet (3 samples) |
|---------|-------------------|-------------------|
| P1: k-distinct subarray | **1/3 (33%)** | **1/3 (33%)** |
| P2: Min jumps | **3/3 (100%)** | **3/3 (100%)** |
| P3: Count inversions | **3/3 (100%)** | **3/3 (100%)** |
| P4: Rain water | **2/3 (67%)** | **3/3 (100%)** |
| **Total** | **9/12 (75%)** | **10/12 (83%)** |

### Efficiency Comparison

| Metric | haiku | sonnet | Delta |
|--------|-------|--------|-------|
| Avg turns | 25.8 | 13.8 | **-47%** |
| Avg tokens | 8,641 | 12,396 | +43% |
| Avg cost | $0.080 | $0.263 | +230% |
| Avg latency | 70s | 208s | +196% |

---

## Key Findings

### 1. P1 (k-distinct subarray) is genuinely hard — both fail 2/3
The "exactly k distinct" variant (not "at most k") requires a clever trick:
`atMost(k) - atMost(k-1)`. Both models sometimes get the basic sliding window
but miss the reduction. This is the first problem where model capability doesn't
help — it requires algorithmic insight that neither model reliably produces.

### 2. P2 and P3 are well-known — both ace them
Minimum jumps (greedy) and count inversions (merge sort) are textbook algorithms.
Both models implement them correctly and efficiently every time. 100% pass rate.

### 3. P4 (rain water) shows a real gap
Sonnet: 3/3 (100%). Haiku: 2/3 (67%). Haiku's failure was a subtlety in the
two-pointer approach. Small sample (n=3) but directionally meaningful.

### 4. Sonnet is dramatically more expensive on CP tasks
$0.263/trial vs $0.080 (3.3× more expensive) because sonnet's per-token price
is higher AND it generates more tokens on complex problems. However, sonnet
uses 47% fewer turns — it gets the algorithm right faster.

### 5. Haiku compensates with iteration
Haiku uses ~26 turns to sonnet's ~14. It tries, fails the performance test,
rethinks, and retries. This iterative approach works for P2-P4 but fails on P1
where the fundamental algorithm choice is wrong.

---

## Verdict

**Sonnet slightly better on competitive programming (83% vs 75%)**, driven by
P4 (rain water). Both fail equally on P1 (k-distinct subarray — requires
non-obvious reduction). P2 and P3 are too well-known to discriminate.

**For competitive programming, sonnet's first-shot accuracy on algorithm selection
matters more than haiku's ability to iterate.** When the initial algorithm choice
is wrong (P1), iteration doesn't help — you need to rethink fundamentally.
