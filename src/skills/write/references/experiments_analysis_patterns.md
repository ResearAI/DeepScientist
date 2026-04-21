# Experiments And Analysis Patterns

Use this reference when strengthening the `experiments` and `analysis` sections of an oral-style ML paper.

The main objective is not to report more numbers. It is to make the empirical package reviewer-auditable, interpretable, and memorable.

## 1. Separate empirical proof from interpretation

When the staged package is rich enough, keep `experiments` and `analysis` as distinct jobs.

- `Experiments` proves where the method works, against whom, and under what settings.
- `Analysis` explains why the pattern is credible, what tradeoff it reveals, and where the claim boundary lies.

Do not let `analysis` become a short epilogue after the main result dump.

## 2. Experiments should answer explicit reviewer questions

A strong experiments section usually reads as a sequence of local questions rather than a flat list of tables.

Typical reviewer-facing questions:

- Does the method beat named baselines on the main task?
- Does the gain persist across datasets, scales, or settings?
- Does the gain survive stronger baselines, retuning, or ablations?
- What practical cost, latency, or data tradeoff accompanies the gain?

Each question should have one dominant display or authored compact table. Do not force one omnibus table to answer all of them.

## 3. Preserve an inspectable main-text comparison surface

Reviewers should be able to audit the main claim from the main text.

Keep in the main paper:

- the principal benchmark comparison
- the main baseline families or evaluation regimes
- at least one non-headline support block when the central claim needs visible transfer, robustness, or objection-handling evidence

Avoid these failure modes:

- prose claims that mention wins without a visible comparison surface
- averaged or compressed tables that hide which baselines matter
- moving all boundary-setting evidence into appendix overflow

## 4. Give different displays different jobs

When several staged artifacts are available, assign complementary roles instead of redundant summary roles.

Useful experiments display jobs:

- headline benchmark block
- robustness or transfer block
- ablation or intervention block
- practical-cost or efficiency block
- human-evaluation or qualitative support block

Useful analysis display jobs:

- mechanism or credibility check
- tradeoff or sensitivity check
- failure-boundary or scope-limit check
- category breakdown or taxonomy check

If two figures or tables support different reviewer concerns, preserve that distinction in the manuscript.

## 5. Analysis needs a visible main-text evidence floor

The main text should not outsource the whole analysis layer to appendix citations.

When the staged package supports it, keep at least:

- one mechanism or credibility display
- one tradeoff, sensitivity, robustness, or quality-support display

These can be compact, but they should remain inspectable in the main paper when they answer different reviewer concerns.

## 6. Analysis should name the stable pattern

Good analysis prose does more than narrate a chart.

It should answer:

- what trend remains stable across settings
- what tradeoff is being managed
- what mechanism most plausibly explains the pattern
- what scope limit or failure boundary the evidence implies

Weak analysis often cites correct numbers but never states the governing pattern.

## 7. Use labeled analysis blocks

When the gold or staged package has multiple interpretive jobs, make them visible through subsection heads, bold mini-heads, or strongly signposted blocks.

Common analysis block types:

- metric or proxy validation
- mechanism explanation
- diversity-versus-accuracy or quality-versus-quantity tradeoff
- robustness across scales or model families
- failure taxonomy or error-boundary analysis

Do not compress these jobs into one generic "Further analysis" paragraph.

## 8. Keep appendix bridges concrete

Main text should hand off overflow support deliberately.

Good bridge sentences name what lives in the appendix:

- extra benchmark slices
- protocol details
- broader sweeps
- qualitative examples
- human-evaluation annotation details
- additional failure cases

Bad bridge sentences just say "see appendix for more results."

## 9. Fast audit for experiments and analysis

Before finalizing these sections, check:

- Can a reviewer inspect the main comparative claim directly in main text?
- Is there a separate non-headline block for robustness, transfer, ablation, or objection handling when the claim needs it?
- Does analysis contain more than one visible reviewer-facing check?
- Does analysis name the stable trend or mechanism instead of re-reading numbers?
- Does the main text still carry visible analysis evidence, or did it drift almost entirely into appendix referrals?

If any answer is no, the section package is probably too thin for oral quality.
