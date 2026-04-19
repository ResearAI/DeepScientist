# 02 Start Research Guide: Fill the Start Research Contract

This page documents the current `Start Research` dialog and the exact startup contract it submits.

Implementation sources:

- `src/ui/src/lib/startResearch.ts`
- `src/ui/src/components/projects/CreateProjectDialog.tsx`

## What the dialog does

`Start Research` is not only a “new project” form. It does four things together:

1. collects structured kickoff context
2. compiles that context into the first project prompt
3. binds an optional reusable baseline
4. persists a structured `startup_contract` for later prompt building

## Worked example: a cleaned-up version of quest 025

The quickest way to understand the dialog is to walk through a real example.

This example is adapted from a real project input in quest `025`, but normalized into a cleaner public form. The task is:

- reproduce the official Mandela-Effect baseline
- keep the original task and evaluation protocol
- study stronger truth-preserving collaboration under mixed correct and incorrect social signals
- use two local OpenAI-compatible endpoints to keep throughput high

### Short fields in the current frontend

| Field in the dialog | Example value | Why |
|---|---|---|
| `Project title` | `Mandela-Effect Reproduction and Truth-Preserving Collaboration` | Clear project title for cards, workspace headers, and later search |
| `Project ID` | leave blank, or set `025` | Leave blank for automatic sequential ids; only pin it manually if you need a fixed id |
| `Connector delivery` | `Local only` for the first run, or one QQ target if already configured | The current frontend allows at most one external connector target per quest |
| `Reusable baseline` | empty for the first run, or the imported official baseline if already available | If selected, derived `baseline_mode` becomes `existing` |
| `Research paper` | `On` | Keep paper-oriented analysis and writing in scope |
| `Research intensity` | `Balanced` | Secure the baseline, then probe one justified direction |
| `Decision mode` | `Autonomous` | Keep moving unless a real blocking decision depends on the user |
| `Launch mode` | `Standard` | Start from the ordinary research graph |
| `Language` | `English` | Use English for the kickoff prompt and user-facing artifacts |

### Multi-line fields for the same example

`Primary research request`

```text
Please reproduce the official Mandela-Effect repository and paper, then study how to improve truth-preserving collaboration under mixed correct and incorrect social signals.

The core research question is: how can a multi-agent system remain factually robust under social influence while still learning from correct peers?

Keep the task definition and evaluation protocol aligned with the original work. Focus on prompt-based or system-level methods that improve truth preservation without simply refusing all social information.
```

`Baseline links`

```text
https://github.com/bluedream02/Mandela-Effect
```

`Reference papers / repos`

```text
https://arxiv.org/abs/2602.00428
```

`Runtime constraints`

This snippet is a tutorial reference only, not a DeepScientist default endpoint setup. Replace the endpoints, API key, and model with your real runtime before you paste it.

```text
- Keep the task definition and evaluation protocol aligned with the official baseline unless a change is explicitly justified.
- Use two OpenAI-compatible inference endpoints for throughput:
  - `http://127.0.0.1:<port-a>/v1`
  - `http://127.0.0.1:<port-b>/v1`
