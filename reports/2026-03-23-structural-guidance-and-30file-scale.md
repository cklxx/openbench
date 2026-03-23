# Structural Guidance & 30-File Scale Test

**Date:** 2026-03-23
**Experiments:** task_decomposition_v4, context_pressure_30files
**Research context:** Agentless (UIUC), LongCodeBench, BABILong, Context Rot

---

## Experiment D4: Structural Guidance (Agentless-Style Phases)

### Research Context

Agentless (UIUC, 2024) showed a 3-phase pipeline (localize → repair → validate)
beats autonomous agents on SWE-bench (32% vs 23%, at $0.70 vs $1.62 per fix).

Question: Does giving agents structural guidance (phases without answers)
improve performance on our tasks?

### Design

8-file codebase, 4 bugs. max_turns=20, n=5.

- **discovery:** "Run tests, read code, fix bugs, verify" (generic)
- **phased:** Explicit 3-phase structure:
  - Phase 1 (Localize): Run tests, identify which files/functions are buggy
  - Phase 2 (Repair): Read only buggy files, fix all bugs in one pass
  - Phase 3 (Validate): Run tests once to verify

### Results

| Metric | discovery | phased | Delta |
|:--|:-:|:-:|:-:|
| Correctness | **5/5** | **5/5** | **0%** |
| Latency | 39.4s | 42.4s | +8% |
| Cost | $0.065 | $0.066 | +1% |
| Tools | 18.0 | 16.8 | -7% |
| Reads | 7.8 | 6.8 | -13% |
| Edits | 5.0 | 5.0 | 0% |
| Bash | 4.8 | 5.0 | +4% |

### Key Finding: Agents Already Follow the Optimal Pattern

**Structural guidance adds zero value** because the agent naturally follows
a localize → repair → validate workflow. Both agents:

1. Run tests first (1 Bash)
2. Read relevant source files (6-8 Reads)
3. Fix all bugs (5 Edits)
4. Verify (1-2 Bash)

The phased agent reads ~1 fewer file (it skips files not identified in Phase 1),
but this doesn't translate into better outcomes.

### Why This Differs From Agentless

Agentless's advantage on SWE-bench comes from:
1. **Scale:** Real-world repos with hundreds of files — hierarchical narrowing saves massive search time
2. **Complexity:** Multi-step bugs requiring deep code understanding across complex codebases
3. **Patch selection:** Generating 40 candidate patches and using test-based filtering

Our 8-file, 4-bug tasks are simple enough that the agent's natural behavior
is already near-optimal. Structural guidance would likely help more on
larger, harder tasks where the agent's default exploration is insufficient.

### Implication

> **Don't scaffold agents for tasks they can already solve efficiently.**
> The Agentless pipeline adds value at SWE-bench scale (hundreds of files, complex bugs),
> not at 8-file scale. Match your scaffolding to task complexity.

---

## Experiment E3: 30-File Codebase (~68K Tokens)

### Research Context

- LongCodeBench: Claude drops to 3% at 1M tokens on coding tasks
- BABILong: Models use only 10-20% of context for reasoning
- Context Rot: Degradation starts at ~50K for 200K-window models
- Our prediction: 30 files (~68K tokens) might enter the degradation zone

### Design

30-file e-commerce app (15 original + 15 additional modules).
5 cross-file bugs. max_turns=30, n=5.

Used **relaxed scratchpad** (not strict FORBIDDEN) based on E2 finding that
constraint strictness is the real issue.

### Results

| Metric | implicit | relaxed scratchpad | Delta |
|:--|:-:|:-:|:-:|
| Correctness | **5/5** | **5/5** | **0%** |
| Latency | 45.4s | 61.3s | +35% |
| Cost | $0.079 | $0.100 | +26% |
| Tools | 19.2 | 22.8 | +19% |
| Reads | 9.4 | 9.2 | -2% |
| Edits | 5.0 | 6.6 | +32% |

### Key Finding: Agents Don't Read All 30 Files

