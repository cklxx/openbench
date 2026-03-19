# Experiment Report: Verified Math Tournament

**Date:** 2026-03-19
**Experiment:** `verified_math_tournament` (3-way, 10 tasks, all answers Python-verified)

---

## Leaderboard

| Rank | Agent | Model | Correctness (avg) |
|------|-------|-------|-------------------|
| 1 | **haiku_code** | haiku + Bash | **80%** (8/10 × 2 pairs) |
| 1 | **sonnet** | sonnet (no tools) | **80%** (8/10 × 2 pairs) |
| 3 | haiku | haiku (no tools) | **70%** (7/10 × 2 pairs) |

## Per-Task Correctness

| Task | Diff | haiku | haiku_code | sonnet |
|------|------|-------|-----------|--------|
| T1: Chickens & rabbits | easy | ✓✓ | ✓✓ | ✓✓ |
| T2: Water tank rates | medium | ✓✓ | ✓✓ | ✓✓ |
| T3: Compound interest | medium | ✗✓ | ✓✓ | ✓✓ |
| T4: Permutations w/ constraint | medium | ✓✓ | ✓✓ | ✓✓ |
| T5: Bouncing ball distance | hard | ✓✓ | ✓✓ | ✓✓ |
| T6: 7^100 mod 13 | hard | ✗✗ | ✗✓ | ✗✗ |
| T7: Digit sum 1-999 | hard | ✗✗ | ✗✗ | ✗✗ |
| T8: F(50) mod 100 | hard | ✓✓ | ✓✓ | ✓✓ |
| T9: Birthday probability | v_hard | ✓✓ | ✓✓ | ✓✓ |
| T10: Non-attacking rooks | v_hard | ✓✓ | ✓✓ | ✓✓ |

## Key Findings

1. **haiku_code = sonnet at 80%** — Bash access on haiku matches sonnet's pure reasoning.
   Cost: haiku_code ~$0.10 vs sonnet ~$0.11 per run. haiku_code is slightly cheaper.

2. **T3 (compound interest) differentiates haiku vs others** — haiku failed once (1/2),
   both haiku_code and sonnet always got it right. Code verification catches arithmetic errors.

3. **T6 (modular arithmetic) is unreliable for all** — haiku_code got it 1/2 times,
   everyone else failed. The Python pow(7,100,13) should guarantee correctness for
   haiku_code, but the agent sometimes doesn't use the right approach.

4. **T7 (digit sum) stumps everyone** — All 3 agents failed. The answer is 13500,
   which requires recognizing a symmetry pattern (each digit 0-9 appears equally
   in each position). Without that insight, manual summation fails.

5. **Fixing expected answers matters** — T2 (water tank) now shows 100% correctness
   across all agents. Last experiment showed 0% because the expected answer was wrong.

---

## Conclusion

**Tool access (Bash) is equivalent to model upgrade (haiku→sonnet) for math.**
Both achieve 80% vs haiku's 70%. The remaining 20% failures (T6, T7) require
either reliable code generation (T6) or mathematical insight that neither
strategy provides (T7).
