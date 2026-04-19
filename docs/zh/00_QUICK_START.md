# 00 快速开始：启动 DeepScientist 并运行第一个项目

可以把 DeepScientist 理解成一个长期运行在本地的科研工作区：你定义任务，准备资源，它持续往前推进，并把文件、分支、笔记和结果都留在你的机器上。

这份文档面向第一次使用 DeepScientist 的用户，写法尽量偏“照着做”：一步做什么、为什么这么做，都讲清楚。

你只需要完成四步：

1. 安装 DeepScientist
2. 启动本地运行时
3. 打开首页
4. 用一个真实示例创建第一个项目

本文中的截图直接使用当前在线页面 `deepscientist.cc:20999` 作为示例。你本地运行后的页面 `127.0.0.1:20999` 通常会与它保持一致或非常接近。

当前平台支持：DeepScientist 目前完整支持 Linux 和 macOS。原生 Windows 支持目前仍处于实验阶段（强烈建议优先使用 WSL2，尤其是在你希望获得最接近 Linux 的终端行为时）。

## 安全建议：先隔离，再启动

在你第一次启动 DeepScientist 前，强烈建议先接受下面这条原则：

- 如果环境允许，优先在 Docker 容器、虚拟机或同等级隔离环境中运行
- 一律使用非 root 账号启动，不要直接用 root 运行
- 不要优先拿生产机、重要服务器或带敏感数据的宿主机做首次试跑
- 不要轻易把 `0.0.0.0` 端口、反向代理地址或网页入口公开分享给别人
- 如果后面会绑定微信、QQ、Lingzhu 等 connector，更不要把这个站点当成可随意共享的网页

原因很直接：DeepScientist 具备自动执行命令、改文件、安装依赖、发送外部消息和读写项目数据的能力。一旦权限给大了，或者站点被错误暴露，后果可能包括服务器损坏、数据丢失、密钥泄露、connector 被盗用，甚至研究结果被错误伪造却未被及时发现。

完整说明见：

- [11 协议与风险说明](./11_LICENSE_AND_RISK.md)

## 0. 开始前先准备什么

建议你先准备好这些：

- 安装好 Node.js `>=18.18` 和 npm `>=9`；请优先参考官方页面安装：https://nodejs.org/en/download
- 一条已经可用的 runner 路径：
  - `codex` 是主路径，也是目前最稳妥的路径
  - `claude` 属于 supported experimental，并且应先在你的 shell 里直接可用
  - `opencode` 属于 supported experimental，并且应先在你的 shell 里直接可用
- 模型或 API 凭证
- 如果任务比较重，准备好 GPU 或远程服务器
- 如果你要长期运行，优先准备 Docker 或其他隔离环境，并准备一个非 root 账号专门启动 DeepScientist
- 如果要从已有工作开始，准备好代码仓库、数据或 baseline 链接
- 如果你希望在网页之外接收进展，也可以先配置一个 connector，例如 QQ

如果你还在选择合适的 Coding Plan / 订阅方案，可以先看这些官方页面：

- 如果你只是想先有一个简单直接的推荐起点，优先从 GPT-5.4 + `xhigh` reasoning effort 开始；如果你更偏向 Google 路线，可以使用 Gemini 3 Pro，对应模型名 `gemini-3-pro-preview`。
- ChatGPT 定价：https://openai.com/chatgpt/pricing/
- ChatGPT Plus 帮助页：https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus%3F.eps
- MiniMax Coding Plan：https://platform.minimaxi.com/docs/guides/pricing-codingplan
- GLM Coding Plan：https://docs.bigmodel.cn/cn/coding-plan/overview
- 阿里百炼 Coding Plan：https://help.aliyun.com/zh/model-studio/coding-plan
- 火山引擎 Ark Coding Plan：https://www.volcengine.com/docs/82379/1925115?lang=zh

