---
name: rebuttal
description: Use when a quest already has a paper, draft, or review package and the task is to map reviewer feedback into experiments, manuscript deltas, and a durable rebuttal / revision response.
skill_role: companion
---

# Rebuttal

Use this skill when the quest is in review, revision, or rebuttal mode.

This is not the same as ordinary `write`.
The task is no longer “draft the paper from evidence”.
The task is “respond to concrete reviewer pressure with the smallest honest set of experiments, text changes, claim adjustments, and response artifacts”.

## Interaction discipline

- Follow the shared interaction contract injected by the system prompt.
- For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
- Message templates are references only. Adapt to the actual context and vary wording so updates feel natural and non-robotic.
- If a threaded user reply arrives, interpret it relative to the latest rebuttal progress update before assuming the task changed completely.
- When the rebuttal plan, the main supplementary-evidence package, or the final response bundle becomes durable, send one richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` update that says what reviewer concerns are now addressed, what still remains open, and what happens next.
- Hard execution rule: if this stage needs terminal work such as manuscript builds, scripted checks, Git inspection, or reviewer-linked experiment launches, every such command must go through `bash_exec`.

## Three-layer todo contract

- keep quest-root `plan.md` as the top-level research map and reviewer-driven route surface
- if rebuttal work is multi-step, use workspace `PLAN.md` as the current rebuttal-node contract and `CHECKLIST.md` as the execution frontier
- when reviewer-driven follow-up becomes clear, update quest-root `plan.md` so the next edge to analysis, write, or decision is explicit instead of living only in the rebuttal packet

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
- If `startup_contract.baseline_execution_policy` is present, honor it:
  - `must_reproduce_or_verify`
    - verify or recover the rebuttal-critical baseline/comparator before reviewer-linked follow-up work
  - `reuse_existing_only`
    - trust the current baseline/results unless you find concrete inconsistency, corruption, or missing-evidence problems
  - `skip_unless_blocking`
    - do not spend time rerunning baselines unless a named reviewer item truly depends on a missing comparator
- If `startup_contract.manuscript_edit_mode = latex_required`, treat the provided LaTeX tree or `paper/latex/` as the preferred writing surface when manuscript revision is needed.
- If LaTeX source is unavailable while `latex_required` is requested, do not pretend the manuscript was edited; produce LaTeX-ready replacement text and an explicit blocker note instead.
- Accept review inputs from URLs, local file paths, local directories, or current-turn attachments; do not assume the review packet must already be neatly structured.

## Primary inputs

Use, in roughly this order:

- the current paper or draft
- the selected outline if one exists
- review comments, meta-review, or editor letter
- current-turn attachments and user-provided local paths / directories / URLs for the manuscript or review packet
- the six-field `evaluation_summary` blocks from recent main experiments and analysis slices
- recent main and analysis experiment results
- prior decision and writing memory
- existing figures, tables, and claim-evidence maps

If the current paper/result state is still unclear, open `intake-audit` first before continuing the rebuttal workflow.
Before launching any new supplementary experiment, read those structured `evaluation_summary` blocks first so the rebuttal plan starts from the already-recorded evidence state rather than from raw narrative memory.
If the user provided manuscript files or review-packet files directly, first normalize them into durable quest-visible paths under `paper/` or `paper/rebuttal/input/` before planning reviewer-linked experiments or draft replies.

## Core outputs

The rebuttal pass should usually leave behind:

- `paper/rebuttal/review_matrix.md`
- `paper/rebuttal/action_plan.md`
- `paper/rebuttal/response_letter.md`
- `paper/rebuttal/text_deltas.md`
- `paper/rebuttal/evidence_update.md`
- `paper/paper_experiment_matrix.md` when reviewer concerns materially change the paper experiment plan
- `paper/paper_experiment_matrix.json` when reviewer concerns materially change the paper experiment plan

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
If reviewer concerns materially change the paper's experiment story, also create or revise `paper/paper_experiment_matrix.*` so the rebuttal experiment package stays consistent with the paper-facing plan rather than drifting into a reviewer-only side list.

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

When a reviewer concern really does imply experimental follow-up, map it into the same paper experiment taxonomy used by the writing line:

- `component_ablation`
- `sensitivity`
- `robustness`
- `efficiency_cost`
- `highlight_validation`
- `failure_boundary`
- `case_study_optional`

Case study remains optional unless the reviewer concern is specifically qualitative and cannot be addressed better with quantitative evidence.

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
Every rebuttal-linked slice should also reference the corresponding `exp_id` from `paper/paper_experiment_matrix.*` when that matrix exists.
After each completed reviewer-linked slice, record the result, the implication for the manuscript, and the concrete modification advice in `paper/rebuttal/evidence_update.md`.
Use the same shared supplementary-experiment protocol as ordinary analysis work; do not invent a rebuttal-only experiment system.
If ids or refs are unclear, recover them first with `artifact.resolve_runtime_refs(...)`, `artifact.get_analysis_campaign(...)`, or `artifact.list_paper_outlines(...)`.
After each completed, excluded, or blocked reviewer-linked slice:

- reopen `paper/paper_experiment_matrix.*`
- update the affected `exp_id`
- update whether the result now belongs in main text, appendix, or omission
- update which reviewer items are now fully answered

Do not finalize the rebuttal package while reviewer-critical and currently feasible matrix rows remain unresolved without an explicit blocker note.

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

Before treating the response letter as final:

- first complete every feasible reviewer-linked experiment or analysis slice that the current plan marked as necessary
- ensure the necessary rows in `paper/paper_experiment_matrix.*` have been refreshed after those runs
- use real completed experiment results directly in the reply wherever the concern is genuinely experimental
- for non-experimental items, do not wait for unnecessary experiments; answer as strongly as the current manuscript, literature, and analysis already allow
- if one experimental item cannot be completed in time, keep the reply honest and explicit about the remaining limitation or fallback wording

The response should be:

- professional
- calm
- specific
- evidence-backed
- non-defensive

Good response structure:

- short appreciation / acknowledgement
- overall response that summarizes the revision strategy and the strongest strengths acknowledged across reviewers
- strengths recognized across reviewers
- direct answer to the reviewer concern
- keep stable item ids visible when helpful
- restate reviewer wording faithfully before answering
- what changed:
  - experiment
  - table / figure
  - text section
  - claim scope
- if not fully addressed, why not and what honest limitation remains

Drafting style rules for the actual author reply body:

- Treat `response_letter.md` as rebuttal-ready author text, not as internal coaching notes.
- Write in a calm, direct, precise author voice.
- Sound like authors clarifying the record, not authors asking for approval.
- Brief professional courtesy is allowed, but keep it short and move to substance immediately.
- Avoid sycophancy, flattery, excessive gratitude, or approval-seeking language.
- Do not default to conceding fault.
- Use selective concede, selective clarify, and selective defend.
- Answer the reviewer concern directly in the first 1 to 2 sentences.
- For non-experimental items, reduce reviewer uncertainty as much as the real evidence allows; the goal is to make a score improvement reasonable for an honest reviewer, not to persuade through rhetoric alone.
- Write strongly enough that a neutral reviewer or AC can judge the concern substantially addressed from the rebuttal text alone.
- After the literal answer, address the underlying doubt about validity, novelty, scope, fairness, or completeness.
- If the answer already exists in the manuscript, restate it in the rebuttal and then point to the manuscript change; do not only say “we will clarify”.
- If the issue is about wording, interpretation, or claim strength, include the revised sentence or close paraphrase that should appear in the manuscript.
- Keep the main response body for each item as 1 to 2 full paragraphs of polished prose.
- Do not use bullets, numbered lists, bold labels, or checklist fragments inside the actual response paragraphs.
- Do not narrate rebuttal strategy inside the author reply.
- Do not rely on future edits alone when you can already give the clarification, argument, or wording now.
- When pushing back, lead with evidence, scope, or feasibility constraints before intuition.
- If `startup_contract.manuscript_edit_mode = latex_required`, keep manuscript-facing replacement text LaTeX-ready.

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

- overall response
- strengths recognized across reviewers
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

- `artifact.record(payload={'kind': 'decision', ...})`
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
- the final package contains both:
  - reviewer-specific replies
  - one overall response that makes the paper strengths, the main resolved concerns, and the remaining limitations legible to a neutral reader or AC

The goal is not just “write a nicer response”.
The goal is to convert review pressure into a durable, auditable revision workflow.
