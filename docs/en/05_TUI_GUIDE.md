# 05 TUI End-To-End Guide: Run The Full Flow In Terminal

This guide is for one concrete goal:

- start from `ds --tui`
- understand which mode the TUI is in
- create or switch quests correctly
- configure QQ, Weixin, and Lingzhu from the TUI
- bind the right connector target to the current quest
- continue the same quest across TUI, Web, QQ, Weixin, and Rokid without losing context

If you want the lower-level runtime and Canvas details afterward, also read [06 Runtime and Canvas](./06_RUNTIME_AND_CANVAS.md).

## 1. Learn The Three TUI Surfaces First

The current TUI is not just one chat box. It moves between three working surfaces:

1. `home / request mode`
   The current terminal session is not bound to a quest yet.
   You can preview quests, create a new quest, and open config, but plain text does not go to any quest.
2. `quest mode`
   The current terminal session is already bound to one quest.
   Plain text becomes a normal user message for that quest.
3. `config mode`
   You are browsing local config, quest config, or connector config.
   This mode is mainly operated with `↑/↓`, `Enter`, and `Esc`.

In practice:

- `home` is for choosing work
- `quest` is for advancing work
- `config` is for wiring external collaboration surfaces and editing configuration

## 2. Install And Start

From the repository root:

```bash
uv sync
npm install
```

The most common start command:

```bash
ds --tui
```

Also useful:

```bash
ds
ds --both
ds --status
ds --stop
```

Meaning:

- `ds`: start the daemon, print the local Web URL, try to open the browser, then exit.
  If you launch with `ds --auth true`, DeepScientist also prints the generated local browser password for that launch.
- `ds --tui`: start the daemon and enter the terminal workspace.
- `ds --both`: open Web and TUI together.
- `ds --status`: inspect daemon status.
- `ds --stop`: stop the daemon itself, not just one quest.

When you need to debug TUI rendering or routing, temporarily enable debug mode:

