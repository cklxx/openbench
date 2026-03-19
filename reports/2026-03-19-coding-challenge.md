# Experiment Report: Coding Challenge — haiku vs sonnet

**Date:** 2026-03-19
**Run ID:** 9cf3822d-df73-43f1-ac3b-0f24c1681f8a
**Experiment:** `coding_challenge`

---

## Setup

Agents implement algorithms from spec + verify with test suites.
Same system prompt, same tools (Read, Bash, Glob, Edit, Write), max_turns=20.

| Task | Difficulty | Algorithm |
|------|-----------|-----------|
| T1 | medium | Matrix spiral traversal |
| T2 | easy | Run-length encoding |
| T3 | medium | Balanced parentheses generator |
| T4 | hard | Trie with prefix search |
| T5 | hard | Longest common subsequence |

---

## Results

| Metric | haiku | sonnet | Delta |
|--------|-------|--------|-------|
| **Correctness** | **5/5** | **5/5** | tie |
| Latency (avg) | 28.87s | **21.33s** | **-26%** |
| Tokens (avg) | 2,770 | **948** | **-66%** |
| Tool calls (avg) | 7.0 | **5.0** | **-29%** |
| Cost (avg) | **$0.032** | $0.035 | +11% |

## Key Findings

### 1. Both agents solve all 5 challenges — correctness is tied
Both haiku and sonnet implement spiral traversal, RLE, parentheses generation,
Trie, and LCS correctly on first or second attempt. These are standard CS
algorithms well within both models' capabilities.

### 2. Sonnet is dramatically more efficient
- **66% fewer tokens**: Sonnet generates concise, correct implementations.
  Haiku generates more verbose code with more iterations.
- **26% faster**: Sonnet completes in 21s avg vs haiku's 29s.
- **29% fewer tool calls**: Sonnet typically reads spec, writes code, runs test
  (5 calls). Haiku often needs extra iterations (7+ calls).

### 3. Sonnet's pattern: one-shot correct
Sonnet's typical flow: Read spec → Write implementation → Run tests → Pass.
5 tool calls, 7-8 turns, done.

Haiku's typical flow: Read spec → Write first attempt → Run tests → Maybe fail →
Fix → Re-run → Pass. 7-8 tool calls, 14-21 turns.

### 4. Haiku is cheaper despite being slower
haiku: $0.032/task vs sonnet: $0.035/task (+11%). Haiku uses more tokens but
at a lower per-token price. For correctness-equivalent results, haiku is the
cost-effective choice.

### 5. Trie (T4) shows the biggest efficiency gap
- haiku: 43.9s, 5,107 tokens, 8 tools, 21 turns
- sonnet: 25.9s, 1,149 tokens, 5 tools, 8 turns

Sonnet implements the Trie correctly on first attempt. Haiku needs multiple
fix-and-retry cycles, particularly on the `starts_with` method returning
sorted results.

---

## Verdict

**Tie on correctness. Sonnet wins on efficiency (-66% tokens, -26% latency).
Haiku wins on cost (-11%).**

For standard algorithm implementation, model capability doesn't affect
correctness (both solve all 5), but dramatically affects efficiency. Sonnet
is the "senior dev who gets it right the first time"; haiku is the "junior
dev who iterates to the right answer."

---

## Next Experiments

1. **Harder algorithms**: Red-black tree, segment tree, A* pathfinding —
   tasks where first-attempt correctness matters more.
2. **Constrained turns**: max_turns=6 to test which model can solve with
   fewer iterations (sonnet should dominate).
3. **Code quality evaluation**: Beyond "tests pass" — evaluate code style,
   edge case handling, time complexity.
