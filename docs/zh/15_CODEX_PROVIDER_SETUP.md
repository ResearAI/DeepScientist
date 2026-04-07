# 15 Codex Provider 配置

DeepScientist 不会为 MiniMax、GLM、火山方舟、阿里百炼单独实现一套 provider 适配器。

它复用的是你本机已经能正常工作的 Codex CLI 配置。

推荐顺序始终是：

1. 先让 Codex 自己能工作
2. 确认 `codex` 或 `codex --profile <name>` 在终端里可用
3. 运行 `ds doctor`
4. 再运行 `ds` 或 `ds --codex-profile <name>`

## 三种推荐使用方式

### 1. 默认 OpenAI 登录路径

如果你的 Codex CLI 走的是标准 OpenAI 登录流，就用这一条。

```bash
codex login
ds doctor
ds
```

### 2. 临时使用 provider profile

如果你已经有一个可用的 Codex profile，例如 `m27`、`glm`、`ark`、`bailian`，最简单的方式就是直接在启动 `ds` 时透传它。

```bash
codex --profile m27
ds doctor --codex-profile m27
ds --codex-profile m27
```

如果你这一轮要强制指定某一个 Codex 可执行文件，也可以这样：

```bash
ds doctor --codex /absolute/path/to/codex --codex-profile m27
ds --codex /absolute/path/to/codex --codex-profile m27
```

这是最简单的路径。只是临时试用某个 provider 时，不需要先改 `runners.yaml`。

### 3. 持久化 provider profile

如果你希望 DeepScientist 之后默认就走这个 profile，可以写进 `runners.yaml`：

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: minimax
  model: inherit
  model_reasoning_effort: xhigh
  approval_policy: on-request
  sandbox_mode: workspace-write
```

注意：

- 对 provider-backed 的 Codex profile，建议优先使用 `model: inherit`
- 除非你非常确定该 provider 接受你要显式传入的模型名，否则不要再额外硬写一个模型
- DeepScientist 现在会在 `.ds/codex-home` 下启动一个隔离的运行时 home，但会先继承你配置的 `~/.codex` 里的 auth、config、skills、agents 与 prompts

## Provider 一览

| Provider | 官方文档 | 是否需要 Codex 登录 | DeepScientist 应该怎么用 |
|---|---|---|---|
| OpenAI | 正常 Codex 配置即可 | 是 | 不需要 profile，直接 `ds` |
| MiniMax | [MiniMax Codex CLI](https://platform.minimaxi.com/docs/coding-plan/codex-cli) | 否 | 使用你自己的 Codex profile，例如 `ds --codex-profile m27` |
| GLM | [GLM Coding Plan：其他工具](https://docs.bigmodel.cn/cn/coding-plan/tool/others) | 否 | 使用一个指向 GLM coding endpoint 的 Codex profile |
| 火山方舟 | [Ark Coding Plan 总览](https://www.volcengine.com/docs/82379/1925114?lang=zh) | 否 | 使用一个指向 Ark coding endpoint 的 Codex profile |
| 阿里百炼 | [百炼 Coding Plan：其他工具](https://help.aliyun.com/zh/model-studio/other-tools-coding-plan) | 否 | 使用一个指向 Bailian coding endpoint 的 Codex profile |

## OpenAI

### 需要准备什么

- 正常安装的 Codex CLI
- 已成功执行过一次 `codex login`，或者在 `codex` 交互界面里完成首次认证

### DeepScientist 命令

```bash
ds doctor
ds
```

### 持久化 runner 配置

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: ""
  model: gpt-5.4
```

## MiniMax

MiniMax 是最典型的 profile 模式。它的官方 Codex CLI 文档直接给了自定义 provider 的配置方式，并明确写了 `requires_openai_auth = false`。

官方文档：

- <https://platform.minimaxi.com/docs/coding-plan/codex-cli>

### 已验证的兼容性说明

按 2026-04-04 对 MiniMax 官方 Codex CLI 页面和本地兼容性测试的核对结果：

- MiniMax 官方 Codex CLI 页面当前建议使用 `@openai/codex@0.57.0`
- MiniMax 当前应使用的 Coding Plan endpoint 是 `https://api.minimaxi.com/v1`
- MiniMax 官方页面示例 profile 名是 `m21`，但 profile 名本身只是本地别名；本仓库统一用 `m27` 作为示例名
- MiniMax 官方页面当前给出的 `codex-MiniMax-*` 模型名，在本地使用你提供的 key 实测并不能稳定通过 Codex CLI
- 本地实测 DeepScientist 可稳定跑通的组合包括 `MiniMax-M2.7` + `m27` + Codex CLI `0.57.0`，以及 `MiniMax-M2.5` + `m25` + Codex CLI `0.57.0`
- 当前最新版 `@openai/codex` 和 MiniMax 官方文档并不能稳定直接对齐

