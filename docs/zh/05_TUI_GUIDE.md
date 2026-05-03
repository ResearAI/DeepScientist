# 05 TUI 端到端指南：如何在终端里跑通整个流程

这份文档面向一个很具体的目标：

- 你从 `ds --tui` 进入终端界面
- 你知道现在自己在什么模式里
- 你能创建或切换 quest
- 你能在 TUI 里把 QQ、微信、Lingzhu 这样的 connector 配好
- 你能把 connector 真正绑定到当前 quest
- 你能继续在 TUI、Web、QQ、微信之间切换，而不会把上下文弄乱

如果你想看更底层的运行时和 Canvas 机制，再继续看 [06 Runtime 与 Canvas](./06_RUNTIME_AND_CANVAS.md)。

## 1. 先记住 TUI 的三个面

当前 TUI 不是“一个纯聊天框”，而是三个工作面来回切换：

1. `home / request mode`
   你还没有把当前终端会话绑定到某个 quest。
   这个模式下可以预览 quest、创建 quest、打开配置，但普通文本不会自动发给任何 quest。
2. `quest mode`
   你已经绑定到一个 quest。
   这个模式下直接输入普通文本，就是给当前 quest 发用户消息。
3. `config mode`
   你在看本地配置、quest 配置、或者 connector 配置。
   这个模式主要靠 `↑/↓`、`Enter`、`Esc` 操作。

你可以把它理解成：

- `home` 负责“选项目”
- `quest` 负责“推进项目”
- `config` 负责“接入外部协作面和编辑配置”

## 2. 安装与启动

在当前仓库根目录：

```bash
uv sync
npm install
```

最常用的启动方式：

```bash
ds --tui
```

也常用：

```bash
ds
ds --both
ds --status
ds --stop
```

含义：

- `ds`：启动 daemon，打印本地 Web 地址，尝试打开浏览器，然后退出。
  如果你是用 `ds --auth true` 启动，DeepScientist 也会同时打印这次启动生成的本地浏览器密码。
- `ds --tui`：启动 daemon，并进入终端工作区。
- `ds --both`：同时开 Web 和 TUI。
- `ds --status`：查看 daemon 状态。
- `ds --stop`：停止 daemon 本身，不只是停止某个 quest。

排查 TUI 渲染或路由问题时，可以临时打开 debug 模式：

