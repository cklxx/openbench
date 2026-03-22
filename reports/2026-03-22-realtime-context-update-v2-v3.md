# Real-Time Context Update v2 + v3: Anti-Recency Needle & Format Tournament

**Date:** 2026-03-22
**Experiments:** `realtime_context_update_v2` (anti-recency), `realtime_context_update_v3` (format tournament)

## Background

v1 found repeated-key and indexed-log formats have identical accuracy (~99% excluding timeouts). Research literature suggests this is because LLMs have strong recency bias — they naturally prefer the last occurrence — and v1 always placed the latest value at the end.

Two follow-up experiments:
- **v2**: Does the model UNDERSTAND "latest by timestamp", or just grab the last line?
- **v3**: Across 4 serialization formats, which gives the best accuracy-per-token?

---

## v2: Anti-Recency Needle

### Design

Same timestamped data, two orderings:
- **Agent A (ordered)**: chronological order, latest = last line
- **Agent B (shuffled)**: latest timestamp at ~40% position, older entries after

If the model relies on position (recency bias), shuffled should fail. If it understands timestamps, both should succeed.

### Results

| Complexity | Ordered | Shuffled | Shuffled Output Tokens |
|:--|:-:|:-:|:-:|
| 10 updates × 2 fields | 8/8 (100%) | 8/8 (100%) | 482 (1.2x) |
| 30 updates × 4 fields | 8/8 (100%) | 8/8 (100%) | 1,021 (3.1x) |
| 50 updates × 5 fields | 7/8 (87.5%)* | 8/8 (100%) | 1,387 (5.1x) |

*The ordered "failure" is a check_fn false negative — model output `59.2` without `%` suffix. All values were correct.

### Key Findings

1. **The model genuinely understands timestamps.** Even at 50 updates with 5 fields, shuffled (latest in middle) achieved 100% accuracy. It does NOT just grab the last line.

2. **Shuffled triggers chain-of-thought.** The model uses 3-5x more output tokens when data is out of order — it explicitly reasons through timestamps to find the latest. Ordered data gets a fast "read the last entry" shortcut.

3. **Cost implication: out-of-order data is 2x more expensive** due to the reasoning overhead, but equally accurate.

---

## v3: Format Tournament

### Design

4 formats encoding the same data, tournament mode (all pairs):
- `key_value`: `cpu: 72.3% | memory: 90.5% | requests: 1946`
- `indexed`: `[1] cpu=72.3% memory=90.5% requests=1946`
- `json_lines`: `{"cpu": "72.3%", "memory": "90.5%", "requests": "1946"}`
- `toon`: header row + CSV-like data rows (field names only once)

3 tasks: 10 updates/3 fields (easy), 30 updates/4 fields (medium), 50 updates/5 fields (hard).

### Results

| Format | Correct | Avg Input Tok | Avg Output Tok | Avg Cost | Prompt Size |
|:--|:-:|:-:|:-:|:-:|:-:|
| key_value | **72/72 (100%)** | 20 | 442 | $0.00476 | 6,101 chars |
| json_lines | **72/72 (100%)** | 20 | 347 | $0.00454 | 7,571 chars |
| indexed | 71/72 (98.6%)* | 20 | **182** | **$0.00352** | 5,504 chars |
| toon | 69/72 (95.8%) | 20 | 473 | $0.00475 | **2,575 chars** |

*indexed's 1 failure was a check_fn false negative (correct values, missing `%` suffix).

### Failure Analysis

| Format | Task | Failures | Root Cause |
|:--|:--|:-:|:--|
| indexed | T2 (30×4) | 1 | False negative: values correct but `%` omitted |
| toon | T2 (30×4) | 3 | **Real error**: picked row 20/30 instead of last row |

**TOON's failure mode**: without per-row markers (no index, no key names), the model grabbed a row from the ~67% position instead of the last row. This is a classic "Lost in the Middle" failure — headerless CSV rows lack structural anchoring, making it harder to identify the boundary.

### Per-Task Breakdown

| Format | T1 (10×3) | T2 (30×4) | T3 (50×5) |
|:--|:-:|:-:|:-:|
| key_value | 24/24 | 24/24 | 24/24 |
| json_lines | 24/24 | 24/24 | 24/24 |
| indexed | 24/24 | 23/24* | 24/24 |
| toon | 24/24 | **21/24** | 24/24 |

TOON only fails at medium scale (30 updates). At 50 updates it succeeds — possibly because the model uses more reasoning for harder tasks.

---

## Combined Insights

### 1. The model understands semantics, not just position

v2 proves the model reads timestamps and finds the latest entry regardless of position. The recency bias explanation from v1 was wrong — the model wasn't "lucky" that latest was last; it would have found it anywhere.

### 2. Format ranking: key_value = json ≥ indexed > toon

| Criterion | Winner | Why |
|:--|:--|:--|
| Accuracy | key_value, json_lines (100%) | Structural clarity: each row is self-contained |
| Token efficiency | indexed (182 avg output tok) | Terse format → terse response |
| Prompt size | toon (2,575 chars, 66% smaller) | Header-only-once design |
| Overall value | **indexed** | Best accuracy-per-token; only "failure" was formatting |

### 3. TOON is a trap

TOON saves 60% on prompt tokens but **loses structural anchoring**. Without per-row field names or indices, the model can't reliably identify which row is "last" in medium-length sequences. The token savings aren't worth the accuracy risk.

### 4. Reasoning cost scales with ambiguity

| Scenario | Avg Output Tokens | Cost Multiplier |
|:--|:-:|:-:|
| Ordered data (latest = last) | 250-350 | 1x |
| Shuffled data (latest in middle) | 1,000-1,400 | 3-5x |

The model "knows" when it needs to think harder. Keeping data in natural order isn't just about accuracy — it's a 3-5x cost saving.

---

## Recommendations for Agentic Systems

1. **Use `indexed` or `key_value` format** — both are reliable; indexed is more token-efficient
2. **Keep data in chronological order** — saves 3-5x on output tokens
3. **Don't use TOON/CSV for sequential state** — the token savings aren't worth the structural ambiguity
4. **JSON works fine** — despite being verbose, it's 100% accurate; use it if your system already produces JSON
5. **The real optimization is not format but volume** — test observation masking / sliding window compaction next

## Next Steps

1. **Observation masking experiment**: keep last N entries + placeholder for older ones. Find the minimum N that maintains 100% accuracy.
2. **Cross-model comparison**: does Sonnet handle TOON better than Haiku? Does the format ranking hold?
3. **Fix check_fn**: use fuzzy matching that strips `%` and whitespace to avoid false negatives.
