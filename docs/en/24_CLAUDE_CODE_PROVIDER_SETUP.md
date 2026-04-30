# 24 Claude Code Setup

It reuses the `claude` CLI that already works on your machine, then injects DeepScientist MCP servers and quest-local skills at runtime.

The right order is:

1. install and authenticate Claude Code
2. confirm `claude` works directly in a terminal
3. run `ds doctor`
4. only then switch DeepScientist to the `claude` runner

## Official docs to read first

Read the official Claude Code docs before editing DeepScientist settings:

- Quickstart: `https://docs.anthropic.com/en/docs/claude-code/quickstart`
- Setup / install: `https://docs.anthropic.com/en/docs/claude-code/getting-started`
- Settings: `https://docs.anthropic.com/en/docs/claude-code/settings`
- MCP: `https://docs.anthropic.com/en/docs/claude-code/mcp`
- SDK / headless mode: `https://docs.anthropic.com/en/docs/claude-code/sdk`
- Environment variables: `https://code.claude.com/docs/en/env-vars`
- Ollama + Claude Code: `https://docs.ollama.com/integrations/claude-code`

DeepScientist expects the same local Claude Code setup described there.

## What DeepScientist actually uses

DeepScientist currently runs Claude Code in headless mode with a command shape close to:

```bash
claude -p \
  --input-format text \
  --output-format stream-json \
  --verbose \
  --add-dir /absolute/workspace \
  --no-session-persistence \
  --permission-mode bypassPermissions \
  --mcp-config /absolute/runtime/claude-home/mcp.json \
  --allowedTools "mcp__memory,mcp__artifact,mcp__bash_exec"
```

Then it injects three built-in MCP servers into the run:

- `memory`
- `artifact`
- `bash_exec`

It also syncs first-party DeepScientist skills into quest-local Claude Code agents under:

```text
<quest_root>/.claude/agents/
```

## Step 1: install Claude Code

According to Anthropic's current setup docs, the common install paths are:

### NPM install

```bash
npm install -g @anthropic-ai/claude-code
```

### Native install

macOS / Linux / WSL:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Windows PowerShell:

```powershell
irm https://claude.ai/install.ps1 | iex
```

After installation, verify the binary you are actually using:

```bash
which claude
claude --version
```

If you need a non-default binary, set the absolute path in DeepScientist `runners.yaml`.

## Step 2: authenticate Claude Code

The official Claude Code docs describe two common account paths:

- Claude.ai account
- Anthropic Console account / API access

The most reliable first check is still interactive login:

```bash
claude
```

Then complete login inside Claude Code.

Claude Code stores local credentials and settings under `~/.claude/`.

The most important local files are usually:

- `~/.claude/.credentials.json`
- `~/.claude/settings.json`
- `~/.claude/settings.local.json`
- `~/.claude/agents/`

DeepScientist reads from `runners.claude.config_dir` and copies the relevant files into a quest-local runtime overlay before each run.

## Step 3: validate Claude Code directly

Before touching DeepScientist settings, confirm headless Claude Code works on its own.

### Minimal smoke check

```bash
claude -p --output-format json --tools "" "Reply with exactly HELLO."
```

### Model-specific smoke check

```bash
claude -p --output-format json --model claude-opus-4-6 --tools "" "Reply with exactly HELLO."
```

### Permission-mode smoke check

```bash
claude -p \
  --output-format json \
  --permission-mode bypassPermissions \
  --tools "" \
  "Reply with exactly HELLO."
```

If these fail, stop there and fix Claude Code first.

## Claude settings that matter most

From the current CLI help and settings docs, the DeepScientist-relevant Claude Code knobs are:

- `--model`
  - choose the Claude model for the session
- `--permission-mode`
  - one of `acceptEdits`, `bypassPermissions`, `default`, `delegate`, `dontAsk`, `plan`
- `--add-dir`
  - add extra directories to tool access scope
- `--system-prompt` / `--append-system-prompt`
  - DeepScientist does not rely on these directly; it builds its own prompt and passes it as the run input
- `--mcp-config`
  - DeepScientist does not ask users to maintain this manually for built-in MCP; it injects MCP itself per run
- `--agent`
  - available in Claude Code CLI, but DeepScientist currently uses synced quest-local agents rather than a global `runners.yaml` field for agent name selection

