---
name: write
description: Use when a quest has enough evidence to draft or refine a paper, report, or research summary without inventing missing support.
skill_role: stage
---
# Write

## Match Signals
- Use when an accepted baseline and at least one meaningful result already exist, and the main blocker is now drafting, revising, bundling, or tightening a paper/report.
- Strong triggers: draft a paper/report, revise a section, synchronize claim-evidence support, prepare a paper bundle, or upgrade an existing draft into a stronger conference submission.
- If the task is specifically "upgrade an existing draft toward top-conference / oral quality", use the `Draft To Top Conference Oral` section below.
- Do not use when the evidence base is still weak or unstable, the main need is new experiments / baselines / ideation, or the request is only literature search.

## One-Sentence Summary
- Refresh the paper contract first, then draft section-by-section from durable evidence; if evidence, figures, or citations are not ready, repair or route back instead of writing around the gap.

## Pre-write Revision Strategy Gate

Before editing a manuscript, first produce a concrete revision strategy from the current evidence state.
Do not begin polishing prose until the strategy separates:

- evidence gaps: require new analysis, rerun, or claim downgrade
- manuscript-mapping gaps: completed results missing from main text, table, figure, or appendix
- unsupported writing: claims present in the draft without durable result artifacts
- narrative / positioning gaps: weak framing, novelty boundary, contribution logic
- citation gaps: too few or weak references for the claimed scope
- metadata drift: matrix, ledger, outline, figures, tables, and manuscript disagree

For each issue, choose exactly one action:

- run or request analysis
- downgrade or remove the claim
- add result to main text
- move result to appendix with a clear bridge
- add or repair a table/figure
- add verified citations
- repair the paper contract before writing
- route to review / decision instead of writing

Never make an unsupported claim sound more convincing.
If evidence is missing, either obtain evidence, narrow the claim, or mark the blocker.

## Workflow
1. Refresh control state first.
   Run `memory.list_recent(scope='quest', limit=5)` plus one writing-relevant `memory.search(...)`. If restart context is unclear, use `artifact.get_quest_state(detail='summary')`, `artifact.read_quest_documents(...)`, or `artifact.get_conversation_context(...)`.
2. Lock the paper contract before heavy prose.
   Keep `paper/selected_outline.json`, `paper/evidence_ledger.json`, and `paper/paper_experiment_matrix.md` or `.json` aligned. Use `artifact.get_paper_contract(detail='full')` as the default paper-reading surface when section rows, experiment rows, or analysis rows matter. Use `artifact.get_paper_contract_health(detail='full')` when outline state, experiment rows, or evidence ownership may be stale. Use `artifact.submit_paper_outline(mode='candidate'|'select'|'revise', ...)` instead of leaving outline choice only in prose.
   When several paper shapes are plausible, record one or more outline candidates with `artifact.submit_paper_outline(mode='candidate', ...)`, then select or revise explicitly with `artifact.submit_paper_outline(mode='select'|'revise', ...)`; do not force extra outline rounds once the selected outline is good enough for the current writing job.
3. Validate the outline before drafting.
   Run `artifact.validate_academic_outline(detail='full')`. If it fails, use `paper-outline` or `artifact.submit_paper_outline(mode='revise', ...)` to repair the paper idea, claims, evidence boundaries, and analysis plan before prose work. When it passes, run `artifact.compile_outline_to_writing_plan(detail='full')` and draft from those jobs.
4. Sort source material before drafting.
   Ask: is this a claim, an experiment setting, a reproducibility detail, implementation plumbing, artifact history, or a user/operator instruction? Claims and experiment settings may become manuscript text. Reproducibility details usually go to appendix. Artifact history and user/operator instructions should not appear in the manuscript.
5. Refresh literature and citation truth.
   Run `breadth -> shortlist -> depth`. Use DeepXiv or OpenAlex for discovery when available, then retrieve BibTeX from DOI or arXiv, not from memory. Keep `paper/references.bib` machine-usable and audit it before bundle submission.
   If DeepXiv is declared available by the system prompt, prefer it for paper-centric discovery and shortlist triage before broad web search when it can answer the question directly. If DeepXiv is declared unavailable, do not try to force it; stay on the legacy route. Use `artifact.arxiv(paper_id=..., full_text=False)` for actual arXiv paper reads before escalating to full text.
6. Plan displays before prose.
   If a section needs a paper-facing measured figure, use `paper-plot` first. Use `figure-polish` only after a durable first-pass render exists. Sync resulting figure paths and takeaways back into `paper/evidence_ledger.json`, `paper/paper_experiment_matrix.md`, and the draft.
7. Route Nature companion work by paper surface.
   Open a `nature-*` skill only after the current section job, evidence rows, and unresolved fields are known. Use the companion skill to produce a bounded section/figure/deck deliverable, then return to `write` to integrate it into the draft, evidence ledger, figure/table catalog, references, and bundle status.
8. Draft by section jobs, not one long stream.
   Write introduction / related work / method / experiments / analysis / conclusion as separate jobs. Write the abstract late, after evidence order and section roles stabilize. For oral-grade upgrades, follow the `Draft To Top Conference Oral` section below.
9. Validate before output and route if needed.
   Refresh claim-evidence, packaging, appendix bridges, `artifact.validate_manuscript_language(detail='full')`, and `artifact.validate_manuscript_coverage(detail='full')`. A short memo is only `artifact.submit_paper_bundle(package_type='draft_checkpoint', ...)`; use `submission_package` only when `submission_ready=true`.

## Paper Quality Reminder

Do not let structural readiness stand in for paper quality.

