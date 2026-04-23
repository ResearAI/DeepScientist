# Literature Survey Report Template

Use this template at the start of a fresh `idea` pass and whenever an existing idea needs deeper refinement.

The purpose is to make related-work coverage durable, searchable, and reusable so future idea turns do not have to repeat the same broad search.

## 1. Survey header

- quest id
- date
- baseline id or method name
- task / dataset / metric contract
- current investigation target
- survey minimum gate status
  - related and usable papers found so far
  - how many are direct task-modeling papers
  - how many are adjacent but translatable papers
  - how many are cross-domain mechanism papers
  - whether the hard floor of at least `5` and usually `5-10` usable papers has been satisfied
- why the survey is being run now
  - first idea build
  - idea refinement
  - novelty check after failure
  - update for newer papers

## 2. Memory consulted before external search

List the durable knowledge you checked first:

- quest `papers`
- quest `ideas`
- quest `decisions`
- quest `knowledge`
- global `papers`
- global `knowledge`
- global `templates`

Record:

- which cards were read
- what they already covered well
- what gaps remained

## 3. Search ledger

For each meaningful search pass, record:

| query | source | reason | new papers | known papers reconfirmed | remaining gap |
| --- | --- | --- | --- | --- | --- |
| baseline + limitation keyword | arXiv | find direct extensions | 2 | 1 | need same-dataset comparisons |

Recommended source labels:

- `memory`
- `arXiv`
- `citation`
- `open-web`
- `repo-search`

## 4. Paper buckets

Split the papers into:

- core papers
- closest competitors
- adjacent inspirations
- cross-domain transferable mechanisms
- watchlist / uncertain relevance

For each paper, include:

- title
- year
- identifier or arXiv id
- URL
- standard citation string or citation key
- short mechanism summary
- task / dataset / metric overlap
- what it means for the current idea
- whether it is directly usable for the current idea, only a novelty check, or only an adjacent inspiration
- status:
  - `new_this_pass`
  - `known_before`
  - `watchlist`

## 5. Closest-prior-work table

Recommended columns:

- identifier
- year
- standard citation key
- mechanism overlap
- task overlap
- dataset overlap
- metric overlap
- strongest supported claim
- weakness or unresolved edge
- implication for our candidate

## 6. Novelty and value verdict

For each serious candidate idea, state:

- closest prior art
- overlap with our mechanism
- what still appears missing
- verdict:
  - `novel`
  - `incremental but valuable`
  - `not sufficiently differentiated`

If the verdict is not strong enough, say so explicitly.

## 7. Codebase translation note

Connect the literature back to the repo:

- relevant files or modules
- required implementation levers
- likely feasibility blockers
- cheapest falsification path

## 8. Memory writes to create or refresh

List the durable follow-up writes:

- quest `papers` cards to create or update
- quest `knowledge` cards to distill
- global cards worth promoting later, if any

At least one survey-derived memory card should be written before the idea stage exits.

## 9. Idea implications

Close with:

- the best surviving candidate ideas
- the rejected ideas and why
- what still needs more search before selection
- whether the remaining serious ideas are breakthrough-seeking, clearly differentiated, or merely incremental
- whether the stage is ready for `idea` selection, more `scout`, or a user decision

## 10. Citation-ready shortlist for the selected idea

Before the final idea draft is written, extract the papers that materially support the winning idea.

For each such paper, include:

- standard citation entry in the format you plan to use later
- what part of the idea it supports:
  - problem motivation
  - closest prior work
  - mechanism inspiration
  - claim boundary
- whether it must appear inline in the idea draft or only in the references section

The final selected idea should not be written or submitted until this shortlist is ready.
