---
name: scout
description: Use when a quest needs problem framing, literature scouting, dataset or metric clarification, or baseline discovery before deeper work.
skill_role: stage
---

# Scout

Use this skill when the quest does not yet have a stable research frame.

## Interaction discipline

- Follow the shared interaction contract injected by the system prompt.
- For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
- Message templates are references only. Adapt to the actual context and vary wording so updates feel natural and non-robotic.
- If a threaded user reply arrives, interpret it relative to the latest scout progress update before assuming the task changed completely.
- When scouting actually resolves the framing ambiguity, locks the evaluation contract, or makes the next anchor obvious, send one richer `artifact.interact(kind='milestone', reply_mode='threaded', ...)` update that says what is now clear, why it matters, and which stage should come next.

## Tool discipline

- **Do not use native `shell_command` / `command_execution` in this skill.**
- **Any shell, CLI, Python, bash, node, git, npm, uv, or repo-inspection execution must go through `bash_exec(...)`.**
- **For git inspection inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.**
- **If scouting only needs durable quest context, prefer `artifact.read_quest_documents(...)`, `artifact.get_quest_state(...)`, and `memory.*` instead of shelling out.**

## Stage purpose

The scout stage exists to answer the smallest set of framing questions required to make the rest of the quest efficient:

- what exact task is being solved?
- which dataset, split, and metric contract matter?
- which papers, repos, and baselines define the local neighborhood?
- which unknowns still block baseline or ideation?

This stage is not generic browsing.
It is a bounded framing and discovery stage that should quickly make the next anchor obvious.

The scout stage should usually establish four layers:

- task-definition layer
- evaluation-contract layer
- literature and repo neighborhood layer
- baseline-direction layer

If one of these layers is still missing, say so explicitly.

## Non-negotiable rules

- Do not let `scout` become endless exploration.
- Do not keep searching once the next anchor is already clear.
- Do not guess the metric, split, or baseline identity when local evidence is still ambiguous.
- Do not ask the user ordinary technical questions before checking local evidence first.
- Do not force a baseline route without comparing attach, import, and reproduce options.
- Do not rely on memory alone when primary sources or durable quest files exist.
- Before broad external search, check quest/global memory first with `memory.list_recent(...)` and `memory.search(...)`.
- When search tools are available, actively use them.
  Prefer web search for paper discovery, usually targeting arXiv first, then expand with benchmark docs, official repos, and broader web search for provenance.
- When a specific arXiv paper must be read or summarized, use `artifact.arxiv(paper_id=..., full_text=False)` instead of defaulting to a raw PDF.
  Keep discovery in web search; use `artifact.arxiv(...)` only for actual paper reading, and set `full_text=True` only when needed.
- Avoid repeating the same wide search from scratch.
  Reuse prior survey notes and search only for genuinely missing, newer, or unresolved references.
- Do not write long paper summaries that do not change the next stage.
- Search for disconfirming evidence, not only supportive evidence.
- If the apparent gap is already closed by straightforward scaling, standard engineering, or a strong recent paper, say so directly instead of inflating novelty.

## Use when

- the user goal is still ambiguous
- the dataset or split contract is unclear
- the primary metric is unclear
- no trustworthy baseline has been identified
- the paper or repo neighborhood is still thin
- the quest was resumed after a long pause and framing needs reconstruction
- the next stage is blocked by ambiguity rather than by implementation

## Do not use when

- the user already fixed the paper, baseline, dataset, metric contract, and scope
- the quest already has a validated baseline and is ready for ideation or execution
- the real blocker is execution or verification rather than framing

## Preconditions and gate

Before spending time scouting, first verify whether the current quest already contains enough framing in:

- `brief.md`
- `plan.md`
- `status.md`
- `SUMMARY.md`
- baseline artifacts
- recent paper or knowledge memory cards

If the answer is already clear, exit quickly and move to the correct next anchor.

## Companion skill rule

`scout` is the framing anchor.
It often prepares for `baseline`.

In practice:

- use `scout` to determine the task frame, evaluation contract, paper neighborhood, and candidate baselines
- use `baseline` once a concrete baseline route is justified

Do not stay in `scout` once the next `baseline` route is obvious enough to record durably.

## Truth sources

Prefer the following sources in order:

1. user-provided task description and explicit constraints
2. durable quest files and artifacts
3. codebase and repository docs
4. primary papers, official repos, and benchmark docs
5. existing reusable baselines and quest/global memory
6. web-search results, often including arXiv and adjacent sources, used to fill gaps, verify provenance, or update recency

Do not let the scout stage rest on vague recollection alone.

## Required durable outputs

The scout stage should usually leave behind:

- an updated `brief.md`
- an updated `plan.md`
- optional `status.md` refresh if the quest state changed
- a literature scouting report when external search was needed
- `memory` cards for key references or framing notes
- a report or decision artifact that points to the next anchor

Recommended durable scout files:

- `artifacts/scout/literature_scout.md`
- `artifacts/scout/framing_report.md`
- `artifacts/scout/eval_contract.md`
- `artifacts/scout/baseline_shortlist.md`

