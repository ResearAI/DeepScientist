# 16 Telegram Connector 指南

当你希望通过 Telegram 继续推进 DeepScientist quest 时，请阅读这份指南。

当前开源版本中的 Telegram 连接方式使用内置 polling 路径：

- 不需要公网 webhook
- 核心凭据是 BotFather token
- 如果启用自动绑定，私聊可以自动跟随最新活跃 quest

## 1. Telegram 支持包含什么

当前 Telegram connector 由以下部分组成：

- `TelegramPollingService`：负责入站轮询
- `GenericRelayChannel`：负责绑定、inbox/outbox、target 与运行时状态
- `TelegramConnectorBridge`：负责通过 Bot API 直接出站发送

这意味着 Telegram 已经接入了和其他 connector 一致的 quest 绑定模型。

## 2. 推荐配置路径

1. 打开 BotFather。
2. 执行 `/newbot`。
3. 保存生成的 bot token。
4. 打开 `Settings > Connectors > Telegram`。
5. 启用 Telegram。
6. 保持 `transport: polling`。
7. 填写 `bot_token`。
8. 保存连接器配置。
9. 从 Telegram 给 bot 发送一条真实私聊，例如 `/start` 或 `/help`。
10. 回到 DeepScientist，确认运行时已经发现这个 target conversation。

## 3. 关键配置字段

主要字段包括：

- `enabled`
- `transport`
- `bot_name`
- `bot_token`
- `command_prefix`
- `require_mention_in_groups`
- `dm_policy`
- `allow_from`
- `group_policy`
- `group_allow_from`
- `groups`
- `auto_bind_dm_to_active_quest`

完整字段说明请参考 [01 设置参考](./01_SETTINGS_REFERENCE.md)。

## 4. 绑定模型

Telegram 会话会被规范化成 quest-aware connector id，例如：

- `telegram:direct:<chat_id>`
- `telegram:group:<chat_id>`

DeepScientist 绑定的是这个规范化后的 conversation id，而不是临时 webhook 状态。

重要规则：

- 一个 quest 会保留本地访问，并且最多只绑定 1 个外部 connector target
- 如果启用了自动绑定，Telegram 私聊可以自动跟随最新活跃 quest
- 之后也可以在项目设置页修改绑定

如果你同时跑多个 quest，请先看 [34 多任务入口选择](./34_MULTITASK_ORCHESTRATION_GUIDE.md)，不要把所有任务都塞进一个聊天入口。

## 5. 群聊行为

默认情况下：

- Telegram 私聊允许直接触发
- 群聊行为由 `group_policy` 控制
- 如果 `require_mention_in_groups` 为 `true`，机器人只有在被明确 mention，或收到命令时才会响应

这也是更适合多人群聊的推荐默认值。

## 6. 出站投递

当前 Telegram connector 主要聚焦于 text-first 的 quest 更新：

- 进度
- 里程碑摘要
- 绑定通知
- 结构化 quest 回复

当前 bridge 使用 Telegram Bot API 的 `sendMessage` 发送。

## 7. 常见问题排查

### 设置页里看不到 Telegram

Telegram 可能被 system connector gate 隐藏了。请确认：

- `config.connectors.system_enabled.telegram` 为 `true`

### 校验提示缺少凭据

请检查：

- `bot_token` 是否已填写
- 或 `bot_token_env` 是否指向真实存在的环境变量

### 机器人收不到消息

请检查：

- bot token 是否正确
- 是否至少从 Telegram 端先和 bot 交互过一次
- `transport` 是否仍然是 `polling`
- 是否存在旧的 webhook 抢占了更新流

### 群聊里 bot 不响应

请检查：

- `group_policy`
- `groups`
- `group_allow_from`
- `require_mention_in_groups`

### Telegram 里无法继续已有 quest

请检查：

- 当前会话是否已经绑定到目标 quest
- 或 `auto_bind_dm_to_active_quest` 是否已经启用

## 8. 相关文档

- [01 设置参考](./01_SETTINGS_REFERENCE.md)
- [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)
- [09 启动诊断](./09_DOCTOR.md)
- [13 核心架构说明](./13_CORE_ARCHITECTURE_GUIDE.md)
