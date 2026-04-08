---
name: optimize
description: Use when an algorithm-first quest should manage candidate briefs, optimization frontier, branch promotion, or fusion-aware search instead of the paper-oriented default loop.
skill_role: stage
---

# Optimize

Use this skill for algorithm-first quests where the goal is the strongest justified optimization result rather than paper packaging.

This skill is the lightweight optimization control layer for DeepScientist.
It does not replace the normal quest runtime. It tells you how to use the existing DeepScientist artifact, memory, bash_exec, Git, and worktree mechanisms as an optimization system.

## Interaction discipline

- Follow the shared interaction contract injected by the system prompt.
- For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
- Ordinary candidate creation, smoke checks, and route updates should stay concise.
- Use richer milestone updates only when a candidate is promoted, a strong run finishes, the frontier shifts materially, or a fusion/debug route becomes the new main path.
- When the user asks for the current optimization state, answer from the frontier and durable artifacts rather than from chat memory.
- Hard execution rule: every terminal command in this stage must go through `bash_exec`; do not use any other terminal path for smoke checks, quick validations, long runs, Git, Python, package-manager, or file-inspection commands.

## Three-layer todo contract

- keep quest-root `plan.md` as the research map and loop tracker for the whole quest
- keep workspace `PLAN.md` as the active optimize-node contract
- keep `OPTIMIZE_CHECKLIST.md` as the optimize-specific execution frontier and mirror the immediate next move into workspace `CHECKLIST.md` when that file exists
- keep only one bottom-layer optimize move truly in progress at a time
- if the frontier and checklist stop changing, revise the node contract or route instead of nesting more local tweaks

## Research-map role

- `optimize` is the looped search controller for algorithm-first quests, not a replacement for the quest-level roadmap
- when a result becomes the new incumbent, plateaus, or stops, update quest-root `plan.md` so the next loop edge is explicit

## Stage purpose

The optimize stage should do four things:

1. turn loose ideas into candidate briefs
2. rank and promote only the strongest briefs into durable lines
3. manage candidate attempts within a durable line
4. choose when to explore, exploit, fuse, debug, or stop

This skill is especially appropriate when `startup_contract.need_research_paper = false`.

Treat `optimize` as one stable stage skill with six internal submodes:

- `brief`
- `rank`
- `seed`
- `loop`
- `fusion`
- `debug`

Do not treat these as separate public skills.
Treat them as internal execution modes inside one optimize workflow.

InternAgent maps most naturally onto the `brief` and `rank` side of this stage.
MLEvolve maps most naturally onto the `seed`, `loop`, `fusion`, and `debug` side of this stage.
Do not collapse those two layers into one vague "optimize more" loop.

## Required working files

Before broad optimization search or candidate management becomes substantial, maintain these quest-visible control files:

- `OPTIMIZE_CHECKLIST.md`
- `CANDIDATE_BOARD.md`

Use:

- the integrated `optimize checklist template` appendix section
- the integrated `candidate board template` appendix section

`OPTIMIZE_CHECKLIST.md` is the execution control surface.
It should track:

- current frontier mode
- current optimize submode
- candidate brief count
- promoted line count
- current smoke queue
- current full-eval queue
- stagnation / fusion checks
- next concrete action

`CANDIDATE_BOARD.md` is the compact candidate ledger.
It should track:

- candidate id
- candidate type: brief or implementation attempt
- parent line or parent candidate
- strategy: explore / exploit / fusion / debug
- status
- expected gain
- observed result
- promote / archive recommendation

## Required MCP-driven workflow

Treat this as the concrete optimize workflow. Do not skip these steps just because the quest is algorithm-first.

### 1. Recover the optimization state first

At the start of each meaningful optimize pass, use this order unless a stronger local reason exists:

1. `artifact.get_optimization_frontier(...)`
2. `memory.list_recent(scope='quest', limit=5)`
3. `memory.search(...)`
4. `artifact.get_quest_state(detail='summary')`
5. `artifact.read_quest_documents(...)` when exact durable wording matters

Do not create new candidates before the frontier, recent optimization lessons, and current runtime refs are checked.
If the frontier is missing or obviously stale, recover that state before proposing more work.

### 2. Shape candidate briefs before branch promotion

When the next direction is still fuzzy, do not jump straight into code or branch creation.
First turn the direction into a compact candidate brief.

The brief-shaping sequence is:

1. clarify the bottleneck, constraints, and comparability boundary
2. identify the incumbent or baseline that this brief must beat or complement
3. generate a small differentiated slate, usually `2-3` serious approaches
4. compare them on one shared surface
5. recommend exactly one lead brief
6. self-check the recommended brief before submission

Every serious brief should answer:

- bottleneck
- why_current_line_is_limited
- mechanism
- why_now
- keep_unchanged
- expected_gain
- implementation_surface
- main_risks

The durable call for this step is usually:

- `artifact.submit_idea(mode='create', submission_mode='candidate', ...)`

Use `idea` when the mechanism family itself is still unresolved.
Use `optimize` when the family is already chosen and the work is now branchless brief shaping, ranking, or within-line search.

### 3. Rank candidate briefs on one explicit surface

Before promoting a line, compare the serious briefs on one shared ranking surface.
At minimum evaluate:

- expected information gain
- feasibility in current repo
- comparability against baseline
- implementation surface
- novelty or distinctiveness
- family diversity
- change-layer diversity
- incumbent-improvement potential
- failure risk

Then state:

- winner justification
- non-winner defer / reject reasons
- promotion cap: how many lines should actually be promoted now

Do not promote every plausible brief.
Default rule: promote only `1-3` candidate briefs, and usually fewer.

The durable call for this step is one of:

- `artifact.submit_idea(mode='create', submission_mode='line', source_candidate_id=..., ...)`
- `artifact.record(payload={'kind': 'decision', 'action': 'branch'|'continue'|'stop', ...})`

### 4. Hand off promoted lines into experiment cleanly