- Use your actual API key `<YOUR_API_KEY>` and model `<YOUR_MODEL>` on both endpoints.
- Keep generation settings close to the baseline unless a justified adjustment is required.
- Implement asynchronous execution, automatic retry on request failure, and resumable scripts.
- Split requests across both endpoints so throughput stays high without overloading the service.
- Record failed, degraded, or inconclusive runs honestly instead of hiding them.
```

`Goals`

```text
1. Restore and verify the official Mandela-Effect baseline as a trustworthy starting point.
2. Measure key metrics and failure modes on the designated `gpt-oss-120b` setup.
3. Propose at least one literature-grounded direction for stronger truth-preserving collaboration.
4. Produce experiment and analysis artifacts that are strong enough to support paper writing.
```

### What the frontend derives from this example

If you leave `Reusable baseline` empty and choose `Balanced`, the current frontend derives:

- `scope = baseline_plus_direction`
- `baseline_mode = auto`
- `resource_policy = balanced`
- `time_budget_hours = 24`
- `git_strategy = semantic_head_plus_controlled_integration`

If you select a reusable baseline entry, only one derived field changes:

- `baseline_mode = existing`

## Current frontend model

### `StartResearchTemplate`

```ts
type StartResearchTemplate = {
  title: string
  quest_id: string
  goal: string
  baseline_id: string
  baseline_variant_id: string
  baseline_urls: string
  paper_urls: string
  review_materials: string
  runtime_constraints: string
  objectives: string
  need_research_paper: boolean
  research_intensity: 'light' | 'balanced' | 'sprint'
  decision_policy: 'autonomous' | 'user_gated'
  launch_mode: 'standard' | 'custom'
  custom_profile: 'continue_existing_state' | 'review_audit' | 'revision_rebuttal' | 'freeform'
  review_followup_policy: 'audit_only' | 'auto_execute_followups' | 'user_gated_followups'
  baseline_execution_policy:
    | 'auto'
    | 'must_reproduce_or_verify'
    | 'reuse_existing_only'
    | 'skip_unless_blocking'
  manuscript_edit_mode: 'none' | 'copy_ready_text' | 'latex_required'
  entry_state_summary: string
  review_summary: string
  custom_brief: string
  user_language: 'en' | 'zh'
}
```

Important point: `scope`, `baseline_mode`, `resource_policy`, `time_budget_hours`, and `git_strategy` are no longer edited directly in the form. They are derived from `research_intensity` plus whether a reusable baseline is selected.

New explicit launch-time controls also exist:

- `baseline_source_mode`
- `execution_start_mode`
- `baseline_acceptance_target`

These are not replacements for the derived contract. They are stronger user-facing route preferences that tell the agent:

- whether to verify a local existing system, attach a reusable baseline, reproduce from source, repair a stale baseline, or defer baseline work until it is actually blocking
- whether to stop after a bounded plan for approval before heavy execution
- how strong the baseline must be before the quest should move into idea selection and experiments

### Derived contract fields

```ts
type StartResearchContractFields = {
  scope: 'baseline_only' | 'baseline_plus_direction' | 'full_research'
  baseline_mode:
    | 'existing'
    | 'restore_from_url'
    | 'allow_degraded_minimal_reproduction'
    | 'stop_if_insufficient'
  resource_policy: 'conservative' | 'balanced' | 'aggressive'
  time_budget_hours: string
  git_strategy:
    | 'branch_per_analysis_then_paper'
    | 'semantic_head_plus_controlled_integration'
    | 'manual_integration_only'
}
```

Resolution logic lives in `resolveStartResearchContractFields(...)`.

## Backend payload

The dialog submits:

```ts
{
  title,
  goal: compiled_prompt,
  quest_id,
  requested_connector_bindings: [
    {
      connector,
      conversation_id
    }
  ],
  requested_baseline_ref: {
    baseline_id,
    variant_id
  } | null,
  startup_contract: {
    schema_version: 3,
    user_language,
    need_research_paper,
    research_intensity,
    decision_policy,
    launch_mode,
    custom_profile,
    review_followup_policy,
    baseline_execution_policy,
    manuscript_edit_mode,
    scope,
    baseline_mode,
    resource_policy,
    time_budget_hours,
    git_strategy,
    runtime_constraints,
    objectives: string[],
    baseline_urls: string[],
    paper_urls: string[],
    review_materials: string[],
    entry_state_summary,
    review_summary,
    custom_brief,
  }
}
```

## Field reference

### Core project identity

**`title`**

- Human-readable project title.
- Used in cards and workspace headers.
- Does not need to equal `quest_id`.

**`quest_id`**

- Stable project identifier stored in `quest_id` and used as the directory name.
- By default the runtime suggests the next sequential id.
- Manual override is allowed.

**`goal`**

- Main scientific request.
- This becomes the central body of the compiled kickoff prompt.
- Good input: scientific question, target, success condition, boundary.
- Bad input: low-level implementation instructions with no research framing.

**`user_language`**

- Declares the preferred user-facing language for kickoff and later interaction.

### Connector delivery

**`requested_connector_bindings`**

- Submitted alongside the project create payload, not inside `startup_contract`.
- The current frontend allows at most one external connector target per quest.
- Typical shape:

```ts
[
  {
    connector: 'qq',
    conversation_id: 'qq:private:openid-123'
  }
]
```

- If you keep the project local-only, this array is empty.
- If the selected target is already bound to another quest, rebinding this project will replace the old binding.

### Baseline and references

**`baseline_id`**

- Selects a reusable baseline from the registry.
- When present, derived `baseline_mode` becomes `existing`.
- Runtime should attach and verify this baseline before ordinary downstream work.

**`baseline_variant_id`**

- Optional variant selector inside a baseline entry.

**`baseline_urls`**

- Fallback source links or absolute local file/folder paths when there is no registered reusable baseline.
- Submitted as `string[]`.

**`paper_urls`**

- Papers, repos, manuscripts, benchmarks, leaderboards, or absolute local file/folder paths that shape early scouting or writing work.
- Submitted as `string[]`.

**`review_materials`**

- Only meaningful for `review_audit` or `revision_rebuttal`.
- Use one URL or one absolute local file/folder path per line for reviewer comments, decision letters, meta-review notes, or revision packets.
- Submitted as `string[]`.

### Constraints and objectives

**`runtime_constraints`**

- Hard constraints such as budget, hardware, privacy, storage, or deadlines.

**`objectives`**

- One goal per line.
- Submitted as `string[]`.
- This should state the next meaningful outcomes, not generic aspirations.

**`need_research_paper`**

- `true`: the project should keep going through analysis and writing readiness.
- `false`: optimize for the strongest justified algorithmic result and avoid default paper routing.

### High-level control knobs

**`research_intensity`**

- `light`
  - derived contract: baseline-only, conservative, 8h, manual integration
- `balanced`
  - derived contract: baseline-plus-direction, balanced, 24h, controlled integration
- `sprint`
  - derived contract: full research, aggressive, 48h, branch-per-analysis

This is the main public knob for round depth.

**`decision_policy`**

- `autonomous`
  - the agent should keep choosing ordinary routes on its own
  - after one turn finishes, it should keep moving automatically: if no real long-running external task exists yet, keep preparing or launching it; once a real long-running external task exists, background monitoring should become low-frequency instead of sub-minute polling
- `user_gated`
  - the agent may raise a blocking decision only when continuation truly depends on the user

Practical note on workspace mode:

- DeepScientist also distinguishes a user-directed `copilot` workspace mode from the default `autonomous` mode.
- In `copilot`, completing the current requested unit should normally park and wait for the next user message or `/resume`.
- In `autonomous`, the quest should not park just because no long-running task is active yet; it should keep pushing toward the next real long-running unit of work.

### Launch mode

**`launch_mode`**

- `standard`
  - start from the ordinary canonical research loop
- `custom`
  - do not assume a blank-slate launch; use the extra custom-entry fields

**`custom_profile`**

Only meaningful when `launch_mode = custom`.

- `continue_existing_state`
  - start by auditing existing baselines, results, drafts, or mixed project assets
  - prompt builder should steer the agent toward `intake-audit`
- `review_audit`
  - start from a substantial draft or paper package that needs an independent skeptical audit
  - prompt builder should steer the agent toward `review`
- `revision_rebuttal`
  - start from reviewer comments, revision packets, or a rebuttal task
  - prompt builder should steer the agent toward `rebuttal`
- `freeform`
  - use this as the “Other” path
  - follow a custom brief with minimal forced workflow assumptions

**`baseline_execution_policy`**

- Only meaningful when `launch_mode = custom`.
- `auto`
  - let the startup contract and current evidence decide
- `must_reproduce_or_verify`
  - verify or recover the rebuttal-critical baseline/comparator before reviewer-linked follow-up work
- `reuse_existing_only`
  - trust the current baseline/results unless they are inconsistent or unusable
- `skip_unless_blocking`
  - skip baseline reruns unless a named review/rebuttal item truly depends on a missing comparator

**`review_followup_policy`**

- Mainly meaningful for `review_audit`.
- `audit_only`
  - stop after the audit artifacts and route recommendation
- `auto_execute_followups`
  - continue automatically into the justified experiments and manuscript deltas after the audit
- `user_gated_followups`
  - finish the audit first, then ask for approval before expensive follow-up work

**`manuscript_edit_mode`**

- Mainly meaningful for `review_audit` and `revision_rebuttal`.
- `none`
  - planning artifacts only
- `copy_ready_text`
  - produce section-level revision text that is ready to paste into the manuscript
- `latex_required`
  - prefer the provided LaTeX tree as the writing surface and produce LaTeX-ready replacement text
  - if you choose this mode, it is best to provide the LaTeX source tree via local path / folder input

**`entry_state_summary`**

- Plain-language summary of what already exists.
- Typical content:
  - trusted baseline exists
  - main run already finished
  - partial draft already exists
  - supplementary figures already exist

**`review_summary`**

- Only meaningful for review-driven work.
- Summarizes reviewer requests, revision demands, or meta-review constraints.

**`custom_brief`**

- Extra launch-time instruction that can narrow or override the default blank-slate full-research path.

## Derived contract mapping

Current preset mapping:

| `research_intensity` | `scope` | `baseline_mode` | `resource_policy` | `time_budget_hours` | `git_strategy` |
|---|---|---|---|---:|---|
| `light` | `baseline_only` | `stop_if_insufficient` | `conservative` | `8` | `manual_integration_only` |
| `balanced` | `baseline_plus_direction` | `restore_from_url` | `balanced` | `24` | `semantic_head_plus_controlled_integration` |
| `sprint` | `full_research` | `allow_degraded_minimal_reproduction` | `aggressive` | `48` | `branch_per_analysis_then_paper` |

Override rule:

- if `baseline_id` is selected, derived `baseline_mode` becomes `existing`
- if `baseline_source_mode` is explicitly set, treat it as the stronger route preference and use `baseline_mode` only as the compact derived summary

## Prompt compilation behavior

`compileStartResearchPrompt(...)` writes a human-readable kickoff prompt containing:

- project bootstrap
- primary research request
- research goals
- baseline context
- reference papers / repositories
- operational constraints
- research delivery mode
- decision handling mode
- launch mode
- research contract
- mandatory working rules

Custom launch behavior is explicit:

- `standard`
  - tells the agent to use the ordinary research graph
- `custom + continue_existing_state`
  - tells the agent to audit and normalize existing assets first
  - explicitly prefers `intake-audit`
- `custom + review_audit`
  - tells the agent that the current draft/paper state is the active contract
  - explicitly prefers `review`
- `custom + revision_rebuttal`
  - tells the agent to interpret reviewer comments and current paper state first
  - explicitly prefers `rebuttal`
- `custom + freeform`
  - tells the agent to follow the custom brief and open only the necessary skills

## Example payloads

### Standard launch

```json
{
  "title": "Sparse adapter robustness",
  "goal": "Investigate whether sparse routing improves robustness without hurting compute efficiency.",
  "quest_id": "012",
  "requested_baseline_ref": {
    "baseline_id": "adapter-baseline",
    "variant_id": "default"
  },
  "startup_contract": {
    "schema_version": 3,
    "user_language": "en",
    "need_research_paper": true,
    "research_intensity": "balanced",
    "decision_policy": "autonomous",
    "launch_mode": "standard",
    "custom_profile": "freeform",
    "scope": "baseline_plus_direction",
    "baseline_mode": "existing",
    "resource_policy": "balanced",
    "time_budget_hours": 24,
    "git_strategy": "semantic_head_plus_controlled_integration",
    "runtime_constraints": "One 24 GB GPU. Keep data local.",
    "objectives": [
      "verify the reusable baseline",
      "test one justified sparse-routing direction"
    ],
    "baseline_urls": [],
    "paper_urls": [
      "https://arxiv.org/abs/2401.00001"
    ],
    "entry_state_summary": "",
    "review_summary": "",
    "custom_brief": ""
  }
}
```

### Custom launch: continue existing state

```json
{
  "title": "Continue retrieval project",
  "goal": "Continue the existing retrieval project and decide whether a fresh main run is still needed.",
  "quest_id": "013",
  "requested_baseline_ref": null,
  "startup_contract": {
    "schema_version": 3,
    "user_language": "en",
    "need_research_paper": true,
    "research_intensity": "light",
    "decision_policy": "autonomous",
    "launch_mode": "custom",
    "custom_profile": "continue_existing_state",
    "scope": "baseline_only",
    "baseline_mode": "stop_if_insufficient",
    "resource_policy": "conservative",
    "time_budget_hours": 8,
    "git_strategy": "manual_integration_only",
    "runtime_constraints": "Do not rerun expensive full-corpus indexing unless evidence says the old run is unusable.",
    "objectives": [
      "normalize current evidence",
      "decide whether a new run is actually required"
    ],
    "baseline_urls": [],
    "paper_urls": [],
    "entry_state_summary": "Trusted baseline exists. One main run finished. Draft intro and method already exist.",
    "review_summary": "",
    "custom_brief": "Audit first. Only rerun if current metrics or artifacts are inconsistent."
  }
}
```

### Custom launch: revision / rebuttal

```json
{
  "title": "Camera-ready revision",
  "goal": "Address reviewer requests, add only the missing evidence, and revise the manuscript cleanly.",
  "quest_id": "014",
  "requested_baseline_ref": null,
  "startup_contract": {
    "schema_version": 3,
    "user_language": "en",
    "need_research_paper": true,
    "research_intensity": "balanced",
    "decision_policy": "user_gated",
    "launch_mode": "custom",
    "custom_profile": "revision_rebuttal",
    "review_followup_policy": "audit_only",
    "baseline_execution_policy": "skip_unless_blocking",
    "manuscript_edit_mode": "latex_required",
    "scope": "baseline_plus_direction",
    "baseline_mode": "restore_from_url",
    "resource_policy": "balanced",
    "time_budget_hours": 24,
    "git_strategy": "semantic_head_plus_controlled_integration",
    "runtime_constraints": "Only add experiments that directly answer reviewer concerns.",
    "objectives": [
      "map reviewer comments to concrete actions",
      "run only the necessary supplementary evidence",
      "update the draft and response letter"
    ],
    "baseline_urls": [],
    "paper_urls": [],
    "review_materials": [
      "/absolute/path/to/review-comments.md"
    ],
    "entry_state_summary": "A draft and previous experiment outputs already exist.",
    "review_summary": "Reviewers asked for one stronger ablation, one extra baseline, and a clearer limitation paragraph.",
    "custom_brief": "Treat the current manuscript and review packet as the active contract."
  }
}
```

## Operational implications

- The startup contract is durable project state, not only UI state.
- Prompt building later reads `launch_mode`, `custom_profile`, `review_followup_policy`, `baseline_execution_policy`, `manuscript_edit_mode`, `entry_state_summary`, `review_summary`, `review_materials`, and `custom_brief` again.
- This means `Start Research` shapes not just the first turn, but later routing decisions too.

## Validation checklist

When changing `Start Research`, update together:

- `src/ui/src/lib/startResearch.ts`
- `src/ui/src/components/projects/CreateProjectDialog.tsx`
- `src/prompts/system.md` if runtime interpretation changes
- `src/deepscientist/prompts/builder.py` if prompt routing changes
- this document
- `docs/zh/02_START_RESEARCH_GUIDE.md`
- related tests in `tests/test_prompt_builder.py` and `tests/test_stage_skills.py`
