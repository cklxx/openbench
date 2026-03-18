# Experiment: concise_system_prompt_vs_none

**Date:** 2026-03-17
**Run ID:** `14321c42-c23c-47f6-b52d-44331fef71a8`
**Duration:** ~54s (16:54:40 → 16:55:34 UTC)

## Hypothesis

An explicit conciseness-focused system prompt reduces token usage while maintaining answer quality compared to no system prompt.

## Setup

| | Agent A (baseline) | Agent B (variant_v1) |
|--|--|--|
| **System Prompt** | *(none)* | "You are a concise Q&A assistant. Answer in as few words as possible while remaining accurate and complete. Use short sentences. No preamble, no filler phrases, no repetition of the question. If a single word or number suffices, give only that." |
| **Model** | claude-haiku-4-5 | claude-haiku-4-5 |
| **Max Turns** | 2 | 2 |
| **Tools** | none | none |

**Tasks (5):**
1. What is the capital of Australia?
2. Explain the difference between TCP and UDP in networking.
3. A store sells apples for $1.50 each. If I buy 7 apples and pay with a $20 bill, how much change do I get?
4. What are three common causes of a Python KeyError exception?
5. Who wrote the novel '1984' and in what year was it published?

**Diff field:** `system_prompt`

## Scores

Scoring criteria: accuracy (correctness of answer) + conciseness (penalise unnecessary elaboration, filler, or unsolicited context). Max 100.

| Task | Agent A | Agent B | Notes |
|------|---------|---------|-------|
| Capital of Australia | 75 | 100 | A answered correctly but added full historical background (purpose-built city, Griffin architects). B: "Canberra." |
| TCP vs UDP | 70 | 95 | A produced 990-token response with tables, analogies, and extensive use-case lists — correct but massively over-verbose. B used concise bullets. |
| Apple change calculation | 90 | 100 | A correct, added redundant trailing sentence ("You get $9.50 in change."). B showed working and stopped. |
| Python KeyError causes | 75 | 92 | A correct but wrapped each cause in a code block with solutions — far beyond what was asked. B listed three causes cleanly. |
| Author of '1984' | 80 | 100 | A correct but added unsolicited cultural commentary on dystopian themes. B: one sentence, done. |
| **Average** | **78.0** | **97.4** | |

## Efficiency

| Metric | Agent A (baseline) | Agent B (variant_v1) |
|--------|--------------------|----------------------|
| Tokens (avg) | 469 | 212 |
| Cost (avg) | $0.00534 | $0.00408 |
| Latency (avg) | 6.2s | 2.97s |

## Result

**Winner: B** (avg score 97.4 vs 78.0, −55% tokens, −24% cost)

The no-system-prompt baseline defaulted to "be thorough" behaviour, producing answers 2–10× longer than needed with no quality gain. The concise system prompt cut tokens in half and improved every quality score, most dramatically on open-ended technical tasks (TCP/UDP: 70 → 95, KeyError: 75 → 92).

## Next Experiment

Test whether format-type-specific rules (one sentence for facts, bullets for technical questions, minimal steps for math) further improve the score beyond generic conciseness instruction.
