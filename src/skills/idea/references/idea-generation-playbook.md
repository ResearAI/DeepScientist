# Idea Generation Playbook

Use this reference when the `idea` stage needs a concrete creation flow for producing a new idea slate.

The goal is not a bag of clever mechanisms.
The goal is one clear next research object plus a durable record of what was deferred or rejected.

## 0. Finish a real literature pass before ideation

Do not start serious ideation from taste alone.
Before generating a candidate slate, the current pass should already have:

- a durable survey refresh
- direct-field frontier coverage
- strongest nearby prior-work coverage
- at least one adjacent-domain mechanism pass when the bottleneck may transfer

If this gate is not met, stay in literature work rather than pretending the idea phase has started.

## 1. Start from one limitation card

Write one limitation card before generating ideas:

- observed symptom
- condition where it appears
- why it matters for the target metric or claim
- strongest evidence that this is a real pattern

If the limitation card is weak, do not widen into ideation yet.

## 2. Split the problem into three layers

For the active limitation, separate:

- symptom
- mechanism hypothesis
- consequence

Do not skip this split.
It prevents solution-shopping from becoming the hidden driver.

## 3. Keep competing hypotheses alive

Before selecting mechanisms, record:

- one main hypothesis
- `2-3` competing hypotheses

If there is only one hypothesis, the idea pass is usually too collapsed.

## 4. Name the lever bucket

Choose the primary lever bucket explicitly:

- data
- model
- objective
- optimization or training dynamics
- inference
- evaluation protocol
- infrastructure

If the lever bucket is unclear, the idea is usually still too fuzzy.

## 5. Generate direction families, not micro-variants

Create a bounded slate of direction families.
Default target:

- `6-12` raw ideas in one bounded divergent pass
- collapse to `2-3` serious candidates and at most `5`

Prefer family-level differences over small parameter or implementation variations.
If several candidates are really the same family with minor tweaks, merge them.
Bias toward routes that could materially change the capability boundary, claim boundary, or paper value.
Do not keep an obvious small tweak in the serious slate unless it remains competitive after the literature pass.

For each serious candidate, record:

- limitation targeted
- mechanism family
- why now
- strongest prior-work overlap
- expected evidence burden
- likely falsification path
- why this is more than a cosmetic delta from the baseline or closest prior work

## 6. Select one and ledger the rest

Before formal promotion, write a compact pre-idea draft for each serious surviving candidate.
Use `pre-idea-draft-template.md`.

At the end of the pass, produce three durable buckets:

- selected
- deferred
- rejected

For deferred ideas, write why they remain plausible but are not first.
For rejected ideas, write one-line rejection reasons such as:

- redundant with closer prior work
- too confounded to test cleanly
- weak value if positive
- too broad for current compute or codebase
- lower priority than the selected route
- decorative tweak with weak research value relative to broader surviving routes

## 7. Exit criterion

The pass is complete only when the output contains:

- one selected idea or selected direction family
- one falsifiable claim
- one minimal experiment concept
- one abandonment condition
- deferred and rejected rationale recorded durably
- explicit evidence that the selected route survived literature-based novelty checking rather than only internal brainstorming
- a pre-idea draft or equivalent challenge memo for the serious surviving candidates before final submission

If the result is still a bag of possibilities, stay in `idea`.