For more explicit output shapes, read:

- `references/paper-triage-playbook.md`
- `references/literature-scout-template.md`
- `references/eval-contract-template.md`
- `references/baseline-shortlist-template.md`

## Thinking protocol

Scout should be:

- conclusion-first
- bounded
- evidence-first
- oriented toward the next stage

Use a simple reasoning order:

1. what is already known?
2. what is still ambiguous?
3. which ambiguity actually changes later stages?
4. what is the cheapest way to resolve it?
5. which next anchor becomes justified after that?

Do not dump disconnected facts.
Turn them into a framing decision.

## Workflow

### 1. Reconstruct the current frame

Summarize:

- current task
- current dataset and split understanding
- current metric contract
- current baseline status
- current blockers

If this can already be stated precisely, scouting may be complete immediately.

### 2. Identify the minimum unknowns

List only the unknowns that materially affect later stages, such as:

- unclear evaluation metric
- multiple conflicting dataset splits
- missing baseline candidate
- unclear repo or paper provenance
- missing source paper for a claimed baseline

Avoid collecting "nice to know" facts that do not change the next stage.

Also classify each unknown:

- blocks `baseline`
- blocks `idea`
- blocks both
- useful but non-blocking

### 2.1 Reuse durable memory before external search

Before opening the web, check what the quest already knows.

At minimum:

- inspect recent quest `papers`, `knowledge`, and `decisions`
- inspect recent global `papers`, `knowledge`, and `templates` when the topic or benchmark looks reusable
- run `memory.search(...)` over:
  - task name
  - dataset or benchmark
  - metric or split keywords
  - likely baseline names
  - mechanism or failure-mode keywords

Then classify the current state:

- already covered well
- stale and needs refresh
- still missing

If the frame is already explicit after memory reuse, stop and record the next anchor.
Do not open a fresh broad search just because scouting feels unfinished.

### 3. Search the paper and repo neighborhood

Build a compact but sufficient neighborhood of references and implementations.

Use external search actively when local evidence is not enough.
When available, prefer:

1. web search targeting arXiv for paper discovery
2. official benchmark docs and official repos for evaluation truth
3. broader web search for provenance checks, follow-up work, and comparison context

For papers that survive triage and need real reading, switch from discovery to reading:

- use web search to find the paper
- then use `artifact.arxiv(paper_id=..., full_text=False)` to read or summarize it
- only switch to `full_text=True` or the raw PDF when the shorter view does not cover the needed detail

Search buckets should include:

- same task, same dataset, same metric
- same task, same mechanism
- same task, same failure mode
- strongest recent competitors
- papers or repos that may have already solved the claimed gap
- official benchmark or evaluation documentation
- official or de facto reference repos

Use a layered search ladder:

1. direct neighborhood:
   - same task
   - same dataset
   - same metric
2. mechanism neighborhood:
   - same main lever or architectural trick
   - same objective or loss family
3. bottleneck neighborhood:
   - papers or repos attacking the same failure mode
   - papers exposing the same evaluation caveat
4. adjacent inspiration neighborhood when useful:
   - nearby tasks or domains that attack the same structural bottleneck

Prefer recent papers more heavily when the area is moving quickly, but keep older anchor papers when they define the true baseline landscape.

Keep a compact scouting ledger while searching.
For each meaningful search pass, record:

- query text
- source, such as `memory`, `arXiv`, benchmark docs, repo search, or open web
- why the query was issued
- what new references were added
- what prior references were re-confirmed
- which ambiguity is still unresolved

For each retained reference, record:

- identifier or title
- why it matters
- whether it mainly informs:
  - task framing
  - evaluation contract
  - baseline choice
  - later ideation

Also keep the retained set legible by classifying papers into:

- closest competitors
- adjacent inspirations
- problem-defining anchors
- maybe-already-solved references

If you used external search, write a literature scouting report before ending the stage.
Prefer the structure in `references/literature-scout-template.md`.

Use `references/paper-triage-playbook.md` for a more detailed search and triage method.

### 4. Clarify the evaluation contract

Produce an explicit statement of:

- task
- dataset
- split or evaluation partition
- primary metric
- secondary metrics if necessary
- what counts as a useful improvement
- what comparisons will be considered fair

The evaluation contract should be strong enough that later `baseline`, `idea`, and `experiment` work do not need to keep re-deriving it.

If the evaluation contract is still ambiguous after local analysis, ask the user for a structured decision instead of guessing.

Use `references/eval-contract-template.md` when writing the contract durably.

### 5. Produce a baseline shortlist

End scouting with a clear baseline direction.

For each serious candidate, score at least:

- trustworthiness of provenance
- metric and split compatibility
- implementation availability
- environment and dependency risk
- reproduction or import cost
- value as a downstream comparison reference

Each candidate should lead to one recommended route:

- attach an existing baseline
- import a reusable baseline package
- reproduce a baseline from source
- reject this candidate

For each serious candidate, also state:

- whether it is a direct baseline, a strong competitor, or only an adjacent reference
- whether the repo path or paper evidence is strong enough to trust the route
- the cheapest credible next action: attach, import, reproduce, or reject

