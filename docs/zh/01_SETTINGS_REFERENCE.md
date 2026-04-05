# 01 设置参考：如何配置 DeepScientist

本手册对应当前 DeepScientist `Settings` 页面与其实际落盘配置，写法参考 PyTorch API reference 的“摘要 + 参数 + 默认值 + 行为影响 + 示例”风格。它不是泛泛的产品介绍，而是面向实际配置、排障与日常运维的字段级参考。

相关实现来源：

- `src/ui/src/components/settings/settingsFormCatalog.ts`
- `src/ui/src/components/settings/connectorCatalog.ts`
- `src/ui/src/components/settings/RegistrySettingsForm.tsx`
- `src/deepscientist/config/models.py`
- `src/deepscientist/config/service.py`

## 总览

`Settings` 页面会直接编辑以下配置文件：

| 文件 | 页面分类 | 作用 |
| --- | --- | --- |
| `~/DeepScientist/config/config.yaml` | Runtime | 运行时主配置：主目录、daemon、UI、日志、Git、技能同步、云链接、ACP 等 |
| `~/DeepScientist/config/runners.yaml` | Models | Runner 配置：`codex` / `claude` 的二进制、模型、审批策略、沙箱与重试策略 |
| `~/DeepScientist/config/connectors.yaml` | Connectors | QQ、Telegram、Discord、Slack、Feishu、WhatsApp、Lingzhu 等连接器配置 |
| `~/DeepScientist/config/plugins.yaml` | Extensions | 插件发现、启用、禁用与信任策略 |
| `~/DeepScientist/config/mcp_servers.yaml` | MCP | 外部 MCP 服务，不包含内置 `memory`、`artifact`、`bash_exec` |

页面上的几个动作语义如下：

- `Save`：把当前结构化表单直接写回对应的 YAML 文件。
- `Check` / `Validate`：做本地结构校验，不会启动真正的研究任务。
- `Test`：执行轻量级运行时探测。不同文件的测试逻辑不同，见本文后面的“校验与测试行为”。

连接器专项文档：

- `docs/zh/03_QQ_CONNECTOR_GUIDE.md`
- `docs/zh/04_LINGZHU_CONNECTOR_GUIDE.md`

## `config.yaml`

### 摘要

`config.yaml` 是 DeepScientist 的主运行时配置文件，控制主目录、默认语言、daemon 行为、Web/TUI 地址、日志、Git、技能同步，以及少量可选的 cloud / ACP 兼容设置。

### 结构

```yaml
home: ~/DeepScientist
default_runner: codex
default_locale: en-US # 或 zh-CN，首次打开 Web 时会按浏览器语言初始化
daemon:
  session_restore_on_start: true
  max_concurrent_quests: 1
  ack_timeout_ms: 1000
ui:
  host: 0.0.0.0
  port: 20999
  auth_enabled: false
  auto_open_browser: true
  default_mode: both
logging:
  level: info
  console: true
  keep_days: 30
git:
  auto_checkpoint: true
  auto_push: false
  default_remote: origin
  graph_formats: [svg, png, json]
skills:
  sync_global_on_init: true
  sync_quest_on_create: true
  sync_quest_on_open: true
bootstrap:
  codex_ready: false
  codex_last_checked_at: null
  codex_last_result: {}
  locale_source: browser
  locale_initialized_from_browser: true
  locale_initialized_at: 2026-03-18T00:00:00+00:00
  locale_initialized_browser_locale: en-US
connectors:
  auto_ack: true
  milestone_push: true
  direct_chat_enabled: true
cloud:
  enabled: false
  base_url: https://deepscientist.cc
  token: null
  token_env: DEEPSCIENTIST_TOKEN
  verify_token_on_start: false
  sync_mode: disabled
acp:
  compatibility_profile: deepscientist-acp-compat/v1
  events_transport: rest-poll
  sdk_bridge_enabled: false
  sdk_module: acp
```

### 核心身份

**`home`**

- 类型：`string`
- 默认值：安装时的 DeepScientist 主目录，通常为 `~/DeepScientist`
- 页面标签：`Home path`
- 作用：这是配置、项目、memory、plugins、logs、cache 的根路径。
- 何时修改：仅在你明确使用自定义安装目录时修改。
- 注意事项：这不是单个项目路径，而是整个 DeepScientist 的运行时根目录。

**`default_runner`**

- 类型：`string`
- 默认值：`codex`
- 允许值：当前页面预设为 `codex`、`claude`
- 页面标签：`Default runner`
- 作用：当项目没有单独覆盖 runner 时，默认走这里指定的 runner。
- 何时修改：只有在你真的接通并启用了其他 runner 时才需要改。
- 注意事项：当前仓库的真实主路径仍然是 `codex`；`claude` 仍是预留位。

**`default_locale`**

