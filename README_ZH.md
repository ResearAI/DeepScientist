<h1 align="center" style="font-size: 3.25rem; line-height: 1.02; margin-bottom: 0.4rem;">
  <img src="assets/branding/logo.svg" alt="DeepScientist logo" width="50" />
  DeepScientist
</h1>

<p align="center">
  <a href="https://github.com/ResearAI/DeepScientist">GitHub</a> |
  <a href="README.md">English README</a> |
  <a href="docs/zh/README.md">中文文档</a> |
  <a href="https://openreview.net/forum?id=cZFgsLq8Gs">论文</a> |
  <a href="https://deepscientist.cc/">官网</a>
</p>

<p align="center">
  <a href="https://github.com/ResearAI/DeepScientist"><img alt="GitHub stars" src="https://img.shields.io/github/stars/ResearAI/DeepScientist?style=for-the-badge&logo=github"></a>
  <a href="https://event.baai.ac.cn/activities/962"><img alt="Watch Video" src="https://img.shields.io/badge/Watch-Video-5B7266?style=for-the-badge"></a>
  <a href="LICENSE"><img alt="License Apache-2.0" src="https://img.shields.io/badge/License-Apache%202.0-yellow.svg?style=for-the-badge"></a>
  <a href="https://www.python.org/"><img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white"></a>
</p>

<p align="center">
  <a href="https://openreview.net/forum?id=cZFgsLq8Gs"><img alt="ICLR 2026 Top 10 Badge" src="assets/readme/iclr2026_top10_badge.svg" height="44"></a>
</p>

<p align="center">
  <strong>15 分钟本地部署</strong> ·
  <strong>一题一仓库</strong> ·
  <strong>研究过程可回看</strong> ·
  <strong>人类可随时接管</strong>
</p>

<p align="center">
  <strong>内建 runner：Codex（主路径）、Claude Code（supported experimental）、OpenCode（supported experimental）</strong>
</p>

<p align="center">
  <a href="docs/zh/00_QUICK_START.md">快速开始</a> •
  <a href="docs/zh/02_START_RESEARCH_GUIDE.md">启动第一个课题</a> •
  <a href="docs/zh/12_GUIDED_WORKFLOW_TOUR.md">产品导览</a> •
  <a href="docs/zh/15_CODEX_PROVIDER_SETUP.md">Codex 配置</a> •
  <a href="docs/zh/24_CLAUDE_CODE_PROVIDER_SETUP.md">Claude 配置</a> •
  <a href="docs/zh/25_OPENCODE_PROVIDER_SETUP.md">OpenCode 配置</a>
</p>

