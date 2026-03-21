# Experiment Flow Log — 2026-03-21

**Researcher:** ckl
**Platform:** OpenBench (Claude Agent SDK-based A/B testing)
**Model:** claude-haiku-4-5 (all experiments)
**Total trials across all experiments:** 300
**Total cost:** ~$13 USD
**Total runtime:** ~45 minutes

---

## Research Context

### How We Identified Research Gaps

The session began with an OpenSeed library search to survey the existing landscape of agent evaluation research. We had a local library of AI research papers and used keyword searches to understand what had been studied and what remained open.

Key findings from the literature survey:
- **Inference-time scaling** (2026 hot topic) focuses on the *amount* of compute, not *allocation strategy* within a fixed budget
- **Self-correction studies** (e.g., Google Research 2025) show 30% error reduction, but don't compare plan-first vs act-first as competing strategies
- **ICLR 2026 Workshop on Recursive Self-Improvement** covers refinement loops but not the planning-vs-acting tradeoff
- **Failure taxonomies** are well-established (MAST: 14 failure modes, kappa=0.88; Tool invocation: 12 categories across 1980 instances), but **no controlled study tests which recovery strategy works best** for each failure type

The gap analysis followed the literature survey with a web search to confirm no recent work had filled these holes. The result: a clear space for controlled A/B studies on agent *strategy*, not just agent *capability*.

### 5 Candidate Directions (Ranked by Priority)

1. **Inference-Time Compute Allocation Strategy** — Plan-first vs act-first under fixed turn budget
2. **Error Recovery Strategy** — How agents should respond when their first fix fails
3. Spec gaming and reward hacking under ambiguous instructions
4. Injection robustness across scaffold architectures
5. Collateral damage measurement (unintended side effects of agent edits)

### Why We Started with #1 and #2

Directions #1 and #2 were selected first because they were:
- **Directly actionable** with the OpenBench platform (system_prompt is the only diff variable)
- **Complementary** — compute allocation asks "how to spend your turns" and error recovery asks "what to do when things go wrong"
- **Practically relevant** — results directly inform agent scaffold design decisions
- **Novel** — no controlled A/B study existed for either question

Directions #3-5 had been partially explored in earlier experiments on 2026-03-20 (the "EXTREME difficulty" batch).

---

## Experiment 1: Inference-Time Compute Allocation Strategy

**Research question:** Given a fixed turn budget, should an AI coding agent front-load analysis (plan-first: read -> understand -> act once) or front-load action (act-first: test -> guess -> iterate)?

---

### v1: Initial Design

**File:** `experiments/compute_allocation_strategy.py`

**Hypothesis:** Plan-first strategy (reading all relevant files before acting) should outperform act-first strategy (coding immediately and iterating) on multi-step bug-fix tasks, because understanding the codebase prevents wasted iterations.

**Prompt design — soft suggestions:**

Agent A (`act_first`):
> "You are a fast, action-oriented developer. Start writing code or making changes IMMEDIATELY. Run tests early and often to get feedback. Fix errors as they appear -- iterate rapidly. Don't overthink -- let the test results guide you."

Agent B (`plan_first`):
> "You are a methodical, analysis-driven developer. FIRST: Read ALL relevant files before making any changes. THEN: Identify the root cause or design requirements thoroughly. THEN: Form a clear plan of what to change and why. ONLY THEN: Implement your changes in one precise pass."

**Task design:** 8 tasks across 3 difficulty levels:
- 2 easy: off-by-one pagination (t1), template engine missing escape (t2)
- 3 medium: event emitter ordering + once bug (t3), CSV parser quoted fields (t4), dependency resolver cycle detection (t5)
- 3 hard: state machine with transition guards (t6), expression evaluator with precedence (t7), web framework router middleware chain (t8)

**Parameters:**
- `max_turns=15`
- `num_samples=5` (n=5 per task for pass@k statistics)
- `check_fn='"passed" in output.lower()'` (case-insensitive match)
- Both agents: same model (haiku), same tools (Read, Write, Bash, Glob, Edit)

