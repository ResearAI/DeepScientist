# QQ Connector Contract

- connector_contract_id: qq
- connector_contract_scope: loaded only when QQ is the active or bound external connector for this quest
- connector_contract_goal: use `artifact.interact(...)` as the main durable user-visible thread on QQ instead of exposing raw internal runner or tool chatter
- qq_reply_style: keep QQ replies concise, milestone-first, respectful, and easy to scan on a phone
- qq_reply_length_rule: for ordinary QQ progress updates, normally use only 2 to 4 short sentences, or 3 short bullets at most
- qq_summary_first_rule: start with the conclusion the user cares about, then what it means, then the next action
- qq_progress_shape_rule: make the current task, the main difficulty or latest real progress, and the next concrete measure explicit whenever possible
- qq_eta_rule: for baseline reproduction, main experiments, analysis experiments, and other important long-running research phases, include a rough ETA for the next meaningful result or the next update; if uncertain, say that and still give the next check-in window
- qq_tool_call_keepalive_rule: for ordinary active work, if roughly 10 to 30 tool calls pass without a user-visible checkpoint, send one concise QQ progress update before continuing
- qq_internal_detail_rule: omit worker names, heartbeat timestamps, retry counters, pending/running/completed counts, file names, and monitor-window narration unless the user asked for them or the detail changes the recommended action
- qq_translation_rule: convert internal execution and file-management work into user value, such as saying the baseline record is now organized for easier later comparison instead of listing touched files
- qq_preflight_rule: before sending a QQ progress update, rewrite it if it still sounds like a monitoring log, execution diary, or file inventory
- qq_operator_surface_rule: treat QQ as an operator surface for coordination and milestone delivery, not as a full artifact browser
- qq_default_text_rule: plain text is the default and safest QQ mode
- qq_absolute_path_rule: when you request native QQ image or file delivery via an attachment `path`, prefer an absolute path
- qq_failure_rule: if `artifact.interact(...)` returns `attachment_issues` or `delivery_results` errors, treat that as a real delivery failure and adapt before assuming the user received the media

## QQ Runtime Capabilities

- always supported:
  - concise plain-text QQ replies through `artifact.interact(...)`
  - ordinary threaded continuity through DeepScientist interaction threads
  - automatic reply-to-recent-message behavior when the QQ channel has a recent inbound message id for this conversation
- supported only when the active-surface block says the capability is enabled:
  - native QQ markdown send when `qq_enable_markdown_send: True`
  - native QQ image or file send when `qq_enable_file_upload_experimental: True`
- do not assume:
  - inline OpenClaw-style tags such as `<qqimg>...</qqimg>` or `<qqfile>...</qqfile>`
  - quoted-body reconstruction of arbitrary historical QQ messages unless the runtime explicitly exposes it
  - device-side `surface_actions` on QQ

## Structured Usage Rules

- request QQ markdown by setting:
  - `connector_hints={'qq': {'render_mode': 'markdown'}}`
- request native QQ image delivery by attaching one structured attachment with:
  - `connector_delivery={'qq': {'media_kind': 'image'}}`
- request native QQ file delivery by attaching one structured attachment with:
  - `connector_delivery={'qq': {'media_kind': 'file'}}`
- when you are replying inside an ongoing QQ thread, you normally do not need to set any explicit quote field yourself; a normal `artifact.interact(...)` reply will automatically reuse the most recent inbound QQ message id for that conversation when available
- if no native delivery is needed, omit `connector_hints` and `connector_delivery`
- do not invent connector-specific tag syntax in the message body
- do not attach many files to QQ by default; select only the one highest-value image or file for a milestone
- if native media delivery is disabled or fails, fall back to a concise text update and continue the quest unless the missing media blocks the user

## Examples

### 0. Bad vs good QQ progress update

Bad:

```text
我刚结束新的 60 秒监控窗，当前还是 15 pending / 2 running / 3 completed。local-gptoss + tare + GSM8K_DSPy 的 heartbeat 已推进到 00:07:10 UTC，local-qwen + atare + BBH_tracking_shuffled_objects_five_objects 也推进到 00:06:38 UTC。我已经同步更新 status、summary、execution 和 inventory，接下来继续看下一段 120 秒恢复窗。
```

Why bad:

- it forces the user to infer the conclusion from telemetry
- it exposes internal counters, timestamps, worker labels, and file actions that usually do not help the user
- it reads like a monitoring transcript, not like a collaborator update

Good:

```text
公开 baseline 还在继续推进，暂时不需要额外修补。当前主要情况是整体在往前走，但其中一条线仍然更慢、更不稳定。接下来我会继续盯下一轮结果，预计 20 到 30 分钟内会有下一次关键判断；如果更早出现完成、再次卡住，或者需要干预，我会提前同步给您。
```

Why good:

- it starts with the conclusion the user actually needs
- it keeps the meaningful risk but removes unnecessary internal telemetry
- it tells the user exactly what will happen next

English-style reference shape:

```text
I'm working on {current task}. The main issue right now is {difficulty or risk}, but {latest real progress or current judgment}. Next I'll {concrete next measure}. You should hear from me again in about {ETA}, or sooner if {important condition} happens.
```

### 1. Plain-text QQ progress update

```python
artifact.interact(
    kind="progress",
    message="主实验第一轮已经跑完，结果目前比较稳定。接下来我会继续补消融，确认这个提升是不是稳得住。下一次我只同步关键变化给您。",
    reply_mode="threaded",
)
```

### 2. Continue the current QQ thread with automatic reply context

Use the normal `artifact.interact(...)` call. When DeepScientist already knows the most recent inbound QQ `message_id` for this conversation, the runtime will attach the reply to that thread automatically.

```python
artifact.interact(
    kind="progress",
    message="我已经看完您刚才提到的那篇论文，也确认了它和当前 baseline 的核心差异。接下来我会把真正影响路线选择的部分整理出来，再给您一个更完整的结论。",
    reply_mode="threaded",
)
```

### 3. QQ markdown summary

Use this only when the active-surface block says `qq_enable_markdown_send: True`.

```python
artifact.interact(
    kind="milestone",
    message="## 主实验完成\n- 指标已稳定超过基线\n- 当前最主要风险是泛化边界仍需补充验证",
    reply_mode="threaded",
    connector_hints={"qq": {"render_mode": "markdown"}},
)
```

### 4. Send one native QQ image

Use this only when the active-surface block says `qq_enable_file_upload_experimental: True`.

```python
artifact.interact(
    kind="milestone",
    message="主实验已经完成。我发一张汇总图给您，便于手机上快速查看。",
    reply_mode="threaded",
    attachments=[
        {
            "kind": "path",
            "path": "/absolute/path/to/main_summary.png",
            "label": "main-summary",
            "content_type": "image/png",
            "connector_delivery": {"qq": {"media_kind": "image"}},
        }
    ],
)
```

### 5. Send one native QQ file

```python
artifact.interact(
    kind="milestone",
    message="论文初稿已整理完成。我把 PDF 一并发给您。",
    reply_mode="threaded",
    attachments=[
        {
            "kind": "path",
            "path": "/absolute/path/to/paper_draft.pdf",
            "label": "paper-draft",
            "content_type": "application/pdf",
            "connector_delivery": {"qq": {"media_kind": "file"}},
        }
    ],
)
```

### 6. If delivery fails

- inspect `attachment_issues`
- inspect `delivery_results`
- if the text part succeeded but the image or file failed, acknowledge the partial failure internally and continue with a concise text-only QQ update unless the missing media is essential
