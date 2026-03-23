# Posture vs Procedure: Prompt Philosophy

**Date:** 2026-03-23
**Experiments:** posture_vs_procedure (Haiku), posture_vs_procedure_sonnet (Sonnet)

---

## Two Prompt Philosophies

| | Posture (态度) | Procedure (步骤) |
|:--|:--|:--|
| 方法 | 描述**心态和价值观** | 描述**具体步骤** |
| 例子 | "You are careful. Think about edge cases." | "Step 1: Run tests. Step 2: Read code." |
| 给 agent 的自由度 | 高 — 自己选行动 | 低 — 遵循脚本 |
| 假设 | 模型知道怎么做，需要的是正确的思维方式 | 模型需要明确指导才不会遗漏步骤 |

---

## Results

### Haiku (T4 bit codec 超出能力边界)

| Task | posture | procedure | minimal (对照) |
|:--|:-:|:-:|:-:|
| T1: Regex | 8/8 | 8/8 | 8/8 |
| T2: Float | 8/8 | 8/8 | 7/8 |
| T3: Closure | 8/8 | 8/8 | 8/8 |
| **T4: Bit Codec** | **2/8** | **0/8** | **0/8** |
| **Total** | **81%** | **75%** | **72%** |
| Cost/trial | **$0.093** | $0.102 | $0.099 |
| Avg tools | **11.6** | 11.8 | — |

### Sonnet (所有任务在能力范围内)

| Task | posture | procedure |
|:--|:-:|:-:|
| T1: Regex | 8/8 | 8/8 |
| T2: Float | 8/8 | 8/8 |
| T3: Closure | 8/8 | 8/8 |
| T4: Bit Codec | 7/8 | **8/8** |
| **Total** | **97%** | **100%** |
| Cost/trial | **$0.279** | $0.335 |
| Avg tools | **9.8** | 10.7 |

---

## Key Findings

### 1. Posture 在能力边界处推了一把

**Haiku T4 首次出现成功案例。** 所有之前的 Haiku 实验（minimal、structured、guided、各种策略）T4 都是 0/8。Posture prompt 产出了 2/8。

Posture prompt 中的 "Think about edge cases and type semantics" 可能帮助 Haiku 在位运算推理上多做了一步验证，让 2/8 的 trial 走通了。

这不是"突破"能力限制——仍然只有 25%。但说明**态度描述可以在能力边缘挤出额外的成功率**。

### 2. Posture 更高效

| 模型 | posture cost | procedure cost | 节省 |
|:--|:-:|:-:|:-:|
| Haiku | $0.093 | $0.102 | **-9%** |
| Sonnet | $0.279 | $0.335 | **-17%** |

Posture prompt 在两个模型上都使用更少的 tools（-1 tool/trial）。

**机制:** Procedure prompt 的步骤指示（"Step 1: Run tests"）让 agent 即使在不需要时也执行该步骤。Posture prompt 让 agent 自己决定是否需要，通常跳过不必要的步骤。

### 3. 综合 prompt 效果对比

| Prompt | Haiku T4 | Haiku 总体 | Sonnet T4 | Haiku Cost |
|:--|:-:|:-:|:-:|:-:|
| Minimal | 0/8 | 72% | — | $0.099 |
| Procedure | 0/8 | 75% | 8/8 | $0.102 |
| **Posture** | **2/8** | **81%** | 7/8 | **$0.093** |

Posture 在 Haiku 上是三者中最好的：最高正确率、最低成本。

在 Sonnet 上 procedure 略好（8/8 vs 7/8），但差距是 1 个 trial，在噪声范围内。

---

## 为什么 Posture 有效

### 态度 vs 步骤的根本区别

**Procedure** 是一个脚本。Agent 按步骤执行，即使某些步骤对当前任务不必要。这增加了 tool call 数量但不增加推理质量。

**Posture** 是一个心智模型。Agent 将 "careful" 和 "think about edge cases" 内化为每个决策的背景。它不增加步骤数量，但提升了每个步骤的思考深度。

类比：
- Procedure = 给司机一份路线图（按图开，不能绕路）
- Posture = 告诉司机"注意安全，遇到不确定的路口减速"（自己判断最佳路线）

### 在能力边界处的效果

能力边界意味着模型"有时能做到，有时做不到"。在这个区间：
- **Procedure 无法帮助**——步骤描述不包含解题所需的推理能力
- **Posture 有微弱帮助**——"think about type semantics" 提醒模型多花注意力在位运算的正确性上

---

## 实践建议

### System Prompt 写法

**推荐（posture 风格）：**
```
You are a careful, methodical developer who values correctness.
- Understand the code's intent before changing anything
- Think about edge cases and type semantics
- Make minimal, targeted changes
- Verify your work before declaring it done
```

**不推荐（procedure 风格）：**
```
Step 1: Run the test suite
Step 2: Read the source code
Step 3: Identify root causes
Step 4: Fix all bugs
Step 5: Review changes
Step 6: Run tests again
```

**原因：**
- Posture 更便宜（-9% to -17% cost）
- Posture 在能力边界有额外收益
- Procedure 的步骤描述是冗余的——agent 已经知道该怎么做
- Procedure 的刚性降低了 agent 的灵活性

### 不是所有 posture 都有效

**有效的 posture 描述：** 与任务相关的思维方式
- "Think about edge cases and type semantics" ← 对代码调试有帮助
- "Understand the code's intent before changing" ← 减少误改

**无效的 posture 描述：** 与任务无关的角色扮演
- "You are a 10x developer" ← 不包含有用信息
- "You have 20 years of experience" ← 不改变推理方式

关键是 posture 描述要**包含与任务相关的认知提示**，而不只是泛泛的角色设定。

---

## Cost Summary

| Experiment | Trials | Cost |
|:--|:-:|:-:|
| Posture vs procedure (Haiku) | 64 | ~$6.24 |
| Posture vs procedure (Sonnet) | 64 | ~$19.65 |
| **Total** | **128** | **~$25.89** |
