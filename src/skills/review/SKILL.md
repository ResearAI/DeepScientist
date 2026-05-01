---
name: review
description: Use when a draft, paper, or paper-like report is substantial enough for an independent skeptical audit before finalization, rebuttal, or revision routing.
skill_role: companion
---

# Review

Use this skill when the quest already has a substantial draft, paper, or paper-like report and now needs an independent, skeptical, evidence-grounded audit.
The goal is to reduce revision ambiguity, not to sound harsh for its own sake.

This is not the same as ordinary `write`.
It is also not the same as `rebuttal`.

- `write` turns accepted evidence into a narrative.
- `review` audits that narrative like a harsh but constructive expert reviewer.
- `rebuttal` responds to concrete external reviewer pressure that already exists.

## Interaction discipline

- Follow the shared interaction contract injected by the system prompt.
- For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
- When the review report, revision plan, or follow-up experiment TODO list becomes durable, send a richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` update that says what the main risks are, what should be fixed next, and whether the next route is writing, experiment, or claim downgrade.
- Hard execution rule: if this stage needs terminal work such as document builds, scripted checks, Git inspection, or file inspection, every such command must go through `bash_exec`.

## Three-layer todo contract

- treat quest-root `plan.md` as the top-level research map whose next anchor must become explicit after the review
- if the review pass is multi-step, use workspace `PLAN.md` as the current review-node contract and `CHECKLIST.md` as the execution frontier
- treat `paper/review/experiment_todo.md` as a review-facing frontier subset, not as a replacement for the quest-level map

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
Do not accept structural green lights as paper-quality proof. Coverage, compile success, and file counts must still survive a skeptical claim/evidence/reviewer-risk audit.
Apply the publishability stop-loss rule during review: when novelty, evidence sufficiency, or reader value has collapsed beyond reasonable claim narrowing, the correct recommendation is `decision` with `stop` or `branch`, with any narrowed non-paper objective recorded as the next direction, not another cosmetic revision pass. If recommending `stop` because paper quality is too low, ask the user to confirm before ending the paper objective. Consider user publication, scope, cost, or non-paper preferences, and ask for a user decision when those preferences are unclear and would change the recommendation.

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
- Do not recommend continued paper revision when the review finds a fatal publishability or value collapse; make the stop/branch route explicit.
- Do not execute a stop route for a low-quality paper judgment without user confirmation; present the evidence, the stop recommendation, and any branch or narrowed non-paper alternative first.
- Do not silently override a user's stated paper, report, or non-paper preference; consider it in the route recommendation, or ask when it is unclear.
- If novelty or positioning is uncertain, treat that as a literature-audit question first, not an automatic experiment request.
- If a claim is too broad for the evidence, prefer narrowing or downgrading the claim over defending it with style.
- If `startup_contract.review_followup_policy` is present, honor it:
  - `audit_only`
    - stop after durable review artifacts and a clear route recommendation
  - `auto_execute_followups`
    - do not stop at the audit if the next route is already clear; continue into the required experiments and manuscript deltas
  - `user_gated_followups`
    - finish the audit first, then package the next expensive follow-up step into one structured decision
- If `startup_contract.manuscript_edit_mode = latex_required`, treat the provided LaTeX tree or `paper/latex/` as the writing surface when manuscript revision is needed.
- If LaTeX source is unavailable while `latex_required` is requested, do not pretend the manuscript was edited; produce LaTeX-ready replacement text and an explicit blocker note instead.
- Accept manuscript and review inputs from URLs, local file paths, local directories, or current-turn attachments; do not assume the draft is already perfectly normalized.

## Primary inputs

Use, in roughly this order:

- `artifact.validate_manuscript_coverage(detail='full')` for paper bundles, memos, or alleged near-final manuscripts
- the current paper or report draft
- the selected outline if one exists
- the claim-evidence map if one exists
- the six-field `evaluation_summary` blocks from recent main experiments and analysis slices
- recent main and analysis experiment results
- figures, tables, and captions
- current-turn attachments and user-provided local paths / directories / URLs for the manuscript bundle or review packet
- prior self-review or reviewer-first notes as low-trust auxiliary input
- nearby papers and high-level accepted papers found through current literature search, not only remembered examples

If the draft/result state is still unclear, open `intake-audit` first before continuing the review workflow.
Before proposing extra experiments, read those structured `evaluation_summary` blocks first so you do not request work that the recorded evidence already resolved.
If the user provided draft files or manuscript bundles directly, first normalize them into durable quest-visible paths before planning experiments or section-level revisions.

## Core outputs

The review pass should usually leave behind:

- `paper/review/review.md`
- `paper/review/revision_log.md`
- `paper/review/experiment_todo.md`
- `paper/paper_experiment_matrix.md` when more evidence is still needed
- `paper/paper_experiment_matrix.json` when more evidence is still needed

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
- manuscript language hygiene and provenance leakage
- figure / table usefulness
- full-paper style, pacing, and section-level argument quality relative to strong accepted papers
- experiment package completeness relative to nearby high-level papers
- submission readiness

## Workflow

### 1. Plan the audit

Before writing the review itself, make the audit explicit.

Identify:

- whether the package is only `draft_checkpoint`, a reviewable manuscript, or truly submission-ready
- 1 to 3 core claims such as `C1`, `C2`, `C3`
- the strongest current evidence
- the weakest current evidence
- the top 3 likely rejection reasons
- the ready experiment/analysis group count versus the current target, including any user-specified target such as 4-8 analyses
- what the closest high-quality paper comparators are and which parts of their writing / logic / experiment package should be used as review standards
- whether manuscript text leaks user requirements, agent actions, route/control state, branch/worktree names, tool recommendations, TODOs, or raw implementation shorthand
- whether `artifact.validate_academic_outline(detail='full')` and `artifact.validate_manuscript_language(detail='full')` pass when a selected outline or draft exists
- whether the likely next route is:
  - text revision
  - literature / novelty audit
  - baseline recovery
  - supplementary experiment
  - claim downgrade

### 2. Run a paper-quality literature benchmark

Before calling a substantial manuscript strong, run a current literature/style benchmark unless the review scope is explicitly local-only.

Search for nearby high-quality papers using the best available current source:

- Prefer DeepXiv or OpenAlex when configured.
- Use web search when needed for venue status, accepted-paper pages, PDFs, proceedings, journal pages, or recent related work.
- Include high-level exemplars when relevant: ICLR, ICML, NeurIPS, CVPR, ACL, EMNLP, KDD, SIGIR, AAAI, IJCAI, Nature/Science family, or Q1 journal papers in the field.
- Prefer accepted papers, proceedings pages, journal pages, arXiv PDFs with accepted-version metadata, and official conference / journal records over blog posts or low-trust summaries.

Build a compact comparison set, usually 3-8 papers:

- 1-3 closest technical neighbors
- 1-3 strong writing / story exemplars from top venues
- 1-2 experiment-package exemplars when the manuscript's evaluation design is uncertain

For each comparator, record title, venue/source, why it is relevant, and what it teaches about:

- abstract and introduction framing
- problem -> gap -> method -> evidence logic
- method explanation and reader onboarding
- experiment design, ablations, robustness, baselines, and limitations
- figure/table roles and result narrative
- related-work positioning and claim boundaries

Do not request new experiments just to answer a literature-positioning question. First decide whether the fix is writing, positioning, claim narrowing, or genuinely missing evidence.

### 3. Write a reliable review report

Write `paper/review/review.md` using `references/review-report-template.md`.

The review should be:

- independent
- skeptical but constructive
- technically specific
- reader-aware
- evidence-grounded

Never write "no weaknesses", "no key issues", or equivalent closure language unless the review has first listed the main rejection routes and shown why each is fixed, downgraded, or out of scope.

At minimum, the review report should cover:

- summary
- strengths
- weaknesses
- key issues
- actionable suggestions
- storyline / outline advice
- priority revision plan
- experiment inventory and research experiment plan
- analysis-count sufficiency and whether the count is real rather than inflated by duplicate/stale rows
- novelty verification and related-work matrix
- high-level paper comparison matrix covering writing, logic, full-paper organization, style, figures/tables, and experiment package gaps
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
- one copy-ready replacement sentence / paragraph when feasible
- one LaTeX-ready replacement block when `startup_contract.manuscript_edit_mode = latex_required`

### 5. Produce the follow-up experiment TODO list

Only if more evidence is truly needed, write `paper/review/experiment_todo.md` using `references/experiment-todo-template.md`.

Before creating TODOs, separate three blocker types:

- analysis blockers: missing, failed, unmapped, or legacy-method evidence needed for a claim
- manuscript blockers: missing sections, missing figures/tables, weak narrative, or stale claim-evidence mapping
- language/provenance blockers: user/operator/agent wording, restart or route-management phrasing, tool-promotion captions, TODOs, or raw endpoint/batch shorthand in paper-facing text
- submission blockers: missing PDF, checklist, artifact availability, camera-ready cleanup, or user approval

Do not turn manuscript/submission blockers into fake experiments or mark a `draft_checkpoint_ready` package final.
Do not accept a draft as reviewable while it still reads like a run log, control memo, or user-request transcript.

When the paper still lacks experimental support, also create or revise:

- `paper/paper_experiment_matrix.md`
- `paper/paper_experiment_matrix.json`

Treat the matrix as the paper-facing master plan and `paper/review/experiment_todo.md` as only the current execution frontier or review-facing subset.

Each TODO item should include:

- the review issue it answers
- the matrix exp id
- the corresponding `exp_id` in the paper experiment matrix
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
The matrix should be broader than the TODO list and should classify the full paper-facing experiment space, not just analysis work.
When building or revising that matrix, explicitly consider:

- main comparison packaging or extension
- component ablations
- sensitivity / hyperparameter checks
- robustness checks
- efficiency / cost / latency / token-overhead checks when relevant
- highlight-validation experiments that test the likely strengths of the method
- limitation-boundary analyses
- case study rows as optional rather than mandatory evidence

Do not assume the paper only needs “analysis experiments”.
Do not assume case studies belong in the required set.
If efficiency or cost could become a reviewer-facing strength or concern, put that into the matrix explicitly.
If local serving, batch size, ports, cache reuse, or command shape are only reproducibility details, route them to appendix/protocol rows rather than main-text claims.

For the matrix, each row should usually record:

- `exp_id`
- `tier`
- `experiment_type`
- `status`
- `feasibility_now`
- `claim_ids`
- `highlight_ids`
- `research_question`
- `hypothesis`
- `comparators`
- `metrics`
- `minimal_success_criterion`
- `paper_placement`
- `promotion_rule`
- `next_action`

The matrix should also keep a short `highlight hypotheses` block.
Do not rely on prose intuition for the method's best selling point; if a likely highlight matters, it should have a corresponding validation row in the matrix.

Before treating the experiments section as stable, require that every currently feasible matrix row that is not merely `optional` or `dropped` is either:

- completed
- analyzed
- excluded with a real reason
- or blocked with a real reason

Before treating the manuscript prose as stable, scan titles, abstract, captions, method setup, conclusion, and section openings for process language. Rewrite or block if they mention user requests, agent decisions, worktrees, branches, artifact ids, "paper restart", "paper should", "remaining work", tool recommendations, or shorthand such as `64 + 64`.

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

### 7. Auto follow-up execution contract

When `startup_contract.review_followup_policy = auto_execute_followups`:

- treat the review as a gate, not as the endpoint
- immediately turn the accepted follow-up route into action:
  - `analysis-campaign`
    - when new evidence is truly required
  - `baseline`
    - when a missing comparator baseline blocks fair review
  - `write`
    - when the issues are mostly text, outline, claim-scope, figure, or framing revisions
- after each completed follow-up step, update:
  - `paper/review/revision_log.md`
  - `paper/review/experiment_todo.md`
  - the draft or manuscript-facing revision package
- only treat the review line as truly closed after the follow-up route has either completed or been downgraded / blocked explicitly

When `startup_contract.review_followup_policy = user_gated_followups`:

- stop after the durable audit artifacts
- turn the next expensive follow-up package into one structured decision instead of continuing silently

When `startup_contract.review_followup_policy = audit_only`:

- stop after the durable audit artifacts and route recommendation

### 8. Manuscript revision delivery contract

If manuscript revision is required, make the delta explicit:

- section
- old claim / weakness
- new wording
- evidence basis
- remaining limitation

If `startup_contract.manuscript_edit_mode = copy_ready_text`:

- provide copy-ready replacement wording in `paper/review/revision_log.md` or a nearby revision note
- keep the wording directly usable by the user or downstream `write`

If `startup_contract.manuscript_edit_mode = latex_required`:

- prefer editing the actual LaTeX sources when they are available
- otherwise provide LaTeX-ready replacement text blocks with explicit insertion targets
- preserve labels, citations, figure/table refs, and section structure in the suggested replacements

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

- `artifact.record(payload={'kind': 'decision', ...})`
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

A good review pass leaves fewer plausible next moves, not more.
