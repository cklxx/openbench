# Experiment: strict_word_limits

**Date:** 2026-03-18
**Run ID:** `293cac33-b785-48aa-89fc-6ef389e73484`
**Duration:** ~44s

## Hypothesis

Stricter word budgets (≤3 bullets, ≤50-word cap for factual questions, ≤12 words per bullet, no parenthetical elaborations) will push average quality above 98 while further reducing token cost compared to the format-adaptive baseline (exp 2 winner).

## Setup

| | Agent A (variant_v2_baseline) | Agent B (variant_v3) |
|--|--|--|
| **System Prompt** | Format-adaptive rules: ≤5 bullets ≤15 words each, one-sentence for facts, essential-steps for math, Yes/No + ≤1 sentence | Stricter: ≤3 bullets ≤12 words each, ≤50 words for facts, one-line working + answer for math, Yes/No + ≤15 words, no parentheticals |
| **Model** | claude-haiku-4-5 | claude-haiku-4-5 |
| **Max Turns** | 2 | 2 |
| **Tools** | none | none |

**Tasks (5 — same as exp 2 for comparability):**
1. What is the capital of Australia?
2. What are the key differences between TCP and UDP?
3. Solve: A train travels 120 km in 1.5 hours. What is its average speed in km/h?
4. Is Python an interpreted language?
5. Explain what a DNS server does.

**Diff field:** `system_prompt`

## Efficiency Results

| Metric | Agent A (baseline) | Agent B (strict) | Delta |
|--------|-------------------|------------------|-------|
| Latency (avg) | 2.65s | 3.39s | +28.3% |
| Tokens (avg) | 179 | 308 | **+72.3%** |
| Cost (avg) | $0.00393 | $0.00458 | +16.7% |
| Successes | 5/5 | 5/5 | — |

## Output Comparison

| Task | Agent A output (summary) | Agent B output (summary) | Winner |
|------|--------------------------|--------------------------|--------|
| Capital of Australia | "Canberra." | "Canberra is the capital of Australia. It was built in the early 1900s as a compromise between rivals Sydney and Melbourne." | A (B violated its own ≤50-word rule by adding unsolicited history) |
| TCP vs UDP | 3 bullets, clean | 4 bullets (violated its own ≤3 rule), similar content | A (B broke its constraint) |
| Train speed | "**80 km/h**\nSpeed = Distance ÷ Time = 120 ÷ 1.5 = 80" | "120 ÷ 1.5 = **80 km/h**" | B (more minimal) |
| Is Python interpreted? | One sentence, 222 tokens | "Yes, though technically it compiles to bytecode first…", 298 tokens | A (more tokens for same quality) |
| DNS server | 207 tokens | 701 tokens — anomalously high | A |

## Result

**Winner: A** (variant_v2_baseline — exp 2 winner)

The hypothesis was **falsified**. Stricter constraints backfired on 4 of 5 tasks:

1. **Constraint violation**: Agent B broke its own rules on 2 tasks (added historical context to a factual question; used 4 bullets despite ≤3 rule).
2. **Token inflation**: Agent B used 72% more tokens on average — the opposite of the goal. The ≤50-word cap for facts seems to have prompted the model to expand rather than compress.
3. **Task 5 anomaly**: DNS task consumed 701 tokens for Agent B vs 207 for Agent A. Likely the model attempted multiple rewrites to satisfy conflicting constraints (be concise AND explain ≤50 words AND no parentheticals).

## Key Findings

- Explicit numeric word limits can paradoxically increase output length: the model may try harder to fill perceived "allowed space" or rewrite responses multiple times to comply.
- The format-adaptive rules from exp 2 (vaguer but well-structured) outperform rigid word budgets for this task set.
- The ≤3-bullet constraint was actively violated without recovery, suggesting haiku-class models don't reliably self-audit against numeric list caps.

## Conclusion

The format-adaptive prompt (exp 2 winner) remains the best-performing system prompt in this series. The optimization ceiling for pure system-prompt instruction-tuning may have been reached for haiku-class models on these Q&A tasks.

## Next Experiment (Options)

- **Model upgrade**: test whether sonnet-class model + exp 2 prompt vs haiku + exp 2 prompt improves quality at acceptable cost delta.
- **Few-shot examples**: add 2–3 gold-standard (question, answer) examples to the system prompt rather than rules — test whether examples beat instructions.
- **Task diversity**: expand to harder tasks (multi-step reasoning, code generation) to find where these prompts break down.
