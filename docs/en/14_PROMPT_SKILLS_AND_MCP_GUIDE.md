# 14 Prompt, Skills, and MCP Guide

This guide explains how one DeepScientist turn is actually driven.

Use it when you want to understand:

- how the runtime builds the prompt for each turn
- what each stage skill is for
- how the built-in MCP tools are structured
- which file or tool you should change when behavior feels wrong

If you only want the user-facing product overview, read [13 Core Architecture Guide](./13_CORE_ARCHITECTURE_GUIDE.md) first.

If you only want the built-in memory contract, read [07 Memory and MCP](./07_MEMORY_AND_MCP.md) after this page.

## 1. One-sentence summary

DeepScientist does not run from one static mega-prompt.

For every turn, it rebuilds a prompt from:

- the core system prompt
- a shared interaction contract
- runtime state
- quest files
- startup contract
- selected memory
- connector-specific rules when needed
- the active skill structure

Then the agent works through three built-in MCP namespaces only:

- `memory`
- `artifact`
- `bash_exec`

## 2. What files are the main prompt truth sources

The most important files are:

- `src/prompts/system.md`
- `src/prompts/contracts/shared_interaction.md`
- `src/prompts/connectors/qq.md`
- `src/prompts/connectors/weixin.md`
- `src/prompts/connectors/lingzhu.md`
- `src/deepscientist/prompts/builder.py`
- `src/skills/*/SKILL.md`
- `src/deepscientist/mcp/server.py`

In practice:

- `system.md` defines the global operating stance
- `shared_interaction.md` defines user-visible continuity rules
- `connectors/*.md` inject connector-specific behavior only when that connector is active or bound
- `builder.py` decides prompt assembly order and runtime context sections
- `SKILL.md` files define stage-specific execution discipline
- `mcp/server.py` defines the built-in tool surface

Managed quest-local prompt mirror:

- DeepScientist still reads prompt fragments from `quest_root/.codex/prompts/` first when they exist.
- But that tree is now managed automatically rather than assumed to be a permanent manual fork.
- Before each real runner turn, DeepScientist compares the active quest-local prompt tree against the repository `src/prompts/` tree and refreshes the active copy when the source changed or the local copy drifted.
- Before that refresh, the previous active tree is backed up under `quest_root/.codex/prompt_versions/<backup_id>/`.
- This means an old quest uses the latest prompt contracts by default, while historical prompt trees remain available for explicit replay.

## 3. How one turn prompt is assembled

The current runtime assembles the turn prompt in roughly this order:

1. `system.md`
2. `contracts/shared_interaction.md`
3. runtime context block
4. active communication surface block
5. optional connector contract block
6. turn driver and continuation guard
7. active user requirements
8. quest context
9. recent durable state
10. research delivery policy
11. paper and evidence snapshot
12. retry recovery packet when this is a retry turn
13. resume context spine when this is an auto-continue turn
14. interaction style block
15. priority memory for this turn
16. recent conversation window
17. current turn attachments
18. current user message

That order matters.

The runtime is trying to answer three questions before the model acts:

1. what is the quest trying to do now
2. what durable state already exists
3. what behavior rules apply on this surface and in this stage

## 4. What the major prompt blocks actually do

### 4.1 `system.md`

This is the global DeepScientist operating contract.

It defines things like:

- long-horizon evidence-first behavior
- use `bash_exec` for shell-like execution
- use durable files, logs, and artifacts as truth
- do not end a quest early
- treat web, TUI, and connectors as one quest
- user-facing reporting style
- baseline confirmation discipline, including preserving the richer metric surface instead of keeping only one headline scalar when the source baseline exposes multiple comparable metrics or variants

If the agent starts sounding wrong everywhere, `system.md` is one of the first places to inspect.

### 4.2 `shared_interaction.md`

This file defines the common continuity spine around `artifact.interact(...)`.

It tells the agent:

- `artifact.interact(...)` is the main user-visible thread
- queued inbound user messages must be acknowledged and handled first
- blocking replies are for real decisions only
- progress updates should be concise and human-readable
- the real user-facing interaction message should stay complete; the runtime may derive a shorter preview separately, so the agent should not manually truncate the actual connector answer with `...` / `…`

If the model is bad at staying in the same long-running thread, this file matters a lot.

### 4.3 Active communication surface

The prompt builder adds a surface block each turn.

This tells the model:

- whether the current turn is local, QQ, Weixin, or another connector
- how many external connectors are bound
- which surface is active right now
- how much detail is appropriate on that surface

This is why connector behavior should not be hard-coded globally.

The same quest may be viewed from the web UI, TUI, or a connector, but the reply shape should adapt.

