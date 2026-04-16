# DeepScientist Windows WSL Notes

Use this note only after the main skill triggers.

## Source-of-truth docs
- Official repo: `https://github.com/ResearAI/DeepScientist`
- Official Windows WSL2 guide: `https://github.com/ResearAI/DeepScientist/blob/main/docs/en/22_WINDOWS_WSL2_DEPLOYMENT_GUIDE.md`

Always check those first because install commands and version pins can change.

## Known-good end state
- Dedicated WSL2 Ubuntu distro exists (version 2, state 1 = Stopped is fine when idle).
- Linux-side `node`, `npm`, `git`, `uv`, `codex`, and `ds` are present, all resolving to Linux paths.
- Linux-side `~/.codex/auth.json` is valid (either ChatGPT auth or API relay key).
- Linux-side `~/.codex/config.toml` exists if using an API relay.
- Proxy is either unnecessary or set to the Windows host address reachable from WSL.
- `ds doctor` shows `[ok] Codex CLI` or `[warn] Codex CLI: Codex startup probe completed.`.
- Windows browser opens `http://127.0.0.1:20999`.

## Practical install sequence

### 1. Pre-flight: WSL health
```powershell
wsl -l -v
wsl --status
wsl -d Ubuntu -- echo hello
```
If `echo hello` fails with HCS_E_CONNECTION_TIMEOUT:
- Check `(Get-CimInstance Win32_OperatingSystem).LastBootUpTime`
- Check pending reboot via registry
- **User must reboot the PC before proceeding**

### 2. Create a dedicated distro if needed
Example:
```powershell
wsl --install Ubuntu-22.04 --name DeepScientist --location <windows-install-path> --version 2 --no-launch --web-download
```

### 3. Disable Windows PATH injection
```bash
printf '[interop]\nappendWindowsPath=false\n' | sudo tee /etc/wsl.conf
```
Then `wsl --terminate <distro>` and re-enter. Verify `command -v node` does NOT resolve to `/mnt/c/...`.

### 4. Install baseline packages inside WSL
```bash
sudo apt-get update
# Check Ubuntu version first: lsb_release -r
# Ubuntu 24.04:
sudo apt-get install -y ca-certificates curl gnupg git sudo build-essential python3-venv python3-pip
# Ubuntu 22.04:
sudo apt-get install -y ca-certificates curl gnupg git sudo build-essential python3.10-venv python3-pip
```

### 5. Install Linux Node.js 20
```bash
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
printf 'deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main\n' | sudo tee /etc/apt/sources.list.d/nodesource.list
sudo apt-get update
sudo apt-get install -y nodejs
```

### 6. Configure npm prefix and PATH
```bash
mkdir -p "$HOME/.npm-global" "$HOME/.local/bin"
npm config set prefix "$HOME/.npm-global"
# Add to .bashrc and .profile:
echo 'export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"' >> ~/.bashrc
echo 'export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:$PATH"' >> ~/.profile
```

### 7. Install DeepScientist and companions
```bash
npm install -g @researai/deepscientist
npm install -g @openai/codex@0.57.0
curl -LsSf https://github.com/astral-sh/uv/releases/latest/download/uv-installer.sh | sh
```

### 8. Configure Codex auth

**Direct ChatGPT auth (reuse from Windows)**:
```bash
mkdir -p ~/.codex
[ -f ~/.codex/auth.json ] && cp ~/.codex/auth.json ~/.codex/auth.json.bak.$(date +%Y%m%d-%H%M%S)
cp /mnt/c/Users/<user>/.codex/auth.json ~/.codex/auth.json
chmod 600 ~/.codex/auth.json
```

**API relay** (common for China users):
```bash
# Write ~/.codex/config.toml with relay base_url
# Write ~/.codex/auth.json with relay API key
# IMPORTANT: use model_reasoning_effort = "high", NOT "xhigh" (Codex 0.57.0 rejects xhigh)
```

### 9. Configure proxy (if needed)
Test direct connectivity first:
```bash
curl -s --max-time 10 -o /dev/null -w '%{http_code}' https://chatgpt.com/
```
If 000 (timeout), proxy is needed.

**Agent-side checks**:
```powershell
pwsh -File scripts/find-wsl-proxy.ps1
```

**Human action**: If proxy listens only on 127.0.0.1, user must enable Allow LAN in proxy app.

**WSL-side**:
```bash
host_ip="$(ip route | awk '/^default/ { print $3; exit }')"
curl -s --max-time 8 -x "http://$host_ip:<port>" -o /dev/null -w '%{http_code}' https://github.com/
```

Persist after validation (see SKILL.md for full template).

## Auth decision tree

```
Has valid ChatGPT subscription? ──yes──> Copy auth.json from Windows
         │no
         v
Has OpenAI API key? ──yes──> Write to auth.json
         │no
         v
Has third-party relay? ──yes──> Write config.toml + auth.json
         │no
         v
Ask user to get one of the above
```

## Proxy decision tree

```
Can WSL reach chatgpt.com directly? ──yes──> No proxy needed
         │no
         v
Is a Windows proxy app running? ──no──> Ask user to set up proxy
         │yes
         v
Does it listen on 0.0.0.0? ──yes──> Configure WSL with gateway IP
         │no (127.0.0.1 only)
         v
Ask user to enable Allow LAN, then configure WSL with gateway IP
```

## Common failure patterns

| Symptom | Cause | Fix |
|---------|-------|-----|
| HCS_E_CONNECTION_TIMEOUT | Pending reboot / long uptime | Reboot PC |
| `command -v ds` returns `/mnt/c/...` | Windows PATH injection | Edit wsl.conf, terminate, re-enter |
| `model is not supported` | Expired ChatGPT sub or wrong model | Use API relay or renew sub |
| `unknown variant xhigh` | Codex 0.57.0 limitation | Change to `high` |
| `python3.10-venv not found` | Ubuntu 24.04 uses python3.12 | Use `python3-venv` |
| Proxy test returns 000 | Proxy on 127.0.0.1 only | User enables Allow LAN |
| ds starts then immediately exits | Process killed when shell closes | Use `Start-Process` or .bat shortcut |
| First ds doctor takes 10+ min | uv downloading Python runtime | Normal, wait |

## Bash escaping workaround

When running WSL commands from a Windows-side agent (Claude Code, etc.), `$` variables in `bash -c "..."` get eaten by the outer shell. The reliable pattern:

1. Write a `.sh` script to a Windows temp file
2. Write a `.ps1` wrapper: `wsl.exe -d Ubuntu -- bash /mnt/c/Users/<user>/AppData/Local/Temp/script.sh`
3. Run: `powershell.exe -ExecutionPolicy Bypass -File wrapper.ps1`

This avoids all escaping issues.

## Validation commands
```bash
cd /tmp
codex exec --skip-git-repo-check "Print exactly OK and exit."
ds doctor
```

Successful `ds doctor` should include:
```text
[ok] Codex CLI: Codex startup probe completed.
```
or:
```text
[warn] Codex CLI: Codex startup probe completed.
  warning: Codex CLI 0.57.0 does not support `xhigh`; DeepScientist downgraded reasoning effort to `high` automatically.
```

Both are acceptable.

Then start:
```bash
ds
```

Open from Windows:
```text
http://127.0.0.1:20999
```
