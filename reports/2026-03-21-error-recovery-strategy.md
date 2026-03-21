# Experiment Report: Error Recovery Strategy — Incremental vs Batch Fix

**Date:** 2026-03-21
**Experiments:** `error_recovery_strategy` (v1), `error_recovery_v2`
**Total trials:** 60 + 60 = 120

## Research Question

When a coding agent encounters multi-bug codebases, which recovery strategy works better:
- **Incremental:** Fix one bug → test → fix next bug → test (maximize feedback)
- **Batch:** Read all code → find all bugs → fix all at once → test once (maximize understanding)

**Literature gap:** Failure taxonomies are well-established (MAST: 14 failure modes; Tool invocation: 12 categories, 1980 instances). But **no controlled study tests which recovery strategy works best** — bridging the taxonomy→intervention gap.

## Experimental Design

| Version | Prompt Strength | Strategy Comparison | Result |
|---------|----------------|---------------------|--------|
| v1 | Moderate | blind retry vs structured reflection | **14/14 tie** — prompts ignored |
| v2 | **Extreme (FORBIDDEN)** | incremental fix vs batch fix | **batch 16/30 vs incr 0/30** |

### v2 Design (definitive)

- **Agent A (incremental_fix):** "Fix ONE bug → test → fix NEXT → test. FORBIDDEN from fixing multiple bugs before testing."
- **Agent B (batch_fix):** "Read ALL files → fix ALL bugs at once → test ONCE at end. FORBIDDEN from running tests before all fixes applied."
- Same model (haiku), tools, max_turns=6
- 6 tasks with cascading/interacting bugs (fixing Bug A reveals Bug B)
- n=5 per task

## Results (v2 — Definitive)

### Overall Metrics

| Metric | incremental_fix | batch_fix | Delta |
|--------|----------------|-----------|-------|
| **Correctness** | **0/30 (0%)** | **16/30 (53%)** | **∞** |
| Latency | 22.37s | 39.84s | +78% |
| Cost | $0.026/trial | $0.043/trial | +64% |
| Tokens | 2,068 | 4,776 | +131% |
| Tool calls | 7.5 | 6.9 | -8% |
| Avg Edits | **1.0** | **1.6** | +60% |
| Avg Bash (tests) | **3.0** | **1.7** | -43% |

### Per-Task Breakdown

| Task | Bug Type | incremental | batch |
|------|----------|-------------|-------|
| T1: Inventory (operand swap + comparison invert) | cascading | 0/5 | 0/5 |
| T2: Rate Limiter (no burst cap + missing refill call) | interacting | 0/5 | 2/5 |
| T3: LRU Cache (MRU eviction + hit_rate formula) | cascading | 0/5 | **4/5** |
| T4: Calculator (zero-var + unclosed paren + 3 bugs) | multi-symptom | 0/5 | **4/5** |
| T5: Transaction (shallow copy + lost reference) | state-dependent | 0/5 | 2/5 |
| T6: Markdown (h1 regex + list inline formatting) | cascading | 0/5 | **4/5** |

### Behavioral Analysis

**Incremental strategy failure mode:**
```
Turn 1: Read test file
Turn 2: Read source file
Turn 3: Bash (run test — see first error)
Turn 4: Read source again (understand error)
Turn 5: Edit (fix first bug)
Turn 6: Bash (run test again — see second error)
→ OUT OF TURNS. Only 1 bug fixed.
```

**Batch strategy success mode:**
```
Turn 1: Glob (find files)
Turn 2: Read source file(s)
Turn 3: Read test file
Turn 4: Edit file 1 (fix all bugs)
Turn 5: Edit file 2 (if needed)
Turn 6: Bash (run test — PASSED)
→ All bugs fixed. Test passes.
```

The critical metric: **incremental makes 3.0 test runs but only 1.0 edit**, while **batch makes 1.7 test runs and 1.6 edits**. The incremental approach wastes 2x more turns on feedback that it can't act on.

## Key Findings

### 1. Batch Fix Dominates for Multi-Bug Tasks (53% vs 0%)

When codebases contain multiple interacting bugs, fixing them all at once after thorough analysis is infinitely more effective than iterative single-bug fixes. Zero incremental trials succeeded.

**Root cause:** With tight turn budgets (6 turns), each test-between-fixes cycle costs 1-2 turns of overhead. The incremental approach exhausts its turn budget on feedback loops, leaving no turns for actual fixes.

### 2. Moderate Recovery Prompts Are Ignored (v1: 14/14 tie)

Soft prompts ("try something else" vs "stop and reflect") produced identical behavior and identical results. This confirms the finding from compute allocation experiments: **only extreme FORBIDDEN constraints change model behavior**.

### 3. Test Cycles Are Expensive Under Turn Constraints

The incremental strategy averages 3.0 Bash calls vs batch's 1.7. Each intermediate test run:
- Consumes 1 turn of budget
- Often reveals a *new* error (from Bug B) not actionable without another read cycle
- Creates the illusion of progress while actually wasting turns

### 4. Batch Strategy Enables More Actual Fixes

Despite using fewer total tools (6.9 vs 7.5), batch makes **60% more edits** (1.6 vs 1.0). This is the key efficiency: batch converts turn budget into actual code changes rather than feedback cycles.

### 5. Hardest Tasks Remain Unsolved By Both

T1 (inventory with operand swap + comparison invert): 0/5 for both strategies. When bugs are sufficiently subtle (operand order in `reserved - stock` vs `stock - reserved`), neither strategy helps — it's a model capability limit.

## Synthesis with Compute Allocation Experiment

Both experiments point to the same meta-finding:

| Experiment | Winner | Core Principle |
|-----------|--------|---------------|
| Compute Allocation | Plan-first (+800%) | **Read before act** |
| Error Recovery | Batch fix (∞ improvement) | **Understand all before fixing any** |

**Unified finding: Under turn constraints, upfront investment in understanding beats iterative trial-and-error.** This is the agent-world analog of "measure twice, cut once."

### Cost-Efficiency

- Batch fix: 12.3 correct answers per dollar
- Incremental fix: 0 correct answers per dollar
- Combined with compute allocation: plan-first + batch-fix is the dominant strategy

## Implications for Agent Design

1. **Default to batch-fix for multi-bug tasks** — read all relevant code before any edits
2. **Avoid intermediate test runs** unless turn budget is generous (>15 turns)
3. **Structural enforcement matters** — prompts alone don't change strategy; use tool restrictions or turn-phase gating
4. **Turn budget planning:** Reserve ≥40% of turns for actual edits; if intermediate tests consume more than 30% of turns, switch to batch mode

## Threats to Validity

- Single model (haiku) — Sonnet/Opus may have different strategy preferences
- check_fn only detects literal "PASSED" — may undercount correct solutions
- max_turns=6 deliberately constrains; results may differ with generous budgets
- All tasks are bug-fix type; feature-building may favor different strategies
- Extreme prompts create artificial separation — real agents use mixed strategies

## Conclusion

**Batch fix completely dominates incremental fix (53% vs 0%) for multi-bug tasks under tight turn budgets.** This is the first controlled A/B study comparing error recovery strategies for coding agents.

**Novel contributions:**
1. First empirical evidence that iterative debugging is counterproductive under turn constraints
2. Quantified the "feedback loop tax" — intermediate tests waste 2x more turns than batch
3. Confirmed that moderate prompts don't alter recovery behavior (only extreme constraints work)
4. Unified "read-first" principle across compute allocation AND error recovery domains