如果你现在要走最稳的 DeepScientist + MiniMax 路径，建议直接使用 Codex CLI `0.57.0`。

### 需要准备什么

- 已安装 Codex CLI `0.57.0`
- 已创建 MiniMax `Coding Plan Key`
- 在启动 Codex 和 DeepScientist 的 shell 中可见的 `MINIMAX_API_KEY`
- 如果你要单独在终端里验证 `codex --profile <name>`，当前 shell 需要先清理 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`
- `~/.codex/config.toml` 中已经配置好的 Codex profile

### 安装 Codex CLI `0.57.0`

最直接的方式是把全局 Codex 安装固定到 `0.57.0`：

```bash
npm install -g @openai/codex@0.57.0
codex --version
```

预期输出：

```text
codex-cli 0.57.0
```

如果你还想保留另一个 Codex 版本，也可以单独写一个 wrapper 脚本，再把 `runners.codex.binary` 指向那个绝对路径。

现在如果 DeepScientist 在启动时检测到 MiniMax profile，但当前 `codex` 版本不是 `0.57.0`，在交互式终端里会主动提示是否自动安装 `@openai/codex@0.57.0`。

### Codex 侧配置

请使用 `https://api.minimaxi.com/v1`，不要用 `https://api.minimax.io/v1`。

MiniMax 官方文档要求在配置前先清理 OpenAI 环境变量：

```bash
unset OPENAI_API_KEY
unset OPENAI_BASE_URL
export MINIMAX_API_KEY="..."
```

如果你是在终端里单独验证 `codex --profile <name>`，就按上面的方式处理。
如果你走的是 DeepScientist 路径，那么当所选 provider 明确写了 `requires_openai_auth = false` 时，DeepScientist 现在会在 startup probe 和真实 runner 执行时自动剥离 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。

MiniMax 官方页面示例 profile 名是 `m21`。由于 profile 名只是本地别名，本仓库统一改写成 `m27`。

先说明差异：

- 官方页面当前展示的是 `codex-MiniMax-M2.5`
- 但本地实测里，直接请求 MiniMax API 能稳定跑通的是 `MiniMax-M2.7` 和 `MiniMax-M2.5`
- 可复现的 DeepScientist 路径是：`MiniMax-M2.7` 配 `m27`，以及 `MiniMax-M2.5` 配 `m25`
- 对 `m25` 这条路径，请使用 `MiniMax-M2.5`，不要写成 `codex-MiniMax-M2.5`

因此，下面给的是当前 DeepScientist 推荐配置：

```toml
[model_providers.minimax]
name = "MiniMax Chat Completions API"
base_url = "https://api.minimaxi.com/v1"
env_key = "MINIMAX_API_KEY"
wire_api = "chat"
requires_openai_auth = false
request_max_retries = 4
stream_max_retries = 10
stream_idle_timeout_ms = 300000

[profiles.m27]
model = "MiniMax-M2.7"
model_provider = "minimax"
```

如果你想走同样的 DeepScientist 路径但使用 `m25`，保持上面的 provider 配置不变，再把 profile 写成：

```toml
[profiles.m25]
model = "MiniMax-M2.5"
model_provider = "minimax"
```

DeepScientist 现在对它的支持方式是：

- 如果你使用的是这类 profile-only MiniMax 配置，再配合 Codex CLI `0.57.0`，DeepScientist 会在自己的 probe / 运行时临时 `config.toml` 副本里，把所选 profile 的 `model_provider` 和 `model` 自动提升到顶层
- 对 provider-backed 的 MiniMax profile，DeepScientist 会强制使用 `model: inherit`，避免再被硬编码的 OpenAI 模型覆盖
- 当 `requires_openai_auth = false` 时，DeepScientist 会自动移除冲突的 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`
- 这意味着即使终端里原样执行 `codex --profile m27` 还会失败，DeepScientist 也可以先兼容跑起来

如果你还希望终端里的 `codex --profile <name>` 也直接可用，请使用显式顶层兼容写法：

```toml
model = "MiniMax-M2.7"
model_provider = "minimax"
approval_policy = "never"
sandbox_mode = "workspace-write"

[model_providers.minimax]
name = "MiniMax Chat Completions API"
base_url = "https://api.minimaxi.com/v1"
env_key = "MINIMAX_API_KEY"
wire_api = "chat"
requires_openai_auth = false
request_max_retries = 4
stream_max_retries = 10
stream_idle_timeout_ms = 300000

