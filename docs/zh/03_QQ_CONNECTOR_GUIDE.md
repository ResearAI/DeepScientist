# 03 QQ 连接器指南：如何用 QQ 与 DeepScientist 沟通

本文说明如何通过 QQ 与 DeepScientist 对话，以及如何在 DeepScientist 的 `Settings` 页面完成 QQ connector 配置。

适用范围：

- 当前 DeepScientist 内置 QQ 官方 Gateway 直连方案
- 不需要公网 callback URL
- 不需要 `relay_url`
- 不需要额外安装 QQ 插件

如果你此前参考过 OpenClaw / NanoClaw 一类的文章，请特别注意：DeepScientist 的 QQ 接入方式已经内置在运行时里，配置入口是 `Settings > Connectors > QQ`，而不是命令行安装插件。

## 1. 你最终会得到什么

完成本文档后，你应该可以做到：

- 用 QQ 私聊 DeepScientist
- 让 QQ 自动绑定到当前最新项目
- 在 QQ 中使用 `/new`、`/use latest`、`/status` 等命令
- 在 `Settings` 页面看到自动检测到的 `openid`
- 从 `Settings` 页面执行非破坏性的连接测试
- 当 QQ 绑定到 quest 时，在每次主实验完成后自动收到按指标生成的时间线图片

### 部署前检查清单

开始前，建议先确认下面几项：

- DeepScientist 已经成功安装，并且 daemon / web UI 正在运行
- 你可以正常打开 `Settings > Connectors`
- 你已经准备好 QQ 机器人的 `AppID` 和 `AppSecret`
- 你有一个真实的 QQ 账号可以主动给机器人发送第一条私聊消息
- 如果你修改过 QQ 配置，`Restart gateway on config change` 建议保持开启

如果上面任意一项还没有满足，先补齐，再继续下面的配置流程，会省很多排查时间。

## 2. 注册 QQ 机器人

这一部分参考腾讯云开发者社区文章《OpenClaw 接入 QQ 机器人》中的注册流程与截图：

- 原文链接：https://cloud.tencent.com/developer/article/2635190
- QQ Bot 官方平台：https://bot.q.qq.com/

建议以 QQ Bot 官方平台为准进行创建；下面的截图用于帮助你快速识别页面。

### 2.1 打开机器人注册入口

优先使用官方平台：

```text
https://bot.q.qq.com/
```

腾讯云文章中给出的快速入口也可以作为参考：

```text
https://q.qq.com/qqbot/openclaw/login.html
```

![QQ 机器人注册入口](../images/qq/tencent-cloud-qq-register.png)

### 2.2 登录并创建机器人

1. 使用 QQ 扫码登录。
2. 创建一个新的 QQ 机器人。
3. 按页面提示完成机器人的基础信息配置。

### 2.3 立刻保存 `AppID` 和 `AppSecret`

创建成功后，请立即记录下面两项：

| 字段 | 说明 | 是否必填到 DeepScientist |
| --- | --- | --- |
| `AppID` | 机器人唯一标识 | 必填 |
| `AppSecret` | 调用 QQ Bot API 的密钥 | 必填 |

重要易错点：

- `AppSecret` 往往只在创建或重置时显示一次。
- 如果你没有保存 `AppSecret`，后续通常只能去控制台重置。
- DeepScientist 只需要这两个凭据即可启动 QQ 官方 Gateway 直连。

## 3. 在 DeepScientist 里，不需要做什么

如果你是从 OpenClaw 相关文章迁移过来的，这一节很重要。

在 DeepScientist 中，下面这些步骤都不需要做：

- 不需要安装 `@sliverp/qqbot`
- 不需要执行 `openclaw channels add ...`
- 不需要配置公网 callback URL
- 不需要配置 `relay_url`
- 不需要在第一次联通前手动填写 `openid`

DeepScientist 当前的 QQ 路径是：

- 固定 `transport: gateway_direct`
- 直接使用 `app_id + app_secret`
- 首次私聊后自动检测并保存 `openid`

## 4. 在 Settings 页面配置 QQ

打开：

