# 12 引导式工作流教程：从首页到真实工作区

这篇文档的目标，是让你在安装完成之后，真正理解 DeepScientist 的使用路径。

适合你在这些情况下阅读：

- 你已经成功启动过一次 DeepScientist
- 你已经能打开首页
- 你想知道每一步该点什么、该怎么填、每个界面到底是干什么的

如果你还没有完成启动，请先看 [00 快速开始](./00_QUICK_START.md)。

如果你想进一步理解 `Start Research` 弹窗背后的精确字段合同，再看 [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)。

## 1. 先分清两种使用方式

DeepScientist 常见有两种使用方式：

1. 真实项目模式
2. 引导教程模式

真实项目模式会创建一个真正的本地 quest 仓库，并开始真实工作。

引导教程模式会进入一个演示用的项目工作区，界面布局与真实项目一致，但内容是为学习而准备的。

如果你的目标是立即做真实任务，就用真实项目模式。

如果你的目标是先理解界面，再决定是否投入真实时间、算力和 connector 资源，就先用引导教程模式。

## 2. 从首页开始

首页不是一个普通聊天框，而是一个研究工作区的启动面。

最核心的两个入口是：

- `Start Research`
- `Open Project`

当你要开始一个全新的 quest 时，点击 `Start Research`。

当 quest 已经存在、你只是要继续推进时，点击 `Open Project`。

第一次使用时，优先点击 `Start Research`。

如果你只记一条最实用的规则：

- 已经知道要启动什么项目，就点 `Start Research`
- 还不知道做哪个 benchmark，就先去 `BenchStore`
- 只是想改配置，还不打算启动项目，就去 `Settings`

## 3. 先理解这个弹窗到底在做什么

`Start Research` 弹窗有两个同样重要的任务：

- 左侧定义项目合同
- 右侧展示真正会写入工作区的 kickoff prompt

所以不要把它当成“随便填两句就行”的表单。

你在这里实际上是在决定：

- quest 到底要解决什么问题
- 已经有哪些可用参考和 baseline
- 第一轮自动研究要推进到什么程度
- 是否需要把进展发到网页之外

如果右侧生成出来的 kickoff prompt 看起来不对，就不要急着创建项目，先回到左侧修正。

## 4. 按步骤填写 `Start Research`

### 4.1 Project title

这里填写一个给人看的项目标题。

推荐写法：

- 任务名称
- benchmark 或仓库名
- 研究方向

示例：

`Mandela-Effect Reproduction and Truth-Preserving Collaboration`

标题的作用，是让你以后在项目列表里快速认出它。

### 4.2 Project ID

大多数时候直接留空。

只有在这些场景下才建议手动填写：

- 教程演示
- 固定复现实验编号
- 团队内部有命名规范

否则让 runtime 自动分配下一个顺序 quest id 即可。

### 4.3 Primary research request

这是整个弹窗里最重要的字段。

这里要写清楚：

- 研究目标
- 成功标准
- 证据要求
- 最关键的限制条件或评测规则

不好的写法：

- 太泛的 brainstorming
- 只写实现细节，不写研究问题
- 没说清楚什么算验证成功

好的写法通常包含四层：

1. 要复现或研究什么
2. 研究问题是什么
3. 哪些协议和边界不能乱改
4. 可以往什么方向改进

### 4.4 Baseline links 和 Reference papers

这两栏的目的，是在第一轮开始前尽量减少歧义。

把仓库或绝对本地文件 / 文件夹路径放进 `Baseline links`，适合这些情况：

- baseline 必须来自某个特定官方仓库
- quest 需要先恢复指定实现

把论文、manuscript 路径或关键材料放进 `Paper / reference sources`，适合这些情况：

- 任务由某篇论文定义
- 评测协议来自某个明确来源
- 系统应该优先阅读某篇参考资料

如果你已经知道 baseline 和论文，不要把它们藏在主请求正文里，应该放进专门字段。

这两个参考字段不是只能填网络链接。
你也可以直接填写绝对本地文件路径，或者绝对本地文件夹路径。

### 4.5 Reusable baseline

