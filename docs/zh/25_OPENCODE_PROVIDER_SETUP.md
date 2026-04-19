# 25 OpenCode 配置指南

DeepScientist 对 OpenCode 也不会额外维护一层独立 provider 适配。

它复用的是你机器上已经能正常工作的 `opencode` CLI，在运行时注入 DeepScientist MCP，并同步一方 skills 到 OpenCode 的项目目录。

正确顺序是：

1. 先安装 OpenCode
2. 先在 OpenCode 里完成 provider 认证和配置
3. 先直接验证 `opencode run`
4. 再运行 `ds doctor`
5. 最后再把 DeepScientist 切到 `opencode` runner

如果 `opencode` 本身还没通，先修 DeepScientist 是错误顺序。

## 官方文档先读哪些

建议先读 OpenCode 官方文档：

- Intro / install：`https://opencode.ai/docs`
- Config：`https://opencode.ai/docs/config/`
- Providers：`https://opencode.ai/docs/providers/`
- MCP servers：`https://opencode.ai/docs/mcp-servers`
- Skills：`https://opencode.ai/docs/skills`

DeepScientist 依赖的就是同一套本地 OpenCode 配置。

## DeepScientist 实际如何调用 OpenCode

DeepScientist 当前对 OpenCode 的调用形态接近：

```bash
opencode run \
  --format json \
  --pure \
  --dir /absolute/workspace \
  [--model provider/model] \
  [--agent agent-name] \
  [--variant high]
```

然后再注入：

- `memory`
- `artifact`
- `bash_exec`

这三个 quest 局部 MCP server。

同时会把 DeepScientist 一方 skills 同步到：

```text
<quest_root>/.opencode/skills/
```

## 第一步：安装 OpenCode

根据 OpenCode 当前官方文档，常见安装方式包括：

### 安装脚本

```bash
curl -fsSL https://opencode.ai/install | bash
```

### NPM

```bash
npm install -g opencode-ai
```

### Bun

```bash
bun install -g opencode-ai
```

### pnpm

```bash
pnpm install -g opencode-ai
```

### Yarn

```bash
yarn global add opencode-ai
```

### Homebrew

```bash
brew install anomalyco/tap/opencode
```

安装后先确认实际 binary：

```bash
which opencode
opencode --version
opencode run --help
```

如果你必须使用特定路径的 OpenCode binary，就把绝对路径写进 `runners.opencode.binary`。

## 第二步：先在 OpenCode 里配置 provider

OpenCode 官方当前把 provider 配置拆成两层：

- `opencode auth login`
- `opencode providers`
- `opencode auth list`

OpenCode 的凭据默认存放在：

```text
~/.local/share/opencode/auth.json
```

全局配置通常在：

```text
~/.config/opencode/opencode.json
```

如果你第一次接触 OpenCode provider，建议先在 OpenCode 自己的 TUI/CLI 里把 provider 接通，再回到 DeepScientist。

## 第三步：先直接验证 OpenCode

在改 DeepScientist 设置之前，先确认 OpenCode 自己能跑。

### 最小 smoke check

```bash
opencode run --format json --pure "Reply with exactly HELLO"
```

### 指定模型 smoke check

```bash
opencode run --format json --pure --model anthropic/claude-sonnet-4-5 "Reply with exactly HELLO"
```

### 指定 agent / variant 的 smoke check

```bash
opencode run \
  --format json \
  --pure \
  --agent plan \
  --variant high \
  "Reply with exactly HELLO"
```

如果这里不通，先别碰 DeepScientist。

## OpenCode 里最重要的配置概念

结合当前官方文档和 CLI help，DeepScientist 相关的 OpenCode 概念主要有：

- 全局配置文件：`~/.config/opencode/opencode.json`
- 凭据文件：`~/.local/share/opencode/auth.json`
- 配置是 merge，而不是简单覆盖
- 模型 id 形态：`provider/model-id`
- OpenCode 的 `default_agent`
- CLI 里的 `--agent`
- CLI 里的 `--variant`
- `--format json` 原始事件输出
- `--thinking`，如果你想在直接使用 OpenCode 时显示 thinking blocks

### 配置 merge 和项目目录

OpenCode 官方 config 文档强调：配置是合并的，不是整份替换。

同时项目目录用的是复数子目录，例如：

- `.opencode/agents/`
- `.opencode/skills/`
- `.opencode/plugins/`
- `.opencode/tools/`

这和 DeepScientist 当前同步 quest 局部 skills 的方式是兼容的。

## Provider 配置

OpenCode 官方 provider 文档当前说明了：

1. 先通过 `opencode auth login` 存凭据
2. 再在 `opencode.json` 的 `provider` 段里配置 provider 行为

