# 20 工作区模式指南：Copilot 与 Autonomous

这篇文档专门解释 DeepScientist 创建项目时最重要的两种模式：

- `Copilot`
- `Autonomous`

适合这些场景：

- 你正准备创建一个新项目
- 你不确定该选哪种启动方式
- 你想理解为什么有的项目会先待命，有的项目会一创建就开始推进

如果你只想快速安装并跑通第一条路径，先看 [00 快速开始](./00_QUICK_START.md)。

如果你想看启动表单和提交 payload 的精确字段，再看 [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)。

## 1. 一句话总结

- `Copilot`：安静启动、用户主导、做完当前请求单元后通常停驻
- `Autonomous`：标准版 DeepScientist，默认继续推进 quest

## 2. 你是在哪里选择它的

在首页或 Projects 页面里，新建项目时会先让你选择启动方式：

- `Copilot Mode`
- `Autonomous Mode`

当前 UI 里可能会看到两层文案：

- 外层入口：`Start Research` 或 `Start Experiment`
- 模式选择弹窗标题：`Choose the start style`

选完之后，这两条创建路径就会分开。

## 3. Copilot 模式

### 3.1 它是什么

Copilot 模式是“用户主导的工作区”。

适合你想让 DeepScientist 主动帮忙，但又希望每个工作单元都由你来明确主导的场景，例如：

- 看仓库
- 读论文
- 改代码
- debug
- 设计实验
- 检查运行状态
- 改写段落
- 汇总结论

它不应该默认把你的一句话理解成“现在开始完整自治科研流程”。

### 3.2 创建之后会发生什么

创建 Copilot 项目之后：

- 项目会被创建出来
- quest 会保持 idle / 待命
- agent 等你发第一条真正的工作指令

也就是说：

- 不会因为项目存在就立刻自动开跑
- 不会默认直接进入 baseline / experiment / write 长循环
- 第一轮实质动作从你的第一条消息开始

### 3.3 continuation 行为

Copilot 模式对 continuation 是刻意保守的。

在当前请求单元完成之后，DeepScientist 正常应该：

- 说明这轮做了什么
- 把上下文和结果持久化
- 等待你下一条消息或 `/resume`

它适合这些目标：

- 你想强控制节奏
- 你想按 request-by-request 方式协作
- 你不希望后台自己扩太多
- 你希望 handoff 点很清楚

### 3.4 什么时候适合选

选择 `Copilot`，通常意味着：

- 你想先看、先问、先改，再决定是否启动长任务
- 当前任务边界还不清楚
- 你预期会频繁交互式迭代
- 你想让 DeepScientist 更像“科研 IDE 搭子”，而不是自治 operator

### 3.5 什么时候不适合选

不建议在这些情况下选 `Copilot`：

- 你已经明确知道这个 quest 应该持续运行好几个小时
- 你希望 detached 实验、监控、后续路由自己接着往前推
- 你的目标是让系统接管完整推进，而不是一小段一小段地问答协作

## 4. Autonomous 模式

### 4.1 它是什么

Autonomous 模式就是标准版 DeepScientist 的工作方式。

适用于 quest 应该自己持续推进、普通路线选择默认由系统承担的情况。

典型场景包括：

- baseline 建立
- 长实验
- analysis campaign
- 持续写作 / finalize
- 通过 connector 长时间回传项目进展

### 4.2 创建之后会发生什么

创建 Autonomous 项目之后：

- quest 会被创建
- 第一轮会立即启动
- 系统开始把 startup contract 变成真实工作

这可能包括：

- 读 baseline 和参考资料
- 检查环境和约束
- 准备脚本
- 决定下一条路线
- 启动 detached `bash_exec` 长任务

### 4.3 continuation 行为

Autonomous 模式下，continuation 可以分成两个阶段来理解。

#### A. 还没有真实长任务

如果真实的外部长时间任务还没有跑起来，DeepScientist 不应该停住。

它应该继续用后续 turns 去：

- 准备真实任务
- 启动真实任务
- 或者把“下一个真实任务到底是什么”记录成耐久决策

这是“准备 / 启动阶段”。

#### B. 已经有真实长任务在跑

一旦真实 detached 长任务已经在跑，continuation 的节奏就应该变。

这时候不应该再用高频 LLM turn 去假装“持续执行”。

更合理的方式是：

- 真实工作继续留在 detached `bash_exec` 或它启动的运行时进程里
- agent turn 变成低频监控 / 汇总 / 决策
- 当前默认巡检节奏大约是每 `240` 秒一轮

这是“后台长任务巡检阶段”。

### 4.4 什么时候适合选

选择 `Autonomous`，通常意味着：

- quest 应该自己持续往前推
- 你预期会有真实长时间实验或分析工作
- 你希望 milestone 之后系统自动继续路由
- 你想用标准版 DeepScientist 的完整研究操作系统行为

### 4.5 什么时候不适合选

不建议在这些情况下选 `Autonomous`：

- 你只是想先建一个安静的项目壳
- 你想先人工检查仓库、再决定是否启动
- 你希望每个下一步都由你明确指令驱动

## 5. 最关键的实际区别

最容易记住的方式是：

- `Copilot` 问的是：“我现在该帮你完成哪一个具体单元？”
- `Autonomous` 问的是：“这个 quest 的下一个真实步骤是什么，我该怎样让它继续推进？”

真正重要的是这个差异，而不是名字本身。

## 6. Resume 是怎么工作的

两种模式都会保留持久上下文，但 resume 方式不同。

现在 auto-continue turn 里会带一个紧凑的 `resume spine`，里面可能包括：

- 最近一条持久化用户消息
- 最近一条 assistant checkpoint
- 最近一条 run 摘要
- 少量最近 memory cue
- 当前 `bash_exec` 状态

但 continuation policy 仍然不同：

- `Copilot`：你说话了，或者显式 `/resume` 了，才继续
- `Autonomous`：除非进入显式等待状态，否则默认继续推进

## 7. 快速选择方法

你可以用这个简单规则：

1. 如果你想让项目先安静待命，等你说第一句明确指令，再开始干活，选 `Copilot`。
2. 如果你想让 DeepScientist 一创建项目就开始把合同变成真实工作，选 `Autonomous`。
3. 如果你暂时拿不准，先用 `Copilot` 更稳；路线清楚后再进入更长时间的自治推进。

## 8. 常见误解

### “Autonomous 就意味着必须一直高速空转”

不是。

Autonomous 的意思是：quest 要继续推进。

如果还没有真实长任务，那推进可以表现为快速准备 / 启动。
如果真实长任务已经在跑，那推进就应该表现为低频巡检，而不是高频模型空转。

### “Copilot 就不能跑实验”

也不是。

Copilot 当然也能帮你启动实验、看运行状态、做分析、改写作。
区别在于：它不该在你没明确要求的时候，自己扩成长期自治流程。

### “这两个模式只是文案不同”

不是。

它们会影响：

- 创建后的默认行为
- continuation policy
- quest 什么时候停驻
- 多大程度上应该自己继续做路线推进

## 9. 相关文档

- [00 快速开始](./00_QUICK_START.md)
- [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)
- [12 引导式工作流教程](./12_GUIDED_WORKFLOW_TOUR.md)
- [14 Prompt、Skills 与 MCP 指南](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md)
