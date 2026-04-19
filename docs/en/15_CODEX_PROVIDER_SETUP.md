# 15 Codex Provider Setup

DeepScientist does not maintain a separate provider adapter layer for MiniMax, GLM, Volcengine Ark, Alibaba Bailian, or other Codex-compatible services.

It reuses the Codex CLI that already works on your machine.

The right mental model is:

1. make `codex` work first
2. confirm the same config works in a terminal
3. run `ds doctor`
4. only then run `ds` or `ds --codex-profile <name>`

If Codex itself is not working yet, fixing DeepScientist first is the wrong order.

For the other built-in runners, see also:

- [24 Claude Code Setup](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
- [25 OpenCode Setup](./25_OPENCODE_PROVIDER_SETUP.md)

## What files matter

Codex CLI reads its local state from `~/.codex/`.

The most important files are:

- `~/.codex/config.toml`
  - your provider, model, profile, and feature configuration
- `~/.codex/auth.json`
  - created by `codex login` when the provider uses the normal OpenAI login flow
- `~/.codex/history.jsonl`
  - local session history; not required for setup

Useful inspection commands:

```bash
ls -la ~/.codex
sed -n '1,220p' ~/.codex/config.toml
codex --version
codex --help
codex exec --help
```

## Recommended setup order

Always follow this order:

1. install Codex CLI and confirm the binary is the one you expect
2. prepare `~/.codex/config.toml`
3. validate `codex` or `codex --profile <name>` directly
4. validate DeepScientist with `ds doctor`
5. launch DeepScientist with the same Codex profile

## Step 1: confirm the Codex binary

Check which Codex is actually being used:

```bash
which codex
codex --version
```

If you need a specific binary, keep its absolute path and pass it to DeepScientist with `--codex`.

Example:

```bash
ds doctor --codex /absolute/path/to/codex --codex-profile glm
ds --codex /absolute/path/to/codex --codex-profile glm
```

## Step 2: understand the two common Codex configuration shapes

### A. OpenAI login shape

Use this when Codex works through normal OpenAI authentication.

Typical flow:

```bash
codex login
codex
```

In this case, `~/.codex/auth.json` is usually present, and `config.toml` may stay minimal.

Minimal example:

```toml
model = "gpt-5.4"
model_reasoning_effort = "high"

[projects."/absolute/path/to/your/project"]
trust_level = "trusted"
```

### B. Explicit provider shape in `config.toml`

Use this when you are pointing Codex at a non-default provider or gateway.

A common pattern is:

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

Another common pattern uses an environment variable instead of embedding a bearer token:

```toml
[model_providers.myprovider]
name = "My Provider"
base_url = "https://example.com/codex"
wire_api = "chat"
env_key = "MYPROVIDER_API_KEY"
requires_openai_auth = false
```

Then export the key in the shell before starting Codex or DeepScientist:

```bash
export MYPROVIDER_API_KEY="..."
```

## Step 3: understand the most important `config.toml` fields

These are the fields you usually need to touch.

### Top-level fields

- `model_provider`
  - which provider block to use by default
- `model`
  - the model id to send by default
- `model_reasoning_effort`
  - for example `medium`, `high`, or `xhigh`
- `service_tier`
  - optional provider-specific runtime preference

### Provider block fields

Inside `[model_providers.<name>]`:

- `name`
  - human-readable label
- `base_url`
  - the exact provider endpoint Codex should call
- `wire_api`
  - usually `responses` or `chat`; use the provider's documented format
- `env_key`
  - name of the shell environment variable containing the API key
- `experimental_bearer_token`
  - fixed bearer token if your provider setup uses one directly
- `requires_openai_auth`
  - whether Codex should still expect the standard OpenAI auth shape
- `request_max_retries`
  - optional request retry count
- `stream_max_retries`
  - optional stream retry count
- `stream_idle_timeout_ms`
  - optional stream idle timeout

### Profile fields

Profiles live under `[profiles.<alias>]`.

Example:

```toml
[profiles.glm]
model = "GLM-4.7"
model_provider = "glm"
```

Then use it with:

```bash
codex --profile glm
```

### Project trust

Codex also cares about project trust.

Example:

```toml
[projects."/ssdwork/deepscientist/DeepScientist"]
trust_level = "trusted"
```

If a project is not trusted, Codex may ask again before running.

## Step 4: a step-by-step profile workflow

This is the safest general workflow.

### 4.1 Edit `~/.codex/config.toml`

Start from your existing file:

```bash
cp ~/.codex/config.toml ~/.codex/config.toml.bak
${EDITOR:-vim} ~/.codex/config.toml
```

### 4.2 Add a provider block

Example skeleton:

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

### 4.3 Add a profile

```toml
[profiles.provider_alias]
model = "provider-model-id"
model_provider = "provider_name"
```

### 4.4 Validate Codex directly

Interactive check:

```bash
codex --profile provider_alias
```

Non-interactive smoke check:

```bash
codex exec --profile provider_alias "Reply with exactly OK."
```

If this fails, stop there and fix Codex first.

## Step 5: map that setup into DeepScientist

## Where to put the provider key

There are three different places people often confuse.

### 1. Shell environment

This is enough when you are only validating Codex directly in the current terminal.

Example:

```bash
export MINIMAX_API_KEY="..."
codex --profile m25
codex exec --profile m25 "Reply with exactly OK."
```

### 2. `~/.codex/config.toml`

This file usually tells Codex **which environment variable name** or **which bearer token field** it should use.
It does **not** guarantee that DeepScientist will magically receive that key in every runtime context.

Examples:

```toml
env_key = "MINIMAX_API_KEY"
```

or:

```toml
experimental_bearer_token = "YOUR_TOKEN_HERE"
```

Use `env_key` when the provider key comes from the shell or another process-level environment source.
Use `experimental_bearer_token` only when your Codex-side provider setup truly expects a fixed bearer token directly inside `config.toml`.

### 3. `~/DeepScientist/config/runners.yaml`

This is the most important place when `codex` works in your shell, but `ds doctor`, `ds`, or `ds docker` still fails with a missing provider environment variable.

In that case, put the required key under `runners.codex.env`.

Example:

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: m25
  model: inherit
  model_reasoning_effort: high
  env:
    MINIMAX_API_KEY: "YOUR_REAL_KEY"
```

This is the most reliable DeepScientist-side fix when the provider works in plain `codex --profile ...` but fails inside DeepScientist runner execution.

### Which one should you choose?

- If you are only testing Codex manually in one shell: shell `export` is enough.
- If you want Codex to know which variable name to read: set `env_key` in `~/.codex/config.toml`.
- If DeepScientist or `ds docker` still reports a missing provider env var: also set the key in `~/DeepScientist/config/runners.yaml` under `runners.codex.env`.

### Docker and daemon note

This is where most confusion comes from.

A shell-level `export MINIMAX_API_KEY=...` only affects the current shell and the processes spawned from it.
If DeepScientist is launched by another daemon, service, container, or supervisor process, that runtime may not inherit the same shell environment.

So for Docker or long-running daemon setups, `runners.yaml -> runners.codex.env` is usually the safer place.

There are three supported DeepScientist usage patterns.

### 1. Default OpenAI login path

```bash
codex login
ds doctor
ds
```

### 2. One-off provider profile

```bash
codex --profile glm
codex exec --profile glm "Reply with exactly OK."
ds doctor --codex-profile glm
ds --codex-profile glm
```

### 3. Persistent runner config

If you want DeepScientist to keep using the same Codex profile by default, set it in `runners.yaml`.

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

Important:

- `profile` should usually be your local Codex profile alias, such as `glm`, `ark`, `bailian`, `m25`, or `m27-local`
- for provider-backed Codex profiles, prefer `model: inherit`
- only hard-code `model:` in DeepScientist if you are sure the provider accepts that exact explicit model id
- DeepScientist launches Codex from an isolated runtime home under `.ds/codex-home`, but copies your configured `~/.codex` auth, config, skills, agents, and prompts into that runtime copy first

## One-off overrides without editing `config.toml`

Codex itself supports `-c key=value` overrides.

Examples:

```bash
codex -c model="gpt-5.4"
codex -c model_provider="yunyi" -c model="gpt-5.4"
codex exec -c model_reasoning_effort="high" "Reply with exactly OK."
```

This is useful for quick checks, but for repeatable DeepScientist runs, profiles in `~/.codex/config.toml` are cleaner.

## OpenAI

### What to prepare

- a working Codex install
- successful `codex login`
- a direct `codex` or `codex exec "Reply with exactly OK."` check

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

Official doc:

- <https://platform.minimaxi.com/docs/coding-plan/codex-cli>

MiniMax is the clearest profile-based case.

### Important compatibility note

MiniMax's official Coding Plan model `MiniMax-M2.7` is **not currently working reliably with Codex CLI** on the supported Codex path used by this repo.

For the official Codex-compatible path, use:

- `MiniMax-M2.5`
- profile alias such as `m25`
- Codex CLI `0.57.0` if you want the current highest-compatibility MiniMax Coding Plan path

If you specifically want `MiniMax-M2.7`, the recommended route is:

- do **not** treat it as the default official Codex Coding Plan path
- instead expose your own local OpenAI-compatible `vllm` endpoint for M2.7
- then point Codex at that local endpoint through a custom provider block in `~/.codex/config.toml`

### Recommended official Coding Plan path

Use the official MiniMax Coding Plan endpoint.

For key placement on the MiniMax path:

- `~/.codex/config.toml` should usually contain `env_key = "MINIMAX_API_KEY"`
- for plain terminal validation, export `MINIMAX_API_KEY` in that same shell
- if `codex --profile m25` works but `ds doctor` or `ds docker` still says a provider env var is missing, also place the real key in `~/DeepScientist/config/runners.yaml` under `runners.codex.env.MINIMAX_API_KEY`

Use the official MiniMax Coding Plan endpoint:

- Base URL: `https://api.minimaxi.com/v1`
- API key env: `MINIMAX_API_KEY`
- Model: `MiniMax-M2.5`

Recommended config shape:

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

Validation order:

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

### If you want MiniMax-M2.7 anyway

Recommended route: run M2.7 behind your own local OpenAI-compatible `vllm` service.

Example shape:

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

Then validate it exactly the same way:

```bash
export OPENAI_API_KEY="dummy-or-local-token-if-needed"
codex --profile m27-local
codex exec --profile m27-local "Reply with exactly OK."
ds doctor --codex-profile m27-local
ds --codex-profile m27-local
```

### Persistent runner config

Official Coding Plan path:

```yaml
codex:
  enabled: true
  binary: codex
  config_dir: ~/.codex
  profile: m25
  model: inherit
  model_reasoning_effort: high
```

Local vLLM M2.7 path:

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

Official docs:

- <https://docs.bigmodel.cn/cn/coding-plan/tool/others>
- <https://docs.bigmodel.cn/cn/coding-plan/faq>

Official values from current public guidance:

- Base URL: `https://open.bigmodel.cn/api/coding/paas/v4`
- Model: `GLM-4.7` or another currently documented Coding Plan model

Recommended workflow:

1. add a GLM provider block in `~/.codex/config.toml`
2. add a profile such as `[profiles.glm]`
3. run `codex --profile glm`
4. run `codex exec --profile glm "Reply with exactly OK."`
5. run `ds doctor --codex-profile glm`
6. run `ds --codex-profile glm`

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

Official doc:

- <https://www.volcengine.com/docs/82379/1925114?lang=zh>

Official values from current public guidance:

- Base URL: `https://ark.cn-beijing.volces.com/api/coding/v3`
- Models: `doubao-seed-code-preview-latest`, `ark-code-latest`

Recommended workflow:

```bash
codex --profile ark
codex exec --profile ark "Reply with exactly OK."
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

Official docs:

- <https://help.aliyun.com/zh/model-studio/other-tools-coding-plan>
- <https://help.aliyun.com/zh/model-studio/coding-plan-faq>

Important:

- supported: Qwen through the Bailian **Coding Plan** endpoint
- not supported here: the generic Bailian / DashScope Qwen platform API

Official values from current public guidance:

- Base URL: `https://coding.dashscope.aliyuncs.com/v1`
- key shape: Coding Plan-specific key, usually `sk-sp-...`

Recommended workflow:

```bash
codex --profile bailian
codex exec --profile bailian "Reply with exactly OK."
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

If a provider-backed profile still fails:

1. check `which codex` and `codex --version`
2. inspect `~/.codex/config.toml`
3. verify the provider block exists and the profile points to it
4. verify the API key or bearer token is actually available
5. verify the Base URL is the Coding Plan or Codex-compatible endpoint, not a generic platform endpoint
6. run `codex --profile <name>` first
7. run `codex exec --profile <name> "Reply with exactly OK."`
8. run `ds doctor --codex-profile <name>`
9. only then run `ds --codex-profile <name>`

If `codex --profile <name>` fails but you believe the provider config is correct, fix Codex first. DeepScientist should not be the first place you debug provider auth.