只有当你已经把某个可信 baseline 导入了 registry，才需要选择它。

一旦这里选中：

- 第一轮会优先 attach 已存在 baseline
- 而不是从原始 URL 再重新恢复

如果你是第一次做这个任务，留空是完全正常的。

### 4.6 Connector delivery

这一栏是可选的。

建议在这些情况下保持 `Local only`：

- 第一次使用
- 想让流程最简单
- 不需要网页之外的提醒

只有在以下情况下才选择一个 connector：

- 你希望在浏览器外也收到进展或里程碑
- 该 connector 已经配置正确

当前 DeepScientist 对每个 quest 只绑定一个外部 connector 目标。

### 4.7 Research paper、Research intensity、Decision mode、Launch mode

这些项会真实改变第一轮研究的形状。

如果你暂时拿不准，推荐默认这样选：

- `Research paper`: `On`
- `Research intensity`: `Balanced`
- `Decision mode`: `Autonomous`
- `Launch mode`: `Standard`

原因很简单：

- `Balanced` 足够做真实工作，又不会让第一轮过重
- `Autonomous` 可以减少无谓阻塞
- `Standard` 让 quest 按普通研究主线启动
- `Research paper = On` 可以把分析与写作保持在范围内

如果你把 `Launch mode` 切到 `Custom`，要进一步明确自定义任务类型：

- `Continue existing state`
  - 适合已有资产很多、希望先复用再决策的任务
- `Review`
  - 适合已有较完整 draft / paper package，想先做一次独立 skeptical 审计
- `Rebuttal / revision`
  - 适合 reviewer comments 驱动，需要把评论映射成补实验、改文和 response letter 的任务
- `Other / freeform`
  - 适合其他不完全属于标准 custom 类型的任务

如果你选择的是 `Review`，还要继续决定：

- 审计后是直接停止，还是自动继续补实验和改稿
- 论文修改输出是普通可直接替换文本，还是 LaTeX-ready 文本

### 4.8 Runtime constraints

这一栏应该写“硬规则”，而不是写愿望。

适合写进去的内容：

- 必须使用哪个模型或推理端点
- 是否必须自动重试
- 是否必须保持与 baseline 对齐
- 是否必须如实记录失败
- 硬件或运行边界

不适合写进去的内容：

- 已经在主请求里说过的泛目标
- 冗长文献综述
- 本该写进 references 的信息

### 4.9 Goals

这一栏适合写更具体的阶段目标。

好的目标应当：

- 明确
- 可验证
- 方便后续复盘

推荐写法：

1. 恢复 baseline
2. 验证关键指标
3. 提出一个有依据的新方向
4. 产出足够支撑后续分析或写作的证据

### 4.10 一定要检查右侧 kickoff prompt

在点击 `Create project` 之前，一定读一遍右侧生成的 kickoff prompt。

重点检查：

- scope 是否错了
- baseline 信息是否丢了
- runtime constraints 是否遗漏
- connector 目标是否错误
- 语气和任务是否已经不一致

这是整个流程里成本最低、收益最高的纠错点。

如果你想记住一条最短真实项目路径，可以直接照这个顺序做：

1. `Start Research`
2. `Autonomous`
3. 填 `Project title`
4. 填 `Primary research request`
5. 检查右侧生成的 prompt
6. 点击 `Create project`

## 5. 点击 `Create project`

在真实项目模式下，这一步会创建真实的本地 quest，并打开真实工作区。

在引导教程模式下，这一步会进入一个演示用 quest，用来让你熟悉工作区界面。

最重要的心态切换是：

- 在点击前，它只是一个任务想法
- 在点击后，它已经变成一个有文件、图谱、memory 和执行历史的持久工作区

## 6. 用正确顺序认识工作区

推荐顺序是：

1. 顶栏
2. Explorer
3. 打开一个真实文件
4. Canvas
5. Details
6. Memory
7. Copilot / Studio

### 6.1 顶栏

顶栏是全局控制条。

你应该用它来判断：

- 当前在哪个 quest 里
- 当前是不是在预期分支上
- 如何返回、重播教程或做全局导航

