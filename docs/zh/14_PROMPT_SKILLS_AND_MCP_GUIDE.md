# 14 Prompt、Skills 与 MCP 指南

这篇文档解释的是：DeepScientist 每一轮到底是怎么被驱动起来的。

适合这些场景：

- 你想理解每轮 prompt 是怎么拼出来的
- 你想知道每个 skill 到底负责什么
- 你想弄清楚内建 MCP 工具的结构
- 你发现系统行为不对，想知道该改 prompt、skill 还是工具代码

如果你只想先看面向用户的系统概览，请先看 [13 核心架构说明](./13_CORE_ARCHITECTURE_GUIDE.md)。

如果你只想进一步看 `memory/artifact/bash_exec` 的使用纪律，请接着看 [07 Memory 与 MCP](./07_MEMORY_AND_MCP.md)。

## 1. 一句话总结

DeepScientist 不是靠一份静态大 prompt 工作的。

每一轮 turn，系统都会重新根据下面这些内容组装 prompt：

- 核心 system prompt
- 共享交互合同
- 当前运行时状态
- quest 持久文件
- startup contract
- 当前优先 memory
- 必要时的 connector 专属规则
- 当前 skill 结构

然后 agent 只通过三个内建 MCP namespace 工作：

- `memory`
- `artifact`
- `bash_exec`

## 2. 哪些文件是 prompt 的主要真相来源

最关键的文件包括：

- `src/prompts/system.md`
- `src/prompts/contracts/shared_interaction.md`
- `src/prompts/connectors/qq.md`
- `src/prompts/connectors/weixin.md`
- `src/prompts/connectors/lingzhu.md`
- `src/deepscientist/prompts/builder.py`
- `src/skills/*/SKILL.md`
- `src/deepscientist/mcp/server.py`

它们各自的作用大致是：

- `system.md`：全局行为准则
- `shared_interaction.md`：统一交互连续性规则
- `connectors/*.md`：只在对应 connector 生效时才注入的专属规则
- `builder.py`：决定 prompt 组装顺序与运行时上下文
- `SKILL.md`：定义各个阶段的执行纪律
- `mcp/server.py`：定义内建工具面

受管 quest-local prompt 镜像：

- DeepScientist 仍然会优先读取 `quest_root/.codex/prompts/` 下存在的 prompt 片段。
- 但这棵树现在是“自动维护的受管副本”，不再默认视为永久手工 fork。
- 每次真实 runner turn 开始前，DeepScientist 都会把当前 active quest-local prompt 树与仓库 `src/prompts/` 做比较；只要仓库源变了，或者 quest 本地副本漂移了，就会刷新 active 副本。
- 刷新之前，旧的 active prompt 树会先备份到 `quest_root/.codex/prompt_versions/<backup_id>/`。
- 所以默认情况下，旧 quest 也会吃到最新 prompt 合同；如果你需要回放历史 prompt，再显式选择某个备份版本。

## 3. 一轮 prompt 是怎么组装的

当前运行时大致按下面顺序组装 turn prompt：

1. `system.md`
2. `contracts/shared_interaction.md`
3. runtime context
4. active communication surface
5. 可选的 connector contract
6. turn driver 与 continuation guard
7. active user requirements
8. quest context
9. recent durable state
10. research delivery policy
11. paper and evidence snapshot
12. 如果是 retry turn，则加入 retry recovery packet
13. 如果是 auto-continue turn，则加入 resume context spine
14. interaction style
15. priority memory for this turn
16. recent conversation window
17. current turn attachments
18. current user message

这个顺序不是随便排的。

系统本质上想先回答三个问题：

1. 这个 quest 这一轮现在到底要做什么
2. 已经有哪些持久状态不能被忽略
3. 这一轮在当前 surface 和当前 stage 下应该遵守什么规则

## 4. 各个主要 prompt block 到底在做什么

### 4.1 `system.md`

这是全局 DeepScientist 行为合同。

它会定义：

- 长周期、证据优先的工作方式
- shell 类执行必须走 `bash_exec`
- 文件、日志、artifact 才是历史真相
- 不要过早结束 quest
- Web、TUI、connector 属于同一个 quest
- 用户可见的汇报风格
- baseline 提交与确认的纪律：如果源 baseline 暴露了多指标或多 variant，就要保留完整比较面，而不是只留下一个 headline scalar