- 类型：`string`
- 默认值：首次打开 Web 时按浏览器语言初始化，随后会落盘为 `zh-CN` 或 `en-US`
- 允许值：`zh-CN`、`en-US`
- 页面标签：`Default locale`
- 作用：影响系统 prompt 与运行时文案默认使用的语言。
- 何时修改：希望整个系统固定偏向中文或英文时修改。
- 注意事项：第一次浏览器初始化完成后，如果你在 `Settings` 手动修改这里，DeepScientist 会把它视为用户显式选择，后续不再自动跟随浏览器覆盖。

### Daemon policy

**`daemon.session_restore_on_start`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Restore sessions on start`
- 作用：daemon 启动时尝试恢复之前的项目会话状态。
- 何时关闭：你希望每次启动都从干净的运行时状态进入。

**`daemon.max_concurrent_quests`**

- 类型：`number`
- 默认值：`1`
- 页面标签：`Max concurrent projects`
- 作用：限制同时活跃的项目数量。
- 推荐值：大多数情况下保持 `1`。
- 风险：并发项目越多，资源竞争、连接器串扰和观察复杂度越高。

**`daemon.ack_timeout_ms`**

- 类型：`number`
- 默认值：`1000`
- 页面标签：`Ack timeout (ms)`
- 作用：短确认、连接器反馈等轻量行为的超时预算。
- 何时增大：本地 I/O、bridge 或 sidecar 持续偏慢时。

### Web / TUI runtime

**`ui.host`**

- 类型：`string`
- 默认值：`0.0.0.0`
- 页面标签：`UI host`
- 作用：本地 Web UI 服务绑定的地址。
- 典型取值：
  - `0.0.0.0`：允许局域网、容器或反向代理访问。
  - `127.0.0.1`：仅本机访问。
- 注意事项：如果你希望通过域名或局域网设备访问，一般必须保持 `0.0.0.0`。

**`ui.port`**

- 类型：`number`
- 默认值：`20999`
- 页面标签：`UI port`
- 作用：本地 UI 服务监听端口。
- 何时修改：端口冲突时。

**`ui.auth_enabled`**

- 类型：`boolean`
- 默认值：`false`
- 页面标签：`Require local password`
- 作用：为 Web 工作区和所有 `/api/*` 路由启用本地 16 位浏览器访问密码。
- 行为：
  - `true`：`ds` 会在终端打印这次启动生成的密码；如果浏览器里没有有效登录态，就必须先输入密码；登录成功后会在浏览器中持久化。
  - `false`：关闭本地密码门禁，保持普通本地地址直连行为。
- CLI 覆盖：`ds --auth true` 或 `ds --auth false`

**`ui.auto_open_browser`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Auto-open browser`
- 作用：启动 UI 时自动打开浏览器。
- 何时关闭：远程服务器、无头环境、tmux/SSH 环境。

**`ui.default_mode`**

- 类型：`string`
- 默认值：`both`
- 允许值：`both`、`web`、`tui`
- 页面标签：`Default start mode`
- 作用：决定 `ds` 默认打开 Web、TUI，或两者同时打开。

### Logging

**`logging.level`**

- 类型：`string`
- 默认值：`info`
- 允许值：`debug`、`info`、`warning`、`error`
- 页面标签：`Log level`
- 作用：控制 daemon 与 runner 日志详细程度。
- 推荐值：日常 `info`，排障时临时切到 `debug`。

**`logging.console`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Log to console`
- 作用：除文件日志外，也在当前终端镜像输出日志。

**`logging.keep_days`**

- 类型：`number`
- 默认值：`30`
- 页面标签：`Retention days`
- 作用：本地日志保留天数。
- 何时增大：需要保留较长的审计链、复现链或 connector 排障记录时。

### Git behavior

**`git.auto_checkpoint`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Auto-checkpoint`
- 作用：项目过程中自动做 Git 检查点。
- 何时关闭：你完全希望手动控制提交节奏。

**`git.auto_push`**

- 类型：`boolean`
- 默认值：`false`
- 页面标签：`Auto-push`
- 作用：把自动检查点推送到默认远端。
- 风险：一旦开启，研究过程中的中间产物可能会更早离开本机。

**`git.default_remote`**

- 类型：`string`
- 默认值：`origin`
- 页面标签：`Default remote`
- 作用：自动推送和导出时使用的默认 Git 远端名。

**`git.graph_formats`**

- 类型：`list[string]`
- 默认值：`["svg", "png", "json"]`
- 页面标签：`Graph export formats`
- 作用：决定 Git / Canvas 图导出时生成哪些格式。

### Reports & visuals

配色不再通过 `Settings` 或 `config.yaml` 配置。

- 图表与论文图的配色规范现在直接写在：
  - `src/prompts/system.md`
  - `src/skills/experiment/SKILL.md`
  - `src/skills/analysis-campaign/SKILL.md`
  - `src/skills/write/SKILL.md`
- DeepScientist 统一使用固定的莫兰迪配色指引，而不是每台机器各自配置。
- 具体的长期参考页为 `docs/zh/08_FIGURE_STYLE_GUIDE.md`。
- 如果需要调整默认视觉语言，应修改 prompt / skill 合同，而不是再新增设置项。

### Skill synchronization

**`skills.sync_global_on_init`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Sync global skills on init`
- 作用：初始化时把项目技能同步到全局 `~/.codex/skills` / `~/.claude/agents`。

**`skills.sync_quest_on_create`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Sync project skills on create`
- 作用：创建项目时，把技能镜像到项目本地 `.codex/skills` / `.claude/agents`。
- Prompt 说明：同时会初始化 quest 本地的受管 prompt 镜像 `.codex/prompts/`。

**`skills.sync_quest_on_open`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Sync project skills on open`
- 作用：打开已有项目时刷新本地技能镜像。
- Prompt 说明：会刷新当前 DeepScientist home 下已发现 quest 的本地技能与 prompt 镜像。

受管 prompt 行为：

- `.codex/prompts/` 现在应被视为“当前 active prompt 树”的受管副本，而不是长期手工维护的 override。
- 每次真实 runner turn 开始前，DeepScientist 都会把 quest 本地 active prompt 树和仓库当前 `src/prompts/` 做比较，并自动修复漂移。
- 如果 active prompt 树与仓库源不同，系统会先把旧树备份到 `.codex/prompt_versions/<backup_id>/`，再写入新的 active 副本。
- 这个运行前同步是针对“本次 turn 实际使用的 quest_root”执行的，所以即使 quest 不在默认 `home/quests` 下面，也仍然会更新。
- 运行时覆盖：`ds daemon --prompt-version latest` 使用当前受管 active prompt；`ds daemon --prompt-version <official_version>` 会优先选择该正式版本号下最新的一份 prompt 备份。
- 如果你不是想用“这个正式版本下最新的一份”，而是想精确回放某一次备份，也仍然可以直接传 `.codex/prompt_versions/` 里的精确目录名。
- 同样的覆盖也支持一次性 CLI run：`ds run --prompt-version <official_version> ...`。

受管 auto-continue 行为：

- `workspace_mode = copilot`
  - 完成当前请求单元后，DeepScientist 通常停驻，等待下一条用户消息或 `/resume`
- `workspace_mode = autonomous`
  - 如果真实外部长任务还没跑起来，就继续用后续 turns 做准备、启动或耐久路由
  - 一旦真实外部长任务已经在跑，auto-continue 就切成低频巡检，默认大约每 `240` 秒一轮
- auto-continue prompt 现在还会带上一个紧凑的 resume spine：最近用户消息、最近 assistant checkpoint、最近 run 摘要、少量 memory cues，以及当前 `bash_exec` 状态

### Connector policy

这一组不是单个 connector 的凭据，而是所有连接器共享的全局行为。

**`connectors.auto_ack`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Auto-ack incoming messages`
- 作用：收到 connector 消息后，先回一条“已收到”式短确认。

**`connectors.milestone_push`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Push milestones`
- 作用：允许里程碑、决策、进度更新主动推送到已启用连接器。

**`connectors.direct_chat_enabled`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Enable direct chat`
- 作用：允许 connector 私聊直接驱动项目。

### Cloud link

这一组是可选远端协调能力，不是本地核心路径。

**`cloud.enabled`**

- 类型：`boolean`
- 默认值：`false`
- 页面标签：`Enable cloud link`
- 作用：开启可选的 cloud link 路径。
- 推荐：本地优先部署保持关闭。

**`cloud.base_url`**

- 类型：`string`
- 默认值：`https://deepscientist.cc`
- 页面标签：`Cloud base URL`
- 作用：云服务基础地址。

**`cloud.token`**

- 类型：`string | null`
- 默认值：`null`
- 页面标签：`Cloud token`
- 作用：直接写入的云认证 token。
- 注意事项：共享环境更推荐使用 `cloud.token_env`。

**`cloud.token_env`**

- 类型：`string`
- 默认值：`DEEPSCIENTIST_TOKEN`
- 页面标签：`Cloud token env var`
- 作用：声明环境变量名，让运行时从环境变量中读取 token。

**`cloud.verify_token_on_start`**

- 类型：`boolean`
- 默认值：`false`
- 页面标签：`Verify token on start`
- 作用：daemon 启动时检查 cloud token 是否有效。
- 风险：如果开启，错误凭据会让启动更早失败。

**`cloud.sync_mode`**

- 类型：`string`
- 默认值：`disabled`
- 允许值：`disabled`、`pull`、`push`、`bidirectional`
- 页面标签：`Cloud sync mode`
- 作用：声明整体云同步方向。

### ACP bridge

这是兼容 ACP 风格外部消费者的附加配置。

**`acp.compatibility_profile`**

- 类型：`string`
- 默认值：`deepscientist-acp-compat/v1`
- 页面标签：`Compatibility profile`
- 作用：给外部 ACP 消费端看的兼容配置名。

**`acp.events_transport`**

- 类型：`string`
- 默认值：`rest-poll`
- 允许值：`rest-poll`、`sse`
- 页面标签：`Events transport`
- 作用：ACP 风格事件的对外传输方式。

**`acp.sdk_bridge_enabled`**

- 类型：`boolean`
- 默认值：`false`
- 页面标签：`Enable SDK bridge`
- 作用：允许通过 ACP SDK 模块做桥接。

**`acp.sdk_module`**

- 类型：`string`
- 默认值：`acp`
- 页面标签：`SDK module`
- 作用：启用 SDK bridge 时，用于导入桥接实现的 Python 模块名。

## `runners.yaml`

### 摘要

`runners.yaml` 定义项目实际由哪个 runner 执行，以及 runner 的模型默认值、审批策略、沙箱策略和失败重试策略。在当前开源版本中：

- `codex`：主路径，默认启用。
- `claude`：TODO / 预留条目，默认禁用，暂时不能运行。

### 结构

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: ""
  model: gpt-5.4
  model_reasoning_effort: xhigh
  approval_policy: never
  sandbox_mode: danger-full-access
  retry_on_failure: true
  retry_max_attempts: 5
  retry_initial_backoff_sec: 1.0
  retry_backoff_multiplier: 2.0
  retry_max_backoff_sec: 8.0
  mcp_tool_timeout_sec: 180000
  env: {}
claude:
  enabled: false
  binary: claude
  config_dir: ~/.claude
  model: inherit
  model_reasoning_effort: ""
  env: {}
  status: reserved_todo
```

### 页面可编辑字段

**`enabled`**

- 类型：`boolean`
- 默认值：`codex=true`，`claude=false`
- 页面标签：`Enabled`
- 作用：决定这个 runner 是否可被选中与实际执行。

**`binary`**

- 类型：`string`
- 默认值：`codex` 或 `claude`
- 页面标签：`Binary`
- 作用：启动 runner 时使用的命令名或绝对路径。
- `Test` 行为：检查该二进制是否在 `PATH` 上。
- `codex` 的解析顺序：环境变量覆盖、显式路径、本机 `PATH`、最后才是 bundled fallback。
- 临时使用说明：你也可以直接用 `ds --codex /absolute/path/to/codex` 临时覆盖这里的设置。
- 首次使用说明：DeepScientist 不会替你完成 Codex 认证。第一次运行 `ds` 前，必须先确保 `codex --login`（或 `codex`）已经成功完成。
- 修复说明：如果执行 `npm install -g @researai/deepscientist` 之后 bundled Codex 依赖仍然缺失，请显式安装 `npm install -g @openai/codex`。

**`config_dir`**

- 类型：`string`
- 默认值：`~/.codex` 或 `~/.claude`
- 页面标签：`Config directory`
- 作用：runner 的全局配置目录，通常存放认证和全局配置。

**`profile`**

- 类型：`string`
- 默认值：`""`
- 页面标签：`Codex profile`
- 作用：可选的 Codex profile 名称，会直接透传为 `codex --profile <name>`。
- 当你的 Codex CLI 已经配置成 MiniMax、GLM、火山方舟、阿里百炼或其他 provider-backed 路径时，就在这里填写。
- 临时使用说明：如果你不想持久化写配置，也可以保持这里为空，直接使用 `ds --codex-profile <name>` 启动。
- 组合使用说明：如果你还想临时指定 Codex 可执行文件，也可以组合成 `ds --codex /absolute/path/to/codex --codex-profile <name>`。

**`model`**

- 类型：`string`
- 默认值：`codex=gpt-5.4`，`claude=inherit`
- 页面标签：`Default model`
- 作用：项目和单次请求没有覆盖时的默认模型。
- 启动说明：DeepScientist 的 Codex 就绪探测会优先使用这里配置的模型。如果你的 Codex 账号无法访问它，DeepScientist 会自动回退到当前 Codex 默认模型，并持久化为 `model: inherit`。
- provider-profile 说明：当 `profile` 已设置时，通常推荐使用 `model: inherit`，让 Codex profile 自己决定 provider 侧模型。

**`model_reasoning_effort`**

- 类型：`string`
- 默认值：`codex=xhigh`
- 页面标签：`Reasoning effort`
- 允许值：`""`、`minimal`、`low`、`medium`、`high`、`xhigh`
- 作用：默认推理强度。
- 推荐：当前仓库的 Codex 默认就是 `xhigh`。
- 兼容性说明：当 DeepScientist 检测到 Codex CLI 低于 `0.63.0` 时，会在启动探测和实际 runner 命令里自动把 `xhigh` 降级成 `high`。这也覆盖了 MiniMax 当前推荐的 `@openai/codex@0.57.0` 路径。

**`approval_policy`**

- 类型：`string`
- 默认值：`never`
- 页面标签：`Approval policy`
- 允许值：`never`、`on-failure`、`on-request`、`untrusted`
- 作用：控制高权限动作如何申请许可。
- 运行说明：launcher 现在默认以 YOLO 模式启动 Codex。若要临时关闭，可显式传 `ds --yolo false`，这会恢复到 `approval_policy=on-request` 与 `sandbox_mode=workspace-write`。

**`sandbox_mode`**

- 类型：`string`
- 默认值：`danger-full-access`
- 页面标签：`Sandbox mode`
- 允许值：`read-only`、`workspace-write`、`danger-full-access`
- 作用：控制 runner 的文件系统/进程访问权限。

**`env`**

- 类型：`mapping<string, string>`
- 默认值：`{}`
- 页面入口：
  - 全局设置：可在 `runners` 结构化表单中直接编辑 `env`
  - 项目设置：`Project settings -> Codex environment`
- 项目设置行为：
  - 点击 `Add` 新增一行环境变量
  - 默认会显示 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`
  - 修改后不会自动保存，需要手动点击 `Save env vars`
  - 空值会被忽略，不会注入到 Codex 进程
- 作用：DeepScientist 启动 Codex run 时，额外传入给 Codex 的环境变量。
- 常见用途：需要 API Key 或自定义 Base URL 的 provider-backed Codex 配置。

**`retry_on_failure`**

- 类型：`boolean`
- 默认值：`true`
- 页面标签：`Retry on failure`
- 作用：遇到失败时是否自动重试当前 turn。

**`retry_max_attempts`**

- 类型：`number`
- 默认值：`5`
- 页面标签：`Max attempts`
- 作用：一个 turn 的最大尝试次数上限。
- 注意事项：DeepScientist 运行时会把该值硬限制在最多 `5`。

**`retry_initial_backoff_sec`**

- 类型：`number`
- 默认值：`1.0`
- 页面标签：`Initial backoff (s)`
- 作用：第一次重试前等待多久。

**`retry_backoff_multiplier`**

- 类型：`number`
- 默认值：`2.0`
- 页面标签：`Backoff multiplier`
- 作用：指数退避倍数。例如 `1s -> 2s -> 4s -> 8s`。

**`retry_max_backoff_sec`**

- 类型：`number`
- 默认值：`8.0`
- 页面标签：`Max backoff (s)`
- 作用：指数退避增长后的最大等待时间上限。

**`status`**

- 类型：`string`
- 默认值：`claude=reserved_todo`
- 页面标签：`Status note`
- 作用：写给操作者的备注，例如 `reserved_todo`、`experimental`、`disabled_by_policy`。

### 配置文件补充字段

这些字段存在于 `runners.yaml`，但不一定都在页面上显式强调。

**`mcp_tool_timeout_sec`**

- 类型：`number`
- 默认值：`180000`
- 作用：允许 runner 等待较长时间的 MCP 工具调用，例如耗时较久的 `bash_exec(await)`。

**`env`**

- 类型：`mapping[string, string]`
- 默认值：`{}`
- 页面位置：Runner 卡片底部的环境变量编辑器。
- 作用：只对该 runner 注入的环境变量覆盖。

### 常见建议

- 第一版部署一般保持 `codex.enabled: true`、`claude.enabled: false`。
- 当前版本不要把 `default_runner` 从 `codex` 改走。
- 如果你不希望任何自动审批，才把 `approval_policy` 调成更严格模式。
- 如果项目经常需要长时间工具调用，不要随意把 `mcp_tool_timeout_sec` 改小。

## `connectors.yaml`

### 摘要

`connectors.yaml` 负责 QQ、Telegram、Discord、Slack、Feishu / Lark、WhatsApp 的启用、传输方式、凭据、访问控制与少量全局路由策略。当前设计原则是：

- 优先使用无需公网回调的原生传输路径。
- legacy webhook / relay 字段只作为兼容或兜底。
- 所有连接器最终都属于同一个项目交互系统，而不是各自独立的一套消息逻辑。

### 顶层路由字段

**`_routing.primary_connector`**

- 类型：`string | null`
- 默认值：`null`
- 作用：指定一个首选连接器，用于“主路径优先”的推送策略。

**`_routing.artifact_delivery_policy`**

- 类型：`string`
- 默认值：`fanout_all`
- 允许值：`fanout_all`、`primary_only`、`primary_plus_local`
- 作用：决定 `artifact` 交互消息在 connector 之间如何分发。

### 所有连接器共享的通用访问控制字段

以下字段会在多个 connector 中重复出现：

**`dm_policy`**

- 类型：`string`
- 常见值：`pairing`、`allowlist`、`open`、`disabled`
- 作用：控制私聊是自动配对、白名单、完全开放还是禁用。

**`allow_from`**

- 类型：`list[string]`
- 作用：允许私聊发送消息的用户 ID 列表。
- 提示：使用 `*` 可以表达开放模式。

**`group_policy`**

- 类型：`string`
- 常见值：`allowlist`、`open`、`disabled`
- 作用：控制群聊是否开放或受白名单约束。

**`group_allow_from`**

- 类型：`list[string]`
- 作用：群内允许的发送者 ID 列表。

**`groups`**

- 类型：`list[string]`
- 作用：允许的目标群组或频道 ID 列表。

**`auto_bind_dm_to_active_quest`**

- 类型：`boolean`
- 默认值：大多数 connector 为 `true`
- 作用：私聊默认自动跟随当前活跃项目。

### `telegram`

摘要：适合私聊驱动，推荐 `polling`，不需要公网回调。

推荐路径：

- `enabled: true`
- `transport: polling`
- 提供 `bot_token`

关键字段：

**`transport`**

- 类型：`string`
- 默认值：`polling`
- 允许值：`polling`、`legacy_webhook`、`relay`
- 作用：选择轮询、旧式 webhook 或 relay。

**`bot_name`**

- 类型：`string`
- 默认值：`DeepScientist`
- 作用：本地显示名称。

**`bot_token`**

- 类型：`string | null`
- 作用：Telegram Bot API token。
- 获取方式：BotFather。
- 配置文件补充字段：`bot_token_env` 可用环境变量注入 token。

**`command_prefix`**

- 类型：`string`
- 默认值：`/`
- 作用：connector 命令前缀，例如 `/use`、`/status`。

**`require_mention_in_groups`**

- 类型：`boolean`
- 默认值：`true`
- 作用：群聊中必须明确 mention 机器人才处理。

legacy / relay 字段：

- `webhook_secret`
- `public_callback_url`
- `relay_url`
- `relay_auth_token`

说明：只有在你明确保留 callback 或 sidecar relay 路径时才需要填写这些字段。

### `discord`

摘要：推荐 `gateway`，不建议把公网 interaction callback 作为主路径。

关键字段：

**`transport`**

- 类型：`string`
- 默认值：`gateway`
- 允许值：`gateway`、`legacy_interactions`、`relay`

**`bot_token`**

- 类型：`string | null`
- 作用：Discord Gateway 与 REST API 的凭据。
- 配置文件补充字段：`bot_token_env`

**`application_id`**

- 类型：`string | null`
- 作用：Discord 应用 ID，用于 richer routing 和后续扩展。

**`guild_allowlist`**

- 类型：`list[string]`
- 作用：允许使用该 bot 的 guild 白名单。

**`require_mention_in_groups`**

- 类型：`boolean`
- 默认值：`true`
- 作用：只在被 mention 时响应 guild 消息。

legacy 字段：

- `public_key`
- `public_interactions_url`
- `relay_url`
- `relay_auth_token`

### `slack`

摘要：推荐 `socket_mode`，这是当前无需公网回调的主路径。

关键字段：

**`transport`**

- 类型：`string`
- 默认值：`socket_mode`
- 允许值：`socket_mode`、`legacy_events_api`、`relay`

**`bot_token`**

- 类型：`string | null`
- 作用：Slack Bot User OAuth Token。
- 配置文件补充字段：`bot_token_env`

**`app_token`**

- 类型：`string | null`
- 作用：Socket Mode 所需的 App-Level Token。
- 配置文件补充字段：`app_token_env`

**`bot_user_id`**

- 类型：`string | null`
- 作用：用于 mention 过滤或路由的可选 bot user id。

**`command_prefix`**

- 类型：`string`
- 默认值：`/`

**`require_mention_in_groups`**

- 类型：`boolean`
- 默认值：`true`

legacy 字段：

- `signing_secret`
- `public_callback_url`
- `relay_url`
- `relay_auth_token`

### `feishu`

摘要：推荐 `long_connection`，尽量避免公网 event callback。

关键字段：

**`transport`**

- 类型：`string`
- 默认值：`long_connection`
- 允许值：`long_connection`、`legacy_webhook`、`relay`

**`app_id`**

- 类型：`string | null`
- 作用：飞书 / Lark 应用 ID。

**`app_secret`**

- 类型：`string | null`
- 作用：应用密钥，用于 token exchange。
- 配置文件补充字段：`app_secret_env`

**`api_base_url`**

- 类型：`string`
- 默认值：`https://open.feishu.cn`
- 作用：直连 API 的基础地址。

**`require_mention_in_groups`**

- 类型：`boolean`
- 默认值：`true`

legacy 字段：

- `verification_token`
- `encrypt_key`
- `public_callback_url`
- `relay_url`
- `relay_auth_token`

### `whatsapp`

摘要：当前设计目标是 `local_session`，而不是 Meta Cloud webhook 主导。

关键字段：

**`transport`**

- 类型：`string`
- 默认值：`local_session`
- 允许值：`local_session`、`legacy_meta_cloud`、`relay`

**`auth_method`**

- 类型：`string`
- 默认值：`qr_browser`
- 允许值：`qr_browser`、`pairing_code`、`qr_terminal`
- 作用：本地会话认证方式。

**`session_dir`**

- 类型：`string`
- 默认值：`~/.deepscientist/connectors/whatsapp`
- 作用：本地 WhatsApp 会话状态目录。

**`command_prefix`**

- 类型：`string`
- 默认值：`/`

legacy Meta Cloud 字段：

- `provider`
- `access_token`
- `phone_number_id`
- `business_account_id`
- `verify_token`
- `api_base_url`
- `api_version`
- `public_callback_url`
- `relay_url`
- `relay_auth_token`

其中：

- `access_token` 可用 `access_token_env`
- `verify_token` 可用 `verify_token_env`

### `qq`

摘要：QQ 在 DeepScientist 中是一级 connector，主路径就是 `gateway_direct`，不需要公网 callback。

快速上手：参见 [《03 QQ 连接器指南：如何用 QQ 与 DeepScientist 沟通》](./03_QQ_CONNECTOR_GUIDE.md)。

推荐路径：

- `enabled: true`
- `transport: gateway_direct`
- 配置 `app_id`、`app_secret`
- 保存后，让用户先给 bot 发一条私聊消息，系统自动检测并写入 `main_chat_id`

关键字段：

**`transport`**

- 类型：`string`
- 默认值：`gateway_direct`
- 页面状态：只读
- 作用：QQ 的 transport 在当前实现中固定为内置 gateway direct。

**`bot_name`**

- 类型：`string`
- 默认值：`DeepScientist`
- 作用：QQ 连接器在本地 UI 与消息中的显示名。

**`app_id`**

- 类型：`string | null`
- 作用：腾讯 QQ Bot App ID。

**`app_secret`**

- 类型：`string | null`
- 作用：换取 access token 并发起直连发送。
- 配置文件补充字段：`app_secret_env`

**`main_chat_id`**

- 类型：`string | null`
- 页面标签：`Detected OpenID`
- 页面状态：只读
- 作用：系统在第一次收到用户私聊消息后自动回填的 `openid` 或 `group_openid`。
- 注意事项：这不是让你手填的字段，而是运行时发现值。

**`require_at_in_groups`**

- 类型：`boolean`
- 默认值：`true`
- 作用：群聊里要求 @ 机器人后才处理。

**`gateway_restart_on_config_change`**

- 类型：`boolean`
- 默认值：`true`
- 作用：QQ 凭据或目标变化后，自动重启本地 gateway worker。

**`command_prefix`**

- 类型：`string`
- 默认值：`/`

**`auto_bind_dm_to_active_quest`**

- 类型：`boolean`
- 默认值：`true`
- 作用：QQ 私聊默认跟随最新活跃项目。

### QQ 里程碑媒体策略

当前推荐的 QQ 策略是“文本优先”。
自动媒体发送应当非常克制，并且只绑定少量高价值里程碑：

- 主实验摘要 PNG：通常开启
- 分析活动聚合摘要 PNG：通常开启
- 每个 slice 的 PNG：通常关闭
- 最终论文 PDF：通常开启
- 实验性文件上传通道：通常关闭

这些设置的目的，是让 QQ 保持清晰、克制，而不是把 QQ 当作默认文件浏览器。

**`auto_send_main_experiment_png`**

- 类型：`boolean`
- 默认值：`true`
- 作用：真实主实验完成后，允许自动发送一张里程碑摘要 PNG。

**`auto_send_analysis_summary_png`**

- 类型：`boolean`
- 默认值：`true`
- 作用：在有意义的分析活动里程碑时，允许自动发送一张聚合摘要 PNG。

**`auto_send_slice_png`**

- 类型：`boolean`
- 默认值：`false`
- 作用：允许自动发送每个分析 slice 的图片。
- 建议：通常保持关闭，除非你明确希望逐 slice 推送。

**`auto_send_paper_pdf`**

- 类型：`boolean`
- 默认值：`true`
- 作用：论文 bundle 稳定就绪时，允许自动发送一次最终论文 PDF。

**`enable_file_upload_experimental`**

- 类型：`boolean`
- 默认值：`false`
- 作用：启用实验性的 QQ 媒体 / 文件上传通道。
- 建议：除非你在明确测试 QQ 上传支持，否则保持关闭。

## `plugins.yaml`

### 摘要

`plugins.yaml` 管理外部插件发现与信任策略，不负责插件本身的运行时状态。

### 结构

```yaml
load_paths:
  - ~/DeepScientist/plugins
enabled: []
disabled: []
allow_unsigned: false
```

### 参数

**`load_paths`**

- 类型：`list[string]`
- 默认值：`[~/DeepScientist/plugins]`
- 页面标签：`Load paths`
- 作用：扫描本地插件包的目录列表。

**`enabled`**

- 类型：`list[string]`
- 默认值：`[]`
- 页面标签：`Force-enable plugin ids`
- 作用：显式启用某些插件 ID。

**`disabled`**

- 类型：`list[string]`
- 默认值：`[]`
- 页面标签：`Force-disable plugin ids`
- 作用：即使被发现也强制禁用。

**`allow_unsigned`**

- 类型：`boolean`
- 默认值：`false`
- 页面标签：`Allow unsigned plugins`
- 作用：允许未通过签名 / 信任检查的插件被加载。
- 风险：只在你完全信任插件来源时开启。

## `mcp_servers.yaml`

### 摘要

这个文件管理外部 MCP 服务。它不控制内置 `memory`、`artifact`、`bash_exec`，也不保存项目内部工具调用历史。

### 结构

```yaml
servers:
  browser:
    enabled: true
    transport: stdio
    command:
      - npx
      - "@example/browser-mcp"
    url: ""
    cwd: ""
    env: {}
```

### 每个 server 条目的参数

**`servers.<server_id>.enabled`**

- 类型：`boolean`
- 默认值：新卡片默认为 `false`
- 作用：只有启用的外部 MCP 才会暴露给项目或 runner。

**`servers.<server_id>.transport`**

- 类型：`string`
- 默认值：`stdio`
- 允许值：`stdio`、`streamable_http`、`http`、`sse`
- 作用：定义这个 MCP 服务通过本地子进程还是远程 HTTP/SSE 暴露。

**`servers.<server_id>.command`**

- 类型：`list[string]`
- 默认值：`[]`
- 作用：`stdio` 模式下的启动命令。
- 页面提示：可以逐行输入，也可以逗号分隔。

**`servers.<server_id>.url`**

- 类型：`string`
- 默认值：`""`
- 作用：HTTP / SSE 类传输的服务 URL。
- 注意事项：`stdio` 纯本地模式通常留空。

**`servers.<server_id>.cwd`**

- 类型：`string`
- 默认值：`""`
- 作用：启动本地 `stdio` MCP 进程时的工作目录。

**`servers.<server_id>.env`**

- 类型：`mapping[string, string]`
- 默认值：`{}`
- 作用：只对该 MCP 服务注入的环境变量覆盖。

## 校验与测试行为

### `config.yaml`

`Test` 会检查：

- `git` 是否已安装
- `git config user.name` 是否存在
- `git config user.email` 是否存在
- `home` 路径是否存在

### `runners.yaml`

`Test` 会检查：

- 启用的 runner 的 `binary` 是否在 `PATH`
- 禁用的 runner 会被跳过，并给出“skipped”式提示

### `connectors.yaml`

`Validate` 会检查：

- connector 必填凭据是否存在
- transport 与字段是否匹配
- relay 模式是否提供 `relay_url`
- 不同平台的推荐/必要字段是否齐全

`Test` 会尝试做轻量 readiness probe，例如：

- Telegram：`getMe`
- Slack：`auth.test`
- Feishu：tenant token exchange
- QQ：`access_token` + `/gateway` 探测

### `plugins.yaml`

- 没有复杂运行时测试，主要是结构校验。

### `mcp_servers.yaml`

- 当前以结构校验为主；真正的连通性需要看服务本身是否可启动或可访问。

## 推荐起步配置

### 本地单机研究

```yaml
# config.yaml
default_runner: codex
default_locale: en-US
ui:
  host: 0.0.0.0
  port: 20999
  default_mode: both
git:
  auto_checkpoint: true
  auto_push: false
connectors:
  auto_ack: true
  milestone_push: true
  direct_chat_enabled: true
```

### 无公网回调的 connector 思路

- Telegram：`transport: polling`
- Discord：`transport: gateway`
- Slack：`transport: socket_mode`
- Feishu：`transport: long_connection`
- WhatsApp：`transport: local_session`
- QQ：固定 `gateway_direct`

## 相关文档

- [02 Start Research 参考：如何填写科研启动合同](./02_START_RESEARCH_GUIDE.md)
- [05 TUI 使用指南：如何使用终端界面](./05_TUI_GUIDE.md)
- [06 运行时与 Canvas：理解运行流程和图结构](./06_RUNTIME_AND_CANVAS.md)
