# DeepScientist 快速启动指南（改进版）

## 目标读者

本指南适合第一次使用 DeepScientist 的用户，特别是需要快速配置并启动的场景。

## 核心流程（5步上手）

1. **安装 DeepScientist**
2. **配置 Runner（Codex / Claude Code / OpenCode）**
3. **配置 DeepXiv（可选但推荐）**
4. **配置 Connector（可选）**
5. **启动并创建第一个项目**

---

## 第一步：安装 DeepScientist

### 1.1 前置要求

- Node.js >= 18.18
- npm >= 9
- Python >= 3.11（会自动管理）

### 1.2 安装命令

```bash
# 全局安装
npm install -g @researai/deepscientist

# 验证安装
ds --version
```

### 1.3 可选：安装 LaTeX 运行时

如果需要本地编译论文 PDF：

```bash
ds latex install-runtime
```

---

## 第二步：配置 Runner

DeepScientist 支持三种 Runner，选择其中一种即可：

### 选项 A：Codex（推荐，最稳定）

**适合场景**：使用 OpenAI、MiniMax、GLM、火山方舟、阿里百炼等

**配置步骤**：

```bash
# 1. 安装 Codex（如果还没有）
npm install -g @openai/codex

# 2. 登录（OpenAI 用户）
codex login

# 或者配置 Provider Profile（MiniMax/GLM 等）
codex --profile m27

# 3. 验证
ds doctor --runner codex
```

**详细文档**：[15_CODEX_PROVIDER_SETUP.md](./15_CODEX_PROVIDER_SETUP.md)

---

### 选项 B：Claude Code（实验性支持）

**适合场景**：使用 Anthropic Claude API

**配置步骤**：

```bash
# 1. 确保 claude 命令可用
claude --version

# 2. 配置 API Key（如果还没有）
# 方式1：通过环境变量
export ANTHROPIC_API_KEY="your-api-key"

# 方式2：通过 claude 配置文件
# 编辑 ~/.config/claude/config.json 或运行 claude login

# 3. 测试 claude 命令
claude -p --output-format json --tools "" "Reply with exactly HELLO."

# 4. 验证 DeepScientist 集成
ds doctor --runner claude
```

**Claude Code 特定配置**：

DeepScientist 会自动映射以下配置：

| DeepScientist 配置 | Claude Code 参数 |
|---|---|
| `model` | `--model` |
| `temperature` | `--temperature` |
| `max_tokens` | `--max-tokens` |
| `thinking_budget` | `--thinking-budget` |

**推荐模型**：
- `claude-opus-4` - 最强能力
- `claude-sonnet-4` - 平衡性能
- `claude-haiku-4` - 快速响应

**详细文档**：[24_CLAUDE_CODE_PROVIDER_SETUP.md](./24_CLAUDE_CODE_PROVIDER_SETUP.md)

---

### 选项 C：OpenCode（实验性支持）

**适合场景**：使用 DeepSeek、Qwen 等开源模型

**配置步骤**：

```bash
# 1. 确保 opencode 命令可用
opencode --version

# 2. 配置 API（如果还没有）
# 编辑 ~/.opencode/config.yaml
# 或通过环境变量：
export OPENCODE_API_KEY="your-api-key"
export OPENCODE_BASE_URL="https://api.deepseek.com"

# 3. 测试 opencode 命令
opencode run --format json --pure "Reply with exactly HELLO"

# 4. 验证 DeepScientist 集成
ds doctor --runner opencode
```

**OpenCode 特定配置**：

DeepScientist 会自动映射以下配置：

| DeepScientist 配置 | OpenCode 参数 |
|---|---|
| `model` | `--model` |
| `temperature` | `--temperature` |
| `max_tokens` | `--max-tokens` |

**推荐模型**：
- `deepseek-chat` - DeepSeek 主力模型
- `qwen-max` - 通义千问最强版本

**详细文档**：[25_OPENCODE_PROVIDER_SETUP.md](./25_OPENCODE_PROVIDER_SETUP.md)

---

## 第三步：配置 DeepXiv（推荐）

DeepXiv 是 DeepScientist 的文献检索增强服务，可以显著提升研究质量。

### 3.1 为什么需要 DeepXiv？

- 自动检索相关论文
- 提供论文摘要和关键信息
- 帮助 AI 理解研究背景
- 避免重复已有工作

### 3.2 配置步骤

