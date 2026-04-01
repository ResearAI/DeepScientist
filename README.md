<h1 align="center">
  <img src="assets/branding/logo.svg" alt="DeepScientist logo" width="92" />
  <br />
  DeepScientist
</h1>

<p align="center">
  <strong>Make AI actually do research with you, not just talk about research.</strong>
</p>

<p align="center">
  DeepScientist is a local-first AI research workspace: read papers, reproduce baselines, run experiments, organize results, and draft papers in one integrated system.
</p>

<p align="center">
  <strong>Bring your own AI scientist onto your machine in 15 minutes.</strong>
</p>

<p align="center">
  <a href="https://github.com/ResearAI/DeepScientist">GitHub</a> |
  <a href="README_ZH.md">Chinese README</a> |
  <a href="docs/en/README.md">English Docs</a> |
  <a href="https://openreview.net/forum?id=cZFgsLq8Gs">Paper</a> |
  <a href="https://deepscientist.cc/">Website</a>
</p>

<p align="center">
  <a href="https://github.com/ResearAI/DeepScientist"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ResearAI/DeepScientist?style=for-the-badge&logo=github"></a>
  <a href="https://openreview.net/forum?id=cZFgsLq8Gs"><img alt="ICLR 2026" src="https://img.shields.io/badge/ICLR-2026-blue?style=for-the-badge&logo=openreview"></a>
  <a href="LICENSE"><img alt="License Apache-2.0" src="https://img.shields.io/badge/License-Apache%202.0-yellow.svg?style=for-the-badge"></a>
  <a href="https://www.python.org/"><img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white"></a>
  <a href="https://www.npmjs.com/package/@researai/deepscientist"><img alt="npm @researai/deepscientist" src="https://img.shields.io/badge/npm-%40researai%2Fdeepscientist-CB3837?style=for-the-badge&logo=npm&logoColor=white"></a>
</p>

<p align="center">
  <strong>15-minute local setup</strong> ·
  <strong>One repo per quest</strong> ·
  <strong>Visible research progress</strong> ·
  <strong>Human takeover anytime</strong>
</p>

<p align="center">
  <a href="docs/en/00_QUICK_START.md">Quick Start</a> •
  <a href="docs/en/02_START_RESEARCH_GUIDE.md">Launch Your First Project</a> •
  <a href="docs/en/12_GUIDED_WORKFLOW_TOUR.md">Product Tour</a> •
  <a href="docs/en/15_CODEX_PROVIDER_SETUP.md">Model Setup</a>
</p>

![DeepScientist workspace preview](assets/branding/projects.png)

> [TODO asset] Replace this with a 15 to 30 second demo GIF if possible: from `Start Research`, to entering the workspace, to experiment results or connector notifications. This slot is extremely important for both star conversion and trial conversion.

If you are tired of paper overload, broken baselines, scattered experiment logs, and late-night writing cleanup, give the project a star first, then keep scrolling to see how much research grunt work it can take off your plate.

---

## Still Spending Your Time On Research Grunt Work?

What drains researchers is often not the lack of ideas. It is the endless cycle of low-leverage work:

- new papers keep coming, but only a small fraction turns into an actionable next-step research plan
- baseline repos fail on environment, dependency, data, and script issues before real work even starts
- experiment results get scattered across terminals, scripts, notes, and chats, making later review painful
- writing, figures, and analysis live in separate tools, so turning them into a coherent paper takes far too long

This is the problem DeepScientist is built to solve:

> turn fragmented, repetitive, easy-to-lose research work into a local AI workspace that can keep moving, keep accumulating, and keep getting stronger over time

## DeepScientist Is Not Just Another "Research Chatbot"

It is not a tool that summarizes papers, throws you a few ideas, and leaves the dirty work to you.

It is much closer to a real long-running AI research partner:

| What common AI tools often look like | What DeepScientist does instead |
|---|---|
| Great at chatting, but context disappears quickly | Turns tasks, files, branches, artifacts, and memory into durable state |
| Good at suggesting ideas, but weak at sustained execution | Pushes papers, baselines, experiments, and writing inside one workspace |
| Strong automation, but feels like a black box | Lets you inspect the process through the web workspace, Canvas, files, and terminal |
| Hard to take over once it goes off track | Lets you pause, take over, edit plans, change code, and continue at any time |
| Each run ends when the run ends | Preserves failed paths, winning paths, and reproduction lessons for the next round |

