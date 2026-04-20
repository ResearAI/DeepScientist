# 32 Windows + WSL2 Deployment Guide

This guide helps Windows 10/11 users deploy DeepScientist through WSL2, keep the Linux image on drive `D:`, configure npm global installs without `sudo`, and use Alibaba Bailian Coding Plan as the Codex backend.

It covers:

- installing WSL2
- moving the Ubuntu image to `D:`
- configuring npm global installs into the user directory
- installing DeepScientist and the pinned Codex CLI version
- configuring Alibaba Bailian Coding Plan
- common troubleshooting steps

The procedure was manually verified on Windows 10 22H2 + WSL2 Ubuntu 22.04 LTS.

## Requirements

- Windows 10/11, version `2004+`, build `19041+`
- an Alibaba Bailian Coding Plan API key, typically `sk-sp-...`
- stable network access; if GitHub or astral downloads fail, prepare a proxy or mirror

## 1. Install WSL2 and move it to drive D

### 1.1 Enable WSL features

Open PowerShell as Administrator and run:

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

### 1.2 Reboot Windows

Restart after enabling the features.

### 1.3 Install the WSL2 kernel update

Download and install the package from Microsoft:

- https://aka.ms/wsl2kernel

The file name is usually similar to `wsl.2.6.3.0.x64.msi`.

### 1.4 Set WSL2 as the default version

```powershell
wsl --set-default-version 2
```

### 1.5 Install Ubuntu and move it to drive D

If your WSL build does not support `--location`, use export/import:

```powershell
# 1. Install Ubuntu to the default location first
wsl --install -d Ubuntu

# 2. Launch Ubuntu once and finish the initial username/password setup

# 3. Export and re-import it onto drive D
wsl --export Ubuntu D:\WSL\Ubuntu.tar
wsl --unregister Ubuntu
mkdir D:\WSL\Ubuntu
wsl --import Ubuntu D:\WSL\Ubuntu D:\WSL\Ubuntu.tar --version 2

# 4. Set the default user (replace <your_username>)
ubuntu config --default-user <your_username>

# 5. Remove the temporary archive
del D:\WSL\Ubuntu.tar
```

Verify:

```powershell
wsl -l -v
```

Confirm that Ubuntu shows version `2` and that `D:\WSL\Ubuntu\ext4.vhdx` exists.

## 2. Enter WSL and prepare the base environment

Launch Ubuntu:

```powershell
wsl -d Ubuntu
```

Update packages and install the basic tools:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git
```

## 3. Configure npm global installs into the user directory

This avoids using `sudo` for global npm packages:

```bash
mkdir -p ~/.npm-global
npm config set prefix '~/.npm-global'
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## 4. Install DeepScientist and the pinned Codex CLI version

```bash
npm install -g @researai/deepscientist
npm install -g @openai/codex@0.57.0
```

Verify:

```bash
codex --version
ds --version
```

`codex --version` should report `0.57.0`.

## 5. Configure Alibaba Bailian Coding Plan

### 5.1 Export the API key

Edit `~/.bashrc`:

```bash
nano ~/.bashrc
```

Add:

```bash
export OPENAI_API_KEY="sk-sp-your-real-key"
```

Then reload:

```bash
source ~/.bashrc
```

### 5.2 Create the Codex configuration

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

### 5.3 Verify Codex access

```bash
codex --profile bailian
```

Type a short prompt such as `hello`, confirm a valid model reply, then exit.

## 6. Install `uv`

DeepScientist relies on `uv` for Python runtime management:

```bash
curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-installer.sh | sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
uv --version
```

## 7. Run diagnostics and start DeepScientist

### 7.1 Run doctor

```bash
ds doctor --codex-profile bailian
```

Most checks should be `[ok]`. Common `[warn]` items such as missing Git identity or missing LaTeX runtime usually do not block basic startup.

### 7.2 Start the service

```bash
mkdir -p ~/my_research && cd ~/my_research
ds --here --codex-profile bailian
```

When startup succeeds, the terminal prints a local web address such as:

```text
Local web UI: http://127.0.0.1:20999
```

### 7.3 Open it from the Windows browser

Open this address in Chrome or Edge:

- http://127.0.0.1:20999

Then click `Start Research`.

## 8. Stop the service

Press `Ctrl+C` in the WSL terminal, or run:

```bash
ds --stop
```

## 9. Common issues

| Symptom | What to do |
|---|---|
| `wsl --import` shows `HCS_E_HYPERV_NOT_INSTALLED` | Enable virtualization in BIOS, run `bcdedit /set hypervisorlaunchtype auto`, then reboot |
| `npm install -g` fails with permissions | Recheck the npm global directory configuration from step 3 |
| `ds doctor` says the Codex version is incompatible | Confirm that `@openai/codex@0.57.0` is installed |
| Codex works but DeepScientist does not start | Make sure you launched with `--codex-profile bailian` |
| `wire_api = "chat"` shows a deprecation warning | It is currently safe to ignore; migrate to `responses` later when the provider supports it |
| `uv` download fails | Use a proxy or fall back to `pip install uv --user` |

## 10. Optional improvements

- Configure Git identity:

  ```bash
  git config --global user.name "Your Name"
  git config --global user.email "you@example.com"
  ```

- Install a LaTeX runtime:

  ```bash
  sudo apt install -y texlive-latex-base texlive-latex-recommended texlive-fonts-recommended texlive-bibtex-extra
  ```

  Or use the built-in runtime:

  ```bash
  ds latex install-runtime
  ```

- If you want a project to prefer the `bailian` profile by default, update the relevant runner configuration inside that project.

## Verification notes

This guide was manually verified on:

- Windows 10 22H2
- WSL2 Ubuntu 22.04.5 LTS
- Node.js 20.x
- npm 10.8.2
- Codex CLI 0.57.0
- DeepScientist 1.5.17
- Alibaba Bailian Coding Plan with `qwen3.5-plus`

If package versions, Codex compatibility, or Bailian API behavior changes later, recheck the latest official references first:

- [15_CODEX_PROVIDER_SETUP.md](./15_CODEX_PROVIDER_SETUP.md)
- [09_DOCTOR.md](./09_DOCTOR.md)