如果你要通过阿里百炼使用 Qwen，请只使用百炼 **Coding Plan** endpoint。普通百炼 / DashScope 平台的 Qwen API，不在当前 Codex-backed DeepScientist 支持范围内。

如果你只是想先走最稳的一条，优先从 Codex 开始。

第一次正式启动前，请先看和自己 runner 对应的那篇配置文档：

- [15 Codex Provider 配置](./15_CODEX_PROVIDER_SETUP.md)
- [24 Claude Code 配置指南](./24_CLAUDE_CODE_PROVIDER_SETUP.md)
- [25 OpenCode 配置指南](./25_OPENCODE_PROVIDER_SETUP.md)

## 1. 先安装 Node.js，再安装 DeepScientist

DeepScientist 目前完整支持 Linux 和 macOS。原生 Windows 支持目前仍处于实验阶段（强烈建议优先使用 WSL2，尤其是在你希望获得更稳定、更接近 Linux 的 shell 行为时）。

在安装 DeepScientist 本身之前，请先从 Node.js 官方页面安装 Node.js：

https://nodejs.org/en/download

请确保你的环境满足：

- Node.js `>=18.18`
- npm `>=9`

运行：

```bash
npm install -g @researai/deepscientist
```

这一步会把 `ds` 命令安装到你的机器上。

DeepScientist 现在内建三条 runner 路径：

- `codex`：主路径
- `claude`：supported experimental
- `opencode`：supported experimental

安装相关有一个很重要的差异：

- 对 `codex`，DeepScientist 会优先使用你机器上已有的 `codex`，本机找不到时才回退到 npm 包里 bundled 的依赖。
- 对 `claude` 和 `opencode`，DeepScientist 不会替你完成安装和认证；这两条路径都应该先让 CLI 本身跑通，再交给 DeepScientist 复用。

如果安装完成后 `codex` 仍然不可用，请显式修复：

```bash
npm install -g @openai/codex
```

最稳妥的做法是立刻验证命令是否真的可用：

```bash
which codex
codex login
```

如果 `which codex` 没有输出，问题通常不是 DeepScientist 本身，而是 npm 全局 bin 目录没有正确进入 shell 的 PATH。先修复 PATH，再重新执行 `npm install -g @openai/codex`。

如果你后面还要在本地编译论文 PDF，可以再运行：

```bash
ds latex install-runtime
```

这一步会安装一个轻量级 TinyTeX 运行时。

## 2. 第一次运行 `ds` 前，先完成你要使用的 runner 配置

如果你还没决定，优先从 `codex` 开始。

### 2.1 Codex：默认 OpenAI 登录路径

运行：

```bash
codex login
```

如果你更喜欢交互式首次配置，就运行：

```bash
codex
```

然后在交互式界面里完成认证。

接着先做一次环境确认：

```bash
ds doctor
```

### 2.2 Codex：provider-backed 的 profile 路径

如果你已经在 MiniMax、GLM、火山方舟、阿里百炼 Coding Plan 或其他 provider 上配置了一个命名的 Codex profile，请先在终端里确认这个 profile 本身可用：

```bash
codex --profile m27
```

然后用同一个 profile 去跑 DeepScientist：

```bash
ds doctor --codex-profile m27
```

之后启动：

```bash
ds --codex-profile m27
```

如果你这一轮还想强制指定某一个 Codex 可执行文件，也可以一起加上 `--codex`：

```bash
ds doctor --codex /absolute/path/to/codex --codex-profile m27
ds --codex /absolute/path/to/codex --codex-profile m27
```

这里的 `m27` 是本仓库统一使用的 MiniMax profile 示例名。MiniMax 官方页面当前示例名是 `m21`，但 profile 名只是本地别名；如果你自己用了别的名字，就把命令里的名字一起改掉。