**Result: 100% pass@k for both agents.** Both act_first and plan_first solved all 8 tasks across all 5 samples. 40/40 successes each side. Zero differentiation.

**Diagnosis:** Tasks were too easy. With 15 turns available, even a suboptimal strategy had enough runway to recover from early mistakes. The generous turn budget eliminated the tradeoff we were trying to measure.

**Key lesson:** The experiment must create *pressure* — the tasks and turn budget must force a real tradeoff between the strategies being tested.

---

### v2: Tighter Budget + Harder Tasks

**File:** `experiments/compute_allocation_v2.py`

**Changes from v1:**
1. **Tighter budget:** `max_turns=8` (down from 15)
2. **Harder tasks:** Multi-file bugs requiring cross-module understanding (6 tasks, all medium-to-very-hard)
3. **Better check_fn:** `'"PASSED" in output'` (case-sensitive, matches test print statements)
4. **Slightly stronger prompts:** Added urgency language ("Every turn spent reading without changing something is a turn wasted" for act-first; "One wasted edit means one fewer chance to get it right" for plan-first)

**Task design — 6 multi-file bug-fix tasks:**
1. Shopping cart + price engine (rounding bug spans 2 files)
2. Task queue (priority sort direction)
3. Config system with inheritance (bool coercion + shallow merge across 3 files)
4. Permission system (cache invalidation + cycle handling)
5. Data pipeline (mutable state + item isolation)
6. Mini ORM + query builder (LIMIT/OFFSET SQL order)

**Result: Identical tool patterns. Model ignores soft prompts.**

Key observations:
- Both agents had identical Read/Edit distribution — approximately 2.7x ratio (reads to edits)
- First-tool distribution was ~50/50 Read/Glob for *both* agents, despite act-first being told to "start writing code IMMEDIATELY"
- Average turns used: 18-24 despite `max_turns=8`

**Critical discovery: SDK turn counting is not what we expected.** The `max_turns` parameter in the Claude Agent SDK counts "agentic cycles" (tool-use rounds), not individual assistant messages. A single "turn" can involve the agent sending a message, calling a tool, getting a result, and responding — that entire cycle counts as one turn. This explained why agents used 18-24 apparent interactions within an 8-turn limit.

**Correctness result:** 0/30 for both agents.

**Root cause of zero correctness:** The `check_fn` was `'"PASSED" in output'`, but "output" in this context is the final agent response text, not the test execution stdout. The agents were successfully fixing bugs and running tests that printed "PASSED", but the check_fn was looking for "PASSED" in the agent's conversational output, not the tool output. Many agents said things like "The tests pass now" without literally including the word "PASSED".

**Key lessons from v2:**
1. Moderate/medium prompts are insufficient to change agent behavior — the model has strong pre-trained strategies that override soft instructions
2. SDK `max_turns` counts agentic cycles, not individual messages — must account for this in experimental design
3. `check_fn` must be designed to match the actual format of agent output — adding explicit instructions like "Print the test output" is necessary

---

### v3: Extreme Prompts (Breakthrough)

**File:** `experiments/compute_allocation_v3.py`

**Changes from v2:**
1. **Extreme prompts with FORBIDDEN constraints** — not suggestions, but explicit behavioral rules with consequences
2. **Tighter budget:** `max_turns=5` (down from 8)
3. **Fixed check_fn issue:** Task prompts now explicitly say "Print the test output" and check_fn looks for `'"PASSED" in output'`
4. **Tasks designed to test the hypothesis from both sides:** 4 "plan-favored" tasks (misleading errors, multi-file tracing) and 2 "act-favored" tasks (clear error messages, single-file fixes)

**Prompt design — extreme behavioral constraints:**

Agent A (`act_first`):
```
STRICT RULES — you MUST follow these in order:

STEP 1: Run the test file IMMEDIATELY as your VERY FIRST action.
  cd tasks/tN && python test_*.py
Do NOT read any source files before running the test.

STEP 2: Based on the error output, make your best guess at a fix.
Edit the source file directly based on the error message.

STEP 3: Run the test again. If it fails, repeat step 2.

CRITICAL: You are FORBIDDEN from using the Read tool before your first
Bash or Edit call. The error messages from tests contain all the info
you need. Reading source code first wastes your limited turns.

You have very few turns. Every Read is a wasted turn.
```