- Compile success, section count, figure/table count, and `draft_checkpoint_ready` mean only that a package exists.
- A mature empirical draft needs a reader-facing thesis, central insight, scoped claims, novelty boundary, reviewer objections, and a mapped analysis plan from `paper-outline`.
- Before calling a full manuscript strong, check the actual ready experiment/analysis group count from `artifact.validate_manuscript_coverage(detail='full')`.
- Normally expect 5-10 ready paper-facing experiment/analysis groups total; if the user asked for a concrete count such as 4-8 analyses, treat that as the active tracked target.
- If the count is below the target, either route to `analysis-campaign`, write an explicit analysis-budget waiver that downgrades the paper scope, or narrow the claims. Do not hide the shortage with prose.
- If duplicate item ids, stale outline refs, or pending main-text rows inflate the count, repair the paper contract before writing claims from those rows.
- Apply the publishability stop-loss rule: if the current evidence, novelty boundary, or reader value cannot support a defensible paper after reasonable claim narrowing, stop drafting and route to `decision` for a recommended `stop` or `branch`; record any narrowed non-paper objective as the next direction. If the recommended action is `stop` because paper quality is too low, ask the user to confirm before ending the paper objective. Consider user publication, scope, cost, or non-paper preferences before routing, and ask when the preference would change the route. Do not use polished prose to keep an unpublishable paper line alive.

## Tool Use
- `artifact.get_paper_contract_health(detail='full')`:
  use when a weak section may actually be caused by stale outline state, unresolved experiment rows, or unclear evidence ownership.
- `artifact.get_paper_contract(detail='full')`:
  use by default before drafting any section, table, or analysis prose that depends on concrete main-experiment rows, analysis rows, or section-level `result_table` content.
- `artifact.validate_manuscript_coverage(detail='full')`:
  use before bundle submission or finalize; it checks sections, displays, ready analysis groups, PDF, and checklist state.
- `artifact.validate_academic_outline(detail='full')`:
  use before serious drafting; it checks whether the outline has a paper idea, scoped claims, evidence boundaries, method, evaluation plan, and enough planned analyses.
- `artifact.compile_outline_to_writing_plan(detail='full')`:
  use after the outline is valid; it turns the outline into section-level writing jobs.
- `artifact.validate_manuscript_language(detail='full')`:
  use after major prose edits and before submission; it catches route/user/worktree/port/batch wording that should not be in main text.
- `artifact.get_quest_state(detail='summary')`, `artifact.read_quest_documents(...)`, `artifact.get_conversation_context(...)`:
  use when restart context is unclear, when exact durable wording matters, or when you need file truth instead of chat recollection.
- `artifact.submit_paper_outline(mode='candidate'|'select'|'revise', ...)`:
  use when outline choice or outline repair becomes durable enough that the paper line should follow it.
- `artifact.create_analysis_campaign(...)`:
  use only when a real paper-facing evidence gap needs follow-up analysis; do not use it for prose cleanup, citation chores, or generic "improve the paper" tasks.
- `artifact.submit_paper_bundle(...)`:
  use explicit `package_type`: `draft_checkpoint`, `review_package`, or `submission_package` only after coverage is submission-ready.
- `artifact.interact(...)` or other durable artifact updates:
  use when the writing pass materially changes paper status, route choice, or bundle readiness and the change should survive beyond chat.
- `bash_exec(...)`:
  use for any real shell/CLI work such as LaTeX compile, bibliography checks, `rg`/`find`/`ls`, figure-generation scripts, PDF render/proofing, git inspection, or reproducibility checks. Do not describe command plans as if they ran; run them through `bash_exec` when execution is actually needed.
- `memory.list_recent(...)` and `memory.search(...)`:
  use at the start of substantial writing passes, before route changes, and before repeating search or drafting patterns that may already have reusable lessons.
- `memory.write(...)`:
  use only for reusable lessons such as citation retrieval rules, packaging traps, figure-integration lessons, or section-rewrite heuristics; do not store one-off draft text, transient wording, or current-section notes that should live in files.

## Interaction Discipline

Follow the shared interaction contract injected by the system prompt.
For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.

## AVOID / Pitfalls
- Do not start with background explanation or overview prose; start with contract health, section job, and evidence state.
- Do not keep drafting while outline, evidence ledger, or experiment matrix are stale.
- Do not treat `paper_contract_health` as a substitute for reading the actual section `result_table`, evidence rows, or experiment-matrix rows.
- Do not draft around missing evidence, unstable baselines, or unresolved non-optional experiment rows.
- Do not hand-write BibTeX, citations, metrics, or method details from memory.
- Do not improvise a new plotting stack inside `write` when `paper-plot` should own the first-pass figure.
- Do not use `nature-polishing` to make unsupported, stale, or overbroad claims sound stronger.
- Do not use `nature-data` to invent repositories, accession numbers, DOIs, licences, embargoes, access committees, or ethics approvals.
- Do not use `nature-paper2ppt` unless the user asked for an actual presentation deck.
- Do not merge experiments and analysis into one undifferentiated result dump when they need distinct reviewer-facing jobs.
- Do not treat `evidence_ready` or `analysis_ready` as equivalent to `manuscript_ready` or `submission_ready`.
- Do not submit a paper-shot memo as a final paper package; checkpoint it and continue writing/review.
- Do not use rows that are not clearly bound to the current `selected_outline_ref` / active paper line.
- Do not keep revising a paper line whose publishability has collapsed; record the blocker and route to `decision` instead of accumulating more draft text.
- Do not keep appending new material to the top control block until it turns back into prose-heavy documentation; keep the top short and use the longer guidance below only when the task actually matches it.
- Do not paste or paraphrase user requests, route decisions, branch/worktree state, checklist language, command names, prompt state, or artifact-management history into manuscript prose.
- Do not write phrases such as `the user requested`, `the latest user requirement`, `paper restart`, `this quest`, `the agent`, `the worktree`, `we were told`, `he accepted`, `paper should`, or `remaining work on this manuscript` inside a paper draft.
- Do not use arithmetic endpoint/batch shorthand such as `64 + 64` or `64+64` in manuscript prose, titles, abstracts, captions, or conclusions.
- Do not let figure captions contain tool recommendations, website promotion, TODOs, or polish notes.