Once a brief is promoted, the next main work belongs to `experiment`, not to vague optimize chatter.
Before substantial implementation or compute:

- activate or confirm the intended durable line
- update `OPTIMIZE_CHECKLIST.md`
- update `CANDIDATE_BOARD.md`
- create or revise `PLAN.md`
- create or revise `CHECKLIST.md`
- define the smoke queue and full-eval queue explicitly

Then hand off into `experiment` for:

- one clean implementation pass
- one bounded smoke or pilot run
- one real measured main run

Do not keep reshaping the method after the run contract is already concrete.

### 5. Record every meaningful result durably

Use these artifact forms consistently:

- candidate brief:
  - `artifact.submit_idea(..., submission_mode='candidate')`
- durable optimization line:
  - `artifact.submit_idea(..., submission_mode='line')`
- implementation-level candidate attempt inside one line:
  - `artifact.record(payload={'kind': 'report', 'report_type': 'optimization_candidate', ...})`
- real measured main result:
  - `artifact.record_main_experiment(...)`
- route change after the result:
  - `artifact.record(payload={'kind': 'decision', 'action': 'iterate'|'branch'|'continue'|'stop', ...})`

Do not treat chat summaries as substitutes for these durable records.

### 6. Manage process lifecycle explicitly

Optimize uses the same long-run process discipline as `experiment`.

- Use `bash_exec` for smoke checks, quick validations, and long runs.
- Before launching a new run, inspect current managed sessions first.
- Do not start a duplicate process for the same purpose if a valid live session already exists.
- Use bounded smoke before long runs unless direct quick validation is already cheap and equally informative.
- Use `bash_exec(mode='detach', ...)` for long runs and monitor with `list/read/await`.
- Read logs before retrying a failed or suspicious run; do not relaunch blindly.
- Kill only on explicit invalidity, supersession, or checked no-progress conditions.
- After pause, resume, or daemon recovery, recover session state before spawning new runs.

### 7. Route from evidence, not from momentum

After every real measured result:

1. refresh the frontier
2. compare the result against the incumbent and backlog
3. choose exactly one dominant next action:
   - explore
   - exploit
   - fusion
   - debug
   - stop
4. record that route durably

Do not treat one candidate creation, one smoke pass, or one detached launch as stage completion.

## Integrated templates and playbooks

Use the following integrated structures directly inside this skill. They replace the old optimize reference files conceptually, even if those files still exist on disk.

### Candidate brief template

Every serious candidate brief should include:

- title
- bottleneck
- why_current_line_is_limited
- mechanism
- mechanism_family
- change_layer: `Tier1` / `Tier2` / `Tier3`
- source_lens
- keep_unchanged
- expected_gain
- implementation_surface
- risks
- foundation
- promote_now
- next_target

### Brief-shaping playbook

Use this when a candidate direction is still fuzzy and needs to become a ranking-ready brief.

- clarify the concrete bottleneck before widening
- resolve the evaluation or comparability boundary
- identify the main hard constraint
- identify the current incumbent
- generate only a small differentiated slate
- compare on one shared surface
- recommend exactly one lead brief
- self-check for ambiguity, overlap, and weak justification

### Candidate ranking template

When several briefs compete, produce:

- candidate set
- ranking scope
- comparison surface
- ranked candidates with score summary, why each ranks there, and promote / hold / reject
- winner justification
- non-winner notes
- promotion cap

### Candidate board template

`CANDIDATE_BOARD.md` should expose at least these columns:

- candidate id
- level: `brief` or `implementation`
- parent
- strategy
- status
- expected gain
- observed result
- promote / archive recommendation

### Optimize checklist template

`OPTIMIZE_CHECKLIST.md` should track at least:

- frontier has been refreshed
- primary optimize submode chosen
- current route mode chosen
- recent optimization memory reviewed
- brief slate checked for family diversity
- candidate briefs updated or confirmed
- candidate ranking updated
- promotion decision made
- current implementation pool recorded
- smoke queue defined
- full-eval queue defined
- failures classified
- stagnation check performed
- fusion eligibility checked
- next concrete action written

### Frontier review template

Whenever route choice is unclear, write down:

- current frontier
- evidence summary
- route choice
- active optimize submode
- immediate next action

### Code-generation route playbook

Choose one route deliberately:

- brief-only when the direction is still unclear
- stepwise generation for first substantial implementation of a new line
- diff / patch generation for improve / exploit / debug / most fusion work
- full rewrite only when the current implementation is structurally broken or mismatched

Do not jump to a rewrite merely because one local patch failed.

### Debug response template

When a candidate fails but still looks strategically valuable, record:

- error
- retrieved memory
- root cause
- minimal fix
- keep unchanged
- next check
- archive threshold

### Fusion playbook

Before opening a fusion candidate, answer:

- what exactly is being fused?
- why are the source strengths complementary rather than redundant?
- what remains unchanged for comparability?
- what bounded evidence would prove the fusion worthwhile?
- what bounded first validation step should run before any broad rollout?

Do not fuse two weak lines or two same-mechanism lines under different names.

### Optimization memory template

When writing reusable optimization lessons, capture:

- type
- context
- observation
- why it matters
- retrieval hint
- reuse hint

### Plateau response playbook

If one line keeps producing non-improving results:

1. state that the line is plateauing
2. identify the most likely root cause
3. choose one larger route change:
   - widen search
   - promote a stronger alternative
   - fuse
   - debug
   - stop
4. record one explicit non-repeat rule

Do not hide plateau under a sequence of tiny "one more tweak" loops.

### Prompt patterns worth preserving

For candidate-brief, improve, fusion, and debug prompts, preserve:

- introduction
- task description
- memory
- previous solution or previous line
- instructions
- explicit response format

Preserve these reasoning contracts whenever possible:

- WHAT is changing?
- WHY is the current line limited?
- HOW should the change address the limitation?
- KEEP UNCHANGED
- NEXT ACTION