```bash
ds --tui --debug
ds --tui --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

也可以用环境变量启动：

```bash
DEEPSCIENTIST_TUI_DEBUG=1 DEEPSCIENTIST_TUI_DEBUG_LOG=/tmp/deepscientist_tui_debug.jsonl ds --tui
```

debug 模式只用于排障，不建议长期打开。

## 3. 进入 TUI 后，第一眼应该怎么看

如果你是第一次进来，欢迎区最重要的信息有三类：

- 当前是 `request mode` 还是 `quest mode`
- 当前本地 Web 地址
- 当前有哪些 quest 可以切换

如果本地浏览器密码模式是开启的，那么终端里打印出来的 Web 地址就是你应该优先使用的地址。

- 第一次优先打开终端里打印的完整 URL
- 当 TUI 已经拿到本地密码 token 时，`Ctrl+O` 重新打开 Web 也会带上同一个 token

如果欢迎区显示的是 `request mode`，说明你还没有绑定 quest。

这时正确动作不是直接输入普通文本，而是先做下面两件事之一：

- 创建一个新 quest：`/new <goal>`
- 绑定一个已有 quest：`/use <quest_id>`

例如：

```text
/new 复现当前项目的 baseline，并整理一个可比较的实验计划
```

或者：

```text
/use 001
```

## 4. 最短可跑通路径：从 0 到第一个 quest

这是我建议的第一条完整路径。

### Step 1. 启动 TUI

```bash
ds --tui
```

### Step 2. 创建 quest

在输入框输入：

```text
/new 用当前仓库跑一次 baseline，并给出后续实验计划
```

成功后，TUI 会自动切进这个新 quest。

### Step 3. 等首轮执行开始

`/new <goal>` 不只是建目录，还会自动启动首轮运行。

这时你会看到：

- quest 已经被绑定
- 历史区开始出现消息、artifact 或操作记录
- 对于长时间运行的 quest，TUI 会先恢复最近一段历史，保证重新打开时依然流畅，然后再从最新 cursor 继续接收新事件
- 状态栏显示当前 quest id

### Step 4. 再发一条普通消息

例如：

```text
先别发散，先把当前 baseline 跑通，然后告诉我缺什么配置。
```

这条消息会发给当前绑定的 quest。

### Step 5. 用 `/status` 和 `/graph` 看状态

常用两条命令：

```text
/status
/graph
```

- `/status`：看 quest 当前状态
- `/graph`：看 quest 图和研究过程

### Step 6. 随时打开 Web

在 TUI 里按：

- `Ctrl+O`：打开当前 quest 对应的 Web 工作区

这很重要，因为 TUI 和 Web 看的是同一个 daemon、同一个 quest、同一套事件流。

## 5. TUI 里最常用的命令和按键

### 命令

- `/home`：回到未绑定 quest 的 request mode
- `/projects`：打开 quest 浏览面板
- `/use <quest_id>`：绑定到指定 quest
- `/new <goal>`：创建新 quest
- `/delete <quest_id> --yes`：删除 quest
- `/pause`：暂停当前 quest；未绑定时会先进入选择面板
- `/resume`：恢复当前 quest；未绑定时会先进入选择面板
- `/stop`：停止当前 quest；未绑定时会先进入选择面板
- `/stop <quest_id>`：显式停止指定 quest
- `/status`：看当前 quest 状态
- `/graph`：看当前 quest 图
- `/config`：进入配置面
- `/config connectors`：直接进 connector 列表
- `/config qq`：直接进 QQ 配置
- `/config weixin`：直接进微信配置
- `/config lingzhu`：直接进 Lingzhu 配置
- `/debug`：打开当前 TUI debug inspector

### 按键

- `Enter`：发送输入或确认选择
- `↑/↓`：切换选择项
- `Tab`：在列表中向下切换
- `Esc`：返回上一层或关闭当前面板
- `Ctrl+R`：强制刷新
- `Ctrl+O`：打开 Web 工作区
- `Ctrl+G`：从任意位置直接打开配置首页
- `Ctrl+D`：从任意位置打开 debug inspector；在 config editor 里也是非破坏式 overlay
- `Ctrl+B`：离开当前 quest；如果你在配置页，则先关闭配置页
- `Ctrl+C`：退出 TUI
- `Shift+↑/↓`：滚动历史区
- `PageUp/PageDown`：整页滚动历史区

## 6. 正确的日常节奏

如果你准备把 TUI 当主工作面，推荐始终按这个顺序：

1. 先确认自己是否已经绑定 quest
2. 再发消息
3. 需要切 quest 时用 `/projects` 或 `/use`
4. 需要配 connector 时先确认“当前 quest”是谁，再进 `/config`

原因很简单：

- connector 绑定动作是“绑定到当前 quest”
- 如果你先进了 `/config qq`，但当前没有 active quest，那么 TUI 只能保存 connector 配置，不能替你完成 quest 绑定

所以推荐顺序是：

1. `/new <goal>` 或 `/use <quest_id>`
2. 确认已经进入 quest mode
3. `/config qq` 或 `/config weixin` 或 `/config lingzhu`

## 7. 在 TUI 里配置 connector 的推荐顺序

当前 TUI 对 connector 的最佳实践顺序是：

1. 先创建或切到你要继续推进的 quest
2. 再进入 connector 配置页
3. 先看顶部 guide
4. 按 guide 的顺序完成平台侧操作
5. 回到 TUI 执行保存、刷新或绑定动作

### 为什么现在顶部 guide 很关键

connector 详情页顶部现在不是装饰性文案，而是“下一步怎么做”的实际操作提示。

- `QQ`：顶部会告诉你应该先填凭据、再发第一条私聊、再等待 OpenID / conversation_id 自动出现
- `Weixin`：顶部会告诉你应该先创建二维码，再用微信扫码确认
- `Lingzhu`：顶部会告诉你应该先设置公网 `public_base_url`，然后把哪些值填到 Rokid 平台

## 8. QQ：在 TUI 里跑通完整链路

这是当前最容易误操作的一条，所以单独展开。

### 推荐路径

1. 先进入目标 quest
2. 输入 `/config qq`
3. 先看顶部 guide
4. 填 `Bot name`、`App ID`、`App Secret`
5. 执行 `Save Connector`
6. 从你自己的 QQ 给 bot 发第一条私聊
7. 回到 TUI，等待自动刷新，或按 `Ctrl+R`
8. 确认 `Detected OpenID` 与 `Last conversation` 不再为空
9. 在下面出现的 target action 里，把当前 quest 绑定到正确的 QQ target

### 你在 QQ 页面会看到什么

顶部通常会给出两类信息：

- `Top Guide`
  这告诉你现在应该先做哪一步
- `Current Status`
  这告诉你当前卡在哪一步

重点字段：

- `Detected OpenID`
  这是系统自动学到的，不是第一次就该手填的字段
- `Last conversation`
  这是运行时最后一次看到的会话 id
- `Discovered targets`
  这是 TUI 已经从运行时学到、可以拿来绑定 quest 的目标
- `Profile · ...`
  如果 QQ 配了多个 profile，TUI 现在会直接显示每个 profile 的运行时摘要，你可以在终端里看到它的 OpenID、偏好 target、当前绑定 quest 和就绪状态，不必先切回 Web。

### 正确理解 QQ 绑定

在当前 TUI 里，QQ 有两层事：

1. 保存 QQ bot 自身凭据
2. 把某个 runtime target 绑定到当前 quest

只有第 1 层完成，还不算真正“跑通”。

真正跑通的标志是：

- `Detected OpenID` 已出现
- target action 已出现
- 你把当前 quest 绑定到了正确 target

### 当前 TUI 里的限制

- 如果你有多个 QQ profile，TUI 详情页仍会提示：profile 的新增、删除、凭据替换属于原始配置编辑任务
- 多 profile 的新增、删除、复杂编辑，仍建议回到原始 `connectors.yaml` 或 Web 设置页
- 但 profile 摘要和 runtime target 绑定动作现在会直接完整展示在 TUI 里

## 9. 微信：在 TUI 里跑通完整链路

### 推荐路径

1. 先进入目标 quest
2. 输入 `/config weixin`
3. 执行 `Bind Weixin` 或 `Rebind Weixin`
4. TUI 会进入二维码页
5. 用目标微信账号所在手机扫码
6. 在微信里确认登录
7. 成功后 TUI 自动回到详情页
8. 确认 `Bot account`、`Owner account`、`Known targets` 已刷新

### 当前行为要点

- 微信绑定不需要你手动填 bot token
- 二维码是 DeepScientist 在 TUI 内直接生成的
- 扫码确认成功后，connector 配置会自动保存

### 什么时候算跑通

至少满足：

- 详情页不再是“未绑定”
- `Bot account` 不为空
- `Owner account` 不为空

如果你还要继续用它推进 quest，后续再让 quest 绑定到微信会话即可。

## 10. Lingzhu / Rokid：在 TUI 里跑通完整链路

Lingzhu 的关键不是“点一个按钮立即完成”，而是“TUI 生成平台字段，你拿去填 Rokid 平台”。

### 推荐路径

1. 先进入目标 quest
2. 输入 `/config lingzhu`
3. 先把 `Public base URL` 改成最终公网地址
4. 如果需要，生成新的 `Custom agent AK`
5. 看详情页里自动生成的 Rokid 字段
6. 把里面的值填到 Rokid 平台
7. 回到 TUI 执行 `Save Connector`

### 你需要特别注意的点

- `public_base_url` 必须是最终可访问的公网 `http(s)` 地址
- `127.0.0.1`、`localhost`、内网地址不能作为真实 Rokid 绑定地址
- 详情页现在会展示和 Web 弹框一致的 Rokid 侧字段：
  - `Custom agent ID`
  - `Custom agent URL`
  - `Custom agent AK`
  - `Agent name`
  - `Category`
  - `Capability summary`
  - `Opening message`
  - `Input type`
- 如果终端一屏放不下，使用 `PgUp` / `PgDn` 往下翻

### 什么时候算跑通

至少满足：

- `Public base URL` 已改成公网地址
- `Custom agent AK` 已生成或已填入
- 你已经把顶部列出的字段复制进 Rokid 平台
- 当前 connector 已保存

## 11. 一条完整推荐剧本

如果你要在一台服务器上用 TUI 跑通“建 quest + 配 connector + 继续推进”，我建议直接照下面这条顺序：

### 剧本 A：QQ

1. `ds --tui`
2. `/new <goal>`
3. 等 quest 自动启动
4. `/config qq`
5. 填 `Bot name / App ID / App Secret`
6. `Save Connector`
7. 去 QQ 给 bot 发一条私聊
8. 回 TUI，确认 `Detected OpenID` 和 target 出现
9. 执行 `Bind ...` 动作，把当前 quest 绑定到该 QQ target
10. 再去 QQ 继续发消息，或回 TUI / Web 继续推进

### 剧本 B：微信

1. `ds --tui`
2. `/new <goal>` 或 `/use <quest_id>`
3. `/config weixin`
4. `Bind Weixin`
5. 手机扫码并确认
6. 等 TUI 自动回详情页
7. 确认绑定信息已刷新
8. 继续在 quest 内推进

### 剧本 C：Lingzhu

1. `ds --tui`
2. `/new <goal>` 或 `/use <quest_id>`
3. `/config lingzhu`
4. 改 `Public base URL`
5. 生成或填写 `Custom agent AK`
6. 把顶部列出的值复制到 Rokid 平台
7. `Save Connector`
8. 再做设备侧联通验证

## 12. TUI、Web、Connector 是同一个 quest

这件事非常重要。

你在 TUI 里做的这些事：

- `/new`
- `/use`
- 普通消息
- `/pause`、`/resume`、`/stop`
- connector 绑定

都会进入同一个 daemon 和同一个 quest 持久状态。

所以：

- 在 TUI 里建的 quest，Web 能立刻看到
- 在 TUI 里绑定的 connector，Web 能立刻看到
- 在 QQ / 微信里继续对话，TUI 和 Web 最终也会回到同一个 quest 上

TUI 不是“另起一套状态”，只是另一种操作面。

## 13. 邮箱语义：为什么运行中发的消息不一定立刻被 agent 看见

TUI、Web、connector 共用同一套 mailbox 语义。

核心规则：

1. quest 空闲时，第一条普通用户消息直接启动一轮
2. quest 正在运行时，后续用户消息先进入队列
3. 只有 agent 调用 `artifact.interact(...)` 时，这些排队消息才会被真正投递

持久化文件在 quest 内：

- `.ds/runtime_state.json`
- `.ds/user_message_queue.json`
- `.ds/interaction_journal.jsonl`
- `.ds/events.jsonl`

这意味着：

- 你追加的一句补充，不一定在 1 秒内就被 agent 看见
- 但它没有丢，只是进入邮箱，等待下一次交互点被投递

## 14. Pause / Resume / Stop 怎么理解

- `/pause`：中断当前 runner，把 quest 置为 `paused`
- `/resume`：把 `paused` 或 `stopped` 的 quest 拉回 `active`
- `/stop`：更强的中断，把 quest 置为 `stopped`

`/stop` 比 `/pause` 更强，因为：

- 未投递的邮箱消息会被取消
- 旧消息不会在下一轮被静默重放
- 但 Git 分支、工作树、已经写过的文件都保留

所以如果你只是“先停一下”，优先用 `/pause`。
如果你要明确切断当前一轮，优先用 `/stop`。

## 15. TUI debug 模式

TUI debug 模式用来回答三个问题：

1. 当前屏幕到底是什么 surface
2. 按 Enter 后会走本地命令、后端命令、quest chat，还是被本地拦截
3. 这个 TUI surface 在 Web 里最接近哪个页面

打开方式：

```bash
ds --tui --debug
```

指定日志路径：

```bash
ds --tui --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

