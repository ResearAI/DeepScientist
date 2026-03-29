<h1 align="center">
  <img src="assets/branding/logo.svg" alt="DeepScientist logo" width="84" />
  DeepScientist
</h1>

<p>
  <strong>DeepScientist is not just a long-running autonomous scientific discovery system. It is also a persistent research map that lives on your own machine.</strong>
</p>

<p>
  Local-first. Open-source. Git-backed. Built for verifiable computational research.
</p>

<p align="center">
  <a href="docs/en/README.md">English</a> | <a href="docs/zh/README.md">中文</a>
</p>

<p align="center">
  <a href="https://openreview.net/forum?id=cZFgsLq8Gs"><img alt="ICLR 2026" src="https://img.shields.io/badge/ICLR-2026-blue?style=for-the-badge&logo=openreview"></a>
  <a href="LICENSE"><img alt="License Apache-2.0" src="https://img.shields.io/badge/License-Apache%202.0-yellow.svg?style=for-the-badge"></a>
  <a href="https://www.python.org/"><img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white"></a>
  <a href="https://www.npmjs.com/package/@researai/deepscientist"><img alt="npm @researai/deepscientist" src="https://img.shields.io/badge/npm-%40researai%2Fdeepscientist-CB3837?style=for-the-badge&logo=npm&logoColor=white"></a>
  <a href="https://deepscientist.cc/"><img alt="Website deepscientist.cc" src="https://img.shields.io/badge/Website-deepscientist.cc-brightgreen?style=for-the-badge&logo=googlechrome&logoColor=white"></a>
</p>

<p align="center">
  <a href="docs/en/00_QUICK_START.md">Quick Start</a> •
  <a href="docs/en/02_START_RESEARCH_GUIDE.md">Start Research Guide</a> •
  <a href="docs/en/16_TELEGRAM_CONNECTOR_GUIDE.md">Telegram</a> •
  <a href="docs/en/17_WHATSAPP_CONNECTOR_GUIDE.md">WhatsApp</a> •
  <a href="docs/en/18_FEISHU_CONNECTOR_GUIDE.md">Feishu</a> •
  <a href="docs/en/10_WEIXIN_CONNECTOR_GUIDE.md"><img src="assets/branding/connector-weixin.png" alt="Weixin" width="14" height="14" /> Weixin</a> •
  <a href="docs/en/03_QQ_CONNECTOR_GUIDE.md"><img src="assets/branding/connector-qq.png" alt="QQ" width="14" height="14" /> QQ</a> •
  <a href="docs/en/04_LINGZHU_CONNECTOR_GUIDE.md"><img src="assets/branding/connector-rokid.png" alt="Rokid" width="14" height="14" /> Rokid</a> •
  <a href="https://openreview.net/forum?id=cZFgsLq8Gs">Paper</a>
</p>

## About

DeepScientist is not just a long-running autonomous scientific discovery system. It is also a persistent research map that lives on your own machine.

- See every branch.
- Recover every lesson.
- Compound every round.

**A research workspace you can actually inspect.** The frontend rebuilds a live [Canvas](docs/en/06_RUNTIME_AND_CANVAS.md) from Git branches, artifacts, connector traffic, and raw quest events, so progress stays visible as a navigable map instead of collapsing into one long chat log.

**Memory that survives failure.** Built-in [memory](docs/en/07_MEMORY_AND_MCP.md) turns paper notes, dead ends, route decisions, and recovered lessons into searchable project state that later rounds can pull back deliberately.

**A self-evolving loop with real state.** Failed branches, reusable baselines, promoted lessons, and new evidence all feed the next round, so DeepScientist compounds research progress instead of restarting from zero.

**A studio, not a sealed autopilot.** DeepScientist can drive a task end to end, but you can step in at any moment to redirect the plan, edit code, inspect files, or run the terminal yourself inside the same quest.

DeepScientist is strong at:

