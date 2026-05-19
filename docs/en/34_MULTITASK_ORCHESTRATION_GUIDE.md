# 34 Multitask Entry Guide

If you run several quests at the same time, do not rush to bind every quest to a chat app.

Chat connectors are good for reminders, quick follow-ups, and decisions. The Web workspace is better for seeing overall state, switching projects, opening files, and managing more than a few quests.

## Simple Recommendation

| Number of quests | Recommended entry | Notes |
| --- | --- | --- |
| 1-3 quests | Any entry | Web, TUI, Weixin, QQ, Telegram, and Feishu are all fine. Use what feels easiest. |
| Weixin | One main quest only | Weixin is good for personal reminders and quick replies, but it is not a good place to manage many quests. |
| QQ | Up to about 5 quests | QQ works well for a few parallel tasks. More than that gets messy quickly. |
| More than 5 quests | Web first | Use the Web workspace as the main control surface instead of a chat window. |
| More than 10 quests | Web overview + key notifications | Use connectors only for milestones, failures, and messages that need a human decision. |

Short version:

```text
Chat is comfortable for a few tasks. Once there are many tasks, use Web for the overview.
```

## Why Chat Is Not The Best Main Surface For Many Quests

The problem is not that chat cannot work. The problem is that it gets confusing quickly:

- It is hard to see which quest is running and which one is stuck.
- Messages from different quests mix together.
- Auto-bound direct messages may target the latest active quest, not the quest you had in mind.
- Files, logs, Canvas, and experiment evidence are clearer in the Web workspace.

So connectors are best treated as notification and quick-collaboration surfaces, not as the main dashboard for 10+ quests.

## How To Set Up Multiple Quests

For multiple active quests, prefer this pattern:

1. Use Web as the main entry.
2. Bind connectors only for important quests.
3. Leave lower-priority quests unbound and inspect them from Web.
4. Use Weixin for only one current main quest.
5. Use QQ for up to about five common quests.
6. When many quests are running, reduce connector push noise and keep only milestones or decision requests.

## Relationship To `max_concurrent_quests`

`daemon.max_concurrent_quests` controls how many projects may be active at once. It does not mean chat apps are the right way to manage all of them.

If you raise this value, also make sure:

- the machine has enough resources
- the runner configuration is stable
- Web is your main status view
- connectors only send a small number of important updates

## When An External Controller Helps

Most users do not need an external controller.

Read [19 External Controller Guide](./19_EXTERNAL_CONTROLLER_GUIDE.md) only when you are really running many long-lived quests and want automation for:

- scanning quest state
- finding stuck or drifting tasks
- writing a summary report
- sending only high-value messages to connectors

For 1-5 quests, Web plus one familiar chat connector is usually enough.
