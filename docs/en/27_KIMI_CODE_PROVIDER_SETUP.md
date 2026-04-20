# Kimi Code Provider Setup

Use this guide when you want DeepScientist to run through the official Kimi Code CLI as a separate builtin runner instead of reusing the Claude path.

## What DeepScientist expects

- Install the official `kimi` CLI and make sure `kimi --version` works in the same shell that launches DeepScientist.
- Complete the first-run login flow once with `kimi login` or by starting `kimi` interactively.
- Your global Kimi home should normally live at `~/.kimi/`.

## Recommended `runners.yaml` shape

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

## Runtime behavior

- DeepScientist copies your configured `~/.kimi` home into an isolated quest runtime under `.ds/kimi-home/.kimi`.
- Quest-local skills are mirrored into `.kimi/skills`.
- Builtin DeepScientist MCP servers are injected through a generated `.kimi/mcp.json`.
- Prompts are sent over stdin, so long DeepScientist turns do not hit argv length limits.

## Validate before enabling globally

1. Run `kimi --print --input-format text --output-format stream-json --yolo`.
2. Send a simple prompt such as `Reply with exactly HELLO.`
3. Run `ds doctor` and confirm the `Kimi Code CLI` startup probe passes.
4. Only then switch `config.default_runner` to `kimi`.
