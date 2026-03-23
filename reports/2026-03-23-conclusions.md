# OpenBench 实验总结论

**平台:** OpenBench — Claude Agent A/B 测试平台
**周期:** 2026-03-17 → 2026-03-23（7 天）
**规模:** 143 个实验组，4,774 次 trial，~$80 USD
**模型:** claude-haiku-4-5（主力），claude-sonnet-4-6（对照）

---

## 一、核心发现（6 条原则）

### 原则 1：理解优先于行动

> **在 turn 受限条件下，先理解再行动大幅优于先行动再迭代。**

| 实验 | 胜者 | 对比 | 幅度 |
|:--|:--|:--|:-:|
| 计算分配 v3 | Plan-first（先读代码） | vs Act-first（先跑测试） | **+800%** |
| 错误恢复 v2 | Batch fix（一次修完） | vs Incremental（逐个修） | **+∞ (53% vs 0%)** |
| Prompt 合规 | Read-first | vs Test-first | **+25-31pp** |

**机制：** 每次"试一下看看"都消耗一个 turn 但不一定推进修复。先读懂代码的 agent 能一次精准修复，省下的 turn 用来验证。这是 agent 世界的"量两次，切一次"。

---

### 原则 2：任何中间开销都有害

> **强制的中间过程（测试、回退、记笔记）与生产性工作竞争 turn 预算。**

| 开销类型 | Turn 成本 | 对正确率的影响 |
|:--|:-:|:--|
| 中间测试（incremental fix） | ~50% turns | 0% vs 53% |
| 回退+重读（pivot strategy） | +13% cost | 70% vs 90% |
| 强制记笔记（scratchpad） | 42% tools | 0-65% vs 100% |
| 先跑测试再读代码 | ~1 wasted turn | 69-75% vs 94-100% |
| "顺便改善"代码质量 | +13% tools | 60% vs 80% |

**实践意义：** Agent 的系统提示应该让它做最少的必要工作。"先读再修再验"是最优循环，任何额外步骤（中间测试、写笔记、回退重试、顺便重构）都降低效果。

---

### 原则 3：上下文窗口就是工作记忆

> **对于适合放入上下文的代码库（≤8 文件），外部化记忆是纯开销。**

| 规模 | Implicit | Scratchpad | 差距 |
|:--|:-:|:-:|:-:|
| 3 文件, 12 turns | 100% | 0% | -100% |
| 3 文件, 20 turns | 100% | 65% | -35% |
| 8 文件, 25 turns | 100% | 60% | -40% |

**机制：** LLM 在 tool call 之间不会"忘记"之前读的文件。强制写 `_notes.md` 消耗 30-42% 的工具调用，但不增加任何信息。上下文窗口本身就是完美的工作记忆（在窗口容量内）。

**边界条件：** 未测试 20+ 文件场景。上下文窗口真正不够用时，scratchpad 可能变得有价值。

---

### 原则 4：Prompt 合规取决于具体性，而非强度

> **控制 agent 行为的关键是指定具体动作，而非使用 FORBIDDEN 等强力措辞。**

| Prompt 风格 | 具体性 | 合规率 |
|:--|:--|:-:|
| "Start coding immediately" | 模糊（code = read? edit? bash?） | **0%** |
| "Read ALL relevant files before changes" | 中等 | **0%** |
| "Start with running the test file" | **精确动作 → Bash** | **100%** |
| "Start with reading every .py file" | **精确动作 → Read/Glob** | **100%** |
| "FORBIDDEN from using Read before Bash" | 精确工具名 + 禁止 | **100%** |

**修正了早期结论：** 最初认为只有 EXTREME FORBIDDEN prompt 才能改变行为。实际上，只要 prompt 能映射到具体的工具调用，moderate prompt 就有 100% 合规率。之前 v2 失败是因为"Start coding"太模糊，不是因为语气太温和。

**适用于 Haiku 和 Sonnet** — 两个模型对具体指令都有 100% 合规。

---

### 原则 5：最小化修改，避免附带损害

> **指示 agent "顺便改善"代码会导致 25% 的回归。**

| 策略 | 正确率 | 失败原因 |
|:--|:-:|:--|
| Minimal fix（只修 bug） | **80%** | 仅 T4 格式化 bug 太难 |
| Thorough fix（修 + 重构） | **60%** | 重构触发了代码陷阱 |

**具体陷阱：**
- `divide()` 返回 `None`（测试期望 `None`）→ 重构 agent 改为 raise → 测试断裂
- `get()` 返回 `deepcopy`（测试验证隔离性）→ 重构 agent 删掉 copy → 隔离性测试失败

**实践意义：** Agent 的系统提示应该明确说"只修报告的问题，不要碰其他代码"。"Leave it better than you found it" 在 agent 上下文中是危险的。

