# 21 Local Model Backends Guide: vLLM, Ollama, and SGLang

This guide explains how to run DeepScientist against local model backends such as vLLM, Ollama, and SGLang.

First, keep the layering clear:

- DeepScientist does not call the local model server directly
- DeepScientist calls a runner CLI: `codex`, `claude`, or `opencode`
- the local backend must work in that runner first, and DeepScientist then reuses it

If you use the Codex runner, the `/v1/responses` checks below are important.
If you use OpenCode or Claude Code, first read the Ollama sections in:

- [24 Claude Code Setup](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
- [25 OpenCode Setup](./25_OPENCODE_PROVIDER_SETUP.md)

The key point is simple:

- current Codex CLI requires `wire_api = "responses"`
- a backend that only works through `/v1/chat/completions` is not enough
- you must verify `/v1/responses` before expecting `ds` or `ds doctor` to succeed

There is one practical fallback:

- if your backend is chat-only, you may still be able to use it through **Codex CLI `0.57.0`**
- that older path can still work with `wire_api = "chat"` when the provider is configured at the top level
- DeepScientist now checks this automatically during the Codex startup probe; if it sees `wire_api = "chat"` on any active provider config, it requires `codex-cli 0.57.0` before continuing

## 1. What DeepScientist actually depends on

DeepScientist does not talk to vLLM, Ollama, or SGLang directly.

It talks to:

- `codex`
- and `codex` talks to your configured provider profile in `~/.codex/config.toml`

So the compatibility chain is:

1. your local backend
2. Codex profile
3. Codex startup probe
4. DeepScientist runner

If step 2 or step 3 fails, DeepScientist cannot start the Codex runner successfully.

## 2. The current Codex rule you must know

On the current Codex CLI:

- `wire_api = "responses"` is supported
- `wire_api = "chat"` is rejected

In practice that means:

- `vLLM`: recommended if its OpenAI-compatible server exposes `/v1/responses`
- `Ollama`: only use it if your installed version exposes `/v1/responses`
- `SGLang`: if your deployment only supports `/v1/chat/completions`, it is not compatible with the latest Codex runner

## 2.1 Support summary

| Backend | `/v1/chat/completions` | `/v1/responses` | Latest Codex | Codex `0.57.0` fallback |
|---|---|---|---|---|
| vLLM | yes | yes | supported | usually unnecessary |
| Ollama | yes | depends on version | supported only when `/v1/responses` works | possible if it is chat-only |
| SGLang | yes | often missing or incomplete | not supported when it is chat-only | possible fallback path |

## 3. Test the backend first

Before touching DeepScientist, verify the backend directly.

### Step 1: list models

```bash
curl http://127.0.0.1:8004/v1/models \
  -H "Authorization: Bearer 1234"
```

You need one real model id from this output, for example:

```text
/model/gpt-oss-120b
```

### Step 2: test chat completions

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

If this works, the backend is at least OpenAI-chat-compatible.

### Step 3: test Responses API

```bash
curl http://127.0.0.1:8004/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 1234" \
  -d '{
    "model": "/model/gpt-oss-120b",
    "input": "Reply with exactly HELLO."
  }'
```

This is the decisive test.

If `/v1/responses` fails, the latest Codex CLI will not work with this backend profile.

## 4. What we actually observed on this server

We tested the local backend at `http://127.0.0.1:8004/v1`.

Observed behavior:

- `GET /v1/models` succeeded
- `POST /v1/chat/completions` succeeded
- `POST /v1/responses` returned `500 Internal Server Error`
- the `/v1/models` payload reported `owned_by: "sglang"`

So this specific `8004` deployment behaves like a chat-compatible SGLang-style server, not a Codex-compatible Responses backend.

That means:

- it can answer raw chat requests
- but it cannot currently be used by the latest Codex runner
- and therefore DeepScientist cannot use it through the normal Codex path

We also tested an older Codex path:

- latest Codex + `wire_api = "responses"` failed against this backend
- Codex `0.57.0` + top-level `model_provider` / `model` + `wire_api = "chat"` succeeded

So for this server specifically:

- **latest Codex path**: no
- **Codex `0.57.0` fallback**: yes

## 5. Codex profile example for a local Responses-compatible backend

If your backend really supports `/v1/responses`, create a profile like this:

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

Then test Codex directly first:

```bash
export LOCAL_API_KEY=1234
codex exec --profile local_vllm --json --cd /tmp --skip-git-repo-check - <<'EOF'
Reply with exactly HELLO.
EOF
```

If this fails, do not continue to DeepScientist yet.

## 5.1 Chat-only fallback for Codex `0.57.0`

If your backend only supports `/v1/chat/completions`, you can try this fallback path:

1. install Codex `0.57.0`
2. use `wire_api = "chat"`
3. put `model_provider` and `model` at the top level

Example:

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

Then test:

```bash
export LOCAL_API_KEY=1234
codex exec --json --cd /tmp --skip-git-repo-check - <<'EOF'
Reply with exactly HELLO.
EOF
```

If this older Codex path works, DeepScientist can usually reuse it with the same runner binary and profile strategy.

## 6. DeepScientist commands after Codex works

Once the direct Codex check works, run:

```bash
ds doctor --codex-profile local_vllm
ds --codex-profile local_vllm
```

`ds doctor` is the canonical command.

`ds docker` is only a legacy alias for `ds doctor`; it is not a Docker deployment command.

If you want to persist it in DeepScientist:

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

## 7. Backend compatibility summary

### vLLM

Recommended.

Use it when:

- `/v1/models` works
- `/v1/responses` works
- the model id is visible and stable

If those are true, vLLM is the cleanest current local path for Codex + DeepScientist.

### Ollama

Conditionally supported.

Use it only when:

- your Ollama version exposes `/v1/responses`
- your target model works through that endpoint

If Ollama only gives you chat-completions semantics, it is not enough for the latest Codex CLI, but it may still be usable through Codex `0.57.0`.

### SGLang

Be careful.

If your SGLang deployment behaves like this:

- `/v1/chat/completions` works
- `/v1/responses` fails

then it is not currently compatible with the latest Codex runner.

If you must use that backend anyway, the realistic fallback is Codex `0.57.0` with `wire_api = "chat"`.

## 8. What to do if you only have chat-completions

If your backend only supports `/v1/chat/completions`, you currently have four practical options:

1. switch to a Responses-compatible backend such as vLLM
2. upgrade to an Ollama release that really exposes `/v1/responses`
3. downgrade the Codex CLI path to `0.57.0` and use `wire_api = "chat"`
4. place a Responses-compatible proxy in front of the backend

Right now, this is a Codex CLI limitation, not a DeepScientist-only setting mistake.

## 8.1 Which Ollama route should you use?

Ollama now documents several integration routes:

- OpenAI-compatible API: `http://localhost:11434/v1`
- Codex integration: `https://docs.ollama.com/integrations/codex`
- Claude Code integration: `https://docs.ollama.com/integrations/claude-code`
- OpenCode integration: `https://docs.ollama.com/integrations/opencode`

So Ollama is not a single-path setup.

| Goal | Recommended runner | Validate first |
|---|---|---|
| Stay close to the default DeepScientist Codex path | Codex | `ollama run`, `/v1/responses`, `codex exec --profile <ollama-profile>` |
| Avoid Codex Responses compatibility details | OpenCode | `opencode run --model ollama/<model>` or a custom provider model string |
| Use Claude Code with an Anthropic-compatible local endpoint | Claude Code | `claude -p --model <ollama-model>` with `ANTHROPIC_BASE_URL=http://localhost:11434` |

Suggested order for new users:

1. use OpenCode first if you just want Ollama running quickly
2. use Codex if you already understand Codex profiles and `/v1/responses` passes
3. use Claude Code if you specifically want the Claude runner path

### Ollama + Codex minimum path

```bash
ollama serve
ollama pull gpt-oss:20b
ollama run gpt-oss:20b "Reply with exactly HELLO."

curl http://localhost:11434/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-oss:20b","input":"Reply with exactly HELLO."}'
```

Then create `~/.codex/config.toml` profile:

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

Validate:

```bash
codex exec --profile ollama-local "Reply with exactly OK."
ds doctor --codex-profile ollama-local
```

### Ollama + OpenCode minimum path

```bash
ollama serve
ollama pull gpt-oss:20b
opencode run --format json --pure --model ollama/gpt-oss:20b "Reply with exactly HELLO."
ds doctor --runner opencode
```

If OpenCode does not recognize `ollama/<model>`, use the `local_ollama` custom provider example in [25 OpenCode Setup](./25_OPENCODE_PROVIDER_SETUP.md).

### Ollama + Claude Code minimum path

```bash
ollama serve
ollama pull gpt-oss:20b

export ANTHROPIC_AUTH_TOKEN=ollama
export ANTHROPIC_BASE_URL=http://localhost:11434
claude -p --output-format json --model gpt-oss:20b --tools "" "Reply with exactly HELLO."

ds doctor --runner claude
```

DeepScientist Claude runner config:

```yaml
claude:
  enabled: true
  model: gpt-oss:20b
  env:
    ANTHROPIC_AUTH_TOKEN: "ollama"
    ANTHROPIC_BASE_URL: "http://localhost:11434"
```

## 9. Recommended workflow

Use this order every time:

1. test `/v1/models`
2. test `/v1/responses`
3. test `codex exec --profile <name>`
4. test `ds doctor --codex-profile <name>`
5. only then launch `ds --codex-profile <name>`

If step 2 fails, stop there. Do not expect DeepScientist to succeed through the latest Codex path.
