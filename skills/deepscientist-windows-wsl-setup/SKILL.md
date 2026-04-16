---
name: deepscientist-windows-wsl-setup
description: Install, repair, and validate DeepScientist on Windows with WSL2 until the Windows browser can open the DeepScientist Web UI. Use when an agent needs to set up or fix DeepScientist on a Windows machine, including WSL distro creation, Linux-side Node/Python prerequisites, Codex auth/relay configuration, WSL proxy troubleshooting, and final `ds doctor` or Web UI verification.
---

# DeepScientist Windows WSL Setup

## One-liner for humans

Copy this to any AI coding agent (Claude Code, Codex, Cursor, etc.) to trigger the install:

> Install DeepScientist on this Windows machine using WSL2. Follow the skill at `deepscientist-windows-wsl-setup/SKILL.md` in the DeepScientist repo for the full procedure. Keep going until `ds doctor` passes and I can open http://127.0.0.1:20999 in my Windows browser.

## Workflow

1. Read the current official DeepScientist README and Windows WSL2 deployment guide before changing anything. Use the official repo as the source of truth for install commands and note any version pins or prerequisites that changed.
2. Inspect the machine first:
   - `wsl -l -v`
   - `wsl --status`
   - Check whether a usable WSL2 Ubuntu distro already exists.
   - Check whether Linux-side `node`, `npm`, `git`, `uv`, `codex`, and `ds` already exist inside the target distro.
3. Prefer a dedicated WSL2 Ubuntu distro for DeepScientist instead of modifying `docker-desktop` or converting an unrelated user distro unless the user asks for that explicitly.
4. Keep working until these end-state checks pass:
   - Linux-side `codex exec --skip-git-repo-check "Print exactly OK and exit."` succeeds.
   - `ds doctor` reports `[ok] Codex CLI` (or `[warn] Codex CLI: Codex startup probe completed.`).
   - `ds` starts and Windows can open `http://127.0.0.1:20999`.

## Human actions required

Some steps require the human to act. The agent cannot do these:

| When | What the human must do |
|------|------------------------|
| WSL cannot start (HCS_E_CONNECTION_TIMEOUT) | Reboot the PC. Pending Windows updates or long uptimes cause Hyper-V VM creation to fail. |
| Proxy listens only on 127.0.0.1 | Open the proxy app (Clash, v2rayN, etc.) and enable **Allow LAN** so it listens on 0.0.0.0. |
| No valid OpenAI auth | Either (a) run `codex login` in a GUI terminal, or (b) provide an API key or relay config. |
| ChatGPT subscription expired | Renew subscription, or provide a third-party API relay endpoint and key. |
| Firewall blocks WSL networking | Temporarily allow WSL/Hyper-V through Windows Firewall. |

## Pre-flight checks (critical)

### HCS_E_CONNECTION_TIMEOUT
If `wsl -d <distro> -- echo hello` fails with `HCS_E_CONNECTION_TIMEOUT`:
1. Check pending reboot: look at `HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager` for `PendingFileRenameOperations`.
2. Check uptime: `(Get-CimInstance Win32_OperatingSystem).LastBootUpTime`. If > 7 days, suggest reboot.
3. Try `wsl --shutdown` then retry. If it still fails, a reboot is required.
4. **Do not proceed with installation until WSL can start.**

### Available memory
If free memory < 2 GB, warn the user. WSL2 VM needs at least 1 GB to start reliably. Check with:
```powershell
$mem = Get-CimInstance Win32_OperatingSystem
[math]::Round($mem.FreePhysicalMemory/1MB,2)
```

## Distro setup

- If no suitable WSL2 Ubuntu distro exists, install one with a dedicated name such as `DeepScientist`.
- Prefer Ubuntu 22.04 or 24.04 unless the official guide says otherwise.
- If the user already has a broken WSL1 distro, do not repurpose it by default. Create a new WSL2 distro and leave the old one alone.
- After installation, create a normal Linux user such as `ds` and make it the default user for that distro.
- Disable Windows PATH injection in the DeepScientist distro to avoid accidentally using Windows-side `npm`, `codex`, or other binaries:

```bash
printf '[interop]\nappendWindowsPath=false\n' | sudo tee /etc/wsl.conf
```

- **Restart that distro after changing `/etc/wsl.conf`** with `wsl --terminate <distro>`.
- After restart, verify that `command -v node` does NOT resolve to `/mnt/c/...`.

## Linux prerequisites

Install the Linux-side dependencies inside the target distro. Prefer native Linux binaries over Windows binaries mounted under `/mnt/c` or other drives.

Required baseline (adapt the python3-venv package name to the distro version):
```bash
sudo apt-get update
# Ubuntu 24.04:
sudo apt-get install -y ca-certificates curl gnupg git sudo build-essential python3-venv python3-pip
# Ubuntu 22.04:
sudo apt-get install -y ca-certificates curl gnupg git sudo build-essential python3.10-venv python3-pip
```

