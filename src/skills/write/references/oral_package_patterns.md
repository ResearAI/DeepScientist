# Oral Package Patterns

Use this reference to translate a dense draft into an oral-quality paper package.

The core lesson is simple: oral papers do not just contain stronger claims. They stage evidence in a way that reduces reviewer friction and makes the contribution easy to retell.

## 1. Complete persuasion chain

A compressed draft often jumps from problem statement to winning numbers.

An oral-ready paper usually gives the reader this sequence:

1. context and why the problem matters
2. deficiency in current methods
3. the paper's core idea in plain language
4. an early intuition or mechanism figure
5. the main empirical result
6. targeted analysis explaining why the result is credible
7. appendix material that answers deeper verification questions

If the draft skips multiple steps, the issue is structural, not stylistic.

## 2. Evidence budget is part of the argument

Reviewer trust depends not only on what evidence exists, but on whether the paper looks prepared for obvious follow-up questions.

Strong oral packages usually spend visible budget on:

- a clear main-text result section
- at least one interpretive analysis section
- a practical-value or objection-handling block when the main claim invites that question
- appendix material for full tables, protocols, sweeps, proofs, and extended examples

Weak packages often look too frugal:

- too few figures doing too many jobs
- one page carrying several unrelated claims
- appendix used only for leftover tables

Another common failure is misallocation rather than underspending:

- too much main-text budget on repeated method defense
- too little main-text budget on the objections reviewers are most likely to raise

## 3. Reader onboarding before sharp claims

Dense drafts often assume the reader already accepts the framing.

Oral papers usually do more onboarding:

- define the problem class before the exact gap
- explain why the current family of methods is unsatisfying
- give the idea in plain language before diving into formalism
- use an early figure to make the later math easier to absorb

This is not padding. It is trust-building.

## 4. Display program: each important figure has a job

High-value figure roles:

- `Intuition figure`: appears early and explains why the method might work
- `Main result figure`: establishes the central empirical pattern
- `Interpretive figure`: explains a tradeoff, robustness pattern, or mechanism
- `Case-study figure`: gives a memorable example, failure mode, or qualitative contrast

Weak drafts often use figures only as result summaries. Oral papers use figures as teaching tools and memory anchors.

When the paper is written section by section, decide this display program in the plan before drafting body prose. Do not let later sections discover displays opportunistically.

## 5. Table program: one table, one reviewer question

Tables should map to local claims rather than aggregate everything into one overloaded display.

Good table roles:

- main benchmark summary
- human evaluation summary
- efficiency summary
- diversity or robustness summary

If one table forces the reader to accept several unrelated conclusions at once, split it.

## 6. Displays carry specifics, prose carries explanation

One of the clearest differences between a draft and an oral-ready paper is the division of labor between figures or tables and the surrounding text.

Use the display to carry:

- exact numbers
- full benchmark comparisons
- local traces
- concrete generations or examples

Use the prose to carry:

- the question the display answers
- the dominant pattern the reader should retain
- why that pattern appears
- what scientific or reviewer-facing implication follows

Weak draft behavior:

- repeating several visible numbers in the paragraph
- re-reading the plot in sentence form
- spending prose budget on facts already obvious from the display

Stronger oral behavior:

- briefly anchor one or two numbers when needed
- spend most of the prose on interpretation and mechanism
- let the reader use the display for detail and the prose for understanding

For data analysis specifically, good prose should identify:

- the trend across settings
- the governing tradeoff
- the likely underlying cause
- the true scope of the conclusion

## 7. Separate experiments from analysis

When the paper has enough material, split these functions:

- `Experiments`: establish where the method wins and under what settings
- `Analysis`: explain why the win is credible, what tradeoff it implies, and which objections have been addressed

This split is often the difference between "result dump" and "mature paper."

## 8. Use analysis to answer reviewer objections

Analysis should not just repeat results in prose. It should answer questions such as:

- Is the gain only visible under one summary metric?
- Is the method simply more conservative?
- Does the result survive baseline retuning?
- Does the behavior transfer across models or tasks?
- Is there a concrete example showing the claimed mechanism?

Useful analysis blocks:

- diversity versus accuracy
- efficiency or runtime
- tuned-baseline comparisons
- transfer checks
- qualitative examples
- failure cases
- case studies with mechanism-level interpretation

When possible, analysis paragraphs should read as causal or mechanistic explanations, not as spreadsheet narration.

Weak analysis often fails in a subtler way:

- it cites the right values
- it points at the right figure
- but it never says what stable pattern the reader should infer or what that pattern reveals about the method

## 9. Memorable case studies matter

Aggregate metrics build confidence. Case studies build recall.

A strong case study often includes:

- one concrete prompt or instance
- competing outputs or behaviors
- the exact error or success mode
- a visualization or local statistic explaining the difference

This gives reviewers something they can describe in conversation.

## 10. Page pacing is part of readability

A draft can be technically correct and still feel rushed because every page is overloaded.

Audit pacing by asking:

- Does this page have one dominant job?
- Is the key display large enough to read comfortably?
- Are several local claims competing for the same visual space?
- Would moving one result block to appendix improve the argument?

Oral-quality papers leave breathing room for important evidence.

## 11. Appendix is part of the package

The appendix should feel designed, not appended.

Common appendix roles:

- protocol and evaluation details
- full benchmark tables
- human evaluation protocol details
- additional ablations or sweeps
- failure cases and extra examples
- proofs or synthetic illustrations
- implementation and reproducibility details

Main text should point to the appendix deliberately, not apologetically.

## 12. Fast audit: draft signal to oral fix

- `Overloaded abstract` -> restore hierarchy: problem, idea, main pattern, one calibrated takeaway
- `Introduction jumps to wins` -> add broader framing and early intuition anchor
- `Method is correct but cold` -> add conceptual contrast and interpretation
- `Results read like spreadsheets` -> separate pattern, key numbers, interpretation
- `Analysis paraphrases the display` -> keep only the few anchoring facts needed, then explain why the pattern appears
- `Analysis lists numbers but not the trend` -> name the stable pattern, the tradeoff, and the likely mechanism
- `Analysis feels optional` -> promote at least one interpretive block into the main text
- `Figures summarize but do not teach` -> add or redesign an intuition figure and a case-study figure
- `Main text is crowded` -> move exhaustive material to appendix
- `Method defense is too thick` -> compress repeated formal defense and spend that budget on objection handling
- `Appendix is just tables` -> organize it around protocol, full results, stress tests, examples, failure cases, and reproducibility
- `Claim wording outruns the data` -> narrow to the strongest evidence zone
- `Artifact availability is inconsistent` -> make abstract, main text, reproducibility, and appendix say the same thing

## 13. What to preserve from the stronger version

When comparing two versions of a paper, preserve changes that improve:

- onboarding
- display roles
- prose-display division of labor
- analysis depth
- trend extraction and mechanism explanation
- page pacing
- reviewer concern coverage
- appendix intentionality

Do not preserve changes only because they add length. Preserve them because they make the paper easier to trust, remember, and defend.

## 14. Sectioned generation pattern

When the manuscript is generated in sections instead of one pass, a strong default order is:

1. plan
2. introduction
3. related work
4. method
5. experiments
6. analysis
7. appendix
8. limitations
9. conclusion
10. abstract
11. integration

This order works because:

- early sections establish the story and novelty boundary
- experiments and analysis are separated before the abstract is finalized
- appendix support exists before scope and limitation language is frozen
- the integration pass can repair cross-section drift without reopening the entire writing problem