DeepScientist 会在启动前强制做一次真实的 Codex hello 探测。当前 `~/DeepScientist/config/runners.yaml` 里的默认 runner 模型已经是 `inherit`。如果你的旧配置里还固定写着某个显式模型，而你的 provider 又希望模型由 profile 自己决定，请把 `model` 改成 `inherit`；或者直接使用 `--codex-profile <name>`，让这一轮启动自动继承 profile 对应的模型。

MiniMax 额外说明：

- 如果当前最新版 `@openai/codex` 和 MiniMax 走不通，直接安装 `npm install -g @openai/codex@0.57.0`
- 如果 DeepScientist 在启动时检测到 MiniMax profile，但当前 Codex CLI 不是 `0.57.0`，现在会在交互式终端里主动提示是否自动安装 `0.57.0`
- 先创建 MiniMax `Coding Plan Key`
- 如果你要单独在终端里验证 `codex --profile <name>`，先在当前 shell 里执行 `unset OPENAI_API_KEY` 和 `unset OPENAI_BASE_URL`
- 使用 `https://api.minimaxi.com/v1`
- MiniMax 官方 Codex CLI 页面当前给出的 `codex-MiniMax-*` 模型名，在本地用提供的 key 实测并不能稳定通过 Codex CLI
- 当前本地实测可用于 DeepScientist 的模型名是 `MiniMax-M2.7` 和 `MiniMax-M2.5`
- 如果你要走 `m25`，请使用 `MiniMax-M2.5`，不要写成 `codex-MiniMax-M2.5`
- DeepScientist 现在可以在 probe 和运行时自动适配 MiniMax profile-only 的 `model_provider` / `model` 配置形态
- 当 provider 设置了 `requires_openai_auth = false` 时，DeepScientist 也会自动移除冲突的 `OPENAI_*` 认证环境变量
- 如果你还希望终端里的 `codex --profile <name>` 也直接可用，再在 `~/.codex/config.toml` 顶层补上 `model_provider = "minimax"`，以及对应的顶层 `model`，例如 `MiniMax-M2.7` 或 `MiniMax-M2.5`
- 当 DeepScientist 检测到旧版 Codex CLI 不支持 `xhigh` 时，会自动把它降级成 `high`

### 2.3 Claude Code 路径

这条路径适合你本机里的 `claude` 已经能直接工作时使用。

最短验证路径是：

```bash
claude --version
claude -p --output-format json --tools "" "Reply with exactly HELLO."
ds doctor --runner claude
```

确认通过后，再用 Claude Code 启动 DeepScientist：

```bash
ds --runner claude
```

如果你要看完整顺序、配置映射和网关说明，继续读：

- [24 Claude Code 配置指南](./24_CLAUDE_CODE_PROVIDER_SETUP.md)

### 2.4 OpenCode 路径

这条路径适合你本机里的 `opencode` 已经能直接工作时使用。

最短验证路径是：

```bash
opencode --version
opencode run --format json --pure "Reply with exactly HELLO"
ds doctor --runner opencode
```

确认通过后，再用 OpenCode 启动 DeepScientist：

```bash
ds --runner opencode
```

如果你要看完整顺序、配置映射和 provider 说明，继续读：

- [25 OpenCode 配置指南](./25_OPENCODE_PROVIDER_SETUP.md)

## 3. 启动本地运行时

运行：

```bash
ds
```

这会启动本地 daemon 和网页工作区。

如果你希望这一轮直接用非默认 runner，可以显式加上 `--runner`：

```bash
ds --runner claude
ds --runner opencode
```

如果目标 runner 已经通过 `ds doctor`，且你准备长期使用它，后面再去 `~/DeepScientist/config/config.yaml` 或 Settings 页面把 `config.default_runner` 切过去。

再次强调：

- 推荐优先在 Docker 或其他隔离环境里运行
- 推荐始终使用非 root 用户启动
- 如果只是第一次试跑，不要先把服务暴露到公网

