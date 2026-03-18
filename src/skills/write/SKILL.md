---
name: write
description: Use when a quest has enough evidence to draft or refine a paper, report, or research summary without inventing missing support.
---

# Write

Use this skill to turn accepted evidence into a faithful draft, report, or paper bundle.
This skill intentionally absorbs the strongest old DeepScientist writing discipline, including:

- evidence assembly
- storyline and outline
- drafting
- citation integrity
- figures and tables
- self-review
- visual proofing
- submission gate

## Interaction discipline

- Treat `artifact.interact(...)` as the main long-lived communication thread across TUI, web, and bound connectors.
- If `artifact.interact(...)` returns queued user requirements, treat them as the highest-priority user instruction bundle before continuing drafting or revision.
- Immediately follow any non-empty mailbox poll with another `artifact.interact(...)` update that confirms receipt; if the request is directly answerable, answer there, otherwise say the current subtask is paused, give a short plan plus nearest report-back point, and handle that request first.
- Emit `artifact.interact(kind='progress', reply_mode='threaded', ...)` when there is real user-visible progress: the first meaningful signal of long work, a meaningful checkpoint, or a concise keepalive if active work has drifted beyond roughly 10 to 30 tool calls without a user-visible update.
- Prefer `bash_exec` for durable document-build commands such as LaTeX compilation, figure regeneration, and scripted export steps so logs remain quest-local and reviewable.
- Keep progress updates chat-like and easy to understand: say what changed, what it means, and what happens next.
- Default to plain-language summaries. Do not mention file paths, artifact ids, branch/worktree ids, session ids, raw commands, or raw logs unless the user asks or needs them to act.
- Keep ordinary subtask completions concise. When a paper/draft milestone is actually completed, upgrade to a richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` report instead of another short progress update.
- That richer writing-stage milestone report should normally cover: which draft, section, or outline milestone finished, what is now supportable, what is still missing, and the exact recommended next revision or route decision.
- That richer milestone report is still normally non-blocking. If the next writing or return-to-experiment step is already clear, continue automatically after reporting instead of pausing by default.
- If the active communication surface is QQ, keep writing milestones text-first unless a final paper PDF or one clearly useful summary artifact already exists.
- Treat connector-facing report charts separately from paper-facing figures; do not auto-send draft paper figures to QQ.
- For paper-facing figures and figure drafts, keep palette discipline explicit:
  - prefer `mist-stone` as the paper-default palette: `#F3EEE8`, `#D8D1C7`, `#8A9199`
  - use `sage-clay` when the method-vs-baseline contrast needs one stronger but still muted accent: `#E7E1D6`, `#B7A99A`, `#7F8F84`
  - use `dust-rose` sparingly for secondary ablations or auxiliary comparisons: `#F2E9E6`, `#D8C3BC`, `#B88C8C`
- Paper-figure requirements:
  - consistent palette across the same paper section
  - white background, restrained grid, minimal decorative elements
  - legends and labels should read cleanly in PDF export
  - do not use bright dashboard colors or connector-style clutter in paper figures
- Choose chart type by the paper claim:
  - line chart for ordered trends
  - bar chart only for a small number of categorical end-point comparisons
  - point-range / dot plot when interval estimates matter
  - heatmap only when matrix structure is the actual result
- If a figure uses continuous color:
  - ordered magnitude -> sequential muted palette
  - signed delta around zero or a reference -> diverging muted palette with a neutral midpoint
