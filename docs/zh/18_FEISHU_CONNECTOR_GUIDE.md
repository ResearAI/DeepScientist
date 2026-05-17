# 18 Feishu Connector 指南

当你希望通过 Feishu / Lark 继续推进 DeepScientist quest 时，请阅读这份指南。

当前开源版本中的 Feishu 推荐路径使用内置 long-connection 方案：

- 不需要公网 event callback
- 核心凭据是 `app_id` 和 `app_secret`
- 可以把多个 Feishu 应用连接配置成独立的 `profiles`
- 如果启用自动绑定，私聊可以自动跟随最新活跃 quest

## 1. Feishu 支持包含什么

当前 Feishu connector 由以下部分组成：

- `FeishuLongConnectionService`：负责 long-connection 入站接收
- `GenericRelayChannel`：负责 bindings、inbox/outbox、targets 与运行时状态
- `FeishuConnectorBridge`：负责直接出站发送

这意味着 Feishu 已经接入了和其他 connector 一致的 quest 绑定模型。

## 2. 推荐配置路径

1. 打开 Feishu / Lark 开发者平台。
2. 创建应用。
3. 保存 `app_id` 和 `app_secret`。
4. 打开 `Settings > Connectors > Feishu`。
5. 启用 Feishu。
6. 保持 `transport: long_connection`。
7. 填写 `app_id` 与 `app_secret`。
8. 保存连接器配置。
9. 给 bot 发送一条真实消息。
10. 回到 DeepScientist，确认目标会话已经被自动发现。

如果要连接多个 Feishu 应用，请在 `profiles` 下为每个应用添加一个启用项。
每个 profile 都需要唯一的 `profile_id`、唯一的 `app_id`，以及自己的
`app_secret` 或 `app_secret_env`。

## 3. 关键配置字段

主要字段包括：

- `enabled`
- `transport`
- `bot_name`
- `app_id`
- `app_secret`
- `api_base_url`
- `command_prefix`
- `dm_policy`
- `allow_from`
- `group_policy`
- `group_allow_from`
- `groups`
- `require_mention_in_groups`
- `auto_bind_dm_to_active_quest`
- `profiles`

完整字段说明请参考 [01 设置参考](./01_SETTINGS_REFERENCE.md)。

## 4. 绑定模型

Feishu 会话会被规范化成 quest-aware connector id，例如：

- `feishu:direct:<chat_id>`
- `feishu:group:<chat_id>`

DeepScientist 绑定的是这个规范化后的 conversation id，而不是临时 callback payload。

重要规则：

- 一个 quest 会保留本地访问，并且最多只绑定 1 个外部 connector target
- 如果启用了自动绑定，Feishu 私聊可以自动跟随最新活跃 quest
- 之后也可以在项目设置页修改绑定

## 5. 群聊行为

默认情况下：

- 私聊允许直接触发
- 群聊行为由 `group_policy` 控制
- 如果 `require_mention_in_groups` 为 `true`，机器人只有在被明确 mention，或收到命令时才会响应

这也是更适合多人协作群的推荐默认值。

## 6. 出站投递

当前 Feishu connector 主要聚焦于 text-first 的 quest 更新：

- 进度
- 里程碑摘要
- 绑定通知
- 结构化 quest 回复

当前 bridge 使用 Feishu Open Platform 的消息接口发送。

## 7. 常见问题排查

### 设置页里看不到 Feishu

Feishu 可能被 system connector gate 隐藏了。请确认：

- `config.connectors.system_enabled.feishu` 为 `true`

### 校验提示缺少凭据

请检查：

- `app_id` 是否已填写
- `app_secret` 是否已填写
- 或 `app_secret_env` 是否指向真实存在的环境变量

### 没有自动发现目标会话

请检查：

- 应用凭据是否正确
- bot 是否已经收到至少一条真实入站消息
- `transport` 是否仍然是 `long_connection`

### 群聊里 bot 不响应

请检查：

- `group_policy`
- `groups`
- `group_allow_from`
- `require_mention_in_groups`

### 无法从 Feishu 继续已有 quest

请检查：

- 当前会话是否已经绑定到目标 quest
- 或 `auto_bind_dm_to_active_quest` 是否已经启用

## 8. 相关文档

- [01 设置参考](./01_SETTINGS_REFERENCE.md)
- [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)
- [09 启动诊断](./09_DOCTOR.md)
- [13 核心架构说明](./13_CORE_ARCHITECTURE_GUIDE.md)