![deepscientist_install](https://github.com/user-attachments/assets/d8244944-4f70-4e08-94e3-002b74ce70fb)

与一次性 **The AI Scientist** 或 **autoresearch** 风格系统不同，DeepScientist 是一个**本地优先的自治 AI 科研工作室**，**10 分钟即可启动**，并能在你的机器上持续推进从 **Baseline**、**多轮实验** 到 **论文级产出** 的完整科研闭环。依靠 **Findings Memory**、**贝叶斯优化** 和 **Research Map**，它会把每个新结果继续变成下一轮优化的起点，并在需要时通过更深入、更广泛的探索推进 **成百上千次实验验证**。

如果你想了解 DeepScientist 的技术细节，欢迎观看[视频](https://event.baai.ac.cn/activities/962)。

---


https://github.com/user-attachments/assets/16e3d346-7b27-41ef-bf3c-dc169aed3911

## 还在把时间花在科研体力活上吗？

很多研究者真正被消耗掉的，不是“想不到 idea”，而是这些每天重复出现的低杠杆工作：

- 新论文一直在来，但真正能沉淀成下一步研究计划的很少
- Baseline 拉下来之后，环境、依赖、数据、脚本问题能卡掉大半天
- 实验跑了很多轮，结果散在终端、脚本、笔记和聊天记录里，后面几乎无法复盘
- 写作、图表、分析分散在不同工具里，最后拼成论文时非常痛苦

DeepScientist 想解决的，就是这件事：

> 把原本碎片化、反复劳动、容易丢状态的科研过程，变成一个可以持续推进、持续积累、持续复用的本地 AI 工作区。

## DeepScientist 不是另一个“科研聊天机器人”

它不是只会总结论文、给你灵感、然后把真正的脏活累活继续留给你的工具。

它更像一个真正能长期一起干活的 AI 科研搭档：

| 普通 AI 工具常见状态 | DeepScientist 的做法 |
|---|---|
| 会聊天，但上下文容易丢 | 把任务、文件、分支、产物、记忆都沉淀成可持续状态 |
| 能给建议，但很难持续落地 | 从论文、Baseline、实验到写作在同一工作区推进 |
| 自动化强，但过程像黑盒 | 你可以在 Web 工作区、Canvas、文件和终端里随时检查过程 |
| 一旦跑偏，人类很难接手 | 任何时候都可以中断、接管、改计划、改代码、继续跑 |
| 本轮结束就结束了 | 失败路线、有效路线、复现经验都能变成下一轮的输入 |

## 关于

> DeepScientist 不是一次性跑完的 Agent demo，而是一个真正面向长期科研工作的系统。

## 它能替你把哪些事真的做起来？

### 1. 从论文和问题出发，启动一个真实课题

- 输入一篇核心论文、一个 GitHub 仓库，或一段自然语言研究目标
- 系统会把这些输入整理成一个真正可执行的 quest，而不是一段很快消失的聊天

### 2. 复现 Baseline，并保留可复用的复现资产

- 拉取仓库、准备环境、处理依赖、跟踪关键问题
- 把“哪里踩坑了、怎么修好的、哪些步骤可靠”留下来，供后续轮次继续使用

### 3. 持续做实验，而不是只跑一次就结束

- 基于已有结果提出下一轮假设
- 开分支、做消融、比对结果、记录结论
- 让失败路线也成为资产，而不是被覆盖掉

### 4. 把结果转化成能发出去的材料

- 整理实验现象、结论和分析
- 产出图表、报告和论文草稿
- 支持本地 PDF / LaTeX 编译路径

### 5. 在不同界面持续跟进研究进展

- 浏览器中的 Web 工作区
- 服务器上的 TUI 工作流
- 外部 Connector 协作入口

目前文档已经覆盖这些协作面：

- [微信](docs/zh/10_WEIXIN_CONNECTOR_GUIDE.md)
- [QQ](docs/zh/03_QQ_CONNECTOR_GUIDE.md)
- [Telegram](docs/zh/16_TELEGRAM_CONNECTOR_GUIDE.md)
- [WhatsApp](docs/zh/17_WHATSAPP_CONNECTOR_GUIDE.md)
- [Feishu](docs/zh/18_FEISHU_CONNECTOR_GUIDE.md)
- [灵珠 / Rokid](docs/zh/04_LINGZHU_CONNECTOR_GUIDE.md)

## 为什么它更容易让人“用下去”？

真正能留下用户的，不是一个炫技 demo，而是一个越用越顺手、越用越有积累的系统。

DeepScientist 最容易让人持续使用的原因有四个：

### 本地优先

- 代码、实验、论文草稿和项目状态默认留在你自己的机器或服务器
- 对未发表 idea、更敏感的实验过程、更长周期的课题更友好

### 一题一仓库

- 每个 quest 都是一个真实 Git 仓库
- 分支、worktree、文件和产物天然就能表达研究结构

### 研究过程不是黑盒

- 不是只给你一个结果
- 你可以看到它读了什么、改了什么、保留了什么、下一步准备做什么

### 人机协作而不是完全放手

- DeepScientist 可以自主推进
- 你也可以随时停下来接手、修改、纠偏，再把控制权交还回去

## 为什么现在值得试？

因为这不是一个只停留在概念层的想法，而是一个已经具备公开资料、公开文档、公开安装路径的真实系统。

- `2026/03/24`：DeepScientist 正式发布 `v1.5`
- `2026/02/01`：论文已上线 [OpenReview](https://openreview.net/forum?id=cZFgsLq8Gs)，对应 `ICLR 2026`
- 已提供 npm 安装路径：[`@researai/deepscientist`](https://www.npmjs.com/package/@researai/deepscientist)
- 已提供中文、英文文档，以及 Web / TUI / Connector 使用入口

## 产品预览

### 架构总览

<p align="center">
  <img src="assets/readme/architecture-promo.png" alt="DeepScientist architecture overview" width="92%" />
</p>

### 示例输出

<table>
<tr>
<td width="50%">
<img src="assets/readme/paper-output-1.png" alt="DeepScientist generated paper example 1" width="100%" />
</td>
<td width="50%">
<img src="assets/readme/paper-output-2.png" alt="DeepScientist generated paper example 2" width="100%" />
</td>
</tr>
<tr>
<td valign="top">
<b>论文输出示例 1</b><br/>
 论文级交付物可以直接保存在 quest 内部，而不是散落在外部工具里。
</td>
<td valign="top">
<b>论文输出示例 2</b><br/>
 DeepScientist 可以把工作一路带到写作、审稿、图表打磨和导出。
</td>
</tr>
</table>

### 工作区预览

<table>
<tr>
<td width="33%">
<img src="assets/readme/start-research-promo.png" alt="Start Research dialog" width="100%" />
</td>
<td width="33%">
<img src="assets/readme/canvas-promo.png" alt="Canvas workspace preview" width="100%" />
</td>
<td width="33%">
<img src="assets/readme/studio-details-promo.png" alt="Studio and details workspace preview" width="100%" />
</td>
</tr>
<tr>
<td valign="top">
<b>Start Research</b><br/>
 从论文、仓库或自然语言目标快速启动一个 quest。
</td>
<td valign="top">
<b>Canvas</b><br/>
 以可视化方式查看分支、Baseline 和累积起来的研究结构。
</td>
<td valign="top">
<b>Studio + Details</b><br/>
 在同一工作区里查看指标、trace 和项目状态。
</td>
</tr>
</table>

### 进度汇报

<p align="center">
  <img src="assets/readme/progress-reporting-promo.png" alt="DeepScientist progress reporting example" width="88%" />
</p>

### 长时间运行后的项目面板

![DeepScientist 项目面板](assets/readme/projects-surface.png)

## 谁最适合用 DeepScientist？

- 想复现论文并继续往上推结果的研究生和工程师
- 需要长期跑实验、消融和结构化结果分析的实验室或研究团队
- 想把代码、实验、笔记、写作统一放在一个工作区的人
- 不想把未发表的 idea 和中间产物直接丢到纯云端流程里的用户
- 想在服务器跑任务，但通过 Web、TUI 或消息入口跟进进展的人

## DeepScientist 背后的核心理念

我们认为，一个真正适合科研工作的系统，至少应该满足这些原则：

- 一题一仓库，而不是让所有状态在短对话里蒸发
- 分支和 worktree 应该自然表达研究路线，而不是被硬塞进聊天历史
- 失败路线应该被保留、总结和复用，而不是被覆盖
- 人类研究者始终保有接管权，而不是被锁在流程外
- 研究过程应该可审阅、可检查、可追责，而不是只剩“模型说它做了”

如果这正是你想要的工作方式，那 DeepScientist 值得现在就试。

## 🚀 30 秒开始上手

如果你现在就想试一下，这里就是最短路径：

平台说明：DeepScientist 完整支持 Linux 和 macOS。Windows 原生支持目前仍然是实验性的，强烈建议优先使用 WSL2。

DeepScientist 现在内建三条 runner 路径：

- `codex`：主路径，也是目前最稳妥的路径
- `claude`：supported experimental，适合你本机里的 `claude` 已经能直接工作时使用
- `opencode`：supported experimental，适合你本机里的 `opencode` 已经能直接工作时使用

如果你已经把其中一个 CLI 跑通了，DeepScientist 通常就可以直接接上它，不需要你把整套环境重新折腾一遍。

你也可以把启动思路理解成一句话：先带来一个已经可用的 runner，DeepScientist 再把它包成一个能长期推进的本地科研工作区。

如果你只是想先走最稳的一条，优先从 Codex 开始。

🎯 推荐第一次先走 `codex`

```bash
npm install -g @researai/deepscientist
codex login
ds --here
```

如果 Claude Code 已经在你的 shell 里直接可用，可以走这条：

```bash
npm install -g @researai/deepscientist
claude --version
ds doctor --runner claude
ds --here --runner claude
```

如果 OpenCode 已经在你的 shell 里直接可用，可以走这条：

```bash
npm install -g @researai/deepscientist
opencode --version
ds doctor --runner opencode
ds --here --runner opencode
```

如需停止当前本地托管 daemon 和所有运行中的 agent：

```bash
ds --stop
```

🛠 如果你更喜欢从 `git clone` 的源码仓库安装，而不是直接走 npm，也可以这样：

```bash
git clone https://github.com/ResearAI/DeepScientist.git
cd DeepScientist
bash install.sh
ds
```

如果你还准备直接改 Web / TUI 源码，再额外安装前端依赖：

```bash
npm --prefix src/ui install
npm --prefix src/tui install
```

如果你更喜欢交互式首次配置，也可以先单独运行一次：

```bash
codex
```

如果安装 DeepScientist 后系统里仍然提示找不到 `codex`，不要假设 bundled 依赖已经正确链接，直接走显式修复路径：

```bash
npm install -g @openai/codex
which codex
codex login
```

如果 `which codex` 仍然没有输出，就先修好 npm global bin 路径，再重试 `codex login` 和 `ds doctor`。

关于 runner，还有一个重要说明：

- `codex` 缺失时，DeepScientist 可以回退到 npm 安装里 bundled 的 helper copy
- `claude` 和 `opencode` 不会由 DeepScientist 自动替你完成安装或登录；这两条路径都应先让 CLI 本身跑通，再执行 `ds doctor --runner <name>`

启动后，默认本地地址是：

```text
http://127.0.0.1:20999
```

本地浏览器访问密码现在默认关闭。如果你希望本次启动启用本地访问密码，请这样启动：

```bash
ds --auth true
```

然后你只需要做三件事：

1. 点击 `Start Research`
2. 填入研究目标、Baseline 链接、论文链接或本地路径
3. 让 DeepScientist 在本地启动一个真正可持续推进的研究项目

如果你是第一次运行，建议优先在隔离环境、非 root 用户和本地机器上开始。完整说明见：

- [00 快速开始](docs/zh/00_QUICK_START.md)
- [15 Codex Provider 配置](docs/zh/15_CODEX_PROVIDER_SETUP.md)
- [24 Claude Code 配置指南](docs/zh/24_CLAUDE_CODE_PROVIDER_SETUP.md)
- [25 OpenCode 配置指南](docs/zh/25_OPENCODE_PROVIDER_SETUP.md)
- [09 启动诊断](docs/zh/09_DOCTOR.md)

## 🧭 选择你的上手方式

### ⚡ 我只想先跑起来看看

- [00 快速开始](docs/zh/00_QUICK_START.md)
- [12 引导式工作流教程](docs/zh/12_GUIDED_WORKFLOW_TOUR.md)

### 🧪 我想今天就启动一个真实课题

- [02 Start Research 参考](docs/zh/02_START_RESEARCH_GUIDE.md)
- [01 设置参考](docs/zh/01_SETTINGS_REFERENCE.md)

### 🖥 我主要在服务器和终端里工作

- [05 TUI 指南](docs/zh/05_TUI_GUIDE.md)

### 🔌 我想接自己的模型或外部协作面

- [15 Codex Provider 配置](docs/zh/15_CODEX_PROVIDER_SETUP.md)
- [24 Claude Code 配置指南](docs/zh/24_CLAUDE_CODE_PROVIDER_SETUP.md)
- [25 OpenCode 配置指南](docs/zh/25_OPENCODE_PROVIDER_SETUP.md)
- [21 本地模型后端指南](docs/zh/21_LOCAL_MODEL_BACKENDS_GUIDE.md)
- [微信连接器指南](docs/zh/10_WEIXIN_CONNECTOR_GUIDE.md)
- [QQ 连接器指南](docs/zh/03_QQ_CONNECTOR_GUIDE.md)
- [Telegram Connector 指南](docs/zh/16_TELEGRAM_CONNECTOR_GUIDE.md)
- [WhatsApp Connector 指南](docs/zh/17_WHATSAPP_CONNECTOR_GUIDE.md)
- [Feishu Connector 指南](docs/zh/18_FEISHU_CONNECTOR_GUIDE.md)

### 🧠 我想先理解它的系统设计

- [文档总览](docs/zh/README.md)
- [核心架构说明](docs/zh/13_CORE_ARCHITECTURE_GUIDE.md)
- [Prompt、Skills 与 MCP 指南](docs/zh/14_PROMPT_SKILLS_AND_MCP_GUIDE.md)

## 自主科研系统

### 端到端自主科研系统

| 系统 | 类型 | E2E | Research Map | Workshop | 持续生长 | 渠道协作 | 图表 / Rebuttal / Review |
|---|---|---|---|---|---|---|---|
| [autoresearch](https://github.com/karpathy/autoresearch) | 开源 |  |  | ✓ |  |  |  |
| [RD-Agent](https://github.com/microsoft/RD-Agent) | 开源 |  |  |  | ✓ |  |  |
| [Agent Laboratory](https://github.com/SamuelSchmidgall/AgentLaboratory) | 开源 | ✓ |  | ✓ | ✓ |  |  |
| [AI-Scientist](https://github.com/SakanaAI/AI-Scientist) | 开源 | ✓ |  |  |  |  |  |
| [AI-Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2) | 开源 | ✓ |  |  |  |  |  |
| [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw) | 开源 | ✓ |  |  | ✓ | ✓ |  |
| [ClawPhD](https://github.com/ZhihaoAIRobotic/ClawPhD) | 开源 |  |  | ✓ |  | ✓ |  |
| [Dr. Claw](https://github.com/OpenLAIR/dr-claw) | 开源 | ✓ |  | ✓ |  | ✓ |  |
| [FARS](https://analemma.ai/fars/) | 闭源 | ✓ |  |  |  |  |  |
| [EvoScientist](https://github.com/EvoScientist/EvoScientist) | 开源 | ✓ |  | ✓ | ✓ | ✓ |  |
| [ScienceClaw](https://github.com/beita6969/ScienceClaw) | 开源 |  |  |  | ✓ | ✓ |  |
| [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar) | 开源 | ✓ |  | ✓ | ✓ |  |  |
| [Research-Claw](https://github.com/wentorai/Research-Claw) | 开源 | ✓ |  | ✓ | ✓ | ✓ |  |
| [DeepScientist](https://github.com/ResearAI/DeepScientist) | 开源 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

## 文档

- [中文文档总览](docs/zh/README.md)
- [English Docs Index](docs/en/README.md)

## 更多 ResearAI 项目

如果你喜欢 DeepScientist，也可以一起看看 ResearAI 的其他项目：

| 项目 | 说明 | Stars |
|---|---|---|
| **[MeOS](https://github.com/ResearAI/MeOS)** | 把你自己 Fork 成一个 Skill，让 agent 更懂你 | ![GitHub stars](https://img.shields.io/github/stars/ResearAI/MeOS?style=flat&logo=github) |
| [AutoFigure](https://github.com/ResearAI/AutoFigure) | 生成论文级图表 | ![GitHub stars](https://img.shields.io/github/stars/ResearAI/AutoFigure?style=flat&logo=github) |
| [AutoFigure-Edit](https://github.com/ResearAI/AutoFigure-Edit) | 生成可编辑矢量论文图 | ![GitHub stars](https://img.shields.io/github/stars/ResearAI/AutoFigure-Edit?style=flat&logo=github) |
| [DeepReviewer-v2](https://github.com/ResearAI/DeepReviewer-v2) | 论文审稿与修改建议 | ![GitHub stars](https://img.shields.io/github/stars/ResearAI/DeepReviewer-v2?style=flat&logo=github) |
| [Awesome-AI-Scientist](https://github.com/ResearAI/Awesome-AI-Scientist) | AI Scientist 项目导航 | ![GitHub stars](https://img.shields.io/github/stars/ResearAI/Awesome-AI-Scientist?style=flat&logo=github) |

## NLPCC 2026 AISB Challenge

如果你想在真实场景里 benchmark 或继续扩展 AI scientist 系统，NLPCC 2026 AISB shared task 是一个自然的下一站：

- [Registration](http://tcci.ccf.org.cn/conference/2026/shared-tasks/)
- [Task Repository](https://github.com/ResearAI/NLPCC-2026-Task9-AISB)

<p align="center">
  <img src="assets/readme/aisb-poster.jpeg" alt="NLPCC 2026 AISB shared task poster" width="88%" />
</p>

## 面向开发者与维护者

如果你正在开发或维护 DeepScientist，可以继续看：

- [Architecture](docs/en/90_ARCHITECTURE.md)
- [Development Guide](docs/en/91_DEVELOPMENT.md)
- [CONTRIBUTING](CONTRIBUTING.md)

## 引用

如果 DeepScientist 对你的论文、报告或研究工作流产生了实质性帮助，我们强烈建议你引用 DeepScientist 论文，并诚实披露有意义的 AI assistance。

这里强调一下：这是一项温和但明确的学术归因请求，不是额外的软件许可证条件。

相关入口：

- 论文链接：`https://openreview.net/forum?id=cZFgsLq8Gs`
- 仓库引用元数据：[CITATION.cff](CITATION.cff)
- 引用与致谢说明：[docs/zh/26_CITATION_AND_ATTRIBUTION.md](docs/zh/26_CITATION_AND_ATTRIBUTION.md)
- 名称与 Logo 使用说明：[TRADEMARK.md](TRADEMARK.md)

可直接参考的致谢模板：

```text
We used DeepScientist to assist parts of the research workflow, including selected planning, implementation, experiment orchestration, analysis, and/or writing support. Final judgments, claims, and reported real experimental results remain the responsibility of the human authors.
```

DeepScientist 由 Yixuan Weng、Weixu Zhao、Shichen Li、Zhen Lin、Minjun Zhu 共同开发。

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

如果这正是你一直想要的科研工作流，欢迎给项目点一颗 Star。每一个 Star，都会帮 DeepScientist 更快地被更多真正需要它的研究者看到。

## 社区

欢迎加入微信讨论群。

<p align="center">
  <img src="assets/readme/wechat7.jpg" alt="DeepScientist WeChat group" width="360" />
</p>

## 路线图

我们正在把 DeepScientist 持续建设成一个长期维护的、本地优先的科研操作系统。

下一阶段会重点围绕四条主线推进：

### 1. 更深的科研闭环

- AI Scientist Benchmark，支持更真实、更系统的评测与比较
- 更顺滑的 baseline 自动上传、下载与复用
- 更强的实验回放、对比与论文输出能力

### 2. 更强的长程记忆

- 更强的 Memory 与 Findings Memory 机制
- 更好的跨运行、跨 quest 复用
- 在长时间项目里进一步减少重复试错和重复探索成本

### 3. 更丰富的多模态与协作工作流

- VideoAnything 一类多模态科研能力
- 更好的本地模型、connector，以及协作模式 / 全自动模式协同体验
- 在本地运行、多人协作、长时间自主推进等场景下，持续打磨一个更高效、更可靠的 DeepScientist 系统

### 4. 更强的安全性与更稳妥的部署

- 更安全的本地优先与服务器部署默认配置
- 更强的认证、权限控制与 connector 协作面保护
- 更少伪造、更低幻觉，以及更强的可验证输出能力
- 为长时间自主科研工作流提供更好的可审计性

如果你对这个方向感兴趣，欢迎点一个 `Watch` 和 `Star`：

[![Watch DeepScientist](https://img.shields.io/github/watchers/ResearAI/DeepScientist?style=for-the-badge&logo=github&label=Watch%20DeepScientist)](https://github.com/ResearAI/DeepScientist/watchers)
[![Star DeepScientist](https://img.shields.io/github/stars/ResearAI/DeepScientist?style=for-the-badge&logo=github&label=Star%20DeepScientist)](https://github.com/ResearAI/DeepScientist/stargazers)

---

本项目由 WestlakeNLP 负责维护。如有问题，建议优先在 [DeepWiki](https://deepwiki.com/ResearAI/DeepScientist) 询问；如果仍无法解决，再通过 issue 汇报。

WestlakeNLP 由 ACL Fellow 张岳教授领导。有意申请长期实习、博士生、研究助理者，可联系张岳教授邮箱：`zhangyue@westlake.edu.cn`。