常见配置大致像这样：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "anthropic": {
      "options": {
        "baseURL": "https://api.anthropic.com/v1"
      }
    }
  }
}
```

这对 DeepScientist 的含义是：

- 如果 OpenCode 自己已经能走你的 provider
- DeepScientist 一般可以直接复用
- 通常不需要再写 DeepScientist 私有 provider 适配

## Agents 和 skills

OpenCode 官方支持：

- 在 `opencode.json` 里定义自定义 agents
- 在 `~/.config/opencode/agents/` 或 `.opencode/agents/` 下放 agent 文件
- 在 `.opencode/skills/<name>/SKILL.md` 下放 skills

DeepScientist 当前会把自己的 first-party skills 映射到：

```text
<quest_root>/.opencode/skills/deepscientist-*/
```

所以从用户角度看：

- 你自己的 OpenCode 全局 agent 仍然是全局的
- DeepScientist 的 quest skills 会按 quest 同步
- 如果你需要特定 OpenCode agent，也可以通过 `runners.opencode.default_agent` 透传 `--agent`

## 第四步：映射到 DeepScientist 配置

### 全局默认 runner

```yaml
# ~/DeepScientist/config/config.yaml
default_runner: opencode
```

### OpenCode runner 配置

```yaml
# ~/DeepScientist/config/runners.yaml
opencode:
  enabled: true
  binary: opencode
  config_dir: ~/.config/opencode
  model: inherit
  default_agent: ""
  variant: ""
  retry_on_failure: true
  retry_max_attempts: 4
  retry_initial_backoff_sec: 10.0
  retry_backoff_multiplier: 4.0
  retry_max_backoff_sec: 600.0
  env: {}
```

### Settings 页面对应关系

在 Web Settings 页面中：

- `Config -> Default runner`
  - 选择 `OpenCode`
- `Runners -> opencode.enabled`
  - 启用 OpenCode runner
- `Runners -> opencode.binary`
  - 填 `opencode` 或绝对路径
- `Runners -> opencode.config_dir`
  - 一般是 `~/.config/opencode`
- `Runners -> opencode.model`
  - 不想让 DeepScientist 强制覆盖模型时保持 `inherit`
- `Runners -> opencode.default_agent`
  - 对应 OpenCode 的 `--agent`
- `Runners -> opencode.variant`
  - 对应 provider-specific 的 `--variant`

## 第五步：验证 DeepScientist

当终端里的 OpenCode 已经验证通过之后，再运行：

```bash
ds doctor
```

你希望 OpenCode 检查显示：

- 找到了 binary
- startup hello probe 成功
- `config_dir` 可读

然后再启动 DeepScientist：

```bash
ds
```

并确认 quest 实际 runner 已经切到 `opencode`。

## 模型接入与其他 provider

如果你想通过 OpenCode 接更多模型/provider，OpenCode 是当前 DeepScientist 三个 runner 里最灵活的一条路径。

官方文档已经覆盖：

- `provider/model-id` 形式的模型名
- provider-specific `baseURL`
- 本地模型
- 大量第三方 provider

对 DeepScientist 来说，这意味着：

- 只要 OpenCode 自己已经能跑该 provider
- DeepScientist 一般就能复用
- 如果希望 OpenCode 自己决定默认模型，保持 `runners.opencode.model: inherit`
- 只有当你明确要让 DeepScientist 每次 quest turn 都强制指定某个模型时，才写死 `runners.opencode.model`

## 项目级切换

DeepScientist 现在支持两层切换：

### 新 quest 跟随全局默认值

```yaml
default_runner: opencode
```

### 已有 quest 单独覆盖

在项目设置里修改：

- `Project settings -> Default runner`

也就是说你可以：

- 某个 quest 留在 Codex
- 某个 quest 改到 OpenCode
- 某个 Claude quest 后面再切到 OpenCode

## DeepScientist 的 OpenCode 运行时行为

每次运行前，DeepScientist 会在 quest 下创建 OpenCode 局部 runtime home：

```text
<quest_root>/.ds/opencode-home/
```

并在里面写 quest-specific OpenCode config，包括 MCP 注入。

同时会把 first-party skills 同步到：

```text
<quest_root>/.opencode/skills/
```

所以你不需要手写 DeepScientist 自己的 MCP 或一方 skills。

## 常见故障

### `opencode` 不在 PATH 上

先查：

```bash
which opencode
opencode --version
```

然后：

- 修 PATH
- 或把绝对路径写进 `runners.opencode.binary`

### 交互式 OpenCode 能用，但 `ds doctor` 失败

常见原因有：

- `runners.opencode.config_dir` 指错了
- OpenCode 凭据保存在另一个 HOME，而 daemon 实际运行时看不到
- `model` override 对当前 provider 不合法
- `variant` 被写了，但当前 provider 根本不支持

### 你想用 provider-specific reasoning tier

只有当 provider 官方确实支持时，才写：

```yaml
runners:
  opencode:
    variant: high
```

否则就保持 `variant: ""`。

### 你想固定某个 OpenCode agent

先确认这个 agent 名称在直接 OpenCode CLI 里能用，然后再写：

```yaml
runners:
  opencode:
    default_agent: plan
```

### 看不到 quest skills

检查 quest 下是否存在：

```text
<quest_root>/.opencode/skills/
```

DeepScientist 会在 quest 创建和 prompt 同步时自动写进去。

## 推荐默认值

对大多数用户，最稳妥的 OpenCode 配置是：

```yaml
# config.yaml
default_runner: opencode

# runners.yaml
opencode:
  enabled: true
  binary: opencode
  config_dir: ~/.config/opencode
  model: inherit
  default_agent: ""
  variant: ""
  env: {}
```

然后所有 provider 认证、模型和 agent 调优都先在 OpenCode 自己那边跑通，再把 DeepScientist 切过来。
