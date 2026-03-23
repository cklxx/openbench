# Task Decomposition & Context Pressure Boundary

**Date:** 2026-03-23
**Experiments:** task_decomposition (v1 + v2), context_pressure_boundary

---

## Experiment D: Task Decomposition — Discovery vs Guided

### Research Question

Does providing agents with an exact list of bugs (file, line, fix) improve performance? Or does it cause anchoring?

This extends the anchoring bias finding (realtime context v4) where **vague** file-level hints hurt by 37-42%. Here we test the opposite: **exact, accurate, complete** bug descriptions.

### Design

8-file web application with 4 bugs (from working_memory_scale codebase).

- **Agent A (discovery):** "Run tests, read code, fix all bugs you find"
- **Agent B (guided):** System prompt lists all 4 bugs with file, line, and exact fix

Two runs:
- v1: max_turns=12 (tight budget)
- v2: max_turns=20 (generous budget)

### Results

#### v1: Tight Budget (max_turns=12)

| Metric | discovery | guided | Delta |
|:--|:-:|:-:|:-:|
| **Correctness** | **0/5** | **5/5** | **+∞** |
| Stop reason | tool_use (limit) | end_turn | |
| Latency | 36.5s | 31.0s | -15% |
| Cost | $0.059 | $0.049 | -16% |
| Tools | 15.6 | 15.4 | -1% |

Discovery hit the turn limit on ALL 5 trials. With 8 files and 4 bugs, 12 turns isn't enough to discover + read + fix + verify. Guided finished comfortably because it skipped discovery entirely.

#### v2: Generous Budget (max_turns=20)

| Metric | discovery | guided | Delta |
|:--|:-:|:-:|:-:|
| **Correctness** | **5/5** | **5/5** | **0%** |
| Latency | 45.9s | 28.0s | **-39%** |
| Cost | $0.064 | $0.040 | **-38%** |
| Tools | 18.4 | 15.2 | **-17%** |

With enough turns, both achieve 100%. But guided is **39% faster** and **38% cheaper**.

### Key Findings

**1. Exact bug decomposition doesn't raise the ceiling but dramatically lowers the floor.**

Both agents eventually solve the same problems. But guided does it with fewer turns, less cost, and can succeed under tighter budgets where discovery fails.

**2. Accuracy and completeness determine whether guidance helps or hurts.**

| Guidance Type | Accuracy | Completeness | Effect |
|:--|:--|:--|:--|
| Vague file hints | Low | Partial | **HURTS** (-37-42%) |
| Exact bug list + fixes | High | Complete | **HELPS** (-38% cost) |

The anchoring bias finding (context v4) applies to **vague, incomplete** hints that reduce exploration. **Accurate, complete** decomposition eliminates unnecessary exploration — a net positive.

**3. Guided saves ~3-5 turns of discovery overhead.**

Discovery agent needs to: run tests → glob files → read multiple files → diagnose bugs → fix → verify. Guided skips everything before "fix" because the diagnosis is provided.

### Practical Implication

> **When you know exactly what's wrong, tell the agent exactly what to fix.**
> Don't make agents "discover" bugs you've already diagnosed. Include file paths, line numbers, and expected behavior.
>
> But when you DON'T know what's wrong, don't guess — vague hints are worse than no hints.

---

## Experiment E: Context Pressure Boundary — 15 Files

### Research Question

At what codebase size does external memory (scratchpad) become valuable?

Previous results:
- 3 files: implicit 100% vs scratchpad 0-65%
- 8 files: implicit 100% vs scratchpad 60%
- **15 files: ?**

### Design

E-commerce application: 15 source files + 1 test file.
4 cross-file bugs requiring tracing through 2-3 files each:

| Bug | Files Involved | Type |
|:--|:--|:--|
| TAX_RATE = 0.08 (should be 0.10) | config → order_service → test | Value error |
| validate_quantity allows qty=0 | validators → order_service → test | Boundary error |
| order_dict["user"] (should be "username") | notifications → models → test | Key name error |
| top_events sorts ascending | analytics → test | Sort direction |

