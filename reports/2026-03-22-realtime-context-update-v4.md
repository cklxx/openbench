# Real-Time Context Update v4: Observation Masking

**Date:** 2026-03-22
**Experiment:** `realtime_context_update_v4`
**Run ID:** `9a64e66a-f8b6-4d30-9155-054d107fef33`

## Hypothesis

Different query types need different amounts of history. Observation masking (dropping old entries and replacing with a placeholder) should work for "latest value" queries but fail for historical queries. A statistical summary can partially recover information lost by masking.

## Design

50 timestamped entries with 3 fields (cpu, memory, requests) + 1 rare alert event at entry #15.

**5 masking levels:**

| Level | Prompt | What's visible |
|:--|:--|:--|
| full | 3,061 chars | All 50 entries |
| last_20 | 1,385 chars | "[30 omitted]" + entries 31-50 |
| last_10 | 825 chars | "[40 omitted]" + entries 41-50 |
| last_5 | 545 chars | "[45 omitted]" + entries 46-50 |
| summary_10 | 1,107 chars | Stats summary of 1-40 + entries 41-50 |

**5 query types:** latest value, peak value, count threshold crossings, needle-in-haystack alert, historical lookup.

## Results: Accuracy Matrix

| Query Type | full | last_20 | last_10 | last_5 | summary_10 |
|:--|:-:|:-:|:-:|:-:|:-:|
| T1: Current values | **100%** | 97%* | **100%** | **100%** | **100%** |
| T2: Peak cpu | **100%** | 0% | 0% | 0% | **100%** |
| T3: Count cpu>80% | **100%** | 0% | 84%† | 0% | 69%† |
| T4: Alert needle | **100%** | 0% | 0% | 0% | **100%** |
| T5: Historical lookup | **100%** | 0% | 0% | 0% | 0% |
| **Overall** | **100%** | **19%** | **37%** | **20%** | **74%** |

\* 1 failure due to number formatting (`5,993` vs `5993`) — false negative.
† T3 counting is unreliable for partial data — models sometimes hallucinate counts.

## Key Findings

### 1. Query type completely determines masking viability

The results form a clean capability matrix:

| Query Type | Requires | Minimum Level |
|:--|:--|:--|
| Latest value | Last entry only | **last_5** (or even last_1) |
| Peak / extremes | Full data or summary | **summary** |
| Counting / aggregation | Full data | **full** only |
| Needle-in-haystack | Full data or summary (if summary captures it) | **summary** |
| Historical point lookup | The specific entry | **full** only |

### 2. Summary is dramatically effective

`summary_10` uses only 36% of `full`'s prompt size but recovers 74% of accuracy. It perfectly handles peak values and needle events because the summary explicitly includes them. It only fails on:
- **Point lookups**: "What was the value at 12:00?" — summary has ranges, not individual points
- **Counting**: sometimes hallucinates counts from summary statistics

### 3. Masked agents correctly refuse when data is missing

When `last_10` or `last_5` can't answer T4 (alert), they say "I cannot see any alert field in the data shown" — not hallucinating. This is the **correct behavior** for a well-calibrated system.

When `summary_10` can't answer T5 (point lookup), it says "I don't have the specific values at that timestamp" — again, correct refusal.

### 4. The "right" answer depends on the model's honesty more than the data

`last_20` for T2 (peak cpu) reported the peak from its visible 20 entries (87.9%) instead of saying "I can't see all data." This is **confidently wrong** — more dangerous than the shorter windows that at least caveat their answers.

### 5. Cost savings from masking are significant

| Level | Prompt Size | Avg Cost | vs Full |
|:--|:-:|:-:|:-:|
| full | 3,061 chars | $0.00643 | baseline |
| summary_10 | 1,107 chars | $0.00480 | -25% |
| last_10 | 825 chars | $0.00438 | -32% |
| last_5 | 545 chars | $0.00430 | -33% |

## Practical Architecture Recommendation

For real agentic systems, use a **tiered context strategy**:

```
┌─────────────────────────────────────┐
│ System Prompt (static)              │
├─────────────────────────────────────┤
│ Summary of history (compacted)      │  ← Captures peaks, alerts, trends
│   cpu: range 10-90%, peak at 10:15  │
│   alerts: disk_failure at 11:10     │
├─────────────────────────────────────┤
│ Recent entries (last N raw)         │  ← For "current value" queries
│   [13:50] cpu=58.0% memory=45.9%   │
│   [13:55] cpu=62.3% memory=48.1%   │
│   [14:00] cpu=55.7% memory=44.2%   │
│   [14:05] cpu=58.0% memory=45.9%   │
├─────────────────────────────────────┤
│ User question                       │
└─────────────────────────────────────┘
```

This gives you:
- **Latest values**: from raw recent entries (100% accurate)
- **Peaks, alerts, trends**: from summary (100% accurate)
- **KV cache friendly**: static prefix + append-only recent entries
- **Cost**: ~36% of full history prompt size

The only thing you lose is **point lookups** ("what was cpu at exactly 12:00?") and **exact counting** ("how many times did X happen?"). If these are needed, keep a separate queryable store (not in the LLM context).

## Next Steps

1. **Dynamic compaction trigger**: test when to re-summarize (every N entries? when context exceeds threshold?)
2. **Cross-model**: does Sonnet handle summary-based queries better than Haiku?
3. **Multi-turn**: does the summary + recent pattern hold up across multiple conversation turns?
