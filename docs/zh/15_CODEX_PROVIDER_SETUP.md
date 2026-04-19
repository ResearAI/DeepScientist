# 15 Codex Provider 配置

DeepScientist 不会为 MiniMax、GLM、火山方舟、阿里百炼等 provider 额外维护一套独立适配层。

它复用的是你本机已经能正常工作的 Codex CLI。

正确的理解方式是：

1. 先让 `codex` 自己能工作
2. 再确认同一套配置在终端里可用
3. 然后运行 `ds doctor`
4. 最后再运行 `ds` 或 `ds --codex-profile <name>`

如果 Codex 本身还没工作，先修 DeepScientist 是错误顺序。

如果你要配置另外两条内建 runner，请同时参考：

- [24 Claude Code 配置指南](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
- [25 OpenCode 配置指南](./25_OPENCODE_PROVIDER_SETUP.md)

## 哪些文件最重要

Codex CLI 默认读取 `~/.codex/` 下面的本地状态。

最重要的文件是：

- `~/.codex/config.toml`
  - provider、model、profile、feature 等主要配置
- `~/.codex/auth.json`
  - 当你走标准 OpenAI 登录流时，`codex login` 通常会写这个文件
- `~/.codex/history.jsonl`
  - 本地会话历史，不是配置必需项

常用检查命令：

```bash
ls -la ~/.codex
sed -n '1,220p' ~/.codex/config.toml
codex --version
codex --help
codex exec --help
```

## 推荐配置顺序

建议严格按这个顺序走：

1. 安装 Codex CLI，并确认正在使用的二进制就是你想要的那个
2. 准备 `~/.codex/config.toml`
3. 直接验证 `codex` 或 `codex --profile <name>`
4. 用 `ds doctor` 验证 DeepScientist
5. 最后再让 DeepScientist 复用这套 Codex 配置

## 第一步：先确认 Codex binary

先检查当前实际在用哪个 Codex：

```bash
which codex
codex --version
```

如果你必须使用特定版本或特定路径的 Codex，可执行文件路径记下来，后续通过 `--codex` 传给 DeepScientist。

例如：

```bash
ds doctor --codex /absolute/path/to/codex --codex-profile glm
ds --codex /absolute/path/to/codex --codex-profile glm
```

## 第二步：理解 Codex 两种常见配置形态

### A. OpenAI 登录形态

如果你的 Codex 走标准 OpenAI 登录流，通常用这一种。

典型流程：

```bash
codex login
codex
```

这种情况下，`~/.codex/auth.json` 往往已经存在，`config.toml` 可以很精简。

最小示例：

```toml
model = "gpt-5.4"
model_reasoning_effort = "high"

[projects."/absolute/path/to/your/project"]
trust_level = "trusted"
```

### B. `config.toml` 显式 provider 形态

如果你要把 Codex 指向一个自定义 provider、代理或兼容网关，通常走这一种。

常见写法之一：

```toml
model_provider = "myprovider"
model = "gpt-5.4"
model_reasoning_effort = "xhigh"

[model_providers.myprovider]
name = "My Provider"
base_url = "https://example.com/codex"
wire_api = "responses"
experimental_bearer_token = "YOUR_TOKEN_HERE"
requires_openai_auth = true
```

另一种常见写法是不用固定 bearer token，而是通过环境变量取 key：

```toml
[model_providers.myprovider]
name = "My Provider"
base_url = "https://example.com/codex"
wire_api = "chat"
env_key = "MYPROVIDER_API_KEY"
requires_openai_auth = false
```

然后在启动 Codex 或 DeepScientist 的 shell 里导出环境变量：

```bash
export MYPROVIDER_API_KEY="..."
```

## 第三步：理解 `config.toml` 里最关键的字段

### 顶层字段

常见需要改的顶层字段包括：

- `model_provider`
  - 默认使用哪个 provider block
- `model`
  - 默认发送哪个模型名
- `model_reasoning_effort`
  - 例如 `medium`、`high`、`xhigh`
- `service_tier`
  - 可选，某些 provider 会用到

### provider block 字段

位于 `[model_providers.<name>]` 下：

- `name`
  - 人类可读名称
- `base_url`
  - Codex 实际请求的 provider endpoint
- `wire_api`
  - 通常是 `responses` 或 `chat`，按 provider 文档来
- `env_key`
  - 如果 API key 从环境变量读取，就写环境变量名
- `experimental_bearer_token`
  - 如果 provider 直接使用固定 bearer token，可写这里
- `requires_openai_auth`
  - provider 是否仍需要 OpenAI 认证形态
- `request_max_retries`
  - 可选，请求重试次数
- `stream_max_retries`
  - 可选，流式重试次数
- `stream_idle_timeout_ms`
  - 可选，流空闲超时

### profile 字段

profile 在 `[profiles.<alias>]` 下定义。

示例：

```toml
[profiles.glm]
model = "GLM-4.7"
model_provider = "glm"
```

然后可以这样调用：

```bash
codex --profile glm
```

### 项目信任

Codex 还会检查项目 trust。

例如：

```toml
[projects."/ssdwork/deepscientist/DeepScientist"]
trust_level = "trusted"
```

如果项目不在 trusted 状态，Codex 运行时可能还会再次确认。

## 第四步：一套最稳妥的 profile 工作流

### 4.1 编辑 `~/.codex/config.toml`

建议先备份原文件：

```bash
cp ~/.codex/config.toml ~/.codex/config.toml.bak
${EDITOR:-vim} ~/.codex/config.toml
```

### 4.2 新增 provider block

通用模板：

```toml
[model_providers.provider_name]
name = "Provider Name"
base_url = "https://provider.example/v1"
wire_api = "chat"
env_key = "PROVIDER_API_KEY"
requires_openai_auth = false
request_max_retries = 4
stream_max_retries = 10
stream_idle_timeout_ms = 300000
```

### 4.3 新增 profile

```toml
[profiles.provider_alias]
model = "provider-model-id"
model_provider = "provider_name"
```

### 4.4 先直接验证 Codex

交互式验证：

```bash
codex --profile provider_alias
```

非交互式 smoke check：

```bash
codex exec --profile provider_alias "Reply with exactly OK."
```

如果这里都还不通，不要先怪 DeepScientist，先把 Codex 自己修通。

## 第五步：把同一套配置映射给 DeepScientist

DeepScientist 推荐三种使用方式。

### 1. 默认 OpenAI 登录路径

```bash
codex login
ds doctor
ds
```

### 2. 临时使用某个 provider profile

```bash
codex --profile glm
codex exec --profile glm "Reply with exactly OK."
ds doctor --codex-profile glm
ds --codex-profile glm
```

### 3. 持久化写入 `runners.yaml`

如果你希望 DeepScientist 默认总是走同一个 Codex profile，可以写进 `runners.yaml`：

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: glm
  model: inherit
  model_reasoning_effort: high
  approval_policy: on-request
  sandbox_mode: workspace-write
```

注意：

- `profile` 一般应该写你本地 Codex profile 的别名，例如 `glm`、`ark`、`bailian`、`m25`、`m27-local`
- 对 provider-backed 的 Codex profile，优先使用 `model: inherit`
- 只有当你非常确定 provider 接受那个显式模型名时，才在 DeepScientist 里硬写 `model:`
- DeepScientist 实际运行 Codex 时会在 `.ds/codex-home` 下构造一个隔离运行时 home，但会先复制你 `~/.codex` 里的 auth、config、skills、agents 和 prompts

## 不改 `config.toml` 的临时覆盖方式

Codex 自己支持 `-c key=value`。

例如：

```bash
codex -c model="gpt-5.4"
codex -c model_provider="yunyi" -c model="gpt-5.4"
codex exec -c model_reasoning_effort="high" "Reply with exactly OK."
```

这很适合临时验证；但如果你希望 DeepScientist 稳定复用，还是推荐把 profile 写进 `~/.codex/config.toml`。

## OpenAI

### 需要准备什么

- 正常可用的 Codex CLI
- 已成功执行 `codex login`
- 能直接运行 `codex` 或 `codex exec "Reply with exactly OK."`

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

官方文档：

- <https://platform.minimaxi.com/docs/coding-plan/codex-cli>

MiniMax 是最典型的 profile 模式。

### 重要兼容性说明

MiniMax 官方 Coding Plan 里的 `MiniMax-M2.7`，当前**并不能稳定作为 Codex 官方兼容路径使用**。

如果你走 MiniMax 官方 Coding Plan + Codex 这条路径，建议直接改用：

- `MiniMax-M2.5`
- profile 别名例如 `m25`
- 如果你想走当前最稳的 MiniMax Coding Plan 路径，建议使用 Codex CLI `0.57.0`

如果你就是想用 `MiniMax-M2.7`，推荐做法是：

- 不要把它当作官方 MiniMax Codex Coding Plan 默认路径
- 而是把 M2.7 通过你本地的 OpenAI-compatible `vllm` 服务暴露出来
- 然后在 `~/.codex/config.toml` 里把 Codex 指向这个本地 `vllm` endpoint

### 推荐的官方 Coding Plan 路径

官方 Coding Plan endpoint 继续使用：

- Base URL：`https://api.minimaxi.com/v1`
- API key 环境变量：`MINIMAX_API_KEY`
- Model：`MiniMax-M2.5`

推荐配置形态：

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

[profiles.m25]
model = "MiniMax-M2.5"
model_provider = "minimax"
```

验证顺序：

```bash
unset OPENAI_API_KEY
unset OPENAI_BASE_URL
export MINIMAX_API_KEY="..."
codex --version
codex --profile m25
codex exec --profile m25 "Reply with exactly OK."
ds doctor --codex-profile m25
ds --codex-profile m25
```

### 如果你坚持使用 MiniMax-M2.7

推荐路径是：通过你本地的 OpenAI-compatible `vllm` 服务来暴露 M2.7。

配置形态示例：

```toml
[model_providers.minimax_local_vllm]
name = "MiniMax M2.7 via local vLLM"
base_url = "http://127.0.0.1:8000/v1"
wire_api = "chat"
requires_openai_auth = false
env_key = "OPENAI_API_KEY"

[profiles.m27-local]
model = "MiniMax-M2.7"
model_provider = "minimax_local_vllm"
```

然后按同样顺序验证：

```bash
export OPENAI_API_KEY="dummy-or-local-token-if-needed"
codex --profile m27-local
codex exec --profile m27-local "Reply with exactly OK."
ds doctor --codex-profile m27-local
ds --codex-profile m27-local
```

### 持久化 runner 配置

如果你走官方 Coding Plan 路径：

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: m25
  model: inherit
  model_reasoning_effort: high
```

如果你走本地 vLLM 的 M2.7 路径：

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: m27-local
  model: inherit
  model_reasoning_effort: high
```

## GLM

官方文档：

- <https://docs.bigmodel.cn/cn/coding-plan/tool/others>
- <https://docs.bigmodel.cn/cn/coding-plan/faq>

当前公开文档里的关键值：

- Base URL：`https://open.bigmodel.cn/api/coding/paas/v4`
- Model：`GLM-4.7` 或其它当前 Coding Plan 支持模型

推荐流程：

1. 在 `~/.codex/config.toml` 里新增 GLM provider block
2. 新增 `[profiles.glm]`
3. 先跑 `codex --profile glm`
4. 再跑 `codex exec --profile glm "Reply with exactly OK."`
5. 再跑 `ds doctor --codex-profile glm`
6. 最后跑 `ds --codex-profile glm`

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

官方文档：

- <https://www.volcengine.com/docs/82379/1925114?lang=zh>

当前公开文档里的关键值：

- Base URL：`https://ark.cn-beijing.volces.com/api/coding/v3`
- 模型：`doubao-seed-code-preview-latest`、`ark-code-latest`

推荐流程：

```bash
codex --profile ark
codex exec --profile ark "Reply with exactly OK."
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

官方文档：

- <https://help.aliyun.com/zh/model-studio/other-tools-coding-plan>
- <https://help.aliyun.com/zh/model-studio/coding-plan-faq>

这里最重要的一点：

- 支持：百炼 **Coding Plan** endpoint 上的 Qwen
- 不支持：普通百炼 / DashScope 平台的 Qwen API

当前公开文档里的关键值：

- Base URL：`https://coding.dashscope.aliyuncs.com/v1`
- key 形态：Coding Plan 专属 key，通常形如 `sk-sp-...`

推荐流程：

```bash
codex --profile bailian
codex exec --profile bailian "Reply with exactly OK."
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

## 一份统一排障清单

如果 provider-backed profile 还是失败：

1. 先检查 `which codex` 和 `codex --version`
2. 检查 `~/.codex/config.toml`
3. 确认 provider block 存在，profile 也确实指向了它
4. 确认 API key 或 bearer token 在当前 shell 里真的可见
5. 确认 Base URL 用的是 Coding Plan / Codex-compatible endpoint，而不是普通平台通用 API
6. 先跑 `codex --profile <name>`
7. 再跑 `codex exec --profile <name> "Reply with exactly OK."`
8. 再跑 `ds doctor --codex-profile <name>`
9. 最后再跑 `ds --codex-profile <name>`

如果 `codex --profile <name>` 还没通，就先修 Codex 自己，不要先怀疑 DeepScientist。