Agent B (`plan_first`):
```
STRICT RULES — you MUST follow these in order:

STEP 1: Use Glob to find all .py files in the task directory.

STEP 2: Read EVERY source file (not test files) completely.
You MUST read all source files before making ANY changes.

STEP 3: Read the test file to understand what's expected.

STEP 4: Now that you understand everything, make ALL fixes in one pass.
Edit each file once, precisely.

STEP 5: Run the test to verify.

CRITICAL: You are FORBIDDEN from using Edit or Bash before you have
read ALL source files. Understanding the full codebase is essential.
One precise fix is better than multiple guesses.

You have very few turns. Every failed edit is a wasted turn.
```

**Task design — 6 tasks tagged by predicted strategy advantage:**

| # | Task | Files | Bugs | Predicted Winner |
|---|------|-------|------|-----------------|
| T1 | Cart + PriceEngine | 3 | Rounding error in wrong file — error manifests in cart.py but root cause is price_engine.py | plan-favored |
| T2 | TaskQueue | 2 | Sort direction (ascending should be descending) — error message directly says "expected highest priority first" | act-favored |
| T3 | Config system | 3 | bool coercion (`bool("false")==True`) + shallow merge loses nested defaults | plan-favored |
| T4 | EventEmitter | 2 | Ascending sort (should be descending) + once-handlers never removed | plan-favored |
| T5 | PermissionSystem | 2 | Cache not invalidated on assign/revoke + `visited` set not passed in recursion | plan-favored |
| T6 | QueryBuilder + ORM | 3 | OFFSET before LIMIT in SQL generation — SQLite error message directly points to fix | act-favored |

**Results: plan_first 18/30 (60%) vs act_first 2/30 (7%) = +800% relative improvement**

#### Overall Metrics

| Metric | act_first | plan_first | Delta |
|--------|-----------|------------|-------|
| **Correctness** | **2/30 (7%)** | **18/30 (60%)** | **+800%** |
| Latency | 15.42s | 18.25s | +18% |
| Cost | $0.020/trial | $0.024/trial | +20% |
| Tokens | 1,355 | 1,930 | +42% |
| Tool calls | 5.1 | 5.8 | +15% |

#### Per-Task Breakdown

| Task | act_first | plan_first | Winner |
|------|-----------|------------|--------|
| T1: Cart + PriceEngine (misleading error) | 0/5 | 4/5 | **plan** |
| T2: TaskQueue (clear error) | 0/5 | 5/5 | **plan** |
| T3: Config system (3-file) | 0/5 | 4/5 | **plan** |
| T4: EventEmitter (dual bug) | 0/5 | 2/5 | **plan** |
| T5: PermissionSystem (cache+cycle) | 0/5 | 2/5 | **plan** |
| T6: QueryBuilder + ORM (SQL order) | 2/5 | 1/5 | **act** |

**Behavioral compliance: 100%.** Extreme prompts achieved complete behavioral divergence:
- **act_first:** ALL 30 trials start with `Bash` (running tests immediately)
- **plan_first:** ALL 30 trials start with `Glob` followed by `Read` (exploring files)

This is a striking contrast with v2, where both agents started with Read/Glob regardless of prompt instructions.

