# DeepScientist Docs

DeepScientist is not just a long-running autonomous scientific discovery system. It is also a persistent research map that lives on your own machine.

2 minutes to install. 2 minutes to bind Weixin. 2 minutes to launch. Extremely fast and easy to use.

Local Web access now starts without a password gate by default. If you want a generated 16-character browser password for one launch, run `ds --auth true`; DeepScientist then prints the password in the terminal and the browser can reuse the stored login after the first successful entry.

It is also a workshop-style collaboration environment: let it keep moving autonomously, or step in anytime to collaborate, edit code, run the terminal yourself, or keep notes and plans in a Notion-style workspace.

Use DeepScientist anywhere: on the server through TUI, in the browser through Web, on the phone through Weixin or QQ, and even on glasses through Rokid Glasses.

## News

- `2026/03/24`: DeepScientist officially releases `v1.5`.
- `2026/02/01`: the DeepScientist paper is available on [OpenReview](https://openreview.net/forum?id=cZFgsLq8Gs) for `ICLR 2026`.

## More From ResearAI

AI Scientist and AutoFigure projects worth exploring alongside DeepScientist:

| Project | What it does |
|---|---|
| [AutoFigure](https://github.com/ResearAI/AutoFigure) | generate paper-ready figures |
| [AutoFigure-Edit](https://github.com/ResearAI/AutoFigure-Edit) | editable vector paper figures |
| [DeepReviewer-v2](https://github.com/ResearAI/DeepReviewer-v2) | review papers and drafts |
| [Awesome-AI-Scientist](https://github.com/ResearAI/Awesome-AI-Scientist) | curated AI scientist landscape |

This page is the shortest path to the right document.

Built-in runners today:

- `codex`
- `claude`
- `kimi`
- `opencode`

## If you are new

- [00 Quick Start](./00_QUICK_START.md)
  Start here if you want to install DeepScientist, choose between Codex / Claude Code / Kimi Code / OpenCode, launch it locally, and create your first project.
- [20 Workspace Modes Guide](./20_WORKSPACE_MODES_GUIDE.md)
  Read this if you want to choose correctly between Copilot and Autonomous before creating a project.
- [31 Local Browser Auth](./31_LOCAL_BROWSER_AUTH.md)
  Read this if you want to understand the local password prompt, where to find the password, and how to disable it.
- [32 Windows + WSL2 Deployment Guide](./32_WINDOWS_WSL2_DEPLOYMENT_GUIDE.md)
  Read this if you are on Windows and want the recommended WSL2-based deployment path instead of guessing the environment setup.
- [05 TUI Guide](./05_TUI_GUIDE.md)
  Read this if your main surface is the terminal and you want one end-to-end path through `ds --tui`, quests, connectors, and cross-surface work.
- [15 Codex Provider Setup](./15_CODEX_PROVIDER_SETUP.md)
  Read this when you want to run DeepScientist through OpenAI, Ollama, MiniMax, GLM, Volcengine Ark, Alibaba Bailian Coding Plan, or another Codex profile. Gemini through Codex is an advanced experiment; OpenCode is usually the better Gemini route.
- [24 Claude Code Setup](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
  Read this when Claude Code already works on your machine and you want DeepScientist to reuse it directly, or when you want to use Ollama through its Anthropic-compatible API.
- [27 Kimi Code Setup](./27_KIMI_CODE_PROVIDER_SETUP.md)
  Read this when the official Kimi Code CLI already works on your machine and you want DeepScientist to use it as a separate builtin runner.
- [25 OpenCode Setup](./25_OPENCODE_PROVIDER_SETUP.md)
  Read this when OpenCode already works on your machine and you want DeepScientist to reuse its provider/model configuration, especially for Gemini or Ollama.
- [21 Local Model Backends Guide](./21_LOCAL_MODEL_BACKENDS_GUIDE.md)
  Read this if you want to run DeepScientist through local model backends such as vLLM, Ollama, or SGLang and need to choose between Codex, Claude Code, and OpenCode.
- [26 Citation And Attribution](./26_CITATION_AND_ATTRIBUTION.md)
  Read this if DeepScientist materially helped a paper or report and you want the preferred citation, acknowledgment wording, and attribution boundary.
- [12 Guided Workflow Tour](./12_GUIDED_WORKFLOW_TOUR.md)
  Follow the real product flow from landing page to workspace, step by step.
- [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md)
  Read this next if you want to understand each field in the `Start Research` dialog and what it actually submits.

## If you want to launch a project well

- [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md)
  Explains the current frontend fields, derived contract fields, and practical examples.
- [20 Workspace Modes Guide](./20_WORKSPACE_MODES_GUIDE.md)
  Use this when the main question is not “how do I fill the form?” but “should this project start as Copilot or Autonomous?”.
- [01 Settings Reference](./01_SETTINGS_REFERENCE.md)
  Use this when DeepScientist is already running and you want to configure runtime defaults, models, connectors, baselines, DeepXiv, extensions, or MCP from the visual Settings page before touching raw YAML.
- [30 Settings Control Center Guide](./30_SETTINGS_CONTROL_CENTER_GUIDE.md)
  Use this when the question is not configuration but runtime supervision: summary, hardware, diagnostics, errors, logs, quests, repairs, controllers, stats, or search.
- [11 License And Risk Notice](./11_LICENSE_AND_RISK.md)
  Read this first if you care about the license boundary, server safety, fabricated outputs, connector leakage, and public exposure risk.
- [26 Citation And Attribution](./26_CITATION_AND_ATTRIBUTION.md)
  Use this when the question is not runtime risk but how to cite or acknowledge DeepScientist fairly in research outputs.

## If you want to collaborate through external surfaces

- [16 Telegram Connector Guide](./16_TELEGRAM_CONNECTOR_GUIDE.md)
  Bind Telegram through the built-in polling runtime and continue quests from bot chats.
- [28 Discord Connector Guide](./28_DISCORD_CONNECTOR_GUIDE.md)
  Configure the built-in Discord gateway connector from the Settings page and keep the workflow visual-first.
- [29 Slack Connector Guide](./29_SLACK_CONNECTOR_GUIDE.md)
  Configure the built-in Slack Socket Mode connector from the Settings page after launch.
- [17 WhatsApp Connector Guide](./17_WHATSAPP_CONNECTOR_GUIDE.md)
  Bind WhatsApp through the local-session runtime and continue quests from local chat sessions.
- [18 Feishu Connector Guide](./18_FEISHU_CONNECTOR_GUIDE.md)
  Bind Feishu through the built-in long-connection runtime and continue quests from bot chats.
- [10 Weixin Connector Guide](./10_WEIXIN_CONNECTOR_GUIDE.md)
  Bind personal WeChat through DeepScientist's built-in QR login and iLink runtime.
- [03 QQ Connector Guide](./03_QQ_CONNECTOR_GUIDE.md)
  Use QQ as a practical collaboration surface for progress, commands, and milestone delivery.
- [04 Lingzhu Connector Guide](./04_LINGZHU_CONNECTOR_GUIDE.md)
  Bind Lingzhu / Rokid Glasses to DeepScientist.

## If you want to understand how the system works

- [13 Core Architecture Guide](./13_CORE_ARCHITECTURE_GUIDE.md)
  Read this first if you want a user-facing overview of launcher, daemon, quests, Canvas, memory, and connectors.
- [14 Prompt, Skills, and MCP Guide](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md)
  Read this when you want the real turn-time structure: prompt assembly order, stage skills, and built-in MCP tool families.
- [06 Runtime and Canvas](./06_RUNTIME_AND_CANVAS.md)
  Explains how the daemon, workspace, canvas, and connector views fit together.
- [07 Memory and MCP](./07_MEMORY_AND_MCP.md)
  Explains memory, artifacts, and built-in MCP behavior.
- [19 External Controller Guide](./19_EXTERNAL_CONTROLLER_GUIDE.md)
  Shows how to build optional outer-orchestration guards on top of mailbox and `quest_control` without patching core runtime code.

## If something is broken

- [09 Doctor](./09_DOCTOR.md)
  Start here for diagnostics and common runtime problems.
- [33 Workspace Explorer Q&A](./33_WORKSPACE_EXPLORER_QA.md)
  Check this when files or folders exist in the terminal but do not appear in Web Explorer or Search; it explains active worktrees, `FILES` / `SCOPE`, refresh behavior, and Git status boundaries.
- [30 Settings Control Center Guide](./30_SETTINGS_CONTROL_CENTER_GUIDE.md)
  Use this when you want the operator view of summary, hardware, diagnostics, errors, logs, quests, repairs, controllers, stats, and search.
- [15 Codex Provider Setup](./15_CODEX_PROVIDER_SETUP.md)
  Check this if the problem is likely in your Codex profile, provider endpoint, API key, or model configuration.
- [24 Claude Code Setup](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
  Check this if the problem is likely in your Claude Code login, config directory, permission mode, or Anthropic-compatible gateway setup.
- [27 Kimi Code Setup](./27_KIMI_CODE_PROVIDER_SETUP.md)
  Check this if the problem is likely in your Kimi Code login, `~/.kimi` home, agent selection, or `--yolo` / thinking configuration.
- [25 OpenCode Setup](./25_OPENCODE_PROVIDER_SETUP.md)
  Check this if the problem is likely in your OpenCode provider login, config file, model selection, agent, or variant setup.
- [21 Local Model Backends Guide](./21_LOCAL_MODEL_BACKENDS_GUIDE.md)
  Check this if the problem is specifically about local OpenAI-compatible backends and whether they support `/v1/responses`.
- [01 Settings Reference](./01_SETTINGS_REFERENCE.md)
  Check this if the problem is likely caused by config, credentials, or connector setup.

## If you are developing DeepScientist
- [23 BenchStore GitHub Releases Spec](./23_BENCHSTORE_GITHUB_RELEASES_SPEC.md)
  Read this when you want to publish BenchStore benchmark source packages on GitHub Releases and make the frontend Download flow work for users.

- [90 Architecture](./90_ARCHITECTURE.md)
  High-level system contracts and repository structure.
- [91 Development](./91_DEVELOPMENT.md)
  Maintainer-facing workflow, implementation notes, and the concrete checklists for adding MCP tools, skills, and connectors.

## Community

Welcome to join the WeChat group for discussion.

<p align="center">
  <img src="../../assets/readme/wechat6.jpg" alt="DeepScientist WeChat group" width="360" />
</p>
