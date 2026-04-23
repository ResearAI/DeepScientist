# Related-Work Playbook

Use this reference during the `idea` stage when you need a deeper and more explicit process for literature scouting, novelty checking, and value judgment.

For a broader history-aware search before final narrowing, also read `research-history-playbook.md`.

## 0. Broad search policy

Search should be broad enough to map the field and its history, not only to confirm the first attractive candidate.
It should also be broad enough to surface cross-domain mechanisms that may transfer into the current task, evaluation setup, or systems bottleneck.

If DeepXiv is available under the runtime contract, prefer it for broad paper-centric discovery, citation expansion, and shortlist triage.
If DeepXiv is unavailable, use search engines directly and keep the same breadth target:

- recent papers
- foundational papers
- turning-point papers
- citation chaining
- adjacent-domain mechanism search

## 1. Search objective

The goal is not to collect random citations.
The goal is to answer:

- what has already been tried?
- what is the strongest nearby prior work?
- what remains unresolved or weakly defended?
- does the candidate still have novelty or at least research value?
- are there adjacent-domain methods that solve a structurally similar limitation and could be translated here?

## 2. Query families

Do not rely on one query.
Use several query families and refine them iteratively:

- task + dataset + metric
- task + failure mode or bottleneck
- baseline method name + limitation keyword
- proposed mechanism + task
- proposed mechanism + dataset
- adjacent-domain principle + task
- strongest recent paper title or method name + "extension", "robustness", "ablation", or "failure"

## 2.1 Source order and de-dup protocol

Before opening a fresh broad search, check durable memory first:

1. recent quest `papers`, `ideas`, and `knowledge`
2. recent global `papers`, `knowledge`, and `templates`
3. `memory.search(...)` with the baseline name, task, dataset, mechanism, and current idea labels

Then search externally for the missing neighborhood:

1. arXiv for direct paper discovery
2. citation trails for nearest-neighbor expansion
3. broader web or repo search for implementation overlap and follow-up work
4. adjacent-domain mechanism search when the direct neighborhood looks saturated or overly incremental

The goal is not to search the same cluster from zero every time.
The goal is to reuse what the quest already knows and only spend new search budget on gaps, recency, or unresolved overlap.

## 2.2 History-aware pass

Before claiming novelty, identify:

- seminal papers
- paradigm-shift papers
- current mainstream or SOTA papers

Then use both:

- backward citation chaining
- forward citation chaining

to reconstruct the problem lineage rather than only the current keyword cluster.

## 2.3 Cross-domain translation pass

Before you conclude that the best route is a small local tweak, search at least one adjacent domain that faces a structurally similar bottleneck.

Useful prompts:

- same failure mode in a different task family
- same mechanism used under a different evaluator or deployment constraint
- same resource or infrastructure bottleneck solved in another systems or modeling setting
- a theory, optimization, or measurement idea that may be portable even if the task is different

For each promising adjacent paper, record:

- why the bottleneck is structurally similar
- what part of the mechanism may transfer
- what part probably does not transfer directly
- whether the translation would still be non-trivial and worth testing here

## 3. Coverage targets

Try to cover these buckets before final selection:

- seminal papers that define the line
- strongest recent direct competitors
- nearest mechanism-level neighbors
- papers focused on the same failure mode
- papers with the same task but different mechanism families
- adjacent-domain papers whose mechanism, objective, or analysis logic can plausibly transfer into the current task

For a normal selected-idea decision, the survey should durably cover at least `5` and usually `5-10` related and usable papers.
Prefer direct task-modeling papers first; if that pool is truly small, fill the rest with the closest adjacent and translatable work instead of pretending the literature is empty.
Do not stop at the direct field if it only yields small variations of the same idea family.
Run at least one deliberate cross-domain pass whenever the bottleneck might be shared with another domain.

If the area is active, recent work matters a lot.
If the area is stable, seminal work may matter more than recency.

## 4. Reading order

For each promising paper, use a layered read:

1. abstract, introduction, conclusion
2. figures, tables, and headline claims
3. method overview
4. experiment section for dataset / metric overlap
5. ablations, limitations, or failure cases

Deep-read only the papers that materially affect the novelty or selection verdict.

## 5. Comparison table

Build a closest-prior-work table.
Recommended columns:

- identifier
- year
- task overlap
- dataset overlap
- metric overlap
- mechanism overlap
- main claim
- evidence strength
- weakness or unresolved edge
- implication for our candidate

Before stopping, also leave behind a literature survey report.
Prefer the structure in `literature-survey-template.md`.

For harder cases, also keep a lineage-style table with:

- research problem
- core assumption or mechanism
- method and data
- main conclusion
- explicit limitation
- implicit limitation you detect

## 6. Novelty triage logic

Ask these questions in order:

1. Did prior work already use essentially the same mechanism for the same task?
2. If yes, is our claim still different because of boundary condition, evidence package, or failure-mode resolution?
3. If not, is our direction still only an obvious combination of known ingredients?
4. If the idea is incremental, is the increment still important enough to justify experiments?

Possible verdicts:

- `novel`
- `incremental but valuable`
- `not sufficiently differentiated`

Default preference:

- first look for a route that is `novel` and still executable
- accept `incremental but valuable` only when the value is concrete and larger routes were honestly ruled out

## 7. Research-value checks

Even if novelty is limited, a direction may still be worth doing when it offers:

- stronger evidence on a disputed claim
- a valuable transfer to a new but important setting
- resolution of a known failure mode
- a negative result that closes off a tempting but weak path
- reusable infrastructure or methodology

If none of these apply, the candidate is usually not worth promoting.

## 8. Common failure patterns

Watch for these traps:

- only reading one or two papers
- repeating the same broad search without checking memory first
- comparing to weak baselines instead of the strongest nearby work
- declaring novelty from implementation detail rather than research claim
- mistaking recency for relevance
- importing a concept from another domain without proving the translation makes sense here
- failing to look outside the immediate field and therefore rediscovering a nearby but more ambitious route too late
- treating a paper title match as evidence without checking dataset and metric overlap
- reading only the last few years and mistaking recency for centrality
- skipping citation chaining and therefore missing the evolution of the question itself

## 9. Exit condition

The related-work search is good enough to stop when:

- the strongest obvious nearby papers are mapped
- at least one explicit cross-domain or adjacent-domain translation pass has been completed when the bottleneck plausibly allows it
- the closest-prior-work table is complete enough to compare seriously
- each top candidate has an explicit novelty or value verdict
- the usable-paper floor for the selected idea has been satisfied or the shortage is explicitly documented
- the remaining uncertainty is recorded rather than hidden