Install Node.js 20 unless the official guide says otherwise:
```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
printf 'deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main\n' | sudo tee /etc/apt/sources.list.d/nodesource.list
sudo apt-get update
sudo apt-get install -y nodejs
```

Set a user-local npm prefix so global packages do not require sudo:
```bash
mkdir -p "$HOME/.npm-global" "$HOME/.local/bin"
npm config set prefix "$HOME/.npm-global"
```

Add to both `~/.bashrc` and `~/.profile`:
```bash
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"
```

## DeepScientist installation

- Install the current official DeepScientist package from npm.
- Install `uv`.
- Install the Codex CLI version required by the official DeepScientist guide. If the guide pins a specific version, follow the guide instead of guessing.

Typical pattern:
```bash
npm install -g @researai/deepscientist
npm install -g @openai/codex@0.57.0
curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-installer.sh | sh
```

After installation, verify Linux-side resolution:
```bash
command -v ds
command -v codex
command -v uv
```

**All three must resolve to Linux paths** (under `$HOME/.npm-global/bin` or `$HOME/.local/bin`), NOT under `/mnt/c/`.

## Codex auth and API relay

### Option A: Reuse Windows-side ChatGPT auth
If WSL cannot complete browser-based Codex login, reuse the Windows-side auth file:

1. Inspect whether Windows already has a working auth file at `C:\Users\<user>\.codex\auth.json`.
2. Back up any existing Linux auth file first.
3. Copy the Windows auth file into `~/.codex/auth.json`.
4. Run `chmod 600 ~/.codex/auth.json`.

**Caveat**: If the ChatGPT subscription is expired, auth will copy successfully but `codex exec` will fail with model errors. Check `chatgpt_subscription_active_until` in the JWT token.

### Option B: Third-party API relay (common in China)
Many users in China use third-party API relay services instead of direct OpenAI access. If the user provides a relay endpoint and API key, configure:

**`~/.codex/config.toml`**:
```toml
model_provider = "OpenAI"
model = "<model-from-relay>"
review_model = "<model-from-relay>"
model_reasoning_effort = "high"
disable_response_storage = true
network_access = "enabled"
windows_wsl_setup_acknowledged = true
model_context_window = 1000000
model_auto_compact_token_limit = 900000

[model_providers.OpenAI]
name = "OpenAI"
base_url = "<relay-base-url>"
wire_api = "responses"
supports_websockets = true
requires_openai_auth = true

[features]
responses_websockets_v2 = true
```

**`~/.codex/auth.json`**:
```json
{
  "OPENAI_API_KEY": "<relay-api-key>"
}
```

**Known gotcha**: Codex 0.57.0 does not accept `model_reasoning_effort = "xhigh"`. Valid values are: `minimal`, `low`, `medium`, `high`. If the relay template says `xhigh`, change it to `high`.

### Option C: Direct OpenAI API key
If the user has a platform.openai.com API key:

**`~/.codex/auth.json`**:
```json
{
  "OPENAI_API_KEY": "sk-..."
}
```

No `config.toml` changes needed for the base URL in this case.

## Proxy and NAT repair

First determine whether the user is using a Windows-side local proxy at all. Do not assume every machine needs proxy handling.

**Quick connectivity test** (run this early to decide if proxy is needed):
```bash
curl -s --max-time 10 -o /dev/null -w '%{http_code}' https://chatgpt.com/
curl -s --max-time 10 -o /dev/null -w '%{http_code}' https://github.com/
```
If both return 200 or 3xx, proxy may not be needed. If `chatgpt.com` returns 000 (timeout/reset), proxy is almost certainly needed (common in China).

### Proxy detection rules
- Start by asking or inferring three things: whether proxy is enabled, which proxy app is in use, and which local port the user expects.
- If those cannot be confirmed with high confidence from the machine state, stop and ask the user before writing proxy configuration.
- Treat app-specific defaults only as candidates, not facts. Common local proxy ports include `7890`, `1080`, `10808`, `10809`, and `20170`, but users often customize them.
- Inspect whether the Windows proxy listens only on `127.0.0.1`.
- If it does, **ask the user to enable LAN access** or equivalent so the proxy listens on a non-loopback address. This is a human action.
- Prefer the WSL gateway IP from `ip route` inside Linux over `/etc/resolv.conf` nameserver.
- Test the candidate proxy address from WSL before persisting it.

Use the bundled helper script for the Windows-side inspection:
```powershell
pwsh -File scripts/find-wsl-proxy.ps1
```

If the user already told you the port, pass it explicitly:
```powershell
pwsh -File scripts/find-wsl-proxy.ps1 -Ports 7890
```