- Avoid rainbow / jet-like maps, heavy shadows, thick borders, and decorative gradients inside the plotted marks.
- Prefer vector-first export for paper figures: `pdf` or `svg`, plus one `png` preview when helpful.
- When practical, size figures so they can survive later single-column or double-column placement without unreadable text.
- For any figure that will enter the draft, appendix, or paper bundle, open `figure-polish/SKILL.md` and complete its render-inspect-revise pass before treating the figure as final.
- If you generate figure code in Python, start from the system prompt Morandi plotting template and only adjust figure size, labels, and series colors as needed.
- If the runtime starts an auto-continue turn with no new user message, keep drafting or verifying from the durable state and active requirements instead of replaying the previous user turn.
- Message templates are references only. Adapt to the actual context and vary wording so updates feel respectful, human, and non-robotic.
- Use `reply_mode='blocking'` only for real user decisions that cannot be resolved from local evidence.
- For any blocking decision request, provide 1 to 3 concrete options, put the recommended option first, explain each option's actual content plus pros and cons, and wait up to 1 day when feasible. If the blocker is a missing external credential or secret that only the user can provide, keep the quest waiting, ask the user to supply it or choose an alternative, and do not self-resolve; if resumed without that credential and no other work is possible, a long low-frequency wait such as `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` is acceptable. Otherwise choose the best option yourself and notify the user of the chosen option if the timeout expires.
- If a threaded user reply arrives, interpret it relative to the latest writing progress update before assuming the task changed completely.
- Use milestone updates deliberately when outline selection, claim downgrades, proofing completion, bundle readiness, or route-back-to-experiment decisions become durably true.

## Stage purpose

The write stage does not exist to make the quest sound finished.
It exists to test whether the current evidence can support a stable narrative.

If the evidence is incomplete, contradictory, or too weak, the correct output is:

- an explicit evidence gap
- a downgraded claim
- or a route back to `experiment`, `analysis-campaign`, or `scout`

not a polished fiction.

For paper-like deliverables, the durable contract is outline-first, not prose-first.
The approved outline should be a real structured object, typically containing:

- `story`
- `ten_questions`
- `detailed_outline`
  - `title`
  - `abstract`
  - usually `3` concrete `research_questions`
  - `methodology`
  - `experimental_designs`
  - `contributions`

## Writing mental guardrails

- Writing starts when the claim and evidence structure are stable enough, not when prose feels easy.
- Underclaim in prose and overdeliver in evidence.
- A figure or table is an argument, not decoration.
- Draft-ready is not submission-ready, and submission-ready is not quest completion.
- If the cleanest next move is to gather evidence rather than to write harder, route back explicitly.
- Organize for the reader's understanding, not the author's implementation chronology.
- Assume a reviewer may form the first judgment from a fast scan rather than a full patient reading.
- Prefer direct contributions and evidence over organizational boilerplate.
- Keep the first page information-dense, evidence-led, and easy to scan.

## Use when

- the quest has an accepted baseline and at least one meaningful experimental result
- a report, paper, or draft summary is now justified
- the user wants a research note, draft, or paper bundle
- finalization is close but narrative and evidence still need consolidation
- the startup contract still requires research-paper delivery, unless the user explicitly changed scope later

## Do not use when

- the quest still lacks a credible evidence base
- the main work is still baseline establishment or ideation
- the current need is a follow-up analysis rather than narrative consolidation
- the startup contract explicitly disables research-paper delivery and the user has not re-enabled paper writing

## Preconditions and gate

Before writing seriously, confirm:

- the baseline state is accepted or explicitly waived
- the claims you intend to write are backed by durable artifacts
- the code/diff path is available for method fidelity checks
- the evaluation contract is explicit

If major claims lack evidence, surface the gap first.

## Truth sources

Use these as the canonical evidence base:

- baseline artifacts
- run artifacts
- analysis campaign reports
- milestone and decision artifacts
- code and diffs
- quest documents
- verified citations from primary sources
- literature discovery results gathered through web search
- paper-reading notes gathered after using `artifact.arxiv(...)` when arXiv papers had to be read closely

Do not rely on memory alone for numbers.
Always prefer direct artifact paths for claims.

## Required durable outputs

The write stage should usually produce most of the following:

- `paper/outline.md` or equivalent outline
- `paper/selected_outline.json`
- `paper/outline_selection.md`
- `paper/reviewer_first_pass.md`
- `paper/section_contracts.md`
- `paper/draft.md` or equivalent draft
- `paper/writing_plan.md` or equivalent working plan
- `paper/figure_storyboard.md`
- `paper/related_work_map.md`
- `paper/references.bib` when citation management is needed
- `paper/claim_evidence_map.json`
- `paper/paper_bundle_manifest.json` or equivalent bundle manifest
- `paper/figures/figure_catalog.json` if figures exist
- `paper/tables/table_catalog.json` if tables exist
- `paper/build/compile_report.json` when a compiled paper bundle exists
- `paper/proofing/proofing_report.md`
- `paper/proofing/page_images_manifest.json` when rendered pages exist
- `paper/proofing/language_issues.md`
- `paper/review/review.md` or equivalent harsh self-review output
- `paper/review/revision_log.md` or equivalent revision ledger
- `paper/review/submission_checklist.json`
- report and decision artifacts describing writing readiness or evidence gaps

The exact paths may vary, but the structure and meaning should remain clear.

Treat the approved outline as the authoritative blueprint for the draft.
Treat `paper/draft.md` or the equivalent working note as the running evidence ledger where useful findings, citation notes, and writing decisions are accumulated as work proceeds.
After every significant search, plot, paragraph, revision pass, or claim downgrade, update the working note and writing plan immediately so important writing state is not trapped in transient chat output.
For any substantial paper-writing line, keep `paper/writing_plan.md` or an equivalent durable plan detailed enough that another agent could resume from it without reconstructing the full logic from chat alone.

Also keep a compact authenticity checklist visible throughout the writing line.
At minimum, repeatedly verify:

- method fidelity
- Result / artifact consistency
- claim-to-evidence alignment
- citation legitimacy
- figure and table provenance
- file inclusion integrity for the draft or bundle

## Workflow

### Phase 0. Ordering discipline

For paper-like deliverables, the safest default order is:

1. consolidate evidence and literature
2. if the line benefits from an explicit outline contract, record one or more outline candidates with `artifact.submit_paper_outline(mode='candidate', ...)`
3. if one outline should become the durable paper contract, select or revise it with `artifact.submit_paper_outline(mode='select'|'revise', ...)`
4. if the selected outline still exposes evidence gaps, launch an outline-bound `artifact.create_analysis_campaign(...)` before drafting
5. plan and generate decisive figures or tables
6. draft sections directly from the evidence and the current working outline; do not force extra outline rounds when direct drafting is clearer and safer
7. run harsh review and revision cycles
8. proof, package, submit `artifact.submit_paper_bundle(...)` when the bundle is ready, and then pass to `finalize`
9. if the final paper PDF exists and QQ milestone media is enabled in config, the bundle-ready milestone may attach that PDF once

Before real drafting, force one explicit planning pass that stabilizes at least:

- the current claim inventory
- the claim-evidence map skeleton
- the outline or outline candidates
- the figure/table plan
- the main evidence gaps

If these are still unstable, continue planning or route back for evidence instead of polishing prose early.

Do not rush into polished prose before evidence assembly, figure planning, and citation verification are far enough along to keep the draft honest.
If writing uncovers missing information, it is acceptable to return to focused literature search or artifact reading, but persist the findings immediately before resuming drafting.
Use web search to discover missing papers or references, and use `artifact.arxiv(paper_id=..., full_text=False)` when you need to actually read an arXiv paper rather than just locate it.
Only set `full_text=True` when the shorter view is insufficient for the needed detail.

For substantial paper-like writing, the durable writing plan should usually include:

- section goals
- paragraph or subsection intent when it materially affects correctness
- experiment-to-section mapping
- figure/table-to-data-source mapping
- citation/search plan
- verification checkpoints
- unresolved risks or downgrade candidates

Treat that plan as an execution contract.
Do not let drafting quietly outrun the current evidence inventory.

For reviewer-facing structure and section-level drafting contracts, read these references when the line needs sharper paper craft:

- `references/reviewer-first-writing.md`
- `references/section-contracts.md`
- `references/sentence-level-proofing.md`

### Phase 1. Evidence assembly

Before drafting, assemble the current evidence base:

- accepted baseline
- main experiment results
- analysis results
- code-level method changes
- prior limitations

Also build an experiment inventory before outlining:

- read all relevant experiments individually
- separate:
  - main-text evidence
  - appendix-only evidence
  - unusable or too-weak evidence
- verify that each planned main claim has at least one durable evidence path

If an experiment is too weak, too tiny, or poorly comparable, do not let it silently anchor a main claim.
As a strong default, experiments with very small evaluation support, such as `<=10` effective examples or similarly fragile sample counts, should not carry a main-text claim unless the user explicitly accepts that limitation and the caveat is written next to the claim.

If the draft will describe the method as a coherent proposal rather than a bag of edits:

- identify which components were actually implemented
- identify which components were validated by ablations or equivalent evidence
- do not elevate a component to “core method” status purely because it exists in code
- do not advertise a component as central when its measured gain is negligible and unconvincing without an additional non-metric rationale

Write down the intended claims first.

For each claim, ask:

- what artifact supports it?
- what metric or observable supports it?
- what code or diff explains it?
- what limitation or caveat belongs next to it?

When baseline numbers are used, also ask:

- does the setup really match?
- is the comparison fair enough for main-text use?

### Phase 2. Evidence-gap check

If evidence is missing, weak, or contradictory:

- identify the exact gap
- connect it to the affected claim
- produce one consolidated evidence-gap report or decision
- route back to `experiment`, `analysis-campaign`, or `scout` as needed

Do not scatter many tiny gap requests unless the quest truly needs that structure.

### Phase 3. Storyline and outline

The storyline should be evidence-led:

- what problem matters
- what baseline exists
- what limitation or opportunity was identified
- what intervention was tested
- what evidence supports the result
- where the result remains limited

For substantial lines, keep three layers explicit:

- `idea layer`
  - direction
  - problem
  - challenge
  - remedy
- `information layer`
  - strongest evidence
  - main figure or table
  - claim boundary
- `section layer`
  - title
  - abstract
  - introduction
  - related work
  - method
  - experiments
  - limitations
  - conclusion

A strong outline often benefits from a five-part story arc:

- motivation
- challenge
- resolution
- validation
- impact

When useful, reverse-engineer the story explicitly as:

- task
- challenge
- insight or intervention
- validation
- boundary of the claim

And a three-part contribution frame:

- theoretical or methodological contribution
- empirical contribution
- practical contribution

Do not optimize for rhetorical drama over factual support.

Outline-construction rules:

- if the paper structure is still unstable or several narratives look similarly plausible, it is often useful to create multiple candidates before choosing one
- each candidate should preserve `story`, `ten_questions`, and `detailed_outline`
- prefer a paperagent-like `story` structure:
  - `motivation`
  - `challenge`
  - `resolution`
  - `validation`
  - `impact`
- when the outline is fully structured, prefer a paperagent-like `ten_questions` block instead of loose outline notes
- each `detailed_outline` should usually preserve:
  - `title`
  - `abstract`
  - `research_questions`
  - `methodology`
  - `experimental_designs`
  - `contributions`
- for paper-like reports, prefer:
  - around `3` concrete `research_questions`
  - a methodological contribution
  - an empirical contribution
  - a practical contribution
- read all relevant experiments before fixing the outline
- read all relevant experiments individually rather than summarizing them as one blurred result bucket
- integrate baseline results only when setups truly match
- prioritize actual quest artifacts over older paper numbers when they conflict
- plan each main-text experiment deliberately rather than dumping all available runs into the story
- move weak, tiny, or non-central experiments to appendix or exclusions instead of overloading the main text
- prefer experimental ordering that starts with the main comparison, then ablations, then supporting analyses when the evidence supports that sequence
- verify that each planned figure or table has real source data before promising it in the outline
- keep method descriptions faithful to the actual implementation and accepted diffs; do not invent idealized components just because they improve the story
- keep the method as the protagonist of the outline while using baselines mainly for factual comparison and context