Both agents read only **9-10 files** out of 30. They use test output to
identify which files matter and skip the rest.

```
30 files exist ──→ 10 tests ──→ 5 fail ──→ 9-10 files read ──→ 5 bugs fixed
```

The extra 1-2 Edits in the scratchpad agent are _notes.md writes.
The actual code editing is identical (5 Edits for 5 bugs).

### Why 30 Files Doesn't Stress Context

Research predicted degradation at ~68K tokens (34% of 200K window).
But the agent doesn't load 68K tokens — it loads ~22K tokens (9-10 files × ~2.3K each).

**Context pressure depends on files READ, not files EXISTING.**

Agents use test-driven localization as a natural filter:
1. Run tests → learn which 5 tests fail
2. Error messages point to specific files/functions
3. Read only those files + their immediate dependencies
4. Skip 20+ irrelevant files entirely

### Updated Scaling Table

| Files Exist | Files Read | Implicit | Scratchpad | Notes |
|:-:|:-:|:-:|:-:|:--|
| 3 | 3 | 100% | 0-65% | All files relevant |
| 8 | 8 | 100% | 60% | All files relevant |
| 15 | ~12 | 100% | 20-100%* | Some files skipped |
| **30** | **~10** | **100%** | **100%*** | **Most files skipped** |

*Strict scratchpad: 20%. Relaxed scratchpad: 100%.

### To Actually Stress Context, We Would Need:

1. **Bugs that require reading ALL files** — every file has a bug, or bugs chain through 20+ files
2. **No test output** — force the agent to read everything without test-based narrowing
3. **Files so interdependent** that understanding any one requires reading most others

These are artificial conditions unlikely in real codebases. In practice,
test-driven localization keeps the effective context well within window capacity.

### Implication

> **The "context pressure boundary" is a practical non-issue for test-driven bug fixing.**
> Agents naturally use test output as a filter, reading only relevant files.
> Even in a 30-file codebase, they read ~10 files — well within context limits.
> The real question is not "how many files exist" but "how many files are relevant to the bugs."

---

## Complete Task Decomposition Spectrum (D1-D4)

| Strategy | What Agent Knows | Correctness (20t) | Avg Cost | Winner? |
|:--|:--|:-:|:-:|:-:|
| **guided_correct** | Exact 4 bugs + fixes | 5/5 | **$0.038** | **Best** |
| **discovery** | Nothing | 5/5 | $0.064 | Baseline |
| **phased** | Workflow structure only | 5/5 | $0.066 | ≈ Discovery |
| **guided_partial** | 3 correct + 1 wrong | 5/5 | $0.074 | Worst |

**Rankings by efficiency:**
1. **Exact correct info** → 40% cheaper than baseline
2. **No info (discovery)** → baseline
3. **Structural guidance** → same as discovery (agent already does this)
4. **Partially wrong info** → 16% more expensive than discovery

> **Only exact, accurate information helps. Structural scaffolding is redundant.
> Wrong information is actively harmful. When in doubt, say nothing.**

---

## Complete Context Pressure Scaling (E1-E3)

| Scale | Files Read | Implicit | Strict Scratch | Relaxed Scratch |
|:-:|:-:|:-:|:-:|:-:|
| 3 files | 3 | **100%** | 0% | — |
| 8 files | 8 | **100%** | 60% | — |
| 15 files | ~12 | **100%** | 20% | 100% (+65% cost) |
| **30 files** | **~10** | **100%** | — | **100% (+26% cost)** |

The scratchpad gap NARROWED from 65% overhead at 15 files to 26% at 30 files.
This is because at 30 files the agent reads FEWER files (proportionally),
so the scratchpad tax is smaller relative to total work.

---

## Cost Summary

| Experiment | Trials | Cost |
|:--|:-:|:-:|
| D4: Structural guidance | 10 | ~$0.65 |
| E3: 30-file scale | 10 | ~$0.90 |
| **Total today (all experiments)** | **70** | **~$5.19** |