## Non-negotiable rules

- Do not treat every patch or micro-attempt as a new durable idea line.
- Do not create a new Git branch/worktree for every implementation-level candidate.
- Use `artifact.submit_idea(..., submission_mode='candidate')` for candidate briefs that should be ranked before promotion.
- Use `artifact.submit_idea(..., submission_mode='line')` only for directions that deserve a durable optimization line and branch/worktree.
- Use `artifact.record(payload={'kind': 'report', 'report_type': 'optimization_candidate', ...})` for implementation-level candidate attempts inside one durable line.
- Before deciding the next route, call `artifact.get_optimization_frontier(...)` when available and use it as the primary optimization-state summary.
- Keep all major optimization successes and failures durable through artifacts and memory.
- Do not drift into paper-outline, bundle, or finalize work by default while this stage is active.
- Do not convert ranking uncertainty into premature branch creation.
- Do not treat an implementation-level candidate report as a new durable optimization line.
- Do not keep widening the frontier once a small serious slate already exists.
- Do not let one optimize pass mix multiple major route changes.
  One pass may inspect several possibilities, but it should finish with one dominant next action.

## When to use

- the quest is algorithm-first
- the baseline gate is already confirmed or waived
- the task has at least one plausible optimization direction
- multiple candidate directions exist and the system should rank them before promotion
- a durable line exists and the next step is to manage explore / exploit / fuse / debug

## Do not use when

- the baseline gate is unresolved
- the main need is a paper draft, rebuttal, or review task
- the quest is still in broad literature scouting with no concrete optimization handle

## Core object model

Use these three object levels consistently:

1. candidate brief
   `artifact.submit_idea(mode='create', submission_mode='candidate', ...)`
   This records a possible direction or method brief without opening a branch yet.

2. durable optimization line
   `artifact.submit_idea(mode='create', submission_mode='line', ...)`
   This opens a real branch/worktree and becomes a formal optimization path.

3. implementation-level candidate attempt
   `artifact.record(payload={'kind': 'report', 'report_type': 'optimization_candidate', ...})`
   This is a within-line attempt such as one patch, one smoke candidate, one debug candidate, or one fusion candidate.

## Recommended workflow

1. Read the current frontier and recent durable state.
2. If only loose candidate directions exist, create or refine candidate briefs first.
3. Rank the candidate briefs and promote only the best `1-3` into durable lines.
4. Inside a durable line, generate a small candidate pool, then run bounded smoke checks before full evaluations.
5. Record each implementation-level attempt durably with status, change plan, and result.
6. After each real result, decide whether to explore, exploit, fuse, debug, or stop.
7. Write optimization lessons to memory before leaving the stage.

At the start of each meaningful optimize pass, update `OPTIMIZE_CHECKLIST.md` before spending significant code or compute.

## Mandatory first-call sequence

At the start of a meaningful optimize pass, use this order unless a stronger local reason exists:

1. `artifact.get_optimization_frontier(...)`
2. `memory.search(...)`
3. `artifact.get_quest_state(detail='summary')`
4. `artifact.read_quest_documents(...)` when exact durable wording matters

Do not start generating new candidates before the frontier and recent optimization lessons are checked.

## Stage-start requirement

Stage-start requirement:

- run `memory.list_recent(scope='quest', limit=5)`
- run at least one `memory.search(...)`
- read `artifact.get_optimization_frontier(...)`
- update `OPTIMIZE_CHECKLIST.md`

If the frontier is missing or obviously stale, recover that state before proposing more work.

## Internal submode selection

Choose exactly one primary optimize submode for the current meaningful pass.

Default selection order:

1. `fusion`
   - when the frontier explicitly says `fusion`
2. `debug`
   - when a strategically valuable candidate failed for a concrete and likely fixable reason
3. `rank`
   - when several candidate briefs already exist and promotion is the main unresolved question
4. `brief`
   - when the candidate-brief slate is too thin or too weak
5. `seed`
   - when a durable line exists but there is no live implementation-candidate pool
6. `loop`
   - when a live candidate pool or leading durable line already exists and the main need is bounded execution progress

Do not bounce among submodes repeatedly in one pass.
If the best submode changes after new evidence appears, record that route shift explicitly.

## Candidate brief protocol

When a direction is interesting but not yet worthy of a new branch:

- create a candidate brief with `submission_mode='candidate'`
- keep it branchless
- record enough structure that later ranking or promotion is possible

Good candidate-brief fields include:

- title
- problem
- hypothesis
- mechanism
- mechanism_family
- change_layer
- source_lens
- expected_gain
- risks
- decision_reason
- foundation_ref
- lineage_intent

Do not promote every candidate automatically.

Use the integrated `method brief template` section for the minimum acceptable candidate-brief structure.
Use the integrated `brief shaping playbook` section when the brief is still too vague, too implementation-first, or too collapsed onto one familiar mechanism.

Candidate briefs should explicitly answer:

- WHAT bottleneck is being targeted?
- WHY is the current line limited?
- HOW does this mechanism address the limitation?
- WHAT must remain unchanged for comparability?

If the brief cannot answer those four questions clearly, it is not ready for promotion or implementation.

Treat a candidate brief as the DeepScientist form of a method brief.
It should sit between "idea intuition" and "code implementation".

Preserve this brief-shaping discipline:

1. clarify the bottleneck, constraints, and comparability boundary first
2. generate a small differentiated slate, usually `2-3` serious approaches
3. recommend one approach with explicit tradeoffs against the alternatives
4. self-check the winning brief for ambiguity, overlap, and weak justification before submission

Do not jump from "interesting intuition" to branch creation.
Do not jump from "I know how to code this" to "this deserves promotion."

When running the `brief` submode:

