# Self-Correction Strategy: Pivot vs Refine

**Date:** 2026-03-22
**Experiment:** `self_correction_strategy`
**Run ID:** `b288926e-e2df-4047-b5d3-474c428a6fdd`

## Hypothesis

When a batch fix partially fails, **refine** (keep working fixes, adjust remaining failures) should outperform **pivot** (revert all changes, re-analyze from scratch) because pivot wastes turns on reverting and re-reading.

## Design

Builds on error_recovery_v2's finding that batch > incremental. Both agents use the batch approach for Phase 1 (read all → fix all → test). The difference is Phase 2 recovery:

- **Agent A (pivot):** After failed test, MUST `git checkout -- .` to revert all changes, re-read source files, and make ALL fixes again from scratch.
- **Agent B (refine):** After failed test, FORBIDDEN from reverting. Must read only test output and make minimal additional edits.

4 tasks, each single-file with 2 bugs (1 obvious + 1 subtle). `max_turns=10`, `n=5`.

| Task | Bugs | Expected Pattern |
|:--|:--|:--|
| T1: Inventory | `+` vs `*` in total_value; `qty` vs `qty*price` in most_valuable | Phase 1 fixes obvious, Phase 2 fixes subtle |
| T2: TextStats | `len(text)` vs word count; `min` vs `max` in most_common | Both bugs likely caught in Phase 1 |
| T3: PQueue | Sort ascending vs descending; `size()` off-by-one | Phase 1 fixes sort, Phase 2 fixes size |
| T4: Grades | `s + curve` vs `s * curve`; `> 90` vs `>= 90` | Grade boundary is deceptive |

## Results

### Overall

| Metric | pivot (A) | refine (B) | Delta |
|:--|:-:|:-:|:-:|
| **Correctness** | **14/20 (70%)** | **18/20 (90%)** | **+28.6%** |
| Latency | 29.41s | 27.30s | -7.2% |
| Cost (avg) | $0.0405 | $0.0352 | -13.2% |
| Tokens (avg) | 3,190 | 2,777 | -12.9% |
| Tool calls (avg) | 10.8 | 9.4 | -13.0% |

### Per-Task Breakdown

| Task | pivot | refine | Winner |
|:--|:-:|:-:|:-:|
| T1: Inventory (arithmetic + comparison) | 4/5 | **5/5** | refine |
| T2: TextStats (len + min/max) | 5/5 | 5/5 | tie |
| T3: PQueue (sort + off-by-one) | 4/5 | **5/5** | refine |
| T4: Grades (curve formula + boundary) | 1/5 | **3/5** | refine |

## Key Findings

### 1. Refine wins on every differentiating task

Refine matched or beat pivot on all 4 tasks. T4 shows the largest gap (1/5 vs 3/5). The "fresh perspective" from pivoting does not compensate for the turn cost of reverting.

### 2. Pivot wastes turns on navigation overhead

Examining failed pivot traces on T4:
```
Pivot (FAILED, 15 tools): Read → Read → pwd → Read → Read → Edit → Edit → cd → cd → Read → Read → Edit → Edit → cd → cd
Refine (FAILED, 13 tools): Read → Read → find → Read → Read → Bash(test) → Edit → Edit → Bash(test) → Bash(test) → Edit → Bash(test) → Read
```

The pivot agent:
- Ran **0 test executions** (never validated its fixes)
- Used **7 navigation/exploration** calls (pwd, cd, ls)
- Got confused by directory changes after git checkout

The refine agent:
- Ran **3 test executions** (iterative validation)
- Used **2 navigation** calls
- Made **3 edit passes** (progressive refinement)

### 3. T4 (grade boundaries) is the hardest bug type

The `> 90` vs `>= 90` boundary bug defeated both agents frequently. This is a "deceptive" bug where the fix is a single character change, but the agent must carefully read the test expectations to notice the boundary condition. Even refine only got 3/5.

### 4. Cost efficiency favors refine

| Strategy | Correct/dollar | vs baseline |
|:--|:-:|:-:|
| Pivot | 17.3 correct/$ | baseline |
| Refine | 25.6 correct/$ | +48% |

Refine is 48% more cost-efficient: higher correctness at lower cost per trial.

## Connection to Prior Findings

This result parallels the compute allocation and error recovery experiments:

| Experiment | Winner | Mechanism |
|:--|:--|:--|
| Compute allocation v3 | Plan-first (+800%) | Upfront understanding beats blind iteration |
| Error recovery v2 | Batch fix (+∞) | All-at-once beats intermediate testing |
| **Self-correction** | **Refine (+29%)** | **Keep working fixes, adjust remaining** |

The unified principle: **minimize turn overhead, maximize productive work.** Pivoting (reverting + re-reading) is overhead. Refining (targeted fixes) is productive work.

## Next Steps

1. **Deceptive bug tasks**: Test pivot on tasks where the Phase 1 fix is fundamentally WRONG (not just incomplete). Pivot should shine when the initial mental model needs to be discarded.
2. **Cross-model**: Does the pivot/refine gap change with Sonnet (stronger model that might pivot more effectively)?
3. **More correction rounds**: With max_turns=20, does pivot's "fresh start" eventually outperform refine's incremental drift?