---

### 原则 6：check_fn 有模型偏见

> **字面匹配 (`"PASSED" in output`) 对不同模型不公平。**

| 模型 | 输出风格 | check_fn 匹配 |
|:--|:--|:-:|
| Haiku | 直接复制测试输出："PASSED" | ✅ |
| Sonnet | 概述："All 4 tests pass" | ❌ 假阴性 |

**影响：** 原始数据显示 Haiku 11/12 vs Sonnet 5/12（+120% 差距）。修正后 11/12 vs 11/12（0% 差距）。**所有使用字面匹配的跨模型比较都可疑。**

**修复：** 使用 `"pass" in output.lower()` 或在 task prompt 中明确要求 "Print the exact test output verbatim"。

---

## 二、实验方法论经验

### 2.1 实验设计公式

经过 20+ 次失败迭代，总结出可靠的 A/B 实验公式：

1. **任务难度校准：** 基线 agent 正确率应在 40-80%。太简单 = 100/100 无区分；太难 = 0/0 无区分
2. **Prompt 要具体：** 指定"第一个工具调用是 X"而不是"你应该先做 X"
3. **Turn 预算要制造压力：** 刚好够高效 agent 完成，逼低效 agent 暴露问题
4. **check_fn 要格式无关：** 不依赖模型输出的具体措辞
5. **每个实验只改一个变量：** DiffSpec 原则

### 2.2 常见失败模式

| 失败 | 如何发现 | 修复 |
|:--|:--|:--|
| 任务太简单（100%/100%） | 两边都完美 | 更难的多文件 bug |
| Prompt 太模糊（行为相同） | 工具分布一致 | 具体化到工具名 |
| Turn 太多（无压力） | 两边都成功 | 降低 max_turns |
| check_fn 不匹配输出格式 | 0/N 但观察到修复 | 让 agent 打印测试输出 |
| SDK turn ≠ 消息数 | 8 turn 限制下观察到 24 条消息 | 理解 agentic cycle 概念 |

### 2.3 关键洞察：turn 是最稀缺资源

> Agent 性能 = f(每个 turn 的生产力)

所有实验都指向同一结论：**优化 agent 的核心不是选择"更好的策略"，而是减少非生产性 turn 的浪费。**

最优 agent 的 turn 分配：
```
40% 读代码（理解）
40% 编辑代码（修复）
20% 运行测试（验证）
0%  中间测试/笔记/回退/重构
```

---

## 三、Context 管理（实时上下文系列）

### 3.1 格式不重要，体积重要

4 种格式（key_value、indexed、json_lines、toon）在准确率上无显著差异（95-100%）。真正的优化是减少注入的数据量。

### 3.2 Summary + Recent 是最优策略

| 策略 | Prompt 大小 | 准确率 | 适用场景 |
|:--|:-:|:-:|:--|
| Full history | 100% | 100% | 需要精确历史查询 |
| Summary + last 10 | 36% | 74% | 大多数监控场景 |
| Last 5 only | 18% | 20% | 仅最新值查询 |

### 3.3 模型真正理解时间戳

Shuffled（非时序排列）的数据，模型仍能正确找到最新值（100% 准确率）。但 reasoning 开销增加 3-5x。保持时序排列不仅是准确率问题，更是成本问题。

### 3.4 导航指引有害（Anchoring Bias）

给 agent 提供 "这个文件可能有 bug" 的提示，**反而降低正确率 37-42%**。机制：预设提示减少了 agent 的测试驱动探索，导致更少的验证循环。

---

## 四、给 Agent 构建者的实践建议

### 系统提示模板

```
你是一个 [角色]。按以下步骤工作：

1. 读取所有相关源文件
2. 读取测试文件了解预期行为
3. 一次性修复所有问题
4. 运行测试验证

约束：
- 只修改直接导致测试失败的代码
- 不要重构、清理或"改善"正常工作的代码
- 不要在修复之间运行中间测试
```

### 不要做的事

1. ❌ 不要让 agent "边修边测"（feedback loop tax）
2. ❌ 不要让 agent 维护 scratchpad/notes（memory tax）
3. ❌ 不要让 agent 失败后"推翻重来"（revert tax）
4. ❌ 不要让 agent "顺便改善"其他代码（collateral damage）
5. ❌ 不要在 prompt 中提供 bug 位置提示（anchoring bias）
6. ❌ 不要用模糊策略描述控制行为（用具体工具名）

### 要做的事

1. ✅ 让 agent 先读完所有文件再动手
2. ✅ 一次修复所有 bug，最后测试一次
3. ✅ 失败后保留已有修复，只补充修改
4. ✅ 只修报告的问题，不碰其他代码
5. ✅ 用具体工具名指定行为（"Start with Read"）
6. ✅ 实时上下文用 summary + recent 格式
