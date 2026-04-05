# 20 Workspace Modes Guide: Copilot vs Autonomous

This page explains the two normal project-start modes in DeepScientist:

- `Copilot`
- `Autonomous`

Use this when:

- you are about to create a new project
- you are unsure which launch mode to choose
- you want to understand why one project waits for you while another starts moving immediately

If you only want the shortest install-and-launch path, read [00 Quick Start](./00_QUICK_START.md) first.

If you want the exact startup payload and form field contract, read [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md) after this page.

## 1. One-sentence summary

- `Copilot`: quiet start, user-directed, stops after the current requested unit unless you ask it to continue
- `Autonomous`: standard DeepScientist, keeps pushing the quest forward on its own

## 2. Where You Choose This

On the home / projects surface, start a new project and then choose the start style:

- `Copilot Mode`
- `Autonomous Mode`

Current UI wording may appear in two layers:

- outer launcher step: `Start Research` or `Start Experiment`
- mode picker title: `Choose the start style`

After that choice, the two flows diverge.

## 3. Copilot Mode

### 3.1 What it is

Copilot mode is the user-directed workspace.

It is for cases where you want DeepScientist to help actively, but you still want to steer each unit of work:

- inspect a repo
- read a paper
- debug code
- design an experiment
- check a running process
- rewrite a section
- summarize a result

The system should not assume that one request means “run the whole autonomous research loop”.

### 3.2 What happens after creation

After you create a Copilot project:

- the project is created
- the quest stays idle
- the agent waits for your first real instruction

In practical terms:

- there is no immediate autonomous launch
- no baseline / experiment / writing loop starts just because the project exists
- the first substantial action begins when you send the first message

### 3.3 Continuation behavior

Copilot mode is intentionally conservative about continuation.

After the current requested unit is complete, DeepScientist should normally:

- summarize what changed
- preserve context durably
- wait for your next message or `/resume`

This is the right mode when you want:

- tight human control
- short request-scoped help
- less background churn
- clearer handoff points

### 3.4 Good fit

Choose `Copilot` when:

- you want to inspect before launching expensive work
- the task is still ambiguous
- you expect to iterate interactively
- you want DeepScientist to behave more like a strong research IDE partner than a long-running autonomous operator

### 3.5 Bad fit

Avoid `Copilot` when:

- you already know the quest should keep running for hours
- you want detached experiments, monitoring, and follow-up routing without repeated user nudges
- the goal is full quest ownership, not request-by-request collaboration

## 4. Autonomous Mode

### 4.1 What it is

Autonomous mode is the standard DeepScientist path.

It is meant for quests where the system should keep making ordinary route choices on its own and continue until the next real checkpoint is reached.

This is the right mode for:

- baseline establishment
- long experiments
- analysis campaigns
- durable writing / finalize loops
- connector-facing project progress over time

### 4.2 What happens after creation

After you create an Autonomous project:

- the quest is created
- the first turn is launched immediately
- the system begins turning the startup contract into real work

This may mean:

- reading the baseline and references
- checking environment and constraints
- preparing scripts
- selecting the next route
- launching detached `bash_exec` work

### 4.3 Continuation behavior

Autonomous mode has two practical continuation regimes.

#### A. No real long-running external task yet

If no real long-running external task exists yet, DeepScientist should not park.

It should keep using the next turns to:

- prepare the real task
- launch the real task
- or make a durable route decision about what the real next task must be

This is the “active preparation / launch” phase.

#### B. A real long-running external task is already active

Once a real detached task is already running, continuation changes shape.

At that point, DeepScientist should not busy-loop through rapid model turns just to imitate continuous execution.

Instead:

- the real work should remain alive in detached `bash_exec` sessions or the runtime process they launched
- agent turns become lower-frequency monitoring / synthesis passes
- the current default monitoring cadence is roughly every `240` seconds

This is the “background progress monitoring” phase.

### 4.4 Good fit

Choose `Autonomous` when:

- the quest should keep moving on its own
- you expect real long-running experiment or analysis work
- you want DeepScientist to keep routing after milestones
- you want the standard research-operating-system behavior

### 4.5 Bad fit

Avoid `Autonomous` when:

- you only want a quiet project shell first
- you want to inspect the repo manually before any real movement
- you want every next unit to be explicitly user-directed

## 5. The Most Important Practical Difference

The easiest way to remember the split is:

- `Copilot` asks: “What single useful unit should I help with right now?”
- `Autonomous` asks: “What is the next real quest step, and how do I keep the quest moving?”

That difference matters more than the labels themselves.

## 6. How Resume Works

Both modes preserve context durably, but they resume differently.

On later turns, DeepScientist now carries a compact resume spine that can include:

- the latest durable user message
- the latest assistant checkpoint
- the latest run summary
- recent memory cues
- current `bash_exec` state

But the continuation policy still differs:

- `Copilot`: resume only when you speak again or explicitly resume
- `Autonomous`: keep going unless a real blocker or explicit waiting state applies

## 7. Choosing Quickly

Use this fast rule:

1. If you want the project to wait quietly until you tell it what to do, choose `Copilot`.
2. If you want DeepScientist to begin turning the quest contract into real work immediately, choose `Autonomous`.
3. If you are unsure, start with `Copilot`; you can still move into longer-running work once the route is clearer.

## 8. Common Misunderstandings

### “Autonomous means it should always spin rapidly”

No.

Autonomous means the quest should keep moving.

When there is no real long-running task yet, that can mean rapid preparation / launch turns.
When a real long-running task is already active, it should usually mean lower-frequency monitoring, not constant model churn.

### “Copilot means it cannot run experiments”

Also no.

Copilot can still help launch, inspect, analyze, and write.
The difference is that it should not assume long autonomous continuation unless you ask for it.

### “The two modes only change wording”

No.

They affect:

- initial launch behavior
- continuation policy
- when the quest parks
- how much autonomous routing is appropriate

## 9. Related Docs

- [00 Quick Start](./00_QUICK_START.md)
- [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md)
- [12 Guided Workflow Tour](./12_GUIDED_WORKFLOW_TOUR.md)
- [14 Prompt, Skills, and MCP Guide](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md)
