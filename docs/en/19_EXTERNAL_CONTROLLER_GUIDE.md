# 19 External Controller Guide

DeepScientist already exposes enough durable state to support an outer orchestration layer without patching core runtime code.

This guide explains the minimal public pattern for external controllers that:

- inspect recent quest state
- decide whether the current run should continue
- enqueue a routed follow-up message through the quest mailbox
- optionally stop the current run through `quest_control`
- record a durable report explaining why the guard fired

This is intentionally lighter than a plugin framework.

## When to use an external controller

Use an external controller when the rule is:

- project-specific
- expensive to hard-code into global prompts or skills
- better treated as outer governance than as core runtime behavior

Examples:

- publishability admission rules before paper-facing writing
- repeated figure-polish loops that monopolize the frontier
- lab-specific stop / branch policies

## Public contracts you can rely on

The safest extension surface is the existing durable runtime contract:

- quest mailbox
  - queued user-facing messages are stored under `.ds/user_message_queue.json`
- recent quest state
  - runtime state, artifact state, and connector-visible outputs are already durable files
- daemon quest control
  - `POST /api/quests/<quest_id>/control`
- connector-visible durable reports
  - write your own report under the quest tree so the next turn can cite it

Prefer these contracts over prompt patching, private monkey-patching, or editing installed package files.

## Minimal controller loop

An external controller usually follows this sequence:

1. Read the latest durable quest state.
2. Decide whether a guard condition is active.
3. Write a durable report describing:
   - what was observed
   - why it matters
   - the recommended next route
4. If intervention is needed:
   - optionally stop the current run through `quest_control`
   - enqueue one clear routed mailbox message for the next turn

The mailbox message should explain the conclusion, not dump raw logs.

## Example control flow

```text
read quest state
-> detect low-yield loop or route violation
-> write durable report
-> stop current run if needed
-> enqueue one mailbox message with the required next route
```

## Example `quest_control` request

```bash
curl -X POST http://127.0.0.1:20999/api/quests/<quest_id>/control \
  -H 'Content-Type: application/json' \
  -d '{
    "action": "stop",
    "source": "external-controller"
  }'
```

## Example mailbox intervention shape

The exact queue file is runtime-owned, so your controller should preserve the existing schema and only append a normal user-style message payload.

The message content should be short and actionable, for example:

```text
Hard control message from external orchestration layer: stop the current figure loop.
Return to the main line and do one bounded route next:
1. literature scout
2. reference expansion
3. manuscript body revision
```

## Example controllers you can adapt

### Example 1: publishability admission guard

This controller is useful when a quest is drifting into paper-facing writing before the evidence line is ready.

Typical inputs:

- the latest verification note
- the current draft / summary state
- recent baseline or utility results

Typical stop condition:

- the claimed paper direction still has weak support
- one or more mandatory evidence items are still missing

Typical intervention:

1. Write `reports/publishability_guard.md` explaining the missing support.
2. Stop the current write-heavy run through `quest_control`.
3. Enqueue one mailbox message that routes the next turn back to `idea`, `analysis`, or a bounded evidence-repair step.

Example mailbox text:

```text
External controller: do not continue manuscript-facing writing yet.
Reason: the current evidence line does not pass the publishability admission gate.
Next route: return to one bounded evidence-building step before write resumes.
```

### Example 2: figure-loop guard

This controller is useful when the frontier is monopolized by repeated reopen / polish cycles on the same figure.

Typical inputs:

- recent figure artifact history
- repeated reopen events
- the latest review or summary note

Typical stop condition:

- the same figure has been reopened multiple times without improving the main claim
- the next useful action is no longer figure polish, but evidence repair or manuscript revision

Typical intervention:

1. Write `reports/figure_loop_guard.md` summarizing the loop.
2. Stop the current figure branch if needed.
3. Enqueue one mailbox message that names exactly one next route.

Example mailbox text:

```text
External controller: stop the current figure-polish loop.
Reason: repeated reopen cycles are no longer improving the main evidence line.
Next route: return to one bounded manuscript or analysis task.
```

## Example connector customization surface

The control logic should stay connector-agnostic. In practice, adapting the same controller to a different connector usually means changing only the message profile, not the stop logic or durable report contract.

For example:

```yaml
connector_profiles:
  weixin:
    summary_style: concise
    max_route_options: 2
    include_report_path: true
  telegram:
    summary_style: concise
    max_route_options: 3
    include_report_path: true
  studio:
    summary_style: detailed
    max_route_options: 4
    include_report_excerpt: true
```

The controller decision stays the same:

- read durable state
- decide whether to stop
- write a durable report
- enqueue one routed mailbox message

What changes per connector is only how much detail you surface to the human operator.

## Durable report shape

Keep reports simple and auditable.

A good report usually includes:

- `generated_at`
- `quest_id`
- `status`
- `recommended_action`
- `blockers`
- `evidence_summary`

Markdown plus a machine-readable JSON companion is a practical pattern.

## What not to rely on

Avoid building controllers that depend on:

- private prompt text offsets
- internal temporary logs that are not documented durable state
- patching installed package files inside `site-packages`
- undocumented frontend-only state

If a controller needs one of those, the contract is not stable enough yet.

## Design recommendations

- keep each controller focused on one question
- prefer additive reports over hidden side effects
- stop only when the next routed action is clear
- keep domain- or lab-specific policy outside core defaults
- treat external controllers as optional governance, not as required runtime plumbing

## Good first controllers

If you want to start small, begin with one of these:

- a publishability admission guard for paper-mode quests
- a figure-loop guard that stops repeated reopen cycles
- a route-drift guard that blocks accidental `write` transitions before evidence is ready
