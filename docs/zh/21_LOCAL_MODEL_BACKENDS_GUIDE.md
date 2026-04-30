# 21 本地模型后端指南：vLLM、Ollama 与 SGLang

这篇文档说明如何把 DeepScientist 接到本地模型后端，重点包括 vLLM、Ollama 和 SGLang。

先分清一个基本事实：

- DeepScientist 不直接调用本地模型服务
- DeepScientist 调用的是 runner CLI：`codex`、`claude`、`opencode`
- 本地模型后端要先被对应 runner CLI 接通，再由 DeepScientist 复用

如果你使用的是 Codex runner，下面的 `/v1/responses` 检查很关键。
如果你使用的是 OpenCode 或 Claude Code runner，请优先看对应 runner 文档里的 Ollama 小节：

- [24 Claude Code 配置指南](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
- [25 OpenCode 配置指南](./25_OPENCODE_PROVIDER_SETUP.md)

最关键的一点只有一句话：

- 当前 Codex CLI 要求 `wire_api = "responses"`
- 只有 `/v1/chat/completions` 能工作还不够
- 在期待 `ds` 或 `ds doctor` 成功之前，必须先验证 `/v1/responses`

同时还有一个现实 fallback：

- 如果你的后端只有 chat 接口，仍然有机会通过 **Codex CLI `0.57.0`** 跑通
- 这条旧路径通常需要使用顶层 `model_provider` / `model`，并把 `wire_api` 设为 `chat`
- DeepScientist 现在会在 Codex 启动探测阶段自动检查这一点；只要发现当前生效 provider 使用的是 `wire_api = "chat"`，就会要求 `codex-cli 0.57.0` 才继续

## 1. DeepScientist 实际依赖的是什么

DeepScientist 并不会直接和 vLLM、Ollama、SGLang 通信。

它真正依赖的是：

- `codex`
- 然后由 `codex` 去调用你在 `~/.codex/config.toml` 里配置的 provider profile

所以真实兼容链路是：

1. 你的本地模型后端
2. Codex profile
3. Codex 启动探测
4. DeepScientist runner

如果第 2 步或第 3 步过不了，DeepScientist 就无法正常启动 Codex runner。

## 2. 当前 Codex 必须知道的限制

在当前 Codex CLI 中：

- 支持 `wire_api = "responses"`
- 不再接受 `wire_api = "chat"`

这意味着：

- `vLLM`：如果 OpenAI-compatible server 暴露了 `/v1/responses`，这是当前最推荐的路径
- `Ollama`：只有在你的版本真的支持 `/v1/responses` 时才建议使用
- `SGLang`：如果你的部署只有 `/v1/chat/completions` 能工作，那么它和最新版 Codex runner 不兼容

## 2.1 支持程度总览

| 后端 | `/v1/chat/completions` | `/v1/responses` | 最新版 Codex | `0.57.0` 回退路径 |
|---|---|---|---|---|
| vLLM | 支持 | 支持 | 支持 | 通常不需要 |
| Ollama | 支持 | 取决于版本 | 只有 `/v1/responses` 正常时才支持 | 如果只有 chat，可以尝试 |
| SGLang | 支持 | 经常缺失或不完整 | chat-only 时不支持 | 可以尝试回退到 `0.57.0` |

## 3. 先直接测试后端

在动 DeepScientist 之前，先直接验证后端。

### 第一步：列模型

```bash
curl http://127.0.0.1:8004/v1/models \
  -H "Authorization: Bearer 1234"
```

你需要从这里拿到一个真实模型名，例如：

```text
/model/gpt-oss-120b
```

### 第二步：测试 chat completions

```bash
curl http://127.0.0.1:8004/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 1234" \
  -d '{
    "model": "/model/gpt-oss-120b",
    "messages": [
      { "role": "user", "content": "Reply with exactly HELLO." }
    ]
  }'
```

如果这一步成功，说明后端至少具备 OpenAI chat-compatible 能力。

### 第三步：测试 Responses API

```bash
curl http://127.0.0.1:8004/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 1234" \
  -d '{
    "model": "/model/gpt-oss-120b",
    "input": "Reply with exactly HELLO."
  }'
```

这一步才是决定性检查。

如果 `/v1/responses` 失败，最新版 Codex CLI 就不能正常使用这个后端 profile。

## 4. 我们在这台服务器上的实际观察

我们已经测试了本机的 `http://127.0.0.1:8004/v1`。

结果是：

- `GET /v1/models` 成功
- `POST /v1/chat/completions` 成功
- `POST /v1/responses` 返回 `500 Internal Server Error`
- `/v1/models` 返回里显示 `owned_by: "sglang"`

所以这条 `8004` 服务当前更像一个 chat-compatible 的 SGLang 风格后端，而不是一个对最新版 Codex 友好的 Responses 后端。

这意味着：

- 它可以响应原始 chat 请求
- 但它目前不能直接给最新版 Codex runner 使用
- 因而 DeepScientist 也不能通过正常 Codex 路径使用它

我们还额外做了旧版 Codex 对照测试：

- 最新版 Codex + `wire_api = "responses"`：失败
- Codex `0.57.0` + 顶层 `model_provider` / `model` + `wire_api = "chat"`：成功

所以对这台机器上的 `8004` 来说：

- **最新版 Codex 路径**：不通
- **Codex `0.57.0` 回退路径**：可行

## 5. 给本地 Responses 后端配置 Codex profile

如果你的后端真的支持 `/v1/responses`，可以写成这样：

```toml
[model_providers.local_vllm]
name = "local_vllm"
base_url = "http://127.0.0.1:8004/v1"
env_key = "LOCAL_API_KEY"
wire_api = "responses"
requires_openai_auth = false

[profiles.local_vllm]
model = "/model/gpt-oss-120b"
model_provider = "local_vllm"
```

然后先直接测试 Codex：

```bash
export LOCAL_API_KEY=1234
codex exec --profile local_vllm --json --cd /tmp --skip-git-repo-check - <<'EOF'
Reply with exactly HELLO.
EOF
```

如果这一步过不了，就先不要继续尝试 DeepScientist。

## 5.1 只支持 chat 时，回退到 Codex `0.57.0`

如果你的后端只有 `/v1/chat/completions`，可以尝试这条回退路径：

1. 安装 Codex `0.57.0`
2. 使用 `wire_api = "chat"`
3. 把 `model_provider` 和 `model` 写到顶层

示例：

```toml
model = "/model/gpt-oss-120b"
model_provider = "localchat"
approval_policy = "never"
sandbox_mode = "workspace-write"

[model_providers.localchat]
name = "localchat"
base_url = "http://127.0.0.1:8004/v1"
env_key = "LOCAL_API_KEY"
wire_api = "chat"
requires_openai_auth = false
```

然后直接测试：

```bash
export LOCAL_API_KEY=1234
codex exec --json --cd /tmp --skip-git-repo-check - <<'EOF'
Reply with exactly HELLO.
EOF
```

如果这条旧版 Codex 路径能通过，DeepScientist 通常也可以沿用同样的 runner binary 和 provider 思路。

## 6. Codex 成功后，再测试 DeepScientist

只有当上面的 `codex exec` 能通过时，再继续：

```bash
ds doctor --codex-profile local_vllm
ds --codex-profile local_vllm
```

这里推荐使用 `ds doctor`。

`ds docker` 只是 `ds doctor` 的历史别名，不是 Docker 部署命令。

如果你想持久化配置：

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: local_vllm
  model: inherit
  model_reasoning_effort: high
  approval_policy: never
  sandbox_mode: danger-full-access
```

## 7. 后端兼容性结论

### vLLM

推荐。

满足下面三个条件时，是当前最稳妥的本地路径：

- `/v1/models` 正常
- `/v1/responses` 正常
- 模型名稳定可见

### Ollama

条件支持。

只有在下面条件满足时才建议使用：

- 当前 Ollama 版本真的暴露了 `/v1/responses`
- 目标模型可以通过该接口稳定工作

如果只有 chat-completions 兼容，不足以支持最新版 Codex，但仍然可以尝试 `0.57.0` 这条旧版 Codex 路径。

### SGLang

要特别小心。

如果你的 SGLang 部署表现是：

- `/v1/chat/completions` 正常
- `/v1/responses` 失败

那么它当前就和最新版 Codex runner 不兼容。

如果你必须使用这类后端，现实可行的 fallback 就是回退到 Codex `0.57.0` 并使用 `wire_api = "chat"`。

## 8. 如果你现在只有 chat-completions

如果你的后端只有 `/v1/chat/completions`，当前有四种现实选择：

1. 切到支持 Responses 的 vLLM
2. 升级到真正支持 `/v1/responses` 的 Ollama
3. 回退到 Codex `0.57.0` 并使用 `wire_api = "chat"`
4. 在后端前面加一层 Responses-compatible 代理

这里的问题本质上是 Codex CLI 的当前要求，不是 DeepScientist 单独某个配置写错了。

## 8.1 Ollama 应该选哪条 runner 路线

Ollama 官方现在同时覆盖：

- OpenAI-compatible API：`http://localhost:11434/v1`
- Codex 集成：`https://docs.ollama.com/integrations/codex`
- Claude Code 集成：`https://docs.ollama.com/integrations/claude-code`
- OpenCode 集成：`https://docs.ollama.com/integrations/opencode`

所以 Ollama 不只有一条路。

| 目标 | 推荐 runner | 你需要先验证什么 |
|---|---|---|
| 想沿用 DeepScientist 默认 Codex 路线 | Codex | `ollama run`、`/v1/responses`、`codex exec --profile <ollama-profile>` |
| 想少处理 Codex Responses 兼容细节 | OpenCode | `opencode run --model ollama/<model>` 或 custom provider 模型名 |
| 想复用 Claude Code 生态和 Anthropic-compatible 路线 | Claude Code | `claude -p --model <ollama-model>` 且 `ANTHROPIC_BASE_URL=http://localhost:11434` |

对新用户的建议：

1. 如果你只是想尽快把 Ollama 接进 DeepScientist，优先走 OpenCode。
2. 如果你已经熟悉 Codex profile，并且 `/v1/responses` 测试通过，可以走 Codex。
3. 如果你明确要使用 Claude Code runner，就按 Claude Code + Ollama 的 Anthropic-compatible 环境变量配置。

### Ollama + Codex 最小路径

```bash
ollama serve
ollama pull gpt-oss:20b
ollama run gpt-oss:20b "Reply with exactly HELLO."

curl http://localhost:11434/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-oss:20b","input":"Reply with exactly HELLO."}'
```

然后在 `~/.codex/config.toml` 中准备 profile：

```toml
[model_providers.local_ollama]
name = "Local Ollama"
base_url = "http://localhost:11434/v1"
wire_api = "responses"
requires_openai_auth = false

[profiles.ollama-local]
model = "gpt-oss:20b"
model_provider = "local_ollama"
```

验证：

```bash
codex exec --profile ollama-local "Reply with exactly OK."
ds doctor --codex-profile ollama-local
```

### Ollama + OpenCode 最小路径

```bash
ollama serve
ollama pull gpt-oss:20b
opencode run --format json --pure --model ollama/gpt-oss:20b "Reply with exactly HELLO."
ds doctor --runner opencode
```

如果你的 OpenCode 没有内置识别 `ollama/<model>`，就按 [25 OpenCode 配置指南](./25_OPENCODE_PROVIDER_SETUP.md) 里的 custom provider 示例写 `local_ollama`。

### Ollama + Claude Code 最小路径

```bash
ollama serve
ollama pull gpt-oss:20b

export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_BASE_URL=http://localhost:11434
claude -p --output-format json --model gpt-oss:20b --tools "" "Reply with exactly HELLO."

ds doctor --runner claude
```

DeepScientist 的 Claude runner 配置里应写：

```yaml
claude:
  enabled: true
  model: gpt-oss:20b
  env:
    ANTHROPIC_AUTH_TOKEN: "ollama"
    ANTHROPIC_BASE_URL: "http://localhost:11434"
```

## 9. 推荐的实际顺序

每次都按这个顺序来：

1. 先测 `/v1/models`
2. 再测 `/v1/responses`
3. 再测 `codex exec --profile <name>`
4. 再测 `ds doctor --codex-profile <name>`
5. 最后再启动 `ds --codex-profile <name>`

如果第 2 步失败，就先停在那里。不要期待最新版 Codex 路径下的 DeepScientist 可以正常工作。