Use `references/baseline-shortlist-template.md` for a structured shortlist.

### 6. Recommend the next anchor

Do not stop with a list of possibilities.
Choose the most justified next anchor:

- `baseline`
- `idea`
- remain in `scout`

`idea` is only justified when the baseline is already durable and trustworthy enough.
If no usable baseline exists, prefer `baseline`.

### 7. Update quest continuity

If the frame changed, update:

- `brief.md`
- `plan.md`
- `status.md`

Then record a durable report or decision showing the recommended next anchor.

### 8. Stop on clarity, not exhaustion

The stage is done when the framing is decision-ready, not when every curiosity is satisfied.

Stop once all of the following are true:

- the task frame is explicit enough
- the evaluation contract is explicit enough
- the baseline direction is justified enough
- the next anchor is durable and obvious

## Search stop rules

Stop literature and repo search when:

- the strongest obvious local neighbors are mapped
- the evaluation contract no longer depends on unknown sources
- at least one baseline route is clearly better than the alternatives
- additional papers are no longer changing the next action

Continue searching only if:

- metric or split ambiguity remains
- the current shortlist is too weak or conflicting
- provenance of the likely baseline is still uncertain

Do not continue searching just to collect more papers after the next anchor is already clear.

## Memory rules

Stage-start requirement:

- begin every scout pass with `memory.list_recent(scope='quest', limit=5)`
- then run at least one scout-relevant `memory.search(...)` before broad new search
- if several idea or baseline lines already exist, narrow retrieval to the current line instead of mixing unrelated memory casually

Write durable memory only when it is reusable later.

Preferred memory usage:

- quest `papers`:
  - literature scouting summaries
  - paper cards
  - benchmark notes
  - official-doc references
  - repo provenance notes
- quest `knowledge`:
  - dataset quirks
  - metric-contract notes
  - split caveats
  - bounded framing lessons for this quest
- quest `decisions`:
  - why a baseline route was preferred
  - why a conflicting evaluation interpretation was rejected
- global `knowledge`:
  - reusable benchmark caveats
  - general scouting heuristics
- global `templates`:
  - paper-card templates
  - eval-contract templates
  - shortlist templates

Useful tags include:

- `stage:scout`
- `type:literature-scout`
- `type:related-work`
- `type:benchmark-note`
- `type:metric-contract`
- `type:baseline-shortlist`
- `topic:<task-or-dataset>`

When calling `memory.write(...)`, pass `tags` as an array like `["stage:scout", "type:related-work", "topic:<task-or-dataset>"]`, not as one comma-joined string.

Recommended read timing:

- before any new web search:
  - run `memory.search(...)` over task, benchmark, metric, split, and likely baselines
- at scout start:
  - read recent quest `papers`, `knowledge`, and `decisions`
- before baseline recommendation:
  - re-check quest `decisions` and shortlist-related notes
- after a long pause:
  - warm-start from quest `papers` and `knowledge` before re-searching

Stage-end requirement:

- if scouting produced a durable framing conclusion, paper note, shortlist lesson, or metric-contract caveat, write at least one `memory.write(...)` before leaving the stage

When writing quest `papers` cards, include enough metadata to reduce repeated scouting later:

- title
- identifier or arXiv id when available
- URL
- year
- task / dataset / metric relevance
- baseline relevance or provenance relevance
- whether the source is official, community, or uncertain
- whether it is `new_this_pass`, `known_before`, or `watchlist`

At least one durable piece of the scouting survey should be written into quest memory whenever external search materially shaped the framing or baseline shortlist.

Prefer concise, high-signal notes over long prose dumps.

## Artifact rules

Preferred artifact usage:

- use `report` for:
  - literature scouting synthesis
  - framing synthesis
  - evaluation contract
  - baseline shortlist
- use `decision` for:
  - next-anchor recommendation
  - blocked-state routing
  - structured user choice requests when evidence cannot resolve the ambiguity
- use `milestone` when the scout stage reached a clear framing checkpoint
- use `approval` only if the user explicitly confirms a preference-sensitive route

Use `artifact.interact(...)` for a structured decision request only when a real ambiguity remains and local evidence cannot safely resolve it.

Do not close a scout stage that depended on external literature search without a durable `report`.

## Blocked-state handling

Record a blocked state if scouting cannot proceed because:

- the quest objective is materially ambiguous
- the required code or paper source is missing
- multiple evaluation contracts conflict and the choice would change later conclusions
- all baseline candidates are too weak, broken, or poorly specified

A blocked scout result should state:

- what is missing
- why it matters
- which next anchor is blocked
- what concrete user choice or source is needed

Do not hide a blocked scout stage behind generic literature chatter.

## Exit criteria

Exit the scout stage once all of the following are true:

- the task frame is explicit
- the evaluation contract is explicit
- at least one baseline direction is justified
- the next anchor is obvious enough to record durably

If the stage relied on external search, the literature scouting report must also be durable before exit.

Typical next anchors:

- `baseline`
- `idea`
- remain in `scout` only if the remaining blocker is explicit and durable