## Constraints
- Keep these files aligned when they exist:
  `paper/selected_outline.json`, `paper/evidence_ledger.json`, `paper/paper_experiment_matrix.md` or `.json`, `paper/references.bib`, `paper/claim_evidence_map.json`, `paper/paper_bundle_manifest.json`.
- If a section depends on experiment or analysis evidence, draft from the current paper contract rows, not from remembered summaries.
- If method, system, or implementation details are mentioned, treat the current codebase, configs, scripts, logs, and durable outputs as the primary truth surface; comments, plans, TODOs, and old draft wording are only hints until verified.
- User requirements and control files are allowed to constrain the writing route, but they are not evidence and are not manuscript text.
- Main text should usually describe serving and evaluation setup as a benchmark, comparison budget, evidence source, or evaluation protocol, not as local operator configuration. If exact throughput settings matter, put them in an appendix or reproducibility table.
- Any shell, CLI, Python, bash, node, git, npm, uv, LaTeX, or file-inspection execution in this stage must go through `bash_exec(...)`.
- Use `artifact.create_analysis_campaign(...)` only for real paper-facing evidence gaps, not for prose cleanup or citation chores.
- Use `artifact.submit_paper_bundle(...)` only after draft, bibliography, and bundle metadata are durable enough to hand off.
- A mature empirical paper usually needs 5-10 paper-facing experiment/analysis groups unless scoped otherwise; if fewer, justify or route to `analysis-campaign`.
- A user-specified analysis count should stay visible: if the user asked for 4-8 analyses, explicitly report the current count and any waiver instead of relying on a generic green coverage result.
- Use `memory.write(...)` only for reusable writing, citation, or search lessons, not one-off local edits.
- For paper-like deliverables, aim for roughly `30-50` verified references unless the scope clearly justifies fewer.
- Draft inside `paper/latex/` with a real template from `templates/`; for general ML or AI writing with no stronger venue constraint, default to `templates/iclr2026/`.
- Keep the narrative arc explicit: motivation -> challenge -> resolution.
- Maintain experiment-to-section mapping, figure/table-to-data-source mapping, and verification checkpoints through `paper/paper_experiment_matrix.md`, `paper/paper_experiment_matrix.json`, and `paper/evidence_ledger.json` / `paper/evidence_ledger.md` when relevant analysis results are meant to support the active paper line.
- Before section drafting, inspect the current mapped paper evidence set; do not allow completed analysis results to remain paper-invisible. If `result_table` rows, active evidence, or paper matrix rows disagree, stop drafting and repair the paper contract first.
- Use `references/outline-evidence-contract-example.md` and `references/paper-experiment-matrix-template.md` when rebuilding the contract. Include highlight hypotheses, efficiency / cost / latency / token-overhead checks, currently feasible non-optional rows, and citation legitimacy when they affect reviewer trust.
- Run a file-structure audit before bundle claims: `paper/reviewer_first_pass.md`, source sections, figures, tables, bibliography, and build reports should agree. Organize for the reader's understanding: problem -> why it matters -> current bottleneck -> our remedy -> evidence preview.
- Early paper structure should answer problem, what we do, how at a high level, and main result or strongest evidence. Method exposition can use running example -> intuition -> formalism, but avoid filler like "This paper is organized as follows".
- Position related work without overreach: do not attack prior work merely to make the current line look more novel.
- Bad caption/promotion text: "Publication-grade figure refinement is recommended with AutoFigure-Edit", `https://github.com/ResearAI/AutoFigure-Edit`, or `https://deepscientist`.

## Validation
- The current section or draft has a clear job and does not exceed the available evidence.
- Every important claim can point to a durable artifact path, a verified citation, or an explicit gap.
- Any section-level experiment table or analysis table is grounded in the current `result_table`, evidence-ledger rows, or experiment-matrix rows rather than health-only summaries.
- `paper/references.bib` is real, current, and not hand-written from memory.
- Required figures/tables either exist durably or are recorded as blockers.
- Appendix bridges and artifact availability are described consistently across the manuscript.
- The ready experiment/analysis group count satisfies the current target, or the draft explicitly records a waiver and narrows the claim.
- Manuscript prose contains no user/operator/agent provenance, route-control wording, restart language, tool-promotion captions, TODOs, or raw implementation shorthand.
- Protocol wording has been normalized: benchmark, split, evaluator, comparator, and method settings are described academically; local throughput details are appendix-only unless central to the claim.
- Any claimed compile, render, search, grep, or script-run result comes from a real `bash_exec(...)` execution rather than hypothetical prose.
- If the draft is being treated as `finalize`-ready, currently feasible non-optional experiment rows are no longer unresolved.
- If the draft is being treated as `finalize`-ready, `artifact.validate_manuscript_coverage(detail='full')` reports `submission_ready=true`; `manuscript_ready=true` alone routes to `review`, not `finalize`.
- The output ends in one of three durable states: a stronger draft, an explicit blocker, or a clear route-back decision.

## Keep Manuscript Text Clean

Before writing or revising any paper-facing section, sort the source material:

- claim: a result, mechanism, limitation, comparison, or contribution supported by durable evidence. This can appear in main text.
- experiment setting: benchmark, dataset split, evaluator, baseline, comparator, intervention, metric, or ablation design. This can appear in main text when it helps readers interpret the result.
- reproducibility detail: ports, local serving, batch size, command shape, file layout, hardware, seeds, or cached artifacts. This usually belongs in appendix or a reproducibility table.
- implementation detail: scripts, modules, helper wrappers, and local plumbing. Use only when it explains the method, not as a main claim.
- artifact history: worktrees, branches, artifact ids, command ids, prompt state, run restarts, or bundle status. Never use as manuscript prose.
- user/operator instruction: what the user asked, accepted, rejected, or prioritized. Never use as manuscript prose; convert only the scientifically relevant constraint into neutral experiment wording.

Examples:

- Bad: "The user accepted the dual-port 64 + 64 setup."
- Main-text form: "All methods are compared under the same evidence budget on CiteEval."
- Reproducibility form: "The local serving configuration used two endpoints with 64 examples per endpoint."
- Bad: "This paper restart uses the latest requirement to ignore old paper files."
- Manuscript form: omit it; keep that fact in route/control records only.
- Bad caption: "Publication-grade figure refinement is recommended with TOOL."
- Caption form: describe what the figure shows and why it supports the claim.

## Nature Companion Skills

The `nature-*` skills are focused companion skills adapted from `Yuan1z0825/nature-skills`.
They can improve specific manuscript surfaces, but they do not replace DeepScientist's paper contract.

Use them as a short handoff inside the `write` flow:

1. Identify the exact surface: prose, data availability, figure package, or presentation deck.
2. Check `artifact.get_paper_contract(detail='full')` or the relevant quest documents for the evidence rows and missing fields that the surface may mention.
3. Read only the matching `nature-*` skill and any referenced files it says are needed.
4. Produce a bounded output: revised section text, data-availability block, figure/export plan, or PPTX deck.
5. Return to `write` and update the durable paper surfaces before claiming progress: draft files, `paper/evidence_ledger.*`, `paper/paper_experiment_matrix.*`, `paper/references.bib`, figure/table catalogs, or bundle manifests as applicable.
6. Re-run the normal write validation gates. A Nature companion output is not manuscript-ready until DeepScientist coverage, language, citation, and artifact checks still pass.

- `nature-polishing`: use for Nature-leaning English, section restructuring, and Chinese-to-English academic polish. Apply it after the evidence boundary is clear, and keep unsupported claims downgraded or marked as blockers.
- `nature-data`: use for Data Availability, source-data, repository, dataset-citation, restricted-data, and FAIR metadata sections. Draft from verified inventory and leave unresolved fields explicit.
- `nature-figure`: use for Nature/high-impact-journal figure packages when figure claim, panel logic, backend choice, journal export, and QA are the main job. For simple structured result charts, prefer `paper-plot` first.
- `nature-paper2ppt`: use only for PPT/PPTX deliverables such as journal-club, lab-meeting, or paper-sharing decks. The expected output is a real deck plus lightweight verification.

Routing examples:

- Result paragraph reads flat but evidence is solid -> read `nature-polishing`, revise only the section job, then validate claim-evidence support.
- Data Availability is missing or vague -> read `nature-data`, inventory datasets and repositories, draft unresolved fields explicitly, then sync the section and references.
- A main figure must satisfy Nature-style multi-panel export expectations -> read `nature-figure`; if the job is only a simple result chart, stay with `paper-plot` plus `figure-polish`.
- User asks for a journal-club deck from a paper -> read `nature-paper2ppt`; keep it outside the manuscript bundle unless the user asks to attach it as a deliverable.

## Potentially Reference-Worthy, Code-Grounded Facts
- Implementation surfaces can be worth citing in prose when they are verified from the current repo state: entrypoints, module boundaries, dataflow stages, control loops, evaluator wiring, and ablation switches that materially affect the claim.
- Config truth can be worth citing when it changes interpretation: actual loss terms, objective weights, decoding or inference settings, comparison toggles, dataset filters, and default runtime modes taken from checked configs or scripts.
- Reproducibility and trust details can be worth citing when they are real: executable scripts, artifact paths, checkpoint conventions, dependency constraints, hardware assumptions, and run-time limits that the current code or logs actually expose.
- Failure-boundary details can be worth citing when they are visible in code or artifacts: guardrails, unsupported regimes, fallback paths, assertions, evaluator exclusions, or branch-specific limitations that materially narrow the claim.
- Concrete traces can be worth citing when they are generated artifacts rather than imagination: logs, examples, case-study outputs, prompt traces, or render outputs produced by the current code path.
- If a detail is only present in comments, TODOs, planning notes, stale branches, or remembered conversation, do not write it as fact.
- If code and manuscript wording disagree, resolve to code plus durable outputs first, then rewrite the manuscript to match.
- If a path exists in code but was not exercised by the evidence package, label it as implemented or available, not as experimentally validated behavior.

## Reference Routing
- Read `references/oral_package_patterns.md` when the draft needs a clearer oral-style evidence package.
- Read `references/oral_writing_principles.md` when the narrative spine, reader onboarding, or reviewer-facing tone is weak.
- Read `references/experiments_analysis_patterns.md` when experiments and analysis need clearer job separation.
- Read `references/section_rewrite_checklist.md` before treating a rewritten section as stable enough for bundling or review.

# Draft To Top Conference Oral

## Overview

Use this skill when a paper already exists in draft form and the real problem is not "write a paper from zero" but "turn this draft into something that reads like a top-conference oral paper."

This skill is for the transition:

- from dense draft to memorable paper
- from correct content to reviewer-facing writing
- from result dump to staged evidence
- from overloaded pages to intentional pacing
- from LLM-like compression to human-like editorial judgment
- from isolated main text to a deliberate oral package with appendix support

Do not use this skill to invent missing evidence. If the draft has real evidence gaps, narrow claims or route to more experiments instead of hiding the weakness with better prose.

