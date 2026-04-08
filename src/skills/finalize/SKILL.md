---
name: finalize
description: Use when the quest is ready to consolidate final claims, limitations, recommendations, summary state, and graph exports before stopping or archiving.
skill_role: stage
---

# Finalize

Use this skill to close or pause a quest responsibly.

## Interaction discipline

- Follow the shared interaction contract injected by the system prompt.
- For ordinary active work, prefer a concise progress update once work has crossed roughly 6 tool calls with a human-meaningful delta, and do not drift beyond roughly 12 tool calls or about 8 minutes without a user-visible update.
- Do not emit another finalize progress update when the user-visible state is unchanged.
- If the runtime starts an auto-continue turn with no new user message, keep finalizing from the durable quest state and active requirements instead of replaying the previous user turn.
- If a threaded user reply arrives, interpret it relative to the latest finalize progress update before assuming the task changed completely.
- When finalize reaches a real closure state, pause-ready packet, or route-back decision, send one threaded `artifact.interact(kind='milestone', ...)` update that names the recommendation, why it is the right call, and any reopen condition that still matters.
- True quest completion still requires explicit user approval through the runtime completion flow before calling `artifact.complete_quest(...)`.
- Rechecking that the same bundle files still exist, or re-aligning status surfaces without changing the closure judgment, does not by itself count as a fresh milestone.
- Hard execution rule: if this stage needs terminal work such as Git inspection, packaging checks, document builds, or file inspection, every such command must go through `bash_exec`.

## Three-layer todo contract

- keep quest-root `plan.md` as the top-level research map and closure map
- keep workspace `PLAN.md` as the active finalize-node contract when closure work is multi-step
- keep workspace `CHECKLIST.md` as the finalize execution frontier with one real in-progress item and a short `Next` list
- if the frontier stops changing, stop nesting closure chores and make the route judgment explicit

## Research-map role

- `finalize` is the loop-closure controller, not automatic quest death
- the finalize outcome should update quest-root `plan.md` to one of: `stop`, `park_and_continue_later`, or `publish_and_continue_from_new_incumbent`
- every finalize handoff should leave explicit reopen conditions and, when relevant, the next loop candidate

## Current-node plan and checklist

When finalize work is multi-step, create or refresh:

- workspace `PLAN.md` as the finalize-node contract
- workspace `CHECKLIST.md` as the finalize execution frontier

The finalize node should make explicit:

- which closure state is currently most justified
- what evidence still blocks closure
- what reopen condition still matters
- whether the next edge is stop, park, or a new loop

## Stage purpose

The finalize stage should not pretend every line succeeded.
It should produce the most accurate final state of the quest:

- what is supported
- what is only partially supported
- what failed
- what remains open
- whether the right move is stop, archive, publish, or continue later

Finalize is not just a short summary.
It is the durable closure protocol that turns a long-running research graph into a recoverable stopping point, a publishable handoff, or an honest continue-later checkpoint.

## Use when

- the evidence base is stable enough for a final recommendation
- the writing line is sufficiently complete
- the user asked for a final summary or closure
- the quest should be paused or archived with a clean state

## Do not use when

- major evidence gaps are still unresolved
- the current line obviously needs another experiment or analysis pass
- the quest is still in exploratory ideation

## Preconditions and gate

Before finalizing, gather:

- latest baseline state
- latest accepted run and analysis state
- latest writing state
- latest decisions and open blockers
- latest quest documents
- latest review / proofing / submission state when a paper bundle exists
- the paper bundle manifest and its referenced paths when the quest has a paper-like deliverable
- the paper evidence ledger and selected-outline section statuses when the quest has a paper-like deliverable

If finalization reveals that the quest is still too uncertain, route back through `decision` rather than forcing closure.
For paper-like deliverables, do not finalize while any of these remain true:

- required main-text outline items are still unresolved
- completed analysis remains unmapped into the paper contract
- the active paper line still reports open supplementary work that is expected to block the manuscript

If the current paper-state blocker is not obvious from the existing files, call `artifact.get_paper_contract_health(detail='full')` before deciding whether finalize is legitimate.
If the active quest/runtime state is unclear after restart or long pause, call `artifact.get_quest_state(detail='summary')` first.
If the exact latest `SUMMARY.md`, `status.md`, or active user requirement wording matters for closure, call `artifact.read_quest_documents(...)`.
If earlier user/assistant continuity matters for whether the quest should really stop, call `artifact.get_conversation_context(...)` instead of guessing from prompt context alone.

## Truth sources

Use:

- `SUMMARY.md`
- latest decisions
- baseline artifacts
- run artifacts
- analysis reports
- writing outputs
- review, proofing, and submission outputs when they exist
- Git history and graph
- durable literature notes already produced during the quest
- outputs or notes gathered through `artifact.arxiv(...)` when final claim checks require rereading an arXiv paper

Do not finalize from chat memory alone.

## Required durable outputs

The finalize stage should usually leave behind:

- refreshed `SUMMARY.md`
- refreshed `status.md`
- final report artifact
- final decision artifact
- refreshed Git graph
- explicit limitations and next-step recommendation
- a final claim ledger or equivalent claim-status summary
- a compact resume packet or handoff packet when later continuation is plausible

If the quest produced a paper-style bundle, finalization should also check that the writing stage left behind enough closure evidence, such as:

- selected outline and outline selection records
- evidence ledger records and section-level result tables
- review output
- proofing output
- submission or packaging checklist
- final draft or bundle manifest

## Workflow

### 1. Consolidate the accepted evidence and package inventory

State clearly:

- accepted baseline
- strongest supported claims
- weaker or partial claims
- important negative results
- unresolved risks
- key deliverables that exist and where they live