If the deliverable is a paper or paper-like report, pressure-test the outline against a compact question set before drafting:

- what exact problem or bottleneck matters here?
- what baseline or prior route exists?
- what is insufficient about that route on this quest?
- what exact intervention was implemented?
- why should that intervention help from a first-principles or mechanism view?
- what is the single strongest empirical validation?
- what limitations remain after the evidence is considered?

Also pressure-test it with a reviewer-first scan:

- can the title preserve the search-relevant keywords and still say what changed?
- can the abstract answer `problem`, `what we do`, `how at a high level`, and `main result` without jargon overload?
- can the introduction opening explain why the reader should keep going?
- is there an early figure or table plan that communicates the main result rapidly when appropriate?

The outline should already imply what belongs in:

- main text
- appendix
- exclusion log
- limitations
- future work

If a planned section has no credible evidence payload, shrink it before drafting instead of padding it with generic prose.
If the selected outline still requires uncollected evidence, route to an outline-bound `analysis-campaign` instead of drafting around the gap.

### Phase 3.1 Outline selection rubric

When several outline drafts exist, choose the winner explicitly rather than by vibe.

Prefer the outline that best satisfies the following paperagent-like rubric:

1. method fidelity
   - the method description matches the actual implementation and accepted diffs
   - no fictional modules, claims, or invented theoretical framing
2. evidence support
   - experimental claims are backed by real quest artifacts
   - planned figures and tables can be generated from available data
   - baseline comparisons are used only when setups are truly comparable
3. story coherence
   - the story progresses cleanly through motivation -> challenge -> resolution -> validation -> impact
   - outsiders can understand why the method is needed and how it is validated
4. research-question quality
   - the core research questions are concrete, decision-relevant, and well matched to the evidence inventory
5. experiment ordering quality
   - the main comparisons appear first when appropriate
   - ablations and supporting analyses are ordered logically
   - weak or tiny experiments are not incorrectly promoted into the main narrative
6. downstream draftability
   - the outline can be turned into a faithful draft without patching over obvious evidence gaps

When recording the selection, explain:

- why the winning outline is strongest
- which evidence-backed questions and experiments it activates
- what weaknesses remain
- whether another analysis pass is still needed before drafting

Do not leave this reasoning only in transient chat.
Record it in `paper/outline_selection.md` or a durable report/decision artifact.

### Phase 4. Drafting

Draft the sections that the evidence can currently support, typically:

- problem framing
- baseline and related setup
- method
- experiments
- analysis
- limitations
- conclusion

Method fidelity rules:

- do not describe components not present in the code or accepted diffs
- do not claim stronger evidence than the artifacts support
- downgrade speculative interpretation explicitly

Paper-oriented drafting defaults:

- title:
  - make it a one-line statement of the work rather than a vague slogan
  - preserve search keywords for the task, mechanism, or setting when possible
- abstract:
  - prefer the four-slot contract:
    - problem
    - what we do
    - how at a high level
    - main result or strongest evidence
  - avoid formula-heavy or jargon-heavy abstracts
- introduction:
  - motivate the concrete problem, not a generic field slogan
  - prefer `problem -> why it matters -> current bottleneck -> our remedy -> evidence preview`
  - state contributions only at the strength actually achieved
  - do not waste space on “This paper is organized as follows”; directly state contributions or evidence-bearing section roles instead
  - ensure the introduction can still survive after experiments finish
- related work:
  - position against the most relevant neighboring methods
  - explain distinction, not just similarity
  - do not attack prior work merely to make the current line look more novel
  - show field lineage and mechanism-level comparison when possible
- method:
  - begin with the baseline or essential background when that lowers reader burden
  - when possible, use a running example
  - prefer the order `running example -> intuition -> formalism`
  - follow actual implementation and accepted outline
  - when equations are used, define symbols clearly and keep them faithful to the code path
- experiments:
  - lead with the main comparison
  - follow with the analysis that explains why the result matters
  - ensure every quantitative interpretation points back to a table, figure, or artifact path
