# Real-Time Status Update Format: Repeated Key vs Indexed Log

**Date:** 2026-03-22
**Experiment:** `realtime_context_update`
**Run ID:** `e1a35431-bc0f-46a2-9a64-80f664e8f678`

## Hypothesis

Among append-only context injection formats (KV-cache friendly), indexed logs (`[1] cpu=72%`) would outperform repeated-key (`Current cpu: 72%`) because sequence numbers give the model an explicit recency anchor.

## Winner

**Agent A: repeated_key** — marginal winner (83.3% vs 81.3% pass@1, 40/48 vs 38/48 correctness).

## Results

| Metric | repeated_key (A) | indexed_log (B) | Delta |
|--------|:-:|:-:|:-:|
| Correctness | 40/48 (83.3%) | 38/48 (79.2%) | A +5.0% |
| pass@1 | 83.3% | 81.3% | A +2.1pp |
| pass@4 | 99.96% | 99.94% | ~tie |
| Avg latency | 17.77s | 19.43s | A 9.3% faster |
| Avg tokens | 1,222 | 1,095 | B 10.5% cheaper |
| Avg cost | $0.00463 | $0.00411 | B 11.4% cheaper |

### Per-Task Breakdown (pass@1)

| Task | Updates | Fields | Difficulty | repeated_key | indexed_log | Winner |
|------|---------|--------|------------|:---:|:---:|:---:|
| T1: single field | 5 | 1 | easy | 100% | 100% | tie |
| T2: multi-field | 5 | 3 | easy | 100% | 100% | tie |
| T3: single, many | 20 | 1 | medium | 100% | 100% | tie |
| T4: multi, many | 20 | 3 | medium | 87.5% | 100% | **B** |
| T5: dense | 50 | 5 | hard | 75.0% | 62.5% | **A** |
| T6: needle | 30 | 3+1 | hard | 37.5% | 25.0% | **A** |

## Key Findings

1. **Both formats are equivalent up to medium difficulty.** T1–T3 are 100%/100%. The formats only diverge at scale (20+ updates × 3+ fields with distractors).

2. **Indexed log won T4 but lost T5/T6.** The one task where indexing helped (20 updates × 3 fields, no heavy distractors) was offset by worse performance on harder tasks. Possible explanation: the `[N]` prefix adds visual noise at high update counts, and the model may anchor on index numbers rather than content.

3. **Needle-in-haystack (T6) is hard for both formats.** Only 37.5% and 25.0% pass@1. The model struggles to report `alert=none` (the latest value) instead of `alert=disk_warning_sector_42` (the salient value). This is a known "salience bias" — models report interesting values over recent values.

4. **Repeated-key uses more tokens but is faster.** The natural-language format (`Current cpu: 72.3%`) produces slightly longer outputs but lower latency, suggesting the model processes it more fluently.

5. **The margin is small.** At pass@4, both formats reach ~100%. The format difference matters most for single-shot accuracy in high-density contexts.

## Implications for Agentic Systems

- **For ≤20 updates with ≤3 fields:** format doesn't matter. Use whichever is simpler.
- **For dense real-time feeds (50+ updates):** repeated-key has a slight edge. The familiar `Key: Value` pattern may be more natural for the model than indexed entries.
- **Salience bias is the real problem.** Neither format solves the issue of the model reporting "interesting" values over "latest" values (T6). This likely requires explicit prompt engineering ("always report the LAST entry, not the most notable one").

## Next Steps

1. Test **timestamped log** format: `[2024-03-21 10:05] cpu=72.3%` — timestamps may give stronger recency signal than index numbers.
2. Test **summary + delta** format: `Current: cpu=72.3% (+2.1)` — delta hints might help the model identify the latest entry.
3. Test with higher update counts (100, 200) to find the recognition ceiling.
4. Investigate prompt-level mitigations for salience bias in T6-style tasks.