### 6.2 Explorer

Explorer 是 quest 的文件视角。

它回答的是一个非常实际的问题：

`这个项目现在到底已经有哪些持久文件了？`

当你想确认 quest 是否真的产出了可复用内容时，就应该先看这里。

不要把图谱当作唯一真相来源。文件树本身就是非常重要的证据面。

### 6.3 ArXiv 和 Files 两个 tab

这两个 tab 分工不同：

- `ArXiv` 是文献书架
- `Files` 是工作树

正常使用中，你会在这两个视图之间反复切换。

一个用来读文献，一个用来打开计划、实验文件、笔记与产物。

### 6.4 打开一个真实文件

当你在 Explorer 里看到一个有价值的文件时，直接点开它。

这一步意味着你从“看结构”进入“看真实内容”。

常见文件类型包括：

- Markdown 笔记
- 计划
- 实验总结
- 结果报告
- 论文草稿

很多用户会把 quest 里的 Markdown 文件当作一个本地优先、类似 Notion 的私有笔记本，用来记录：

- 笔记
- 计划
- handoff
- 发现
- 协作信息

### 6.5 Canvas

Canvas 会把研究地图直接展示出来。

一个健康的 quest，不应该像一段无限滚动聊天记录。

Canvas 应该帮助你看到：

- baseline 工作
- 新想法
- 失败分支
- 成功路径
- 后续分析和写作

它最重要的价值，是展示 quest 是怎样长出来的，而不只是停在了哪里。

### 6.6 点击 Canvas 上的节点

不要只看形状。

点开一个节点，去看它到底代表什么。

一个有价值的节点应该把你带到：

- 分支摘要
- 关联文件
- stage 状态
- 持久证据

这样 Canvas 才不是装饰，而是真正可检查的研究地图。

### 6.7 Details

当你想最快回答下面这个问题时，就看 `Details`：

`这个 quest 现在到底是什么状态？`

特别适合这些场景：

- 你离开一段时间后回来
- quest 已经运行了一阵子
- 你想先看总结，再决定是否介入

### 6.8 Memory

Memory 是让 quest 能持续生长的关键。

你可以在这里理解：

- 哪些经验已经变成可复用知识
- 哪些弱路径以后不该再重复
- 哪些稳定事实已经从论文或实验中沉淀下来

没有 memory，每一轮都容易变成一次性消耗品。

### 6.9 Copilot / Studio

如果你希望持续贴着 quest 的执行过程，就把这个面板一直开着。

它适合做这些事情：

- 看执行过程
- 中途介入
- 请求状态总结
- 改路线
- 过一段时间再回来继续

这里是 quest 从“自动运行”变成“可协作工作坊”的地方。

## 7. 一个实用的一轮操作节奏

当 quest 已经开始运行后，最有用的节奏通常是：

1. 先让第一轮动起来
2. 不要只盯着聊天，去打开 workspace
3. 看 1 到 2 个关键文件
4. 用 Canvas 看分支结构
5. 用 Details 看当前状态
6. 再决定是否介入

这样可以避免两个常见错误：

- 介入太早
- 还没看证据就过度相信总结

## 8. 常见误区

### 8.1 把 `Start Research` 当成随便聊天

它不是聊天框，而是项目合同。

### 8.2 目标写得太空

如果目标里没有验证要求，第一轮通常会更弱。

### 8.3 重要参考都塞在一段正文里

baseline 和 references 应该写在专门字段里。

### 8.4 不看右侧 kickoff prompt

这是整个流程里最便宜的纠错位置。

### 8.5 把 Canvas 当成漂亮图片

真正有价值的用法，是点节点、看文件、查证据。

### 8.6 只盯着工作区实时输出，不看文件

文件树本身就是系统的主要真相面之一。

## 9. 下一步建议阅读

- [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)
- [06 Runtime 与 Canvas](./06_RUNTIME_AND_CANVAS.md)
- [07 Memory 与 MCP](./07_MEMORY_AND_MCP.md)
- [13 核心架构说明](./13_CORE_ARCHITECTURE_GUIDE.md)
