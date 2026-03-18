# 00 快速开始：启动 DeepScientist 并运行第一个项目

这份文档面向第一次使用 DeepScientist 的用户，目标是让你从安装直接走到“成功启动并跑起来一个项目”。

你只需要完成四步：

1. 安装 DeepScientist
2. 启动本地运行时
3. 在首页创建一个新项目
4. 从项目列表重新打开已有任务

本文中的截图直接使用当前在线页面 `deepscientist.cc:20999` 作为示例。你本地运行后的页面 `127.0.0.1:20999` 通常会与它保持一致或非常接近。

## 1. 安装

全局安装 DeepScientist：

```bash
npm install -g @researai/deepscientist
```

如果你后续还要在本地编译论文 PDF，也可以顺手安装轻量级 LaTeX 运行时：

```bash
ds latex install-runtime
```

## 2. 启动 DeepScientist

启动本地 daemon 与 Web 工作区：

```bash
ds
```

DeepScientist 现在使用 `uv` 管理锁定的本地 Python 运行时。如果你已经激活了 conda 环境，且其中的 Python 满足 `>=3.11`，`ds` 会优先使用它；否则 `uv` 会自动在 DeepScientist home 下准备受管 Python。

如果你的机器上还没有 `uv`，第一次运行 `ds` 时会自动在本地安装一份。npm 包本身也已经带上了 Codex CLI 依赖，因此不需要再单独执行 `npm install -g @openai/codex`；但你后续仍然可能需要手动运行一次 `codex` 完成登录。

默认情况下，DeepScientist home 在 macOS / Linux 上是 `~/DeepScientist`，在 Windows 上是 `%USERPROFILE%\\DeepScientist`。如果你希望放到别的路径，可以直接使用 `ds --home <path>`。

如果你希望直接把“当前工作目录”作为 DeepScientist home，可以运行：

```bash
ds --hero
```

它等价于 `ds --home "$PWD"`。

如果你是从源码仓库安装，并希望把默认的 CLI 安装基路径改到别的位置，可以使用：

```bash
bash install.sh --dir /data/DeepScientist
```

如果你已经有一个正在使用的 DeepScientist home，之后又想安全迁移到别的路径，可以使用：

```bash
ds migrate /data/DeepScientist
```

`ds migrate` 会先显示当前绝对路径和目标绝对路径，停止托管 daemon，要求二次确认，校验复制结果，并在确认迁移成功后才删除旧路径。

默认情况下，网页会运行在：

```text
http://127.0.0.1:20999
```

如果浏览器没有自动打开，就手动访问这个地址。

如果你想改端口，可以直接运行：

```bash
ds --port 21000
```

如果你希望绑定到所有网卡地址：

```bash
ds --host 0.0.0.0 --port 21000
```

## 3. 认识首页

启动完成后，先打开 `/` 首页。

![DeepScientist 首页](../images/quickstart/00-home.png)

首页故意做得很简单，核心只有两个按钮：

- `Start Research`：创建一个新的项目，并立刻启动新的研究任务
- `打开项目`：打开已有项目列表，重新进入已经存在的任务

如果你是第一次使用，建议先从 `Start Research` 开始。

## 4. 使用 Start Research 创建新项目

点击 `Start Research`，会弹出启动表单。

![Start Research 弹窗](../images/quickstart/01-start-research.png)

这个弹窗不只是“新建任务”，它还会为 agent 写入本次研究的启动合同。

最重要的字段是：

- `项目 ID`：通常会自动按顺序生成，例如 `00`、`01`、`02`
- `Primary request` / 研究目标：你真正希望 agent 完成的科研任务
- `Reuse Baseline`：可选；如果你要复用已有 baseline，就在这里选择
- `Research intensity`：本次研究的投入强度
- `Decision mode`：`Autonomous` 表示除非真的需要审批，否则 agent 默认持续自主推进
- `Research paper`：是否要求本次任务同时产出论文式结果
- `Language`：本次运行希望使用的用户侧语言

第一次测试时，建议你这样填写：

- 写一个清晰、单一的研究问题
- 如果还没有 baseline，就先留空
- 强度选择 `Balanced` 或 `Sprint`
- 决策模式保持 `Autonomous`

最后点击弹窗底部的 `Start Research` 即可正式启动。

## 5. 使用“打开项目”重新进入已有任务

点击首页上的 `打开项目`，会打开项目列表。

![打开项目 弹窗](../images/quickstart/02-list-quest.png)

这个列表适合以下场景：

- 重新进入一个已经在运行中的项目
- 打开一个以前已经完成或已经创建过的项目
- 按项目标题或项目 ID 搜索目标任务

列表中的每一行都对应一个项目仓库。点击对应卡片即可进入该项目的工作区。

## 6. 打开项目之后会发生什么

创建或打开项目后，DeepScientist 会进入这个项目的工作区页面。

通常你会在里面做这些事情：

1. 在 Copilot / Studio 中观察 agent 的实时进展
2. 查看文件、笔记和生成出来的 artifact
3. 在 Canvas 中理解当前项目的图结构与阶段进展
4. 只有在你明确想中断时，才主动停止任务

## 7. 常用运行命令

查看当前状态：

```bash
ds --status
```

停止当前本地 daemon：

```bash
ds --stop
```

如果启动异常或环境有问题，运行诊断：

```bash
ds doctor
```

## 8. 下一步该看什么

- [01 设置参考：如何配置 DeepScientist](./01_SETTINGS_REFERENCE.md)
- [02 Start Research 参考：如何填写科研启动合同](./02_START_RESEARCH_GUIDE.md)
- [03 QQ 连接器指南：如何用 QQ 与 DeepScientist 沟通](./03_QQ_CONNECTOR_GUIDE.md)
- [05 TUI 使用指南：如何使用终端界面](./05_TUI_GUIDE.md)
