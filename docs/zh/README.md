# DeepScientist 文档总览

DeepScientist 不仅仅是一个可长期运行的自动化科学发现系统，更是一个真正持续保存在你自己机器里的科研地图。

2 分钟安装，2 分钟配置微信，2 分钟启动。极快、方便、易用。

现在本地 Web 默认不启用浏览器访问密码。如果你希望某次启动启用 16 位本地访问密码，可以使用 `ds --auth true`；启用后，`ds` 会在终端里打印这次启动的密码，第一次成功进入后浏览器会持久化这次本地登录。

它也是一种工作坊式协作环境：可以长期自主推进，也允许你随时接管、协作、改代码、自己跑终端，亦或者用 Notion 式方式记录笔记、计划与协作内容。

DeepScientist 灵活且易于使用，支持：

- 本地优先、开源、一条命令安装
- Git 驱动的 quest 仓库、Web 工作区、Studio / Canvas 与 TUI
- 工作坊式协作：可长期自主推进，也可随时接管、协作、改代码、跑终端或记录 Notion 式笔记
- 内建 `codex`、`claude`、`kimi`、`opencode` 四种 runner，其中 `codex` 是主路径，`claude`、`kimi` 与 `opencode` 属于 supported experimental
- 兼容外部 OpenAI-compatible 模型端点
- 你可以在任何地方使用 DeepScientist：服务器（TUI）、浏览器（Web）、手机（微信或 QQ），甚至眼镜（Rokid Glasses）
- 每个 quest 绑定一个外部 connector
- 支持 [微信](./10_WEIXIN_CONNECTOR_GUIDE.md)、[QQ](./03_QQ_CONNECTOR_GUIDE.md)、Telegram、Discord、Slack、Feishu、WhatsApp、[灵珠 / Rokid](./04_LINGZHU_CONNECTOR_GUIDE.md)
- 一题一仓库
- 分支与 worktree 是原生科研结构
- Studio 与 Canvas 从持久状态实时重建
- baseline 可复用，不是一次性跑分
- `bash_exec` 是持久化 shell 会话
- 支持会议扩展期刊与 rebuttal 工作流

## 端到端自治科研系统

以下是基于公开仓库、论文、demo 与公开报道整理的保守快照，检查日期为 `2026/03/23`。打勾表示该能力在公开材料中被清晰呈现为一等能力，而不是用户自行拼装后才可能实现。

| 系统 | 系统类型 | E2E | Research Map | Workshop | Keeps Growing | Channels | Figure & Rebuttal & Review |
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

列含义：

- `系统类型`：系统本体是开源还是闭源。
- `E2E`：是否覆盖从想法或文献到实验与写作的完整链路。
- `Research Map`：是否把研究过程显式组织成可回看的地图，而不只是日志或聊天记录。
- `Workshop`：人类是否可以随时接管、改计划、改代码、跑命令、继续推进。
- `Keeps Growing`：后续轮次是否能基于持久记忆、经验与产物持续累积。
- `Channels`：是否能通过消息或会议式外部协作面持续推进同一研究会话。
- `Figure & Rebuttal & Review`：是否把图表生成、审稿、rebuttal 或 review 工作流做成明确能力。

## 动态