- reproducing baselines and keeping them reusable
- reading papers, extracting concrete limitations, and generating hypotheses
- running experiment branches, analysis campaigns, figures, and paper drafts
- preserving both successful and failed results so the next round can start stronger

DeepScientist is flexible and easy to use with:

- local-first, open-source, one-command install
- Git-backed quest repositories, shared web workspace, Studio / Canvas, and TUI
- workshop-style collaboration: let DeepScientist drive, or pause anytime to inspect, edit, and run commands yourself
- Codex with `gpt-5.4` by default, plus external OpenAI-compatible inference endpoints
- use DeepScientist anywhere: server via TUI, browser via Web, phone via Weixin or QQ, and even glasses via Rokid Glasses
- one bound external connector per quest: [Weixin](docs/en/10_WEIXIN_CONNECTOR_GUIDE.md), [QQ](docs/en/03_QQ_CONNECTOR_GUIDE.md), Telegram, Discord, Slack, Feishu, WhatsApp, and [Lingzhu / Rokid](docs/en/04_LINGZHU_CONNECTOR_GUIDE.md)
- conference-to-journal extension workflows, and rebuttal workflows from paper, code, and reviewer comments
- one quest, one Git repository
- branches and worktrees as native research structure
- live Studio and Canvas from durable quest state
- reusable baselines, not one-off benchmark runs
- durable `bash_exec` sessions, not disposable terminal output

DeepScientist works best when the task is computational, verifiable, and worth tracking across multiple rounds.

## News

