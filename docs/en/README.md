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

## If you are new

- [00 Quick Start](./00_QUICK_START.md)
  Start here if you want to install DeepScientist, launch it locally, and create your first project.
- [20 Workspace Modes Guide](./20_WORKSPACE_MODES_GUIDE.md)
  Read this if you want to choose correctly between Copilot and Autonomous before creating a project.
- [19 Local Browser Auth](./19_LOCAL_BROWSER_AUTH.md)
  Read this if you want to understand the local password prompt, where to find the password, and how to disable it.
- [05 TUI Guide](./05_TUI_GUIDE.md)
  Read this if your main surface is the terminal and you want one end-to-end path through `ds --tui`, quests, connectors, and cross-surface work.
- [15 Codex Provider Setup](./15_CODEX_PROVIDER_SETUP.md)
  Read this when you want to run DeepScientist through MiniMax, GLM, Volcengine Ark, Alibaba Bailian, or another Codex profile.
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
  Use this when you need to configure runners, connectors, runtime defaults, or home paths.
- [11 License And Risk Notice](./11_LICENSE_AND_RISK.md)
  Read this first if you care about the license boundary, server safety, fabricated outputs, connector leakage, and public exposure risk.

## If you want to collaborate through external surfaces

- [16 Telegram Connector Guide](./16_TELEGRAM_CONNECTOR_GUIDE.md)
  Bind Telegram through the built-in polling runtime and continue quests from bot chats.
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
- [15 Codex Provider Setup](./15_CODEX_PROVIDER_SETUP.md)
  Check this if the problem is likely in your Codex profile, provider endpoint, API key, or model configuration.
- [01 Settings Reference](./01_SETTINGS_REFERENCE.md)
  Check this if the problem is likely caused by config, credentials, or connector setup.

## If you are developing DeepScientist

- [90 Architecture](./90_ARCHITECTURE.md)
  High-level system contracts and repository structure.
- [91 Development](./91_DEVELOPMENT.md)
  Maintainer-facing workflow and implementation notes.

## Community

Welcome to join the WeChat group for discussion.

<p align="center">
  <img src="../../assets/readme/wechat.jpg" alt="DeepScientist WeChat group" width="360" />
</p>