如果你发现 agent 在所有场景里行为都不对，`system.md` 一定是首要检查点之一。

### 4.2 `shared_interaction.md`

这个文件统一规定 `artifact.interact(...)` 相关的连续性交互规则。

它告诉 agent：

- `artifact.interact(...)` 是主要的长对话脊柱
- 排队中的用户消息必须优先确认和处理
- `blocking` 只该用于真实用户决策
- 进展汇报应该简洁且可读
- 真正发给用户的交互消息应保持完整；系统会单独生成短预览，所以 agent 不应该自己把 connector 回复截成 `...` / `…`

如果模型经常在长任务里“断线”或者不会接住用户后续消息，这个文件非常关键。

### 4.3 Active communication surface

prompt builder 每轮都会加一个当前 surface 的说明块。

它会告诉模型：

- 当前这轮是本地、QQ、微信还是其他 connector
- 当前 quest 绑定了几个外部 connector
- 此时真正活跃的是哪个 surface
- 这个 surface 上应该说多少细节

这也是为什么 connector 行为不应该被硬编码进全局 prompt。

同一个 quest 可以同时被 Web、TUI 和 connector 看到，但回复形态应该随 surface 变化。

### 4.4 Connector contract

connector 专属 prompt 片段只在需要时才会被加载。

当前对应文件有：

- `src/prompts/connectors/qq.md`
- `src/prompts/connectors/weixin.md`
- `src/prompts/connectors/lingzhu.md`

这些文件主要控制：

- 回复长度
- 文本优先还是支持媒体
- 附件该如何发
- 哪些内部细节不该在聊天面里暴露

例如：

- QQ 被当作里程碑式 operator surface
- Weixin 被当作简洁的手机侧 operator surface，并依赖 `context_token` 连续性
- Lingzhu 被当作更短、更受限的 surface

如果只有某个 connector 的行为需要调整，优先改它自己的 connector prompt，而不是把逻辑塞进全局 system prompt。

### 4.5 Runtime context 与 durable quest state

builder 会注入很多运行时事实，例如：

- `quest_id`
- `quest_root`
- 当前工作分支
- 当前 active idea id
- 当前 active analysis campaign id
- bound conversations
- startup contract
- baseline gate
- active interactions
- recent artifacts
- recent runs

这正是 prompt 变成 quest-aware 的原因，而不是普通通用对话。

### 4.6 Quest context

builder 会直接把这些 quest 文件读进 prompt：

- `brief.md`
- `plan.md`
- `status.md`
- `SUMMARY.md`

这一点很重要：

- 当前 live prompt 并不只依赖聊天记录
- 持久 quest 文档本身就是一等真相面

### 4.7 Research delivery policy

这个 block 会把启动时的选择，转成具体执行规则。

它主要包括：

- 是否要求 paper delivery
- launch mode
- custom profile
- baseline 路由规则
- idea 路由规则
- paper branch 行为
- review gate 行为

如果你感觉 `Start Research` 后行为不对，通常要检查：

- `startup_contract`
- `src/deepscientist/prompts/builder.py`
- 当前 quest 所处的 stage skill

它现在还明确承载了 continuation 的模式分叉：

- `workspace_mode = copilot`
  - 以当前请求为单位提供帮助
  - 做完这一小段之后，通常停驻，等待下一条用户消息或 `/resume`
- `workspace_mode = autonomous`
  - 默认继续往前推进
  - 如果真实长任务还没跑起来，就继续用接下来的 turns 做准备、启动或耐久决策
  - 一旦真实长任务已经在跑，后台 auto-continue 就切成低频巡检

### 4.8 Interaction style

这个 block 决定这轮该怎么“说话”。

它会控制：

- 语言偏置
- blocking 还是 threaded
- 长时间运行时的汇报节奏
- mailbox 消息要怎么确认
- 如何把进展压缩成人类可读的更新

所以 DeepScientist 虽然是同一套 runtime，但在这些场景里可以表现不同：

- 长实验
- connector 回复
- 写作阶段
- 等待用户决策的阶段