- limitations and conclusion:
  - state what the method does not show
  - do not let future work secretly carry unsupported present-tense claims

After the experiments section stabilizes, revisit the introduction and contribution framing.
If the experimental outcome changed the real story, rewrite the introduction so that motivation, claimed contributions, and significance match the actual results rather than the earlier hope.

### Phase 5. Citation integrity

Never generate references from memory.

For each important citation:

1. search from primary or reliable discovery sources
2. verify the citation exists in at least two compatible ways when feasible
3. prefer DOI-based BibTeX retrieval when DOI exists
4. confirm the cited claim actually appears in the source
5. record the citation immediately in the draft or references store
6. if verification fails, keep an explicit placeholder and mark it unresolved

Do not hide citation uncertainty.
Do not leave search findings only in transient chat state; persist them in the working draft or writing notes immediately.

### Phase 6. Figures and tables

If the deliverable includes figures or tables:

- generate them from durable experiment artifacts
- keep them publication-quality and readable
- ensure grayscale readability where relevant
- avoid dense, unreadable tables that only look correct in source form
- when appropriate, plan one early decisive figure or table that can anchor the reader's first pass through the paper

Selection rules:

- include only the most important rows in main-text tables
- prioritize strongest baselines, best configurations, and decisive comparisons
- do not exhaustively list every minor intermediate result in the main narrative
- verify that data for each planned figure or table actually exists before promising it

When generating visuals:

- prefer artifact-derived data over hand-copied numbers
- record the data source and generation script path when possible
- ensure captions and surrounding text match the actual figure contents exactly
- make captions self-contained enough that the reader can understand the main message without hunting through the body text
- if any synthetic or illustrative data is used for explanation, disclose that fact clearly and avoid mixing it with claimed empirical evidence

Each figure or table should be traceable to source artifacts.

### Phase 7. Claim-evidence map and self-review

Before the full adversarial self-review, run a quick reviewer-first pass and record it in `paper/reviewer_first_pass.md`.

That pass should answer:

- what a reviewer would conclude after reading only the title, abstract, introduction opening, and first decisive figure or table
- what is most likely to confuse that reviewer first
- what part of the first page still feels author-centered rather than reader-centered

Before declaring writing complete, build a claim-evidence map.

For each key claim, record:

- claim text or claim id
- evidence paths
- support status: supported, partial, unsupported
- caveats

Then run a harsh self-review:

- claim/evidence audit
- method fidelity audit
- experimental validity audit
- narrative and related-work audit
- presentation audit
- submission audit

Also check:

- experiment coverage audit: did you read and classify all relevant experiments individually?
- baseline comparability audit: are imported baseline numbers matched by setup?
- contribution audit: do the claimed contributions align with actual evidence?
- authenticity audit: do the method, results, figures, tables, and citations all trace back to real quest files and accepted artifacts?
- file-structure audit: do the bundle entry points and referenced files actually exist and open cleanly?

The review should be section-aware.
For each serious issue, record:

- section or file location
- severity: critical, major, or minor
- why it matters
- the concrete fix
- whether the issue blocks `finalize`

The self-review output should also make the verification logic externally legible:

- what was checked
- what evidence was used
- what passed
- what failed
- what was downgraded or deferred

When useful, add explicit “questions for the author” style prompts to expose what still needs proof or clarification.
If the draft is targeting publication quality, compare against a few strong nearby papers or templates only to raise quality, never to copy unsupported claims.

Run that review with an adversarial mindset:

- read the draft like a skeptical reviewer looking for the strongest rejection reason
- prefer deleting or downgrading an attractive but weak claim over defending it with rhetoric
- if a neutral outsider could not trace a claim back to concrete evidence, treat that as a writing failure, not as a presentation problem

When the draft is substantial enough to judge rather than merely sketch, open `review/SKILL.md` for an independent skeptical audit before you call the paper task done.
Use that review pass to decide whether the next route is further writing, a claim downgrade, a literature audit, a baseline recovery step, or a reviewer-linked follow-up experiment campaign.

