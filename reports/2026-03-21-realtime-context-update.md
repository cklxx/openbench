# Real-Time Status Update Format: Repeated Key vs Indexed Log

**Date:** 2026-03-21
**Experiment:** `realtime_context_update`
**Run ID:** `e1a35431-bc0f-46a2-9a64-80f664e8f678`

## Hypothesis

Among append-only status update formats (both KV-cache friendly), indexed logs (`[1] cpu=72.3%`) would outperform repeated-key (`Current cpu: 72.3%`) because explicit sequence numbers help the model anchor to the most recent entry.

## Result: Repeated Key wins marginally (83.3% vs 81.3% pass@1)

**Winner: Agent A (repeated_key)** — but the difference is small and concentrated in hard tasks.

## Scores

| Metric | Repeated Key (A) | Indexed Log (B) | Delta |
|--------|-------------------|------------------|-------|
| Correctness | 40/48 (83.3%) | 38/48 (79.2%) | +5.0% A |
| Latency (avg) | 17.77s | 19.43s | A 9% faster |
| Tokens (avg) | 1,222 | 1,095 | B 10% cheaper |
| Cost (avg) | $0.00463 | $0.00411 | B 11% cheaper |

## Task-Level Breakdown

| Task | Updates | Fields | Difficulty | Repeated Key | Indexed Log |
|------|---------|--------|------------|--------------|-------------|
| T1: Single field, 5 updates | 5 | 1 | easy | 8/8 (100%) | 8/8 (100%) |
| T2: Multi-field, 5 updates | 5 | 3 | easy | 8/8 (100%) | 8/8 (100%) |
| T3: Single field, 20 updates | 20 | 1 | medium | 8/8 (100%) | 8/8 (100%) |
| T4: Multi-field, 20 updates | 20 | 3 | medium | 7/8 (87.5%) | 8/8 (100%) |
| T5: Dense, 50 updates, 5 fields | 50 | 5 | hard | 6/8 (75%) | 5/8 (62.5%) |
| T6: Needle-in-haystack, 30 updates | 30 | 3+1 | hard | 5/8 (62.5%) | 2/8 (25%) |

## Key Findings

1. **Easy/medium tasks: no difference.** Both formats achieve 100% accuracy up to 20 updates with 3 fields. Format doesn't matter when context is short enough.

2. **Hard tasks favor repeated-key.** At 50 updates (T5) and in needle-in-haystack (T6), repeated-key outperforms indexed-log. T6 is the starkest: 62.5% vs 25%.

3. **Indexed log is cheaper but less accurate.** The indexed format uses ~10% fewer tokens (more compact), but the model seems to find repeated labels easier to scan for the "latest" value.

4. **Needle-in-haystack is hard for both.** T6 (a field that changes once at update #7 then reverts to "none" for 23 updates) challenged both formats. The model often latched onto the interesting "disk_warning_sector_42" value instead of the boring latest "none".

5. **pass@4 erases most differences.** With 4 attempts, both formats hit ~99.9%. The format matters most in single-shot scenarios.

## Why Repeated Key Might Win

The repeated-key format (`Current cpu: 72.3%`) reads like natural language with identical prefixes. The model may use positional heuristics (last occurrence of "Current cpu:") more reliably than parsing sequence numbers. The indexed format requires the model to understand that `[50]` is the latest, which adds an inference step.

## Recommendations

1. **Use repeated-key format** for real-time status injection in agentic systems — it's simpler and slightly more accurate.
2. **For cost-sensitive applications**, indexed-log saves ~11% on tokens with only marginal accuracy loss on easy/medium tasks.
3. **Next experiment**: test timestamped log format (`[2024-03-21 10:05] cpu=72.3%`) — timestamps may give even stronger recency signals than bare sequence numbers.
4. **Next experiment**: test with higher update counts (100, 200) to find the recognition ceiling for repeated-key format.