它现在也编码了 auto-continue 的节奏分叉：

- autonomous 下，如果还在准备 / 启动真实长任务，可以较快地连续推进
- 如果真实外部长任务已经在跑，则默认切成低频检查，默认大约每 `240` 秒一轮
- copilot 模式则通常在当前请求单元完成后停驻，不继续自动扩展

### 4.9 Resume context spine

现在在 auto-continue turn 中，prompt 会额外注入一个紧凑的 resume spine，避免模型只凭一个 stage 名称硬续。

里面包括：

- 最近一条持久化用户消息
- 最近一条 assistant checkpoint
- 最近一条 run result 摘要
- 少量最近 memory cues
- 当前 `bash_exec` 状态，包括是否有长时间 shell 会话正在运行

这也是为什么 auto-continue 能更贴着“最新用户意图 + 最新检查点”继续，而不是漂回泛泛的 stage narration。

### 4.10 Priority memory

DeepScientist 不是随机往 prompt 里塞 memory 的。

`PromptBuilder` 会根据 stage 使用不同的 memory plan。

例如：

- `scout` 更偏向 `papers`、`knowledge`、`decisions`
- `baseline` 更偏向 `papers`、`decisions`、`episodes`、`knowledge`
- `idea` 更偏向 `papers`、`ideas`、`decisions`、`knowledge`
- `experiment` 更偏向 `ideas`、`decisions`、`episodes`、`knowledge`

也就是说，prompt 会有明确的 stage bias。

agent 不应该在每一轮都看到完全同一批 memory。

## 5. 本地 active prompt 与历史版本

当前 quest 的 active prompt 树仍在这些路径下：

- `.codex/prompts/system.md`
- `.codex/prompts/contracts/shared_interaction.md`
- `.codex/prompts/connectors/<connector>.md`

仓库默认 prompt 仍然在 `src/prompts/`。

但现在有一个关键变化：

- `.codex/prompts/` 不应再理解为长期手工维护的 override 树。
- 每次真实运行前，DeepScientist 都会把 active quest-local copy 修回当前仓库 prompt 真相。
- 所以如果你手工改了 active copy，这种改动会在下次运行时被视为漂移：先备份，再替换。
- 历史 prompt 会保存在 `.codex/prompt_versions/<backup_id>/`。

如果你确实想让某个 quest 临时按旧 prompt 跑，启动时优先传正式版本号即可：

- `ds daemon --prompt-version <official_version>`
- `ds run --prompt-version <official_version> ...`

DeepScientist 会把它解析成“该正式版本号下最新的一份 prompt 备份”。如果你想精确回放某一次具体备份，而不是该版本下最新的一份，也仍然可以直接传备份目录名。

如果只是想继续使用当前受管 active prompt，就用 `latest`。

如果这个改动应该影响正常未来行为，就不该只改 quest-local active copy，而应该直接改仓库默认 prompt。

## 6. Skills 是怎么分层的

DeepScientist 当前有两层 skill：

1. 标准 stage skills
2. companion skills

### 6.1 标准 stage skills

这些是主研究锚点：

| Skill | 什么时候用 | 主要职责 | 通常交给谁 |
|---|---|---|---|
| `scout` | 任务框架还不清楚 | 定义问题、找 baseline、确认数据集和 metric 合同 | `baseline` 或 `idea` |
| `baseline` | 还没有可信 baseline | attach、import、复现、修复和验证 baseline | `idea` |
| `idea` | baseline 清楚，但下一条研究路线不清楚 | 生成、比较并选择可持久化的新方向 | `experiment` |
| `experiment` | 已经有选中的 idea | 在单条 durable 线路上实现并跑主实验 | `analysis-campaign`、`write` 或 `decision` |
| `analysis-campaign` | 需要补充实验 | 跑 slice、ablation、robustness 或 reviewer-facing supplement | `write`、`decision` 或 `finalize` |
| `write` | 证据已经足够写作 | 把证据转成 outline、draft 和 paper bundle | `review` 或 `finalize` |
| `finalize` | quest 接近收尾 | 汇总 claims、总结状态并做关闭前检查 | quest completion approval |
| `decision` | 需要做 durable route choice | 基于证据做 go/stop/branch/reuse 决策 | 交给下一个 anchor |

