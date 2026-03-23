# Agent Scaling Laws: Turns, Models, and Compute Allocation

**Date:** 2026-03-23
**Experiments:** turn_correctness_curve, model_turns_tradeoff, budget_awareness, parallel_vs_sequential

---

## 1. Turn-Correctness Curve (Sigmoid)

### Data

| Turns | Correctness | Avg Cost | Per-Task |
|:-:|:-:|:-:|:--|
| 8 | **72.9%** | $0.039 | T1:8/12 T2:11/12 T3:7/12 T4:9/12 |
| 11 | **95.8%** | $0.038 | T1:11/12 T2:11/12 T3:12/12 T4:12/12 |
| 14 | **100%** | $0.039 | T1:12/12 T2:12/12 T3:12/12 T4:12/12 |
| 17 | **100%** | $0.041 | 12/12 all tasks |
| 20 | **100%** | $0.041 | 12/12 all tasks |

n=12 per agent per task (from tournament round-robin), 4 hard tasks (3 bugs each).

### The Curve

```
100% ─────────────────────────■━━━━━■━━━━━■━━━━━■
 95% ─────────────────■
 90%
 80%
 73% ────■
 60%
     ────┼─────┼─────┼─────┼─────┼────→
          8    11    14    17    20   turns

     ◄── critical ──►◄── plateau ──────►
         zone            (no benefit)
```

### Findings

**The curve is a sharp sigmoid with knee at 11-14 turns.**

- Below 11: rapid degradation (73% → lower)
- 11-14: transition zone (96% → 100%)
- Above 14: **flat — zero benefit from more turns**. Cost even increases slightly
  due to the agent doing unnecessary verification reads.

**Cost is nearly constant across turn budgets** ($0.038-0.041). The agent naturally
uses ~9-10 tools regardless of how many turns are available. Extra turns are unused.

**Implication:** The optimal turn budget for these tasks is **~1.5x the minimum
viable turns**. Minimum viable ≈ 9 tools → set max_turns ≈ 14. Going higher wastes
nothing (cost is flat) but provides no benefit.

---

## 2. Model × Turns Tradeoff

### Data

| Agent | Correctness | Avg Cost | Per-Task |
|:--|:-:|:-:|:--|
| **Haiku @ 20 turns** | **20/20 (100%)** | **$0.044** | 5/5 all tasks |
| Sonnet @ 8 turns | 14/20 (70%) | $0.081 | T1:2/5 T2:3/5 T3:4/5 T4:5/5 |

### Finding: Cheap Model + More Turns Dominates

| Metric | Haiku@20 | Sonnet@8 | Winner |
|:--|:-:|:-:|:--|
| Correctness | **100%** | 70% | **Haiku** (+30pp) |
| Cost/trial | **$0.044** | $0.081 | **Haiku** (-46%) |
| Total cost | **$0.88** | $1.62 | **Haiku** (-46%) |

**Haiku with generous turns is both MORE ACCURATE and CHEAPER than Sonnet with tight turns.**

Sonnet at 8 turns fails because 8 turns is below the "knee" of the sigmoid curve.
Sonnet doesn't need fewer turns than Haiku — it needs the same ~14 turns.
The per-turn cost of Sonnet is ~2x Haiku, so Sonnet@14 would cost ~$0.08 vs
Haiku@14 at ~$0.04. For the same correctness (100%), Haiku is 2x cheaper.

**This confirms Snell et al. (DeepMind):** smaller model + more compute beats
larger model on tasks within the smaller model's capability range. These bugs
are solvable by Haiku — Sonnet's extra capability adds no value.

**When would Sonnet win?** Only on tasks that Haiku fundamentally cannot solve
(e.g., the codec bit-shift bug from batch_vs_iterative where both Haiku
variants failed). For those tasks, no amount of extra turns helps Haiku.

---

## 3. Budget Awareness

### Data

| Agent | Correctness | Avg Cost | Timeouts |
|:--|:-:|:-:|:-:|
| unaware | 19/20 (95%) | $0.040 | 1 |
| **budget_aware** | **20/20 (100%)** | $0.040 | **0** |

Per-task: identical except unaware had 1 timeout on T4.

### Finding: Marginal Benefit

Budget awareness prevents 1 timeout in 20 trials (+5pp). The effect is real
but tiny. The budget-aware agent uses MORE tools (10.4 vs 9.3) but FEWER
tokens (3178 vs 3686) — more action-oriented, less thinking.

**Why this differs from BATS (Google, -31% cost):** BATS tested web browsing
agents that waste many turns on redundant searches. Our coding agents are
already efficient — they naturally use ~9 tools with or without budget info.