### Phase 7.5. Revision loop

Do not stop after a single self-review pass.
For paper-style deliverables, a strong default is a five-pass revision loop:

1. fix critical accuracy and evidence issues
2. verify structural and checklist compliance
3. repair narrative flow and logical transitions
4. polish wording, citations, figures, and tables
5. run a final verification pass against the original claim-evidence map

For each pass:

- record what changed
- record what remains open
- ensure new text did not reintroduce old claim inflation
- update the revision ledger or working note immediately

If the draft still fails a critical pass, do not pretend the revision loop is complete.

### Phase 8. Visual proofing

If the output is paper-style:

- compile it when relevant
- save compile logs, preferably through `bash_exec` session ids or exported `bash_exec` logs
- render page images or an equivalent preview
- read the rendered output page by page
- audit first page, first main figure, table overflow, caption balance, and page-limit risk

For markdown-only deliverables, perform an equivalent rendered read-through rather than checking only source text.
During that rendered read-through, explicitly inspect the first page for title clarity, abstract readability, contribution visibility, and early figure/table effectiveness.

### Phase 9. Submission gate

Before marking the writing line complete, verify:

- venue or template compliance if applicable
- page limit
- anonymization if applicable
- references integrity
- appendix or checklist placement
- entry-file openability
- artifact completeness
- handoff readiness

If a critical packaging issue remains, mark the stage as blocked or warn explicitly.

## Required file expectations

### `claim_evidence_map.json` minimum shape

```json
{
  "claims": [
    {
      "claim_id": "C1",
      "claim_text": "The method improves F1 on the target benchmark.",
      "support_status": "supported",
      "evidence_paths": [
        "artifacts/runs/run-main-001.json",
        "experiments/main/run-main-001/metrics.json"
      ],
      "caveats": ["Gain is strongest on split A."]
    }
  ]
}
```

### `figure_catalog.json` minimum shape

```json
{
  "figures": [
    {
      "id": "F1",
      "path": "paper/figures/fig1.pdf",
      "script_path": "paper/figures/generate_figures.py",
      "source_artifacts": ["artifacts/runs/run-main-001.json"],
      "claim_ids": ["C1"],
      "style_notes": {
        "grayscale_safe": true
      }
    }
  ]
}
```

### `table_catalog.json` minimum shape

```json
{
  "tables": [
    {
      "id": "T1",
      "path": "paper/tables/table1.tex",
      "source_artifacts": ["artifacts/runs/run-main-001.json"],
      "claim_ids": ["C1"],
      "layout_notes": {
        "overflow_checked": true
      }
    }
  ]
}
```

### `compile_report.json` minimum shape

```json
{
  "success": true,
  "status": "passed",
  "entry_path": "paper/main.tex",
  "pdf_path": "paper/build/paper.pdf",
  "log_path": "paper/build/latexmk.log",
  "page_images_manifest_path": "paper/proofing/page_images_manifest.json",
  "visual_recheck_completed": true
}
```

### `page_images_manifest.json` minimum shape

```json
{
  "pages": [
    {
      "page": 1,
      "image_path": "paper/proofing/page-001.png",
      "audit_notes": ["Main figure readable", "No visible overflow"]
    }
  ]
}
```

### `submission_checklist.json` minimum shape

```json
{
  "overall_status": "ready",
  "checks": [
    {
      "key": "references_integrity",
      "status": "pass",
      "notes": "Verified citations recorded."
    }
  ],
  "blocking_items": [],
  "handoff_ready": true
}
```

## Memory rules

Stage-start requirement:

- begin every writing pass with `memory.list_recent(scope='quest', limit=5)`
- then run at least one write-relevant `memory.search(...)` before drafting, major revision, or claim restructuring
- if several idea or experiment lines exist, narrow retrieval to the line actually supporting the current draft and do not mix evidence memory from another line unless you are explicitly comparing claims

Use memory for reusable lessons only, such as:

- citation pitfalls
- writing-stage failure patterns
- strong narrative framing lessons

Do not use memory as the only record of the draft state.

Preferred memory usage:

- quest `papers`:
  - related-work notes
  - citation verification notes
  - paper-specific source reminders
- quest `decisions`:
  - claim downgrades
  - scope reductions
  - evidence-gap route changes
- quest `knowledge`:
  - stable writing constraints
  - venue or packaging caveats
  - distilled review lessons that still matter later in this quest
- global `knowledge`:
  - reusable writing playbooks
  - stable citation or proofing heuristics
- global `templates`:
  - reusable claim-evidence map patterns
  - review checklist structures
  - submission packaging templates

Use tags to refine meaning when helpful, for example:

- `stage:write`
- `type:writing-playbook`
- `type:evidence-ledger`
- `type:citation-check`
- `type:proofing-lesson`

When calling `memory.write(...)`, pass `tags` as an array like `["stage:write", "type:writing-playbook", "type:evidence-ledger"]`, not as one comma-joined string.

Recommended read timing:

- before outline drafting:
  - consult quest `papers`, `decisions`, and `knowledge`
  - consult `references/reviewer-first-writing.md` and `references/section-contracts.md` when the narrative shape is still unstable
- before final completion:
  - re-check quest `decisions` and writing-related `knowledge`
- after a serious writing failure:
  - consult quest and global writing failure patterns before retrying
  - consult `references/sentence-level-proofing.md` when the failure is mainly about readability, wording, or sentence quality

Write quest memory when:

- a citation or evidence mistake is likely to recur later in the quest
- a review lesson should shape the next revision
- a claim boundary or package constraint should not be rediscovered

Stage-end requirement:

- if writing produced a durable citation lesson, review lesson, claim-boundary rule, or packaging constraint, write at least one `memory.write(...)` before leaving the stage

Promote to global memory only when the lesson is clearly reusable beyond this quest.

## Artifact rules

Typical artifact sequence:

- report artifact for evidence assembly or outline readiness
- report or decision artifact for evidence gaps
- milestone or report artifact for draft readiness
- report artifact for review/proofing/submission outputs
- decision artifact if the quest should return to another stage

Preferred artifact choices:

- use `report` for:
  - outline candidate comparison
  - outline readiness
  - evidence assembly summaries
  - self-review outputs
  - proofing outputs
  - submission-gate summaries
- use `decision` for:
  - evidence gaps that force route changes
  - downgrade / defer / stop choices
  - the final go-to-finalize judgment
- use `milestone` for:
  - draft readiness when a user-facing checkpoint helps
- use `approval` when the user explicitly confirms a submission-critical choice
- use `artifact.submit_paper_outline(mode='candidate'|'select'|'revise', ...)` for the real outline lifecycle instead of leaving outline choice only in prose
- use `artifact.submit_paper_bundle(...)` before leaving the writing stage when the draft, plan, references, and packaging evidence are durable enough
- continue writing on the parent idea branch/worktree after analysis slices finish; do not open a separate paper-only branch unless a recovery situation explicitly requires it

Keep each writing artifact tightly linked to evidence paths.

## Hard integrity rules

- do not invent citations
- do not invent experiments
- do not invent metrics
- do not invent method components
- do not write past missing evidence
- do not silently treat unsupported claims as settled

## Failure and blocked handling

Common blocked states:

- evidence_gap
- citation_unverified
- method_description_mismatch
- proofing_failed
- submission_gate_failed

Record blocked writing clearly and route the quest to the correct next step.

## Extra references

Use these references when the deliverable is paper-like and you need a denser operating checklist:

- `references/revision-checklist.md`
- `references/paper-section-playbook.md`

## Exit criteria

Exit the write stage only when one of the following is durably true:

- the current draft is evidence-complete enough for `finalize`, including a selected outline and a durable paper bundle manifest when the deliverable is paper-like
- a clear evidence gap has been recorded and the quest is routed backward
- a packaging or proofing blocker has been recorded and the next action is explicit
