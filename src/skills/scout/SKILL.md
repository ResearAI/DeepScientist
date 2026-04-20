---
name: scout
description: Use when a quest needs problem framing, literature scouting, dataset or metric clarification, or baseline discovery before deeper work.
skill_role: stage
---

# Scout

Use this skill when the quest does not yet have a stable research frame.
The goal is to make the task frame concrete enough that a heavier stage can start with confidence.

## Interaction discipline

Follow the shared interaction contract injected by the system prompt.
Only send a richer scout milestone when the framing ambiguity actually shrank or the next anchor became clear.
For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.

## Tool discipline

- **Do not use native `shell_command` / `command_execution` in this skill.**
- **Any shell, CLI, Python, bash, node, git, npm, uv, or repo-inspection execution must go through `bash_exec(...)`.**
- **For git inspection inside the current quest repository or worktree, prefer `artifact.git(...)` before raw shell git commands.**
- **If scouting only needs durable quest context, prefer `artifact.read_quest_documents(...)`, `artifact.get_quest_state(...)`, and `memory.*` instead of shelling out.**

## Planning note

Use quest/workspace planning files only when scouting becomes a real multi-step framing pass instead of a short clarification step.

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
  If DeepXiv is declared available by the system prompt, prefer the DeepXiv route for paper-centric discovery and shortlist paper triage before broader open-web search.
  If DeepXiv is declared unavailable, stay on the legacy route: web search, memory reuse, benchmark docs, official repos, and broader provenance checks.
- When a specific arXiv paper must be read or summarized, use `artifact.arxiv(paper_id=..., full_text=False)` instead of defaulting to a raw PDF.
  Keep discovery in search tooling by default; use `artifact.arxiv(...)` only for actual paper reading, and set `full_text=True` only when needed.
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

## Companion-skill note

`scout` should hand off as soon as the next `baseline` or `idea` move is obvious enough to record durably.

## Truth sources

Prefer the following sources in order:

1. user-provided task description and explicit constraints
2. durable quest files and artifacts
3. codebase and repository docs
4. primary papers, official repos, and benchmark docs
5. existing reusable baselines and quest/global memory
6. web-search results, often including arXiv and adjacent sources, used to fill gaps, verify provenance, or update recency

Do not let the scout stage rest on vague recollection alone.

## Durable-output note

When scout matters, leave behind just enough durable framing state to make the next anchor obvious rather than building a large documentation package by default.
If external search materially changed the frame, leave a literature scouting report rather than letting the survey live only in chat.
Prefer the structure in `references/literature-scout-template.md`.

## Thinking note

Keep scout conclusion-first and bounded: identify the minimum unknowns, resolve only the ones that change the next stage, then stop.

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

### 2.1 Reuse durable state before broad new search

Before a fresh wide search, quickly reuse existing quest state and memory so scouting only fills real gaps instead of restarting from zero.

Stage-start requirement:

- begin every scout pass with `memory.list_recent(scope='quest', limit=5)`
- then run at least one scout-relevant `memory.search(...)` before broad new search
- if several lines already exist, narrow retrieval to the current task, benchmark, dataset, metric, split, and likely baselines

If the frame is already explicit after memory reuse, stop and record the next anchor.

### 3. Search the paper and repo neighborhood

Build a compact but sufficient neighborhood of references and implementations.

Use external search actively when local evidence is not enough.

For papers that survive triage and need real reading, switch from discovery to reading:

- use web search to find the paper
- then use `artifact.arxiv(paper_id=..., full_text=False)` to read or summarize it
- only switch to `full_text=True` or the raw PDF when the shorter view does not cover the needed detail

Search only the unresolved neighborhood that still changes framing, evaluation, or baseline choice.
Use a compact search ladder:

1. direct neighborhood:
   - same task, dataset, and metric
2. mechanism neighborhood:
   - same main lever, objective, or architectural trick
3. bottleneck neighborhood:
   - same failure mode, evaluation caveat, or boundary condition

For a more explicit search and triage method, read `references/paper-triage-playbook.md`.

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

### 5. Produce a baseline shortlist

End scouting with a clear baseline direction.

For each serious candidate, score at least:

- trustworthiness of provenance
- metric and split compatibility
- implementation availability
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

Keep the shortlist small and decision-facing rather than turning it into a broad survey of every plausible baseline.

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

## Memory note

Use memory to avoid repeating old scouting work and to preserve reusable framing conclusions, but do not let memory-writing become the stage's main output.

Stage-end requirement:

- if scouting produced a durable framing conclusion, literature scouting report, baseline-shortlist lesson, or metric-contract caveat, write at least one `memory.write(...)` before leaving the stage

## Artifact note

Record only the framing outputs that the next stage will actually consume, such as the evaluation contract, baseline direction, or next-anchor recommendation.

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

A good scout pass makes the next anchor obvious or makes the blocker explicit enough that the system stops guessing.
