# 16 External Controller 指南

DeepScientist 已经暴露出足够多的持久状态，因此你可以在不改 core runtime 的前提下，构建一层外部编排控制器。

这篇文档说明一种最小、稳定的 external controller 模式，用来：

- 检查 quest 最近状态
- 判断当前 run 是否应该继续
- 通过 quest mailbox 注入下一步路由消息
- 必要时通过 `quest_control` 停止当前 run
- 写出一份 durable report，解释为什么 guard 被触发

这里刻意不引入重量级 plugin framework。

## 什么时候适合用 external controller

当某条规则满足下面任一条件时，适合放到外层 controller：

- 明显是项目级 / 团队级规则
- 不适合硬编码进全局 prompts 或 skills
- 更像治理逻辑，而不是 core runtime 默认行为

常见例子：

- paper-facing 写作前的 publishability admission 规则
- figure polish 在同一张图上反复 reopen 的空转
- 某个实验室自己的 stop / branch 策略

## 可以依赖的公共契约

最稳妥的扩展面是现有的 durable runtime contract：

- quest mailbox
  - 排队中的用户消息位于 `.ds/user_message_queue.json`
- 最近 quest 状态
  - runtime state、artifact state、connector 可见输出本来就是 durable files
- daemon quest control
  - `POST /api/quests/<quest_id>/control`
- connector 可见的 durable report
  - 你可以在 quest 树下写自己的 report，供下一轮 turn 引用

优先依赖这些契约，而不是 patch prompt、monkey-patch 私有实现，或者直接修改安装包文件。

## 最小 controller 工作流

一个 external controller 一般按下面顺序工作：

1. 读取最新 durable quest state。
2. 判断某个 guard 条件是否成立。
3. 写 durable report，说明：
   - 观察到了什么
   - 这意味着什么
   - 推荐的下一步路由是什么
4. 如果需要干预：
   - 可选地通过 `quest_control` 停止当前 run
   - 往 mailbox 注入一条清晰的 routed message，供下一轮处理

mailbox 里的消息应该表达结论与下一步，而不是原样转储日志。

## 一个典型的控制流

```text
读取 quest 状态
-> 识别低收益循环或路线漂移
-> 写 durable report
-> 必要时 stop 当前 run
-> 往 mailbox 注入下一步 routed message
```

## `quest_control` 请求示例

```bash
curl -X POST http://127.0.0.1:20999/api/quests/<quest_id>/control \
  -H 'Content-Type: application/json' \
  -d '{
    "action": "stop",
    "source": "external-controller"
  }'
```

## mailbox intervention 内容示例

队列文件本身由 runtime 管理，所以 controller 应该保留既有 schema，只追加一条普通的 user-style message payload。

消息正文应短而可执行，例如：

```text
Hard control message from external orchestration layer: stop the current figure loop.
Return to the main line and do one bounded route next:
1. literature scout
2. reference expansion
3. manuscript body revision
```

## durable report 建议结构

report 应该尽量简单且可审计。

一份好的 report 一般至少包含：

- `generated_at`
- `quest_id`
- `status`
- `recommended_action`
- `blockers`
- `evidence_summary`

常见且实用的做法是：一份 Markdown 报告，外加一份 machine-readable JSON。

## 不建议依赖什么

避免构建依赖下面这些东西的 controller：

- 私有 prompt 文本偏移或拼接细节
- 没有文档化的临时日志
- 直接改 `site-packages` 里的安装包文件
- 仅前端可见、没有 durable contract 的状态

如果某个 controller 必须依赖这些东西，说明契约还不够稳定。

## 设计建议

- 每个 controller 只回答一个清晰问题
- 优先写可回看的报告，而不是做隐藏副作用
- 只有当下一步路由很清楚时才 stop 当前 run
- 领域特定或团队特定规则尽量留在 core defaults 之外
- 把 external controller 当成可选治理层，而不是必需运行层

## 最适合先做的 controller

如果你想先从小处开始，优先做下面几类：

- 面向 paper-mode quest 的 publishability admission guard
- 阻止 figure reopen 循环的 figure-loop guard
- 在证据未准备好时阻止误入 `write` 的 route-drift guard