### 4.4 Connector contract

Connector prompt fragments are loaded only when needed.

Current connector prompt files are:

- `src/prompts/connectors/qq.md`
- `src/prompts/connectors/weixin.md`
- `src/prompts/connectors/lingzhu.md`

These files define surface-specific rules such as:

- reply length
- text-first versus media-enabled behavior
- how attachments should be sent
- what not to expose in chat

For example:

- QQ is treated as a milestone operator surface
- Weixin is treated as a concise phone-side operator surface with `context_token` continuity
- Lingzhu is treated as an even shorter, more constrained surface

If one connector needs behavior changes, change its connector prompt first before bloating the global system prompt.

### 4.5 Runtime context and durable quest state

The builder injects runtime facts such as:

- `quest_id`
- `quest_root`
- current workspace branch
- active idea id
- active analysis campaign id
- bound conversations
- startup contract
- baseline gate
- active interactions
- recent artifacts
- recent runs

This is what makes the prompt quest-aware instead of generic.

### 4.6 Quest context

The builder reads these quest files directly into the prompt:

- `brief.md`
- `plan.md`
- `status.md`
- `SUMMARY.md`

This is important:

- the live prompt is not only based on chat history
- durable quest docs are treated as first-class truth surfaces

### 4.7 Research delivery policy

This block converts startup choices into concrete execution rules.

It includes logic around:

- whether paper delivery is required
- launch mode
- custom profile
- baseline routing
- idea routing
- paper branch behavior
- review gate behavior

If `Start Research` behavior feels wrong, you usually need to inspect:

- the `startup_contract`
- `src/deepscientist/prompts/builder.py`
- the stage skill the quest is currently using

It also carries the key mode split for continuation:

- `workspace_mode = copilot`
  - request-scoped help
  - complete one useful unit, then normally park and wait for the next user message or `/resume`
- `workspace_mode = autonomous`
  - keep advancing without waiting for the user
  - if no real long-running external task exists yet, keep using the next turns to prepare, launch, or durably decide that real unit of work
  - once a real long-running external task exists, background auto-continue turns become low-frequency monitoring passes

### 4.8 Interaction style

This block tells the model how to speak on this turn.

It includes:

- locale bias
- blocking versus threaded behavior
- long-run update cadence
- how to acknowledge mailbox messages
- how to compress progress into human-readable updates

This is why DeepScientist can keep the same runtime but behave differently across:

- long experiments
- connector replies
- writing stages
- waiting-for-decision stages

It now also encodes the auto-continue cadence split:

- autonomous preparation / launch work may continue quickly across turns
- monitoring an already-running external task should switch to low-frequency checks, roughly every `240` seconds by default
- copilot mode should usually stop after the current requested unit instead of auto-continuing

### 4.9 Resume context spine

On auto-continue turns, the prompt now injects a compact resume spine so the model does not restart from a vague stage label alone.

It includes:

- the latest durable user message
- the latest assistant checkpoint
- the latest run result summary
- a few recent memory cues
- current `bash_exec` state, including whether a long-running shell session is active

This is the main reason auto-continue turns can stay grounded in the latest intent and latest checkpoint instead of drifting into generic stage narration.

### 4.10 Priority memory

DeepScientist does not inject memory randomly.

`PromptBuilder` uses a stage-specific memory plan.

Examples:

- `scout` prefers `papers`, `knowledge`, `decisions`
- `baseline` prefers `papers`, `decisions`, `episodes`, `knowledge`
- `idea` prefers `papers`, `ideas`, `decisions`, `knowledge`
- `experiment` prefers `ideas`, `decisions`, `episodes`, `knowledge`

This means the prompt is stage-biased on purpose.

The agent should not see the same memory bundle on every turn.

## 5. Managed local prompt copies and historical versions

The active quest-local prompt tree lives under:

- `.codex/prompts/system.md`
- `.codex/prompts/contracts/shared_interaction.md`
- `.codex/prompts/connectors/<connector>.md`

Repository defaults still live under `src/prompts/`.

Important behavior change:

- `.codex/prompts/` is no longer best understood as a permanent hand-maintained override tree.
- On each real run, DeepScientist repairs the active quest-local copy back to the current repository prompt source when they differ.
- Manual edits to the active copy are therefore treated as drift: they are backed up and then replaced on the next run.
- Historical copies are preserved under `.codex/prompt_versions/<backup_id>/`.

If you need to run a quest against an older prompt version intentionally, start the daemon or one-off run with the official DeepScientist version number:

- `ds daemon --prompt-version <official_version>`
- `ds run --prompt-version <official_version> ...`

