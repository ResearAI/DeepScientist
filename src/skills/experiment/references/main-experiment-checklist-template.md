# Main Experiment Checklist Template

Update this while planning, modifying code, running pilots, monitoring the full run, and validating the result.

## Identity

- parent_map_node:
- loop_id:
- run id:
- idea id:
- stage:

## In Progress

- [ ] one concrete experiment frontier item is actively in progress

## Next

- [ ] next code / run / validation step is explicit
- [ ] next map transition is explicit
- [ ] next reporting checkpoint is explicit

## Later

- [ ] deferred but still relevant items live here

## Blocked

- [ ] blockers or unresolved dependencies are recorded here

## Planning

- [ ] selected idea summarized in `1-2` sentences
- [ ] baseline and comparability contract confirmed
- [ ] code touchpoints listed
- [ ] smoke plan written
- [ ] full run plan written
- [ ] fallback options written

## Implementation

- [ ] intended files modified
- [ ] unrelated changes avoided or justified
- [ ] risky logic guarded or sanity-checked
- [ ] plan updated if the implementation route changed

## Pilot / Smoke

- [ ] smoke command executed
- [ ] outputs look valid
- [ ] metrics / logs are interpretable
- [ ] comparability still holds

## Main Run

- [ ] real run launched
- [ ] monitoring cadence started
- [ ] health signals confirmed
- [ ] major runtime deviations reflected in `PLAN.md`

## Validation

- [ ] outputs exist
- [ ] metrics are complete
- [ ] baseline delta is comparable
- [ ] main claim is classified as supported / refuted / inconclusive
- [ ] result recorded durably

## Done

- [ ] completed frontier items are moved here instead of staying mixed into `Next`

## Closeout

- [ ] main experiment summarized in `1-2` sentences
- [ ] next action is explicit