Do not only say that evidence exists.
Say clearly what exists and why it matters. Name concrete paths or artifact ids only when the user asks for them or needs them to act.
When a paper bundle exists, verify the manifest inventory explicitly, including:

- `paper/paper_bundle_manifest.json`
- `paper/evidence_ledger.json`
- the recorded `paper_branch` and source evidence branch / run fields in that manifest
- referenced `outline_path`
- referenced `draft_path`
- referenced `writing_plan_path`
- referenced `references_path`
- referenced `claim_evidence_map_path`
- referenced `evidence_ledger_path`
- referenced `baseline_inventory_path`
- referenced `compile_report_path`
- referenced `pdf_path`
- referenced `latex_root_path`
- `release/open_source/manifest.json` when open-source preparation has started
- `release/open_source/cleanup_plan.md` when the paper line is being prepared for a public code release

### 2. Build the final claim ledger

For every important outcome, classify it as one of:

- supported
- partially supported
- unsupported
- deferred

For each claim, record:

- claim text or claim id
- evidence paths
- key caveats
- whether it is safe to surface in summaries or papers

If a claim was once believed and later weakened, preserve that downgrade history rather than silently deleting it.

Also build a compact belief-change log for the most important claim transitions, such as:

- supported -> partial
- partial -> unsupported
- promising route -> abandoned
- draft-ready -> evidence-gap

For each transition, record:

- what changed
- which evidence caused the change
- what the new recommendation is

### 3. Produce a final limitations and failure section

Limitations should include:

- data or split limitations
- metric limitations
- implementation limitations
- robustness limitations
- reproducibility risks
- claims intentionally not made

Also preserve:

- failed branches that meaningfully changed the research direction
- blocked items that remain unresolved
- confounders or comparability issues that weaken confidence
- handoff cautions for anyone resuming the quest later

### 4. Produce the final recommendation

Choose the most honest next recommendation, such as:

- stop and archive
- stop and publish
- continue later with a targeted experiment
- continue later with a targeted analysis campaign
- reset the current line and revisit ideation

The recommendation should include:

- the chosen action
- why that action is appropriate now
- what evidence most strongly supports it
- what would have to become true to justify a different recommendation

When deciding whether the quest is publish-ready or only archive-ready, be explicit about which writing or validation gates have actually passed.

### 5. Build a resume or handoff packet

If the quest may continue later, leave behind a compact restart packet that answers:

- where the strongest evidence is
- what the current accepted baseline is
- what the current preferred route is
- what the top blockers are
- what should be read first on resume
- what should not be repeated

This packet should be short, high-signal, and directly usable by a future agent turn.

### 6. Refresh the durable quest view

Refresh:

- `SUMMARY.md`
- `status.md`
- Git graph export

If the summary changes materially, make it clear why the quest is now considered final or paused.

When summarizing long histories, prefer the highest-impact findings and decisions rather than a full chronological replay.

### 7. Record the final decision

The final stage should end with an explicit durable decision or report rather than an implied stopping point.
If multiple closure options were available, record why the chosen one beat the alternatives.

## Finalization-quality rules

Good finalization:

- distinguishes supported findings from hopes
- preserves negative evidence
- names open questions honestly
- leaves a clean state for later resumption
- exposes whether writing/proofing/submission gates passed or failed
- makes reopen conditions explicit

Weak finalization:

- overclaims unresolved work
- hides failed branches
- skips limitations
- leaves no clear recommendation
- claims “done” without showing what is actually done
- drops the package or file inventory needed for resumption
- ignores unmapped completed analysis that never entered the paper contract

## Memory rules

Stage-start requirement:

- begin every finalize pass with `memory.list_recent(scope='quest', limit=5)`
- then run at least one finalize-relevant `memory.search(...)` before closure writing
- if several idea, run, or campaign lines exist, retrieve only the memory tied to the line being finalized unless the final report is explicitly comparing lines

Finalize should read memory before writing closure, especially:

- quest `decisions`
- quest `knowledge`
- quest `episodes`
- quest `papers` when the final story depends on citation or literature context

If final closure depends on rereading a paper, keep the same split:

- use web search only to relocate or verify the paper reference
- use `artifact.arxiv(paper_id=..., full_text=False)` for the actual paper reading or refresh
- switch to `full_text=True` only when the shorter view is insufficient

Write to memory only when the lesson is reusable across quests, such as:

- general methodological pitfalls
- robust baseline lessons
- durable writing or evaluation lessons

Stage-end requirement:

- if finalize produced a durable cross-quest lesson worth reusing later, write at least one `memory.write(...)` before leaving the stage

Quest-specific closure state belongs in files and artifacts first, not only memory.

## Artifact rules

Typical final artifacts:

- report artifact summarizing final state
- decision artifact indicating stop, archive, or continue-later recommendation
- graph artifact via `artifact.render_git_graph()`

Good final artifacts often include:

- a final report focused on supported findings, limitations, and packaging state
- a final decision with action, reasons, and reopen conditions
- a graph export when the path through the quest matters for later resumption
- a milestone only when a human-facing checkpoint helps

## Failure and blocked handling

If finalization is premature, record that explicitly.

Common blocked finalize states:

- unresolved_major_claim
- unresolved_write_gate
- missing_proofing_or_submission_checks
- unclear_final_recommendation
- missing_handoff_packet
- stale_summary_or_graph
- unresolved_package_inventory

In that case, route back to the proper stage through `decision`.

## Extra references

Use these references when you need a denser closure checklist:

- `references/finalization-checklist.md`
- `references/resume-packet-template.md`

## Exit criteria

Exit the finalize stage once one of the following is durably true:

- a final or pause-ready summary exists
- the graph is refreshed
- the limitations and recommendation are explicit
- the stopping point is recorded through artifact
- the claim ledger and package inventory are clear enough for later resumption or publication handoff
