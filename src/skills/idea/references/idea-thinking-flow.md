# Idea Thinking Flow

Use this reference when the `idea` stage needs a more explicit internal reasoning path.

## 1. Start from the limitation, not the method

Do not begin by asking "what module can I add?"
Begin by asking:

- what exactly fails?
- under what condition does it fail?
- why is that failure important for the main metric?
- what evidence suggests this is a real pattern rather than noise?

If the failure is still vague, do not jump to ideation.

## 2. Separate symptom, mechanism, and consequence

For each serious limitation, write three layers:

- symptom: what is observed
- mechanism hypothesis: what might cause it
- consequence: why it hurts the target metric or claim

This prevents solution shopping before understanding the problem.

## 3. Build competing hypotheses early

Do not allow only one explanation.
For each promising limitation, keep:

- one main hypothesis
- `2-3` competing hypotheses

This matters because a good idea is often the one whose experiment can quickly distinguish among hypotheses.

## 4. Translate the problem into a lever bucket

Choose the primary lever bucket explicitly:

- data
- model
- objective
- optimization or training dynamics
- inference
- evaluation protocol
- infrastructure

If you cannot name the lever bucket, the idea is usually still too fuzzy.

## 5. Search literature with a reason

Every paper you read should answer one of these questions:

- has this already been tried?
- has this failure mode already been explained?
- is there a mechanism from another domain that maps onto this problem?
- what is the strongest version of the approach we may be reinventing?

Avoid passive reading.
Read with a candidate claim in mind.

## 6. Convert literature into a mechanism map

After reading, do not keep only summaries.
Extract:

- what the paper changes
- why the change is supposed to help
- what assumptions must hold
- what evidence supports the claim
- what boundary or weakness remains

Then map that mechanism into the current codebase:

- where would it land?
- what components would change?
- what is the smallest faithful version we can test?

## 7. Prefer ideas with fast falsification

A strong idea is not just promising.
It is also cheap enough to disprove.

Ask:

- what is the minimal experiment?
- what result would count as failure?
- what confounder could create a false positive?
- what is the abandonment condition?

If none of these are clear, the idea is not ready.

## 8. Translate to reader value

Before selection, convert the idea into reader-facing value:

- what new knowledge would the reader gain?
- why is this not just another tweak?
- if the result is negative, would that still teach something?
- what table, ablation, or failure case would make the claim believable?

If the answer is weak, the idea may be implementable but not worth prioritizing.

## 9. Use an anti-self-deception check

Before promotion, challenge the idea:

- what is the strongest prior work that makes this look redundant?
- what assumption is most likely wrong?
- what easier baseline tweak could produce the same gain?
- what result would embarrass this theory quickly?

This check is especially important for attractive cross-domain ideas.

Also ask:

- are we staying near the current line only because it is familiar or already partially built?
- what hidden assumption has gone unchallenged in the current frontier?
- what assumption-reversal or outside-family route would break a local-optimum lock if the current framing is wrong?

## 10. End with one clear research object

The selected output should be one clear research object:

- one falsifiable claim
- one code-level plan
- one minimal experiment
- one abandonment rule
- one relation-to-literature summary

If the result is still a bag of possibilities, the idea stage is not done.