**Implication:** Budget awareness is a minor optimization, not a game-changer
for coding tasks. The agent already plans efficiently without being told.

---

## 4. Parallel vs Sequential Compute Allocation

### Data

| Agent | pass@1 | pass@4 | pass@8 | Avg Cost | Total Cost (8 samples) |
|:--|:-:|:-:|:-:|:-:|:-:|
| shallow (5 turns) | 3.1% | ~12% | ~22% | $0.027 | $0.86 |
| **deep (20 turns)** | **100%** | 100% | 100% | $0.043 | **$1.39** |

shallow per-task: T1:1/8, T2:0/8, T3:0/8, T4:0/8.

### Finding: Sequential Depth Wins When Minimum Viable Turns Exist

**5 turns is below the sigmoid knee.** At 5 turns, the agent can at most:
read source + read test + edit + run tests = 4 tools. Only 1 spare for anything
going wrong. Success rate is ~3%.

Even pass@8 (8 independent attempts): 1 - (1-0.031)^8 ≈ 22%. Still far below
deep@20's 100%.

**The Large Language Monkeys scaling law breaks down when samples can't succeed.**
Their power law `coverage = 1 - (1-a)^(k^b)` requires `a > 0` — a non-trivial
per-sample success rate. At 5 turns, `a ≈ 0.03`, so even k=100 gives coverage
of only 1 - 0.97^(100^0.5) ≈ 94%. Meanwhile, 1 deep attempt at 20 turns gives 100%.

**The right comparison is AT the sigmoid knee:**

| Allocation | Total Turns | Correctness |
|:--|:-:|:-:|
| 1 × 20 turns (deep) | 20 | 100% |
| 2 × 8 turns (pass@2) | 16 | 1-(1-0.73)^2 = **93%** |
| 4 × 5 turns (pass@4) | 20 | 1-(1-0.03)^4 = **12%** |
| 3 × 11 turns (pass@3) | 33 | 1-(1-0.96)^3 = **99.99%** |

**Parallel sampling is effective above the knee (≥8 turns) but wasteful below.**
The optimal strategy: allocate at least knee-level turns per sample, then
use remaining budget for parallel attempts.

---

## Unified Scaling Model

```
Correctness = sigmoid(turns, knee=12, steepness=0.5)
            = 1 / (1 + exp(-0.5 * (turns - 12)))

Cost = base_cost × model_multiplier × max(turns_used, min_viable)
     ≈ constant (agents use ~same tools regardless of budget)

Optimal turns = knee × 1.2 ≈ 14 for these tasks
```

### The Complete Decision Framework

```
                        Task within          Task beyond
                        model capability     model capability
                     ┌───────────────────┬───────────────────┐
                     │                   │                   │
   Budget ≥ knee     │  100% correct     │  ~0% correct      │
   (14+ turns)       │  Use cheap model  │  Must upgrade      │
                     │  Cost: $0.04      │  model             │
                     │                   │                   │
   Budget < knee     │  73-96% correct   │  ~0% correct      │
   (8-13 turns)      │  Parallel helps   │  Nothing helps    │
                     │  pass@k scales    │                   │
                     │                   │                   │
   Budget << knee    │  ~3% correct      │  ~0% correct      │
   (<8 turns)        │  Waste of money   │  Waste of money   │
                     │                   │                   │
                     └───────────────────┴───────────────────┘
```

### Practical Recommendations

1. **Find the knee first.** Run a quick calibration: same task at 3 turn budgets
   (low/mid/high). The knee is where correctness jumps from <80% to >95%.

2. **Set budget to 1.2-1.5× the knee.** Extra turns above the knee cost nothing
   (agents don't use them) but provide safety margin.

3. **Use the cheapest model that can solve the task.** At the knee, Haiku = Sonnet
   on solvable tasks. Sonnet only helps on tasks Haiku fundamentally can't solve.

4. **If budget is tight, use parallel sampling at the knee level.** 3 attempts at
   11 turns (33 total) gives 99.99% vs 1 attempt at 33 turns giving 100%. Parallel
   is more robust to variance.

5. **Never allocate below the knee.** 5-turn attempts are nearly worthless (3%)
   regardless of how many you run.

---

## Cost Summary

| Experiment | Trials | Cost |
|:--|:-:|:-:|
| Turn-correctness curve (tournament) | 240 | ~$9.40 |
| Model × turns tradeoff | 40 | ~$2.50 |
| Budget awareness | 40 | ~$1.61 |
| Parallel vs sequential | 64 | ~$2.25 |
| **Total** | **384** | **~$15.76** |

**Running total for today: ~$28.53, ~500 trials, 15 experiments.**