DeepScientist resolves that to the newest backup recorded for that formal version. If you need one exact backup rather than “latest backup for version X”, you may still pass the exact backup directory name.

Use `latest` to stay on the managed active prompt tree.

If a prompt change should affect normal future behavior, change the repository prompt source instead of editing only one quest-local active copy.

## 6. How skills are structured

DeepScientist currently has two skill layers:

1. standard stage skills
2. companion skills

### 6.1 Standard stage skills

These are the main research anchors:

| Skill | Use when | Main job | Usually hands off to |
|---|---|---|---|
| `scout` | the task frame is still unclear | task framing, baseline discovery, metric and dataset clarification | `baseline` or `idea` |
| `baseline` | a trustworthy baseline does not yet exist | attach, import, reproduce, repair, and verify the baseline | `idea` |
| `idea` | the baseline is clear but the next direction is not | generate, compare, and select durable research directions | `experiment` |
| `experiment` | one selected idea is ready to run | implement and evaluate the main run on one durable line | `analysis-campaign`, `write`, or `decision` |
| `analysis-campaign` | follow-up experiments are needed | run slices, ablations, robustness checks, or reviewer-facing supplements | `write`, `decision`, or `finalize` |
| `write` | there is enough evidence to draft | turn accepted evidence into outline, draft, and paper bundle work | `review` or `finalize` |
| `finalize` | the quest is near closure | consolidate claims, summaries, final state, and closure checks | quest completion approval |
| `decision` | a durable route choice is needed | make a clear go/stop/branch/reuse decision from evidence | another anchor |

### 6.2 Companion skills

These are auxiliary entry or quality-control skills:

| Skill | Use when | Main job |
|---|---|---|
| `figure-polish` | a figure is important beyond debug use | render-inspect-revise a milestone or paper figure |
| `intake-audit` | the quest already has meaningful prior state | trust-rank old assets and choose the correct next anchor |
| `review` | a substantial draft already exists | run a skeptical paper-like audit before claiming done |
| `rebuttal` | reviewer comments or revision requests exist | map reviewer pressure into experiments, text deltas, and response artifacts |

### 6.3 The important design point

The daemon is not supposed to contain a giant hard-coded research scheduler.

Instead:

- the prompt defines the operating contract
- the skill defines stage-specific discipline
- the runtime persists state and routes turns

That is the core DeepScientist design choice.

## 7. What each skill usually leaves behind

These are the durable outputs you should expect:

| Skill | Typical durable outputs |
|---|---|
| `scout` | updated `brief.md`, updated `plan.md`, literature notes, framing memory |
| `baseline` | `PLAN.md`, `CHECKLIST.md`, baseline verification notes, confirmed or waived baseline state |
| `idea` | durable idea draft, selected idea package, rationale for why this route won |
| `experiment` | implementation changes, run logs, `record_main_experiment(...)`, result evidence |
| `analysis-campaign` | campaign manifest, slice records, synthesis notes |
| `write` | selected outline, writing plan, draft, references, claim-evidence map, paper bundle |
| `finalize` | final summary, closure state, final quest health check |
| `decision` | durable route decision, next-anchor recommendation |
| `intake-audit` | trusted-versus-untrusted asset map, next anchor recommendation |
| `review` | review report, revision log, experiment TODO list |
| `rebuttal` | review matrix, response letter, text deltas, evidence-update plan |
| `figure-polish` | final polished figure assets and render-checked outputs |

## 8. Built-in MCP structure

DeepScientist keeps the built-in MCP surface intentionally small.

Only these namespaces are built in:

- `memory`
- `artifact`
- `bash_exec`

There is no separate public built-in `git` namespace.

Git-aware behavior is exposed through `artifact`.

### 8.1 `memory`

Purpose:

- reusable knowledge
- lessons that should survive beyond one turn
- quest-local or global memory cards

Current built-in tools:

- `memory.write(...)`
- `memory.read(...)`
- `memory.search(...)`
- `memory.list_recent(...)`
- `memory.promote_to_global(...)`

Use `memory` when the output should be remembered and reused later.

Do not use it for transient progress chatter.

### 8.2 `artifact`

Purpose:

- quest control plane
- durable research state
- Git-aware branch and worktree routing
- experiment and paper records
- user-visible interaction continuity

The artifact namespace is large, but it is still one family.

#### A. Generic durable records

- `artifact.record(...)`
- `artifact.refresh_summary(...)`
- `artifact.render_git_graph(...)`

#### B. Branch and route control

- `artifact.checkpoint(...)`
- `artifact.prepare_branch(...)`
- `artifact.activate_branch(...)`
- `artifact.submit_idea(...)`
- `artifact.list_research_branches(...)`
- `artifact.resolve_runtime_refs(...)`

