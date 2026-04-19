# 02 Start Research 参考：如何填写科研启动合同

这份文档说明当前 `Start Research` 弹窗的真实结构，以及它到底会向后端提交什么。

实现来源：

- `src/ui/src/lib/startResearch.ts`
- `src/ui/src/components/projects/CreateProjectDialog.tsx`

## 这个弹窗实际做什么

`Start Research` 不只是“新建项目表单”，它同时完成四件事：

1. 收集结构化启动上下文
2. 把这些上下文编译成项目的第一条 kickoff prompt
3. 绑定一个可选的可复用 baseline
4. 持久化 `startup_contract`，供后续 prompt builder 持续读取

## 实战示例：整理后的 quest 025 启动输入

理解这个弹窗最快的方法，不是先背字段定义，而是先看一个真实例子。

下面这个例子来自 quest `025` 的真实启动输入，但我做了必要的整理，让它更适合公开文档和第一次填写时参考。这个任务的目标是：

- 复现官方的 Mandela-Effect baseline
- 保持原论文任务与评测协议
- 研究在混合正确 / 错误社会信号下，如何实现更强的 truth-preserving collaboration
- 使用两个本地 OpenAI-compatible 端点提高吞吐量

### 当前前端里先填的短字段

| 弹窗字段 | 示例值 | 为什么这样填 |
|---|---|---|
| `Project title` | `Mandela-Effect Reproduction and Truth-Preserving Collaboration` | 标题清楚，后面在卡片、工作区和搜索里都好认 |
| `Project ID` | 留空，或者填 `025` | 想自动编号就留空；只有你明确要固定编号时才手动填写 |
| `Connector delivery` | 第一次建议 `Local only`，如果 QQ 已配置也可以选一个目标 | 当前前端对每个 quest 最多只允许绑定一个外部 connector 目标 |
| `Reusable baseline` | 第一次可留空；如果官方 baseline 已经导入 registry，就直接选它 | 一旦选中，自动推导的 `baseline_mode` 会变成 `existing` |
| `Research paper` | `On` | 让项目保持分析和论文式产出在范围内 |
| `Research intensity` | `Balanced` | 先把 baseline 立稳，再探索一个合理方向 |
| `Decision mode` | `Autonomous` | 普通路线选择默认自己推进，不把常规决策丢回给用户 |
| `Launch mode` | `Standard` | 按默认科研主线启动 |
| `Language` | `English` | 默认用英文组织 kickoff prompt 和用户侧产物 |

### 同一个例子里的长文本字段

`Primary research request`

```text
Please reproduce the official Mandela-Effect repository and paper, then study how to improve truth-preserving collaboration under mixed correct and incorrect social signals.

The core research question is: how can a multi-agent system remain factually robust under social influence while still learning from correct peers?

Keep the task definition and evaluation protocol aligned with the original work. Focus on prompt-based or system-level methods that improve truth preservation without simply refusing all social information.
```

`Baseline links`

```text
https://github.com/bluedream02/Mandela-Effect
```

`Reference papers / repos`

```text
https://arxiv.org/abs/2602.00428
```

`Runtime constraints`

下面这段只是教程参考，不是 DeepScientist 的默认端点配置。粘贴前请把端点、API key 和模型名替换成你自己的真实运行时。

```text
- Keep the task definition and evaluation protocol aligned with the official baseline unless a change is explicitly justified.
- Use two OpenAI-compatible inference endpoints for throughput:
  - `http://127.0.0.1:<port-a>/v1`
  - `http://127.0.0.1:<port-b>/v1`
