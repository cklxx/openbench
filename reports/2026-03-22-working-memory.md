# Working Memory: Forced Scratchpad vs Implicit Context

**Date:** 2026-03-22
**Experiments:** `working_memory_v2` (tight budget), `working_memory_v3` (generous budget)

## Hypothesis

Forced externalized memory (_notes.md scratchpad) should improve correctness on multi-file debugging tasks by preventing the agent from "forgetting" facts discovered in earlier files.

## Design

4 multi-file tasks, each with 3 source files + 1 test file and 2 bugs requiring cross-file understanding.

| Task | Files | Bugs | Cross-file Dependency |
|:--|:-:|:--|:--|
| T1: Config Cascade | 3 | POOL_SIZE=5→10; client retry logic | config value flows to server and client |
| T2: Data Pipeline | 3 | int() vs float(); `>` vs `>=` in filter | parser type affects pipeline aggregation |
| T3: Event System | 3 | default priority CRITICAL→NORMAL; fallback `>=` vs `>` | events.py priority affects dispatcher fallback |
| T4: Auth Roles | 3 | admin missing "read"; mutable permission list | roles.py affects middleware checks |

**Agent A (implicit):** Standard debugging prompt. Relies on context window.
**Agent B (scratchpad):** EXTREME FORBIDDEN constraint — MUST update _notes.md after reading each file, FORBIDDEN from editing source without recent note update.

## Results

### v2: max_turns=12 (Tight Budget)

| Metric | implicit | scratchpad | Delta |
|:--|:-:|:-:|:-:|
| **Correctness** | **20/20 (100%)** | **0/20 (0%)** | **-100%** |
| Latency | 27.07s | 34.62s | +28% |
| Cost (avg) | $0.0370 | $0.0472 | +28% |
| Tools (avg) | 11.1 | 12.8 | +15% |
| Stop reason | 20× end_turn | **20× tool_use** | all hit limit |

**Scratchpad agent never completed a single task.** All 20 trials hit the turn limit while still trying to use tools. The note-taking overhead consumed the entire budget.

#### Tool Pattern Comparison (T1)

**Implicit (11 tools — completed):**
```
Bash(test) → Read(dir) → Glob → Read(test) → Read(config) → Read(server) → Read(client) → Edit(config) → Edit(client) → Bash(test) → Bash(test)
```

**Scratchpad (12 tools — incomplete, still running):**
```
Write(_notes.md) → Bash(pwd) → Bash(ls) → Write(_notes.md) → Bash(cd) → Edit(_notes.md) → Read(test) → Read(server) → Read(config) → Edit(_notes.md) → Read(client) → Edit(_notes.md)
```

The scratchpad agent spent **5 of 12 tool calls (42%) on _notes.md** and reached 0 source file edits and 0 test executions.

### v3: max_turns=20 (Generous Budget)

| Metric | implicit | scratchpad | Delta |
|:--|:-:|:-:|:-:|
| **Correctness** | **20/20 (100%)** | **13/20 (65%)** | **-35%** |
| Latency | 26.67s | 51.91s | +95% |
| Cost (avg) | $0.0359 | $0.0764 | +113% |
| Tokens (avg) | 2,557 | 5,018 | +96% |
| Tools (avg) | 11.8 | 18.1 | +53% |
| Stop reason | 20× end_turn | 13× end_turn, **7× tool_use** | 35% still hit limit |

With 67% more turns, scratchpad improved from 0% to 65% — but **still 35% worse than implicit** and costs 2x more.

#### Per-Task (v3)

| Task | implicit | scratchpad | Gap |
|:--|:-:|:-:|:-:|
| T1: Config Cascade | 5/5 | 4/5 | -1 |
| T2: Data Pipeline | 5/5 | **2/5** | **-3** |
| T3: Event System | 5/5 | 4/5 | -1 |
| T4: Auth Roles | 5/5 | 3/5 | -2 |

T2 (data pipeline) is hardest for scratchpad: the cascading parser bug (int→float skipping records) requires understanding across parser.py and pipeline.py, but the note-taking overhead leaves less room for debugging.

## Key Findings

### 1. The context window IS the working memory

For 3-file codebases, the LLM's context window provides sufficient working memory. The agent naturally retains information from earlier file reads — it doesn't "forget" facts between tool calls. Externalizing this to a file adds overhead without adding capability.

### 2. Forced note-taking is a "memory tax"

| Budget | Note-taking overhead | Effective work turns | Correctness |
|:--|:-:|:-:|:-:|
| 12 turns | ~5 turns (42%) | ~7 turns | 0% |
| 20 turns | ~6 turns (33%) | ~14 turns | 65% |
| No notes (12 turns) | 0 turns | 12 turns | 100% |

The scratchpad consumes 33-42% of the turn budget. This "memory tax" directly reduces the turns available for productive work (reading, editing, testing).

### 3. Even generous budgets can't overcome the overhead

At max_turns=20, the scratchpad agent uses **18.1 tools** (avg) vs implicit's **11.8** — 53% more tool calls for 35% less correctness. The extra turns go to note-taking, not to better debugging.

7 out of 20 scratchpad trials (35%) STILL hit the turn limit at max_turns=20, suggesting the overhead grows with task complexity.

### 4. The scratchpad agent's behavioral compliance was 100%

Unlike the soft-prompt experiments (which produced zero behavioral change), the EXTREME FORBIDDEN constraints successfully forced note-taking behavior. The scratchpad agent dutifully updated _notes.md after every file read, exactly as instructed.

**The constraint worked perfectly — but the strategy it enforced was harmful.**

## Comparison: Overhead Strategies Across Experiments

| Experiment | Overhead Type | Cost | Outcome |
|:--|:--|:--|:--|
| Error recovery v2 | Intermediate tests (incremental) | 3.0 test runs vs 1.7 | 0% vs 53% — harmful |
| Self-correction | Revert + re-read (pivot) | +13% cost | 70% vs 90% — harmful |
| **Working memory** | **Note-taking (scratchpad)** | **+53% tool calls** | **65% vs 100% — harmful** |

All three show the same pattern: **forced intermediate work competes with productive work for turn budget.**

## Practical Implications

1. **Don't force agents to externalize state.** LLMs with 100K+ token context windows don't need scratchpad files for tasks within their context capacity.
2. **The "measure twice, cut once" principle has limits.** Planning helps (compute allocation v3), but forced documentation hurts. The distinction: planning reduces wasted actions, while documentation adds overhead without reducing actions.
3. **Turn budget is the scarcest resource.** Any process that consumes turns without directly advancing toward the goal reduces performance.
4. **This may change at scale.** For 10+ file codebases where the full codebase exceeds context capacity, externalized memory might become necessary. That's a different experiment.

## Next Steps

1. **Scale test**: 10+ file tasks where context window IS the bottleneck — does scratchpad become valuable?
2. **Optional scratchpad**: Let the agent choose when to take notes (but moderate prompts won't change behavior, per prior findings)
3. **Cross-model**: Does a stronger model (Sonnet) use scratchpad more efficiently?
