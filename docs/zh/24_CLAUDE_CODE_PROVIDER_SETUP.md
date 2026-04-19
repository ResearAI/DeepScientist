# 24 Claude Code 配置指南

DeepScientist 不会为 Claude Code 额外再包一层私有适配器。

它复用的是你机器上已经能正常工作的 `claude` CLI，然后在运行时注入 DeepScientist 的 MCP 和 quest 局部 skills。

正确顺序是：

1. 先安装并认证 Claude Code
2. 先在终端里确认 `claude` 自己可用
3. 再运行 `ds doctor`
4. 最后再把 DeepScientist 切到 `claude` runner

如果 `claude` 本身还没通，先修 DeepScientist 是错误顺序。

## 官方文档先读哪些

建议先读 Claude Code 官方文档：

- Quickstart：`https://docs.anthropic.com/en/docs/claude-code/quickstart`
- Setup / install：`https://docs.anthropic.com/en/docs/claude-code/getting-started`
- Settings：`https://docs.anthropic.com/en/docs/claude-code/settings`
- MCP：`https://docs.anthropic.com/en/docs/claude-code/mcp`
- SDK / headless mode：`https://docs.anthropic.com/en/docs/claude-code/sdk`

DeepScientist 依赖的就是同一套本地 Claude Code 配置。

## DeepScientist 实际如何调用 Claude Code

DeepScientist 当前用的 headless 调用形态接近：

```bash
claude -p \
  --input-format text \
  --output-format stream-json \
  --verbose \
  --add-dir /absolute/workspace \
  --no-session-persistence \
  --permission-mode bypassPermissions
```

然后再注入三个内建 MCP：

- `memory`
- `artifact`
- `bash_exec`

同时会把一方 skills 同步到 quest 本地目录：

```text
<quest_root>/.claude/agents/
```

## 第一步：安装 Claude Code

按照 Anthropic 当前官方文档，常见安装方式是：

### NPM 安装

```bash
npm install -g @anthropic-ai/claude-code
```

### Native 安装

macOS / Linux / WSL：

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Windows PowerShell：

```powershell
irm https://claude.ai/install.ps1 | iex
```

安装后先确认你实际调用的是哪个二进制：

```bash
which claude
claude --version
```

如果你必须用一个非默认路径的 Claude Code binary，就把绝对路径写进 DeepScientist 的 `runners.yaml`。

## 第二步：认证 Claude Code

Claude Code 官方当前主要覆盖两条账户路径：

- Claude.ai 账户
- Anthropic Console / API 账户

最稳妥的第一步仍然是直接交互登录：

```bash
claude
```

然后在 Claude Code 里完成登录。

Claude Code 的本地状态通常放在 `~/.claude/`，最重要的文件一般是：

- `~/.claude/.credentials.json`
- `~/.claude/settings.json`
- `~/.claude/settings.local.json`
- `~/.claude/agents/`

DeepScientist 会从 `runners.claude.config_dir` 指向的目录读取这些内容，并在每次运行前复制到 quest 局部 overlay 里。

## 第三步：先直接验证 Claude Code

在改 DeepScientist 设置之前，先确认 headless Claude Code 自己能跑。

### 最小 smoke check

```bash
claude -p --output-format json --tools "" "Reply with exactly HELLO."
```

### 指定模型 smoke check

```bash
claude -p --output-format json --model claude-opus-4-6 --tools "" "Reply with exactly HELLO."
```

### 指定 permission mode 的 smoke check

```bash
claude -p \
  --output-format json \
  --permission-mode bypassPermissions \
  --tools "" \
  "Reply with exactly HELLO."
```

如果这里都不通，先别碰 DeepScientist。

## Claude Code 里最重要的参数

结合当前 CLI help 和官方 settings 文档，DeepScientist 相关的参数主要是：

- `--model`
  - 指定本次会话模型
- `--permission-mode`
  - 可选值包括 `acceptEdits`、`bypassPermissions`、`default`、`delegate`、`dontAsk`、`plan`
- `--add-dir`
  - 扩展工具可访问目录
- `--system-prompt` / `--append-system-prompt`
  - DeepScientist 不直接依赖这个；它会自己构建 prompt，并作为输入传给 Claude Code
- `--mcp-config`
  - DeepScientist 的内建 MCP 不需要你手写；它会按每次运行自动注入
- `--agent`
  - Claude Code CLI 支持，但 DeepScientist 当前更依赖 quest 局部同步到 `.claude/agents/` 的 agents

## 环境变量与网关

Claude Code 官方 settings 文档明确列出 `ANTHROPIC_API_KEY`。

对 DeepScientist 用户来说，最常见的字段是：

- `ANTHROPIC_API_KEY`
  - 标准 Anthropic API key
- `ANTHROPIC_BASE_URL`
  - Claude 兼容网关 / proxy endpoint
- `CLAUDE_CODE_MAX_OUTPUT_TOKENS`
  - 如果你的 Claude Code 环境或 provider 支持这个限制

### 一个重要的 DeepScientist 兼容说明

有些第三方 Claude 兼容网关暴露的是 `ANTHROPIC_AUTH_TOKEN`，而不是 `ANTHROPIC_API_KEY`。

DeepScientist 现在会在 `ANTHROPIC_API_KEY` 为空时自动做：