- produce only `2-4` serious candidate briefs by default
- ask or answer the minimum clarifying questions needed to remove ambiguity around bottleneck, constraint fit, and comparability
- explicitly keep one incumbent-compatible refinement when possible
- explicitly keep one orthogonal alternative when possible
- explicitly keep one broader lens or paradigm shift candidate when possible
- avoid generating several renamed variants of the same mechanism
- prefer mechanism-level distinctness over volume
- present the differentiated slate on one shared comparison surface before choosing a recommended brief
- keep the questioning bounded and execution-oriented rather than open-ended brainstorming

Use a coverage contract for every serious brief slate:

- one `incumbent-deepening` direction when justified
- one `orthogonal-mechanism` direction when justified
- one `paradigm/objective/data-view shift` direction when justified

If all serious briefs belong to the same mechanism family, do one widening pass before ranking.
Do not treat a same-family slate as sufficient merely because the local scores look good.

For each serious brief, record at least:

- bottleneck
- why_current_line_is_limited
- mechanism
- why_now
- mechanism_family
- change_layer: `Tier1` / `Tier2` / `Tier3`
- source_lens
- keep_unchanged
- expected_gain
- implementation_surface
- main_risks
- promote_now: yes or no

InternAgent-style behavior to preserve here:

- generate candidate methods first
- critique them before promotion
- express them as method-layer objects rather than code patches
- defer branch creation until the candidate is actually chosen
- prefer one-question-at-a-time clarification when one missing assumption would otherwise contaminate the whole brief slate

Do not require a paper-style literature hard gate inside this submode unless the quest explicitly moved back toward paper work.

## Promotion protocol

Only promote a candidate brief into a durable line when at least one of the following is true:

- it clearly dominates the nearby alternatives
- it is top-ranked and sufficiently distinct
- the user explicitly asked to pursue it
- the current frontier indicates the line is the strongest next move

Promotion should use:

`artifact.submit_idea(mode='create', submission_mode='line', source_candidate_id=..., ...)`

When several candidate briefs are plausible, rank them explicitly before promotion.
Use the integrated `candidate ranking template` section for the minimum acceptable ranking record.

Default promotion rule:

- promote only `1-3` candidate briefs into durable lines
- if one candidate clearly dominates, promote only that one
- if the frontier is still structurally uncertain, promote at most two sufficiently distinct lines

When running the `rank` submode:

- compare the current serious briefs on one explicit shared surface
- score or rank them with written reasons
- state why the winner is better now
- state why the main alternatives are deferred rather than erased
- never treat "all seem promising" as a sufficient reason to promote them all

Use a distinct promotion policy:

- default rule: each mechanism family should contribute at most one promoted line
- do not let one familiar family fill the whole promoted slate
- only override that family cap when one candidate clearly dominates the whole field

When ranking, explicitly check:

- family diversity
- change-layer diversity
- whether the brief slate is collapsing into one familiar lens

If the top briefs are all same-family, either:

- keep only the strongest one
- or return to `brief` for a widening pass

The output of `rank` should be promotion-ready.
The output of `brief` should be candidate-ready.

## Frontier protocol

At meaningful route boundaries, inspect:

- best branch
- best recent run
- stagnant branches
- candidate backlog
- possible fusion opportunities
- recommended mode

Prefer these route meanings:

- `explore`: widen search with fresh candidate directions
- `exploit`: focus on the strongest current line
- `fusion`: merge insights from multiple successful or complementary lines
- `debug`: rescue a candidate or line blocked by a concrete failure mode
- `stop`: the current frontier is saturated or the remaining routes are not justified

Use the integrated `frontier review template` section when the next route is unclear.

Interpret frontier state with these default heuristics:

- `explore`
  - use when no line is clearly dominant
  - use when current lines are too similar
  - use when the search has not yet established a strong incumbent

- `exploit`
  - use when one line clearly leads on evidence and comparability
  - use when smoke results already narrowed the candidate pool

- `fusion`
  - use when at least two lines have meaningful strengths
  - use when one line is strong but another line contributes a complementary mechanism
  - use when the current incumbent is stagnating but the broader frontier is still promising

- `debug`
  - use when a candidate failed for a concrete and likely fixable reason
  - use when the candidate is still strategically valuable after the failure

- `stop`
  - use when the frontier is saturated
  - use when remaining routes are low-value, redundant, or too weak relative to cost

When the frontier says `explore`, the default optimize submode is `brief`.
When the frontier says `exploit`, the default optimize submode is `seed` or `loop`.
When the frontier says `fusion`, the default optimize submode is `fusion`.
When a candidate failure dominates the next move, the default optimize submode is `debug` even if the frontier does not yet say so explicitly.

## Seed protocol

Use `seed` after a durable line exists and before a broad execution loop begins.

The goal is not to launch a full run immediately.
The goal is to generate a small within-line candidate pool that can be smoke-tested and triaged.

When running `seed`:

- generate only `2-3` implementation-level candidates by default
- make each candidate meaningfully different in mechanism, implementation path, or risk profile
- prefer plan-first candidates over immediate large edits
- record each candidate as `report_type='optimization_candidate'`
- define which candidates enter smoke first
- for a newly promoted line, keep at least one `simple-first` candidate in the initial seed batch
- do not start a fresh line with ensemble stacking, broad HPO, or a heavy multi-stage pipeline unless durable evidence already proves the simple route is insufficient

For each seed candidate, record at least:

- candidate_id
- parent line
- strategy
- mechanism_family
- change_layer
- change_plan
- expected_gain
- keep_unchanged
- first validation step
- archive condition

MLEvolve-style behavior to preserve here:

- one durable line may produce multiple candidate attempts
- candidate generation is bounded
- smoke comes before full evaluation unless the task is explicitly `fast-check` and direct quick validation is cheaper and equally informative

Use a validation-cost-aware seed policy:

- `fast-check`: the first objective smoke signal is likely under about `20` minutes
- `slow-check`: the first objective smoke signal is likely over about `20` minutes or expensive enough that broad probing is wasteful

For `fast-check` seed work:

- widen a bit more aggressively inside the line
- a seed batch of `3-5` candidates can be justified when they are genuinely differentiated
- prefer multiple orthogonal quick tests over one over-discussed candidate
- a separate smoke stage is optional; direct submission into quick parallel validation is acceptable when the first check is already cheap
- only skip smoke when the parallel quick validations are expected to produce distinguishable conclusions rather than repeated near-duplicate outcomes

For `slow-check` seed work:

- keep the initial seed batch tighter, usually `1-2` candidates and rarely `3`
- insist on a stronger reason for every candidate entering smoke
- prefer one dominant hypothesis plus one hedge candidate over a broad exploratory pool
- do not spend long runs to discover that the brief itself was weak

Do not keep a live implementation pool dominated by the same mechanism family.
Default active-pool rule:

- at most `1-2` live candidates from the same family
- if one family already fills the live pool, new same-family candidates do not enter smoke by default

## Loop protocol

Use `loop` when a durable line and implementation-candidate pool already exist and the main need is bounded forward motion.

Before changing code in `loop`, inspect the same-line local attempt memory for the current line.
Treat recent sibling attempts on the same line as the first memory surface, ahead of broader quest memory.

When running `loop`, choose one primary action:

- `smoke`
- `promote_to_full_eval`
- `archive`
- `record_main_result`
- `switch_to_fusion`
- `switch_to_debug`
- `stop`

Every loop pass should end with:

- one updated candidate status
- one updated next action
- one frontier review trigger

Do not leave the line with several half-started directions and no dominant next move.

Default exploit rule: one atomic improvement per pass.
Do not bundle several unrelated changes into one exploit candidate unless:

- the changes are one tightly coupled design package
- or the pass is explicitly a fusion route

MLEvolve-style behavior to preserve here:

- bounded parallelism
- small live candidate pool
- explicit move from draft -> smoke -> full eval -> archive or result
- measured frontier review after real evidence

Use a validation-cost-aware loop policy:

- for `fast-check` tasks, it is acceptable to run more quick, different tests before converging
- for `fast-check` tasks, direct quick validation may replace a separate smoke stage if that saves time without losing decision quality
- for `slow-check` tasks, use fewer but sharper passes, and require objective gain before widening or evolving further
- if the validation loop is slow, do not keep paying for frontier uncertainty that could have been reduced in `brief`
- if the validation loop is fast, prefer resolving uncertainty with evidence instead of over-arguing in chat

Use a branch/family diversity cap during exploitation:

- do not keep selecting only the locally familiar family because it is easiest to elaborate
- when several strong candidates are close, prefer the one that preserves frontier diversity
- if one branch or family already dominates recent attempts, require stronger evidence before selecting another near-duplicate attempt

## Memory protocol

Before broad new search, run at least one `memory.search(...)` using:

- the current task name
- the active idea id
- a method keyword
- the most recent failure mode or successful mechanism

When the search appears too narrow, also retrieve one of:

- a similar failure pattern
- an orthogonal success pattern
- a deliberately dissimilar but high-value prior attempt

For `seed`, `loop`, and `debug`, also inspect the same-line local attempt memory from the current leading line before widening to broader quest memory.

Write at least one quest memory card when you learn something reusable, such as:

- a successful optimization pattern
- a repeated failure pattern
- a fusion lesson
- a reason a candidate should not be retried

Use the integrated `optimization memory template` section for the minimum acceptable memory-card shape.

Do not write generic "we tried some optimization" memory cards.
Each card should be retrieval-friendly and decision-relevant.

## Artifact protocol

Use:

- `artifact.submit_idea(..., submission_mode='candidate')` for candidate briefs
- `artifact.submit_idea(..., submission_mode='line')` for durable promoted lines
- `artifact.record(payload={'kind': 'report', 'report_type': 'optimization_candidate', ...})` for within-line attempts
- `artifact.record(payload={'kind': 'decision', 'action': 'iterate'|'branch'|'continue'|'stop', ...})` for route changes
- `artifact.record_main_experiment(...)` for real measured line results

When the optimize pass is about ranking or promotion, also record one durable decision explaining:

- which briefs were compared
- which one won
- why promotion was justified now
- why the others were held, fused, or rejected

When recording implementation-level candidates, prefer these status values:

- `proposed`
- `smoke_running`
- `smoke_passed`
- `smoke_failed`
- `promoted`
- `full_eval_running`
- `succeeded`
- `failed`
- `archived`

Use `report_type='optimization_candidate'` consistently for implementation-level attempts so they can later be summarized into the frontier.

## Execution protocol

- Use `bash_exec` for smoke checks and full runs.
- Prefer bounded smoke before full evaluation unless `fast-check` direct validation is cheaper and equally informative.
- Do not keep rerunning the same unchanged candidate.
- If a candidate fails with a clear root cause, either debug it deliberately or archive it.
- If the same line stalls repeatedly, switch to exploit or fusion rather than pretending more of the same is new evidence.

Use this execution order by default:

1. candidate brief selection
2. implementation-level candidate generation
3. smoke test or direct quick validation
4. promotion to fuller evaluation when justified
5. durable result recording
6. frontier review

Prefer only a small active pool at once:

- usually `2-4` candidate briefs before promotion
- usually `2-3` live implementation candidates in smoke
- usually `1-2` full evaluations running at once unless the environment clearly supports more

Validation-cost-aware override:

- if first-pass validation is under about `20` minutes, it is reasonable to increase smoke breadth modestly and compare more alternatives early
- if first-pass validation is under about `20` minutes, you may skip a separate smoke stage and submit several quick validations in parallel
- only do that when the validations are likely to yield different conclusions such as clear win / tie / fail / instability, rather than redundant repeats
- if first-pass validation is slower than that, keep the active pool narrow and gate evolution on clear objective signal
- for slow validation, do not promote a candidate into heavier resource investment until smoke or pilot evidence shows a real performance improvement, stability improvement, or comparability-preserving advantage