**方式 1：通过 Web UI 配置（推荐）**

1. 启动 DeepScientist：`ds`
2. 打开浏览器访问：`http://localhost:20999`
3. 进入 Settings → DeepXiv
4. 填写配置：

```yaml
# DeepXiv 配置示例
deepxiv:
  enabled: true
  api_key: "your-deepxiv-api-key"  # 从 deepxiv.com 获取
  base_url: "https://api.deepxiv.com/v1"  # 默认地址
  max_papers: 10  # 每次检索最多返回论文数
  auto_fetch: true  # 自动获取论文全文
```

5. 点击"Test Connection"验证
6. 保存配置

**方式 2：通过配置文件**

编辑 `~/DeepScientist/config/config.yaml`：

```yaml
deepxiv:
  enabled: true
  api_key: "your-deepxiv-api-key"
  base_url: "https://api.deepxiv.com/v1"
  max_papers: 10
  auto_fetch: true
```

### 3.3 获取 DeepXiv API Key

1. 访问：https://deepxiv.com
2. 注册账号
3. 进入 Dashboard → API Keys
4. 创建新的 API Key
5. 复制 Key 并粘贴到配置中

### 3.4 验证配置

```bash
# 通过 doctor 命令验证
ds doctor

# 查看 DeepXiv 部分是否显示 ✓
```

---

## 第四步：配置 Connector（可选）

Connector 让你可以通过微信、QQ 等接收研究进展通知。

### 4.1 支持的 Connector

- **微信（Weixin）** - 推荐，最常用
- **QQ** - 适合国内用户
- **Telegram** - 适合国际用户
- **Slack** - 适合团队协作
- **Discord** - 适合开发者社区

### 4.2 配置微信 Connector（示例）

**步骤 1：获取微信企业号凭证**

1. 访问：https://work.weixin.qq.com
2. 注册企业微信账号
3. 创建应用，获取：
   - `corp_id`（企业ID）
   - `agent_id`（应用ID）
   - `secret`（应用密钥）

**步骤 2：配置 DeepScientist**

编辑 `~/DeepScientist/config/connectors.yaml`：

```yaml
connectors:
  weixin:
    enabled: true
    corp_id: "your-corp-id"
    agent_id: "your-agent-id"
    secret: "your-secret"
    # 可选：指定接收消息的用户
    default_user: "@all"  # 或具体用户ID
```

**步骤 3：验证连接**

```bash
ds doctor --connector weixin
```

**详细文档**：[10_WEIXIN_CONNECTOR_GUIDE.md](./10_WEIXIN_CONNECTOR_GUIDE.md)

### 4.3 配置 QQ Connector（示例）

**步骤 1：获取 QQ Bot 凭证**

1. 访问：https://q.qq.com/bot
2. 创建 Bot，获取：
   - `app_id`
   - `app_secret`
   - `bot_token`

**步骤 2：配置 DeepScientist**

编辑 `~/DeepScientist/config/connectors.yaml`：

```yaml
connectors:
  qq:
    enabled: true
    app_id: "your-app-id"
    app_secret: "your-app-secret"
    bot_token: "your-bot-token"
```

**详细文档**：[03_QQ_CONNECTOR_GUIDE.md](./03_QQ_CONNECTOR_GUIDE.md)

---

## 第五步：启动 DeepScientist

### 5.1 基本启动

```bash
# 默认启动（使用 codex）
ds

# 指定 runner
ds --runner claude
ds --runner opencode

# 指定端口
ds --port 21000

# 监听所有网卡（用于远程访问）
ds --host 0.0.0.0 --port 20999
```

### 5.2 启动选项

| 参数 | 说明 | 示例 |
|---|---|---|
| `--runner` | 指定 runner | `--runner claude` |
| `--host` | 监听地址 | `--host 0.0.0.0` |
| `--port` | 监听端口 | `--port 21000` |
| `--home` | 指定 home 目录 | `--home /data/DS` |
| `--here` | 使用当前目录 | `--here` |
| `--auth` | 启用密码保护 | `--auth true` |
| `--codex-profile` | Codex profile | `--codex-profile m27` |

### 5.3 验证启动

```bash
# 检查状态
ds --status

# 查看日志
tail -f ~/DeepScientist/logs/daemon.log

# 测试 API
curl http://localhost:20999/api/health
```

---

## 第六步：创建第一个项目

### 6.1 打开 Web UI

浏览器访问：`http://localhost:20999`

