# DeepScientist Quick Start Guide (Improved)

## Target Audience

This guide is for first-time DeepScientist users who need to configure and launch quickly.

## Core Workflow (5 Steps)

1. **Install DeepScientist**
2. **Configure Runner (Codex / Claude Code / OpenCode)**
3. **Configure DeepXiv (Optional but Recommended)**
4. **Configure Connector (Optional)**
5. **Launch and Create Your First Project**

---

## Step 1: Install DeepScientist

### 1.1 Prerequisites

- Node.js >= 18.18
- npm >= 9
- Python >= 3.11 (auto-managed)

### 1.2 Installation

```bash
# Global install
npm install -g @researai/deepscientist

# Verify installation
ds --version
```

### 1.3 Optional: Install LaTeX Runtime

For local paper PDF compilation:

```bash
ds latex install-runtime
```

---

## Step 2: Configure Runner

DeepScientist supports three runners. Choose one:

### Option A: Codex (Recommended, Most Stable)

**Use Case**: OpenAI, MiniMax, GLM, Volcengine Ark, Alibaba Bailian, etc.

**Setup Steps**:

```bash
# 1. Install Codex (if not already installed)
npm install -g @openai/codex

# 2. Login (OpenAI users)
codex login

# Or configure Provider Profile (MiniMax/GLM/etc.)
codex --profile m27

# 3. Verify
ds doctor --runner codex
```

**Detailed Documentation**: [15_CODEX_PROVIDER_SETUP.md](./15_CODEX_PROVIDER_SETUP.md)

---

### Option B: Claude Code (Experimental Support)

**Use Case**: Anthropic Claude API

**Setup Steps**:

```bash
# 1. Ensure claude command is available
claude --version

# 2. Configure API Key (if not already done)
# Method 1: Environment variable
export ANTHROPIC_API_KEY="your-api-key"

# Method 2: Claude config file
# Edit ~/.config/claude/config.json or run: claude login

# 3. Test claude command
claude -p --output-format json --tools "" "Reply with exactly HELLO."

# 4. Verify DeepScientist integration
ds doctor --runner claude
```

**Claude Code Configuration Mapping**:

DeepScientist automatically maps these configurations:

| DeepScientist Config | Claude Code Parameter |
|---|---|
| `model` | `--model` |
| `temperature` | `--temperature` |
| `max_tokens` | `--max-tokens` |
| `thinking_budget` | `--thinking-budget` |

**Recommended Models**:
- `claude-opus-4` - Most capable
- `claude-sonnet-4` - Balanced performance
- `claude-haiku-4` - Fast response

**Detailed Documentation**: [24_CLAUDE_CODE_PROVIDER_SETUP.md](./24_CLAUDE_CODE_PROVIDER_SETUP.md)

---

### Option C: OpenCode (Experimental Support)

**Use Case**: DeepSeek, Qwen, and other open-source models

**Setup Steps**:

```bash
# 1. Ensure opencode command is available
opencode --version

# 2. Configure API (if not already done)
# Edit ~/.opencode/config.yaml
# Or use environment variables:
export OPENCODE_API_KEY="your-api-key"
export OPENCODE_BASE_URL="https://api.deepseek.com"

# 3. Test opencode command
opencode run --format json --pure "Reply with exactly HELLO"

# 4. Verify DeepScientist integration
ds doctor --runner opencode
```

**OpenCode Configuration Mapping**:

DeepScientist automatically maps these configurations:

| DeepScientist Config | OpenCode Parameter |
|---|---|
| `model` | `--model` |
| `temperature` | `--temperature` |
| `max_tokens` | `--max-tokens` |

**Recommended Models**:
- `deepseek-chat` - DeepSeek flagship model
- `qwen-max` - Qwen most capable version

**Detailed Documentation**: [25_OPENCODE_PROVIDER_SETUP.md](./25_OPENCODE_PROVIDER_SETUP.md)

---

## Step 3: Configure DeepXiv (Recommended)

DeepXiv is DeepScientist's literature retrieval enhancement service that significantly improves research quality.

### 3.1 Why DeepXiv?

- Automatically retrieve relevant papers
- Provide paper summaries and key information
- Help AI understand research background
- Avoid duplicating existing work

### 3.2 Configuration Steps