```bash
ds --tui --debug
ds --tui --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

You can also use environment variables:

```bash
DEEPSCIENTIST_TUI_DEBUG=1 DEEPSCIENTIST_TUI_DEBUG_LOG=/tmp/deepscientist_tui_debug.jsonl ds --tui
```

Debug mode is for troubleshooting. Do not leave it on for ordinary daily use.

## 3. What To Look At First After Entering TUI

When the TUI opens, the first useful signals are:

- whether you are in `request mode` or `quest mode`
- the local Web URL
- which quests are available to switch to

If local browser auth is enabled, treat that printed Web URL as the source of truth.

- open the exact printed URL first
- `Ctrl+O` reopens the Web workspace with the same local password token when TUI already has it

If the welcome area says `request mode`, the current terminal session is not bound to a quest yet.

The correct next move is not plain text. Do one of these first:

- create a new quest: `/new <goal>`
- bind an existing quest: `/use <quest_id>`

For example:

```text
/new Reproduce the current baseline and turn it into a comparable experiment plan
```

or:

```text
/use 001
```

## 4. Shortest Working Path: From Zero To The First Quest

This is the first path I recommend.

### Step 1. Start TUI

```bash
ds --tui
```

### Step 2. Create a quest

Enter:

```text
/new Run the baseline in this repo once and tell me what configuration is still missing
```

The TUI will automatically switch into that new quest.

### Step 3. Wait for the first run to start

`/new <goal>` does not only create the quest. It also starts the first run.

You should then see:

- the quest is already bound
- the history area starts showing messages, artifacts, or operations
- on long-running quests, TUI restores a recent history window first so reopening stays responsive, then continues streaming new events from the latest cursor
- the status line shows the active quest id

### Step 4. Send one normal message

For example:

```text
Stay narrow. First get the baseline running, then tell me exactly which settings are still missing.
```

That message goes to the currently bound quest.

### Step 5. Check `/status` and `/graph`

Useful commands:

```text
/status
/graph
```

- `/status`: inspect the current quest state
- `/graph`: inspect the quest graph and research progress

### Step 6. Open Web anytime

Inside TUI:

- `Ctrl+O`: open the Web workspace for the current quest

That matters because TUI and Web are looking at the same daemon, the same quest, and the same event stream.

## 5. Most Useful Commands And Keys

### Commands

- `/home`: return to unbound request mode
- `/projects`: open the quest browser
- `/use <quest_id>`: bind to a specific quest
- `/new <goal>`: create a new quest
- `/delete <quest_id> --yes`: delete a quest
- `/pause`: pause the current quest; if no quest is bound, open the selector
- `/resume`: resume the current quest; if no quest is bound, open the selector
- `/stop`: stop the current quest; if no quest is bound, open the selector
- `/stop <quest_id>`: stop a specific quest explicitly
- `/status`: inspect the current quest status
- `/graph`: inspect the current quest graph
- `/config`: open config
- `/config connectors`: open the connector list directly
- `/config qq`: open QQ config directly
- `/config weixin`: open Weixin config directly
- `/config lingzhu`: open Lingzhu config directly
- `/debug`: open the current TUI debug inspector

### Keys

- `Enter`: send input or confirm the current selection
- `↑/↓`: move selection
- `Tab`: move forward in list selection
- `Esc`: go back one layer or close the current panel
- `Ctrl+R`: force refresh
- `Ctrl+O`: open the Web workspace
- `Ctrl+G`: open the config home directly
- `Ctrl+D`: open the debug inspector from any screen; inside the config editor it opens as a non-destructive overlay
- `Ctrl+B`: leave the current quest; if you are in config first, close config
- `Ctrl+C`: quit the TUI
- `Shift+↑/↓`: scroll the history area by one line
- `PageUp/PageDown`: scroll the history area by one page

## 6. Recommended Daily Rhythm

If TUI is your main surface, keep this order:

1. confirm whether a quest is already bound
2. then send messages
3. use `/projects` or `/use` when you need to switch quests
4. before touching connectors, confirm which quest is current

The reason is simple:

- connector binding actions bind to the current quest
- if you open `/config qq` without an active quest, TUI can save the connector config, but it cannot bind a detected runtime target to a quest for you

So the normal order should be:

1. `/new <goal>` or `/use <quest_id>`
2. confirm you are in quest mode
3. then open `/config qq`, `/config weixin`, or `/config lingzhu`

## 7. The Right Order For Connector Setup In TUI

The current best-practice order is:

1. create or switch to the quest you want to continue
2. open the connector detail page
3. read the top guide first
4. finish the platform-side action in that order
5. come back to TUI and run save, refresh, or bind

### Why the top guide matters now

The connector detail header is no longer decorative text. It is the actual next-step instruction.

- `QQ`: it tells you to fill credentials first, then send the first private QQ message, then wait for OpenID and conversation targets to appear
- `Weixin`: it tells you to create the QR code first and scan it with WeChat
- `Lingzhu`: it tells you to set a public `public_base_url` first and then copy the generated values into Rokid

## 8. QQ: Run The Full Binding Chain In TUI

This is the easiest flow to misuse, so it needs its own section.

### Recommended path

1. enter the target quest first
2. run `/config qq`
3. read the top guide
4. fill `Bot name`, `App ID`, and `App Secret`
5. run `Save Connector`
6. send the bot one private QQ message from your own QQ account
7. return to TUI and wait for auto-refresh, or press `Ctrl+R`
8. confirm that `Detected OpenID` and `Last conversation` are no longer empty
9. use the target action shown below to bind the current quest to the correct QQ target

### What you will see on the QQ page

Usually two top sections matter:

- `Top Guide`
  This tells you what to do next.
- `Current Status`
  This tells you what step is still missing.

Key fields:

- `Detected OpenID`
  This is learned automatically from runtime activity. It is not supposed to be typed first.
- `Last conversation`
  This is the latest conversation id seen by the runtime.
- `Discovered targets`
  These are the runtime targets that TUI can already use for quest binding.
- `Profile · ...`
  When QQ has multiple profiles, TUI now shows one runtime summary block per profile so you can see the detected OpenID, preferred target, current bound quest, and readiness state without switching back to Web first.

### The right way to think about QQ binding

There are two separate layers:

1. save QQ bot credentials
2. bind one runtime target to the current quest

Finishing only layer 1 does not mean the flow is complete.

A fully working QQ flow means:

- `Detected OpenID` is visible
- target actions are visible
- the current quest is bound to the correct QQ target

### Current TUI limits

- if you have multiple QQ profiles, the TUI detail page still warns that profile add, delete, and credential replacement are raw-config tasks
- adding or deleting multiple profiles is still better done in raw `connectors.yaml` or in Web settings
- per-profile summaries and runtime target bindings are visible directly in TUI

## 9. Weixin: Run The Full Binding Chain In TUI

### Recommended path

1. enter the target quest first
2. run `/config weixin`
3. choose `Bind Weixin` or `Rebind Weixin`
4. TUI switches into the QR page
5. scan with the target WeChat account on the phone
6. confirm the login in WeChat
7. after success, TUI returns to the detail page automatically
8. confirm that `Bot account`, `Owner account`, and `Known targets` are refreshed

### Current behavior that matters

- you do not need to type a bot token manually
- the QR code is generated directly inside TUI
- after the QR login succeeds, the connector config is saved automatically

### When the flow is actually done

At minimum:

- the detail page no longer looks unbound
- `Bot account` is not empty
- `Owner account` is not empty

If you want to use Weixin to keep advancing a quest, bind the relevant Weixin conversation to that quest afterward.

## 10. Lingzhu / Rokid: Run The Full Binding Chain In TUI

The key point for Lingzhu is not "click once and finish". The TUI generates platform fields, and you copy them into Rokid.

### Recommended path

1. enter the target quest first
2. run `/config lingzhu`
3. set `Public base URL` to the final public address
4. if needed, generate a new `Custom agent AK`
5. read the generated Rokid fields shown on the detail page
6. copy those values into the Rokid platform
7. return to TUI and run `Save Connector`

### What to watch carefully

- `public_base_url` must be the final public `http(s)` address
- `127.0.0.1`, `localhost`, and private LAN addresses are not valid for a real Rokid device
- the detail page now shows the same Rokid-facing generated fields as the Web popup:
  - `Custom agent ID`
  - `Custom agent URL`
  - `Custom agent AK`
  - `Agent name`
  - `Category`
  - `Capability summary`
  - `Opening message`
  - `Input type`
- use `PgUp` / `PgDn` if the full generated field list does not fit in one terminal screen

### When the flow is actually done

At minimum:

- `Public base URL` is a public address
- `Custom agent AK` is generated or filled
- the fields shown in the top guide have been copied into Rokid
- the connector has been saved

## 11. Three Full Recommended Scripts

If you want to run "create quest + configure connector + continue work" on a server through TUI, follow one of these.

### Script A: QQ

1. `ds --tui`
2. `/new <goal>`
3. wait for the quest to auto-start
4. `/config qq`
5. fill `Bot name / App ID / App Secret`
6. `Save Connector`
7. send one private QQ message to the bot
8. return to TUI and confirm `Detected OpenID` plus a target are visible
9. run the `Bind ...` action to bind the current quest to that QQ target
10. continue through QQ, TUI, or Web

### Script B: Weixin

1. `ds --tui`
2. `/new <goal>` or `/use <quest_id>`
3. `/config weixin`
4. `Bind Weixin`
5. scan and confirm on the phone
6. wait until TUI returns to the detail page
7. confirm the binding fields are refreshed
8. continue inside the quest

### Script C: Lingzhu

1. `ds --tui`
2. `/new <goal>` or `/use <quest_id>`
3. `/config lingzhu`
4. update `Public base URL`
5. generate or fill `Custom agent AK`
6. copy the top guide values into Rokid
7. `Save Connector`
8. then do the device-side connectivity check

## 12. TUI, Web, And Connectors Are The Same Quest

This point matters.

These TUI actions:

- `/new`
- `/use`
- plain messages
- `/pause`, `/resume`, `/stop`
- connector binding

all write into the same daemon and the same durable quest state.

So:

- a quest created in TUI is visible in Web immediately
- a connector bound in TUI is visible in Web immediately
- a conversation continued in QQ or Weixin returns to the same quest that TUI and Web see

TUI is not a second state system. It is another surface over the same quest.

## 13. Mailbox Semantics: Why The Agent May Not See A New Message Immediately

TUI, Web, and connectors share the same mailbox semantics.

Core rules:

1. when a quest is idle, the first normal user message starts a turn directly
2. while a quest is already running, later messages are queued first
3. queued messages are only delivered when the agent calls `artifact.interact(...)`

Durable quest files involved:

- `.ds/runtime_state.json`
- `.ds/user_message_queue.json`
- `.ds/interaction_journal.jsonl`
- `.ds/events.jsonl`

So:

- a follow-up sentence may not reach the agent within one second
- it is not lost; it is waiting in the mailbox for the next interaction point

## 14. How To Think About Pause / Resume / Stop

- `/pause`: interrupt the current runner and mark the quest as `paused`
- `/resume`: move a `paused` or `stopped` quest back to `active`
- `/stop`: a stronger interruption that marks the quest as `stopped`

`/stop` is stronger than `/pause` because:

- undelivered mailbox messages are cancelled
- stale messages are not silently replayed on the next turn
- but Git branches, worktrees, and already written files remain intact

So if you only want to pause for a while, prefer `/pause`.
If you want to cut off the current turn clearly, prefer `/stop`.

## 15. TUI Debug Mode

TUI debug mode answers three questions:

1. what surface the terminal is actually rendering
2. whether Enter will run a local command, forward to the backend, send quest chat, or get blocked locally
3. which Web page is the closest equivalent for this TUI surface

Enable it with:

```bash
ds --tui --debug
```

Choose a log path:

```bash
ds --tui --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

