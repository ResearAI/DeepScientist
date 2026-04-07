# 15 Codex Provider Setup

DeepScientist does not implement separate provider adapters for MiniMax, GLM, Volcengine Ark, or Alibaba Bailian.

Instead, it reuses the same Codex CLI setup that already works in your terminal.

The recommended order is always:

1. make Codex itself work first
2. confirm `codex` or `codex --profile <name>` works in a terminal
3. run `ds doctor`
4. run `ds` or `ds --codex-profile <name>`

## Three supported patterns

### 1. Default OpenAI login path

Use this when your Codex CLI works through the standard OpenAI login flow.

```bash
codex login
ds doctor
ds
```

### 2. One-off provider profile

Use this when you already have a named Codex profile such as `m27`, `glm`, `ark`, or `bailian`.

```bash
codex --profile m27
ds doctor --codex-profile m27
ds --codex-profile m27
```

If you need one specific Codex binary for this run, use:

```bash
ds doctor --codex /absolute/path/to/codex --codex-profile m27
ds --codex /absolute/path/to/codex --codex-profile m27
```

This is the simplest path. You do not need to edit `runners.yaml` just to try one provider-backed session.

### 3. Persistent provider profile

Use this when you want DeepScientist to keep using the same profile by default.

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

Important:

- keep `model: inherit` for provider-backed Codex profiles unless you are certain the provider accepts the explicit model id you plan to send
- DeepScientist now launches Codex from an isolated runtime home under `.ds/codex-home`, but that runtime copy inherits your configured `~/.codex` auth, config, skills, agents, and prompts first

## Provider matrix

