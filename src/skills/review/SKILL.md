---
name: review
description: Use when a draft, paper, or paper-like report is substantial enough for an independent skeptical audit before finalization, rebuttal, or revision routing.
---

# Review

Use this skill when the quest already has a substantial draft, paper, or paper-like report and now needs an independent, skeptical, evidence-grounded audit.

This is not the same as ordinary `write`.
It is also not the same as `rebuttal`.

- `write` turns accepted evidence into a narrative.
- `review` audits that narrative like a harsh but constructive expert reviewer.
- `rebuttal` responds to concrete external reviewer pressure that already exists.

## Interaction discipline

- Treat `artifact.interact(...)` as the main long-lived communication thread across TUI, web, and bound connectors.
- If `artifact.interact(...)` returns queued user requirements, treat them as the highest-priority user instruction bundle before continuing the review pass.
- Immediately follow any non-empty mailbox poll with another `artifact.interact(...)` update that confirms receipt; if the request is directly answerable, answer there, otherwise say the current subtask is paused, give a short plan plus nearest report-back point, and handle that request first.
- Emit `artifact.interact(kind='progress', reply_mode='threaded', ...)` when there is real user-visible progress: the first meaningful signal of the review pass, a meaningful checkpoint, or a concise keepalive if active work has drifted beyond roughly 10 to 30 tool calls without a user-visible update.
- Keep progress updates chat-like and easy to understand: say what changed, what it means, and what happens next.
- Default to plain-language summaries. Do not mention file paths, artifact ids, branch/worktree ids, session ids, raw commands, or raw logs unless the user asks or needs them to act.
- Use `reply_mode='blocking'` only for real user decisions that cannot be resolved from local evidence.
- For any blocking decision request, provide 1 to 3 concrete options, put the recommended option first, explain each option's actual content plus pros and cons, and wait up to 1 day when feasible. If the blocker is a missing external credential or secret that only the user can provide, keep the quest waiting, ask the user to supply it or choose an alternative, and do not self-resolve; if resumed without that credential and no other work is possible, a long low-frequency wait such as `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` is acceptable. Otherwise choose the best option yourself and notify the user of the chosen option if the timeout expires.
- When the review report, revision plan, or follow-up experiment TODO list becomes durable, send a richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` update that says what the main risks are, what should be fixed next, and whether the next route is writing, experiment, or claim downgrade.

## Purpose

`review` is an auxiliary audit skill for paper-like deliverables.

It should convert “the draft feels almost done” into a durable, skeptical, technically grounded review workflow:

1. identify the core claims and likely rejection reasons
2. audit novelty, value, rigor, clarity, and evidence sufficiency
3. write a reliable review note, not vague prose
4. produce a concrete revision plan
5. produce a follow-up experiment TODO list only when the paper truly needs more evidence
6. route the next step cleanly to `write`, `analysis-campaign`, `baseline`, `scout`, or `decision`

Default review stance: independent audit before celebration.
Do not treat “looks polished” as “is defensible”.

## Use when

- a substantial `paper/draft.md`, report draft, or paper-like manuscript already exists
- the quest has enough evidence to support a real audit rather than just speculative comments
- the user asks for:
  - a harsh review
  - a reliable paper audit
  - revision advice before submission
  - a decision about whether more experiments are still needed
- the writing line feels close to done and you need a skeptical gate before stopping

## Do not use when

- the quest still lacks a meaningful draft or report
- the task is ordinary drafting from evidence
- concrete external reviewer comments already exist and the real task is response / revision
  - in that case use `rebuttal`

## Non-negotiable rules

- Review independently. Do not simply mirror previous self-review notes.
- Do not fabricate praise, flaws, citations, novelty overlaps, or fatal defects.
- Keep every serious criticism evidence-grounded.
- Do not recommend more experiments when the real problem is wording, positioning, or claim scope.
- Do not recommend rhetoric when the real problem is missing evidence.
- If novelty or positioning is uncertain, treat that as a literature-audit question first, not an automatic experiment request.
- If a claim is too broad for the evidence, prefer narrowing or downgrading the claim over defending it with style.

## Primary inputs

Use, in roughly this order:

- the current paper or report draft
- the selected outline if one exists
- the claim-evidence map if one exists
- the six-field `evaluation_summary` blocks from recent main experiments and analysis slices
- recent main and analysis experiment results
- figures, tables, and captions
- prior self-review or reviewer-first notes as low-trust auxiliary input
- nearby papers when novelty or comparison is unclear

If the draft/result state is still unclear, open `intake-audit` first before continuing the review workflow.
Before proposing extra experiments, read those structured `evaluation_summary` blocks first so you do not request work that the recorded evidence already resolved.

## Core outputs

The review pass should usually leave behind:

- `paper/review/review.md`
- `paper/review/revision_log.md`
- `paper/review/experiment_todo.md`

Use the templates in `references/` when needed:

- `review-report-template.md`
- `revision-log-template.md`
- `experiment-todo-template.md`

## Review dimensions

Audit at least these dimensions:

- research question and value
- novelty and positioning
- method-to-problem fit
- evidence sufficiency
- experimental validity and baseline comparability
- claim scope and over-claiming risk
- writing defensibility and logical flow
- figure / table usefulness
- submission readiness

## Workflow

### 1. Plan the audit

Before writing the review itself, make the audit explicit.

Identify:

- 1 to 3 core claims such as `C1`, `C2`, `C3`
- the strongest current evidence
- the weakest current evidence
- the top 3 likely rejection reasons
- whether the likely next route is:
  - text revision
  - literature / novelty audit
  - baseline recovery
  - supplementary experiment
  - claim downgrade

### 2. Check novelty and positioning only when needed

If novelty, related-work coverage, or field positioning is unclear:

1. open `scout`
2. run a focused literature / comparison audit
3. record what is genuinely overlapping, what remains novel, and what is merely better positioned writing

Do not request new experiments just to answer a literature-positioning question.

### 3. Write a reliable review report

Write `paper/review/review.md` using `references/review-report-template.md`.

The review should be:

- independent
- skeptical but constructive
- technically specific
- reader-aware
- evidence-grounded

At minimum, the review report should cover:

- summary
- strengths
- weaknesses
- key issues
- actionable suggestions
- storyline / outline advice
- priority revision plan
- experiment inventory and research experiment plan
- novelty verification and related-work matrix
- references

If helpful, include an internal conservative overall judgment or score, but do not pretend numerical precision when evidence is still unstable.

### 4. Produce the revision log

Write `paper/review/revision_log.md` using `references/revision-log-template.md`.

For each serious issue, record:

- issue id
- why it matters
- what should change
- whether the fix is writing-only, evidence-only, or experiment-dependent
- whether the issue blocks `finalize`

### 5. Produce the follow-up experiment TODO list

Only if more evidence is truly needed, write `paper/review/experiment_todo.md` using `references/experiment-todo-template.md`.

Each TODO item should include:

- the review issue it answers
- why existing evidence is still insufficient
- the minimum experiment or analysis needed
- required metric(s)
- minimal success criterion
- whether this is:
  - analysis of existing results
  - new comparator baseline
  - supplementary experiment
  - figure / table regeneration only

Do not write a vague “run more ablations” list.
Each TODO item should be concrete enough to turn into `analysis-campaign` slices or a `baseline` recovery task.
When extra evidence is truly needed, use the shared supplementary-experiment protocol:

- recover ids / refs first if needed
- create one `artifact.create_analysis_campaign(...)`
- represent even one extra run as a one-slice campaign
- record each completed slice with `artifact.record_analysis_slice(...)`

Do not invent a separate review-only experiment workflow.

### 6. Route the next step

After the review artifacts are durable:

- if the issues are mostly narrative or claim-scope fixes, route to `write`
- if novelty / positioning is still unclear, route to `scout`
- if a requested comparator baseline is missing, route to `baseline`
- if new evidence is truly required, route to `analysis-campaign`
- if the route is costly or non-obvious, record a `decision`

Do not stop immediately after writing the review if the next route is already clear.

## Companion skill routing

Open additional skills only when the review workflow requires them:

- `intake-audit`
  - when the current draft/result/bundle state is still unclear
- `scout`
  - when novelty, positioning, or related-work coverage is genuinely uncertain
- `baseline`
  - when a missing comparator baseline blocks fair review
- `analysis-campaign`
  - when the review identifies concrete evidence gaps that need supplementary runs
- `write`
  - when the review identifies text, outline, claim-scope, or figure revisions
- `figure-polish`
  - when the review identifies figure/table quality as a real weakness
- `decision`
  - when route choice, cost, or claim downgrade is non-trivial

## Artifact routing guidance

Use these tools deliberately:

- `artifact.record(kind='decision', ...)`
  - review conclusion, claim downgrade recommendation, route choice, stop/go recommendation
- `artifact.create_analysis_campaign(...)`
  - when the experiment TODO list should become concrete follow-up slices
- `artifact.record_analysis_slice(...)`
  - one completed review-driven slice
- `artifact.submit_paper_outline(mode='revise', ...)`
  - when the review materially changes the narrative blueprint
- `artifact.submit_paper_bundle(...)`
  - only when the revised manuscript package is genuinely ready
- `artifact.interact(...)`
  - user-visible progress and review milestones

## Memory discipline

Stage-start requirement:

- run `memory.list_recent(scope='quest', limit=5)`
- run at least one `memory.search(...)` for:
  - paper title
  - main method name
  - review or self-review
  - key claim or strongest figure

Stage-end requirement:

- if the review produced a durable lesson, claim downgrade, revision rule, or experiment-gap judgment, write at least one `memory.write(...)`

Useful tags include:

- `stage:review`
- `type:paper-review`
- `type:revision-plan`
- `type:experiment-gap`
- `type:claim-downgrade`

## Success condition

`review` is successful when:

- a reliable skeptical review note exists
- the highest-risk issues are explicit
- the next revision route is unambiguous
- any needed experiments are captured as a concrete TODO list
- the quest can continue into `write`, `analysis-campaign`, `baseline`, `scout`, or `finalize` without ambiguity

The goal is not to sound severe.
The goal is to make the next revision step technically clear and evidence-bound.