- Use your actual API key `<YOUR_API_KEY>` and model `<YOUR_MODEL>` on both endpoints.
- Keep generation settings close to the baseline unless a justified adjustment is required.
- Implement asynchronous execution, automatic retry on request failure, and resumable scripts.
- Split requests across both endpoints so throughput stays high without overloading the service.
- Record failed, degraded, or inconclusive runs honestly instead of hiding them.
```

`Goals`

```text
1. Restore and verify the official Mandela-Effect baseline as a trustworthy starting point.
2. Measure key metrics and failure modes on the designated `gpt-oss-120b` setup.
3. Propose at least one literature-grounded direction for stronger truth-preserving collaboration.
4. Produce experiment and analysis artifacts that are strong enough to support paper writing.
```

### 这个例子在前端里会自动推导出什么

如果 `Reusable baseline` 留空，且 `Research intensity` 选择 `Balanced`，当前前端会自动推导：

- `scope = baseline_plus_direction`
- `baseline_mode = auto`
- `resource_policy = balanced`
- `time_budget_hours = 24`
- `git_strategy = semantic_head_plus_controlled_integration`

如果你已经选中了一个可复用 baseline，那么只会有一项不同：

- `baseline_mode = existing`

## 当前前端数据模型

### `StartResearchTemplate`

```ts
type StartResearchTemplate = {
  title: string
  quest_id: string
  goal: string
  baseline_id: string
  baseline_variant_id: string
  baseline_urls: string
  paper_urls: string
  review_materials: string
  runtime_constraints: string
  objectives: string
  need_research_paper: boolean
  research_intensity: 'light' | 'balanced' | 'sprint'
  decision_policy: 'autonomous' | 'user_gated'
  launch_mode: 'standard' | 'custom'
  custom_profile: 'continue_existing_state' | 'review_audit' | 'revision_rebuttal' | 'freeform'
  review_followup_policy: 'audit_only' | 'auto_execute_followups' | 'user_gated_followups'
  baseline_execution_policy:
    | 'auto'
    | 'must_reproduce_or_verify'
    | 'reuse_existing_only'
    | 'skip_unless_blocking'
  manuscript_edit_mode: 'none' | 'copy_ready_text' | 'latex_required'
  entry_state_summary: string
  review_summary: string
  custom_brief: string
  user_language: 'en' | 'zh'
}
```

关键变化：

- `scope`
- `baseline_mode`
- `resource_policy`
- `time_budget_hours`
- `git_strategy`

这几项已经不再由用户逐个填写，而是由 `research_intensity` 和是否选中 `baseline_id` 自动推导。

现在还新增了 3 个显式启动控制项：

- `baseline_source_mode`
- `execution_start_mode`
- `baseline_acceptance_target`

它们不是替代自动推导字段，而是更强的用户侧路线偏好，用来告诉 agent：

- baseline 应优先验证本地已有系统、附着可复用 baseline、从源码复现、修复已有 baseline，还是先别把 baseline 当前置主线
- 是否应先输出一个有边界的计划并等待批准，再进入重型执行
- baseline 至少要达到什么强度，quest 才应该进入 idea 与 experiment

### 自动推导字段

```ts
type StartResearchContractFields = {
  scope: 'baseline_only' | 'baseline_plus_direction' | 'full_research'
  baseline_mode:
    | 'existing'
    | 'restore_from_url'
    | 'allow_degraded_minimal_reproduction'
    | 'stop_if_insufficient'
  resource_policy: 'conservative' | 'balanced' | 'aggressive'
  time_budget_hours: string
  git_strategy:
    | 'branch_per_analysis_then_paper'
    | 'semantic_head_plus_controlled_integration'
    | 'manual_integration_only'
}
```

推导逻辑在 `resolveStartResearchContractFields(...)`。

## 后端提交结构

前端最终会提交：

```ts
{
  title,
  goal: compiled_prompt,
  quest_id,
  requested_connector_bindings: [
    {
      connector,
      conversation_id
    }
  ],
  requested_baseline_ref: {
    baseline_id,
    variant_id
  } | null,
  startup_contract: {
    schema_version: 3,
    user_language,
    need_research_paper,
    research_intensity,
    decision_policy,
    launch_mode,
    custom_profile,
    review_followup_policy,
    baseline_execution_policy,
    manuscript_edit_mode,
    scope,
    baseline_mode,
    resource_policy,
    time_budget_hours,
    git_strategy,
    runtime_constraints,
    objectives: string[],
    baseline_urls: string[],
    paper_urls: string[],
    review_materials: string[],
    entry_state_summary,
    review_summary,
    custom_brief,
  }
}
```

## 字段说明

### 项目基本身份

**`title`**

- 项目的人类可读标题。
- 用于卡片和工作区标题。
- 不要求与 `quest_id` 一致。

**`quest_id`**

- 项目的稳定标识，保存在 `quest_id` 中，同时也是目录名。
- 默认由 runtime 提供下一个顺序编号。
- 允许用户手动覆盖。

**`goal`**

- 核心研究请求。
- 会成为 kickoff prompt 的主体。
- 好的写法：科学问题、目标、成功标准、研究边界。
- 不好的写法：直接写一堆过细的实现步骤。

**`user_language`**

- 声明后续 kickoff 和交流默认偏好的语言。

### Connector 投递

**`requested_connector_bindings`**

- 这是创建项目时随请求一起提交的字段，但不在 `startup_contract` 里面。
- 当前前端对每个 quest 最多只允许一个外部 connector 目标。
- 典型结构如下：

```ts
[
  {
    connector: 'qq',
    conversation_id: 'qq:private:openid-123'
  }
]
```

- 如果你保持项目仅本地运行，这个数组就是空的。
- 如果你选中的那个目标已经绑定在别的 quest 上，当前项目创建时会把旧绑定替换掉。

### Baseline 与参考资料

**`baseline_id`**

- 从 registry 中选择一个可复用 baseline。
- 一旦存在，推导出的 `baseline_mode` 会变成 `existing`。
- 运行时应优先 attach 并 verify 它，而不是从零开始。

**`baseline_variant_id`**

- baseline 条目中某个具体 variant 的选择器。

**`baseline_urls`**

- 当没有 registry baseline 时，作为恢复 baseline 的候选来源。
- 可以填写网络链接，也可以直接填写绝对本地文件 / 文件夹路径。
- 提交时转成 `string[]`。

**`paper_urls`**

- 论文、代码仓库、benchmark、leaderboard、manuscript 路径等参考资料。
- 可以填写网络链接，也可以直接填写绝对本地文件 / 文件夹路径。
- 提交时转成 `string[]`。

**`review_materials`**

- 主要用于 `review_audit` 或 `revision_rebuttal`。
- 每行填写一个 URL，或一个绝对本地文件 / 文件夹路径，用于 reviewer comments、decision letter、meta-review 或 revision packet。
- 提交时转成 `string[]`。

### 约束与目标

**`runtime_constraints`**

- 硬约束，例如预算、硬件、隐私、存储、截止时间等。

**`objectives`**

- 每行一个目标。
- 提交时转成 `string[]`。
- 应该写“下一轮需要产出什么”，而不是写空泛口号。

**`need_research_paper`**

- `true`：默认继续推进到分析和写作准备
- `false`：默认追求最强且有依据的算法结果，不自动进入论文写作

### 高层控制项

**`research_intensity`**

- `light`
  - 推导结果：仅 baseline、保守、8 小时、手动集成
- `balanced`
  - 推导结果：baseline + 方向、平衡、24 小时、受控集成
- `sprint`
  - 推导结果：完整研究、激进、48 小时、analysis 分支优先

这是当前公开给用户的主要“轮次深度”控制杆。

**`decision_policy`**

- `autonomous`
  - 普通路线由 agent 自行决定
  - 一轮结束后默认继续：如果真实长时间外部任务还没跑起来，就继续准备或启动；一旦真实长任务已经在跑，后台监控应切成低频，而不是亚分钟轮询
- `user_gated`
  - 只有真正依赖用户偏好时，才允许阻塞式决策请求

关于 workspace mode 的实际含义：

- DeepScientist 还会区分用户导向的 `copilot` 模式和默认的 `autonomous` 模式。
- 在 `copilot` 下，当前请求单元完成后通常应该停驻，等待下一条用户消息或 `/resume`。
- 在 `autonomous` 下，不能因为“当前还没有长任务在跑”就停住；系统应继续推进，直到下一个真实长任务被准备好或启动起来。

### 启动模式

**`launch_mode`**

- `standard`
  - 按默认科研主线启动
- `custom`
  - 不假设这是一个“从零开始”的普通科研任务

**`custom_profile`**

仅在 `launch_mode = custom` 时有效。

- `continue_existing_state`
  - 先审计已有 baseline、结果、草稿或混合资产
  - prompt builder 会显式引导 agent 优先打开 `intake-audit`
- `review_audit`
  - 这是一个对现有 draft / paper package 做独立 skeptical 审计的任务
  - prompt builder 会显式引导 agent 优先打开 `review`
- `revision_rebuttal`
  - 这是一个审稿回复、revision、rebuttal 类型任务
  - prompt builder 会显式引导 agent 优先打开 `rebuttal`
- `freeform`
  - 这是“其它”入口
  - 以自定义 brief 为主，尽量少做额外假设

**`baseline_execution_policy`**

- 仅在 `launch_mode = custom` 时有意义。
- `auto`
  - 让启动合同和当前证据自己决定
- `must_reproduce_or_verify`
  - 在 reviewer-linked 的后续工作之前，先验证或恢复 rebuttal 关键依赖的 baseline / comparator
- `reuse_existing_only`
  - 默认信任当前 baseline / 结果，除非它们明显不一致或不可用
- `skip_unless_blocking`
  - 默认跳过 baseline 重跑，只有当某个 review / rebuttal 条目明确依赖缺失 comparator 时才补跑

**`review_followup_policy`**

- 主要用于 `review_audit`。
- `audit_only`
  - 只完成审计产物和路由建议
- `auto_execute_followups`
  - 审计后自动继续进入合理的实验和论文修改
- `user_gated_followups`
  - 先完成审计，再在昂贵后续动作前等待你的批准

**`manuscript_edit_mode`**

- 主要用于 `review_audit` 和 `revision_rebuttal`。
- `none`
  - 只输出规划产物
- `copy_ready_text`
  - 输出 section-level 的可直接粘贴修改文本
- `latex_required`
  - 优先把提供的 LaTeX 树当作写作表面，并输出 LaTeX-ready 的替换文本
  - 如果选择这个模式，最好同时通过本地路径 / 文件夹输入提供 LaTeX 源目录

**`entry_state_summary`**

- 用自然语言概括当前已经存在什么。
- 典型内容：
  - 已有可信 baseline
  - 主实验已经跑完
  - 部分论文草稿已经存在
  - 部分补充图表已经存在

**`review_summary`**

- 主要用于 review / revision 场景。
- 用来概括 reviewer comments、修改要求、meta-review 约束。

**`custom_brief`**

- 一个额外的启动级说明。
- 用来覆盖或收窄默认的 blank-slate full-research 行为。

## 自动推导合同映射

当前 preset 映射如下：

| `research_intensity` | `scope` | `baseline_mode` | `resource_policy` | `time_budget_hours` | `git_strategy` |
|---|---|---|---|---:|---|
| `light` | `baseline_only` | `stop_if_insufficient` | `conservative` | `8` | `manual_integration_only` |
| `balanced` | `baseline_plus_direction` | `restore_from_url` | `balanced` | `24` | `semantic_head_plus_controlled_integration` |
| `sprint` | `full_research` | `allow_degraded_minimal_reproduction` | `aggressive` | `48` | `branch_per_analysis_then_paper` |

额外规则：

- 如果选中了 `baseline_id`，推导得到的 `baseline_mode` 会强制变成 `existing`
- 如果显式设置了 `baseline_source_mode`，应把它当作更强的路线偏好，而把 `baseline_mode` 视为较粗粒度的推导摘要

## Prompt 编译行为

`compileStartResearchPrompt(...)` 会生成一段可读 kickoff prompt，包含：

- 项目启动上下文
- 核心研究请求
- 研究目标
- baseline 上下文
- 参考论文 / 仓库
- 运行约束
- 研究交付模式
- 决策处理模式
- 启动模式
- 研究合同
- 必须遵守的工作规则

其中自定义启动会被明确写出来：

- `standard`
  - 告诉 agent 使用默认科研图谱
- `custom + continue_existing_state`
  - 告诉 agent 先整理和信任排序已有资产
  - 明确优先 `intake-audit`
- `custom + review_audit`
  - 告诉 agent 当前 draft / paper 状态就是主动合同
  - 明确优先 `review`
- `custom + revision_rebuttal`
  - 告诉 agent 先理解 reviewer comments 和当前论文状态
  - 明确优先 `rebuttal`
- `custom + freeform`
  - 告诉 agent 以 custom brief 为主，只打开真正需要的 skills

## 示例 payload

### 标准启动

```json
{
  "title": "Sparse adapter robustness",
  "goal": "Investigate whether sparse routing improves robustness without hurting compute efficiency.",
  "quest_id": "012",
  "requested_baseline_ref": {
    "baseline_id": "adapter-baseline",
    "variant_id": "default"
  },
  "startup_contract": {
    "schema_version": 3,
    "user_language": "en",
    "need_research_paper": true,
    "research_intensity": "balanced",
    "decision_policy": "autonomous",
    "launch_mode": "standard",
    "custom_profile": "freeform",
    "scope": "baseline_plus_direction",
    "baseline_mode": "existing",
    "resource_policy": "balanced",
    "time_budget_hours": 24,
    "git_strategy": "semantic_head_plus_controlled_integration",
    "runtime_constraints": "One 24 GB GPU. Keep data local.",
    "objectives": [
      "verify the reusable baseline",
      "test one justified sparse-routing direction"
    ],
    "baseline_urls": [],
    "paper_urls": [
      "https://arxiv.org/abs/2401.00001"
    ],
    "entry_state_summary": "",
    "review_summary": "",
    "custom_brief": ""
  }
}
```

### 自定义启动：继续已有状态

```json
{
  "title": "Continue retrieval project",
  "goal": "Continue the existing retrieval project and decide whether a fresh main run is still needed.",
  "quest_id": "013",
  "requested_baseline_ref": null,
  "startup_contract": {
    "schema_version": 3,
    "user_language": "en",
    "need_research_paper": true,
    "research_intensity": "light",
    "decision_policy": "autonomous",
    "launch_mode": "custom",
    "custom_profile": "continue_existing_state",
    "scope": "baseline_only",
    "baseline_mode": "stop_if_insufficient",
    "resource_policy": "conservative",
    "time_budget_hours": 8,
    "git_strategy": "manual_integration_only",
    "runtime_constraints": "Do not rerun expensive full-corpus indexing unless evidence says the old run is unusable.",
    "objectives": [
      "normalize current evidence",
      "decide whether a new run is actually required"
    ],
    "baseline_urls": [],
    "paper_urls": [],
    "entry_state_summary": "Trusted baseline exists. One main run finished. Draft intro and method already exist.",
    "review_summary": "",
    "custom_brief": "Audit first. Only rerun if current metrics or artifacts are inconsistent."
  }
}
```

### 自定义启动：审稿 / rebuttal

```json
{
  "title": "Camera-ready revision",
  "goal": "Address reviewer requests, add only the missing evidence, and revise the manuscript cleanly.",
  "quest_id": "014",
  "requested_baseline_ref": null,
  "startup_contract": {
    "schema_version": 3,
    "user_language": "en",
    "need_research_paper": true,
    "research_intensity": "balanced",
    "decision_policy": "user_gated",
    "launch_mode": "custom",
    "custom_profile": "revision_rebuttal",
    "review_followup_policy": "audit_only",
    "baseline_execution_policy": "skip_unless_blocking",
    "manuscript_edit_mode": "latex_required",
    "scope": "baseline_plus_direction",
    "baseline_mode": "restore_from_url",
    "resource_policy": "balanced",
    "time_budget_hours": 24,
    "git_strategy": "semantic_head_plus_controlled_integration",
    "runtime_constraints": "Only add experiments that directly answer reviewer concerns.",
    "objectives": [
      "map reviewer comments to concrete actions",
      "run only the necessary supplementary evidence",
      "update the draft and response letter"
    ],
    "baseline_urls": [],
    "paper_urls": [],
    "review_materials": [
      "/absolute/path/to/review-comments.md"
    ],
    "entry_state_summary": "A draft and previous experiment outputs already exist.",
    "review_summary": "Reviewers asked for one stronger ablation, one extra baseline, and a clearer limitation paragraph.",
    "custom_brief": "Treat the current manuscript and review packet as the active contract."
  }
}
```

## 运行时意义

- `startup_contract` 是项目的持久状态，不只是 UI 临时字段。
- 后续 prompt builder 还会继续读取 `launch_mode`、`custom_profile`、`review_followup_policy`、`baseline_execution_policy`、`manuscript_edit_mode`、`entry_state_summary`、`review_summary`、`review_materials`、`custom_brief`。
- 所以 `Start Research` 不只影响第一轮，还会影响后续路由判断。

## 修改检查清单

如果修改 `Start Research`，要同步检查：

- `src/ui/src/lib/startResearch.ts`
- `src/ui/src/components/projects/CreateProjectDialog.tsx`
- `src/prompts/system.md`（如果运行时解释变了）
- `src/deepscientist/prompts/builder.py`（如果 prompt 路由变了）
- 本文档
- `docs/en/02_START_RESEARCH_GUIDE.md`
- `tests/test_prompt_builder.py`
- `tests/test_stage_skills.py`
