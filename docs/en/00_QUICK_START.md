# 00 Quick Start: Launch DeepScientist and Run Your First Project

Think of DeepScientist as a local workspace for long-running research tasks. You define the task, prepare the resources it needs, and DeepScientist keeps the files, branches, notes, and results on your machine.

This guide is written for first-time users. It is intentionally hands-on: one step, one action, one explanation.

You will do four things:

1. install DeepScientist
2. start the local runtime
3. open the home page
4. create a real project with a worked example

The screenshots in this guide use the current live web UI at `deepscientist.cc:20999` as an example. Your local UI at `127.0.0.1:20999` should look the same or very close.

Current platform support: DeepScientist fully supports Linux and macOS. Native Windows support is currently experimental (strongly recommend WSL2 when you want the closest Linux-like terminal behavior).

## Safety First: Isolate Before You Start

Before your first DeepScientist run, strongly adopt this baseline:

- if your environment allows it, prefer Docker, a virtual machine, or an equivalent isolation boundary
- always run DeepScientist under a non-root account
- do not use a production host, critical server, or sensitive-data machine for the first run
- do not casually share a `0.0.0.0` binding, reverse-proxy URL, or the web entry with other people
- if you plan to bind WeChat, QQ, Lingzhu, or other connectors later, be even more conservative about public exposure

The reason is simple: DeepScientist can execute commands, modify files, install dependencies, send external messages, and read or write project data. If you give it too much privilege, or expose it carelessly, the outcome can include server damage, data loss, secret leakage, connector misuse, or fabricated research outputs that are not caught in time.

See the full notice here:

- [11 License And Risk Notice](./11_LICENSE_AND_RISK.md)

## 0. Before You Start

Prepare these first:

- Node.js `>=18.18` and npm `>=9`; install them from the official download page: https://nodejs.org/en/download
- one working runner path:
  - `codex` is the primary and most battle-tested path
  - `claude` is supported experimental and should already work as `claude` in your shell
  - `opencode` is supported experimental and should already work as `opencode` in your shell
- a model or API credential if your project needs external inference
- GPU or server access if your experiments are compute-heavy
- if you plan to run DeepScientist for real work, prepare Docker or another isolated environment and a dedicated non-root user
- code, data, or repository links if the task starts from an existing baseline
- optionally, one connector such as QQ if you want updates outside the web workspace

If you are still choosing a coding plan or subscription, these are practical starting points:

- If you just want one simple starting recommendation, start with GPT-5.4 using `xhigh` reasoning effort, or Gemini 3 Pro using `gemini-3-pro-preview`.
- ChatGPT pricing: https://openai.com/chatgpt/pricing/
- ChatGPT Plus help: https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus%3F.eps
- MiniMax Coding Plan: https://platform.minimaxi.com/docs/guides/pricing-codingplan
- GLM Coding Plan: https://docs.bigmodel.cn/cn/coding-plan/overview
- Alibaba Cloud Bailian Coding Plan: https://help.aliyun.com/zh/model-studio/coding-plan
- Volcengine Ark Coding Plan: https://www.volcengine.com/docs/82379/1925115?lang=zh

If you plan to use Qwen through Alibaba Bailian, use the Bailian **Coding Plan** endpoint only. The generic Bailian or DashScope Qwen API is not supported in the Codex-backed DeepScientist path.

If you want the safest recommendation, start with Codex first.

Use the matching runner setup doc before your first real launch:

- [15 Codex Provider Setup](./15_CODEX_PROVIDER_SETUP.md)
- [24 Claude Code Setup](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
- [25 OpenCode Setup](./25_OPENCODE_PROVIDER_SETUP.md)

## 1. Install Node.js and DeepScientist

DeepScientist fully supports Linux and macOS. Native Windows support is currently experimental (strongly recommend WSL2 when you want the most reliable Linux-like shell behavior).

Before installing DeepScientist itself, install Node.js from the official page:

https://nodejs.org/en/download

Make sure your environment satisfies:

- Node.js `>=18.18`
- npm `>=9`

Run:

```bash
npm install -g @researai/deepscientist
```

This installs the `ds` command globally.

DeepScientist ships three built-in runner paths:

- `codex`: primary path
- `claude`: supported experimental
- `opencode`: supported experimental

Important installation detail:

- DeepScientist prefers the `codex` already available on your machine and only falls back to the bundled npm dependency when no local Codex path is available.
- DeepScientist does not auto-install or auto-authenticate Claude Code or OpenCode for you. For those two paths, make the CLI work first, then let DeepScientist reuse it.

If `codex` is still missing afterward, repair it explicitly:

```bash
npm install -g @openai/codex
```

If you want the most reliable path, verify the command immediately:

```bash
which codex
codex login
```

If `which codex` prints nothing, the issue is usually the npm global bin path rather than DeepScientist itself. Fix the shell PATH first, then rerun `npm install -g @openai/codex`.

If you want local PDF compilation later, also run:

```bash
ds latex install-runtime
```

This installs a lightweight TinyTeX runtime for local paper compilation.

## 2. Finish Your Chosen Runner Before The First `ds`

If you are undecided, choose `codex` first.

### 2.1 Codex: default OpenAI login path

Run:

```bash
codex login
```

If you prefer the interactive first-run flow, run:

```bash
codex
```

and finish the interactive authentication there.

Then verify:

```bash
ds doctor
```

### 2.2 Codex: provider-backed profile path

If you already use a named Codex profile for MiniMax, GLM, Volcengine Ark, Alibaba Bailian Coding Plan, or another provider-backed path, verify that profile first in a terminal:

```bash
codex --profile m27
```

Then run DeepScientist through the same profile:

```bash
ds doctor --codex-profile m27
```

and later:

```bash
ds --codex-profile m27
```

If you need one specific Codex binary for this run, add `--codex` too:

```bash
ds doctor --codex /absolute/path/to/codex --codex-profile m27
ds --codex /absolute/path/to/codex --codex-profile m27
```

`m27` is the MiniMax profile name used consistently in this repo. MiniMax's own page currently uses `m21`, but the profile name is only a local alias; if you created a different name, use that same name in all commands.

DeepScientist blocks startup until Codex can pass a real hello probe. The current default runner model in `~/DeepScientist/config/runners.yaml` is `inherit`. If your existing config still pins an explicit model while your provider expects the model to come from the profile itself, change it to `model: inherit`, or simply launch with `--codex-profile <name>` and let that session inherit the profile-defined model.

MiniMax note:

- if the current `@openai/codex` latest does not work with MiniMax, install `npm install -g @openai/codex@0.57.0`
- when DeepScientist detects a MiniMax profile on startup and the installed Codex CLI is not `0.57.0`, it now offers to reinstall `0.57.0` automatically in interactive terminal launches
- create a MiniMax `Coding Plan Key` first
- for plain terminal `codex --profile <name>` checks, clear `OPENAI_API_KEY` and `OPENAI_BASE_URL` in the current shell before exporting `MINIMAX_API_KEY`
- use `https://api.minimaxi.com/v1`
- the `codex-MiniMax-*` model names shown on MiniMax's current Codex CLI page did not pass reliably through Codex CLI in local testing with the provided key
- the locally verified DeepScientist model names are `MiniMax-M2.7` and `MiniMax-M2.5`
- for `m25`, use `MiniMax-M2.5`, not `codex-MiniMax-M2.5`
- DeepScientist can auto-adapt MiniMax's profile-only `model_provider` / `model` config shape during probe and runtime
- DeepScientist also strips conflicting `OPENAI_*` auth variables automatically for providers that set `requires_openai_auth = false`
- if you also want plain terminal `codex --profile <name>` to work directly, add `model_provider = "minimax"` and the matching top-level model such as `MiniMax-M2.7` or `MiniMax-M2.5` to `~/.codex/config.toml`
- DeepScientist automatically downgrades `xhigh` to `high` when it detects an older Codex CLI that does not support `xhigh`

### 2.3 Claude Code path

Use this when `claude` already works directly in your terminal.

The shortest validation path is:

```bash
claude --version
claude -p --output-format json --tools "" "Reply with exactly HELLO."
ds doctor --runner claude
```

Then launch DeepScientist through Claude Code:

```bash
ds --runner claude
```

If you want the full setup order, config mapping, and gateway notes, continue with:

- [24 Claude Code Setup](./24_CLAUDE_CODE_PROVIDER_SETUP.md)

### 2.4 OpenCode path

Use this when `opencode` already works directly in your terminal.

The shortest validation path is:

```bash
opencode --version
opencode run --format json --pure "Reply with exactly HELLO"
ds doctor --runner opencode
```

Then launch DeepScientist through OpenCode:

```bash
ds --runner opencode
```

If you want the full setup order, config mapping, and provider notes, continue with:

- [25 OpenCode Setup](./25_OPENCODE_PROVIDER_SETUP.md)

## 3. Start the Local Runtime

Run:

```bash
ds
```

This starts the local daemon and the web workspace.

If you want this launch to use a non-default runner, add `--runner`:

```bash
ds --runner claude
ds --runner opencode
```

If the target runner passes `ds doctor` and you want to keep using it, switch `config.default_runner` later in `~/DeepScientist/config/config.yaml` or in the Settings page.

Again, strongly recommended:

- prefer Docker or another isolated environment
- always run under a non-root user
- do not expose the service publicly for your first run

DeepScientist now uses `uv` to manage a locked local Python runtime. If a conda environment is already active and provides Python `>=3.11`, `ds` will prefer it. Otherwise it will bootstrap a managed Python under the DeepScientist home.

By default, the DeepScientist home is:

- macOS / Linux: `~/DeepScientist`

If you want to place the DeepScientist home under the current working directory instead, run:

```bash
ds --here
```

This is equivalent to `ds --home "$PWD/DeepScientist"`.

Important:  
* if you start DeepScientist with `ds --here`, later `ds --status`, `ds --stop`, and `ds --restart` run in the same directory will now usually prefer that local `./DeepScientist` home automatically  
* if you start with an explicit `--home <path>`, or you keep multiple DeepScientist homes on one machine, it is still safest to pass the same home explicitly for later management commands  
* using the same `DEEPSCIENTIST_HOME` or `DS_HOME` environment variable for those commands is also fine
* when multiple non-default homes exist, explicit `--home` remains the most reliable choice  

For example, when using a non-default home, run:  

```bash
ds --status --home /path/to/DeepScientist  
ds --stop --home /path/to/DeepScientist
```

If you want another port, run:

```bash
ds --port 21000
```

This keeps everything the same, but serves the web UI on port `21000`.

By default, DeepScientist starts without a local browser password gate.

- open the normal local URL manually if the browser does not open automatically, such as `http://127.0.0.1:20999`
- if you want a generated local browser password for one launch, run `ds --auth true`
- on authenticated launches, DeepScientist prints the generated password in the terminal
- if the browser is not authenticated yet, DeepScientist shows a password modal before loading the landing page and workspace
- after the first successful login, the browser keeps the local session and later visits usually do not need the password again
- if you need to look up the password again for an authenticated launch, check the launch terminal or run `ds --status`

## 4. Open the Home Page

When DeepScientist starts, open the home page at `/`.

![DeepScientist home page](../images/quickstart/00-home.png)

After 12 hours of running, the projects surface will often look more like this:

![DeepScientist projects surface](../assets/branding/projects.png)

The two main entry points are:

- `Start Research` or `Start Experiment`: begin a new project flow
- `Open Project`: reopen an existing project

For your first run, click `Start Research` or `Start Experiment`.

Important update:

- the product now asks you to choose a start style first
- `Copilot` creates a quieter project that waits for your first instruction
- `Autonomous` creates the standard DeepScientist project and starts moving immediately

If you are unsure which one to choose, read [20 Workspace Modes Guide](./20_WORKSPACE_MODES_GUIDE.md) first.

## 5. Create Your First Project With A Worked Example

This walkthrough uses a cleaned-up version of a real project input from quest `025`.

The example task is:

- reproduce the official Mandela-Effect baseline
- keep the original task setting and evaluation protocol
- study how to improve truth-preserving collaboration under mixed correct and incorrect social signals
- in this reference example, use two local inference endpoints to keep throughput high

Click `Start Research` / `Start Experiment`, then choose `Autonomous Mode` to follow the flow below.

![Start Research dialog](../images/quickstart/01-start-research.png)

### 5.1 Fill the short identity fields first

Use these values:

| Field in the UI | Example value | Why |
|---|---|---|
| `Project title` | `Mandela-Effect Reproduction and Truth-Preserving Collaboration` | Short, clear, and easy to recognize later in the project list |
| `Project ID` | leave blank, or enter `025` | Leave it blank if you want automatic sequential numbering; enter a fixed id only when you need one |
| `Connector delivery` | `Local only` for the first run | Keep the first run simple; if QQ or another connector is already configured, you can bind one target here |

### 5.2 Paste the main research request

Paste this into `Primary research request`:

```text
Please reproduce the official Mandela-Effect repository and paper, then study how to improve truth-preserving collaboration under mixed correct and incorrect social signals.

The core research question is: how can a multi-agent system remain factually robust under social influence while still learning from correct peers?

Keep the task definition and evaluation protocol aligned with the original work. Focus on prompt-based or system-level methods that improve truth preservation without simply refusing all social information.
```

Why this is a good request:

- it states the baseline to reproduce
- it names the research question explicitly
- it gives a boundary: stay on the same task and protocol
- it hints at promising directions without over-prescribing the implementation

### 5.3 Add the baseline and reference sources

If this is your first run, leave `Reusable baseline` empty.

If you already imported a reusable official baseline into the registry, select it here instead. That lets DeepScientist attach the trusted baseline directly.

Paste this into `Baseline links`:

```text
https://github.com/bluedream02/Mandela-Effect
```

Paste this into `Reference papers / repos`:

```text
https://arxiv.org/abs/2602.00428
```

These fields tell DeepScientist where the baseline comes from and what prior work defines the task.

### 5.4 Add the runtime constraints

Paste this into `Runtime constraints`:

This snippet is a tutorial reference only, not a DeepScientist default endpoint setup. Replace the endpoints, API key, and model with your real runtime before you paste it.

```text
- Keep the task definition and evaluation protocol aligned with the official baseline unless a change is explicitly justified.
- Use two OpenAI-compatible inference endpoints for throughput:
  - `http://127.0.0.1:<port-a>/v1`
  - `http://127.0.0.1:<port-b>/v1`
- Use your actual API key `<YOUR_API_KEY>` and model `<YOUR_MODEL>` on both endpoints.
- Keep generation settings close to the baseline unless a justified adjustment is required.
- Implement asynchronous execution, automatic retry on request failure, and resumable scripts.
- Split requests across both endpoints so throughput stays high without overloading the service.
- Record failed, degraded, or inconclusive runs honestly instead of hiding them.
```

This is one of the most important fields in the whole dialog. It turns vague operational wishes into hard project rules.

### 5.5 Add the goals

Paste this into `Goals`:

```text
1. Restore and verify the official Mandela-Effect baseline as a trustworthy starting point.
2. Measure key metrics and failure modes on the designated `gpt-oss-120b` setup.
3. Propose at least one literature-grounded direction for stronger truth-preserving collaboration.
4. Produce experiment and analysis artifacts that are strong enough to support paper writing.
```

This field should describe the outcomes of the first meaningful research cycle, not a vague aspiration like “do something new”.

### 5.6 Choose the policy fields

For this example, use these settings:

| Field in the UI | Example value | What it means |
|---|---|---|
| `Research paper` | `On` | The project should continue through analysis and paper-ready outputs |
| `Research intensity` | `Balanced` | Secure the baseline first, then test one justified direction |
| `Decision mode` | `Autonomous` | The run should keep moving unless a real user decision is needed |
| `Launch mode` | `Standard` | Start from the ordinary research graph |
| `Language` | `English` | Use English for the kickoff prompt and user-facing artifacts by default |

What the frontend derives automatically from these choices:

- `scope = baseline_plus_direction`
- `baseline_mode = restore_from_url` if no reusable baseline is selected
- `baseline_mode = existing` if a reusable baseline is selected
- `resource_policy = balanced`
- `time_budget_hours = 24`
- `git_strategy = semantic_head_plus_controlled_integration`

This matters because the dialog does not only create a project. It also writes a structured `startup_contract` that later prompt building keeps reading.

### 5.7 Review the preview, then create the project

Look at the prompt preview on the right before you click `Create project`.

Check that it clearly includes:

- the primary research request
- the baseline repository
- the reference paper
- the runtime constraints
- the goals
- the chosen delivery and decision mode

When it looks right, click `Create project`.

At this point, the frontend submits:

- a compiled kickoff prompt
- an optional `requested_baseline_ref`
- an optional `requested_connector_bindings`
- a structured `startup_contract`

If you want to understand that payload in detail, read [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md).

## 6. Reopen an Existing Project

Click `Open Project` on the home page to open the project list.

![Open Project dialog](../images/quickstart/02-list-quest.png)

Use this when you want to:

- reopen a running project
- reopen a finished project
- search by project title or id

Each row is one project repository. Click the card to open it.

## 7. What Happens After Opening a Project

After you create or open a project, DeepScientist takes you to the workspace page for that project.

The usual first loop is:

1. watch progress in Copilot / Studio
2. inspect files, notes, and generated artifacts
3. use Canvas to understand the project graph and stage progress
4. let the run continue unless you intentionally want to interrupt it

## 8. Useful Runtime Commands

Check status:

```bash
ds --status
```

If you started DeepScientist with a non-default home, specify it explicitly:  

```bash
ds --status --home /path/to/DeepScientist
```

This shows whether the local runtime is up.

Stop the daemon:

```bash
ds --stop
```

If you started DeepScientist with a non-default home, specify it explicitly:  

```bash
ds --stop --home /path/to/DeepScientist
```

This stops the local DeepScientist daemon.

Uninstall code and runtime, but keep local data:

```bash
ds uninstall
```

If you started DeepScientist with a non-default home, specify it explicitly:

```bash
ds uninstall --home /path/to/DeepScientist --yes
```

This removes launcher wrappers, local runtime code, and install-local code trees, but preserves:

- `quests/`
- `memory/`
- `config/`
- `logs/`
- `plugins/`
- `cache/`

If you installed DeepScientist from npm and also want to remove the global npm package itself, run this after `ds uninstall`:

```bash
npm uninstall -g @researai/deepscientist
```

If you really want to delete local data too, remove the DeepScientist home manually after uninstall:

```bash
rm -rf /path/to/DeepScientist
```

Run diagnostics:

```bash
ds doctor
```

Use this when startup, config, runner, or connector behavior looks wrong.

## 9. What To Read Next

- [DeepScientist Docs Index](./README.md)
- [12 Guided Workflow Tour](./12_GUIDED_WORKFLOW_TOUR.md)
- [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md)
- [13 Core Architecture Guide](./13_CORE_ARCHITECTURE_GUIDE.md)
- [01 Settings Reference](./01_SETTINGS_REFERENCE.md)
- [03 QQ Connector Guide](./03_QQ_CONNECTOR_GUIDE.md)
- [05 TUI Guide](./05_TUI_GUIDE.md)

## 10. Short FAQ

### How do I install from a source checkout into another base directory?

Run:

```bash
bash install.sh --dir /data/DeepScientist
```

Use this when you are working from a repository checkout but want the bundled CLI installed into a separate runtime location.

### How do I move an existing DeepScientist home safely?

Run:

```bash
ds migrate /data/DeepScientist
```

This is the supported way to migrate an existing DeepScientist home to a new path.

### How do I bind on all interfaces?

Run:

```bash
ds --host 0.0.0.0 --port 21000
```

Only do this when you really need external reachability, and review the risk notice first:

- [11 License And Risk Notice](./11_LICENSE_AND_RISK.md)