### Bash variable escaping in WSL commands
When running WSL commands from Windows (via `wsl -d Ubuntu -- bash -c "..."`), bash variable `$` signs get consumed by the calling shell. Two reliable workarounds:
1. **Write a .sh script to a temp file** and run `wsl -d Ubuntu -- bash /mnt/c/Users/<user>/AppData/Local/Temp/script.sh`
2. **Use a PowerShell wrapper**: write a .ps1 file containing `wsl.exe -d Ubuntu -- bash /path/to/script.sh` and execute it via `powershell.exe -ExecutionPolicy Bypass -File script.ps1`

The PowerShell wrapper approach is the most reliable for avoiding escaping issues.

### Persist proxy env
Only after the proxy port is confirmed:
```bash
cat > "$HOME/.wsl-proxy-env" <<'EOF'
host_ip="$(ip route 2>/dev/null | awk '/^default/ { print $3; exit }')"
proxy_port="<confirmed-port>"
if [ -n "$host_ip" ]; then
    export http_proxy="http://$host_ip:$proxy_port"
    export https_proxy="http://$host_ip:$proxy_port"
    export HTTP_PROXY="$http_proxy"
    export HTTPS_PROXY="$https_proxy"
    export ALL_PROXY="$http_proxy"
fi
EOF
```

Then source that file from both `~/.profile` and `~/.bashrc`:
```bash
echo '[ -f "$HOME/.wsl-proxy-env" ] && source "$HOME/.wsl-proxy-env"' >> ~/.bashrc
echo '[ -f "$HOME/.wsl-proxy-env" ] && source "$HOME/.wsl-proxy-env"' >> ~/.profile
```

Ignore the generic WSL warning about localhost proxy mirroring if:
- the distro has a working non-localhost proxy configuration, and
- `codex exec` and `ds doctor` both pass.

## Validation

Run validation in this order:

1. Verify shell path and binaries:
```bash
whoami
command -v node npm git ds codex uv
```

2. Verify Codex can actually execute:
```bash
cd /tmp
codex exec --skip-git-repo-check "Print exactly OK and exit."
```

3. Verify DeepScientist:
```bash
ds doctor
```

4. Set git user info if `ds doctor` warns about it:
```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

5. Start DeepScientist:
```bash
ds
```

6. Confirm Windows can reach the UI:
```text
http://127.0.0.1:20999
```

**Important**: When starting `ds` from an agent, the process must outlive the agent's shell. Either:
- Start it in a separate WSL terminal window: `Start-Process wsl.exe -ArgumentList '-d','Ubuntu','--','bash','-lc','ds'`
- Or create a .bat shortcut on the Desktop for the user to double-click.

## Troubleshooting

### WSL won't start
- **HCS_E_CONNECTION_TIMEOUT**: Reboot required. Check pending reboot registry and uptime.
- **LxssManager stopped and won't start**: Reboot required. Service may be blocked by pending OS updates.
- If `wsl` shows a target distro as version `1`, do not install into it until WSL2 is available or a new WSL2 distro is created.

### Binaries resolve to Windows paths
- If `command -v ds` or `command -v codex` resolves under `/mnt/c`, fix PATH and disable Windows PATH injection before continuing.
- After editing `/etc/wsl.conf`, you must `wsl --terminate <distro>` for changes to take effect.

### Codex model errors
- `model is not supported when using Codex with a ChatGPT account`: ChatGPT subscription expired or model not available on the plan. Switch to API relay.
- `unknown variant xhigh`: Codex 0.57.0 only supports `minimal`, `low`, `medium`, `high`. Change to `high`.
- `Reconnecting... 5/5` then failure: usually a network issue. Check proxy first, then auth.

### Proxy issues
- If you cannot reliably determine whether proxy is enabled or which port is correct, ask the user directly before editing shell proxy config.
- If `codex exec` fails with TLS resets or websocket resets, suspect proxy reachability before suspecting auth.
- If the copied auth file exists but `ds doctor` still says Codex startup probe failed, re-test network reachability to `chatgpt.com` and the proxy endpoint.

### Python package issues
- `python3.10-venv` does not exist on Ubuntu 24.04. Use `python3-venv` instead. Always check `lsb_release -r` first.
- The first `ds doctor` run may take 10+ minutes as it downloads and installs the Python runtime via `uv`.

### Other
- If `ds` says `Codex is not marked ready yet. Running startup probe..`, treat that as a normal transitional state until proven otherwise.
- If shell startup files were edited from Windows and start throwing syntax errors, normalize them back to LF line endings before debugging anything else.

## Desktop shortcut

Create a .bat file on the Desktop for the user to launch DS easily:
```bat
@echo off
start wsl.exe -d Ubuntu -- bash -lc "ds; exec bash"
timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:20999"
```

## References
- Read [references/deepscientist-windows-wsl-notes.md](references/deepscientist-windows-wsl-notes.md) for the concrete repair commands, common failure patterns, and the proxy/auth decision tree.
