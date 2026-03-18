---
name: rebuttal
description: Use when a quest already has a paper, draft, or review package and the task is to map reviewer feedback into experiments, manuscript deltas, and a durable rebuttal / revision response.
---

# Rebuttal

Use this skill when the quest is in review, revision, or rebuttal mode.

This is not the same as ordinary `write`.
The task is no longer “draft the paper from evidence”.
The task is “respond to concrete reviewer pressure with the smallest honest set of experiments, text changes, claim adjustments, and response artifacts”.

## Interaction discipline

- Treat `artifact.interact(...)` as the main long-lived communication thread across TUI, web, and bound connectors.
- If `artifact.interact(...)` returns queued user requirements, treat them as the highest-priority user instruction bundle before continuing the rebuttal pass.
- Immediately follow any non-empty mailbox poll with another `artifact.interact(...)` update that confirms receipt; if the request is directly answerable, answer there, otherwise say the current subtask is paused, give a short plan plus nearest report-back point, and handle that request first.
- Emit `artifact.interact(kind='progress', reply_mode='threaded', ...)` when there is real user-visible progress: the first meaningful signal of the rebuttal pass, a meaningful checkpoint, or a concise keepalive if active work has drifted beyond roughly 10 to 30 tool calls without a user-visible update.
- Keep progress updates chat-like and easy to understand: say what changed, what it means, and what happens next.
- Default to plain-language summaries. Do not mention file paths, artifact ids, branch/worktree ids, session ids, raw commands, or raw logs unless the user asks or needs them to act.
- Message templates are references only. Adapt to the actual context and vary wording so updates feel natural and non-robotic.
- Use `reply_mode='blocking'` only for real user decisions that cannot be resolved from local evidence.
- For any blocking decision request, provide 1 to 3 concrete options, put the recommended option first, explain each option's actual content plus pros and cons, and wait up to 1 day when feasible. If the blocker is a missing external credential or secret that only the user can provide, keep the quest waiting, ask the user to supply it or choose an alternative, and do not self-resolve; if resumed without that credential and no other work is possible, a long low-frequency wait such as `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` is acceptable. Otherwise choose the best option yourself and notify the user of the chosen option if the timeout expires.
- If a threaded user reply arrives, interpret it relative to the latest rebuttal progress update before assuming the task changed completely.
- When the rebuttal plan, the main supplementary-evidence package, or the final response bundle becomes durable, send one richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` update that says what reviewer concerns are now addressed, what still remains open, and what happens next.

## Purpose

`rebuttal` is an auxiliary orchestration skill for review-driven work.

It should convert reviewer material into a durable response workflow:

1. parse and normalize the review package
2. split comments into stable atomic items and classify what they actually require
3. decide which concerns need literature/positioning analysis, which need experiments, which need text, and which require claim downgrades
4. route supplementary runs to `analysis-campaign` only after the analysis step says they are truly needed
5. route manuscript edits to `write`
6. assemble the response letter and revision ledger

Default rebuttal stance: analysis before execution.
Do not jump from “reviewer asked for more evidence” straight to experiments.
Do not invent rebuttal-only special tools or side workflows.
Stay inside the normal DeepScientist surface: `memory`, `artifact`, `bash_exec`, plus ordinary stage/companion skills.
First decide whether the issue is actually:

- a wording / clarity gap
- a literature / novelty / positioning gap
- an evidence-presentation gap
- a missing baseline or comparator
- a genuinely new experiment gap

## Use when

- `startup_contract.custom_profile = revision_rebuttal`
- the quest already has:
  - reviewer comments
  - a meta-review
  - a revision request
  - a decision letter
  - a list of required extra experiments for a submitted paper
- the user says:
  - “补实验并写 rebuttal”
  - “根据 review 修改论文”
  - “先整理 reviewer comments 再决定实验”

## Do not use when

- the paper does not yet exist and the task is ordinary paper drafting
- there are no concrete review materials
- the work is actually a fresh ideation or baseline quest

## Non-negotiable rules

- Do not invent experiment results, response claims, or manuscript changes that have not been made.
- Do not promise “we will add” unless the work is truly planned and the response format explicitly allows future-work statements.
- Do not silently ignore hard reviewer concerns because they are inconvenient.
- Do not answer a reviewer with rhetoric when the issue actually requires evidence.
- Do not run supplementary experiments without first mapping them to named reviewer concerns.
- Do not keep the original claim scope if the new evidence no longer supports it.
- If a reviewer request cannot be fully satisfied, say so clearly and explain the honest limitation.

## Primary inputs

Use, in roughly this order:

- the current paper or draft
- the selected outline if one exists
- review comments, meta-review, or editor letter
- the six-field `evaluation_summary` blocks from recent main experiments and analysis slices
- recent main and analysis experiment results
- prior decision and writing memory
- existing figures, tables, and claim-evidence maps

If the current paper/result state is still unclear, open `intake-audit` first before continuing the rebuttal workflow.
Before launching any new supplementary experiment, read those structured `evaluation_summary` blocks first so the rebuttal plan starts from the already-recorded evidence state rather than from raw narrative memory.

## Core outputs

The rebuttal pass should usually leave behind:

- `paper/rebuttal/review_matrix.md`
- `paper/rebuttal/action_plan.md`
- `paper/rebuttal/response_letter.md`
- `paper/rebuttal/text_deltas.md`
- `paper/rebuttal/evidence_update.md`

Use the templates in `references/` when needed:

- `review-matrix-template.md`
- `action-plan-template.md`
- `response-letter-template.md`
- `evidence-update-template.md`

## Atomic reviewer-item contract

Before any rebuttal experiment or major rewrite, normalize reviewer pressure into stable atomic items.

For each item:

- give it a stable id such as `R1-C1`, `R1-C2`, `R2-C1`
- preserve the reviewer wording as faithfully as possible
  - if the original text is too long or noisy, controlled head/tail ellipsis is allowed
  - do not rewrite the reviewer's meaning
- record whether the item is explicit or inferred
  - inferred items are allowed only when comments are incomplete or the user gave only rough prose
  - mark them clearly as inferred
- attach at least one evidence anchor:
  - manuscript location
  - existing result / table / figure
  - literature comparison note
  - or `missing_evidence` if the gap is still real
- decide one primary route:
  - `text_revision`
  - `evidence_repackaging`
  - `literature_positioning`
  - `baseline_recovery`
  - `supplementary_experiment`
  - `claim_downgrade`
  - `explicit_limitation`

Do not let one vague reviewer paragraph remain as one vague work item.
The point is to make downstream routing auditable.

## Comment classes

Every substantive reviewer comment should be classified as one or more of:

- `editorial`
  - wording, organization, typo, presentation
- `text_only`
  - explanation gap, related-work gap, clarity gap, missing discussion
- `evidence_gap`
  - the paper is missing a table, figure, comparison, or stronger analysis already latent in existing results
- `experiment_gap`
  - genuinely new supplementary runs are required
- `claim_scope`
  - the current claim is too broad and must be narrowed or downgraded
- `cannot_fully_address`
  - the request is currently infeasible, out of scope, or impossible within the real evidence budget

Do not blur these categories.
The whole point is to route work correctly.

Useful stance values for draft replies:

- `agree`
- `partially_agree`
- `clarify`
- `respectful_disagree`

Useful concern-type labels when the simple class list is not enough:

- `non_experimental`
- `experimental`
- `writing_logic`
- `scope_novelty`

## Workflow

### 1. Normalize the review package

Collect reviewer inputs into a durable matrix using `references/review-matrix-template.md`.

For each comment, record:

- reviewer id if known
- original comment summary
- class
- severity
- whether it affects:
  - acceptance risk
  - the main claim
  - only presentation
- recommended action
- stable item id such as `R1-C1`
- reviewer wording or a source-faithful clipped quote
- whether the item is explicit or inferred
- preliminary route:
  - text
  - literature
  - baseline
  - experiment
  - claim scope
  - limitation

If the user gave only rough prose rather than a structured review package, build that matrix yourself before planning experiments or edits.

### 2. Decide what must change

For each reviewer issue, decide whether the right answer is:

- explanation only
- existing evidence repackaging
- new supplementary experiment
- claim downgrade
- explicit limitation response

Then write one durable rebuttal plan in `paper/rebuttal/action_plan.md`.
That plan should explicitly include the analysis-experiment TODO list for reviewer-linked follow-up work.

The action plan should be the main thinking draft before execution.
For each serious item, record:

- item id
- concern type
- stance
- chosen route
- why that route is sufficient
- what evidence already exists
- what is still missing

For experimental items, do not stop at “run experiment”.
Write at least:

- hypothesis
- minimal success criterion
- required metric(s)
- MVP plan
- Enhanced plan
- fallback response wording if the experiment cannot be completed in time

For novelty / comparison / positioning complaints, do not default to experiments.
First decide whether the issue is better answered by a focused literature audit and clearer paper positioning.

### 3. Route experiments only when genuinely needed

If one or more comments truly require new runs:

1. if the complaint is mainly about novelty, related work, or scope positioning, open `scout` first instead of treating it as an experiment request
2. if the complaint requires an extra comparator baseline that is not yet available, open `baseline` first
3. record a `decision(action='launch_analysis_campaign')`
4. open `analysis-campaign`
5. create a campaign where each slice is tied to one or more reviewer concerns
6. after each slice finishes, immediately `artifact.record_analysis_slice(...)`
7. update the review matrix and evidence update note

Do not launch a free-floating ablation batch.
Every supplementary run should answer a named reviewer issue.
Every slice should reference one or more stable reviewer item ids.
After each completed reviewer-linked slice, record the result, the implication for the manuscript, and the concrete modification advice in `paper/rebuttal/evidence_update.md`.
Use the same shared supplementary-experiment protocol as ordinary analysis work; do not invent a rebuttal-only experiment system.
If ids or refs are unclear, recover them first with `artifact.resolve_runtime_refs(...)`, `artifact.get_analysis_campaign(...)`, or `artifact.list_paper_outlines(...)`.

### 4. Route manuscript changes explicitly

If the paper text, structure, or claim scope must change:

- open `write`
- revise the selected outline when the narrative or claim map changed materially
- keep `text_deltas.md` explicit:
  - section
  - old claim / weakness
  - new wording or new scope
  - evidence basis
- keep the revision reader-first:
  - direct answer to reviewer concern
  - manuscript change
  - evidence basis
  - remaining limitation if still unresolved

If a reviewer request forces a narrower story, revise the outline before polishing prose.

### 5. Assemble the response letter

Use `references/response-letter-template.md` when helpful.

The response should be:

- professional
- calm
- specific
- evidence-backed
- non-defensive

Good response structure:

- short appreciation / acknowledgement
- direct answer to the reviewer concern
- keep stable item ids visible when helpful
- restate reviewer wording faithfully before answering
- what changed:
  - experiment
  - table / figure
  - text section
  - claim scope
- if not fully addressed, why not and what honest limitation remains

If details are still genuinely unknown, use explicit placeholders such as `[[AUTHOR TO FILL]]` rather than inventing specifics.

Avoid:

- empty politeness
- evasive wording
- pretending a limitation is solved when it is only reframed

### 6. Final revision handoff

When the rebuttal package is durably ready:

- update the review matrix statuses
- update the response letter
- update text deltas and evidence update
- if the revised manuscript bundle is genuinely ready, route through `artifact.submit_paper_bundle(...)`

If a combined rebuttal note is useful, make sure the total package still covers:

- overview and revision strategy
- draft responses to reviewers
- point-to-point triage
- experiment action plan
- manuscript revision suggestions
- evidence mapping
- unresolved items and risk notes

## Companion skill routing

Open additional skills only when the rebuttal workflow requires them:

- `intake-audit`
  - when the current draft/result/review state is still unclear
- `scout`
  - when reviewer pressure is mainly about novelty, positioning, related work, or comparison framing
- `baseline`
  - when the rebuttal requires an extra comparator baseline that is not yet trusted
- `analysis-campaign`
  - when reviewer concerns require supplementary runs
- `write`
  - when claims, outline, sections, or figures must be revised
- `figure-polish`
  - when a new figure or revised figure will be part of the rebuttal or manuscript update
- `decision`
  - when the rebuttal route is non-trivial, for example:
    - whether to spend budget on a hard reviewer request
    - whether to downgrade the claim
    - whether to treat one concern as appendix-only

## Artifact routing guidance

Use these tools deliberately:

- `artifact.record(kind='decision', ...)`
  - route choice, claim downgrade, literature-audit launch, baseline-recovery launch, supplementary-experiment launch, rebuttal completion recommendation
- `artifact.create_analysis_campaign(...)`
  - multi-slice reviewer-driven supplementary work
- `artifact.record_analysis_slice(...)`
  - one completed reviewer-facing supplementary slice
- `artifact.submit_paper_outline(mode='revise', ...)`
  - when review changes the active paper blueprint
- `artifact.submit_paper_bundle(...)`
  - when the revised manuscript package is durably ready
- `artifact.interact(...)`
  - user-visible progress and rebuttal milestones

## Memory discipline

Stage-start requirement:

- run `memory.list_recent(scope='quest', limit=5)`
- run at least one `memory.search(...)` for:
  - paper title
  - main method name
  - reviewer / rebuttal / revision
  - key criticized claim or figure

Stage-end requirement:

- if the rebuttal pass produced a durable lesson, claim downgrade, or reviewer-driven route change, write at least one `memory.write(...)`

Useful tags include:

- `stage:rebuttal`
- `type:review-matrix`
- `type:claim-downgrade`
- `type:revision-lesson`
- `type:reviewer-request`

## Success condition

`rebuttal` is successful when:

- reviewer concerns are normalized into a durable matrix
- each serious concern has an explicit action class
- supplementary experiments, if needed, are routed cleanly
- manuscript deltas are explicit
- the response letter is evidence-backed and honest

The goal is not just “write a nicer response”.
The goal is to convert review pressure into a durable, auditable revision workflow.