## What This Skill Optimizes

This skill is specifically about oral-paper upgrade work, not generic prose cleanup. It optimizes:

- story spine and claim scope
- reader onboarding and early intuition
- evidence budget across main text and appendix
- figure and table role clarity
- division of labor between displays and prose
- experiments versus analysis separation
- trend-first, mechanism-aware data analysis
- reviewer-concern handling
- page pacing and readability
- limitations, reproducibility, and trust signaling

Read `references/oral_package_patterns.md` early when deciding what to add, cut, move, or split.

## When to Use This Skill

Use this skill when:

- A full or partial scientific draft already exists
- The user wants to upgrade a draft to conference-ready or oral-quality writing
- The paper has results but the story, writing, figures, or analysis feel weak
- The draft reads like a compressed summary, lab note, or LLM reconstruction
- The task is to improve abstract, introduction, method explanation, result writing, figure/table communication, or analysis depth
- The user wants the paper to feel more like ICLR/NeurIPS/ICML/CVML oral quality
- Two paper versions exist and the job is to distill what made the stronger version feel more oral-ready, then reuse those patterns

Do not use this skill when:

- There is no meaningful draft yet
- The core task is literature search only
- The real blocker is missing experiments, missing baselines, or missing results
- The request is for formal peer review rather than revision and upgrade

## Workflow

### 1. Audit the draft before rewriting

Read the current abstract, introduction, method, experiments, analysis, conclusion, and appendix if present.

Extract:

- `C1-C3`: the 1 to 3 core claims
- strongest current evidence
- weakest current evidence
- likely rejection reasons
- which parts are writing problems versus evidence problems

Classify the draft weakness into one or more of:

- story
- writing
- method exposition
- figure/table communication
- experiment analysis
- claim calibration
- reproducibility/trust signaling

If the main issue is evidence, do not proceed as if this were only a writing problem.

### 2. Build an oral delta map before line editing

Use `references/oral_package_patterns.md` to compare the current draft against an oral-ready target.

Label the biggest gaps. Typical gaps include:

- weak reader onboarding
- no early intuition or mechanism figure
- one page trying to carry too many claims
- tables acting as storage rather than argument
- experiments and analysis collapsed into one results block
- analysis that only repeats numbers without extracting the trend
- no memorable case study or failure-mode analysis
- appendix functioning as a dump instead of a supplement package
- claim language that extends beyond the strongest evidence zone
- artifact availability described inconsistently across sections

When two versions of the paper exist, explicitly write the delta:

- what the stronger version added
- which added elements improved persuasion rather than merely adding length
- which patterns are reusable in the current rewrite

### 3. Reallocate the evidence budget

Top-conference oral papers are not just more polished. They spend pages and displays where reviewer friction is highest.

Before rewriting paragraphs, decide:

- which figures or tables belong in the main text
- which evidence blocks should become standalone subsections
- what must move to appendix
- where to place the appendix bridge in the main text
- which exact facts live in displays versus surrounding prose
- which core claim or reviewer question each main-text display is responsible for defending
- whether method defense is taking budget away from objection handling

Default main-text priorities:

- one early intuition or mechanism figure
- one main result display
- one interpretive analysis or tradeoff display
- one practical-value or objection-handling block when it is central to the claim
- one memorable qualitative example or case-study display when available

If the paper's central claim is comparative, benchmark-driven, or baseline-beating, the "main result display" must stay competitor-inclusive.

That usually means:

- named baselines or nearest neighbors remain visible in the main text
- the metric spread needed to justify the comparative wording remains visible
- the reader can verify the claimed ranking or scope without reconstructing it from prose alone

Do not collapse a broad benchmark story into a self-only summary table if the prose still makes broad comparative claims.

When the gold oral package keeps both a compact setup or baseline taxonomy and a competitor-inclusive benchmark surface in main text, preserve both jobs in the rewrite. Do not jump straight from prose setup to compressed averages if the reviewer still needs to see who was compared, under which regime, and where the main ranking or boundary actually appears.

When the paper has multiple proof obligations, do not present them as one continuous "results" stream.

Instead, turn the main empirical body into explicit reviewer-question blocks, where each block has:

- one concrete question the reviewer would naturally ask
- one short setup line that states the regime or slice being tested
- one named baseline, counterfactual, or comparison target when the draft package or staged artifacts provide one
- one dominant display
- one dominant takeaway
- one explicit appendix bridge for overflow evidence
- a clear handoff to the next question

If the strong paper or staged package already separates a section into named internal jobs, preserve that internal scaffold in the rewrite.

Do not collapse those jobs into one continuous wall of prose when reviewers need to inspect them separately.

This is especially important for:

- related work sections that need a distinct closest-comparator contrast
- method sections that need separate blocks for workflow, component design, supervision, and action realization
- experiments sections that need visibly separate headline evaluation, transfer breadth, and mechanism-validation blocks

When the paper's credibility depends on first proving that a metric, proxy, or diagnostic predicts reviewer-relevant outcomes, allocate a standalone validation block before intervention or design-guidance blocks.

Do not bury that proof inside later intervention subsections or leave `analysis` with only mechanism commentary if the draft package signals validation as the bridge into the rest of the paper.

If the draft package or staged artifacts separate several intervention families, keep them separate in the rewrite.

Each intervention family should still preserve:

- its own setup line
- its own baseline or counterfactual when one exists
- its own dominant display
- its own headline result
- its own appendix bridge

If the evidence package carries multiple transfer fronts, keep at least one non-headline transfer benchmark or cross-setting validation in the main experiments section beyond the primary deployment or headline benchmark.

