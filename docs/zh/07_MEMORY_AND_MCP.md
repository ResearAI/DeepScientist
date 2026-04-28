# 07 Memory 与 MCP：内建 MCP 和记忆协议

本文定义 DeepScientist Core 内建的 3 个 MCP namespace 的含义与使用纪律：

- `memory`
- `artifact`
- `bash_exec`

目标很简单：

- `artifact` 驱动 quest 的“研究状态与结构化产物”
- `memory` 降低重复发现成本（可复用知识）
- `bash_exec` 运行可审计的持久 shell 工作

## 1. 什么时候用哪个 MCP

当输出是“以后还会复用、需要记住”的内容时，用 `memory`：

- 论文阅读笔记（可复用）
- 失败模式与排错经验
- 选择/否决某个 idea 的稳定理由
- 评测/指标的稳定注意事项（metric caveat）

对 ideation 的要求（非常重要）：

- 在提出新 idea 前，先回看相关的 idea cards
- 在扩大检索前，先回看实验结果与失败模式
- 不要把历史上某行内容当作当前 active idea，除非它被明确再次选中

当输出会改变/汇报 quest 状态时，用 `artifact`：

- idea 的创建/修订
- 分支/工作树切换记录
- 主实验记录
- analysis campaign 记录
- 进度/里程碑推送
- 决策与 approval
- connector 侧需要看到的交互状态

当需要运行“可持续跟踪、可回放”的命令时，用 `bash_exec`：

- 训练/评测
- 长时间脚本
- 需要后续 `read/list/kill` 的命令

## 2. Memory 工具语义（建议用法）

### `memory.list_recent(...)`

用途：

- 快速恢复本地上下文
- pause/restart 后重建状态

建议在：

- turn 开始
- 恢复 stopped quest 后
- 在决定“要读哪几张卡”之前

示例：

```text
memory.list_recent(scope="quest", limit=5, kind="knowledge")
```

### `memory.search(...)`

用途：

- 在重复劳动之前做定向检索

建议在：

- 做大范围文献检索之前
- 反复失败前先查是否已有排错记录
- 选择/修订 idea 之前
- 问用户前先查是否已经有稳定答案

常见 kind：

- `papers`：论文与引用
- `decisions`：路线选择理由
- `episodes`：故障与排错
- `knowledge`：稳定规则

示例：

```text
memory.search(query="official validation split", scope="both", kind="papers", limit=6)
memory.search(query="metric wiring mismatch", scope="quest", kind="episodes", limit=5)
memory.search(query="baseline novelty constraints", scope="both", kind="ideas", limit=6)
```

### `memory.read(...)`

用途：

- 读一张“确定相关”的卡

建议：

- 先 `search/list_recent` 找到少量候选，再 `read` 其中 1~3 张
- 不要一口气读几十张

示例：

```text
memory.read(path="~/DeepScientist/quests/q-xxxx/memory/knowledge/metric-contract.md")
```

### `memory.write(...)`

用途：

- 写入可复用的持久化发现

默认 scope 为 `global`。仅在写 quest 内部任务追踪（TODO 列表、草稿大纲、进行中的 checkpoint、resume packet 等）时显式传 `scope='quest'`。

适合写在：

- 有价值的论文阅读总结之后
- 非平凡的 debug episode 之后
- 稳定的评测规则确认之后
- 选中/否决某个 idea（有理由与证据）之后

不适合写在：

- 泛泛的聊天总结
- 临时的进度 ping（那应该用 artifact）
- 已经在 artifact 中更好记录的信息

Memory 卡片格式：**Markdown + 顶部 YAML**。建议包含：

1. context
2. action/observation
3. outcome
4. interpretation
5. boundaries
6. evidence paths
7. retrieval hints

示例：

```md
---
id: knowledge-1234abcd
type: knowledge
title: 指标对比只有在官方验证划分下才成立
quest_id: q-xxxx
scope: quest
tags:
  - stage:baseline
  - topic:metric-contract
stage: baseline
confidence: high
evidence_paths:
  - artifacts/baselines/verification_report.md
retrieval_hints:
  - baseline comparison
  - metric contract
updated_at: 2026-03-11T18:00:00+00:00
---

背景：在官方 benchmark 设置下验证 baseline。

观察：只有使用官方 validation split 时数值才一致。

解释：若使用自定义 split，与该 baseline 的对比将不成立。

边界：该规则是 benchmark-specific 的；除非在多个 quest 中复现，否则不建议提升为 global。
```