- `2026/03/24`: DeepScientist officially releases `v1.5`.
- `2026/02/01`: the DeepScientist paper is available on [OpenReview](https://openreview.net/forum?id=cZFgsLq8Gs) for `ICLR 2026`.

## Getting Started

- [Docs Index (English)](docs/en/README.md)
- [Quick Start (English)](docs/en/00_QUICK_START.md)
- [Guided Workflow Tour (English)](docs/en/12_GUIDED_WORKFLOW_TOUR.md)
- [Start Research Guide (English)](docs/en/02_START_RESEARCH_GUIDE.md)
- [Core Architecture Guide (English)](docs/en/13_CORE_ARCHITECTURE_GUIDE.md)

## Install

```bash
npm install -g @researai/deepscientist
codex --login
ds --yolo --here
```

If `codex --login` is unavailable, run `codex` once and finish authentication there. After startup, open `http://127.0.0.1:20999`.

Linux and macOS remain the most battle-tested platforms. Native Windows support is now experimental; if you need the closest Linux-like terminal behavior, prefer WSL2.

For detailed install, troubleshooting, PDF compile, and other launch modes, use:

- [Quick Start](docs/en/00_QUICK_START.md)
- [Codex Provider Setup](docs/en/15_CODEX_PROVIDER_SETUP.md)
- [Doctor](docs/en/09_DOCTOR.md)

## Documentation

- [Docs Index (English)](docs/en/README.md)
- [Guided Workflow Tour (English)](docs/en/12_GUIDED_WORKFLOW_TOUR.md)
- [Core Architecture Guide (English)](docs/en/13_CORE_ARCHITECTURE_GUIDE.md)
- [Prompt, Skills, and MCP Guide (English)](docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md)
- [Weixin Connector Guide (English)](docs/en/10_WEIXIN_CONNECTOR_GUIDE.md)
- [Telegram Connector Guide (English)](docs/en/16_TELEGRAM_CONNECTOR_GUIDE.md)
- [WhatsApp Connector Guide (English)](docs/en/17_WHATSAPP_CONNECTOR_GUIDE.md)
- [Feishu Connector Guide (English)](docs/en/18_FEISHU_CONNECTOR_GUIDE.md)
- [QQ Connector Guide (English)](docs/en/03_QQ_CONNECTOR_GUIDE.md)
- [Lingzhu / Rokid Guide (English)](docs/en/04_LINGZHU_CONNECTOR_GUIDE.md)
- [Memory and MCP Guide (English)](docs/en/07_MEMORY_AND_MCP.md)
- [External Controller Guide (English)](docs/en/19_EXTERNAL_CONTROLLER_GUIDE.md)
- [Settings Reference (English)](docs/en/01_SETTINGS_REFERENCE.md)
- [Codex Provider Setup (English)](docs/en/15_CODEX_PROVIDER_SETUP.md)

## Maintainers

- [Architecture](docs/en/90_ARCHITECTURE.md)
- [Development Guide](docs/en/91_DEVELOPMENT.md)

## Citation

This project is currently contributed by Yixuan Weng, Shichen Li, Weixu Zhao, Qiyao Sun, Zhen Lin, Minjun Zhu. If you find our work valuable, please cite:

```bibtex
@inproceedings{
weng2026deepscientist,
title={DeepScientist: Advancing Frontier-Pushing Scientific Findings Progressively},
author={Yixuan Weng and Minjun Zhu and Qiujie Xie and QiYao Sun and Zhen Lin and Sifan Liu and Yue Zhang},
booktitle={The Fourteenth International Conference on Learning Representations},
year={2026},
url={https://openreview.net/forum?id=cZFgsLq8Gs}
}
```

## End-to-End Autonomous Research Systems

| System | System Type | E2E | Research Map | Workshop | Keeps Growing | Channels | Figure & Rebuttal & Review |
|---|---|---|---|---|---|---|---|
| [autoresearch](https://github.com/karpathy/autoresearch) | Open-source |  |  | ✓ |  |  |  |
| [RD-Agent](https://github.com/microsoft/RD-Agent) | Open-source |  |  |  | ✓ |  |  |
| [Agent Laboratory](https://github.com/SamuelSchmidgall/AgentLaboratory) | Open-source | ✓ |  | ✓ | ✓ |  |  |
| [AI-Scientist](https://github.com/SakanaAI/AI-Scientist) | Open-source | ✓ |  |  |  |  |  |
| [AI-Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2) | Open-source | ✓ |  |  |  |  |  |
| [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw) | Open-source | ✓ |  |  | ✓ | ✓ |  |
| [ClawPhD](https://github.com/ZhihaoAIRobotic/ClawPhD) | Open-source |  |  | ✓ |  | ✓ |  |
| [Dr. Claw](https://github.com/OpenLAIR/dr-claw) | Open-source | ✓ |  | ✓ |  | ✓ |  |
| [FARS](https://analemma.ai/fars/) | Closed-source | ✓ |  |  |  |  |  |
| [EvoScientist](https://github.com/EvoScientist/EvoScientist) | Open-source | ✓ |  | ✓ | ✓ | ✓ |  |
| [ScienceClaw](https://github.com/beita6969/ScienceClaw) | Open-source |  |  |  | ✓ | ✓ |  |
| [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) | Open-source | ✓ |  | ✓ | ✓ |  |  |
| [Research-Claw](https://github.com/wentorai/Research-Claw) | Open-source | ✓ |  | ✓ | ✓ | ✓ |  |
| [DeepScientist](https://github.com/ResearAI/DeepScientist) | Open-source | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## More From ResearAI

DeepReviewer and AutoFigure projects worth exploring alongside DeepScientist:

| Project | What it does |
|---|---|
| [AutoFigure](https://github.com/ResearAI/AutoFigure) | generate paper-ready figures |
| [AutoFigure-Edit](https://github.com/ResearAI/AutoFigure-Edit) | editable vector paper figures |
| [DeepReviewer-v2](https://github.com/ResearAI/DeepReviewer-v2) | review papers and drafts |
| [Awesome-AI-Scientist](https://github.com/ResearAI/Awesome-AI-Scientist) | curated AI scientist landscape |

## License

[Apache License 2.0](LICENSE)