When the gold oral package uses multiple main-text displays to answer distinct reviewer questions, keep one explicit main-text boundary, robustness, or scope-setting display in addition to the headline comparison block. Do not push every non-headline empirical check into appendix overflow if the central claim still depends on visible claim-boundary evidence.

Only move exhaustive rows, per-task detail, and secondary checks to the appendix; do not narrow the main paper to one deployment table plus appendix overflow when the central claim depends on visible generalization breadth.

When the method makes a core claim operational, reserve method-local evidence for that claim.

For claims about open-ended actions, executable control, retrieval-grounding, tool use, or interaction loops, include at least one concrete method artifact when available:

- a compact code snippet
- a local worked example
- an input-output trace
- a method-local schematic
- a small table that makes the mechanism inspectable

Do not push all operational concreteness into experiments or appendix material.

Move exhaustive material to appendix:

- full result tables
- hyperparameter sweeps
- annotation protocol details
- extended examples
- extra proofs and implementation detail

Default appendix blueprint when the paper is mature enough:

- methodology overflow that defends setup, measurement choices, and regime inventory
- full-results overflow that keeps task-level or slice-level evidence inspectable
- enlarged-display overflow for figures, tables, and curves that reviewers may need to inspect closely
- literature overflow when related work has secondary breadth that would crowd the main text
- transfer-overflow evidence when main experiments keep the headline transfer block but not all transfer rows
- tuned baselines or sensitivity checks
- protocol transparency or prompt detail when the gold package uses them to make the empirical story auditable
- formal-properties or metric-support material when the main text relies on a new metric, proxy, or diagnostic
- qualitative examples
- failure cases
- separate compliance or broader-impacts support when the gold package keeps that job distinct
- reproducibility and artifact details

Before drafting, record which main-text section must point to each appendix bucket.

Method, experiments, and analysis should each know which overflow material they are delegating and where the bridge sentence will appear.

Related work should also know whether it needs a bridge to an extended-literature appendix lane.

Generic appendix references are not enough when the manuscript relies on overflow evidence for credibility.

Each important bridge should name a precise appendix destination such as:

- a labeled subsection
- a labeled table or figure
- a titled overflow lane that will later receive a stable label

Do not write only "see the appendix" when the claim depends on protocol detail, method implementation detail, transfer overflow, extended literature, or worked traces.

When compressing a strong paper, do not let the appendix degrade into a light method bridge.

The appendix should still look like a reviewer-support package with explicit jobs, especially when the main text has compressed:

- setup details that make comparisons interpretable
- extra analyses that answer likely objections
- qualitative or human-evaluation evidence
- supporting tables that defend the main claim's breadth

### 4. Rewrite the paper in oral-paper order

Top-conference oral papers stage information in the order that minimizes reviewer friction.

Rewrite in this order:

1. story spine
2. abstract and introduction
3. method and related work
4. main results
5. analysis
6. figures and tables with surrounding prose
7. conclusion, limitations, appendix bridge

When writing the paper in a sectioned workflow, use this concrete generation order:

1. `section_plan`
2. `introduction`
3. `related_work`
4. `method`
5. `experiments`
6. `analysis`
7. `appendix`
8. `limitations`
9. `conclusion`
10. `abstract`
11. `integration`

Use `section_plan` as an internal control document, not as manuscript prose. It should record:

- `C1-C3`
- which section owns the headline proof or validation burden for each main claim
- the chosen main-text display program
- the first-page evidence stack: at least one problem-scale anchor and one solution-shape anchor when staged artifacts support both
- likely reviewer objections
- the study regime inventory that must stay visible in main text
- the closest-work novelty boundary
- appendix overflow jobs
- the appendix bridge map from method, experiments, and analysis into those jobs
- any related-work-to-appendix bridge lane
- any non-headline transfer benchmark that must remain in main text
- any method-local operational artifact that must not be demoted
- any closest-comparator contrast that must remain explicit in related work
- any section-internal scaffold that must survive compression
- the exact appendix labels or label candidates each main-text bridge should point to
- any analysis taxonomy terms that must be defined before interpretation
- one concise job description for each section
- which concrete staged displays or authored tables will answer each objection

Write the abstract last, after the paper's actual evidence order has stabilized.

In sectioned mode, keep `main.tex` as the canonical top-level document and keep body prose in separate section files. Do not collapse the manuscript back into one giant draft while writing. Use the final integration pass only to repair consistency, sharpen transitions, synchronize claim wording, and remove staging artifacts from the prose.

Do not reserve essential evidence allocation for integration. Each body section should already be locally complete enough that an interrupted integration pass does not erase key reviewer-defense blocks or appendix bridges.

### 5. Apply oral-level writing rules

Use the principles in `references/oral_writing_principles.md`.

The most important rules are:

- optimize for reader guidance, not maximum compression
- every section must have a job
- every paragraph should do one main thing
- signpost transitions explicitly
- explain why a result matters, not only what the number is
- let displays carry detailed values while prose carries interpretation
- make data analysis extract the trend, mechanism, and tradeoff instead of narrating values
- defend the method from multiple angles, not just by giving formulas
- keep claim wording inside the strongest evidence zone
- use figures as narrative anchors, not just evidence containers
- move low-priority detail to appendix and keep main text legible
- calibrate claims instead of overselling

### 6. Use section-specific rewrite checks

When actively rewriting, use `references/section_rewrite_checklist.md`.

That file gives a practical pass for:

- abstract
- introduction
- related work
- method
- experiments
- analysis
- conclusion
- appendix

### 7. Convert reviewer objections into visible evidence blocks

A mature oral paper does not merely mention likely reviewer concerns. It allocates explicit evidence to them.

Typical evidence blocks include:

- tuned-baseline results
- transfer or cross-model checks
- efficiency or cost analysis
- diversity or conservatism analysis
- human evaluation protocol details
- failure cases
- case studies that explain a mechanism