[profiles.m27]
model = "MiniMax-M2.7"
model_provider = "minimax"
```

然后执行：

```bash
codex --profile m27
```

### DeepScientist 命令

```bash
ds doctor --codex-profile m27
ds --codex-profile m27
```

### 持久化 runner 配置

```yaml
codex:
  enabled: true
  binary: /tmp/codex057-wrapper
  config_dir: ~/.codex
  profile: m27
  model: inherit
  model_reasoning_effort: high
```

如果你已经把全局 `codex` 固定到 `0.57.0`，也可以把 `binary` 写回 `codex`。这里写绝对路径只是为了明确避免误用系统里其他版本的 Codex。

如果你不想把这个路径持久化写进 `runners.yaml`，也可以保留 `binary: codex`，然后在启动时临时加：

```bash
ds --codex /absolute/path/to/codex --codex-profile m27
```

DeepScientist 现在会为 MiniMax 的 `0.57.0` 路径额外做两层兼容：

- 当检测到旧版 Codex CLI 不支持 `xhigh` 时，自动把 `xhigh` 降级成 `high`
- 当检测到 MiniMax 使用 profile-only 的 `model_provider` / `model` 配置形态时，在临时 DeepScientist Codex home 里自动补齐顶层字段
- 当 provider 明确声明 `requires_openai_auth = false` 时，自动移除冲突的 `OPENAI_*` 认证环境变量

## GLM

GLM 的官方文档把 Coding Plan 描述成 OpenAI-compatible 的 coding endpoint，而不是单独的 Codex 登录流程。

官方文档：

- <https://docs.bigmodel.cn/cn/coding-plan/tool/others>
- <https://docs.bigmodel.cn/cn/coding-plan/faq>

### 官方给出的 provider 关键值

- Base URL：`https://open.bigmodel.cn/api/coding/paas/v4`
- API Key：你的 GLM Coding Plan key
- Model：文档中明确写了 `GLM-4.7`，部分场景也支持 `GLM-5`

### 推荐做法

GLM 当前没有像 MiniMax 那样单独给出一篇 Codex CLI 专页。对 DeepScientist 来说，最稳的做法是：

1. 在 `~/.codex/config.toml` 中创建一个指向上面 GLM coding endpoint 的 Codex profile
2. 先确保 `codex --profile glm` 在终端里能工作
3. 再让 DeepScientist 复用同一个 profile

### DeepScientist 命令

```bash
ds doctor --codex-profile glm
ds --codex-profile glm
```

### 持久化 runner 配置

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: glm
  model: inherit
```

## 火山方舟

火山方舟的 Coding Plan 官方文档明确列出了 Codex CLI。

官方文档：

- <https://www.volcengine.com/docs/82379/1925114?lang=zh>

### 官方给出的 provider 关键值

- OpenAI-compatible Base URL：`https://ark.cn-beijing.volces.com/api/coding/v3`
- 支持的 coding 模型：`doubao-seed-code-preview-latest`、`ark-code-latest`
- 必须使用 Coding Plan 的 key 和对应的 Coding Plan endpoint

### 推荐做法

先创建一个指向 Ark coding endpoint 的 Codex profile，并先验证：

```bash
codex --profile ark
```

然后再启动 DeepScientist：

```bash
ds doctor --codex-profile ark
ds --codex-profile ark
```

### 持久化 runner 配置

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: ark
  model: inherit
```

## 阿里百炼

阿里百炼的 Coding Plan 官方文档也是 OpenAI-compatible endpoint 路径。它特别强调：必须使用 Coding Plan 专属 key 和 endpoint，而不是普通平台 endpoint。

官方文档：

- <https://help.aliyun.com/zh/model-studio/other-tools-coding-plan>
- <https://help.aliyun.com/zh/model-studio/coding-plan-faq>

### 官方给出的 provider 关键值

- OpenAI-compatible Base URL：`https://coding.dashscope.aliyuncs.com/v1`
- API Key：Coding Plan 专属 key，通常形如 `sk-sp-...`
- Model：请以当前百炼 Coding Plan 概览页支持的模型为准

### 推荐做法

先创建一个指向 Bailian Coding Plan endpoint 的 Codex profile，并先验证：

```bash
codex --profile bailian
```

然后再启动 DeepScientist：

```bash
ds doctor --codex-profile bailian
ds --codex-profile bailian
```

### 持久化 runner 配置

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: bailian
  model: inherit
```

## 一份统一的排障清单

如果 provider-backed profile 在 DeepScientist 里还是失败：

1. 先手动运行 `codex --profile <name>`
2. 确认 provider API key 在同一个 shell 中可见
3. 确认 Base URL 使用的是 Coding Plan endpoint，而不是普通通用 API endpoint
4. DeepScientist 里优先保持 `model: inherit`
5. 运行 `ds doctor --codex-profile <name>`
6. 最后再运行 `ds --codex-profile <name>`