## Code-generation route selection

Do not use the same code-generation route for every optimization step.

Prefer:

1. brief-first, no code yet
   - when the direction is still unclear
   - stay at candidate-brief level

2. stepwise generation
   - for the first substantial implementation of a new durable line
   - especially when the line touches multiple subsystems such as data processing, model design, and training/evaluation

3. diff / patch generation
   - when a strong current implementation already exists
   - for improve, exploit, debug, and most fusion work

4. full rewrite
   - only when the current implementation is too broken or too structurally mismatched for diff patching to remain safe

Use the integrated `codegen route playbook` section before committing to a larger rewrite.

## Debug protocol

Use `debug` when a candidate failed but still looks strategically valuable.

`debug` is bugfix-only.
Do not use a debug pass to sneak in a new performance-improvement idea.
If the proposed change goes beyond the minimal fix and becomes a new mechanism, stop and route back to `brief` or `loop` instead.

When a candidate fails:

- classify whether the failure is structural, local, or environmental
- retrieve similar failure patterns from memory before changing code
- prefer targeted fixes over broad rewrites
- define the exact post-fix bounded check before editing

Good debug prompts should make these explicit:

- the concrete error
- the likely root cause
- the minimal fix
- what must remain unchanged

Use the integrated `debug response template` section for the minimum acceptable debug response shape.

Archive rather than debug when:

- the failure is mostly strategic rather than local
- the candidate no longer looks better than the nearby alternatives
- the fix would effectively turn it into a different candidate anyway

## Fusion protocol

Use `fusion` only when the frontier justifies cross-line combination.

Before opening a fusion candidate:

- identify the real strength of each source line
- identify the real weakness of each source line
- explain why the strengths are complementary rather than redundant
- define what remains unchanged for comparability
- define the bounded evidence that would prove the fusion was worthwhile

Use the integrated `fusion playbook` section before launching cross-line fusion.

Do not fuse:

- two lines with the same mechanism under different names
- two weak lines that lack a clear strength
- merely because multiple branches exist

If the fusion hypothesis is still underspecified, return to `brief` instead of pretending fusion is ready.

## Prompt patterns worth preserving

For candidate-brief, improve, fusion, and debug prompts, preserve these recurring structures:

- Introduction
- Task description
- Memory
- Previous solution or previous line
- Instructions
- assistant_prefix when a stable response lead-in reduces drift
- explicit response format

And preserve these recurring reasoning contracts:

- root cause first
- WHAT / WHY / HOW
- KEEP UNCHANGED
- explicit next action

Use the integrated `prompt patterns` section as the canonical optimization prompt crib sheet.

## Plateau and fusion protocol

Treat repeated local edits without evidence gain as a search failure mode.

If one line shows repeated non-improving results:

- stop issuing near-duplicate attempts
- record the stagnation explicitly
- either widen the search or fuse with another line

Use the integrated `fusion playbook` section before launching cross-line fusion.
Use the integrated `plateau response playbook` section when deciding how to respond to repeated non-improving results.

Good fusion candidates usually satisfy both:

- each source line has at least one real strength
- the strengths are complementary rather than redundant

Do not fuse merely because two lines both exist.

When a line plateaus:

- stop issuing near-duplicate low-information attempts
- say explicitly that the line is plateauing
- force one larger route change:
  - widen the brief slate
  - promote a stronger alternative
  - fuse
  - debug one blocked but valuable candidate
  - stop

Do not hide plateau under a sequence of tiny "one more tweak" loops.

Family-shift trigger:

- if recent attempts stay inside one mechanism family and there is no meaningful improvement
- or if `success_patience >= 2`
- or if `total_patience >= 5`
- the next pass must not be another same-family Tier1 tweak
- instead choose one of:
  - orthogonal family
  - Tier2 or Tier3 shift
  - fusion
  - stop

This is the default anti-collapse rule for optimize.

## Task-category primer

Before widening a stale frontier, classify the task briefly into one or more dominant structures:

- tabular
- vision / spatial
- sequence / language
- graph / topology
- systems / optimization
- mixed

Then ask whether the current brief slate overfits one familiar method family for that task.
If it does, require at least one serious candidate from a different plausible family or lens before promotion.

## Stall-recovery protocol

If the optimize stage appears to stall, diagnose the stall explicitly instead of idling.

Common stall classes:

- no frontier information
- no candidate clearly worth promotion
- candidate pool is too similar
- repeated failures on one line
- no active runs and no next action recorded

Preferred recovery order:

1. refresh the frontier
2. inspect the current candidate board
3. inspect recent optimization memory
4. record one explicit route decision
5. continue with exactly one concrete next action

Do not leave the stage parked without a recorded reason and a concrete reopen condition.

## Stage-end requirement

Stage-end requirement:

- write at least one `memory.write(...)` when the pass produced a reusable success pattern, repeated failure pattern, fusion lesson, or explicit non-retry rule
- update `OPTIMIZE_CHECKLIST.md`
- update `CANDIDATE_BOARD.md` when the candidate pool changed
- leave one durable next action or stop condition

If nothing reusable was learned, record why this pass was still necessary instead of writing a fake memory card.

## Completion rule

This stage is complete only when one of these is durably true:

- a stronger line was promoted and the next anchor is clear
- the current line produced a real measured result and the next route is recorded
- the optimization frontier says stop and that stop decision is durably recorded

Do not treat one candidate creation or one smoke pass as stage completion.

## Integrated reference appendix

This appendix inlines the former `optimize/references/*.md` material so the skill remains self-contained.

### brief-shaping-playbook.md

# Brief Shaping Playbook

Use this reference when a candidate direction is still fuzzy and needs to become a structured, ranking-ready brief.

This playbook borrows the useful part of product-style brainstorming without importing a full software-spec workflow.
The goal is not a long design document.
The goal is a compact candidate brief that is clear enough to compare, rank, and either submit as `submission_mode='candidate'` or reject.