If a likely objection matters, do not hide the answer in one sentence.

If the draft package supports several objection-resolving blocks, keep them as separate visible subsections rather than folding them into one omnibus paragraph or one overloaded table.

When the paper has enough evidence, reserve one explicit main-text block for reviewer-concern handling rather than hoping the reader infers those answers from the benchmark summary alone.

Typical reviewer-concern blocks to surface in the main text include:

- broader baseline coverage or competitor context
- human-evaluation signal
- efficiency or cost tradeoffs
- qualitative traces or failure cases
- transfer or robustness checks
- mechanism-level evidence about why the method's policy changes behavior

For each evidence block, make the prose-display contract explicit:

- the table or figure carries the concrete values, examples, or traces
- the surrounding prose states the question, takeaway, and mechanism
- the analysis text explains why the observed pattern appears instead of re-reading visible numbers
- the analysis text names the trend explicitly and says what underlying behavior or tradeoff it reveals

### 8. Distinguish writing upgrades from evidence upgrades

If a section feels weak, diagnose the real cause:

- If the claim is unsupported, reduce or narrow the claim.
- If the result exists but reads weakly, rewrite the framing and result prose.
- If the mechanism is unexplained, add analysis or move analysis into the main text.
- If the trend is visible but the section only lists values, rewrite around the pattern and its cause.
- If the method section is crowding out reviewer-concern handling, compress repeated defense and reallocate the space.
- If artifact status is described inconsistently, synchronize every mention across abstract, main text, reproducibility, and appendix.
- If the page is crowded, rebalance main text versus appendix.

Never use polished language to conceal an unaddressed scientific gap.

## Sectioned Execution Pattern

When the draft is dense enough to support staged writing, prefer generating the manuscript section by section rather than asking for the full paper in one turn.

Use these operating rules:

- The plan turn chooses the story spine, display program, reviewer-question blocks, and appendix jobs before body prose is written.
- Each section turn should read the global plan plus only the small subset of earlier sections and staged artifacts it truly needs.
- `Introduction` should not collapse a display-led first page into prose. When the staged package supports both problem scale and solution shape, preserve both roles with concrete displays, authored compact tables, or a figure-plus-table pairing.
- `Introduction` should preserve one concrete first-page failure case, benchmark contrast, or payoff anchor when the gold oral package uses it to make the problem vivid before formal sections begin.
- `Related Work` should name the closest prior and the exact novelty boundary rather than stopping at broad capability buckets.
- `Method` should keep a short main-text audit surface for model suites, benchmark groups, or regime inventory when the gold paper uses one to make the method's evidence base inspectable.
- `Experiments` should establish the main empirical pattern through explicit reviewer-question blocks, each anchored by one dominant display.
- `Experiments` should keep one non-headline transfer or robustness block in main text when the staged package has several transfer fronts and the central claim needs visible generalization breadth.
- `Experiments` should preserve visibly separate internal layers for headline evaluation, transfer breadth, and mechanism validation when the staged package distinguishes those jobs. Do not compress them into one undifferentiated benchmark narrative.
- `Experiments` should preserve repeated setup/results scaffolds for distinct intervention families when the gold oral paper uses them to turn validation into actionability. Do not collapse several intervention families into one short summary block if reviewers still need to inspect them separately.
- `Method` should preserve main-text setup and study-regime inventory when the draft package contains them. If the staged package distinguishes prediction settings, model suites, checkpoint slices, benchmark groups, or measurement definitions, keep those distinctions through separate subsections or strong subsection headings instead of pushing them all into appendix prose.
- `Method` should keep at least one local operational artifact when a core mechanism claim depends on concreteness, especially for executable action spaces, tool calls, browser actions, retrieval grounding, or closed-loop control.
- `Method` should preserve visible internal scaffold when the system explanation has distinct jobs such as workflow overview, specialist model design, supervision/data construction, and executable action realization. Strong paragraph heads are acceptable; one merged prose block is not.
- `Analysis` should not continue the result dump. It should explain mechanism, trend, tradeoff, or failure behavior that the reviewer cannot infer from the visible numbers alone, and it should use a visible display or table when the interpretive claim depends on evidence the reader would otherwise not see.
- `Analysis` should remain a standalone reviewer-facing layer after headline results. Keep at least two visible check blocks, subsections, or strongly signposted units when the staged package separates mechanism, credibility, robustness, tradeoff, sensitivity, or failure-boundary work instead of collapsing everything into one short afterword.
- `Analysis` should own the headline validation burden when the paper first needs to prove that a metric, proxy, or diagnostic is meaningful before moving to interventions, recommendations, or downstream design guidance. Do not let `analysis` devolve into a leftover mechanism note if it is carrying primary credibility work in the staged evidence package.
- `Analysis` should keep a minimum main-text evidence floor before deferring support to the appendix: preserve at least one mechanism or credibility display and at least one tradeoff, robustness, sensitivity, or quality-support display when the staged package uses them to answer different reviewer concerns.
- `Analysis` should open with an explicit taxonomy, mechanism frame, or tradeoff frame when later interpretation depends on named categories. If the gold package distinguishes failure types such as programming, planning, and summarization, define those categories before interpreting shifts between them.
- `Appendix` should be written before `limitations`, `conclusion`, and `abstract` so later sections can accurately describe the support package that actually exists.
- `Integration` should check cross-section consistency, display roles, appendix bridges, and claim calibration, not rewrite the paper from scratch.
- `Integration` should remove meta-signposting or planning language that still reads like drafting scaffolding, and it should preserve one memorable qualitative, human, or failure anchor when the staged package can support it.
- `Integration` should check titles, abstract, captions, conclusion, and section openings for user/operator/route wording; these locations must read like paper text, not process notes.
- `Integration` should replace generic appendix mentions with precise labeled destinations whenever the body section already knows the supporting overflow lane.
- `Integration` should audit canonical section jobs, not just headings.