### 6.2 选择启动模式

点击 "Start Research"，选择模式：

- **Copilot Mode**：人机协作，你控制每一步
- **Autonomous Mode**：自主研究，AI 自动推进

**新手推荐**：先选 Copilot Mode

### 6.3 填写项目信息

**必填字段**：

| 字段 | 说明 | 示例 |
|---|---|---|
| Project Title | 项目标题 | "ResNet 复现与改进" |
| Primary Request | 研究目标 | "复现 ResNet-50 在 ImageNet 上的结果" |

**推荐填写**：

| 字段 | 说明 | 示例 |
|---|---|---|
| Baseline Links | 代码仓库 | `https://github.com/xxx/resnet` |
| Reference Papers | 参考论文 | `https://arxiv.org/abs/1512.03385` |
| Runtime Constraints | 运行约束 | "使用单张 24GB GPU" |
| Goals | 具体目标 | "1. 复现 baseline<br>2. 提升 1% 准确率" |

**Connector 绑定**（如果已配置）：

- 选择 "Weixin" 或 "QQ"
- 填写接收消息的用户ID或群组ID

### 6.4 创建并启动

1. 检查右侧预览
2. 点击 "Create Project"
3. 等待项目初始化
4. 进入工作区

---

## 常用命令速查

```bash
# 启动
ds                              # 默认启动
ds --runner claude              # 使用 Claude Code
ds --host 0.0.0.0 --port 20999  # 远程访问

# 管理
ds --status                     # 查看状态
ds --stop                       # 停止服务
ds --restart                    # 重启服务

# 诊断
ds doctor                       # 全面诊断
ds doctor --runner claude       # 诊断特定 runner
ds doctor --connector weixin    # 诊断特定 connector

# 维护
ds latex install-runtime        # 安装 LaTeX
ds migrate /new/path            # 迁移数据
ds uninstall                    # 卸载（保留数据）
```

---

## 故障排查

### 问题 1：Runner 无法启动

**症状**：`ds doctor` 显示 runner 失败

**解决方案**：

```bash
# Codex
which codex                     # 检查是否安装
codex login                     # 重新登录
npm install -g @openai/codex    # 重新安装

# Claude Code
which claude                    # 检查是否安装
echo $ANTHROPIC_API_KEY         # 检查 API Key
claude --version                # 测试命令

# OpenCode
which opencode                  # 检查是否安装
echo $OPENCODE_API_KEY          # 检查 API Key
opencode --version              # 测试命令
```

### 问题 2：DeepXiv 连接失败

**症状**：Settings 中 DeepXiv 显示红色

**解决方案**：

1. 检查 API Key 是否正确
2. 检查网络连接
3. 验证 base_url 是否正确
4. 查看日志：`tail -f ~/DeepScientist/logs/daemon.log`

### 问题 3：Connector 无法接收消息

**症状**：项目运行但没有收到通知

**解决方案**：

```bash
# 检查 connector 状态
ds doctor --connector weixin

# 查看 connector 日志
tail -f ~/DeepScientist/logs/connectors.log

# 验证配置
cat ~/DeepScientist/config/connectors.yaml
```

### 问题 4：端口被占用

**症状**：启动时提示端口已被使用

**解决方案**：

```bash
# 查看占用端口的进程
lsof -i :20999

# 停止旧进程
ds --stop

# 或使用其他端口
ds --port 21000
```

---

## 下一步

- **深入学习**：[12_GUIDED_WORKFLOW_TOUR.md](./12_GUIDED_WORKFLOW_TOUR.md)
- **配置参考**：[01_SETTINGS_REFERENCE.md](./01_SETTINGS_REFERENCE.md)
- **架构理解**：[13_CORE_ARCHITECTURE_GUIDE.md](./13_CORE_ARCHITECTURE_GUIDE.md)
- **Connector 指南**：[03_QQ_CONNECTOR_GUIDE.md](./03_QQ_CONNECTOR_GUIDE.md)

---

## 安全提醒

⚠️ **重要**：

1. **不要用 root 账号运行**
2. **不要在生产服务器上首次试用**
3. **不要随意暴露 0.0.0.0 端口到公网**
4. **定期备份** `~/DeepScientist/quests/` 目录
5. **妥善保管** API Keys 和 Connector 凭证

详细风险说明：[11_LICENSE_AND_RISK.md](./11_LICENSE_AND_RISK.md)
