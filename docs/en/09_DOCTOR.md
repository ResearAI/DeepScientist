# 09 `ds doctor`: Repair Startup and Environment Problems

Use `ds doctor` when DeepScientist does not start cleanly after installation.

## Recommended flow

1. Install DeepScientist:

   ```bash
   npm install -g @researai/deepscientist
   ```

2. Make sure Codex itself is working first:

   Default OpenAI path:

   ```bash
   codex login
   ```

   Provider-backed profile path:

   ```bash
   codex --profile m27
   ```

   If `codex` is missing, repair it explicitly with:

   ```bash
   npm install -g @openai/codex
   ```

3. Try to start DeepScientist:

   ```bash
   ds
   ```

4. If startup fails or looks unhealthy, run:

   ```bash
   ds doctor
   ```

5. Read the checks from top to bottom and fix the failed items first.

6. Run `ds doctor` again until all checks are healthy, then run `ds`.

## What `ds doctor` checks

- local Python runtime health
- whether `~/DeepScientist` exists and is writable
- whether `uv` is available to manage the local Python runtime
- whether `git` is installed and configured
- whether required config files are valid
- whether the enabled/default runner configuration is internally consistent
- whether the Codex CLI can be found and passes a startup probe
- whether a recent quest runtime failure already points to a known provider / protocol / retry problem
- whether an optional local `pdflatex` runtime is available for paper PDF compilation
- whether the web and TUI bundles exist
- whether the configured web port is free or already running the correct daemon

`ds doctor` now tries to render failed checks in a more operational form:

- `Problem`: what failed
- `Why`: why DeepScientist believes it failed
- `Fix`: the concrete next steps to try
- `Evidence`: the quest/run/request clues that matched the diagnosis

## Common fixes

### Codex is missing

DeepScientist prefers the `codex` already available on your machine and only uses the bundled dependency as fallback. If neither is present, run the package install again so the bundled Codex dependency is present:

```bash
npm install -g @researai/deepscientist
```

If `codex` is still unavailable afterward, install it explicitly:

```bash
npm install -g @openai/codex
```

### Codex is installed but not logged in

Run:

```bash
codex login
```

If you prefer the interactive first-run flow, run `codex` and finish the setup there.

Finish login once, then rerun `ds doctor`.

### Codex profile works in the terminal, but DeepScientist still fails

Run DeepScientist with the same profile explicitly:

```bash
ds doctor --codex-profile m27
ds --codex-profile m27
```

If your working Codex CLI is not the one on `PATH`, point DeepScientist at it explicitly:

```bash
ds doctor --codex /absolute/path/to/codex --codex-profile m27
ds --codex /absolute/path/to/codex --codex-profile m27
```

`m27` is the MiniMax profile name used consistently in this repo. MiniMax's own page currently uses `m21`, but the profile name is only a local alias; if you created a different name, use that same name in both commands.

Also check:

- the same shell still exports the provider API key
- if `codex --profile <name>` works but `ds doctor` or `ds docker` still reports a missing provider environment variable, also put that key in `~/DeepScientist/config/runners.yaml` under `runners.codex.env`
- the profile points at the provider's Coding Plan endpoint, not the generic API endpoint
- if you are using Qwen through Alibaba Bailian, use the Bailian Coding Plan endpoint only; the generic Bailian or DashScope Qwen API is not supported here
- `~/DeepScientist/config/runners.yaml` uses `model: inherit` if the provider expects the model to come from the profile itself

MiniMax-specific note:

- if MiniMax fails on the current `@openai/codex` latest, install `npm install -g @openai/codex@0.57.0`
- when DeepScientist detects a MiniMax profile on startup and the installed Codex CLI is not `0.57.0`, it now offers to reinstall `0.57.0` automatically in interactive terminal launches
- create a MiniMax `Coding Plan Key` first
- for plain terminal `codex --profile <name>` checks, clear `OPENAI_API_KEY` and `OPENAI_BASE_URL` in the current shell before exporting `MINIMAX_API_KEY`
- use `https://api.minimaxi.com/v1`
- the `codex-MiniMax-*` model names shown on MiniMax's current Codex CLI page did not pass reliably through Codex CLI in local testing with the provided key
- the locally verified DeepScientist model names are `MiniMax-M2.7` and `MiniMax-M2.5`
- for `m25`, use `MiniMax-M2.5`, not `codex-MiniMax-M2.5`
- DeepScientist can auto-adapt MiniMax's profile-only `model_provider` / `model` config shape during probe and runtime
- DeepScientist also strips conflicting `OPENAI_*` auth variables automatically for providers that set `requires_openai_auth = false`
- if you also want plain terminal `codex --profile <name>` to work directly, put `model_provider = "minimax"` and the matching top-level model such as `MiniMax-M2.7` or `MiniMax-M2.5` in `~/.codex/config.toml`
- DeepScientist automatically downgrades `xhigh` to `high` when it detects a Codex CLI older than `0.63.0`
- if the provider returns `tool call result does not follow tool call (2013)`, treat it as a request-ordering/protocol error rather than a transient network failure
- if the provider returns malformed tool-call argument errors such as `invalid function arguments json string` or `failed to parse tool call arguments`, fix the tool-call serialization path before retrying again

### The configured Codex model is unavailable

DeepScientist blocks startup until Codex passes a real startup hello probe. In the current release, that probe first uses the runner model configured in:

```text
~/DeepScientist/config/runners.yaml
```

The default is `gpt-5.4`. If your Codex account or CLI config cannot access that model, DeepScientist now retries with the current Codex default model and persists `model: inherit` for future runs. If you still want a specific model, edit the runner config manually and rerun:

```bash
ds doctor
```

For provider-backed Codex profiles, `model: inherit` is usually the right default.

### `uv` is missing

Normally `ds` will bootstrap a local `uv` automatically. If that bootstrap fails, install it manually:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On Windows PowerShell (still strongly recommend WSL2 for regular DeepScientist use):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Local paper PDF compilation is unavailable

DeepScientist can compile papers without a full TeX Live install if you add a lightweight TinyTeX runtime:

```bash
ds latex install-runtime
```

If you prefer a system package instead, install a distribution that provides `pdflatex` and `bibtex`.

### Port `20999` is busy

If it is your managed daemon:

```bash
ds --stop
```

Then run `ds` again.

If another service already uses the port, change `ui.port` in:

```text
~/DeepScientist/config/config.yaml
```

Or start on another port directly:

```bash
ds --port 21000
```

### Python `3.10` or older is active

DeepScientist still prefers the active conda environment when it already satisfies Python `>=3.11`.

If your current conda environment is too old, either activate a newer one:

```bash
conda activate ds311
python3 --version
which python3
ds
```

Or create a suitable one:

```bash
conda create -n ds311 python=3.11 -y
conda activate ds311
ds
```

If you do nothing, `ds` can still bootstrap a managed `uv` + Python runtime automatically under the DeepScientist home.

### Git user identity is missing

Run:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

### Runner switching and enablement

Current releases support `codex`, `claude`, and `opencode`.

If a non-default runner was enabled by mistake, check:

```text
~/DeepScientist/config/config.yaml
~/DeepScientist/config/runners.yaml
```

Then confirm:

- `default_runner` points at the runner you actually want
- the selected runner has `enabled: true`
- disabled runners stay disabled if you are not using them
- `ds doctor` passes for the enabled runner before you switch quests over

## Notes

- `ds docker` is kept as a compatibility alias, but the official command is `ds doctor`.
- The default browser URL stays in the plain local form, for example `http://127.0.0.1:20999`.
- When local browser auth is enabled, DeepScientist shows a password modal before loading the workspace.
- You can view the current password in the launch terminal or through `ds --status`.
- By default the password modal is disabled; use `ds --auth true` when you want the local browser password gate for one launch.