DeepScientist 现在使用 `uv` 管理锁定的本地 Python 运行时。如果你已经激活了 conda 环境，且其中的 Python 满足 `>=3.11`，`ds` 会优先使用它；否则会自动在 DeepScientist home 下准备一份受管 Python。

默认情况下，DeepScientist home 是：

- macOS / Linux：`~/DeepScientist`

如果你希望把 DeepScientist home 放到当前目录下，可以运行：

```bash
ds --here
```

它等价于 `ds --home "$PWD/DeepScientist"`。

重要提醒：

- 现在如果你是在某个目录里用 `ds --here` 启动，后续直接在同一目录执行 `ds --status`、`ds --stop`、`ds --restart`，launcher 通常会优先识别当前目录下的 `./DeepScientist`
- 如果你是通过显式的 `--home <path>`，或者机器上同时存在多个 DeepScientist home，仍然建议后续管理命令继续显式使用同一个 home
- 如果你是通过 `DEEPSCIENTIST_HOME` 或 `DS_HOME` 环境变量固定 home，只要后续命令继续使用同一个环境变量配置，也可以
- 当存在多个非默认 home 时，显式指定 `--home` 仍然是最稳妥的做法

例如，当你使用的是非默认 home 时，应这样执行：

```bash
ds --status --home /path/to/DeepScientist
ds --stop --home /path/to/DeepScientist
```

如果你想换一个端口，可以运行：

```bash
ds --port 21000
```

这会把网页界面放到 `21000` 端口。

默认情况下，DeepScientist 启动时不会开启本地浏览器密码门禁。

- 如果浏览器没有自动打开，就手动访问普通本地地址，例如 `http://127.0.0.1:20999`
- 如果你想在某次启动里启用本地浏览器密码，可以用 `ds --auth true`
- 在启用密码模式的启动中，终端会直接打印这次启动生成的密码
- 如果当前浏览器还没有登录，本地首页会先弹出密码框，再继续显示后续界面
- 第一次成功进入后，浏览器会保存这次本地登录，之后再次访问通常不需要重复输入
- 如果你之后忘了某次启用密码启动的密码，可以回到启动终端查看，或者执行 `ds --status`

## 4. 打开首页

启动完成后，先打开 `/` 首页。

![DeepScientist 首页](../images/quickstart/00-home.png)

运行 12 小时之后，你的项目首页更可能像下面这样：

![DeepScientist 项目首页](../assets/branding/projects.png)

你最先会看到两个入口：

- `Start Research` 或 `Start Experiment`：进入新项目创建流程
- `Open Project`：重新打开已有项目

第一次使用时，先点击 `Start Research` 或 `Start Experiment`。

这里有一个重要变化：

- 现在系统会先让你选择启动方式
- `Copilot`：先创建一个安静待命的项目，等你发第一条明确指令
- `Autonomous`：标准版 DeepScientist，创建后直接开始推进

如果你还不确定该选哪一个，先看 [20 工作区模式指南](./20_WORKSPACE_MODES_GUIDE.md)。

## 5. 用一个真实示例创建第一个项目

这里使用一个经过整理的真实示例，它来自 quest `025` 的启动输入，但我把它改得更正式、更适合公开文档。

这个示例项目的目标是：

- 复现官方的 Mandela-Effect baseline
- 保持原论文的任务定义与评测协议
- 研究在混合正确 / 错误社会信号下，如何实现更强的 truth-preserving collaboration
- 在这个参考示例里，使用两个本地推理端点提高吞吐量

点击 `Start Research` / `Start Experiment`，然后选择 `Autonomous Mode`，再进入下面这条标准创建流程。

![Start Research 弹窗](../images/quickstart/01-start-research.png)

### 5.1 先填简短字段

先用这些值：