- **Agent A (implicit):** Generic "run tests, read code, fix bugs"
- **Agent B (scratchpad):** Must maintain _notes.md, update after reading each file

max_turns=25, num_samples=5.

### Results

| Metric | implicit | scratchpad | Delta |
|:--|:-:|:-:|:-:|
| **Correctness** | **5/5 (100%)** | **1/5 (20%)** | **-80%** |
| Latency | 37.3s | 68.0s | +82% |
| Cost | $0.066 | $0.117 | +77% |
| Tools | 17.2 | 24.0 | +40% |
| Avg turns | 35.4 | 55.0 | +55% |

#### Per-Trial Detail

| Trial | implicit | scratchpad |
|:--|:--|:--|
| 1 | ✅ end_turn, 17 tools | ❌ tool_use (limit), 25 tools |
| 2 | ✅ end_turn, 17 tools | ❌ tool_use (limit), 25 tools |
| 3 | ✅ end_turn, 18 tools | ❌ tool_use (limit), 25 tools |
| 4 | ✅ end_turn, 17 tools | ✅ end_turn, 20 tools |
| 5 | ✅ end_turn, 17 tools | ❌ tool_use (limit), 25 tools |

4/5 scratchpad trials hit the turn limit. The one that succeeded used 20 tools (fewer notes written).

### Key Findings

**1. Implicit memory STILL wins at 15-file scale.**

The LLM context window handles 15 files without external memory. This extends the finding from 3→8→15 files.

**2. The scratchpad tax scales with file count.**

| Files | Scratchpad Overhead | Scratchpad Correctness |
|:--|:-:|:-:|
| 3 (12 turns) | +28% cost | 0% |
| 3 (20 turns) | +113% cost | 65% |
| 8 (25 turns) | +81% cost | 60% |
| **15 (25 turns)** | **+77% cost** | **20%** |

With 15 files, the scratchpad agent needs to read + update notes for each file = 30+ tool calls just for the reading phase. 25 turns can't accommodate this overhead.

**3. The implicit agent is remarkably consistent.**

5/5 implicit trials: all 17-18 tools, all end_turn. The agent doesn't need extra turns at 15-file scale — it efficiently reads, fixes, and verifies. No note-taking, no extra process.

**4. The break-even point may not exist for current context windows.**

| Scale | Implicit Win Margin |
|:--|:-:|
| 3 files | 35-100pp |
| 8 files | 40pp |
| 15 files | **80pp** |

The margin actually **increased** at 15 files because scratchpad overhead scales linearly with file count while context window capacity handles the load easily. The break-even (if any) would require both:
- Enough files to overflow the context window (~50+?)
- Enough turns to absorb the scratchpad overhead (40+?)

---

## Updated Principles

### Principle 3 (revised): Context Window ≫ External Memory (up to 15 files)

| Scale | Implicit | Scratchpad | Verdict |
|:--|:-:|:-:|:--|
| 3 files | 100% | 0-65% | Implicit wins |
| 8 files | 100% | 60% | Implicit wins |
| **15 files** | **100%** | **20%** | **Implicit wins (larger margin)** |

The break-even point for scratchpad is far beyond 15 files. For any codebase that fits in the context window, external memory is pure overhead.

### New Principle: Accurate Decomposition Saves Turns

| Guidance Quality | Effect | Mechanism |
|:--|:--|:--|
| No guidance | Baseline | Agent discovers bugs via test+read |
| Vague hints | **Hurts** (-37-42%) | Reduces exploration, causes anchoring |
| Exact decomposition | **Helps** (-38% cost) | Eliminates discovery overhead |

When you know what's wrong, tell the agent precisely. When you don't, say nothing.

---

## Cost Summary

| Experiment | Trials | Cost |
|:--|:-:|:-:|
| Task decomposition v1 (12 turns) | 10 | ~$0.54 |
| Task decomposition v2 (20 turns) | 10 | ~$0.52 |
| Context pressure boundary (15 files) | 10 | ~$0.91 |
| **Total** | **30** | **~$1.97** |