In one sentence:

> DeepScientist is not a one-shot agent demo. It is a system built for long-horizon research work.

## What Can It Actually Help You Get Done?

### 1. Start a real project from a paper or a research question

- feed it a core paper, a GitHub repository, or a natural-language research objective
- it turns those inputs into an executable quest instead of a chat that loses state after a few turns

### 2. Reproduce baselines and keep the reproduction reusable

- restore repositories, prepare environments, handle dependencies, and track the critical failures
- preserve what broke, what got fixed, and which steps are trustworthy for future rounds

### 3. Run experiments continuously instead of stopping after one pass

- propose the next hypothesis from existing results
- branch, ablate, compare, and record conclusions
- keep failed routes as assets instead of deleting them

### 4. Turn results into materials you can actually ship

- organize findings, conclusions, and analysis
- produce figures, reports, and paper drafts
- support local PDF and LaTeX compilation workflows

### 5. Follow the same research effort from multiple surfaces

- the web workspace in your browser
- the TUI workflow on a remote server
- external connector surfaces for collaboration and progress updates

The current docs already cover these collaboration channels:

- [Weixin](docs/en/10_WEIXIN_CONNECTOR_GUIDE.md)
- [QQ](docs/en/03_QQ_CONNECTOR_GUIDE.md)
- [Telegram](docs/en/16_TELEGRAM_CONNECTOR_GUIDE.md)
- [WhatsApp](docs/en/17_WHATSAPP_CONNECTOR_GUIDE.md)
- [Feishu](docs/en/18_FEISHU_CONNECTOR_GUIDE.md)
- [Lingzhu / Rokid](docs/en/04_LINGZHU_CONNECTOR_GUIDE.md)

## Why Is It Easier To Keep Using?

What retains users is not a flashy demo. It is a system that becomes more useful the longer you work with it.

DeepScientist tends to stick for four reasons:

### Local-first by default

- code, experiments, drafts, and project state stay on your own machine or server by default
- this is especially valuable for unpublished ideas, sensitive experiment history, and longer-running research loops

### One repo per quest

- every quest is a real Git repository
- branches, worktrees, files, and artifacts naturally express research structure

### The process is not a black box

- it does not only give you an output
- you can inspect what it read, what it changed, what it kept, and what it plans to do next

### Human collaboration is built in

- DeepScientist can move autonomously
- you can also step in, edit, redirect, and hand control back whenever you want

## Why Try It Now?

Because this is not just a concept. It is a real system with public docs, a public paper, and a public install path.