| 界面字段 | 示例值 | 为什么这样填 |
|---|---|---|
| `Project title` | `Mandela-Effect Reproduction and Truth-Preserving Collaboration` | 标题简短、明确，后面在项目列表里也好认 |
| `Project ID` | 留空，或填 `025` | 想自动编号就留空；只有你明确想固定项目编号时才手动填写 |
| `Connector delivery` | 第一次建议用 `Local only` | 先把本地工作流跑通；如果你已经配好了 QQ 等 connector，也可以在这里直接绑定一个目标 |

### 5.2 填写主研究请求

把下面这段内容粘贴到 `Primary research request`：

```text
Please reproduce the official Mandela-Effect repository and paper, then study how to improve truth-preserving collaboration under mixed correct and incorrect social signals.

The core research question is: how can a multi-agent system remain factually robust under social influence while still learning from correct peers?

Keep the task definition and evaluation protocol aligned with the original work. Focus on prompt-based or system-level methods that improve truth preservation without simply refusing all social information.
```

这段写法是比较好的，因为它同时做了四件事：

- 明确告诉系统要复现什么 baseline
- 把核心研究问题单独说清楚
- 说明边界：不要换任务，不要乱改评测协议
- 给出研究方向提示，但没有把实现路线写死

### 5.3 填写 baseline 和参考资料

如果这是你第一次跑这个任务，`Reusable baseline` 先留空。

如果你已经把官方 baseline 导入过 registry，那么这里就直接选择它。这样 DeepScientist 会优先 attach 这个可信 baseline，而不是重新从零恢复。

把下面内容粘贴到 `Baseline links`：

```text
https://github.com/bluedream02/Mandela-Effect
```

把下面内容粘贴到 `Reference papers / repos`：

```text
https://arxiv.org/abs/2602.00428
```

这两项的作用很直接：

- `Baseline links` 告诉系统 baseline 从哪里恢复
- `Reference papers / repos` 告诉系统哪篇论文和哪套方法定义了这个任务

### 5.4 填写运行约束

把下面内容粘贴到 `Runtime constraints`：

下面这段只是教程参考，不是 DeepScientist 的默认端点配置。粘贴前请把端点、API key 和模型名替换成你自己的真实运行时。

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

这个字段非常重要。很多用户会把运行细节散落在聊天里，但真正稳妥的做法，是把它们写成项目的硬约束。

### 5.5 填写研究目标

把下面内容粘贴到 `Goals`：

```text
1. Restore and verify the official Mandela-Effect baseline as a trustworthy starting point.
2. Measure key metrics and failure modes on the designated `gpt-oss-120b` setup.
3. Propose at least one literature-grounded direction for stronger truth-preserving collaboration.
4. Produce experiment and analysis artifacts that are strong enough to support paper writing.
```

这里不要写成“做出一个很厉害的方法”这种空话。更好的写法是把“第一轮真正要交付什么”拆成几条明确结果。

### 5.6 选择策略字段

这个例子里，建议你使用下面这些选项：

| 界面字段 | 示例值 | 实际含义 |
|---|---|---|
| `Research paper` | `On` | 这个项目默认继续推进到分析和论文式产出 |
| `Research intensity` | `Balanced` | 先把 baseline 立稳，再测试一个合理方向 |
| `Decision mode` | `Autonomous` | 普通路线选择默认自己推进，除非真的需要用户决定 |
| `Launch mode` | `Standard` | 按默认科研主线启动 |
| `Language` | `English` | 默认用英文组织 kickoff prompt 和用户侧产物 |

你在前端里选完这些以后，系统还会自动推导出一组真正提交的合同字段：

- `scope = baseline_plus_direction`
- 如果没有选 `Reusable baseline`，则 `baseline_mode = restore_from_url`
- 如果选了 `Reusable baseline`，则 `baseline_mode = existing`
- `resource_policy = balanced`
- `time_budget_hours = 24`
- `git_strategy = semantic_head_plus_controlled_integration`

这就是为什么 `Start Research` 不只是“新建项目表单”。它还会写入一份结构化的 `startup_contract`，后续 prompt builder 会持续读取它。

### 5.7 检查预览，然后创建项目

