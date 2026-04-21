# Section Rewrite Checklist

Use this checklist when upgrading an existing draft into an oral-quality paper.

## 1. Abstract

Check that the abstract does all of the following in order:

1. problem or deficiency
2. proposed idea
3. why the idea is different or principled
4. the main empirical pattern
5. one or two strongest concrete outcomes
6. calibrated takeaway

Rewrite if the abstract:

- dumps too many numbers without hierarchy
- sounds like a compressed lab note
- lacks a stable one-sentence memory of the paper
- tries to answer every reviewer question before the paper has started
- uses strict-dominance language that the evidence package does not fully support

## 2. Introduction

Check that the introduction:

- states the problem clearly
- explains why current approaches are insufficient
- introduces the paper's core idea in plain language
- gives the reader an intuition anchor early
- clearly identifies the default setting or operating regime the method is meant to improve
- places the paper in the broader method family before narrowing to the exact gap
- makes novelty legible
- ends with clear contributions or roadmap

Rewrite if the introduction:

- jumps to results too quickly
- delays positioning until late sections
- assumes the reader already agrees the method matters
- has no early figure or verbal mechanism anchor for the main idea

## 3. Related Work

Check that related work:

- appears early enough to establish context
- distinguishes the paper from the closest competitors
- separates "similar goal" from "similar mechanism"
- identifies the nearest neighbors, not just the broad method family
- clarifies what is genuinely new versus better framed

Rewrite if related work:

- is only a bibliography dump
- comes too late to help novelty perception
- never defines the paper's place in the literature
- leaves the nearest-neighbor novelty boundary ambiguous

## 4. Method

Check that the method section:

- defines the method precisely
- gives intuition, not only equations
- explains why the method should work
- compares the method conceptually to alternatives
- tells the reader what property to watch for in experiments
- does not consume space that would be more valuable as objection-handling evidence

Rewrite if the method:

- only presents formulas
- uses notation without interpretive guidance
- leaves the main conceptual difference implicit
- never tells the reader how to read the key figure or later results
- repeats defenses that could be compressed to make room for stronger main-text evidence

## 5. Experiments

Check that the experiments section:

- introduces the evaluation setup briefly but clearly
- states the main empirical pattern before drowning in numbers
- breaks the empirical case into explicit reviewer-question subsections when multiple claim clusters are being defended
- uses displays that match the central claim
- separates main results from supporting details
- anticipates obvious objections
- gives each major display one dominant local claim
- lets the table or plot carry most of the raw detail
- gives practical-value or objection-handling evidence main-text space when central to the claim

If the central claim is comparative, also check that:

- one main-text result block still shows named competitors or baseline families
- the visible metrics are sufficient to justify the comparative wording
- the comparison surface has not been collapsed into self-only rows plus prose summary

Rewrite if the experiments:

- read like table narration
- rely too heavily on averages without decomposition
- bury the key message inside long numerical paragraphs
- compress setup, headline win, robustness, and ablation into one continuous flow with no clear subsection jobs
- push interpretive or objection-handling evidence into tiny leftover sentences
- preserve broad comparative claims after removing the benchmark block that would let a reviewer verify them

## 6. Analysis

Check that analysis:

- explains the mechanism behind the empirical pattern
- addresses likely reviewer concerns
- includes at least one targeted interpretive angle
- connects back to the central claim
- contains at least one memorable piece of evidence when the paper can support it
- uses the prose to explain why the pattern appears, not to restate visible numbers
- names the cross-setting trend and the underlying tradeoff or essence of the result

Possible useful analysis forms:

- robustness analysis
- diversity or efficiency analysis
- tuned-baseline analysis
- qualitative examples
- failure cases
- case study

Rewrite if analysis:

- feels like leftover supplementary material
- repeats results without explaining them
- mostly paraphrases what the reader can already see in the figure or table
- cites values correctly but never states what stable pattern the reader should infer
- never changes the reader's understanding of why the method works
- could be deleted without changing how memorable the paper feels

## 7. Figures and Tables

For each important figure or table, ask:

- Why is this display here?
- What exact question does it answer?
- Is the caption enough to read it independently?
- Does the surrounding prose tell the reader what takeaway matters?
- Does the surrounding prose interpret rather than duplicate the display?
- Should this live in the main text or appendix?
- Is it the right display type for this job: intuition, result, tradeoff, or case study?

Move material to appendix if it is:

- complete but not central
- exhaustive rather than explanatory
- useful only for deep verification
- too dense to remain legible in the main text

Make sure the main text has a balanced display program:

- one early intuition or mechanism figure
- one main result display
- one analysis or tradeoff display
- one memorable qualitative or case-study display when available

If the paper is being written section by section, lock this display program in the plan first and then preserve those roles through integration. Do not let later sections silently demote a planned main-text display into a passing prose mention.

## 8. Conclusion

Check that the conclusion:

- restates the main contribution cleanly
- summarizes the evidence at the right level
- makes the implication clear
- avoids overclaiming
- stays inside the strongest evidence zone

Rewrite if the conclusion:

- merely repeats the abstract
- adds new unsupported claims
- lacks limitation or scope awareness when needed

## 9. Limitations and Reproducibility

Check that the paper:

- acknowledges real limitations
- signals what is reproducible now
- points to appendix or code artifacts where appropriate
- describes artifact availability consistently across abstract, main text, appendix, and reproducibility statements

Do not use limitation language performatively. The limitation should calibrate trust, not just check a box.

## 10. Appendix Package

Check that the appendix has explicit jobs such as:

- protocol and evaluation detail
- full result tables
- human evaluation protocol details
- hyperparameter sweeps or ablations
- tuned baselines or sensitivity checks
- extra examples or failure cases
- proofs or formal derivations
- reproducibility detail

If the main text was compressed for pacing, check that the appendix still visibly carries the overflow jobs needed to defend the main claim.

Rewrite if the appendix:

- looks like unstructured leftovers
- contains critical evidence that the main text never signals
- fails to answer the reviewer questions most likely to arise
- has no visible progression from protocol to results to stress tests to qualitative evidence
- behaves like a short method tailnote instead of a reviewer-support package

## 11. Final oral pass

Before considering the rewrite complete, ask:

- Can someone summarize the paper after one read?
- Is the central idea visually and verbally anchored early?
- Does each main-text page or section have a clear dominant job?
- Are the strongest figures and analyses in the main text?
- Does the evidence budget look intentional rather than frugal or overloaded?
- Is there breathing room on major result pages?
- Does the paper feel guided rather than compressed?
- Does it read like a human-curated argument rather than an LLM summary?
- Has the final integration pass removed planning language, self-narrating rhetoric, and other drafting scaffolding?

If not, the draft is not oral-ready yet.