## Environment variables and gateways

The official Claude Code settings docs explicitly list `ANTHROPIC_API_KEY`.

For DeepScientist users, the practical env fields are:

- `ANTHROPIC_API_KEY`
  - standard Anthropic API key path
- `ANTHROPIC_BASE_URL`
  - for compatible gateways / proxy endpoints
- `CLAUDE_CODE_MAX_OUTPUT_TOKENS`
  - if your Claude Code environment or provider supports this limit knob

### Important DeepScientist compatibility note

Some third-party Claude-compatible gateways expose a token as `ANTHROPIC_AUTH_TOKEN` rather than `ANTHROPIC_API_KEY`.

DeepScientist now mirrors:

- `ANTHROPIC_AUTH_TOKEN -> ANTHROPIC_API_KEY`

when `ANTHROPIC_API_KEY` is empty.

This is a DeepScientist compatibility behavior, not a Claude Code guarantee.

If your direct `claude` terminal run already works with `ANTHROPIC_API_KEY`, prefer that field.

## Claude Code + Ollama

Ollama exposes an Anthropic-compatible API, so Claude Code can point `ANTHROPIC_BASE_URL` at local Ollama.

Use this path when:

- you want DeepScientist to use the `claude` runner while the actual model is served by Ollama
- the Ollama model has enough context for DeepScientist's long prompts and MCP tool use
- a direct Claude Code headless smoke check works first

Do not use this as the normal Gemini route. Gemini's official compatibility path is OpenAI-compatible, not Anthropic-compatible; use OpenCode for Gemini unless you have your own Anthropic-compatible Gemini gateway.

### 1. Make an Ollama model available

```bash
ollama --version
ollama serve
```

In another terminal:

```bash
ollama pull gpt-oss:20b
ollama run gpt-oss:20b "Reply with exactly HELLO."
```

Replace `gpt-oss:20b` with the model you actually plan to run.

### 2. Validate Claude Code directly

```bash
export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_BASE_URL=http://localhost:11434

claude -p \
  --output-format json \
  --model gpt-oss:20b \
  --tools "" \
  "Reply with exactly HELLO."
```

If this fails, fix Ollama, the model name, or Claude Code's provider env before changing DeepScientist.

### 3. Put the same route in DeepScientist

```yaml
claude:
  enabled: true
  binary: claude
  config_dir: ~/.claude
  model: gpt-oss:20b
  permission_mode: bypassPermissions
  env:
    ANTHROPIC_AUTH_TOKEN: "ollama"
    ANTHROPIC_BASE_URL: "http://localhost:11434"
```

DeepScientist mirrors `ANTHROPIC_AUTH_TOKEN` to `ANTHROPIC_API_KEY` when `ANTHROPIC_API_KEY` is empty. Do not rely on an empty `ANTHROPIC_API_KEY: ""` entry in `runners.yaml`; empty env values are ignored.

### 4. Validate DeepScientist

```bash
ds doctor --runner claude
ds --runner claude
```

If `claude -p` works but `ds doctor --runner claude` fails, check `runners.claude.env` and make sure the daemon reads the same `~/DeepScientist/config/runners.yaml`.

## Claude Code + Gemini

Gemini is not a normal Claude Code provider path.

- Claude Code uses Anthropic / Anthropic-compatible protocol
- Gemini's easiest documented compatibility path is OpenAI-compatible Chat Completions
- these are different protocols

If you have a private Anthropic-compatible gateway in front of Gemini, configure it with `ANTHROPIC_BASE_URL`; otherwise use [25 OpenCode Setup](./25_OPENCODE_PROVIDER_SETUP.md) for Gemini.

## Step 4: map Claude Code into DeepScientist settings

### Global runtime config

Set the global default runner in:

```yaml
# ~/DeepScientist/config/config.yaml
default_runner: claude
```

### Runner config

Configure the Claude runner in:

```yaml
# ~/DeepScientist/config/runners.yaml
claude:
  enabled: true
  binary: claude
  config_dir: ~/.claude
  model: inherit
  permission_mode: bypassPermissions
  mcp_timeout_ms: 172800000
  mcp_tool_timeout_ms: 172800000
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

If your direct Claude Code install uses the default account and settings under `~/.claude`, keep `config_dir` unchanged.

### Settings-first path after launch

If DeepScientist is already running, use the visual `Models` page first:

- route: `/settings/runners`

Use it to:

- switch the global default runner to `Claude`
- enable the Claude runner
- fill `binary`, `config_dir`, `model`, `permission_mode`, `mcp_timeout_ms`, `mcp_tool_timeout_ms`, and `env`

![Models settings page](../images/settings/settings-runners-en.png)

### Settings page mapping

In the web Settings page:

- `Config -> Default runner`
  - choose `Claude`
- `Runners -> claude.enabled`
  - enable the runner
- `Runners -> claude.binary`
  - set `claude` or an absolute path
- `Runners -> claude.config_dir`
  - usually `~/.claude`
- `Runners -> claude.model`
  - use `inherit` unless you want a fixed Claude model
- `Runners -> claude.permission_mode`
  - use `bypassPermissions` when you want Codex-like local automation
- `Runners -> claude.mcp_timeout_ms`
  - MCP server startup timeout forwarded to Claude Code as `MCP_TIMEOUT`
- `Runners -> claude.mcp_tool_timeout_ms`
  - per-tool MCP timeout forwarded to Claude Code as `MCP_TOOL_TIMEOUT`
- `Runners -> claude.env`
  - put `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, and related gateway values here

## Step 5: validate DeepScientist

Run doctor after your terminal-level Claude check passes:

```bash
ds doctor
```

You want the Claude section to confirm:

- the `claude` binary is found
- the startup probe returns `HELLO`
- the configured `config_dir` is readable

Then launch DeepScientist and verify the runner used by a project:

```bash
ds
```

or create a project from the web UI and confirm the quest runner is `claude` in project settings.

## Project-level switching

DeepScientist now supports both levels of switching:

### Global default for new quests

```yaml
# config.yaml
default_runner: claude
```

### Per-quest override

Inside a quest, change:

- `Project settings -> Default runner`

or edit `quest.yaml` through the settings API surface.

This means:

- new quests can default to Claude Code
- existing quests can stay on Codex
- a single quest can be switched from Codex to Claude or back later

## DeepScientist-specific runtime behavior

For each Claude run, DeepScientist creates a quest-local overlay and injects:

- quest-local MCP server config
- quest-local skills mirrored into `.claude/agents/`
- quest and worktree environment variables such as:
  - `DS_HOME`
  - `DS_QUEST_ID`
  - `DS_QUEST_ROOT`
  - `DS_WORKTREE_ROOT`
  - `DS_RUN_ID`

You do not need to hand-write Claude MCP config for DeepScientist's three built-in MCP namespaces.

## Common failure cases

### `claude` is not on PATH

Check:

```bash
which claude
claude --version
```

Then either:

- fix PATH
- or set `runners.claude.binary` to an absolute path

### Interactive `claude` works, but DeepScientist doctor fails

Usually one of these is wrong:

- `runners.claude.config_dir`
- `ANTHROPIC_API_KEY` / gateway env not available to the daemon shell
- `permission_mode` is too strict for your automation path
- the configured `model` is not available to the current Claude account

### Gateway works only with `ANTHROPIC_AUTH_TOKEN`

If direct Claude Code still shows `apiKeySource: none`, set `ANTHROPIC_API_KEY` explicitly.

DeepScientist can mirror `ANTHROPIC_AUTH_TOKEN`, but your own direct terminal validation should still prefer a real `ANTHROPIC_API_KEY` path whenever possible.

### Project-level skills are not visible

Check that the quest contains:

```text
<quest_root>/.claude/agents/
```

DeepScientist syncs first-party skills there during quest creation and prompt refresh.

### MCP tools appear in the run, but not in the UI

Current DeepScientist surfaces display Claude tool events through canonical `runner.tool_call` / `runner.tool_result` events.

If the backend works but the UI looks empty, check:

- `ds doctor`
- the browser network response for `/api/quests/<id>/events?format=acp`
- the quest event log at `.ds/events.jsonl`

## Recommended defaults

For most users, this is the safest Claude setup:

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

Then keep actual credentials in the shell or in the runner env mapping, validate with `claude -p`, and only then start DeepScientist.