点击创建之前，先检查右侧的 prompt 预览。

至少确认这几件事都在里面：

- 研究请求是否清楚
- baseline 链接是否对
- 参考论文是否对
- 运行约束是否完整
- 目标是否写成了可执行结果
- 决策模式和交付模式是否符合预期

确认没问题之后，点击 `Create project`。

这时前端实际会提交：

- 一段编译好的 kickoff prompt
- 一个可选的 `requested_baseline_ref`
- 一个可选的 `requested_connector_bindings`
- 一份结构化的 `startup_contract`

如果你想进一步理解这些字段的真实提交结构，请继续看 [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)。

## 6. 重新打开已有项目

点击首页上的 `Open Project`，会打开项目列表。

![打开项目 弹窗](../images/quickstart/02-list-quest.png)

你可以用它来：

- 重新进入一个正在运行中的项目
- 重新打开以前完成过的项目
- 按项目标题或项目 ID 搜索目标项目

列表中的每一行都对应一个项目仓库。点击卡片即可进入。

## 7. 打开项目之后会发生什么

创建或打开项目后，DeepScientist 会进入这个项目的工作区。

通常第一轮你会做这些事情：

1. 在 Copilot / Studio 里看进展
2. 检查文件、笔记和 artifact
3. 在 Canvas 中理解项目图结构与阶段进展
4. 除非你明确想打断，否则先让任务继续推进

## 8. 常用运行命令

查看当前状态：

```bash
ds --status
```

这会告诉你本地运行时是否正常在线。

停止 daemon：

```bash
ds --stop
```

这会停止当前本地 DeepScientist daemon。

卸载代码和运行时，但保留本地数据：

```bash
ds uninstall
```

如果你使用的是非默认 home，可以显式指定：

```bash
ds uninstall --home /path/to/DeepScientist --yes
```

这会删除 launcher wrapper、本地运行时代码，以及 install-local 安装树，但会保留：

- `quests/`
- `memory/`
- `config/`
- `logs/`
- `plugins/`
- `cache/`

如果你是通过 npm 安装的，并且还想把全局 npm 包本体一起移除，请在 `ds uninstall` 之后再执行：

```bash
npm uninstall -g @researai/deepscientist
```

如果你真的想把本地数据一起删掉，请在卸载后手动删除 DeepScientist home：

```bash
rm -rf /path/to/DeepScientist
```

运行诊断：

```bash
ds doctor
```

当你怀疑是启动、配置、runner 或 connector 出问题时，用这个命令排查。

## 9. 下一步该看什么

- [文档总览](./README.md)
- [12 引导式工作流教程](./12_GUIDED_WORKFLOW_TOUR.md)
- [02 Start Research 参考](./02_START_RESEARCH_GUIDE.md)
- [13 核心架构说明](./13_CORE_ARCHITECTURE_GUIDE.md)
- [01 设置参考](./01_SETTINGS_REFERENCE.md)
- [03 QQ 连接器指南](./03_QQ_CONNECTOR_GUIDE.md)
- [05 TUI 使用指南](./05_TUI_GUIDE.md)

## 10. 简短 FAQ

### 如果我是从源码仓库安装，想装到另一个目录里，怎么做？

运行：

```bash
bash install.sh --dir /data/DeepScientist
```

这个命令适合你在源码 checkout 里工作，但希望把 DeepScientist 安装到另一个独立运行目录时使用。

### 如果我已经有一个 DeepScientist home，想安全迁移到新路径，怎么做？

运行：

```bash
ds migrate /data/DeepScientist
```

这是迁移现有 DeepScientist home 的正式方式。

### 如果我确实需要监听所有网卡，怎么启动？

运行：

```bash
ds --host 0.0.0.0 --port 21000
```

只有在你确实需要外部访问时才这样做，而且建议先看风险说明：

- [11 协议与风险说明](./11_LICENSE_AND_RISK.md)
