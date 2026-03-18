---
name: idea
description: Use when a quest needs concrete hypotheses, limitation analysis, candidate directions, or a selected idea relative to the active baseline.
---

# Idea

Use this skill to turn the current baseline and problem frame into concrete, literature-grounded, testable directions.

## Interaction discipline

- Treat `artifact.interact(...)` as the main long-lived communication thread across TUI, web, and bound connectors.
- If `artifact.interact(...)` returns queued user requirements, treat them as the highest-priority user instruction bundle before selecting or refining ideas.
- Immediately follow any non-empty mailbox poll with another `artifact.interact(...)` update that confirms receipt; if the request is directly answerable, answer there, otherwise say the current subtask is paused, give a short plan plus nearest report-back point, and handle that request first.
- Emit `artifact.interact(kind='progress', reply_mode='threaded', ...)` when there is real user-visible progress: the first meaningful signal of long work, a meaningful checkpoint, or a concise keepalive if active work has drifted beyond roughly 10 to 30 tool calls without a user-visible update.
- Keep progress updates chat-like and easy to understand: say what changed, what it means, and what happens next.
- Default to plain-language summaries. Do not mention file paths, artifact ids, branch/worktree ids, session ids, raw commands, or raw logs unless the user asks or needs them to act.
- Keep ordinary subtask completions concise. When the idea stage actually finishes a meaningful deliverable such as a selected idea package, a rejected-ideas summary, or a route-shaping ideation checkpoint, upgrade to a richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` report.
- That richer idea-stage milestone report should normally cover: the final selected or rejected direction, why it won or lost, the main remaining risk, and the exact recommended next stage or experiment.
- That richer milestone report is still normally non-blocking. If the next experiment or route is already clear from durable evidence, continue automatically after reporting instead of waiting.
- If the runtime starts an auto-continue turn with no new user message, keep advancing from the active requirements and current durable state instead of re-answering the previous user turn.
- Message templates are references only. Adapt to the actual context and vary wording so updates feel natural and non-robotic.
- Use `reply_mode='blocking'` only for real user decisions that cannot be resolved from local evidence.
- For any blocking decision request, provide 1 to 3 concrete options, put the recommended option first, explain each option's actual content plus pros and cons, and wait up to 1 day when feasible. If the blocker is a missing external credential or secret that only the user can provide, keep the quest waiting, ask the user to supply it or choose an alternative, and do not self-resolve; if resumed without that credential and no other work is possible, a long low-frequency wait such as `bash_exec(command='sleep 3600', mode='await', timeout_seconds=3700)` is acceptable. Otherwise choose the best option yourself and notify the user of the chosen option if the timeout expires.
- If a threaded user reply arrives, interpret it relative to the latest idea progress update before assuming the task changed completely.

## Stage purpose

The idea stage should not generate vague inspiration.
It should produce executable hypotheses tied to:

- the active baseline
- the current codebase
- the accepted evaluation contract
- the strongest relevant prior work

This stage is not just "brainstorming".
It is the research-direction selection stage.
It should normally create a new candidate direction branch and node; it does not by itself decide the next optimization round.
The output must survive three checks at once:

- novelty or at least clear research value
- feasibility in the current repo and resource budget
- manuscript defensibility if the line later becomes a paper claim

Finishing one idea deliverable is not quest completion.
After reporting a completed idea package, continue into the next justified stage unless a real blocking decision is still unresolved.

When the quest disables research-paper delivery, keep manuscript defensibility secondary to:

- algorithmic value
- feasibility
- clean experimental follow-through
- durable recording of why this direction should be the next measured attempt

Before starting a genuinely new round, default to the current research head as the foundation.
However, you may deliberately choose a different foundation when the durable evidence says it is better.
When the best starting point is not obvious, inspect `artifact.list_research_branches(...)` first and compare:

- current head
- baseline foundation
- strongest recent measured branch
- older but cleaner branch

If you do not use the default current head, record the reason explicitly in the new idea submission.
Treat a newly accepted branch as one durable research round.
If the active branch already has a durable main-experiment result and you are starting a genuinely new optimization round, prefer creating a child branch from the chosen foundation rather than revising the old branch in place.

At the direction level, prefer elegant algorithmic or theoretical improvements over brute-force cost-for-performance tradeoffs whenever possible.

This stage should preserve the strongest old DeepScientist direction-selection logic:

- understand the baseline and its failure modes
- search related work broadly before claiming an idea is good
- derive limitations
- produce a compact set of candidate ideas from an explicit direction set
- rank them with explicit tradeoffs
- choose a direction with a clear evidence-based decision path
- ensure the selected direction is manuscript-defensible rather than merely implementation-plausible

Use a compact search discipline during ideation:

- first identify the current strongest line from existing results, literature, and branch history
- treat that line as the current `incumbent`
- keep only a small `frontier`, usually 2 to 3 serious alternatives
- ensure the frontier is meaningfully differentiated rather than the same idea renamed
- prefer selecting from existing evidence over expanding the candidate list indefinitely

Candidate sets should usually cover some mix of:

- a strong local refinement of the incumbent
- an orthogonal alternative that addresses the same bottleneck differently
- a cleaner or more defensible route with lower conceptual complexity

Do not default to “run a small experiment and see” as the way to break ties.
Break ties primarily through careful reasoning over:

- existing experiment results
- failure patterns
- related-work overlap
- code-path feasibility
- claim defensibility

## Non-negotiable rules

- Do not claim novelty without a written related-work comparison.
- Do not select an idea before checking whether close prior work already did it.
- Do not confuse "I can implement this" with "this is a publishable or useful research direction".
- Do not treat a weak literature search as sufficient because the idea sounds elegant.
- Every fresh idea build or idea-refinement pass must begin with:
  - a memory sweep, and
  - an external literature sweep.
- Every fresh or resumed idea pass must update `artifacts/idea/literature_survey.md` or an equivalent durable survey report before a direction is promoted.
- Every survey update must explicitly separate:
  - reused prior survey coverage
  - newly added papers or comparisons from this pass
  - still-missing or unresolved overlaps
- When a web/search tool is available, actively use it.
  Prefer web search for paper discovery, usually targeting arXiv first, then expand with citation and open-web search for neighborhood coverage.
- When a concrete arXiv paper needs to be read, compared, or summarized, use `artifact.arxiv(paper_id=..., full_text=False)`.
  Keep search in web discovery; use `artifact.arxiv(...)` for reading shortlisted papers, and set `full_text=True` only when needed.
- Before opening a broad new search, check quest and global memory with `memory.search(...)` and reuse existing paper notes, idea notes, and knowledge cards.
- Search for genuinely missing, newly relevant, or more recent papers whenever possible.
  Do not rerun the same broad search without stating what gap the new search is meant to close.
- Do not introduce a new dataset or a new evaluation regime unless the quest scope explicitly changed.
- Do not rely on human evaluation or subjective assessment for idea validation; the eventual experiment must remain automatable with code and accepted metrics.
- Treat ideation as read-heavy and write-light: inspect code and papers, but avoid substantial implementation during this stage.
- Do not propose directions that require new datasets.
- Do not default to brute-force engineering escalation when a cleaner first-principles direction is available.
- Do not keep generating more ideas once a small, clearly ranked frontier already exists.
- Do not treat superficial variation as a new idea if the expected mechanism and evidence burden are effectively unchanged.
- Do not promote a direction unless you can explain:
  - what limitation it targets
  - why prior methods do not already solve it
  - what evidence would later be needed to defend the claim
- If the idea is not novel but still worth doing, state that honestly as:
  - replication value
  - transfer-to-new-setting value
  - stronger evidence on an unresolved question
  - negative-result value
  - infrastructure/platform value

## Use when

- the baseline is ready
- the task and metric contract are already clear
- the quest needs a concrete research direction
- the current idea line failed and a new direction is needed

## Do not use when

- the baseline gate is unresolved
- the quest still lacks basic problem framing
- the next step is obviously a write-up or finalization rather than ideation

## Preconditions and gate

Before ideation, confirm:

- there is an active or accepted baseline
- the dataset and metric contract are explicit
- the relevant code path and papers are available
- the strongest obvious related-work cluster can be searched from available references and tools

If these are still unclear, route back to `baseline` or `scout`.

## Companion skill rule

`idea` is the anchor skill for direction selection.
However, when the quest still needs literature grounding or novelty checking, actively open `scout` as a companion skill before final idea selection.

In practice:

- use `scout` to expand the paper set, search adjacent methods, and clarify the baseline landscape
- use `idea` to convert that landscape into limitations, candidate directions, and a selected idea

Do not skip the `scout` pass just because the quest is already in the `idea` stage.

## Truth sources

Use:

- baseline artifacts and verification notes
- baseline paper and source repo
- current codebase and recent diffs
- scout notes and paper memory cards
- prior failed runs and decisions
- current task constraints
- quest and global memory cards returned by `memory.list_recent(...)` and `memory.search(...)`
- prior literature survey reports and related-work artifacts
- web-search discovery results for arXiv and related sources
- paper-reading notes produced after using `artifact.arxiv(...)`
- citation trails and open-web search results for nearby work
- citation trails from the baseline paper and strongest nearby papers
- recent papers that share the same task, metric, dataset, mechanism, or bottleneck

Do not rank ideas on style alone.
Rank them on evidence, feasibility, and testability.

## Related-work and novelty mandate

Before you choose a direction, perform a broad but bounded literature sweep.

The sweep must be grounded in actual retrieval, not recall alone.
If durable quest memory already contains a recent and explicit survey, reuse it first and search externally only for the missing buckets, newer papers, or unresolved overlaps.

When tools allow it, combine:

- `memory.search(...)` and recent memory reads
- web search for arXiv and adjacent sources
- `artifact.arxiv(paper_id=..., full_text=False)` for actually reading shortlisted papers
- citation expansion or open-web search for follow-up papers, code, and comparisons

The sweep should cover at least these search angles:

- direct same-task / same-dataset / same-metric competitors
- methods using the same mechanism or main lever you are considering
- papers targeting the same failure mode or bottleneck
- strong recent papers that may have closed the gap already

When the direct neighborhood looks saturated or too incremental, extend the sweep to adjacent conceptual neighborhoods:

- optimization methods targeting the same instability or objective mismatch
- representation-learning methods targeting the same information bottleneck
- signal-processing, geometry, probabilistic, or control-inspired methods addressing an analogous failure mode
- methods from neighboring tasks that solve the same structural problem under a different surface form

The point is principled translation, not superficial import.
Borrow the core mechanism or mathematical idea only if you can explain why it should survive translation into the current codebase and metric contract.

For each promising idea, you must be able to answer:

- which papers are the closest prior art?
- what exactly is the overlap with your proposed mechanism?
- what is still missing, weak, or untested in those papers?
- if they already did most of it, why is this still worth pursuing?

The goal is not to cite everything on Earth.
The goal is to avoid fake novelty and to identify a direction that has credible research value.

Recommended search outputs:

- a compact related-work map
- a closest-prior-work table
- a novelty / value verdict for each serious candidate
- a paper bucket split:
  - `core papers`
  - `closest competitors`
  - `adjacent inspirations`
  - `watchlist / uncertain relevance`

For a more detailed search and triage method, read `references/related-work-playbook.md`.

If the search is still too thin to support a novelty or value judgment, the idea stage is not ready to end.

## Required durable outputs

The idea stage should usually leave behind:

- a limitations analysis
- a literature survey report
- a survey-delta section that marks:
  - reused findings
  - newly retrieved papers this pass
  - unresolved gaps or watchlist items
- a related-work map
- a novelty and research-value audit
- `2-5` candidate ideas
- a selected idea or explicit rejection of the current line
- a durable Markdown idea draft that is finalized before the accepted idea is submitted
- one or more memory cards for reusable rationale
- one or more quest `papers` cards for the strongest papers or search clusters
- an idea artifact and a decision artifact

Recommended durable intermediate outputs:

- an outline-style direction note with:
  - executive summary
  - current baseline results and metric direction
  - codebase analysis
  - dataset analysis
  - mathematical problem formulation
  - baseline methods as special cases
  - five actionable research directions
  - evaluation metrics and success criteria
  - infrastructure and constraint notes
  - claim boundary

When producing a fuller research-outline style note, prefer a direct-agent-like structure:

- `Executive Summary`
- `Codebase Analysis`
- `Limitations / Bottlenecks`
- `KPIs`
- `Research Directions`
- `Risks & Mitigations`

Do not force this structure for every tiny ideation turn, but use it when the quest needs a serious research-plan artifact.

Recommended durable files:

- `artifacts/idea/literature_survey.md`
- `artifacts/idea/related_work.md`
- `artifacts/idea/limitations.md`
- `artifacts/idea/candidates.md`
- `artifacts/idea/selected_idea.md`
- `artifacts/idea/research_outline.md`

When producing the literature survey report, prefer the structure in `references/literature-survey-template.md`.

When producing a full research-outline style note, prefer the detailed structure in `references/research-outline-template.md`.

When the runtime supports durable knowledge cards, also preserve:

- incident or failure-pattern lookups relevant to the mechanism
- a reusable knowledge card for the selected idea hypothesis

## Thinking protocol

Use the old PI discipline here too.
Your analysis should be:

- hypothesis-driven: viewpoint first, evidence second
- pyramid-shaped: conclusion first, then reasons, then action
- MECE where possible:
  - data
  - model
  - objective
  - optimization or training dynamics
  - inference
  - evaluation protocol
  - infrastructure
- SCQA-compatible:
  - situation
  - complication
  - research question
  - answer hypothesis plus `2-3` competing hypotheses

Do not dump disconnected observations.
Turn them into a direction argument.

For a more explicit end-to-end reasoning sequence, read `references/idea-thinking-flow.md`.

## Workflow

### 1. Lock the success target and contribution frame

Before generating ideas, state:

- the primary metric and whether higher or lower is better
- the strongest baseline number with source path
- the expected contribution type:
  - `Insight`
  - `Performance`
  - `Capability`
- the problem importance in one sentence
- the main challenge or bottleneck in one sentence
- whether the direction is emerging, stable, or late relative to the current literature wave
- the risk that the direction is valuable but may still be under-recognized
- one sentence for the intended increment over the strongest baseline
- what new knowledge the reader would gain if this line works

If the metric, baseline value, or contribution frame is unclear, stop and clarify before ideation.

### 1.1 Plan the ideation investigation

Before deep searching, write a compact plan for:

- which limitation or bottleneck you are investigating first
- which literature buckets you will search
- which evidence would validate or refute your current hypothesis
- which prior ideas, findings, or failed attempts must not be duplicated blindly
- a short first-principles memo explaining what you currently believe before you let the literature reshape that belief

The plan does not need to be long.
It does need to make the search strategy explicit.

### 1.2 Reuse durable memory before searching again

Before the open-web sweep, actively check what the quest already knows.

At minimum:

- inspect recent quest `papers`, `ideas`, `decisions`, and `knowledge`
- inspect recent global `papers`, `knowledge`, and `templates` if the topic looks reusable
- inspect the latest `artifacts/idea/literature_survey.md` or equivalent survey report when it exists
- run `memory.search(...)` on:
  - the baseline method name
  - the task and dataset
  - the likely mechanism keywords
  - the strongest current candidate labels
- record which buckets are:
  - already covered
  - stale or incomplete
  - still missing

If the quest already has a strong survey and paper memory set, do not blindly repeat the whole search.
Only search the open web for uncovered gaps, newer papers, or unclear overlaps.
Every new external query should close one of these explicit gaps:

- missing paper bucket
- newer-than-last-survey refresh
- unresolved overlap with a candidate idea
- verification of a paper that might block novelty or value claims

### 2. Run the related-work sweep

Search broadly enough to cover the strongest obvious competitors and neighboring methods.

Use the runner's search tooling actively.
When available, use web search for discovery, often targeting arXiv first, then use citation or broader web search to expand the closest-neighbor cluster.

At minimum, inspect:

- the baseline paper references
- papers cited by the closest prior methods
- papers that cite the baseline or core method, when available
- recent papers on the same task, dataset, metric, or failure mode
- implementation repositories for the strongest nearby methods, when relevant

Keep a compact search ledger while you work.
For each meaningful search query or paper cluster, record:

- query text
- source, such as `memory`, `arXiv`, or open web
- why you issued the query
- which papers were newly added
- which previously known papers were re-confirmed
- which gaps remain after this pass

Do not treat the search ledger as optional prose.
It is the durable reason why the next idea pass should search only the remaining gaps instead of restarting broad discovery from zero.

For the shortlist of closest papers, record:

- paper identifier and year
- core mechanism
- task / dataset / metric overlap
- what claim it already supports
- what gap, weakness, or open edge remains
- whether it reduces the novelty of your candidate

Search guidance:

- prefer recent work when the area is moving quickly, especially `2023-2027`
- do not ignore older seminal papers if they are the real origin of the idea
- use purpose-driven search rather than quota-chasing
- repeat the search multiple times with refined queries when novelty or motivation remains uncertain
- when resuming idea work, start from the latest survey report and search only for the still-missing neighborhood or newer papers

At the start of the sweep, classify the challenge type in one sentence, for example:

- information bottleneck
- optimization instability
- weak inductive bias
- noisy supervision
- poor calibration
- brittle inference procedure

Then use that abstraction to widen the search.
This prevents the stage from staying trapped in only same-keyword literature when the deeper mechanism may have better inspirations elsewhere.

Cross-domain exploration is allowed and encouraged when it sharpens the idea.
Map the failure type to `2-3` adjacent domains when useful, such as:

- optimization
- information theory
- signal processing
- statistical learning
- systems or inference engineering

Look for principles that can be translated into the current codebase, not copied blindly.

Do not stop at one or two papers if the area is active.
Keep going until the strongest obvious overlaps are mapped.

Also compare against prior quest ideas and findings when they exist:

- avoid rediscovering an already rejected line without new evidence
- explain how the current candidate differs from prior attempts
- explicitly note if the new direction is a refinement, branch, or replacement

### 3. Reconstruct the baseline line

State clearly:

- what the baseline does
- what assumptions it depends on
- where it appears to fail
- which metrics matter most
- what resource or repository constraints matter

Also identify concrete code touchpoints:

- train or eval entrypoints
- dataset loaders and preprocessing
- model, loss, and metric code
- where a future method difference would actually land

For each serious baseline method, also rate improvement potential as:

- `HIGH`
- `MEDIUM`
- `LOW`

and justify the rating from:

- algorithmic flexibility
- implementation complexity
- coupling or maintainability constraints
- room for principled extension

### 4. Produce a limitations map

List the most decision-relevant limitations, such as:

- obvious architectural bottleneck
- error concentration on a known case type
- mismatch between objective and evaluation metric
- weak robustness
- compute or efficiency bottleneck
- missing information flow or representation quality

Do not confuse random inconveniences with true research limitations.

The limitations map should be concrete enough that each top limitation can support one falsifiable research question.

For each top limitation, also record:

- why it matters for the main metric
- what evidence currently supports it
- whether it is likely a data, model, objective, optimization, inference, evaluation, or infrastructure issue
- `2-4` concrete root-cause hypotheses

### 5. Add mathematical and mechanism framing

Where possible, express the baseline as a concrete optimization or algorithmic object rather than only prose.

For each serious line, state:

- the baseline as a special case or constrained version
- what assumption or constraint may be hurting performance
- what relaxation, extension, or alternative information flow might help
- what competing hypothesis could explain the same problem

Also decompose the broader research problem into `3-5` sub-problems when useful, so later experiments can target them separately.

This step is important because it prevents superficial "just add module X" ideation.

### 6. Generate direction options first, then candidate ideas

First derive exactly five actionable research directions whenever the space is not already tiny.
Rank them from higher to lower expected return on investment.

For each direction, specify:

- targeted limitation
- problem plus solution approach
- key discipline and technique
- code-level implementation sketch
- metrics to watch and success threshold
- abandonment criteria
- risks and confounders
- reader-facing takeaway
- defensibility evidence package

At the direction stage, these should remain exploration directions rather than full implementation plans.
Favor directions that:

- solve the core insufficiency more elegantly
- avoid unnecessary complexity or compute cost
- fit the existing architecture
- create genuinely differentiated research value

When possible, make the direction-generation step explicitly two-layered:

1. abstract direction:
   - the core conceptual thrust
   - the first-principles rationale
   - why it is more elegant than brute-force scaling
2. repo-grounded translation:
   - where it could land in the current codebase
   - what the smallest meaningful implementation would be
   - what evidence would falsify it quickly

Then reduce to a compact `2-5` candidate set for actual selection.
When operating in a tightly scoped idea assignment, prefer converging to one final idea rather than dumping many half-baked options.

When the search space is not tiny, try to preserve diversity in the final candidate set:

- one conservative or low-risk line
- one higher-upside line
- one elegance-first line with low engineering burden

If all surviving candidates are minor variants of the same mechanism family, widen the search once before converging.

When the quest needs a stronger strategist-style ideation pass, prefer a two-layer direct-agent framing for each direction:

1. conceptual thrust
   - one memorable abstract phrase
2. first-principles rationale
   - why the direction should work from mathematical, algorithmic, or logical reasoning
3. path to an elegant solution
   - why it is better than brute-force scaling or expensive engineering
4. innovation factor
   - what appears genuinely unexplored or underexplored
5. research value justification
   - why the direction should score well on usefulness, quality, or exploration value
6. optional cross-domain inspiration
   - where the idea borrows its structural intuition, if relevant

For each candidate idea, specify:

- mechanism
- expected gain
- main risk
- required files or components
- likely metric effect
- cheapest falsification path
- strongest competing hypothesis
- closest prior work and novelty / value verdict
- whether it overlaps too much with prior quest ideas or prior failed findings

Treat each serious candidate as a compact decision package, not a slogan.
For every candidate that survives initial triage, make sure you can state:

- target limitation
- why current methods still fail here
- the smallest credible implementation surface in the current repo
- the primary metric that would matter first
- the cheapest falsification path
- the abandonment condition
- the reader-facing payoff if it works
- the exact reason it is still worth trying despite the closest prior work

When possible, also specify:

- why current methods fail on this point
- reader-facing takeaway if the direction works
- minimum defensibility evidence package needed later for writing

Prefer ideas that can be tested in the current repo with minimal ambiguity.
If a candidate requires a large refactor, call that out explicitly and propose a smaller variant.

### 7. Score the candidates

Score each candidate along explicit axes:

- relevance to the limitation
- feasibility in the current codebase
- expected upside
- falsifiability
- implementation cost
- evaluation clarity
- risk of confounding
- novelty headroom
- research value even if not fully novel
- expected information gain
- reusability as a platform capability

Also keep a compact strategist-style score lens when useful:

- `utility_score`
- `quality_score`
- `exploration_score`

If these are used, explain the scores in prose rather than treating them as magic numbers.
Use them as a secondary decision lens, not as a substitute for evidence-backed reasoning.

Avoid "best sounding" choices.
Prefer the best-explained choice.

If a candidate scores weakly on novelty but strongly on research value, label that explicitly instead of pretending it is novel.

### 7.1 Lightweight quality gate before selection

Run the final candidate through the quality gate in `references/selection-gate.md`.

At minimum, explicitly score:

- novelty
- falsifiability
- feasibility
- evidence quality
- constraint fit

If the total is below `7/10`, do not promote the idea yet.
Either refine once more or record a blocked / reject decision with the exact weakness.

### 8. Select, branch, reject, or route back

The idea stage should end with one of:

- a selected idea ready for `experiment`
- a decision to branch and keep more than one line alive
- a rejection of all current ideas and a return to `scout`
- a blocked state if the real issue is missing evidence rather than missing creativity

Before selecting, perform a narrative defensibility precheck:

- who is the target reader or evaluator of the claim?
- why should they care?
- what is the one falsifiable research question for this direction?
- what evidence package would be needed later to defend it?
- what is the claim boundary?
- what is the strongest nearby prior work, and what remains differentiating here?
- why is this the highest-leverage direction to invest in now, rather than merely one direction that could work?

If the direction is not defensible even in outline form, do not promote it just because it is implementable.

If multiple directions remain plausible and the choice is materially preference-sensitive, ask the user for a structured decision instead of pretending the tradeoff is objective.

If the real issue is that literature coverage is weak or novelty is uncertain, route back to `scout` rather than forcing an idea selection.

When the stage reaches a route-shaping outcome, notify the user through `artifact.interact(...)` deliberately:

- use a richer threaded `milestone` update when a selected idea package, a rejected-ideas summary, or a route back to `scout` is durably recorded
- the update should name the winner or rejection result, the strongest supporting evidence, the main residual risk, and the exact recommended next stage
- if more than one candidate remains genuinely plausible and preference-sensitive, use `reply_mode='blocking'` for the user decision instead of pretending the choice is objective

## Idea output contract

The selected idea should be recorded in a form that the `experiment` stage can follow without drift.
Use the handoff template in `references/selection-gate.md`.

At minimum, preserve:

- a stable idea id
- a falsifiable claim tied to metric and direction
- the code-level plan and minimal experiment
- the literature relation and evidence pointers
- the strongest alternative hypothesis

## Idea quality rules

Good ideas should be:

- literature-grounded
- specific
- executable
- testable
- comparable against baseline
- cheap enough to falsify
- either genuinely novel or clearly research-valuable
- narratively defensible to a real reader
- constraint-compatible with the current dataset and evaluation setup

Weak ideas often look like:

- pure ambition without a mechanism
- a large rewrite without a clean test
- a metric claim without a plausible path to improvement
- a direction that requires a new dataset or evaluation regime without scope approval
- an apparent novelty that collapses after reading nearby papers
- a direction with no clear reader payoff even if it works
- a mechanism borrowed from another domain without translation to this codebase
- an idea that cannot be validated automatically with current metrics
- a brute-force scale-up disguised as a research idea

## Novelty and research-value rules

Use the novelty and value labels from `references/selection-gate.md`.

Do not force every good direction into the `novel` bucket.
But do require every selected direction to land in either:

- `novel`, or
- `incremental but valuable`

If it lands in `not sufficiently differentiated`, reject it or send it back for refinement.

## Code-change rule

The idea stage is primarily a planning and reasoning stage.

- avoid large code changes during ideation
- only perform a tiny code or config inspection change if it is necessary to verify feasibility
- if major implementation seems necessary just to understand the idea, that is a sign to stop and sharpen the idea first

## Memory rules

Stage-start requirement:

- begin every idea pass with `memory.list_recent(scope='quest', limit=5)`
- then run at least one idea-relevant `memory.search(...)` before broad new ideation or literature expansion
- before proposing a new idea, explicitly review prior quest idea records and experiment outcomes so the new proposal builds on actual history instead of rediscovering old work
- treat prior idea lines and experiment lines as reference material, not as the active idea contract unless you intentionally select and continue that line

Store reusable reasoning in memory, such as:

- literature survey summaries
- search-ledger conclusions
- related-work judgments
- limitation summaries
- idea tradeoff notes
- failure patterns that should shape future ideation
- novelty caveats and research-value boundaries

Do not let the only copy of the idea rationale live in chat.

Preferred memory usage:

- quest `papers`:
  - literature survey summaries
  - arXiv or paper-cluster notes
  - related-work notes
  - closest-prior-work comparisons
  - citation-grounded method observations
- quest `ideas`:
  - candidate direction records
  - selected idea handoff notes
  - rejected idea rationale when it may matter later
- quest `decisions`:
  - selection tradeoffs
  - branch or reject choices
  - user-sensitive route resolutions
- quest `knowledge`:
  - distilled limitation patterns
  - stable novelty caveats
  - research-value boundaries worth reusing later in this quest
- global `knowledge`:
  - reusable ideation heuristics
  - cross-domain translation lessons
- global `templates`:
  - reusable related-work maps
  - selection-gate checklists

Use tags to sharpen retrieval when helpful, for example:

- `stage:idea`
- `type:related-work`
- `type:literature-survey`
- `type:novelty-check`
- `type:selection-rationale`
- `topic:<mechanism>`

When calling `memory.write(...)`, pass `tags` as an array like `["stage:idea", "type:selection-rationale", "topic:<mechanism>"]`, not as one comma-joined string.

Recommended read timing:

- before any new paper search:
  - run `memory.search(...)` over the baseline, task, dataset, mechanism, and current idea labels
- before broad new ideation:
  - review prior quest `ideas`, experiment results, failure patterns, and decision notes in detail
- before wide literature search:
  - consult quest `papers`, `ideas`, experiment lessons, and `decisions`
- before final selection:
  - re-check quest `ideas`, `decisions`, and `knowledge`
- after a failed or rejected idea line:
  - check quest and global ideation lessons before proposing the next line

Stage-end requirement:

- if ideation produced a durable survey conclusion, selected-idea rationale, rejected-idea lesson, or novelty caveat, write at least one `memory.write(...)` before leaving the stage
- at least one quest memory card should preserve the survey delta with retrieval hints, such as:
  - covered paper buckets
  - unresolved buckets
  - paper identifiers or arXiv ids
  - search-window notes like `searched_through: 2026-03`

When writing paper memory cards, include enough metadata to avoid redundant search later, such as:

- title
- paper identifier or arXiv id when available
- year
- URL
- task / dataset / metric overlap
- mechanism summary
- novelty or value implication for this quest
- whether it is `new_this_pass`, `known_before`, or `watchlist`

At the end of ideation, at least one part of the literature survey must be preserved in memory so a later idea pass can retrieve it directly instead of rebuilding the search from scratch.

Promote to global memory only when the lesson is reusable outside this quest.

## Artifact rules

Typical durable records:

- report artifact for the literature survey
- report artifact for related-work mapping
- report artifact for limitation analysis
- idea artifact for one or more candidate directions
- decision artifact for the selected line

Preferred artifact choices:

- use `report` for:
  - literature survey synthesis
  - survey-delta refresh
  - related-work mapping
  - limitation analysis
  - novelty or value audit
- use `idea` for:
  - shortlisted candidates
  - the selected direction package
- use `decision` for:
  - select / reject / branch / return-to-scout outcomes
- use `approval` when the user explicitly confirms a preference-sensitive choice
- use `milestone` when ideation hits a meaningful user-visible checkpoint

If the idea is selected and becomes the active route, immediately call `artifact.submit_idea(mode='create', lineage_intent='continue_line'|'branch_alternative', ...)`.
Before that call, first finalize a concise but durable Markdown draft for the chosen route.
That draft should usually cover:

- executive summary
- bottleneck or limitation framing
- closest prior work and overlap
- any cross-domain inspirations worth borrowing
- selected claim
- theory and method
- code-level change plan
- evaluation or falsification plan
- risks, caveats, and implementation notes

Use the draft to think clearly first, then compress the accepted contract into the structured `artifact.submit_idea(...)` fields.
When the MCP surface supports it, pass the final Markdown draft through `draft_markdown` so the branch records both `idea.md` and `draft.md`.
Normal durable idea flow should create a new branch and a new canvas node every time an accepted idea package changes meaningfully, including documentation-only idea-package changes.
Use `lineage_intent='continue_line'` when the new idea is a child of the current active branch.
Use `lineage_intent='branch_alternative'` when the new idea should branch from the current branch's parent foundation as a sibling-like alternative.
`artifact.submit_idea(mode='revise', ...)` is maintenance-only compatibility for the same branch and should not be the normal research-route mechanism.
Do not prefer `artifact.prepare_branch(...)` for the normal idea-selection path.

Do not record a final selected-idea artifact without first recording a literature survey `report`.

## Failure and blocked handling

If ideation stalls, record why:

- baseline is still too uncertain
- evaluation contract is under-specified
- code path is unclear
- candidate ideas are too confounded to rank safely
- user preference is required for the tradeoff
- related-work coverage is still too weak to judge novelty or value
- closest prior work already invalidated the strongest candidate

Do not hide blocked ideation behind generic brainstorming text.

## Exit criteria

Exit the idea stage once one of the following is durably true:

- one idea is selected and ready for `experiment`
- several ideas are retained with an explicit branching decision
- the current line is rejected and the quest returns to `scout`
- the stage is blocked and a clear next decision is recorded

Do not exit this stage with a "selected idea" if:

- the literature survey report is missing
- the related-work map is missing
- the novelty / value verdict is still hand-wavy
- the falsification path is unclear
- the experiment handoff contract is incomplete