If you run the TUI bundle directly:

```bash
node src/tui/dist/index.js --base-url http://127.0.0.1:20999 --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

### What appears on screen

Debug mode shows a small diagnostic strip above the input area:

- `surface`: the current TUI surface, such as `home`, `quest:<id>`, `config:root:browse`, or `config:files:edit`
- `web`: the closest Web page, such as `Web Settings` or `Web quest workspace`
- `route`: the route type for the current input
- `target`: the endpoint, utility panel, or local action that would receive the input
- `parse / preview`: the parsed command and a short input preview

Press `Ctrl+D` from any screen to open the `TUI Debug` panel. The panel shows:

- `Submitted Route`: where the current input would have gone before opening the debug panel
- `Input`: a redacted input summary
- `Screen`: the current main surface, composer, selected item, and redaction state
- `Render`: quest/config/utility counts and selection index
- `Capture`: status line, session id, log path, and snapshot signature

### JSONL logs

Debug mode writes snapshots as JSONL. The default path is:

```text
/tmp/deepscientist_tui_debug.jsonl
```

Each line is one snapshot. Common fields:

- `surface`
- `web_analog`
- `route`
- `input`
- `screen`
- `counts`
- `status_line`

Config editor buffers and connector secret fields are redacted. Example:

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

Important: the JSONL log redacts config buffers, but terminal recording tools such as `script`, tmux logs, or screen recordings capture the real editor view. That is expected because the editor must show the file content. Do not post terminal transcripts containing real tokens in public issues.

### When to use debug mode

Use debug mode when:

- `/config`, `/benchstore`, `/tasks`, or another command does not appear to open the expected surface
- you need to know whether a slash command is local, backend-forwarded, or blocked
- you are in the config editor and need to know which draft Enter would save
- TUI and Web look inconsistent and you need the `web_analog`
- you need reproducible route/screen evidence for an issue or regression test

Avoid debug mode when:

- you are just chatting with a quest normally
- you are editing real secrets and also recording the full terminal output
- you only need daemon log verbosity; use `logging.level` for that

### Relationship to Web debug

Web also has a lightweight debug inspector for the Settings surface. Enable it with a query flag:

```text
/settings/connector/qq?debug=1
```

or persist it in the browser console:

```js
localStorage.setItem('deepscientist.debug', '1')
```

To keep an in-browser JSONL buffer for the current page session:

```js
localStorage.setItem('deepscientist.debug.log', '1')
```

Remove the key or use `?debug=0` to turn it off.

The Web inspector appears in the bottom-right corner. It shows the current Settings surface, route, selected section or connector, dirty/loading/saving/testing flags, config/connector/quest counts, action disabled reasons, recent API request status, and a redacted JSON snapshot. Use `Copy JSON` or `Download JSONL` when attaching evidence to an issue. When `deepscientist.debug.log` is enabled, `Download JSONL` exports the accumulated in-browser snapshot log; otherwise it exports the current snapshot.

For a strict Web/TUI comparison:

1. record TUI JSONL with `--debug-log`
2. open the matching Web page with `?debug=1`, such as `/settings/connector/qq?debug=1`
3. compare TUI `surface`, `web_analog`, and `route.target` with Web `surface`, `route`, `selected`, `flags`, and `actions`
4. confirm neither snapshot contains real token, secret, password, API key, credential, auth AK, or app secret values

Current scope: the first Web implementation covers Settings, especially connector and config pages. Quest workspace and BenchStore snapshots are planned follow-ups.

## 16. Troubleshooting

### Problem 1: I entered TUI, but plain text does nothing

Check first:

- are you still in `request mode`
- did you run `/use <quest_id>` or `/new <goal>` first

Without a bound quest, plain text is not sent.

### Problem 2: `Detected OpenID` stays empty in QQ

Check in order:

1. did you save `App ID / App Secret` first
2. did you really send the bot the first private QQ message
3. did you wait for one refresh cycle or press `Ctrl+R`

### Problem 3: I can see QQ targets, but there is no bind action

Usually that means:

- there is no active quest right now

Run:

```text
/use <quest_id>
```

Then go back to:

```text
/config qq
```

### Problem 4: I scanned the Weixin QR code, but the page did not return

Check:

- whether the login was really confirmed on the phone
- whether the daemon is still online

If unsure, press `Ctrl+R` once.

### Problem 5: Lingzhu is filled, but the device still cannot connect

Confirm:

- `Public base URL` is publicly reachable
- it is not `localhost`, `127.0.0.1`, or a private LAN address
- the Rokid platform is using the values shown in the top guide, not a local address

### Problem 6: The TUI does not seem to run my command

Start with debug enabled:

```bash
ds --tui --debug --debug-log /tmp/deepscientist_tui_debug.jsonl
```

Reproduce the input once and inspect:

- whether `route.kind` is `blocked`
- whether `route.target` is the endpoint or panel you expected
- whether `surface` changed to the expected page
- whether `web_analog` points to the Web page you expected

If you are inside the config editor, press `Ctrl+D` to open the debug inspector. Do not type `/debug`, because normal text is part of the editor buffer there.

## 17. A Simple Final Check

If you want to know whether you can really run the TUI flow end to end, check whether all four are true:

1. you can create or bind a quest from `request mode`
2. you can send messages and inspect status in `quest mode`
3. you can configure at least one connector inside `/config`
4. you understand that "connector saved" is not always the same as "quest bound", and you know where the quest binding action lives

If all four are true, you can already run the main TUI workflow end to end.