**Method 1: Web UI Configuration (Recommended)**

1. Start DeepScientist: `ds`
2. Open browser: `http://localhost:20999`
3. Go to Settings → DeepXiv
4. Fill in configuration:

```yaml
# DeepXiv configuration example
deepxiv:
  enabled: true
  api_key: "your-deepxiv-api-key"  # Get from deepxiv.com
  base_url: "https://api.deepxiv.com/v1"  # Default URL
  max_papers: 10  # Max papers per search
  auto_fetch: true  # Auto-fetch full text
```

5. Click "Test Connection" to verify
6. Save configuration

**Method 2: Configuration File**

Edit `~/DeepScientist/config/config.yaml`:

```yaml
deepxiv:
  enabled: true
  api_key: "your-deepxiv-api-key"
  base_url: "https://api.deepxiv.com/v1"
  max_papers: 10
  auto_fetch: true
```

### 3.3 Get DeepXiv API Key

1. Visit: https://deepxiv.com
2. Register account
3. Go to Dashboard → API Keys
4. Create new API Key
5. Copy and paste into configuration

### 3.4 Verify Configuration

```bash
# Verify with doctor command
ds doctor

# Check if DeepXiv section shows ✓
```

---

## Step 4: Configure Connector (Optional)

Connectors let you receive research progress notifications via WeChat, QQ, etc.

### 4.1 Supported Connectors

- **WeChat (Weixin)** - Recommended, most popular
- **QQ** - For Chinese users
- **Telegram** - For international users
- **Slack** - For team collaboration
- **Discord** - For developer communities

### 4.2 Configure WeChat Connector (Example)

**Step 1: Get WeChat Enterprise Credentials**

1. Visit: https://work.weixin.qq.com
2. Register WeChat Enterprise account
3. Create application, obtain:
   - `corp_id` (Enterprise ID)
   - `agent_id` (Application ID)
   - `secret` (Application Secret)

**Step 2: Configure DeepScientist**

Edit `~/DeepScientist/config/connectors.yaml`:

```yaml
connectors:
  weixin:
    enabled: true
    corp_id: "your-corp-id"
    agent_id: "your-agent-id"
    secret: "your-secret"
    # Optional: specify message recipient
    default_user: "@all"  # or specific user ID
```

**Step 3: Verify Connection**

```bash
ds doctor --connector weixin
```

**Detailed Documentation**: [10_WEIXIN_CONNECTOR_GUIDE.md](./10_WEIXIN_CONNECTOR_GUIDE.md)

### 4.3 Configure QQ Connector (Example)

**Step 1: Get QQ Bot Credentials**

1. Visit: https://q.qq.com/bot
2. Create Bot, obtain:
   - `app_id`
   - `app_secret`
   - `bot_token`

**Step 2: Configure DeepScientist**

Edit `~/DeepScientist/config/connectors.yaml`:

```yaml
connectors:
  qq:
    enabled: true
    app_id: "your-app-id"
    app_secret: "your-app-secret"
    bot_token: "your-bot-token"
```

**Detailed Documentation**: [03_QQ_CONNECTOR_GUIDE.md](./03_QQ_CONNECTOR_GUIDE.md)

---

## Step 5: Launch DeepScientist

### 5.1 Basic Launch

```bash
# Default launch (uses codex)
ds

# Specify runner
ds --runner claude
ds --runner opencode

# Specify port
ds --port 21000

# Listen on all interfaces (for remote access)
ds --host 0.0.0.0 --port 20999
```

### 5.2 Launch Options

| Parameter | Description | Example |
|---|---|---|
| `--runner` | Specify runner | `--runner claude` |
| `--host` | Listen address | `--host 0.0.0.0` |
| `--port` | Listen port | `--port 21000` |
| `--home` | Specify home directory | `--home /data/DS` |
| `--here` | Use current directory | `--here` |
| `--auth` | Enable password protection | `--auth true` |
| `--codex-profile` | Codex profile | `--codex-profile m27` |

### 5.3 Verify Launch

```bash
# Check status
ds --status

# View logs
tail -f ~/DeepScientist/logs/daemon.log

# Test API
curl http://localhost:20999/api/health
```

---

## Step 6: Create Your First Project

### 6.1 Open Web UI