如果你是直接运行 TUI bundle，也可以使用：

```bash
node src/tui/dist/index.js --base-url http://127.0.0.1:20999 --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

### 屏幕上会看到什么

debug 模式会在输入区上方显示一条小型诊断条：

- `surface`：当前 TUI surface，例如 `home`、`quest:<id>`、`config:root:browse`、`config:files:edit`
- `web`：最接近的 Web 页面，例如 `Web Settings`、`Web quest workspace`
- `route`：当前输入会走的路由类型
- `target`：目标 endpoint、utility panel 或本地动作
- `parse / preview`：当前输入的解析结果

在任何页面按 `Ctrl+D` 可以打开 `TUI Debug` 面板。这个面板会显示：

- `Submitted Route`：触发 debug 前，当前输入按 Enter 会提交到哪里
- `Input`：当前输入摘要
- `Screen`：当前主屏、composer、选中项和 redaction 状态
- `Render`：quest/config/utility 数量和选中索引
- `Capture`：status line、session id、日志路径和快照签名

### JSONL 日志

debug 模式会把快照写成 JSONL。默认路径是：

```text
/tmp/deepscientist_tui_debug.jsonl
```

每一行都是一个快照。典型字段：

- `surface`
- `web_analog`
- `route`
- `input`
- `screen`
- `counts`
- `status_line`

config editor 和 connector secret 字段会被脱敏。例如：

```json
{
  "surface": "config:files:edit",
  "route": {
    "kind": "config-save",
    "arg": "[redacted: config editor buffer; 53 chars]"
  },
  "input": {
    "raw": "[redacted: config editor buffer; 53 chars]",
    "redacted": true,
    "redaction_reason": "config editor buffer"
  },
  "screen": {
    "main": "Config editor: config.yaml",
    "input_redacted": true
  }
}
```

注意：debug JSONL 会脱敏 config buffer；但如果你用 `script`、tmux 日志或终端录屏捕获真实 TUI 屏幕，config editor 本身仍会显示文件内容。这是编辑器的正常行为，不要把包含真实 token 的终端 transcript 发到公共 issue。

### 什么时候应该打开 debug

适合打开 debug 的情况：

- `/config`、`/benchstore`、`/tasks` 等命令看起来没有进入预期页面
- 输入了 slash command，但不确定它是本地处理、后端转发，还是被 TUI 拦截
- config editor 里按 Enter 后不知道会保存哪个 draft
- TUI 和 Web 看起来不一致，需要比较 `web_analog`
- 写 issue 或回归测试时，需要可复现的 route/screen 快照

不建议打开 debug 的情况：

- 日常聊天或运行 quest
- 正在编辑大量真实密钥，并且你还会额外录制完整终端输出
- 只是想调 daemon 日志级别；这种情况应该改 `logging.level`

### 和 Web debug 的关系

Web 端也有一个轻量 debug inspector，目前先覆盖 Settings surface。可以用 query flag 打开：

```text
/settings/connector/qq?debug=1
```

也可以在浏览器 console 里持久打开：

```js
localStorage.setItem('deepscientist.debug', '1')
```

如果要为当前页面会话保留浏览器内 JSONL buffer：

```js
localStorage.setItem('deepscientist.debug.log', '1')
```

删除这个 localStorage key，或使用 `?debug=0` 可以关闭。

Web inspector 会出现在右下角。它会显示当前 Settings surface、route、选中的 section/connector、dirty/loading/saving/testing 状态、config/connector/quest 数量、action disabled reason、最近 API 请求状态，以及脱敏后的 JSON snapshot。提交 issue 或回归证据时，可以使用 `Copy JSON` 或 `Download JSONL`。当 `deepscientist.debug.log` 打开时，`Download JSONL` 会导出浏览器内累计 snapshot 日志；否则只导出当前 snapshot。

如果要做严格的 Web/TUI 对照，建议：

1. 在 TUI 用 `--debug-log` 记录 JSONL
2. 在 Web 打开对应页面并加 `?debug=1`，例如 `/settings/connector/qq?debug=1`
3. 对比 TUI 的 `surface`、`web_analog`、`route.target` 与 Web 的 `surface`、`route`、`selected`、`flags`、`actions`
4. 确认两边 snapshot 都没有真实 token、secret、password、API key、credential、auth AK 或 app secret

当前范围：第一版 Web debug 先覆盖 Settings，尤其是 connector/config 页面。quest workspace 和 BenchStore snapshot 是后续扩展项。

## 16. 排错

### 问题 1：我进了 TUI，但输入普通文本没反应

先检查：

- 你是不是还在 `request mode`
- 你有没有先 `/use <quest_id>` 或 `/new <goal>`

如果没有绑定 quest，普通文本不会自动发出去。

### 问题 2：QQ 的 `Detected OpenID` 一直为空

按顺序排查：

1. 你有没有先保存 `App ID / App Secret`
2. 你有没有真的从 QQ 发过第一条私聊
3. 你有没有等一次自动刷新，或者按 `Ctrl+R`

### 问题 3：我在 `/config qq` 里能看到 target，但没有绑定动作

通常是因为：

- 你当前没有 active quest

先：

```text
/use <quest_id>
```

再回到：

```text
/config qq
```

### 问题 4：微信二维码扫了，但页面没回去

先看：

- 手机里是否真的确认了登录
- 当前 daemon 是否还在线

如果不确定，按 `Ctrl+R` 强制刷新一次。

### 问题 5：Lingzhu 已经填了，但设备还是不通

先确认：

- `Public base URL` 是公网可达地址
- 不是 `localhost` / `127.0.0.1` / 内网地址
- Rokid 平台里填的是顶部 guide 给出的值，而不是本地地址

### 问题 6：TUI 看起来没有执行我输入的命令

打开 debug：

```bash
ds --tui --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

然后复现一次输入，重点看：

- `route.kind` 是不是 `blocked`
- `route.target` 是不是你预期的 endpoint 或 panel
- `surface` 有没有跳到预期页面
- `web_analog` 是否指向你预期的 Web 页面

如果在 config editor 里排查，按 `Ctrl+D` 打开 debug inspector；不要输入 `/debug`，因为普通文本会进入 editor buffer。

## 17. 最后给一个简单判断标准

如果你想判断自己是否真的“会用 TUI 跑通流程”，看下面四条是否都能做到：

1. 你能从 `request mode` 创建或绑定 quest
2. 你能在 `quest mode` 给当前 quest 发消息并看状态
3. 你能在 `/config` 里把至少一个 connector 配好
4. 你知道 connector 配好不等于 quest 已绑定，并且你知道在哪里做 quest 绑定

如果这四条都能做到，TUI 的主流程你就已经跑通了。
