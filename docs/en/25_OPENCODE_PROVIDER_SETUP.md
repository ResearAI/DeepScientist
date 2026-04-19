# 25 OpenCode Setup

DeepScientist does not implement a separate provider layer for OpenCode either.

It reuses the `opencode` CLI that already works on your machine, injects DeepScientist MCP servers, and mirrors first-party skills into the OpenCode project tree.

The right order is:

1. install OpenCode
2. authenticate / configure providers directly in OpenCode
3. validate `opencode run` directly
4. run `ds doctor`
5. only then switch DeepScientist to the `opencode` runner

If `opencode` itself is not working yet, fixing DeepScientist first is the wrong order.

## Official docs to read first

Read the official OpenCode docs first:

- Intro / install: `https://opencode.ai/docs`
- Config: `https://opencode.ai/docs/config/`
- Providers: `https://opencode.ai/docs/providers/`
- MCP servers: `https://opencode.ai/docs/mcp-servers`
- Skills: `https://opencode.ai/docs/skills`

DeepScientist expects the same local OpenCode configuration described there.

## What DeepScientist actually uses

DeepScientist currently runs OpenCode through a command shape close to:

```bash
opencode run \
  --format json \
  --pure \
  --dir /absolute/workspace \
  [--model provider/model] \
  [--agent agent-name] \
  [--variant high]
```

Then it injects:

- `memory`
- `artifact`
- `bash_exec`

as quest-local MCP servers.

It also mirrors DeepScientist skills into:

```text
<quest_root>/.opencode/skills/
```

## Step 1: install OpenCode

According to the current OpenCode docs, common install paths include:

### Install script

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

Then verify the actual binary:

```bash
which opencode
opencode --version
opencode run --help
```

If you need a custom binary, set an absolute path in `runners.opencode.binary`.

## Step 2: authenticate providers in OpenCode

The official OpenCode docs describe provider setup through:

- `opencode auth login`
- `opencode providers`
- `opencode auth list`

OpenCode stores credentials in:

```text
~/.local/share/opencode/auth.json
```

and global config in:

```text
~/.config/opencode/opencode.json
```

If you are new to OpenCode providers, the docs recommend connecting a provider first and then setting the model in config.

## Step 3: validate OpenCode directly

Before changing DeepScientist settings, validate OpenCode on its own.

### Minimal smoke check

```bash
opencode run --format json --pure "Reply with exactly HELLO"
```

### Model-specific smoke check

```bash
opencode run --format json --pure --model anthropic/claude-sonnet-4-5 "Reply with exactly HELLO"
```

### Agent / variant smoke check

```bash
opencode run \
  --format json \
  --pure \
  --agent plan \
  --variant high \
  "Reply with exactly HELLO"
```

If this does not work, stop there and fix OpenCode first.

## OpenCode config concepts that matter most

From the current official docs and CLI help, the DeepScientist-relevant OpenCode concepts are:

- global config file: `~/.config/opencode/opencode.json`
- credentials file: `~/.local/share/opencode/auth.json`
- project config merge behavior
- model id format: `provider/model-id`
- `default_agent` in OpenCode config
- `--agent` in CLI
- `--variant` in CLI
- `--format json` for raw event output
- `--thinking` in CLI if you want OpenCode itself to print thinking blocks in direct terminal usage

### Config merge and project locations

OpenCode config files are merged, not replaced.

The official config docs also note that project-level OpenCode directories use plural names such as:

- `.opencode/agents/`
- `.opencode/skills/`
- `.opencode/plugins/`
- `.opencode/tools/`

That aligns with how DeepScientist mirrors its own quest-local skills.

## Provider configuration

OpenCode's provider docs describe two layers:

1. credentials added through `opencode auth login`
2. provider behavior customized in the `provider` section of `opencode.json`

A common provider example looks like:

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

This matters for DeepScientist because the `opencode` runner does not bypass your OpenCode provider setup. It reuses it.

## Agents and skills

The official OpenCode docs support:

- custom agents in `opencode.json`
- file-based agents in `~/.config/opencode/agents/` or `.opencode/agents/`
- skills in `.opencode/skills/<name>/SKILL.md`

DeepScientist currently maps its own first-party skill bundles into:

```text
<quest_root>/.opencode/skills/deepscientist-*/
```

So from the user's point of view:

- your own global OpenCode agents stay global
- DeepScientist's quest skills are mirrored per quest
- DeepScientist can still pass `--agent <name>` through `runners.opencode.default_agent`

## Step 4: map OpenCode into DeepScientist settings

### Global default runner

```yaml
# ~/DeepScientist/config/config.yaml
default_runner: opencode
```

### Runner config

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

### Settings page mapping

In the web Settings page:

- `Config -> Default runner`
  - choose `OpenCode`
- `Runners -> opencode.enabled`
  - enable the runner
- `Runners -> opencode.binary`
  - set `opencode` or an absolute path
- `Runners -> opencode.config_dir`
  - usually `~/.config/opencode`
- `Runners -> opencode.model`
  - use `inherit` unless you want DeepScientist to force a specific `provider/model`
- `Runners -> opencode.default_agent`
  - optional `--agent`
- `Runners -> opencode.variant`
  - optional provider-specific `--variant`

## Step 5: validate DeepScientist

After direct OpenCode validation works, run:

```bash
ds doctor
```

You want the OpenCode checks to confirm:

- the binary is found
- the startup hello probe succeeds
- the configured `config_dir` is readable

Then start DeepScientist:

```bash
ds
```

and confirm that a quest actually runs on `opencode`.

## Model selection and other providers

OpenCode is the most flexible runner in DeepScientist today for users who want to connect other model providers.

The official docs describe:

- `provider/model-id` model naming
- provider-specific `baseURL`
- local models
- many third-party providers through the OpenCode provider system

In practice that means:

- if OpenCode already works with your provider, DeepScientist can reuse it
- you usually do not need DeepScientist-specific provider code
- keep `runners.opencode.model: inherit` when OpenCode itself should decide the default model
- only set `runners.opencode.model` when you want DeepScientist to override the OpenCode default for every quest turn

## Project-level switching

DeepScientist now supports both levels of switching:

### New quests follow the global default

```yaml
default_runner: opencode
```

### Existing quests can override it

Inside project settings, change:

- `Project settings -> Default runner`

This means you can:

- keep one quest on Codex
- move another quest to OpenCode
- switch a Claude quest over to OpenCode later if the provider fit is better

## DeepScientist-specific OpenCode behavior

For each run, DeepScientist creates a quest-local OpenCode home overlay under:

```text
<quest_root>/.ds/opencode-home/
```

and writes quest-specific config there, including MCP injection.

It also mirrors first-party skills into:

```text
<quest_root>/.opencode/skills/
```

So users do not need to hand-maintain DeepScientist's MCP or first-party skills inside the quest.

## Common failure cases

### `opencode` is missing

Check:

```bash
which opencode
opencode --version
```

Then either:

- fix PATH
- or set `runners.opencode.binary` to an absolute path

### `opencode run` works interactively, but DeepScientist doctor fails

Usually one of these is wrong:

- `runners.opencode.config_dir`
- OpenCode credentials were saved under a different user home than the daemon actually sees
- the configured `model` override is invalid for the current provider
- `variant` is set even though the current provider does not support it

### You use a provider-specific reasoning tier

Put it in:

```yaml
runners:
  opencode:
    variant: high
```

only if your provider actually documents that variant flag.

Otherwise leave `variant` empty.

### You want a custom OpenCode agent

Set:

```yaml
runners:
  opencode:
    default_agent: plan
```

only after confirming the same agent name works in direct OpenCode CLI usage.

### Skills do not appear

Check that the quest contains:

```text
<quest_root>/.opencode/skills/
```

DeepScientist syncs first-party skill bundles there during quest creation and prompt refresh.

## Recommended defaults

For most users, the safest OpenCode setup is:

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

Then do all provider-specific auth and model tuning inside OpenCode first, validate with `opencode run`, and only then switch DeepScientist over.