- [Settings > Connectors > QQ](/settings/connectors#connector-qq)

进入后会直接定位到 `QQ` 配置卡片。当前页面按步骤分成：

- `#connector-qq-step-credentials`：填写 `App ID` 与 `App Secret`
- `#connector-qq-step-bind`：保存后，提示你先从 QQ 发送第一条私聊消息
- `#connector-qq-step-success`：OpenID 自动检测成功后的确认区域
- `#connector-qq-step-advanced`：高级设置与里程碑投递开关

### 4.1 建议按这个顺序填写

| 字段 | 如何填写 | 建议 |
| --- | --- | --- |
| `Enabled` | 打开 | 必开 |
| `Transport` | 保持 `gateway_direct` | 固定值，不需要改 |
| `App ID` | 填 QQ 机器人后台拿到的 `AppID` | 必填 |
| `App secret` | 填 QQ 机器人后台拿到的 `AppSecret` | 必填 |
| `Detected OpenID` | 先留空 | 第一次私聊后自动填充 |

其余高级项例如群内 @ 规则、命令前缀、自动绑定、里程碑投递，都放在 `#connector-qq-step-advanced` 里。当前默认是“里程碑投递全部开启”，只有你想减少外发内容时才需要手动关闭。

### 4.2 推荐保存前先看清楚的几点

- QQ 不需要 `public_callback_url`
- QQ 不需要 `relay_url`
- `Detected OpenID` 不是一开始就要填的字段
- 如果你还没有给机器人发过私聊消息，那么 `Detected OpenID` 为空是正常的

## 5. 推荐联通测试流程

这是最稳妥、最少踩坑的一条路径。

如果你同时跑多个 quest，QQ 适合跟进几个常用任务，但建议最多 5 个左右；更多任务请主要用 Web 查看和操作。详见 [34 多任务入口选择](./34_MULTITASK_ORCHESTRATION_GUIDE.md)。

### 第一步：保存凭据

先在 `QQ` 配置卡里填好：

- `App ID`
- `App secret`

然后保存。

### 第二步：点击“校验”

在 `Settings` 页面点击：

- `校验`

期望结果：

- 不再出现缺少 `app_id` 或 `app_secret` 的错误

### 第三步：点击“全部测试”或单独“发送测试消息”

在第一次私聊前，QQ 测试结果很可能出现这类提示：

```text
QQ readiness is healthy, but no OpenID has been learned yet. Save credentials, then send one private QQ message so DeepScientist can auto-detect and save the `openid`.
```

这通常不是致命错误，而是在提醒你：

- DeepScientist 已经能做 `access_token` 交换和 `/gateway` 探测
- 但还没有一个可以主动发消息的目标 `openid`

换句话说：

- “就绪性检查成功”不等于“已经知道该把测试消息发给谁”

### 第四步：从你的 QQ 给机器人发第一条私聊消息

推荐先用私聊，不要一开始就用群聊。

![QQ 私聊机器人示意](../images/qq/tencent-cloud-qq-chat.png)

可以发送：

```text
/help
```

或者：

```text
你好
```

如果接入正常，DeepScientist 会自动检测这次私聊对应的 `openid`，并写回 `main_chat_id`。

### 第五步：回到 Settings 页面确认状态

重新打开或刷新 `Settings > Connectors > QQ`，或者直接回到 [#connector-qq-step-success](/settings/connectors#connector-qq-step-success)，重点看：

- `Detected OpenID` 是否已经自动出现
- 右侧 `Snapshot` 中：
  - `Transport` 是否是 `gateway_direct`
  - `Connection` / `Auth` 是否接近 `ready`
  - `Discovered targets` 是否大于 `0`
  - `Bound target` 是否出现你的 `openid`

### 第六步：再次点击“发送测试消息”

这时再点：

- `发送测试消息`

如果成功，说明 DeepScientist 已经能够：

- 主动向该 QQ 用户发送消息
- 接收该 QQ 用户的新消息

### 5.1 成功后应该看到什么

如果整个链路正常，通常会同时看到下面这些现象：

- QQ 机器人能回复 `/help`、`/status` 之类的命令
- `Settings > Connectors > QQ` 中的 `Detected OpenID` 不再为空
- `Snapshot` 里出现已经发现的目标会话，且绑定目标不是空
- 再次点击“发送测试消息”时，不再提示 target 为空
- 如果当前已经有最新项目，普通文本会自动进入该项目；如果还没有项目，则优先返回帮助信息

## 5.3 主实验指标图自动推送

当 QQ 是当前 quest 的绑定连接器时，DeepScientist 现在会在每次主实验完成后自动发送指标时间线图片。

当前行为：

- 每个指标生成一张图
- 如果 baseline 存在该指标，会画一条横向虚线作为 baseline 参考线
- 系统会自动判断该指标是“越高越好”还是“越低越好”
- 超过 baseline 的点会额外标星
- 最新点使用莫兰迪深红色填充
- 较早的点使用莫兰迪深蓝色填充
- 如果指标有多个，DeepScientist 会按顺序发送，并在相邻两张图之间间隔约 2 秒

这些图来自 quest 本地生成的文件，并会作为 QQ 原生图片自动发送。

如果你想关闭这项自动推送，可以在 QQ 连接器配置中关闭 `auto_send_main_experiment_png`。

### 5.2 报错提示速查

| 提示 | 代表什么 | 应该怎么做 |
| --- | --- | --- |
| `app_id is required` / `app_secret is required` | 凭据没填完整 | 回到 Settings 补全后重新保存 |
| `401` / `invalid credential` / token 获取失败 | `AppID` 或 `AppSecret` 有误，或者 secret 已被重置 | 到 QQ 机器人后台重新核对并保存 |
| `QQ readiness is healthy, but no OpenID has been learned yet...` | 凭据大概率已经生效，但系统还不知道要给哪个 QQ 用户发主动消息 | 先用你的 QQ 私聊机器人一条消息，让系统自动发现 `openid` |
| `QQ callback flow usually needs public_callback_url...` | 这是旧式 callback/relay 思路下的提示，不是当前 DeepScientist 推荐路径 | 保持 `transport = gateway_direct`，不要额外配置 callback URL |
| `QQ relay mode needs relay_url...` | 说明 transport 被错误切到了 relay 模式 | 改回 `gateway_direct` |
| `Detected OpenID` 一直为空 | 机器人还没收到第一条私聊，或者配置改完后 gateway 没重启成功 | 确认先保存配置，再从 QQ 私聊机器人，必要时重启 gateway |

## 6. 如何在 QQ 中和 DeepScientist 沟通

常用命令：

| 命令 | 作用 |
| --- | --- |
| `/help` | 查看帮助 |
| `/projects` 或 `/list` | 查看项目列表 |
| `/use <quest_id>` | 绑定指定项目 |
| `/use latest` | 绑定最新项目 |
| `/new <goal>` | 新建项目并把当前 QQ 会话绑定过去 |
| `/status` | 查看当前项目状态 |

日常沟通建议：

- 如果已经有最新项目，普通文本通常会继续那个项目
- 如果还没有项目，优先发送 `/new <goal>`
- 如果你想切换到另一个项目，显式发送 `/use <quest_id>`

## 7. 最容易踩坑的地方

### 7.1 误以为 QQ 需要公网回调

当前 DeepScientist 的 QQ 方案不需要公网 callback。

看到这些字段时，请注意：

- `public_callback_url`：不需要
- `relay_url`：不需要

### 7.2 误以为测试失败就是凭据错了

如果提示 target 为空，通常只是因为：

- 你还没给机器人发第一条私聊
- 系统还没自动拿到 `openid`

这和 `app_id/app_secret` 是否有效，不是同一类问题。

### 7.3 误以为 `openid` 需要自己去找

在 DeepScientist 里，最简单的方式不是手工查 `openid`，而是：

1. 先保存 `App ID` 和 `App secret`
2. 再用 QQ 给机器人发一条私聊消息
3. 等系统自动检测并写回 `Detected OpenID`

### 7.4 群聊里机器人没反应

先检查：

- 你是不是在群里没有 `@` 机器人
- `Require @ mention in groups` 是否开启

如果你还没有跑通私聊，先不要直接排查群聊。

### 7.5 切换了另一个 QQ 操作者，但 `main_chat_id` 还是旧的

如果之前已经绑定过一个 `main_chat_id`，新的私聊用户不一定会自动覆盖旧值。

这时建议：

- 先确认当前应该由谁作为主操作者
- 如有必要，手动清空或重新配置 QQ 目标，再重新测试

## 8. 推荐的最小可行部署顺序

如果你只想最快跑通：

1. 创建 QQ 机器人
2. 保存 `AppID` 和 `AppSecret`
3. 打开 [Settings > Connectors > QQ](/settings/connectors#connector-qq)
4. 启用 QQ，并填入 `App ID` / `App secret`
5. 保存并点击 `校验`
6. 用你的 QQ 私聊机器人，发送 `/help`
7. 回到设置页确认 `Detected OpenID` 已自动出现
8. 再次点击 `发送测试消息`
9. 用 `/new <goal>` 或 `/use latest` 开始正式使用

## 9. 参考资料

- 腾讯云开发者社区：《OpenClaw 接入 QQ 机器人》
  - https://cloud.tencent.com/developer/article/2635190
- QQ Bot 官方平台
  - https://bot.q.qq.com/

说明：

- 本文中的“注册 QQ 机器人”流程和截图参考了上面的腾讯云文章
- 但 DeepScientist 的配置方式以当前 DeepScientist 内置 QQ connector 为准