This audit should flag:

- introductions that lost a concrete first-page evidence or visual anchor
- introductions that keep a problem anchor but lose the early solution-shape display
- methods that dropped study-regime inventory or setup-to-definition staging
- methods that make operational claims without a local example, code snippet, trace, or mechanism display
- experiments that merged separate intervention proof blocks into one omnibus stream
- experiments that moved all non-headline transfer evidence out of main text
- analysis sections that lost the headline validation burden
- analysis sections that collapsed multiple reviewer-facing checks into one short interpretive afterword
- analysis sections that defer both mechanism or credibility support and tradeoff or boundary support to appendix references
- analysis sections that interpret named failure shifts without first defining the failure categories
- related work sections that stay thematic instead of naming the closest comparator and exact novelty boundary
- related work sections that need but lack an explicit bridge to extended literature overflow
- appendices that no longer expose the planned support buckets or their bridge sentences
- body sections that say only "the appendix" where a specific appendix destination should be named

In this mode, a strong default main-text display program is:

- one early mechanism or intuition display
- one competitor-inclusive main result display
- one interpretive analysis or tradeoff display
- one memorable qualitative, human-evaluation, or failure-case display when the package can support it

If one of these roles is missing, do not merely mention it in prose. Either promote a staged artifact into that role or narrow the paper's claims to match the thinner package.

### 9. Run a final oral-package pass

Before stopping, check:

- Can a reviewer summarize the paper after one read?
- Is the central idea anchored early in both text and visuals?
- Does each main-text page or section have one dominant job?
- Is there at least one memorable figure or case study?
- Does the analysis change the reader's understanding rather than repeat results?
- Does the appendix feel prepared rather than improvised?
- Are the strongest claims phrased no more strongly than the evidence package allows?
- Is artifact availability described consistently everywhere it appears?

## Operating Principles

### Reader-first writing

A draft often tries to maximize information density. An oral paper maximizes comprehension, recall, and trust.

### Method defending, not just method defining

A strong oral paper does not stop at the formula. It explains:

- what the method is
- why it is principled
- how it differs from alternatives
- why the observed empirical behavior makes sense

### Result organization over result accumulation

Do not pile all numbers into one page or paragraph. Break results into:

- the main pattern
- the mechanism or interpretation
- the objection-handling evidence

### Data analysis should expose trend and essence

Strong oral papers do not treat analysis as number recitation.

Use analysis to answer:

- what trend is stable across settings
- what tradeoff is actually being managed
- what mechanism most plausibly drives the pattern
- what this implies about the method's true scope

### Writing around figures and tables matters

The prose before and after a figure or table should tell the reader:

- why this display appears here
- what question it answers
- what takeaway to retain

### Prose explains, displays show

In strong oral papers, main-text prose does not waste its budget by restating numbers the reader can already read from a table or plot.

Use displays for:

- exact values
- full comparisons
- trajectories and traces
- qualitative examples

Use prose for:

- why the display matters here
- what the dominant pattern is
- why that pattern appears
- what reviewer concern the display resolves

When the display is a benchmark block, the prose may summarize the headline pattern, but it should not be the only place where the comparison surface exists.

### Claims should stay inside the strongest evidence zone

If the evidence supports "strong default," "wins or ties most settings," or "more robust under sweep," do not escalate the wording into universal dominance.

Overclaiming wastes reviewer trust that the rest of the paper worked hard to build.

If you removed competitor rows, compressed the metric spread, or moved key comparison context out of view, narrow the comparative wording accordingly.

### Method defense should not crowd out objection handling

A method section can be principled and still overconsume main-text budget.

Compress repeated defense if that space is more valuable as:

- tuned-baseline evidence
- transfer evidence
- limitations
- practical-value discussion
- a compact objection-handling block

### Appendix is part of the oral package

An oral paper is usually defended by main text plus appendix together. Treat the appendix as part of the persuasion system, not as detached storage.

## Common Failure Modes To Remove

These are strong signals that a draft still reads like a compressed or LLM-like paper:

- abstract overloaded with numbers and no pacing
- introduction that states conclusions before building motivation
- related work arriving too late
- method section that defines equations but never teaches the reader how to think about them
- result sections that report averages without decomposing the pattern
- analysis sections that feel like leftover support instead of part of the argument
- analysis prose that simply narrates the visible table or plot
- analysis that lists values without naming the trend or mechanism
- no early mechanism figure
- no memorable case study or failure-mode evidence
- figures appearing late and functioning only as storage
- one page carrying several unrelated local claims
- tables dominating the main text
- weak signposting
- appendix that looks appended rather than designed
- appendix without an explicit reviewer-defense structure
- claim language that outruns the evidence package
- artifact availability described inconsistently across sections
- isolated claim-calibration sentences instead of structurally calibrated writing
- user, operator, branch, worktree, prompt, restart, or bundle-management language appearing in manuscript prose
- raw local execution shorthand in main text, especially endpoint or batch arithmetic that should be protocol prose or appendix-only reproducibility detail

## Output Pattern

When using this skill, leave behind one or more of the following:

- a revised paper draft
- a section-by-section rewrite plan
- a claim-evidence map
- an oral delta map
- a figure/table revision plan
- a main-text versus appendix reallocation plan
- a list of writing-only fixes versus evidence-dependent fixes

Prefer concrete edits over generic advice.

## References

- `references/oral_package_patterns.md`
- `references/oral_writing_principles.md`
- `references/section_rewrite_checklist.md`
- `references/experiments_analysis_patterns.md`
