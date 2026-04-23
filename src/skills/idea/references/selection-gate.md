# Selection Gate And Handoff

Use this reference when choosing the final idea and preparing the handoff to `experiment`.

## 1. Value and feasibility screen

Before promotion, score each serious candidate on a compact `1-5` scale:

- importance
- novelty
- feasibility
- verifiability
- paper or report potential
- failure value
- breakthrough or boundary-changing potential

Also check the FINER-style screen explicitly:

- `F`
  - feasible with current data, compute, codebase, and schedule
- `I`
  - interesting enough that the field would care
- `N`
  - novel in a meaningful sense relative to the strongest nearby work
- `E`
  - ethically acceptable and not obviously high-risk
- `R`
  - relevant to an important bottleneck rather than a decorative tweak

If the route scores poorly on both value and feasibility, do not promote it merely because it feels exciting.
If the route is only a small local tweak, require an explicit justification for why a more differentiated route did not survive.

## 2. Lightweight quality gate

Score the final serious candidate on a `0/1/2` scale:

- novelty
  - `0` obvious tweak
  - `1` moderate variant
  - `2` clear non-trivial mechanism change
- falsifiability
  - `0` vague claim
  - `1` partially testable
  - `2` explicit metric, direction, and boundary condition
- feasibility
  - `0` unclear implementation path
  - `1` large refactor risk
  - `2` minimal touchpoints clearly identified
- evidence quality
  - `0` no credible citation
  - `1` weak or indirect support
  - `2` directly relevant papers plus baseline evidence
- constraint fit
  - `0` violates constraints
  - `1` uncertain fit
  - `2` fully compliant with dataset, protocol, and compute limits

If total `< 7/10`, do not promote the idea yet.
Also treat these as hard gates before promotion:

- the literature survey must already durably cover at least `5` and usually `5-10` related and usable papers
- the survey must show both the strongest direct-field overlap and any adjacent-domain mechanisms that could plausibly subsume or outgrow the candidate
- a pre-idea draft or equivalent durable challenge memo must already exist for the serious surviving candidates, especially the likely winner
- that draft must explicitly surface hidden assumptions, local-optimum lock-in risk, strongest rejection case, and strongest outside-family alternative
- the closest-prior-work comparison must explain why the idea is still needed
- the selected route must be classified honestly as breakthrough-seeking, clearly differentiated, or incremental-with-justification; default rejection applies to decorative tweaks
- the final selected-idea draft must be ready to carry standard-format citations for the papers actually used

## 3. Honest novelty / value labels

Use these labels explicitly:

- `novel`: closest prior work does not already make the same mechanism-plus-claim combination, and the route is materially more than a cosmetic delta from the baseline
- `incremental but valuable`: overlap exists, but the new setting, evidence package, or failure-mode resolution is still meaningful
- `not sufficiently differentiated`: closest prior work already dominates the idea

Only the first two are eligible for promotion.
Even then, prefer `novel` when it remains feasible.

## 4. Mechanism and falsification gate

Before a candidate can be promoted, it should make explicit:

- core hypothesis
- mechanism sketch
- strongest falsification experiment

The mechanism sketch can be brief, but it must answer:

- why should this route work at all?
- what part of the current limitation does it change?
- for whom, where, or under what condition should it work or fail?

If the mechanism sketch or strongest falsification experiment is still vague, the route is not yet ready.

## 5. Handoff fields for experiment

The selected idea record should include:

- stable idea id
- `motivation` in SCQA form
- `reasoning` with main hypothesis plus `2-3` competing hypotheses near the top
- `claim` as one falsifiable sentence tied to:
  - `metric_key`
  - expected direction
  - boundary condition
- `theory_and_method`
- `code_level_plan`
- `relation_to_literature`
- `references` or `bibliography` in a standard citation format
- evidence or source pointers

Inside the implementation handoff, also include:

- `metric_key`
- `expected_direction`
- `minimal_experiment`
- `abandon_condition`
- `strongest_alternative_hypothesis`

## 6. Recommended presentation shape

Use a compact Pyramid structure:

- first line: falsifiable claim plus metric focus plus boundary condition
- then `3-6` bullets of reasoning and evidence pointers
- then the minimal validation plan
- then a short `References` or `Bibliography` section that cites the survey-stage papers actually used

## 7. Promotion gate

Do not promote a candidate if any of these remain unclear:

- what exactly is being claimed
- how the claim differs from closest prior work
- what hidden assumption is carrying most of the route
- whether the route only looks best because of incumbent inertia or implementation convenience
- what minimal experiment can refute it
- which code touchpoints are affected
- what evidence package would later defend it in writing
- which `5-10` surveyed papers actually support the motivation, mechanism, and claim boundary
- whether the final idea draft includes proper citation markers plus a standard-format reference list
- why this route deserves promotion over simpler but lower-value tweaks and over more ambitious but still feasible alternatives