Browser: `http://localhost:20999`

### 6.2 Choose Launch Mode

Click "Start Research", select mode:

- **Copilot Mode**: Human-AI collaboration, you control each step
- **Autonomous Mode**: Autonomous research, AI progresses automatically

**Beginner Recommendation**: Start with Copilot Mode

### 6.3 Fill Project Information

**Required Fields**:

| Field | Description | Example |
|---|---|---|
| Project Title | Project title | "ResNet Reproduction and Improvement" |
| Primary Request | Research goal | "Reproduce ResNet-50 on ImageNet" |

**Recommended Fields**:

| Field | Description | Example |
|---|---|---|
| Baseline Links | Code repository | `https://github.com/xxx/resnet` |
| Reference Papers | Reference papers | `https://arxiv.org/abs/1512.03385` |
| Runtime Constraints | Runtime constraints | "Use single 24GB GPU" |
| Goals | Specific goals | "1. Reproduce baseline<br>2. Improve 1% accuracy" |

**Connector Binding** (if configured):

- Select "Weixin" or "QQ"
- Fill in recipient user ID or group ID

### 6.4 Create and Launch

1. Check preview on the right
2. Click "Create Project"
3. Wait for project initialization
4. Enter workspace

---

## Command Quick Reference

```bash
# Launch
ds                              # Default launch
ds --runner claude              # Use Claude Code
ds --host 0.0.0.0 --port 20999  # Remote access

# Management
ds --status                     # Check status
ds --stop                       # Stop service
ds --restart                    # Restart service

# Diagnostics
ds doctor                       # Full diagnostics
ds doctor --runner claude       # Diagnose specific runner
ds doctor --connector weixin    # Diagnose specific connector

# Maintenance
ds latex install-runtime        # Install LaTeX
ds migrate /new/path            # Migrate data
ds uninstall                    # Uninstall (keep data)
```

---

## Troubleshooting

### Issue 1: Runner Won't Start

**Symptom**: `ds doctor` shows runner failure

**Solution**:

```bash
# Codex
which codex                     # Check if installed
codex login                     # Re-login
npm install -g @openai/codex    # Reinstall

# Claude Code
which claude                    # Check if installed
echo $ANTHROPIC_API_KEY         # Check API Key
claude --version                # Test command

# OpenCode
which opencode                  # Check if installed
echo $OPENCODE_API_KEY          # Check API Key
opencode --version              # Test command
```

### Issue 2: DeepXiv Connection Failed

**Symptom**: DeepXiv shows red in Settings

**Solution**:

1. Check if API Key is correct
2. Check network connection
3. Verify base_url is correct
4. View logs: `tail -f ~/DeepScientist/logs/daemon.log`

### Issue 3: Connector Not Receiving Messages

**Symptom**: Project running but no notifications received

**Solution**:

```bash
# Check connector status
ds doctor --connector weixin

# View connector logs
tail -f ~/DeepScientist/logs/connectors.log

# Verify configuration
cat ~/DeepScientist/config/connectors.yaml
```

### Issue 4: Port Already in Use

**Symptom**: Port already in use error on launch

**Solution**:

```bash
# Check process using port
lsof -i :20999

# Stop old process
ds --stop

# Or use different port
ds --port 21000
```

---

## Next Steps

- **Deep Dive**: [12_GUIDED_WORKFLOW_TOUR.md](./12_GUIDED_WORKFLOW_TOUR.md)
- **Configuration Reference**: [01_SETTINGS_REFERENCE.md](./01_SETTINGS_REFERENCE.md)
- **Architecture Understanding**: [13_CORE_ARCHITECTURE_GUIDE.md](./13_CORE_ARCHITECTURE_GUIDE.md)
- **Connector Guide**: [03_QQ_CONNECTOR_GUIDE.md](./03_QQ_CONNECTOR_GUIDE.md)

---

## Security Reminders

⚠️ **Important**:

1. **Never run as root**
2. **Don't test on production servers first**
3. **Don't expose 0.0.0.0 port to public internet carelessly**
4. **Regularly backup** `~/DeepScientist/quests/` directory
5. **Securely store** API Keys and Connector credentials

Detailed risk notice: [11_LICENSE_AND_RISK.md](./11_LICENSE_AND_RISK.md)