## 1. Clarify before widening

Before generating more variants, resolve the minimum ambiguity around:

- the concrete bottleneck
- the evaluation or comparability boundary
- the main hard constraint: data, metric, compute, latency, memory, interface, or training budget
- the current incumbent or baseline that this brief must beat or complement

If one unknown would materially change every candidate, clarify it first instead of generating a noisy slate.
Prefer one question at a time when clarification is genuinely needed.
If the answer is already available from durable state, use that instead of asking.

## 2. Generate a small differentiated slate

Default target: `2-3` serious approaches.

The slate should usually include:

- one incumbent-deepening refinement
- one orthogonal mechanism
- one broader shift candidate when justified

Do not produce several renamed variants of the same mechanism family.
If two variants differ only by parameter choice or patch detail, keep only the sharper one.

For each candidate, write:

- bottleneck
- why_current_line_is_limited
- mechanism
- why_now
- keep_unchanged
- expected_gain
- main_risks

## 3. Compare on one shared surface

Before recommending a winner, compare the serious candidates on the same dimensions:

- expected upside
- comparability safety
- implementation surface
- mechanism distinctness
- failure risk
- reason this route is better now than the nearby alternatives

Do not let each candidate justify itself with a different scoring story.
Use one comparison surface so ranking is auditable.

## 4. Recommend exactly one lead brief

After comparison, recommend one lead brief and explain:

- why it is the best next move now
- why the main alternatives are deferred instead of promoted
- what evidence would quickly disconfirm the lead brief

Do not say "all are promising" and promote everything.
If the slate is still too close to call, return to widening once or narrow the slate further.

## 5. Self-check before submission

Before calling `artifact.submit_idea(..., submission_mode='candidate', ...)`, check:

- Is the bottleneck concrete rather than generic?
- Does `why_current_line_is_limited` explain a real gap instead of restating the mechanism?
- Does `why_now` explain what changed in evidence, failure pattern, or frontier state?
- Is the comparability boundary explicit?
- Is the recommendation based on tradeoffs rather than implementation convenience?
- Would the brief still make sense if handed to another agent with no chat context?

If any answer is no, refine the brief before submission.

## 6. Output shape

A good final brief package is short and structured:

1. brief title
2. one-paragraph bottleneck and constraint summary
3. a `2-3` candidate comparison table or bullet slate
4. recommended brief with tradeoff summary
5. self-check outcome
6. fields ready for the integrated `method-brief-template.md` section

Keep it compact.
This is a shaping pass for optimization candidates, not a paper draft or engineering spec.

### candidate-board-template.md

# CANDIDATE_BOARD.md

| Candidate ID | Level | Parent | Strategy | Status | Expected Gain | Observed Result | Promote / Archive |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cand-001 | brief | current-head | explore | proposed | Better tail accuracy | n/a | pending |
| cand-002 | impl | cand-001 | exploit | smoke_passed | Faster convergence | smoke ok | consider promote |

Notes:

- `Level` should be `brief` or `implementation`
- `Parent` may be a branch, idea id, run id, or candidate id
- `Strategy` should usually be one of `explore`, `exploit`, `fusion`, `debug`
- `Promote / Archive` should be a clear recommendation, not an empty placeholder

### candidate-ranking-template.md

# Candidate Ranking Template

## Candidate Set

- Candidate IDs:
- Ranking scope:
- Comparison surface:

## Criteria

- expected information gain
- feasibility in current repo
- comparability against baseline
- implementation surface
- likely novelty or distinctiveness
- risk of redundant overlap
- incumbent-improvement potential
- distinctness from other candidates
- mechanism-family diversity
- change-layer diversity

## Ranked Candidates

1. `candidate_id`
   Score summary:
   Why it ranks here:
   Promote / hold / reject:

2. `candidate_id`
   Score summary:
   Why it ranks here:
   Promote / hold / reject:

3. `candidate_id`
   Score summary:
   Why it ranks here:
   Promote / hold / reject:

## Winner Justification

Why the selected candidate should become a durable line now.

## Non-Winner Notes

Why the other candidates were deferred, fused, or rejected.

## Promotion Cap

- how many candidates should be promoted now:
- why more promotion would dilute the frontier:
- same-family cap override justification:

### codegen-route-playbook.md

# Codegen Route Playbook

Choose the code-generation route deliberately.

## Use brief-only

Use no-code candidate briefs when:

- the direction is still underspecified
- multiple distinct directions still need ranking
- a new line should not be promoted yet

## Use stepwise generation

Prefer stepwise generation when:

- a new durable line is being implemented for the first time
- the change spans data processing, model design, and training/evaluation
- a modular decomposition will reduce large integrated errors
- a plan -> refine -> implement sequence is safer than one monolithic edit

## Use diff / patch generation

Prefer diff / patch generation when:

- a strong current implementation already exists
- the current change is local enough to preserve most of the line
- the task is improve, exploit, debug, or most fusion work
- the desired change can be described as a bounded delta from the current solution

## Use full rewrite

Use a full rewrite only when:

- the existing implementation is structurally broken
- the desired architecture no longer matches the current codebase shape
- diff patching would be more fragile than replacement

Do not jump to a rewrite merely because one local patch failed.

## Response shape

For non-trivial codegen work, prefer this shape:

1. short plan
2. bounded implementation surface
3. keep-unchanged contract
4. validation step

Do not go from a vague idea directly into a large patch with no intermediate plan.

### debug-response-template.md

# Debug Response Template

## Error

What concrete error or failure occurred?

## Retrieved Memory

What similar failure pattern or repair lesson should be reused before changing code?

## Root Cause

What is the most likely underlying cause?

## Minimal Fix

What is the smallest plausible fix?

## Keep Unchanged

What parts of the line must remain unchanged for comparability and stability?

## Next Check

What bounded smoke or validation check should confirm the fix?

## Archive Threshold

What outcome would prove this candidate should be archived instead of debugged again?