- `ANTHROPIC_AUTH_TOKEN -> ANTHROPIC_API_KEY`

这是 DeepScientist 的兼容行为，不是 Claude Code 官方保证。

如果你的直连 `claude` 终端已经能直接使用 `ANTHROPIC_API_KEY`，优先使用标准字段。

## 第四步：映射到 DeepScientist 配置

### 全局默认 runner

```yaml
# ~/DeepScientist/config/config.yaml
default_runner: claude
```

### Claude runner 配置

```yaml
# ~/DeepScientist/config/runners.yaml
claude:
  enabled: true
  binary: claude
  config_dir: ~/.claude
  model: inherit
  permission_mode: bypassPermissions
  retry_on_failure: true
  retry_max_attempts: 4
  retry_initial_backoff_sec: 10.0
  retry_backoff_multiplier: 4.0
  retry_max_backoff_sec: 600.0
  env:
    ANTHROPIC_API_KEY: "..."
    ANTHROPIC_BASE_URL: "https://your-gateway.example/api"
    CLAUDE_CODE_MAX_OUTPUT_TOKENS: "12000"
```

如果你的 Claude Code 一直就在默认 `~/.claude` 下工作，`config_dir` 一般不用改。

### Settings 页面对应关系

在 Web Settings 页面里：

- `Config -> Default runner`
  - 选择 `Claude`
- `Runners -> claude.enabled`
  - 启用 Claude runner
- `Runners -> claude.binary`
  - 填 `claude` 或绝对路径
- `Runners -> claude.config_dir`
  - 一般就是 `~/.claude`
- `Runners -> claude.model`
  - 不想写死模型时保持 `inherit`
- `Runners -> claude.permission_mode`
  - 想要接近 Codex 的本地自动化时，通常用 `bypassPermissions`
- `Runners -> claude.env`
  - 写 `ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL` 等运行时环境变量

## 第五步：验证 DeepScientist

当终端里的 Claude Code smoke check 已经通过之后，再运行：

```bash
ds doctor
```

你希望 Claude 相关检查显示：

- 找到了 `claude` binary
- startup probe 能返回 `HELLO`
- 配置目录 `config_dir` 可读取

然后再启动 DeepScientist：

```bash
ds
```

或者直接从 Web 创建项目，并在项目设置里确认 quest runner 是 `claude`。

## 项目级切换

DeepScientist 现在支持两层切换：

### 全局默认值，影响新 quest

```yaml
default_runner: claude
```

### 单个 quest 覆盖

在项目设置里修改：

- `Project settings -> Default runner`

也就是说：

- 新 quest 可以默认走 Claude Code
- 老 quest 可以继续留在 Codex
- 同一个 quest 后续也可以从 Codex 切到 Claude，再切回来

## DeepScientist 的 Claude 运行时行为

每次 Claude 运行前，DeepScientist 会自动准备：

- quest 局部 MCP 配置
- 同步后的 `.claude/agents/` skills
- quest/worktree 运行时环境变量，例如：
  - `DS_HOME`
  - `DS_QUEST_ID`
  - `DS_QUEST_ROOT`
  - `DS_WORKTREE_ROOT`
  - `DS_RUN_ID`

你不需要手写 DeepScientist 的三个内建 MCP 配置。

## 常见故障

### `claude` 不在 PATH 上

先查：

```bash
which claude
claude --version
```

然后：

- 修 PATH
- 或者把绝对路径写进 `runners.claude.binary`

### 交互式 `claude` 能用，但 `ds doctor` 失败

通常是以下问题之一：

- `runners.claude.config_dir` 指错了
- daemon 启动时拿不到 `ANTHROPIC_API_KEY` / 网关环境变量
- `permission_mode` 太严格，不适合自动化路径
- 你在 `runners.yaml` 里配置的 `model` 当前账号不可用

### 只有 `ANTHROPIC_AUTH_TOKEN` 才能走通网关

如果你直接运行 Claude Code 时仍然显示 `apiKeySource: none`，请优先显式设置 `ANTHROPIC_API_KEY`。

DeepScientist 可以兼容 `ANTHROPIC_AUTH_TOKEN`，但你自己的终端验证仍然应该尽量使用标准 `ANTHROPIC_API_KEY` 路径。

### quest 里的 skills 看不到

检查 quest 下是否有：

```text
<quest_root>/.claude/agents/
```

DeepScientist 会在 quest 创建和 prompt 同步时把一方 skills 写进去。

### 工具调用后端有，UI 里没显示

当前 DeepScientist 的 Claude tool 事件都是通过标准 `runner.tool_call / runner.tool_result` 事件显示的。

如果后端能跑但前端空白，先查：

- `ds doctor`
- 浏览器里的 `/api/quests/<id>/events?format=acp`
- quest 下的 `.ds/events.jsonl`

## 推荐默认值

对大多数用户，最稳妥的 Claude 设置是：

```yaml
# config.yaml
default_runner: claude

# runners.yaml
claude:
  enabled: true
  binary: claude
  config_dir: ~/.claude
  model: inherit
  permission_mode: bypassPermissions
  env: {}
```

然后把认证信息放在 shell 或 `runners.claude.env`，先用 `claude -p` 验证，再启动 DeepScientist。