- `2026/03/24`: DeepScientist officially released `v1.5`
- `2026/02/01`: the paper went live on [OpenReview](https://openreview.net/forum?id=cZFgsLq8Gs) for `ICLR 2026`
- npm install path is already available: [`@researai/deepscientist`](https://www.npmjs.com/package/@researai/deepscientist)
- both Chinese and English docs are available, along with Web, TUI, and connector entry points

> [TODO asset] If you can later add one public case summary such as "reproduce a baseline + finish multiple experimental rounds + draft a paper package," this section will become much more convincing.

## Get Started In 30 Seconds

If you want to try it right now, the shortest path is:

```bash
npm install -g @researai/deepscientist
codex --login
ds --here
```

If `codex --login` is unavailable, run this once first:

```bash
codex
```

After startup, the default local address is:

```text
http://127.0.0.1:20999
```

Then you only need to do three things:

1. click `Start Research`
2. fill in the research goal, baseline links, paper links, or local paths
3. let DeepScientist start a real research project that can keep evolving locally

If this is your first run, prefer an isolated environment, a non-root user, and a local machine. For the full details, see:

- [00 Quick Start](docs/en/00_QUICK_START.md)
- [15 Codex Provider Setup](docs/en/15_CODEX_PROVIDER_SETUP.md)
- [09 Doctor](docs/en/09_DOCTOR.md)

## Choose Your Starting Path

### I just want to get it running first

- [00 Quick Start](docs/en/00_QUICK_START.md)
- [12 Guided Workflow Tour](docs/en/12_GUIDED_WORKFLOW_TOUR.md)

### I want to launch a real project today

- [02 Start Research Guide](docs/en/02_START_RESEARCH_GUIDE.md)
- [01 Settings Reference](docs/en/01_SETTINGS_REFERENCE.md)

### I mainly work on servers and terminals

- [05 TUI Guide](docs/en/05_TUI_GUIDE.md)

### I want to connect my own models or external collaboration channels

- [15 Codex Provider Setup](docs/en/15_CODEX_PROVIDER_SETUP.md)
- [Weixin Connector Guide](docs/en/10_WEIXIN_CONNECTOR_GUIDE.md)
- [QQ Connector Guide](docs/en/03_QQ_CONNECTOR_GUIDE.md)
- [Telegram Connector Guide](docs/en/16_TELEGRAM_CONNECTOR_GUIDE.md)
- [WhatsApp Connector Guide](docs/en/17_WHATSAPP_CONNECTOR_GUIDE.md)
- [Feishu Connector Guide](docs/en/18_FEISHU_CONNECTOR_GUIDE.md)

### I want to understand the system design first

- [Docs Index](docs/en/README.md)
- [Core Architecture Guide](docs/en/13_CORE_ARCHITECTURE_GUIDE.md)
- [Prompt, Skills, and MCP Guide](docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md)

## Product Preview

### Home page / project entry

![DeepScientist home page](docs/images/quickstart/00-home.png)

### Projects surface after long-running work

![DeepScientist projects surface](assets/branding/projects.png)

> [TODO asset] Two visual additions would help this README a lot:
>
> 1. a `Start Research` dialog screenshot to emphasize "launch a real research task in natural language"
> 2. a workspace or Canvas screenshot to emphasize "visible, steerable, reviewable research progress"

## Who Will Love DeepScientist Most?

- graduate students and engineers who want to reproduce papers and push beyond existing baselines
- labs or research teams running long experiment loops, ablations, and structured result analysis
- people who want code, experiments, notes, and writing to live in one workspace
- users who do not want to hand unpublished ideas and intermediate results directly to a pure cloud workflow
- people who want to run work on servers while following progress from web, TUI, or messaging surfaces

## The Core Philosophy Behind DeepScientist

We believe a system that is actually suitable for research should at least satisfy these principles:

- one quest, one repository, instead of letting everything dissolve after a short conversation
- branches and worktrees should express research routes naturally instead of being forced into chat history
- failed paths should be preserved, summarized, and reused instead of overwritten
- human researchers should always retain takeover power instead of being locked outside the loop
- the research process should be reviewable, inspectable, and auditable instead of relying on "the model says it did it"

If that sounds like the way you want to work, DeepScientist is worth trying now.

## Documentation

- [English Docs Index](docs/en/README.md)
- [Chinese Docs Index](docs/zh/README.md)

## More From ResearAI

If you like DeepScientist, you may also want to explore the rest of the ResearAI ecosystem:

| Project | What it does |
|---|---|
| [AutoFigure](https://github.com/ResearAI/AutoFigure) | generate publication-ready figures |
| [AutoFigure-Edit](https://github.com/ResearAI/AutoFigure-Edit) | generate editable vector paper figures |
| [DeepReviewer-v2](https://github.com/ResearAI/DeepReviewer-v2) | review papers and suggest revisions |
| [Awesome-AI-Scientist](https://github.com/ResearAI/Awesome-AI-Scientist) | curated AI scientist landscape |

## For Developers And Maintainers

If you are developing or maintaining DeepScientist, continue with:

- [Architecture](docs/en/90_ARCHITECTURE.md)
- [Development Guide](docs/en/91_DEVELOPMENT.md)
- [CONTRIBUTING](CONTRIBUTING.md)

## Citation

If DeepScientist helps your research or engineering work, please cite:

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

## License

[Apache License 2.0](LICENSE)

If this feels like the research workflow you have been waiting for, give the project a star. Every star makes it easier for more researchers who actually need it to find it.
