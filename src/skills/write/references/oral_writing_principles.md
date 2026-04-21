# Oral Writing Principles

This reference distills the difference between a strong draft and a top-conference oral paper.

## 1. Optimize for reviewer cognition

A draft often tries to say everything. An oral paper tries to make the reader:

- understand the core idea quickly
- remember the main claim
- trust the evidence
- repeat the paper's contribution accurately

Write for cognition, not for compression.

## 2. Build a story spine before polishing prose

Before line editing, define:

- the problem
- the deficiency in current methods
- the core idea
- why the idea is principled
- the main empirical pattern
- the key mechanism or explanation
- the exact scope of the claim

If this spine is weak, local prose polish will not fix the paper.

## 3. Section jobs

Each main section should have one dominant function:

- `Abstract`: compress the whole paper into one coherent impression
- `Introduction`: motivate, frame the gap, preview the contribution, and make the reader care
- `Related Work`: position the paper early enough that novelty is legible
- `Method`: define and defend the method
- `Experiments`: establish the main empirical pattern
- `Analysis`: explain why the pattern is credible and important
- `Conclusion`: restate contribution, scope, and implication without overselling

When a section tries to do too many jobs, it usually becomes dense and forgettable.

## 4. Paragraph jobs

A paragraph should usually do one main thing:

- set up a problem
- state a pattern
- interpret a figure or table
- answer an objection
- explain a mechanism

If a paragraph simultaneously motivates, reports numbers, argues novelty, and calibrates claims, split it.

## 5. Signposting is mandatory

Use explicit transitions when changing jobs. Good signals include:

- `To address this deficiency`
- `The key question is`
- `This result matters because`
- `A reasonable concern is`
- `This plot shows`
- `This contrast illustrates`
- `Taken together`

These phrases are not fluff. They reduce the reader's organizational burden.

## 6. Method sections must teach, not only define

A weak method section gives equations and maybe a theorem.

A strong method section also provides:

- intuition
- conceptual contrast with alternatives
- why the method should work
- what property makes it different
- what interpretation the reader should keep in mind while reading results

The goal is not just mathematical correctness. The goal is reader uptake.

## 7. Results are not a spreadsheet

Do not write results as a raw sequence of numbers.

Use a three-layer structure:

1. state the main pattern
2. anchor the pattern with key numbers
3. interpret why those numbers matter

When possible, separate:

- main empirical win
- robustness evidence
- objection-handling evidence
- mechanism evidence

When writing data analysis, do not stop at "what value is larger." Push to:

- what trend persists across settings
- what tradeoff the method is managing
- what mechanism best explains the pattern
- what narrower claim is actually justified by that pattern

## 8. Figures and tables need surrounding prose

Every important display should be introduced and closed.

Before the display, say:

- why it appears here
- what question it answers

After the display, say:

- the main takeaway
- what the reader should remember

Do not force the figure or table to do all the explanatory work alone.

Do not waste the surrounding prose by re-reading the display line by line. The display should carry the detailed values; the prose should carry the interpretation.

## 9. Use figures as narrative anchors

Top papers use figures for different jobs:

- an early intuition figure
- a main result figure
- a mechanism or case-study figure

The most important figure often appears early, before the full technical development, to give the reader a visual handle on the idea.

## 10. Keep the main text legible

Main text is for:

- the story
- the key evidence
- the interpretation

Appendix is for:

- full result tables
- extra ablations
- detailed proofs
- extended examples
- extra implementation details

Do not let the main text become a storage container for every supporting number.

## 11. Calibrate claims structurally

Strong claim calibration is not just one sentence saying "we do not claim X."

Claim calibration should appear in:

- the chosen wording
- the selected comparisons
- the scope of conclusions
- the discussion of limitations
- the organization of evidence

If the evidence only supports robustness under certain settings, say that clearly and build the section around that scope.

Prefer wording that stays inside the strongest evidence zone:

- `strong default`
- `wins or ties most settings`
- `more robust under sweep`

Be careful with wording that implies strict dominance unless the evidence package really supports it.

## 12. Remove LLM-draft signals

Common LLM-like writing signals:

- excessive density
- summary-first writing with weak staging
- low paragraph differentiation
- late positioning
- tables carrying too much of the paper
- result sections that feel like narration of a spreadsheet
- analysis that feels appended rather than integral

Replace them with:

- staged narrative
- stronger signposting
- section discipline
- figure/table role clarity
- mechanism-aware analysis

## 13. The target feeling

The final paper should feel like:

- the authors know exactly what the contribution is
- the evidence is in the right order
- the reader is being guided, not tested
- the paper is easy to summarize after one read

That is what often separates a strong draft from an oral-quality paper.

## 14. Evidence budget signals preparedness

Oral papers usually look prepared for reviewer follow-up.

That feeling comes from visible evidence allocation:

- enough main-text space for the central claim
- enough analysis to explain the claim
- enough appendix support to answer deeper questions

If every display is overloaded or every concern is answered in one sentence, the paper will still feel underdeveloped even if the raw evidence exists.

Budget allocation can also fail when too much space is spent defending the method repeatedly while too little space is spent answering the objections reviewers are actually likely to raise.

## 15. Separate experiments from analysis when the paper can support it

If the draft has enough material, use different sections for different jobs:

- `Experiments` to establish the pattern
- `Analysis` to explain, defend, and interpret the pattern

This often improves pacing and makes the paper feel more deliberate.

## 16. Memorable evidence beats only aggregate evidence

Aggregate tables and plots establish scale.

But oral papers also benefit from at least one memorable, concrete piece of evidence:

- a case study
- a failure mode
- a qualitative contrast
- a mechanism-level visualization

This is what makes the paper easy to discuss after one reading.

## 17. Main-text prose is for explanation, not duplication

Main-text prose is scarce and expensive.

Use it to answer:

- why this result appears
- why this tradeoff matters
- why a reviewer should trust the interpretation
- what mechanism connects the display to the claim

For data analysis, the prose should surface the trend and essence of the result, not just the surface comparison.

Do not spend it on long numeric narration when the table or figure already shows the facts.

## 18. Page pacing matters

Even a correct paper can feel draft-like if every page is trying to win too many arguments.

Prefer:

- one dominant job per page or subsection
- readable figure sizes
- visible transitions between result blocks
- moving exhaustive material to appendix instead of shrinking everything

Compression is not the same thing as sophistication.

## 19. Appendix should feel designed

For oral-level work, appendix is part of the persuasive system.

Use it to house:

- full result matrices
- protocol details
- tuned baselines and sensitivity checks
- failure cases
- extra ablations
- extended examples
- proofs and formal details

The appendix should make the paper look more complete, not more improvised.

## 20. Artifact status must be globally consistent

If the abstract says code is available, the reproducibility section, appendix, and any artifact note must say the same thing.

Small inconsistencies about release status, anonymous repos, or availability dates create avoidable trust friction.