- `2026/03/24`：DeepScientist 正式发布 `v1.5` 版本。
- `2026/02/01`：DeepScientist 论文已上线 [OpenReview](https://openreview.net/forum?id=cZFgsLq8Gs)，对应 `ICLR 2026`。

## ResearAI 相关项目

这里聚焦与 DeepScientist 关联最强的一组 AI Scientist 与 AutoFigure 项目。

| 项目 | 用途 |
|---|---|
| [AutoFigure](https://github.com/ResearAI/AutoFigure) | 生成论文级图像 |
| [AutoFigure-Edit](https://github.com/ResearAI/AutoFigure-Edit) | 可编辑矢量论文图 |
| [DeepReviewer-v2](https://github.com/ResearAI/DeepReviewer-v2) | 审稿与论文建议 |
| [Awesome-AI-Scientist](https://github.com/ResearAI/Awesome-AI-Scientist) | AI Scientist 导航 |

这页的目标很简单：帮你最快找到该看的那篇文档。

## 如果你是第一次使用

- [00 快速开始](./00_QUICK_START.md)
  从安装、选择 Codex / Claude Code / Kimi Code / OpenCode runner，到启动和创建第一个项目，先看这一篇。
- [20 工作区模式指南](./20_WORKSPACE_MODES_GUIDE.md)
  如果你最纠结的是“应该选 Copilot 还是全自动”，先看这篇。
- [31 本地浏览器密码说明](./31_LOCAL_BROWSER_AUTH.md)
  如果你想弄清楚密码弹窗是什么、密码去哪里看、怎样关闭这一层本地保护，先看这篇。
- [32 Windows + WSL2 部署指南](./32_WINDOWS_WSL2_DEPLOYMENT_GUIDE.md)
  如果你在 Windows 上使用 DeepScientist，并且想走推荐的 WSL2 路线，先看这篇。
- [05 TUI 端到端指南](./05_TUI_GUIDE.md)
  如果你主要在服务器或终端里工作，这篇会带你从 `ds --tui` 一路走到 quest、connector 和跨端协作跑通。
- [15 Codex Provider 配置](./15_CODEX_PROVIDER_SETUP.md)
  如果你准备通过 MiniMax、GLM、火山方舟、阿里百炼 Coding Plan 或其他 Codex profile 来运行 DeepScientist，先看这一篇。
- [24 Claude Code 配置指南](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
  如果 Claude Code 在你的机器上已经能正常工作，并且你想让 DeepScientist 直接复用它，先看这一篇。
- [27 Kimi Code 配置指南](./27_KIMI_CODE_PROVIDER_SETUP.md)
  如果官方 `kimi` CLI 在你的机器上已经能正常工作，并且你想把它作为独立 builtin runner 使用，先看这一篇。
- [25 OpenCode 配置指南](./25_OPENCODE_PROVIDER_SETUP.md)
  如果 OpenCode 在你的机器上已经能正常工作，并且你想让 DeepScientist 直接复用它的 provider/model 配置，先看这一篇。
- [21 本地模型后端指南](./21_LOCAL_MODEL_BACKENDS_GUIDE.md)
  如果你想通过 vLLM、Ollama、SGLang 等本地 OpenAI-compatible 后端运行 DeepScientist，先看这一篇。
- [26 引用与致谢说明](./26_CITATION_AND_ATTRIBUTION.md)
  如果 DeepScientist 对论文或报告已经产生了实质性帮助，想看推荐引用方式、致谢模板和归因边界，就看这一篇。
- [12 引导式工作流教程](./12_GUIDED_WORKFLOW_TOUR.md)
  按真实产品流程，逐步理解从首页到工作区应该怎么使用。
- [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)
  如果你想真正理解 `Start Research` 弹窗里每个字段该怎么填、会提交什么，就接着看这篇。

## 如果你想把项目启动得更稳

- [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)
  解释当前前端字段、自动推导合同字段，以及实际可照抄的例子。
- [20 工作区模式指南](./20_WORKSPACE_MODES_GUIDE.md)
  如果你已经知道怎么填表，但还不确定项目应该从 Copilot 还是全自动启动，先看这篇。
- [01 设置参考](./01_SETTINGS_REFERENCE.md)
  当你需要配置 runner、connector、运行时默认值或主目录路径时，看这一篇。
- [11 协议与风险说明](./11_LICENSE_AND_RISK.md)
  如果你关心开源协议、责任边界、服务器安全、结果伪造风险和 connector 泄露风险，先看这一篇。
- [26 引用与致谢说明](./26_CITATION_AND_ATTRIBUTION.md)
  如果你主要关心的是论文里该如何引用、如何做温和而清楚的 AI assistance 披露，优先看这篇。

## 如果你想通过外部协作面继续推进

- [16 Telegram Connector 指南](./16_TELEGRAM_CONNECTOR_GUIDE.md)
  通过内置 polling 运行时绑定 Telegram，并从 bot 会话继续推进 quest。
- [17 WhatsApp Connector 指南](./17_WHATSAPP_CONNECTOR_GUIDE.md)
  通过本地 local-session 运行时绑定 WhatsApp，并从本地聊天会话继续推进 quest。
- [18 Feishu Connector 指南](./18_FEISHU_CONNECTOR_GUIDE.md)
  通过内置 long-connection 运行时绑定 Feishu，并从 bot 会话继续推进 quest。
- [10 微信连接器指南](./10_WEIXIN_CONNECTOR_GUIDE.md)
  适合通过 DeepScientist 内置扫码流程，把个人微信直接绑定进来。
- [03 QQ 连接器指南](./03_QQ_CONNECTOR_GUIDE.md)
  适合把 QQ 当作日常协作、里程碑通知和命令入口。
- [04 灵珠 / Rokid 指南](./04_LINGZHU_CONNECTOR_GUIDE.md)
  适合绑定灵珠 / Rokid Glasses。

## 如果你想理解系统是怎么工作的

- [13 核心架构说明](./13_CORE_ARCHITECTURE_GUIDE.md)
  先看这篇，理解 launcher、daemon、quest、Canvas、memory 与 connector 是怎样拼起来的。
- [14 Prompt、Skills 与 MCP 指南](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md)
  适合你想直接弄清楚每轮 prompt 组装顺序、各个 skill 分工，以及内建 MCP 工具家族结构的时候阅读。
- [06 Runtime 与 Canvas](./06_RUNTIME_AND_CANVAS.md)
  说明 daemon、工作区、canvas 和 connector 视图之间的关系。
- [07 Memory 与 MCP](./07_MEMORY_AND_MCP.md)
  说明 memory、artifact 和内置 MCP 的行为。
- [19 External Controller 指南](./19_EXTERNAL_CONTROLLER_GUIDE.md)
  说明如何在不改 core runtime 的前提下，基于 mailbox 和 `quest_control` 构建可选的外层治理控制器。

## 如果你遇到了问题

- [09 启动诊断](./09_DOCTOR.md)
  启动诊断、排查常见运行问题，先看这篇。
- [15 Codex Provider 配置](./15_CODEX_PROVIDER_SETUP.md)
  如果问题更像出在 Codex profile、provider endpoint、API key 或模型配置上，优先看这篇。
- [24 Claude Code 配置指南](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
  如果问题更像出在 Claude Code 登录、配置目录、permission mode 或 Anthropic 兼容网关上，优先看这篇。
- [27 Kimi Code 配置指南](./27_KIMI_CODE_PROVIDER_SETUP.md)
  如果问题更像出在 Kimi Code 登录、`~/.kimi` home、agent 或 `--yolo` / thinking 配置上，优先看这篇。
- [25 OpenCode 配置指南](./25_OPENCODE_PROVIDER_SETUP.md)
  如果问题更像出在 OpenCode provider 登录、配置文件、模型选择、agent 或 variant 上，优先看这篇。
- [21 本地模型后端指南](./21_LOCAL_MODEL_BACKENDS_GUIDE.md)
  如果问题具体出在本地 OpenAI-compatible 后端以及 `/v1/responses` 支持上，优先看这篇。
- [01 设置参考](./01_SETTINGS_REFERENCE.md)
  如果问题可能和配置、凭据或 connector 有关，再查这篇。

## 如果你在维护 DeepScientist
- [23 BenchStore GitHub Releases 分发规范](./23_BENCHSTORE_GITHUB_RELEASES_SPEC.md)
  如果你想把 BenchStore 的 benchmark 源码包发布到 GitHub Releases，并让用户在前端通过 Download 正常安装，先看这篇。

- [90 Architecture](../en/90_ARCHITECTURE.md)
  说明系统级约束、核心契约和仓库结构。
- [91 Development](../en/91_DEVELOPMENT.md)
  面向维护者的开发工作流、实现说明，以及新增 MCP 工具、skills、connector 的具体清单。

## 社群交流

欢迎加群讨论。

<p align="center">
  <img src="../../assets/readme/wechat6.jpg" alt="DeepScientist 微信群" width="360" />
</p>
