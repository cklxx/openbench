# Self-Correction Strategy & Working Memory — Deep Dive

**Date:** 2026-03-23
**Experiments:** 6 runs across 3 research directions

---

## Direction 1: Self-Correction Strategy

### v1: Independent Bugs (Refine Wins)

**Result: refine 18/20 (90%) vs pivot 14/20 (70%)**

| Task | pivot | refine |
|:--|:-:|:-:|
| T1: Inventory (+ vs *, qty vs value) | 4/5 | 5/5 |
| T2: TextStats (len vs split, min vs max) | 5/5 | 5/5 |
| T3: PQueue (sort direction, size off-by-one) | 4/5 | 5/5 |
| T4: Grades (formula, boundary >=) | 1/5 | 3/5 |

Refine wins because keeping a correct partial fix and adding the missing fix is more efficient than reverting everything. Pivot wastes turns on `git checkout`, re-reading, and directory navigation.

### v2: Deceptive Bugs (Refine Still Wins)

**Hypothesis:** Tasks where the error message suggests a WRONG fix should favor pivot, because reverting a wrong fix gives a cleaner state.

**Design:** 4 tasks with "swapped arguments" bugs — the error output suggests one fix but the real bug is different:
- T1: `normalize(s, src_max, src_min)` → reversed output → obvious wrong fix: reverse list
- T2: `result.extend(a[j:])` → duplicates → obvious wrong fix: deduplicate
- T3: `config[value] = key` → key lookup fails → obvious wrong fix: change lookup
- T4: `template.format(value, name)` → swapped output → obvious wrong fix: swap template

**Result: refine 20/20 (100%) vs pivot 19/20 (95%)**

The deceptive bugs barely differentiated. **Haiku reads the code carefully enough to find the real bug directly**, without being fooled by the error message. The "deception" hypothesis failed — the model doesn't rely on error messages alone.

### Cross-Model: Haiku vs Sonnet

**Result (raw): haiku 11/12 vs sonnet 5/12**
**Result (corrected): haiku 11/12 vs sonnet ~11/12**

| Task | haiku_refine | sonnet_refine | sonnet (corrected) |
|:--|:-:|:-:|:-:|
| T1: Inventory | 3/3 | 2/3 | **3/3** (1 false negative) |
| T2: TextStats | 2/3 | 2/3 | 2/3 (1 real timeout) |
| T3: PQueue | 3/3 | 1/3 | **3/3** (2 false negatives) |
| T4: Grades | 3/3 | 0/3 | **3/3** (3 false negatives) |

**CRITICAL METHODOLOGY FINDING — check_fn bias:**

Sonnet's 7 "failures" all had output saying *"All 4 tests pass"* — but the check_fn (`"PASSED" in output`) requires the literal string "PASSED". Haiku includes test output verbatim; Sonnet paraphrases. The raw metric is **model-biased**.

After manual correction: **both models are equivalent** on these tasks (~11/12). The strategy gap (pivot vs refine) matters more than the model gap.

**Implication:** Any cross-model comparison using literal string matching in check_fn is suspect. Future experiments must use format-agnostic checks or explicit instructions to print test output verbatim.

### Self-Correction: Unified Findings

1. **Refine > Pivot** across both independent and deceptive bugs
2. **Pivot's overhead** (revert + re-read) is never worth the "fresh perspective"
3. **Deceptive bugs don't fool the model** — haiku reads code carefully, not just error messages
4. **Model gap ≈ 0** for these self-correction tasks (haiku ≈ sonnet after correcting check_fn bias)

---

## Direction 2: Working Memory (Scratchpad)

### v2: 3-File Tasks, max_turns=12

**Result: implicit 20/20 (100%) vs scratchpad 0/20 (0%)**

Scratchpad agent hit turn limit on ALL 20 trials. Note-taking consumed 42% of tool calls.

### v3: 3-File Tasks, max_turns=20

**Result: implicit 20/20 (100%) vs scratchpad 13/20 (65%)**

With 67% more turns, scratchpad improved to 65% but still lost. 7/20 trials still hit turn limit.

### Scale Test: 8-File Codebase, max_turns=25

**Result: implicit 5/5 (100%) vs scratchpad 3/5 (60%)**

| Metric | implicit | scratchpad | Delta |
|:--|:-:|:-:|:-:|
| Correctness | 5/5 (100%) | 3/5 (60%) | -40% |
| Latency | 43.1s | 89.8s | +108% |
| Cost | $0.065 | $0.118 | +81% |
| Tools | 18.0 | 23.8 | +32% |
| Stop: end_turn | 5 | 3 | |
| Stop: tool_use (hit limit) | 0 | **2** | |

Even at 8-file scale with 4 bugs across different files, scratchpad STILL hurts. The LLM context window handles 8 files without needing external memory.

### Working Memory: Unified Findings

| Experiment | Files | max_turns | Implicit | Scratchpad | Overhead |
|:--|:-:|:-:|:-:|:-:|:-:|
| v2 | 3 | 12 | 100% | **0%** | +28% cost |
| v3 | 3 | 20 | 100% | **65%** | +113% cost |
| Scale | 8 | 25 | 100% | **60%** | +81% cost |

1. **The context window IS the working memory.** LLMs don't forget between tool calls for codebases that fit in context.
2. **Forced note-taking is a "memory tax"** that consumes 30-42% of the turn budget.
3. **Even at 8-file scale**, implicit memory wins. The break-even point (if any) is beyond 8 files.
4. **The cost of scratchpad scales with codebase size** — more files = more notes = more overhead.

---

## Meta-Findings Across All Experiments

### The Overhead Principle

Every experiment that adds **intermediate process work** hurts performance:

| Experiment | Overhead Type | Turn Cost | Effect |
|:--|:--|:-:|:--|
| Error recovery v2 | Intermediate tests | ~50% of turns | 0% vs 53% |
| Self-correction v1 | Revert + re-read | ~13% more cost | 70% vs 90% |
| Working memory v2 | Note-taking | ~42% of tools | 0% vs 100% |
| Working memory scale | Note-taking (8 files) | ~32% more tools | 60% vs 100% |

**Principle: Every turn spent on process (testing, reverting, documenting) is a turn not spent on productive work (reading, fixing, verifying).**

### The check_fn Methodology Lesson

Literal string matching (`"PASSED" in output`) is **model-biased**:
- Haiku includes test output verbatim → matches
- Sonnet paraphrases ("All 4 tests pass") → doesn't match

This caused a **120% apparent performance gap** (haiku 11/12 vs sonnet 5/12) that was actually **0%** after correction. Any cross-model study using literal check_fn needs format-agnostic matching or explicit output instructions.

---

## Trial Counts & Costs

| Experiment | Trials | Cost |
|:--|:-:|:-:|
| Self-correction v1 | 40 | ~$1.23 |
| Self-correction v2 (deceptive) | 40 | ~$1.22 |
| Working memory v2 (3 files, 12 turns) | 40 | ~$1.68 |
| Working memory v3 (3 files, 20 turns) | 40 | ~$2.24 |
| Working memory scale (8 files) | 10 | ~$0.91 |
| Cross-model refine | 24 | ~$1.30 |
| **Total** | **194** | **~$8.58** |

---

## Next Steps

1. **Fix check_fn for cross-model studies**: Use `"pass" in output.lower()` or require agents to explicitly print test output
2. **Working memory at 20+ files**: Find the scale where context window actually becomes insufficient
3. **Strategy × model interaction**: Does Sonnet respond to moderate prompts (unlike Haiku)?
4. **Pivot on truly deceptive tasks**: Design bugs where the model's code reading CAN'T identify the real bug without running tests
