# Main Experiment Plan Template

Use this before substantial code edits or the real main run.
Treat it as the implementation-and-execution plan for the selected idea, not just a metadata form.

## 1. Map Link

- parent_map_node:
- loop_id:
- node_objective:
- node_deliverable:
- success_condition:
- abandonment_condition:
- next_on_success:
- next_on_failure:

## 2. Objective

- run id:
- selected idea in `1-2` sentences:
- user's core requirements:
- non-negotiable user constraints:
- research question:
- null hypothesis:
- alternative hypothesis:

## 3. Current Node Tasks

- [ ] sync the experiment node status and current incumbent context
- [ ] confirm comparability and code translation plan
- [ ] run the smoke or pilot path
- [ ] launch or validate the main run
- [ ] classify the result and update the next map edge

## 4. Baseline And Comparability

- baseline id:
- baseline variant:
- dataset / split:
- primary metric:
- required metric keys:
- comparability risks:

## 5. Code Translation Plan

Map the idea into concrete code changes.

| Path | Current role | Planned change | Why this is needed | Risk |
|---|---|---|---|---|
| | | | | |

## 6. Execution Design

- minimal experiment:
- smoke / pilot plan:
- full run plan:
- expected outputs:
- stop condition:
- abandonment condition:
- strongest alternative hypothesis:

## 7. Runtime Strategy

- command for smoke:
- command for main run:
- expected runtime / budget:
- log / artifact locations:
- safe efficiency levers to use first:
- how existing tooling will be used efficiently:

Monitoring and sleep plan:

- wait cadence:
  - `60s`
  - `120s`
  - `300s`
  - `600s`
  - `1800s`
- health signals that justify continuing to monitor:
- conditions that trigger kill / relaunch:

## 8. Fallbacks And Recovery

- if the intended model / endpoint / download path fails:
- if hardware or memory is tighter than expected:
- if the code path is wrong after smoke:
- if the first full run becomes non-comparable:

## 9. Checklist Link

- checklist path:
- next unchecked item:

## 10. Revision Log

| Time | What changed | Why it changed | Impact on comparability or runtime |
|---|---|---|---|
| | | | |