### `memory.promote_to_global(...)`

用途：

- 将已证明可复用的 quest-local 经验提升到 global memory

仅在以下情况下使用：

- 不是项目噪声
- 已足够稳定
- 其他 quest 很可能受益

## 3. Artifact vs Memory 的边界

两者都写的前提是“职责不同”：

- 实验完成：
  - `artifact.record_*` 记录官方实验与证据
  - `memory.write`（可选）只记录可复用规则/教训

不要用 memory 代替实验 artifact。
不要用 artifact 代替可复用知识卡。

## 4. Artifact 指标契约规则

baseline 与主实验的正式指标提交，应以 `artifact` 为唯一权威入口。

### `artifact.confirm_baseline(...)`

对于已确认的 baseline：

- canonical metric contract 应保存在 `<baseline_root>/json/metric_contract.json`
- canonical `metrics_summary` 应是顶层扁平字典，key 直接使用论文面对比时的 metric id
- 如果原始评测输出是嵌套结构，应在 `metric_contract.metrics` 中为每个必需 canonical metric 提供显式 `origin_path`，而不是直接提交嵌套 blob
- 每个 canonical baseline metric 都应说明数值来源，至少包含：
  - `description`
  - `derivation` 或 `origin_path`
  - `source_ref`
- `primary_metric` 只是 headline metric，不能借此删掉其他论文面对比所需指标

### `artifact.record_main_experiment(...)`

对于基于已确认 baseline 的主实验：

- 默认以已确认 baseline 的 metric-contract JSON 作为 canonical comparison contract
- 主实验提交时必须覆盖 baseline 的全部必需 metric id
- 可以多报额外指标，但不能缺少 baseline 的必需指标
- canonical baseline metrics 应继续使用原有评测代码和指标定义
- 如果确实需要额外评测器，应把它作为 supplementary evidence 记录，而不是替换 canonical comparator

### 校验失败与临时记录

- 当 MCP 工具开启严格校验时，失败会返回结构化错误字段，例如：
  - `missing_metric_ids`
  - `baseline_metric_ids`
  - `baseline_metric_details`
  - `evaluation_protocol_mismatch`
- `Result/metric.md` 只可作为工作过程中的临时草稿/记忆文件，不是必需文件，也不是权威来源
- 如果存在 `Result/metric.md`，请在调用 artifact 提交前用它核对最终 baseline 或主实验提交内容，避免遗漏或写错

## 5. Bash exec 的基本用法

用于可监控命令：

```text
bash_exec.bash_exec(command="python train.py --config configs/main.yaml", mode="detach", workdir="<quest workspace>")
```

随后检查：

```text
bash_exec.bash_exec(mode="list", status="running")
bash_exec.bash_exec(mode="read", id="<bash_id>")
bash_exec.bash_exec(mode="await", id="<bash_id>", wait_timeout_seconds=1800)
```

如果这个有界 `await` 返回时 session 仍然是 `running`，说明进程还在后台继续跑。此时先读取保存的日志、判断是否存在真实前进，再决定是否还要继续等下一个 `1800s` 窗口。只有在确实需要停止时才使用 `kill`。

## 6. Prompt 级纪律（建议）

通常推荐遵循：

1. turn 开始/恢复时先 `memory.list_recent(...)`
2. 重复劳动前 `memory.search(...)`
3. 只 `memory.read(...)` 少量关键卡片
4. quest 状态变化用 `artifact`
5. 长任务 shell 用 `bash_exec`
6. 有真正的可复用发现才 `memory.write(...)`

## 7. UI 期望

在 `/projects/{id}` 的 Studio trace 中：

- `memory.*` 应渲染为结构化卡片，而不是 raw JSON
- 卡片应显示：
  - 操作类型
  - scope / kind
  - title 或 query
  - 命中条目或写入摘要

如果 agent 完全不调用 memory：优先看 prompt/skill 行为是否偏离。
如果 agent 调用 memory 但 UI 只显示 raw logs：优先修 UI 的渲染层。

## 8. 跨 quest 经验蒸馏

`experience_distill` 开关、finalize 终结门、`decision(action='distill_review')` 制品、`recall_priors` 提示、以及 `memory.list_knowledge_summaries` / `artifact.list_distill_candidates` 这两个 MCP 工具，统一在 [34 Experience Distillation Guide](../en/34_EXPERIENCE_DISTILL_GUIDE.md) 中说明（中文版已移除）。
