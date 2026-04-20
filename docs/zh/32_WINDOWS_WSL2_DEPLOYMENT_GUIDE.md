# 32 Windows + WSL2 部署指南

本指南适用于 Windows 10/11 用户，通过 WSL2 在本地部署 DeepScientist，并使用阿里百炼 Coding Plan 作为模型后端。步骤覆盖 WSL2 安装、迁移到 D 盘、npm 免 `sudo` 配置、DeepScientist 与固定版本 Codex CLI 安装，以及常见问题排查。

## 适用环境

- Windows 10/11，版本 `2004+`，内部版本 `19041+`
- 阿里百炼 Coding Plan API Key，形如 `sk-sp-...`
- 稳定网络；如遇 GitHub 或 astral 下载失败，可准备代理或镜像

本指南已在 Windows 10 22H2 + WSL2 Ubuntu 22.04 LTS 上手动验证。

## 1. 安装 WSL2 并迁移到 D 盘

### 1.1 启用 WSL 相关功能

以管理员身份打开 PowerShell，执行：

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

### 1.2 重启系统

执行上述命令后，先重启 Windows。

### 1.3 安装 WSL2 内核更新包

从微软官方链接下载安装：

- https://aka.ms/wsl2kernel

通常文件名类似 `wsl.2.6.3.0.x64.msi`。下载安装后双击运行。

### 1.4 设置 WSL2 为默认版本

```powershell
wsl --set-default-version 2
```

### 1.5 安装 Ubuntu 并迁移到 D 盘

如果当前 WSL 版本不支持直接使用 `--location` 指定安装路径，可以采用“导出再导入”的通用方式：

```powershell
# 1. 先临时安装到默认位置
wsl --install -d Ubuntu

# 2. 第一次启动 Ubuntu，完成用户名和密码初始化

# 3. 导出并迁移到 D 盘
wsl --export Ubuntu D:\WSL\Ubuntu.tar
wsl --unregister Ubuntu
mkdir D:\WSL\Ubuntu
wsl --import Ubuntu D:\WSL\Ubuntu D:\WSL\Ubuntu.tar --version 2

# 4. 设置默认用户（把 <your_username> 换成初始化时的用户名）
ubuntu config --default-user <your_username>

# 5. 清理导出文件
del D:\WSL\Ubuntu.tar
```

验证：

```powershell
wsl -l -v
```

确认 Ubuntu 的版本为 `2`，并且 `D:\WSL\Ubuntu\ext4.vhdx` 已生成。

## 2. 进入 WSL，准备基础环境

进入 Ubuntu：

```powershell
wsl -d Ubuntu
```

更新系统并安装基础工具：

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git
```

## 3. 把 npm 全局路径配置到用户目录

这样可以避免全局安装时使用 `sudo`：

```bash
mkdir -p ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## 4. 安装 DeepScientist 和固定版本 Codex CLI

```bash
npm install -g @researai/deepscientist
npm install -g @openai/codex@0.57.0
```

验证：

```bash
codex --version
ds --version
```

其中 `codex --version` 应显示 `0.57.0`。

## 5. 配置阿里百炼 Coding Plan

### 5.1 设置 API Key

编辑 `~/.bashrc`：

```bash
nano ~/.bashrc
```

添加：

```bash
export OPENAI_API_KEY="sk-sp-你的真实API密钥"
```

然后执行：

```bash
source ~/.bashrc
```

### 5.2 创建 Codex 配置文件

```bash
mkdir -p ~/.codex
cat > ~/.codex/config.toml << 'EOF'
model = "qwen3.5-plus"
model_provider = "Model_Studio_Coding_Plan"

[model_providers.Model_Studio_Coding_Plan]
name = "Model_Studio_Coding_Plan"
base_url = "https://coding.dashscope.aliyuncs.com/v1"
env_key = "OPENAI_API_KEY"
wire_api = "chat"

[profiles.bailian]
model = "qwen3.5-plus"
model_provider = "Model_Studio_Coding_Plan"
EOF
```

### 5.3 测试 Codex 配置

```bash
codex --profile bailian
```

在提示符后输入一条简单消息，例如 `你好`，确认可以收到回复，再用 `exit` 退出。

## 6. 安装 uv

DeepScientist 的 Python 运行时依赖 `uv`：

```bash
curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-installer.sh | sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
uv --version
```

## 7. 运行诊断并启动 DeepScientist

### 7.1 运行诊断

```bash
ds doctor --codex-profile bailian
```

大部分检查项应为 `[ok]`。`[warn]` 里常见的是 Git 用户名或 LaTeX 运行时未配置，这些通常不阻止基本启动。

### 7.2 启动服务

```bash
mkdir -p ~/my_research && cd ~/my_research
ds --here --codex-profile bailian
```

成功后终端会显示本地 Web 地址，例如：

```text
Local web UI: http://127.0.0.1:20999
```

### 7.3 在 Windows 浏览器里访问

直接在 Windows 浏览器中打开：

- http://127.0.0.1:20999

然后点击 `Start Research` 开始使用。

## 8. 停止服务

在 WSL 终端中按 `Ctrl+C`，或执行：

```bash
ds --stop
```

## 9. 常见问题

| 现象 | 处理方式 |
|---|---|
| `wsl --import` 报 `HCS_E_HYPERV_NOT_INSTALLED` | 在 BIOS 中开启虚拟化，并执行 `bcdedit /set hypervisorlaunchtype auto` 后重启 |
| `npm install -g` 权限错误 | 确认已把 npm 全局路径配置到用户目录 |
| `ds doctor` 提示 Codex 版本不兼容 | 确认安装的是 `@openai/codex@0.57.0` |
| Codex 可用但 DeepScientist 启动失败 | 确认启动时带了 `--codex-profile bailian` |
| `wire_api = "chat"` 弃用警告 | 目前可忽略；未来待上游兼容后可切到 `responses` |
| `uv` 下载失败 | 配置代理，或尝试 `pip install uv --user` 作为替代 |

## 10. 可选优化

- 配置 Git 用户信息：

  ```bash
  git config --global user.name "Your Name"
  git config --global user.email "you@example.com"
  ```

- 安装 LaTeX 运行时：

  ```bash
  sudo apt install -y texlive-latex-base texlive-latex-recommended texlive-fonts-recommended texlive-bibtex-extra
  ```

  或使用 DeepScientist 内置运行时：

  ```bash
  ds latex install-runtime
  ```

- 若你想让某个项目默认使用 `bailian` profile，可以在项目目录下调整对应 runner 配置。

## 验证说明

本指南基于以下环境手动验证：

- Windows 10 22H2
- WSL2 Ubuntu 22.04.5 LTS
- Node.js 20.x
- npm 10.8.2
- Codex CLI 0.57.0
- DeepScientist 1.5.17
- 阿里百炼 Coding Plan（`qwen3.5-plus`）

如果后续项目版本、Codex 版本或阿里百炼 API 兼容方式发生变化，请以最新官方文档为准，并优先复查：

- [15_CODEX_PROVIDER_SETUP.md](./15_CODEX_PROVIDER_SETUP.md)
- [09_DOCTOR.md](./09_DOCTOR.md)
