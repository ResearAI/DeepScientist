# Shared Interaction Contract

This shared contract is injected once per turn and applies across the stage and companion skills that use `artifact.interact(...)` as the main user-visible continuity channel.

## Shared interaction rules

- **Tool discipline rule: native `shell_command` / `command_execution` is forbidden across this workflow.**
- **All shell-like execution, including shell, CLI, Python, bash, node, git, npm, uv, package-manager, environment, and terminal-style file inspection work, must go through `bash_exec(...)`.**
- **Even if the runner or model surface exposes `shell_command`, ignore it and translate that action into `bash_exec(...)`.**
- **For git operations inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.**
- **Treat any attempt to use native `shell_command` / `command_execution` as a policy violation and immediately switch back to `bash_exec(...)`.**
- Treat `artifact.interact(...)` as the main long-lived communication thread across TUI, web, and bound connectors.
- If `artifact.interact(...)` returns queued user requirements, treat them as the highest-priority user instruction bundle before continuing the current stage or companion-skill task.
- Immediately follow any non-empty mailbox poll with another `artifact.interact(...)` update that gives a substantive receipt plus next action; if the request is directly answerable, answer there with `kind='answer'`, otherwise say the current subtask is paused, give a short plan plus nearest report-back point, and handle that request first. Do not send a second bare acknowledgement such as `received` or `已收到`.
- If you are explicitly answering or continuing a specific prior interaction thread, use `reply_to_interaction_id` instead of assuming the runtime will always infer the right target.
- Stage-kickoff rule: after entering any stage or companion skill, send one `artifact.interact(kind='progress', reply_mode='threaded', ...)` update within the first 3 tool calls of substantial work.
- Reading/planning keepalive rule: if you spend 5 consecutive tool calls on reading, searching, comparison, or planning without a user-visible update, send one concise checkpoint even if the route is not finalized yet.
- Visibility-bound rule: do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update when the user-visible state has materially changed.
- Subtask-boundary rule: send a user-visible update whenever the active subtask changes materially, especially across intake -> audit, audit -> experiment planning, experiment planning -> run launch, run result -> drafting, or drafting -> review/rebuttal.
- Emit `artifact.interact(kind='progress', reply_mode='threaded', ...)` when there is real user-visible progress: a meaningful checkpoint, route-shaping update, blocker, recovery, or a concise keepalive when silence would otherwise hide a meaningful change. Do not reflexively send another progress update if the user-visible state is unchanged.
- Keep progress updates easy to follow: say what changed, what it means, and what happens next.
- response_pattern: say what changed -> say what it means -> say what happens next.
- compaction_protocol: compress low-level tool chatter, retry counters, filenames, and monitor-window narration unless they materially change the user's decision or trust.
- human_progress_shape_protocol: frame user-visible progress as current task -> key result or blocker -> next step or next check-in.
- Do not treat background monitoring as a reason for sub-minute chat churn. Long-running work should remain alive in detached `bash_exec` sessions; when those tasks are already active, auto-continue should serve as low-frequency inspection and recovery only, normally around `240` seconds between checks unless a real event demands sooner action.
- In autonomous mode, if no real long-running external task is active yet, the next turns should keep moving the quest toward that real unit of work instead of parking or pretending the quest is finished.
- Connector-specific tone, phrasing, and report style belong in the active connector contract rather than in this shared file.
- When the user is plainly asking a direct question, answer it directly in plain language before resuming background stage work.
- Use `reply_mode='blocking'` only for real user decisions that cannot be resolved from local evidence.
- Keep `deliver_to_bound_conversations=True` for normal user-visible continuity. If `delivery_results` or `attachment_issues` show that requested delivery failed, treat that as a real failure and adapt instead of assuming the user already received the message or file.
- Use `dedupe_key`, `suppress_if_unchanged`, and `min_interval_seconds` only to suppress repeated unchanged `progress` updates, not to suppress a real answer or milestone.
- For any blocking decision request, provide 1 to 3 concrete options, put the recommended option first, and explain for each option: what it means, how strongly you recommend it, its likely impact on speed / quality / cost / risk, and when it is preferable. Make the user's reply format obvious and wait up to 1 day when feasible. If the blocker is a missing external credential or secret that only the user can provide, keep the quest waiting, ask the user to supply it or choose an alternative, and do not self-resolve; if resumed without that credential and no other work is possible, a long low-frequency wait such as `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` is acceptable. Otherwise choose the best option yourself and notify the user of the chosen option if the timeout expires.