### 6.2 Companion skills

这些是辅助入口或质量控制技能：

| Skill | 什么时候用 | 主要职责 |
|---|---|---|
| `figure-polish` | 某张图已经不只是 debug 图 | 对 milestone 或 paper figure 做 render-inspect-revise |
| `intake-audit` | quest 里已经有不少历史状态 | 给旧资产做 trust-rank，并决定下一个 anchor |
| `review` | 已经有比较完整的 draft | 在宣布完成前做一次 skeptical audit |
| `rebuttal` | 已经有 reviewer comments 或 revision request | 把 reviewer pressure 映射成实验、文字修改和 response artifact |

### 6.3 最关键的设计点

DeepScientist 的 daemon 不应该变成一个巨大的硬编码科研调度器。

真正的分工是：

- prompt 定义总合同
- skill 定义当前阶段纪律
- runtime 负责持久化状态与路由 turn

这就是 DeepScientist 最核心的设计选择之一。

## 7. 每个 skill 通常会留下什么 durable 输出

你可以期待的大致持久化产物如下：

| Skill | 常见 durable outputs |
|---|---|
| `scout` | 更新后的 `brief.md`、更新后的 `plan.md`、文献笔记、framing memory |
| `baseline` | `PLAN.md`、`CHECKLIST.md`、baseline 验证记录、confirmed 或 waived baseline 状态 |
| `idea` | durable idea draft、选中路线包、为什么这条路线胜出的理由 |
| `experiment` | 实现改动、run logs、`record_main_experiment(...)`、结果证据 |
| `analysis-campaign` | campaign manifest、slice 记录、综合分析说明 |
| `write` | selected outline、writing plan、draft、references、claim-evidence map、paper bundle |
| `finalize` | 最终 summary、closure state、关闭前健康检查 |
| `decision` | durable route decision、next-anchor recommendation |
| `intake-audit` | trusted 与 untrusted 资产映射、next anchor recommendation |
| `review` | review report、revision log、experiment TODO list |
| `rebuttal` | review matrix、response letter、text deltas、evidence-update plan |
| `figure-polish` | 最终 polished figure 资产和已检查过的导出结果 |

## 8. 内建 MCP 结构

DeepScientist 故意把内建 MCP 面压得很小。

只有下面三个 namespace 是内建的：

- `memory`
- `artifact`
- `bash_exec`

没有单独公开的内建 `git` namespace。

所有 Git-aware 行为都通过 `artifact` 暴露。

### 8.1 `memory`

作用：

- 保存可复用知识
- 保存应该跨 turn 保留下来的经验
- 管理 quest-local 或 global memory cards

当前内建工具有：

- `memory.write(...)` — 默认 `scope='global'`；写 quest 内部任务追踪时显式传 `scope='quest'`
- `memory.read(...)`
- `memory.search(...)`
- `memory.list_recent(...)`
- `memory.promote_to_global(...)`

当输出应该被后续轮次继续复用时，用 `memory`。

不要把瞬时进度消息塞到 memory 里。

### 8.2 `artifact`

作用：

- quest control plane
- durable research state
- Git-aware branch / worktree 路由
- experiment 与 paper 记录
- 用户可见交互连续性

artifact 名字虽然多，但本质上还是一个家族。

#### A. 通用持久记录

- `artifact.record(...)`
- `artifact.refresh_summary(...)`
- `artifact.render_git_graph(...)`

#### B. 分支与路线控制

- `artifact.checkpoint(...)`
- `artifact.prepare_branch(...)`
- `artifact.activate_branch(...)`
- `artifact.submit_idea(...)`
- `artifact.list_research_branches(...)`
- `artifact.resolve_runtime_refs(...)`

#### C. Baseline 生命周期

- `artifact.publish_baseline(...)`
- `artifact.attach_baseline(...)`
- `artifact.confirm_baseline(...)`
- `artifact.waive_baseline(...)`

#### D. 实验与分析生命周期

- `artifact.record_main_experiment(...)`
- `artifact.create_analysis_campaign(...)`
- `artifact.get_analysis_campaign(...)`
- `artifact.record_analysis_slice(...)`