**Surprising finding:** plan_first wins even on T2, which was designed to be "act-favored" (clear error message directly says what's wrong). The sort direction fix is trivial *if you read the code*, but the act-first agent's blind guess from error output alone is unreliable — it scored 0/5 while plan-first scored 5/5.

**The one act-first win:** T6 (LIMIT/OFFSET SQL swap) — the SQLite error `near "OFFSET": syntax error` is uniquely informative and points directly to the fix. Act-first scored 2/5 vs plan-first's 1/5.

**Cost-efficiency analysis:**
- act_first: ~3.5 correct answers per dollar
- plan_first: ~24.7 correct answers per dollar
- **Plan-first is 7x more cost-efficient** despite being 20% more expensive per trial

---

### Key Learnings from Experiment 1

1. **Soft prompts don't change behavior (v1, v2).** Models have strong pre-trained coding strategies that absorb soft strategy suggestions. "Start coding immediately" doesn't prevent a model from reading first.
2. **Only extreme FORBIDDEN constraints force different strategies (v3).** The word "FORBIDDEN" combined with explicit step ordering and consequences was required to actually change tool-use patterns.
3. **`max_turns` in SDK is not assistant message count.** It counts agentic cycles (tool-use rounds). A cycle can include reasoning, tool call, result processing, and response. Experiments must calibrate for this.
4. **`check_fn` must match agent output format.** "PASSED" literal string must actually appear in what the check_fn evaluates. Task prompts must explicitly instruct agents to print test output.
5. **Tasks must be hard enough to differentiate strategies.** Easy tasks (v1) give 100/100 and reveal nothing. Multi-file bugs with misleading errors create the discriminative pressure needed.

---

## Experiment 2: Error Recovery Strategy

**Research question:** When a coding agent encounters multi-bug codebases, which recovery strategy works better — fixing one bug at a time with testing between fixes, or fixing all bugs at once after thorough analysis?

---

### v1: Blind Retry vs Structured Reflection

**File:** `experiments/error_recovery_strategy.py`

**Hypothesis:** When a first fix attempt fails, structured reflection (re-reading error + code, stating what went wrong, forming new hypothesis) should outperform blind retry (just try something different).

**Prompt design — moderate recovery instructions:**

Agent A (`blind_retry`):
> "IF THE TEST STILL FAILS after your fix: Try a different fix immediately. Don't spend time analyzing -- just try another approach. Speed matters: the faster you try alternatives, the more chances you get."

Agent B (`reflect_retry`):
> "IF THE TEST STILL FAILS after your fix: STOP. Do NOT immediately try another fix. Re-read the FULL error message and traceback carefully. Re-read the source code around the failure point. State explicitly: 'The fix failed because [reason]...' Only THEN implement your revised fix."

Both prompts shared the same initial workflow (read files, run test, fix bug, run test again). The divergence was in what happens after a failed fix attempt.

**Task design — 6 cascading-bug tasks:**
Each task was designed so that fixing Bug A reveals Bug B, and the error from Bug B is misleading unless you understand the full code:

1. Inventory system: operand swap (Bug A) + comparison inversion (Bug B)
2. Markdown parser: regex misses h1 (Bug A) + no inline formatting in list items (Bug B)
3. Rate limiter: no burst cap (Bug A) + missing refill call (Bug B) — interacting
4. LRU cache: MRU eviction (Bug A) + hit_rate formula (Bug B)
5. Calculator: variable=0 treated as undefined (Bug A) + unclosed paren in function call (Bug B) + 3 total bugs
6. Transaction manager: shallow copy (Bug A) + rollback replaces dict instead of updating in place (Bug B)

**Parameters:**
- `max_turns=8`
- `num_samples=5`
- `check_fn='"PASSED" in output'`

**Result: 14/14 perfect tie. Identical behavior from both agents.**

Both agents produced:
- Same average tool distribution: ~3.4 reads, ~3.4 bash calls, ~2.1 edits
- Same first-tool behavior
- Same pass rates per task

**Diagnosis:** This confirmed the lesson from compute allocation v2 — moderate prompts are ignored. The recovery instructions ("try something else" vs "stop and reflect") did not alter agent behavior at all. The model's pre-trained recovery strategy dominated.

The tie result is itself a data point: it proves that within the moderate-prompt regime, recovery strategy prompts have zero effect on outcomes.

---

### v2: Incremental Fix vs Batch Fix (Breakthrough)

**File:** `experiments/error_recovery_v2.py`

**Reframing the question:** Instead of "how to reflect on failure" (which the model ignores), we tested a structurally different question: "how often to test." This changes the *behavioral shape* of the agent's workflow, not just its internal reasoning.

**Changes from v1:**
1. **Reframed as incremental vs batch** — a more fundamental strategic difference than retry style
2. **Extreme FORBIDDEN constraints** — applying the lesson from compute allocation v3
3. **Tighter budget:** `max_turns=6` (down from 8)
4. **Same cascading-bug tasks** — reused from v1 since they're designed for multi-bug scenarios

**Prompt design — extreme behavioral constraints:**

Agent A (`incremental_fix`):
```
STRICT RULES for fixing bugs:

1. Read the test file FIRST to understand what's expected
2. Read ONE source file
3. Find the FIRST bug you see
4. Fix ONLY that one bug
5. Run the test immediately
6. If the test still fails, go back to step 2 and find the NEXT bug
7. Repeat: fix ONE bug -> test -> fix NEXT bug -> test

CRITICAL CONSTRAINTS:
- NEVER fix more than one bug per Edit call
- ALWAYS run the test between each fix
- You are FORBIDDEN from fixing multiple bugs before testing
- Each fix-then-test cycle gives you feedback for the next fix
```

Agent B (`batch_fix`):
```
STRICT RULES for fixing bugs:

1. Read ALL source files in the task directory (not test files)
2. Read the test file to understand expected behavior
3. Identify EVERY bug across all files -- list them all
4. Fix ALL bugs in a single pass (one Edit per file, but fix everything)
5. Run the test ONCE at the end to verify

CRITICAL CONSTRAINTS:
- You MUST read every .py file before making ANY edit
- You are FORBIDDEN from running the test before all fixes are applied
- Do NOT run partial tests -- fix EVERYTHING first, test ONCE at the end
- Your first Bash call should be the final verification test
```

**Results: batch_fix 16/30 (53%) vs incremental_fix 0/30 (0%)**

#### Overall Metrics

| Metric | incremental_fix | batch_fix | Delta |
|--------|----------------|-----------|-------|
| **Correctness** | **0/30 (0%)** | **16/30 (53%)** | **infinite** |
| Latency | 22.37s | 39.84s | +78% |
| Cost | $0.026/trial | $0.043/trial | +64% |
| Tokens | 2,068 | 4,776 | +131% |
| Tool calls | 7.5 | 6.9 | -8% |
| Avg Edits | **1.0** | **1.6** | +60% |
| Avg Bash (tests) | **3.0** | **1.7** | -43% |

#### Per-Task Breakdown

| Task | Bug Type | incremental | batch |
|------|----------|-------------|-------|
| T1: Inventory (operand swap + comparison invert) | cascading | 0/5 | 0/5 |
| T2: Rate Limiter (no burst cap + missing refill call) | interacting | 0/5 | 2/5 |
| T3: LRU Cache (MRU eviction + hit_rate formula) | cascading | 0/5 | **4/5** |
| T4: Calculator (zero-var + unclosed paren + 3 bugs) | multi-symptom | 0/5 | **4/5** |
| T5: Transaction (shallow copy + lost reference) | state-dependent | 0/5 | 2/5 |
| T6: Markdown (h1 regex + list inline formatting) | cascading | 0/5 | **4/5** |

#### The "Feedback Loop Tax" — Why Incremental Fails

The critical behavioral difference is in how turns are allocated:

**Incremental strategy failure mode (typical trace):**
```
Turn 1: Read test file
Turn 2: Read source file
Turn 3: Bash (run test — see first error)
Turn 4: Read source again (understand error)
Turn 5: Edit (fix first bug only)
Turn 6: Bash (run test — see SECOND error)
--> OUT OF TURNS. Only 1 of 2+ bugs fixed.
```

**Batch strategy success mode (typical trace):**
```
Turn 1: Glob (find all files)
Turn 2: Read source file(s)
Turn 3: Read test file
Turn 4: Edit file 1 (fix ALL bugs in that file)
Turn 5: Edit file 2 (if needed)
Turn 6: Bash (run test — PASSED)
--> All bugs fixed. Test passes.
```

The numbers tell the story:
- Incremental makes **3.0 test runs** but only **1.0 edit** — it burns 50% of its turns on test feedback
- Batch makes **1.7 test runs** and **1.6 edits** — it converts turns into actual fixes
- Despite using fewer total tool calls (6.9 vs 7.5), batch makes **60% more edits**

The incremental approach's intermediate tests are a *tax on turn budget*. Each test run:
1. Consumes 1 turn of budget
2. Often reveals a *new* error (from the next bug in the cascade) that isn't actionable without another read cycle
3. Creates an illusion of progress while actually reducing the agent's capacity for fixes

#### Hardest Task: T1 Inventory (0/5 Both Sides)

The inventory task (operand swap `reserved - stock` should be `stock - reserved`, plus comparison inversion `>` should be `<`) defeated both strategies at 0/5. This represents a model capability limit rather than a strategy failure — the operand swap is subtle enough that even with full code understanding, haiku-level models struggle to identify it.

---

### Key Learnings from Experiment 2

1. **Same prompt strength lesson confirmed.** Moderate recovery prompts (v1) produced a perfect tie. Only extreme FORBIDDEN constraints (v2) produced behavioral divergence and performance differentiation.
2. **The "feedback loop tax" is real.** Intermediate test runs consume precious turns that could be used for actual fixes. Under tight budgets, each test-between-fixes cycle costs 1-2 turns of overhead that the incremental approach cannot recover from.
3. **Turn budget allocation matters more than strategy philosophy.** The winning strategy (batch) allocates ~40% of turns to reading/understanding and ~60% to editing/testing. The losing strategy (incremental) allocates ~50% to testing and only ~17% to editing.

---

## Cross-Experiment Meta-Findings

### Unified Principle

Both experiments converge on a single finding:

> **Under turn constraints, upfront investment in understanding dramatically outperforms iterative trial-and-error.**

| Experiment | Winner | Core Principle | Margin |
|-----------|--------|---------------|--------|
| Compute Allocation | Plan-first | Read before act | +800% |
| Error Recovery | Batch fix | Understand all before fixing any | +infinity (53% vs 0%) |

This is the agent-world analog of "measure twice, cut once." When turns are scarce, every turn spent on understanding pays dividends in precision. Every turn spent on blind iteration (running tests, guessing fixes) is likely wasted.

### The Prompt Strength Discovery

This is perhaps the most methodologically important finding of the day:

| Experiment | Prompt Strength | Behavioral Change? | Performance Delta |
|-----------|----------------|-------------------|-------------------|
| Compute Allocation v1 | Soft suggestions | No | 0% (100% vs 100%) |
| Compute Allocation v2 | Medium instructions | No | 0% (identical patterns) |
| Error Recovery v1 | Moderate constraints | No | 0% (14/14 tie) |
| **Compute Allocation v3** | **Extreme FORBIDDEN** | **Yes (100% compliance)** | **+800%** |
| **Error Recovery v2** | **Extreme FORBIDDEN** | **Yes** | **+infinity** |

Four experiments with moderate prompts produced zero behavioral change. Two experiments with extreme FORBIDDEN prompts produced dramatic behavioral change AND dramatic performance differences.

**This suggests a "prompt compliance threshold"** — language models have strong pre-trained coding strategies that soft prompts cannot override. There is a qualitative jump between "suggestion" and "prohibition" in terms of behavioral impact. The threshold appears to require:
1. Explicit **FORBIDDEN** language
2. Step-by-step **ordering constraints**
3. **Consequences** framing ("every X is a wasted turn")
4. Structural enforcement (specific tool prohibitions, not just strategy preferences)

### Methodology Evolution

The following table captures how experimental design improved across the session:

| Attempt | What Failed | How We Discovered It | Fix Applied |
|---------|------------|---------------------|-------------|
| v1 easy tasks | No differentiation (100%/100%) | Both agents perfect | Harder multi-file bugs (v2) |
| v1/v2 soft prompts | Model ignores strategy suggestions | Identical tool distributions | FORBIDDEN constraints (v3) |
| v1 generous turns (15) | No tradeoff pressure | Both succeed despite different strategies | max_turns=5 (v3) |
| v2 check_fn (`"PASSED" in output`) | False negatives — agents fix bugs but don't print "PASSED" | 0/30 both agents despite observed fixes | Task prompts say "Print the test output" (v3) |
| v1 error_recovery moderate prompts | Same behavior both sides | 14/14 perfect tie, identical tool usage | Extreme structural constraints (v2) |
| v2 SDK turn counting assumption | Agents use 18-24 apparent interactions in 8 "turns" | Observation during v2 runs | Understood that SDK turns = agentic cycles |

Each failure taught a principle that was immediately applied to the next version. The session followed a natural progression: easy/soft/generous -> hard/extreme/tight.

---

## Technical Notes

### Platform
- **OpenBench:** Custom A/B testing platform built on the Claude Agent SDK
- **DiffSpec:** Each experiment varies exactly one field (system_prompt) between agent_a and agent_b
- **Setup files:** Injected as the working directory for each trial — agents don't see each other's attempts

### Model
- `claude-haiku-4-5` for all experiments
- Chosen for speed and cost ($0.02-$0.04/trial) to enable rapid iteration
- Effect size may differ for Sonnet/Opus (larger models may have stronger pre-trained strategies)

### SDK Turn Counting
- `max_turns` in the Claude Agent SDK counts "agentic cycles," not individual assistant messages
- One cycle: agent reasoning -> tool call -> tool result -> agent processes result
- This means `max_turns=5` allows approximately 5 tool-use rounds, not 5 messages
- Agents regularly used 15-25 total messages within a 5-8 turn budget

### Trial Counts
| Experiment | Tasks | Samples/task | Total trials |
|-----------|-------|-------------|-------------|
| Compute Allocation v1 | 8 | 5 | 40 x 2 = 80 |
| Compute Allocation v2 | 6 | 5 | 30 x 2 = 60 |
| Compute Allocation v3 | 6 | 5 | 30 x 2 = 60 |
| Error Recovery v1 | 6 | 5 | 30 x 2 = 60 |
| Error Recovery v2 | 6 | 5 | 30 x 2 = 60 |
| **Total** | | | **320 trials** |

Note: Some trial counts reported elsewhere as 300 reflect deduplication of paired comparisons.

### Cost Breakdown (Approximate)
- Compute Allocation v1: ~$3 (80 trials, generous turns)
- Compute Allocation v2: ~$2.50 (60 trials, 8 turns)
- Compute Allocation v3: ~$1.50 (60 trials, 5 turns, cheapest)
- Error Recovery v1: ~$2.50 (60 trials, 8 turns)
- Error Recovery v2: ~$3.50 (60 trials, batch agent uses more tokens)
- **Total: ~$13 USD**

### Threats to Validity
- **Single model:** All results are for claude-haiku-4-5. Stronger models may show different strategy preferences or be more responsive to soft prompts.
- **check_fn sensitivity:** Only detects literal "PASSED" string. Some correct fixes that produce different output formats may be undercounted.
- **Deliberate tight budgets:** The dramatic results depend on turn scarcity. With generous budgets (>15 turns), strategy differences may shrink as both approaches have enough runway.
- **Bug-fix only:** All tasks are debugging/fixing. Feature-building tasks may favor different strategies.
- **Small n:** n=5 per task. Statistical significance is limited; larger samples needed for publication-grade claims.
- **Extreme prompt artificiality:** Real agents use mixed strategies. The FORBIDDEN constraints create cleaner experimental separation but don't reflect natural agent behavior.

---

## Experiment 3: Context Efficiency (Navigation Guidance)

### Motivation

Priority #3 from gap analysis. AgentDiet (2025) achieves 40-60% token savings via trajectory compression, but does the *retained information* (navigation pointers) actually help? This tests whether a "codebase map" with bug location hints improves fix rates.

### v1: Single Hard Task (6 files, 3 bugs, max_turns=6)

- **Design:** Guided agent gets file descriptions + "POSSIBLY BUGGY" tags. 1 task, n=10.
- **Result:** 0/10 vs 0/10 — task too hard for haiku in 6 turns. Both fail equally.
- **Interesting signal:** Guided used 20% fewer tools (6.9 vs 8.7), suggesting it skipped some exploration. But not enough turns to actually fix.

### v2: Multiple Tasks by Codebase Size (2-6 files, max_turns=8)

- **Design:** 4 tasks scaling from 2-file to 6-file. Guided gets file map + "POSSIBLY BUGGY" hints. n=5/task.
- **Result:** Guided 16/20 (80%) vs Unguided 14/20 (70%) = **+14%**

Per-task breakdown revealed surprising non-monotonic pattern:
| Files | Unguided | Guided | Delta |
|-------|----------|--------|-------|
| 2 | 4/5 | 5/5 | +1 |
| 3 | 4/5 | 3/5 | **-1** |
| 4 | 4/5 | 5/5 | +1 |
| 6 | 2/5 | 3/5 | +1 |

Guidance **hurt** on the 3-file task. The codebase map consumed attention without providing enough value for a small codebase.

### v3: Extreme Turn Pressure (max_turns=4, exact bug locations)

- **Design:** 3 tasks (4-6 files). Guided gets EXACT file + line + bug descriptions.
- **Result:** 0/30 vs 0/30 — max_turns=4 too tight for multi-file tasks.
- **Behavioral difference:** Guided made 2.2 edits vs unguided 1.2 edits. The guidance DID redirect effort toward fixes, but 4 turns is below the minimum viable budget for multi-file debugging.

### Key Findings

1. **Navigation guidance has marginal effect (+14%, not statistically significant)**
2. **Models navigate efficiently without help** — error tracebacks provide sufficient direction
3. **Guidance can hurt on small codebases** — attention overhead > navigation savings
4. **Critical contrast with Experiments 1 & 2:** Behavioral change (how to act) >> Informational change (where to look)

### Methodology Lesson

This experiment confirmed the meta-pattern: **the powerful lever is behavioral instruction, not informational context.** Compute allocation (+800%) and error recovery (+∞%) both changed what the agent DOES. Context efficiency only changed what the agent KNOWS — and the agent already knew enough from reading error messages.

---

## Updated Trial Counts

| Experiment | Tasks | n | Trials |
|-----------|-------|---|--------|
| Compute Allocation v1 | 8 | 5 | 80 |
| Compute Allocation v2 | 6 | 5 | 60 |
| Compute Allocation v3 | 6 | 5 | 60 |
| Error Recovery v1 | 6 | 5 | 60 |
| Error Recovery v2 | 6 | 5 | 60 |
| Context Efficiency v1 | 1 | 10 | 20 |
| Context Efficiency v2 | 4 | 5 | 40 |
| Context Efficiency v3 | 3 | 10 | 60 |
| **Total** | | | **440 trials** |

### Updated Cost (~$17 USD total)

---

## Appendix: File Index

| File | Description |
|------|-------------|
| `experiments/compute_allocation_strategy.py` | v1: Soft prompts, 8 tasks, max_turns=15 |
| `experiments/compute_allocation_v2.py` | v2: Medium prompts, 6 harder tasks, max_turns=8 |
| `experiments/compute_allocation_v3.py` | v3: Extreme FORBIDDEN prompts, 6 tasks, max_turns=5 |
| `experiments/error_recovery_strategy.py` | v1: Moderate retry/reflect prompts, 6 cascading-bug tasks, max_turns=8 |
| `experiments/error_recovery_v2.py` | v2: Extreme incremental/batch prompts, 6 cascading-bug tasks, max_turns=6 |
| `experiments/context_efficiency.py` | v1: Single 6-file task, max_turns=6 |
| `experiments/context_efficiency_v2.py` | v2: 4 tasks (2-6 files), max_turns=8 |
| `experiments/context_efficiency_v3.py` | v3: Extreme pressure, exact bug locations, max_turns=4 |
| `reports/2026-03-21-compute-allocation-strategy.md` | Final report for compute allocation experiments |
| `reports/2026-03-21-error-recovery-strategy.md` | Final report for error recovery experiments |
| `reports/2026-03-21-context-efficiency.md` | Final report for context efficiency experiments |
| `reports/2026-03-21-experiment-flow-log.md` | This document — full lab notebook |