#### C. Baseline lifecycle

- `artifact.publish_baseline(...)`
- `artifact.attach_baseline(...)`
- `artifact.confirm_baseline(...)`
- `artifact.waive_baseline(...)`

#### D. Experiment and analysis lifecycle

- `artifact.record_main_experiment(...)`
- `artifact.create_analysis_campaign(...)`
- `artifact.get_analysis_campaign(...)`
- `artifact.record_analysis_slice(...)`

#### E. Paper lifecycle

- `artifact.submit_paper_outline(...)`
- `artifact.list_paper_outlines(...)`
- `artifact.submit_paper_bundle(...)`

#### F. Reading and interaction continuity

- `artifact.arxiv(...)`
- `artifact.interact(...)`
- `artifact.complete_quest(...)`

The most important artifact tool for long-running collaboration is:

- `artifact.interact(...)`

Because it keeps together:

- user-visible updates
- mailbox polling
- connector delivery
- threaded continuity
- attachment delivery

### 8.3 `bash_exec`

Purpose:

- durable shell execution
- monitored long runs
- durable logs
- stoppable and readable sessions

Current built-in tool:

- `bash_exec.bash_exec(...)`

This one tool supports multiple modes:

- `detach`
- `await`
- `read`
- `kill`
- `list`
- `history`

The design rule is simple:

- anything shell-like should go through `bash_exec`
- do not hide important execution in transient shell snippets
- for already running managed sessions, prefer bounded waits such as `bash_exec.bash_exec(mode='await', id=..., wait_timeout_seconds=1800)`; if the wait window ends first, the process keeps running and the next step should usually be reading logs rather than killing the session

## 9. How the three MCP namespaces divide responsibility

Use this mental model:

- `memory`: remember
- `artifact`: decide and record
- `bash_exec`: run and monitor

Examples:

- a reusable lesson from a failed run -> `memory.write(...)`
- confirming a baseline -> `artifact.confirm_baseline(...)`
- launching training -> `bash_exec.bash_exec(mode='detach', ...)`
- notifying the user about the next checkpoint -> `artifact.interact(...)`

If you mix these roles badly, the quest becomes harder to resume and audit.

## 10. How one real turn usually works

A typical turn looks like this:

1. a user or connector message arrives
2. the daemon restores quest snapshot and history
3. `PromptBuilder` assembles the current turn prompt
4. the active skill defines the stage discipline
5. priority memory is injected
6. the agent uses `memory`, `artifact`, and `bash_exec`
7. outputs are persisted into files, artifacts, memory cards, logs, and Git state
8. `artifact.interact(...)` keeps the user-facing thread continuous

That is why DeepScientist feels more like a persistent workshop than a stateless chat.

## 11. When to change prompt, skill, or MCP code

Use this quick rule:

- change `src/prompts/system.md` when the global operating stance is wrong
- change `src/prompts/contracts/shared_interaction.md` when continuity behavior is wrong
- change `src/prompts/connectors/*.md` when one connector behaves wrong
- change `src/skills/<skill>/SKILL.md` when one stage behaves wrong
- change `src/deepscientist/prompts/builder.py` when prompt assembly or runtime context selection is wrong
- change `src/deepscientist/mcp/server.py` when the built-in tool surface itself is wrong

Do not use a giant prompt patch to fix a real MCP contract bug.

Do not use a new MCP tool to fix a stage-discipline problem that belongs in a skill.

## 12. What to read next

- [07 Memory and MCP](./07_MEMORY_AND_MCP.md)
- [13 Core Architecture Guide](./13_CORE_ARCHITECTURE_GUIDE.md)
- [06 Runtime and Canvas](./06_RUNTIME_AND_CANVAS.md)
- [01 Settings Reference](./01_SETTINGS_REFERENCE.md)

## 13. Distill finalize gate

Quests opt into experience distillation by setting `experience_distill: {mode: on}` in the `startup_contract` field of `quest.yaml`. Once enabled, the finalize gate intercepts `decision(action='write'|'finalize')` whenever there are completed runs that have not yet been reviewed: it injects a `guidance_vm` directive pointing the agent at the `distill` skill before write is allowed. The `distill` skill uses the `artifact.list_distill_candidates` MCP tool (auto-approved for Codex) to enumerate the current batch of undistilled runs visible under the active workspace root. After distilling the batch, the skill records a `distill_review` artifact — specifying `reviewed_run_ids` (which must all reference known run artifact IDs) and any `cards_written` — which advances the cursor. On the subsequent `decision(write)` call the gate finds no pending candidates and clears, returning the quest to the normal finalize path.
