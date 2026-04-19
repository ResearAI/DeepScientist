# 23 Claude Runner 指南：用 Claude Code CLI 驱动 DeepScientist

DeepScientist 支持 `codex` 和 `claude` 两个 runner。本文说明如何用 Claude Code CLI 替代 Codex 作为执行引擎。

计费说明：DeepScientist 不调用模型 API，只启动本机 CLI 子进程。使用 Claude runner 走的是你的 Claude 订阅额度（Max / Pro），不是 Anthropic API 按量计费。

## 1. 安装并验证 Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
claude --version
claude -p "Reply with exactly OK."
```

如果最后一步不通（未认证、订阅不支持、命令找不到），先修通 CLI 再继续。

## 2. 初始化 DeepScientist 并修改配置

先确保 DeepScientist 已安装，然后初始化配置目录：

```bash
npm install -g @researai/deepscientist
ds init
```

`ds init` 会在 `~/DeepScientist/config/` 下生成默认配置文件。然后修改两个文件：

**`~/DeepScientist/config/runners.yaml`** — 启用 claude：

```yaml
claude:
  enabled: true
  binary: claude
  config_dir: ~/.claude
  model: inherit
  max_turns: 200
  approval_policy: never
  sandbox_mode: danger-full-access
  env: {}
```

如果不需要 Codex，可以把 `codex.enabled` 设为 `false`。

**`~/DeepScientist/config/config.yaml`** — 设置默认 runner：

```yaml
default_runner: claude
```

如果服务器在不支持的地区，需要代理才能访问 Anthropic，在 `env` 里加上：

```yaml
claude:
  enabled: true
  # ...
  env:
    HTTPS_PROXY: "http://your-proxy:port"
```

## 3. 验证并启动

```bash
ds doctor   # 检查 claude 二进制是否就绪
ds          # 启动
```

启动后的使用方式和 Codex runner 完全一样。

## 4. 环境变量覆盖

不修改配置文件也可以临时调整：

| 环境变量 | 作用 |
|---|---|
| `DS_CLAUDE_BINARY` | 覆盖 claude 二进制路径 |
| `DS_CLAUDE_MODEL` | 覆盖模型 |
| `DEEPSCIENTIST_CLAUDE_MAX_TURNS` | 覆盖最大轮次 |
| `DEEPSCIENTIST_CLAUDE_YOLO` | `true` = YOLO 模式；`false` = 安全模式 |

## 5. 排障

### 日志位置

- 命令详情：`<quest_root>/.ds/runs/<run_id>/command.json`
- 事件流：`<quest_root>/.ds/runs/<run_id>/stdout.jsonl`
- 错误输出：`<quest_root>/.ds/runs/<run_id>/stderr.txt`
- 最终输出：`<quest_root>/.ds/claude_history/<run_id>/assistant.md`

### 常见问题

**401 Unauthorized** — Claude CLI 认证失败。运行 `claude` 进入交互模式重新登录。

**权限错误** — 检查 `approval_policy`。`never` 对应 `--dangerously-skip-permissions`；如果不想自动批准，改为 `on-request`。

**网络不通** — 在 `runners.yaml` 的 `env` 中配置 `HTTPS_PROXY`。

**root 用户卡住无输出** — Claude CLI 禁止 root 使用 `--dangerously-skip-permissions`。将 `approval_policy` 改为 `auto`，或使用非 root 用户运行。

## 6. 相关文档

- [00 快速开始](./00_QUICK_START.md)
- [01 设置参考](./01_SETTINGS_REFERENCE.md)
- [09 启动诊断](./09_DOCTOR.md)
