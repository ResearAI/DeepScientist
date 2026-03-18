# 09 `ds doctor`：诊断与修复启动问题

当 DeepScientist 安装后无法正常启动时，请使用 `ds doctor` 做一次本地诊断。

## 推荐使用流程

1. 先安装 DeepScientist：

   ```bash
   npm install -g @researai/deepscientist
   ```

2. 先直接尝试启动：

   ```bash
   ds
   ```

3. 如果启动失败，或者看起来不正常，再运行：

   ```bash
   ds doctor
   ```

4. 从上到下阅读诊断结果，优先修复失败项。

5. 修完后重新运行 `ds doctor`，直到检查通过，再运行 `ds`。

## `ds doctor` 会检查什么

- 本地 Python 运行时是否健康
- `~/DeepScientist` 是否存在且可写
- `uv` 是否可用，以便管理本地 Python 运行时
- `git` 是否安装并完成基本配置
- 必需配置文件是否有效
- 当前开源版本是否仍然使用 `codex` 作为可运行 runner
- Codex CLI 是否存在并通过启动探测
- 是否已经具备可选的本地 `pdflatex` 运行时，以便编译论文 PDF
- Web / TUI bundle 是否存在
- 当前 Web 端口是否空闲，或者是否已运行正确的 daemon

## 常见修复方式

### 没有安装 Codex

重新安装 DeepScientist，让随包的 Codex 依赖一起装好：

```bash
npm install -g @researai/deepscientist
```

### 已安装 Codex，但还没有登录

运行：

```bash
codex
```

先完成一次登录，再重新执行 `ds doctor`。

### 没有安装 `uv`

正常情况下，第一次运行 `ds` 会自动在本地安装 `uv`。如果自动安装失败，再手动执行：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

如果你在 Windows PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 本地论文 PDF 编译暂时不可用

如果你希望直接在 DeepScientist 里本地编译论文，可以安装一个轻量级 TinyTeX `pdflatex` 运行时：

```bash
ds latex install-runtime
```

如果你更倾向于系统级安装，也可以直接安装提供 `pdflatex` 和 `bibtex` 的 LaTeX 发行版。

### `20999` 端口被占用

如果是 DeepScientist 自己之前启动的守护进程：

```bash
ds --stop
```

然后重新执行 `ds`。

如果是其他服务占用了端口，请修改：

```text
~/DeepScientist/config/config.yaml
```

里的 `ui.port`。

也可以直接临时换一个端口启动：

```bash
ds --port 21000
```

### 当前激活的是 Python `3.10` 或更低版本

如果你已经在使用 conda，而当前环境过旧，请先激活正确环境：

```bash
conda activate ds311
python3 --version
which python3
ds
```

或者新建一个可用环境：

```bash
conda create -n ds311 python=3.11 -y
conda activate ds311
ds
```

如果你不手动切换，`ds` 也可以在 DeepScientist home 下自动准备受管的 `uv` + Python 运行时。

### Git 用户身份没有配置

运行：

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

### 误开启了 Claude

当前开源版本里，`claude` 仍然只是 TODO / 预留位，并不能正常运行。
请在：

```text
~/DeepScientist/config/runners.yaml
```

里把它重新设为禁用。

## 说明

- `ds docker` 保留为兼容别名，但正式命令是 `ds doctor`。
- 默认浏览器访问地址是 `http://127.0.0.1:20999`。