| Provider | Official docs | Codex login needed | What DeepScientist should use |
|---|---|---|---|
| OpenAI | use the normal Codex setup | Yes | no profile; run `ds` |
| MiniMax | [MiniMax Codex CLI](https://platform.minimaxi.com/docs/coding-plan/codex-cli) | No | your Codex profile, for example `ds --codex-profile m27` |
| GLM | [GLM Coding Plan: Other Tools](https://docs.bigmodel.cn/cn/coding-plan/tool/others) | No | a Codex profile that targets the GLM coding endpoint |
| Volcengine Ark | [Ark Coding Plan Overview](https://www.volcengine.com/docs/82379/1925114?lang=zh) | No | a Codex profile that targets the Ark coding endpoint |
| Alibaba Bailian | [Bailian Coding Plan: Other Tools](https://help.aliyun.com/zh/model-studio/other-tools-coding-plan) | No | a Codex profile that targets the Bailian coding endpoint |

## OpenAI

### What to prepare

- a normal Codex CLI install
- a successful `codex login` or `codex` interactive first-run setup

### DeepScientist commands

```bash
ds doctor
ds
```

### Persistent runner config

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: ""
  model: gpt-5.4
```

## MiniMax

MiniMax is the clearest profile-based case. Its official Codex CLI guide configures a custom Codex provider and sets `requires_openai_auth = false`.

Official doc:

- <https://platform.minimaxi.com/docs/coding-plan/codex-cli>

### Verified compatibility note

Checked against MiniMax's current Codex CLI doc and local compatibility validation on 2026-04-04:

- MiniMax's Codex CLI page currently recommends `@openai/codex@0.57.0`
- the Coding Plan endpoint to use is `https://api.minimaxi.com/v1`
- MiniMax's official page uses `m21` as the profile name, but that profile name is only a local alias; this repo uses `m27` consistently in examples
- the `codex-MiniMax-*` model names shown on MiniMax's page did not pass reliably through Codex CLI in local testing with the provided key
- the locally verified DeepScientist working paths were `MiniMax-M2.7` + `m27` + Codex CLI `0.57.0` and `MiniMax-M2.5` + `m25` + Codex CLI `0.57.0`
- the current `@openai/codex` latest release still does not line up cleanly with MiniMax's current guide

If you want the most reproducible DeepScientist + MiniMax path today, use Codex CLI `0.57.0`.

### What to prepare

- Codex CLI `0.57.0`
- a MiniMax `Coding Plan Key`
- `MINIMAX_API_KEY` available in the shell that starts Codex and DeepScientist
- for plain terminal `codex --profile <name>` checks, the current shell cleared of `OPENAI_API_KEY` and `OPENAI_BASE_URL`
- a working Codex profile in `~/.codex/config.toml`

### Install Codex CLI `0.57.0`

The simplest path is to pin the global Codex install:

```bash
npm install -g @openai/codex@0.57.0
codex --version
```

Expected output:

```text
codex-cli 0.57.0
```

If you want to keep another Codex version elsewhere, create a small wrapper script and point `runners.codex.binary` at that absolute path.

When DeepScientist detects a MiniMax profile at startup and the active Codex CLI is not `0.57.0`, it now prompts to reinstall `@openai/codex@0.57.0` automatically in interactive terminal launches.

### Codex-side setup

Use `https://api.minimaxi.com/v1`, not `https://api.minimax.io/v1`.

MiniMax's doc requires clearing the OpenAI environment variables first:

```bash
unset OPENAI_API_KEY
unset OPENAI_BASE_URL
export MINIMAX_API_KEY="..."
```

For plain terminal validation, keep doing that exactly as shown above.
For the DeepScientist path, when the selected provider sets `requires_openai_auth = false`, DeepScientist now strips `OPENAI_API_KEY` and `OPENAI_BASE_URL` automatically during the startup probe and real runner execution.

MiniMax's official page uses `m21` as the example profile name. Since the profile name is only a local alias, this repo rewrites that example to `m27`.

The important difference is the model name:

- MiniMax's page currently shows `codex-MiniMax-M2.5`
- in local testing, direct MiniMax API calls worked with `MiniMax-M2.7` and `MiniMax-M2.5`
- the reproducible DeepScientist paths were `MiniMax-M2.7` on profile `m27` and `MiniMax-M2.5` on profile `m25`
- for the `m25` path, use `MiniMax-M2.5`, not `codex-MiniMax-M2.5`

So the config below is the currently recommended DeepScientist configuration:

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

If you want the same DeepScientist path on `m25`, keep the provider block unchanged and use:

```toml
[profiles.m25]
model = "MiniMax-M2.5"
model_provider = "minimax"
```

What DeepScientist supports now:

- if you use this profile-only MiniMax config with Codex CLI `0.57.0`, DeepScientist automatically promotes the selected profile's `model_provider` and `model` to the top level inside its probe/runtime copy of `config.toml`
- DeepScientist forces provider-backed MiniMax runs to use `model: inherit`, so it does not accidentally override the profile with a hard-coded OpenAI model
- when `requires_openai_auth = false`, DeepScientist strips conflicting `OPENAI_API_KEY` and `OPENAI_BASE_URL` values from the probe/runtime environment
- this means DeepScientist can start even when plain terminal `codex --profile m27` still fails on that exact profile-only shape

If you want plain terminal `codex --profile <name>` to work too, use the explicit top-level compatibility form instead:

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

Then:

```bash
codex --profile m27
```

### DeepScientist commands

```bash
ds doctor --codex-profile m27
ds --codex-profile m27
```

### Persistent runner config

```yaml
codex:
  enabled: true
  binary: /tmp/codex057-wrapper
  config_dir: ~/.codex
  profile: m27
  model: inherit
  model_reasoning_effort: high
```

If you already pinned your global `codex` binary to `0.57.0`, you can set `binary: codex` instead. The absolute wrapper path here is only to make the version choice explicit.

If you do not want to persist that path in `runners.yaml`, you can keep `binary: codex` there and launch ad hoc with:

```bash
ds --codex /absolute/path/to/codex --codex-profile m27
```

DeepScientist now does two MiniMax-specific compatibility steps for the `0.57.0` path:

- it downgrades `xhigh` to `high` automatically when the Codex CLI does not support `xhigh`
- it auto-adapts MiniMax's profile-only `model_provider` / `model` shape inside the temporary DeepScientist Codex home when needed
- it removes conflicting `OPENAI_*` auth variables automatically when the provider explicitly says `requires_openai_auth = false`

## GLM

GLM documents the Coding Plan as an OpenAI-compatible coding endpoint rather than a dedicated Codex login flow.

Official docs:

- <https://docs.bigmodel.cn/cn/coding-plan/tool/others>
- <https://docs.bigmodel.cn/cn/coding-plan/faq>

### Official provider values

- Base URL: `https://open.bigmodel.cn/api/coding/paas/v4`
- API key: your GLM Coding Plan key
- Model: `GLM-4.7` for the documented path, or `GLM-5` where supported

### Recommended Codex adaptation

GLM does not currently publish a separate Codex CLI page in the same style as MiniMax. The practical DeepScientist path is:

1. create a Codex profile in `~/.codex/config.toml` that points to the GLM coding endpoint above
2. make sure `codex --profile glm` works in a terminal first
3. run DeepScientist with the same profile

### DeepScientist commands

```bash
ds doctor --codex-profile glm
ds --codex-profile glm
```

### Persistent runner config

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: glm
  model: inherit
```

## Volcengine Ark

Volcengine Ark explicitly lists Codex CLI as a supported coding tool.

Official doc:

- <https://www.volcengine.com/docs/82379/1925114?lang=zh>

### Official provider values

- OpenAI-compatible Base URL: `https://ark.cn-beijing.volces.com/api/coding/v3`
- Supported coding models: `doubao-seed-code-preview-latest`, `ark-code-latest`
- Use the Coding Plan key and the exact Coding Plan endpoint

### Recommended Codex adaptation

Create a Codex profile that targets the Ark coding endpoint and test it directly first:

```bash
codex --profile ark
```

Then start DeepScientist with the same profile:

```bash
ds doctor --codex-profile ark
ds --codex-profile ark
```

### Persistent runner config

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: ark
  model: inherit
```

## Alibaba Bailian

Bailian documents Coding Plan as an OpenAI-compatible coding endpoint. It requires the Coding Plan-specific key and endpoint, not the generic platform endpoint.

Official docs:

- <https://help.aliyun.com/zh/model-studio/other-tools-coding-plan>
- <https://help.aliyun.com/zh/model-studio/coding-plan-faq>

### Official provider values

- OpenAI-compatible Base URL: `https://coding.dashscope.aliyuncs.com/v1`
- API key: Coding Plan-specific key, typically `sk-sp-...`
- Model: choose a Coding Plan-supported model from the current Bailian overview

### Recommended Codex adaptation

Create a Codex profile that points to the Bailian Coding Plan endpoint and test it directly first:

```bash
codex --profile bailian
```

Then start DeepScientist with the same profile:

```bash
ds doctor --codex-profile bailian
ds --codex-profile bailian
```

### Persistent runner config

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: bailian
  model: inherit
```

## Troubleshooting checklist

If a provider-backed profile still fails in DeepScientist:

1. run `codex --profile <name>` manually first
2. confirm the provider API key is present in the same shell
3. confirm the provider-specific Base URL is the Coding Plan endpoint, not the generic API endpoint
4. keep DeepScientist runner `model: inherit` unless you need an explicit override
5. run `ds doctor --codex-profile <name>`
6. only after that run `ds --codex-profile <name>`