### frontier-review-template.md

# Frontier Review Template

## Current Frontier

- mode:
- best branch:
- best run:
- stagnant branches:
- candidate backlog:
- fusion candidates:

## Evidence Summary

- strongest support:
- strongest contradiction:
- biggest unresolved risk:

## Route Choice

- explore / exploit / fusion / debug / stop:
- why this is the best next move:

## Active Optimize Submode

- brief / rank / seed / loop / fusion / debug:
- why this submode is dominant now:

## Immediate Next Action

- exact next step:
- what result will trigger another frontier review:
- what result would force a different mode:

### fusion-playbook.md

# Fusion Playbook

Use fusion only when:

- at least two lines have real strengths
- the strengths are complementary
- one line alone is no longer improving fast enough

Before fusion, write down:

- source line A:
  strongest mechanism:
  strongest evidence:
  main weakness:
  what must survive the fusion:

- source line B:
  strongest mechanism:
  strongest evidence:
  main weakness:
  what must survive the fusion:

Then answer:

- what exactly is being fused?
- why does this combination address a real bottleneck?
- why are the source strengths complementary rather than redundant?
- what remains unchanged for comparability?
- what evidence would prove the fusion was worth it?
- what bounded first validation step should run before any broad rollout?

Do not fuse:

- two lines with the same mechanism under different names
- two weak lines with no clear strengths
- merely because multiple branches exist

### method-brief-template.md

# Method Brief Template

## Title

One short line naming the candidate direction.

## Bottleneck

What concrete bottleneck or limitation does this target?

## Why Current Line Is Limited

Why is the current best line or baseline not already solving this?

## Mechanism

What specific intervention or design change is proposed?

## Mechanism Family

Name the family explicitly, for example `adapter`, `loss`, `architecture`, `augmentation`, `ensemble`, `retrieval`, `objective-shift`.

## Change Layer

One of:

- `Tier1`: local optimization / training detail
- `Tier2`: representation or component change
- `Tier3`: paradigm or system-level shift

## Source Lens

Where did this candidate come from?

- baseline_refinement
- orthogonal_mechanism
- failure_repair
- cross_domain_transfer
- objective_shift
- search_widening

## Keep Unchanged

What must remain stable for comparability?

## Expected Gain

What evidence should improve if this works?

## Implementation Surface

- main files or modules likely involved:
- likely change scope: local / moderate / broad

## Risks

- Main failure mode
- Comparability risk
- Implementation risk

## Foundation

- Source branch / run / baseline:
- Why this foundation is the right starting point:

## Promote Now

- yes / no
- why:

## Next Target

Usually `optimize` or `experiment`.

### optimization-memory-template.md

# Optimization Memory Template

## Type

- success pattern / failure pattern / fusion lesson

## Context

- task:
- branch or idea:
- candidate id:
- strategy:

## Observation

What actually happened?

## Why It Matters

Why should a later optimization pass retrieve this?

## Retrieval Hint

- query keywords:
- closest line or mechanism family:
- when this should be recalled first:

## Reuse Hint

When should this lesson be reused, and when should it be avoided?

### optimize-checklist-template.md

# OPTIMIZE_CHECKLIST.md

- [ ] Read `artifact.get_optimization_frontier(...)` or equivalent durable frontier summary
- [ ] Select the primary optimize submode: `brief`, `rank`, `seed`, `loop`, `fusion`, or `debug`
- [ ] Confirm whether the current pass is `explore`, `exploit`, `fusion`, `debug`, or `stop`
- [ ] Review recent optimization memory before generating new candidates
- [ ] Check whether the current brief slate covers more than one mechanism family
- [ ] Candidate briefs updated or confirmed
- [ ] Candidate ranking updated
- [ ] Promote only the strongest brief(s) into durable line(s) if justified
- [ ] Current implementation candidate pool recorded
- [ ] Smoke queue defined
- [ ] Full-eval queue defined
- [ ] Recent failures classified and either debugged or archived
- [ ] Stagnation check performed
- [ ] Family-shift trigger checked
- [ ] Fusion eligibility checked
- [ ] Next concrete action written

### plateau-response-playbook.md

# Plateau Response Playbook

Use this when one line keeps producing non-improving results.

## Plateau indicators

- repeated non-improving results on the same line
- repeated "small tweak" proposals with no structural change
- candidate queue filled with near-duplicate mechanisms

## Required response

1. state that the line is plateauing
2. identify the most likely root cause of the plateau
3. choose one of:
   - widen search
   - promote a stronger alternative
   - fuse with another line
   - debug a strategically valuable blocked candidate
   - stop the line
4. record one explicit non-repeat rule so the next pass does not retry the same low-information move

## Do not do

- keep proposing near-identical local tweaks
- rerun the same unchanged candidate
- fuse without a clear complementary mechanism
- hide a plateau under a sequence of tiny "one more tweak" edits

### prompt-patterns.md

# Optimization Prompt Patterns

These prompt structures are worth preserving across optimize subroutines.

## Common skeleton

- Introduction
- Task description
- Memory
- Previous solution or previous line
- Instructions
- assistant_prefix when a stable response lead-in reduces drift
- Explicit response format

## Common reasoning contract

- WHAT is changing?
- WHY is the current line limited?
- HOW should the change address the limitation?
- KEEP UNCHANGED: what must remain stable for comparability?
- NEXT ACTION: what concrete step follows this prompt?

## Plateau pattern

When the line is stagnating:

- explicitly state that the current approach has plateaued
- forbid trivial hyperparameter-only tweaks when a deeper change is needed
- require a larger representational or architectural shift

## Fusion pattern

When combining lines:

- identify the real strength of each source line
- explain why those strengths are complementary
- avoid combining everything
- preserve the comparison surface

## Debug pattern

For debugging:

- restate the concrete error
- state the likely root cause
- require the minimal targeted fix
- preserve the original solution intent unless the bug proves the design invalid
