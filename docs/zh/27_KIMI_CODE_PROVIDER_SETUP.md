# Kimi Code Provider 配置指南

当你希望 DeepScientist 通过官方 `kimi` CLI 运行，并且把它作为一个独立 builtin runner 使用时，使用这份文档；不要再把 Kimi 混在 Claude 路径里。

## DeepScientist 的前提假设

- 已安装官方 `kimi` CLI，并且在启动 DeepScientist 的同一个 shell 里执行 `kimi --version` 能成功。
- 已经至少执行过一次 `kimi login`，或者手动启动过 `kimi` 完成首次登录。
- 全局 Kimi home 默认位于 `~/.kimi/`。

## 推荐的 `runners.yaml` 配置

```yaml
kimi:
  enabled: true
  binary: kimi
  config_dir: ~/.kimi
  model: inherit
  agent: ""
  thinking: false
  yolo: true
```

## DeepScientist 的运行方式

- DeepScientist 会把你配置的 `~/.kimi` 复制到 quest 隔离运行目录 `.ds/kimi-home/.kimi`。
- quest 内的技能会同步到 `.kimi/skills`。
- 内置 MCP 会通过生成的 `.kimi/mcp.json` 注入进去。
- prompt 通过 stdin 发送，所以长 prompt 不会再撞到 argv 长度限制。

## 切换前的验证步骤

1. 手动运行 `kimi --print --input-format text --output-format stream-json --yolo`。
2. 输入一个简单提示，例如 `Reply with exactly HELLO.`。
3. 运行 `ds doctor`，确认 `Kimi Code CLI` 的 startup probe 通过。
4. 只有在这些都正常后，再把 `config.default_runner` 切到 `kimi`。
