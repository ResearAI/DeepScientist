# 17 WhatsApp Connector 指南

当你希望通过 WhatsApp 继续推进 DeepScientist quest 时，请阅读这份指南。

当前开源版本里的 WhatsApp 推荐路径使用本地 local-session 方案：

- 不需要公网 webhook
- 本地认证 / 会话状态保存在你自己的机器上
- 如果启用自动绑定，私聊可以自动跟随最新活跃 quest

## 1. WhatsApp 支持包含什么

当前 WhatsApp connector 由以下部分组成：

- `WhatsAppLocalSessionService`：负责本地会话同步与入站接入
- `GenericRelayChannel`：负责 bindings、inbox/outbox、targets 与运行时状态
- `WhatsAppConnectorBridge`：负责出站投递

在推荐路径下，出站消息会先写入 local-session outbox，再由本地 session / sidecar 处理。

## 2. 推荐配置路径

1. 打开 `Settings > Connectors > WhatsApp`。
2. 启用 WhatsApp。
3. 保持 `transport: local_session`。
4. 保持默认或指定一个可写的 `session_dir`。
5. 保存连接器配置。
6. 完成本地 WhatsApp 会话登录流程。
7. 从 WhatsApp 发送一条真实消息。
8. 回到 DeepScientist，确认目标会话已经被自动发现。

## 3. 关键配置字段

主要字段包括：

- `enabled`
- `transport`
- `bot_name`
- `auth_method`
- `session_dir`
- `command_prefix`
- `dm_policy`
- `allow_from`
- `group_policy`
- `group_allow_from`
- `groups`
- `auto_bind_dm_to_active_quest`

完整字段说明请参考 [01 设置参考](./01_SETTINGS_REFERENCE.md)。

## 4. 绑定模型

WhatsApp 会话会被规范化成 quest-aware connector id，例如：

- `whatsapp:direct:<jid>`
- `whatsapp:group:<jid>`

DeepScientist 绑定的是这个规范化后的 conversation id，而不是临时浏览器状态或短期 session 状态。

重要规则：

- 一个 quest 会保留本地访问，并且最多只绑定 1 个外部 connector target
- 如果启用了自动绑定，WhatsApp 私聊可以自动跟随最新活跃 quest
- 之后也可以在项目设置页修改绑定

如果你同时跑多个 quest，请先看 [34 多任务入口选择](./34_MULTITASK_ORCHESTRATION_GUIDE.md)，不要把所有任务都塞进一个聊天入口。

## 5. local-session 运行方式

当前开源版本里的 WhatsApp 路径是 local-session 导向的：

- 运行时状态会镜像写入 DeepScientist 的 connector 日志目录
- 入站消息会从本地 session inbox 中被消费
- 出站消息会被写入本地 session outbox

这也符合 DeepScientist 的本地优先设计。

## 6. 群聊行为

默认情况下：

- 私聊可以和活跃 quest 自动配对
- 群聊行为由 `group_policy` 控制
- 也可以通过 `groups` 与 `group_allow_from` 强制使用白名单

## 7. 常见问题排查

### 设置页里看不到 WhatsApp

WhatsApp 可能被 system connector gate 隐藏了。请确认：

- `config.connectors.system_enabled.whatsapp` 为 `true`

### 校验提示连接器未就绪

请检查：

- `transport` 是否为 `local_session`
- `session_dir` 是否指向可写目录

### 没有自动发现目标会话

请检查：

- 本地登录 / 配对流程是否已经完成
- 是否至少有一条真实入站消息进入 local session inbox

### 无法从 WhatsApp 继续已有 quest

请检查：

- 当前会话是否已经绑定到目标 quest
- 或 `auto_bind_dm_to_active_quest` 是否已经启用

### 出站消息没有送达

请检查：

- 本地 session sidecar / processor 是否正在运行
- 本地 session outbox 是否正在被消费
- 目标 JID 是否正确

## 8. 相关文档

- [01 设置参考](./01_SETTINGS_REFERENCE.md)
- [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)
- [09 启动诊断](./09_DOCTOR.md)
- [13 核心架构说明](./13_CORE_ARCHITECTURE_GUIDE.md)