#### E. Paper 生命周期

- `artifact.submit_paper_outline(...)`
- `artifact.list_paper_outlines(...)`
- `artifact.submit_paper_bundle(...)`

#### F. 阅读与交互连续性

- `artifact.arxiv(...)`
- `artifact.interact(...)`
- `artifact.complete_quest(...)`

对长时间协作来说，最重要的 artifact 工具是：

- `artifact.interact(...)`

因为它会把这些事情连接起来：

- 用户可见更新
- mailbox 消息轮询
- connector 投递
- threaded continuity
- 附件发送

### 8.3 `bash_exec`

作用：

- 持久化 shell 执行
- 监控长任务
- 保存 durable logs
- 允许停止和回读执行会话

当前内建工具只有一个：

- `bash_exec.bash_exec(...)`

但是它支持多种 mode：

- `detach`
- `await`
- `read`
- `kill`
- `list`
- `history`

设计原则很简单：

- 任何 shell-like 的执行都应该走 `bash_exec`
- 不要把关键执行藏在一次性 shell 片段里
- 对已经在跑的 managed session，优先使用有界等待，例如 `bash_exec.bash_exec(mode='await', id=..., wait_timeout_seconds=1800)`；如果等待窗口先结束，进程仍会继续运行，下一步通常应该先读日志，而不是直接杀掉 session

## 9. 这三个 MCP namespace 是怎么分工的

可以这样记：

- `memory`：记住
- `artifact`：决策并记录
- `bash_exec`：执行并监控

例如：

- 从失败实验里抽出可复用经验 -> `memory.write(...)`
- 确认 baseline -> `artifact.confirm_baseline(...)`
- 启动训练 -> `bash_exec.bash_exec(mode='detach', ...)`
- 给用户回传下一次 checkpoint -> `artifact.interact(...)`

如果这三类职责混用得太乱，quest 就会变得难以恢复，也难以审计。

## 10. 一轮真实 turn 通常怎么流动

一个典型 turn 大致如下：

1. 用户或 connector 发来一条消息
2. daemon 恢复 quest snapshot 和 history
3. `PromptBuilder` 组装当前 turn prompt
4. 当前 active skill 定义这一轮的阶段纪律
5. 注入 priority memory
6. agent 使用 `memory`、`artifact` 和 `bash_exec`
7. 输出被持久化进文件、artifact、memory cards、logs 和 Git 状态
8. `artifact.interact(...)` 保持用户可见线程不断线

这也是 DeepScientist 更像一个持续科研工作坊，而不是无状态聊天的原因。

## 11. 什么时候该改 prompt、skill 或 MCP 代码

可以用下面这个快速判断：

- 全局行为准则错了 -> 改 `src/prompts/system.md`
- 连续性交互不对 -> 改 `src/prompts/contracts/shared_interaction.md`
- 某个 connector 表现不对 -> 改 `src/prompts/connectors/*.md`
- 某个 stage 的工作纪律不对 -> 改 `src/skills/<skill>/SKILL.md`
- prompt 组装顺序或 runtime context 选择错了 -> 改 `src/deepscientist/prompts/builder.py`
- 内建工具面本身不对 -> 改 `src/deepscientist/mcp/server.py`

不要试图用一大段 prompt patch 去修一个真正的 MCP contract bug。

也不要为了修 stage discipline 问题，去新增一个本该属于 skill 的 MCP 工具。

## 12. 下一步建议阅读

- [07 Memory 与 MCP](./07_MEMORY_AND_MCP.md)
- [13 核心架构说明](./13_CORE_ARCHITECTURE_GUIDE.md)
- [06 Runtime 与 Canvas](./06_RUNTIME_AND_CANVAS.md)
- [01 设置参考](./01_SETTINGS_REFERENCE.md)

## 13. 跨 quest 经验蒸馏

`experience_distill` 开关、finalize 终结门、`decision(action='distill_review')` 制品、`recall_priors` 提示、以及 `memory.list_knowledge_summaries` / `artifact.list_distill_candidates` 这两个 MCP 工具，统一在 [34 Experience Distillation Guide](../en/34_EXPERIENCE_DISTILL_GUIDE.md) 中说明（中文版已移除）。
