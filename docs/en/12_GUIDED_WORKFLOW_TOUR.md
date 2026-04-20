# 12 Guided Workflow Tour: From Landing Page to Real Workspace

This guide is the shortest path to understanding how DeepScientist is actually used after installation.

Use it when:

- you already launched DeepScientist once
- you can open the home page
- you want a concrete walkthrough of what to click, what to fill, and what each surface is for

If you still have not launched DeepScientist yet, start with [00 Quick Start](./00_QUICK_START.md).

If you want the exact payload and field contract behind `Start Research`, then read [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md) after this page.

## 1. First, choose the right mode

There are two normal ways to use the product:

1. real project mode
2. guided tutorial mode

Real project mode creates a real local quest repository and starts real work.

Guided tutorial mode uses the same project-page layout, but the project contents are staged for learning. It is useful when you want to practice the interface before spending real time, compute, or connector resources.

If your goal is real work, use real project mode.

If your goal is to understand the interface safely, replay the tutorial first.

## 2. Start from the home page

The home page is not a chat box. It is the launch surface for a research workspace.

The two primary entry points are:

- `Start Research`
- `Open Project`

Use `Start Research` when you want to begin a new quest.

Use `Open Project` when the quest already exists and you want to continue it.

For a first run, click `Start Research`.

If you only want one practical rule:

- click `Start Research` when you already know what project you want to start
- click `BenchStore` when you want the system to help you choose a benchmark first
- click `Settings` when you are not starting a project yet and only want to configure the system

## 3. Understand what the dialog is doing

The `Start Research` dialog has two jobs:

- the left side defines the project contract
- the right side shows the kickoff prompt that will seed the workspace

This means you should not treat the dialog as a casual form.

You are deciding:

- what problem the quest should solve
- what evidence or references already exist
- how autonomous the first round should be
- whether any external connector should receive progress updates

If the right-side generated prompt looks wrong, stop and fix the left side before you create the project.

## 4. Fill the dialog step by step

### 4.1 Project title

Use a short human-facing title.

Good pattern:

- task name
- benchmark or repository name
- the main research direction

Example:

`Mandela-Effect Reproduction and Truth-Preserving Collaboration`

Use the title so future-you can recognize the quest quickly in the project list.

### 4.2 Project ID

Usually leave this blank.

Only fill it manually when you need a specific stable identifier such as:

- a tutorial run
- a reproduced paper case
- a team convention

If you do not need that, let the runtime assign the next sequential quest id.

### 4.3 Primary research request

This is the most important field in the dialog.

Write:

- the scientific goal
- the success condition
- the evidence requirement
- the most important boundary or evaluation rule

Bad input:

- vague brainstorming
- implementation-only instructions
- a prompt that never says what must be verified

Good pattern:

1. what to reproduce or investigate
2. what question should be answered
3. what must stay aligned with prior work
4. what kind of improvement is allowed

### 4.4 Baseline links and reference papers

Use these fields to reduce ambiguity before the first round starts.

Put repositories or absolute local file/folder paths in `Baseline links` when:

- the quest should restore a known repo
- the baseline must come from a specific official implementation

Put papers, manuscript paths, or important external references in `Paper / reference sources` when:

- the task is defined by a paper
- the expected protocol comes from prior work
- the system should read a known source first

If you already know the baseline and paper, do not hide them in the main request. Put them in the dedicated fields.

These reference fields are not web-only.
You can use network links, absolute local file paths, or absolute local folder paths.

### 4.5 Reusable baseline

Use this only when you already imported a trusted reusable baseline into the registry.

If this field is selected:

- the first round starts from an attached baseline instead of restoring from raw URLs
- the contract becomes more grounded immediately

If you are doing the task for the first time, leaving it empty is normal.

### 4.6 Connector delivery

Connector delivery is optional.

Keep it `Local only` when:

- this is your first run
- you want the simplest setup
- you do not need progress outside the web workspace

Choose one connector target only when:

- you want milestone delivery outside the browser
- you already configured that connector correctly

DeepScientist currently keeps one bound external connector target per quest.

### 4.7 Research paper, intensity, decision mode, and launch mode

These fields change the shape of the first round.

Use these defaults if you are unsure:

- `Research paper`: `On`
- `Research intensity`: `Balanced`
- `Decision mode`: `Autonomous`
- `Launch mode`: `Standard`

Why these defaults are usually correct:

- `Balanced` is strong enough to do real work without overcommitting the first round
- `Autonomous` avoids unnecessary blocking
- `Standard` keeps the workflow on the ordinary path
- `Research paper = On` keeps analysis and writing in scope

If you switch `Launch mode` to `Custom`, choose the custom task type explicitly:

- `Continue existing state`
  - for reuse-first work on an existing quest state
- `Review`
  - for an independent skeptical audit of a substantial draft or paper package
- `Rebuttal / revision`
  - for reviewer-driven work where comments must be mapped into experiments, manuscript deltas, and a response letter
- `Other / freeform`
  - for everything else that does not fit the standard custom types

If you choose `Review`, also decide:

- whether the system should stop after the audit or continue automatically into follow-up experiments and manuscript updates
- whether manuscript-facing output should be ordinary copy-ready text or LaTeX-ready text

### 4.8 Runtime constraints

Use this field for hard rules, not wishes.

Good things to put here:

- which model or inference endpoint must be used
- whether retries are required
- whether evaluation must stay aligned with a baseline
- whether the system must record failure honestly
- hardware or runtime boundaries

Bad things to put here:

- generic goals already written in the main request
- long literature summaries
- content that belongs in references instead

### 4.9 Goals

Use this field for concrete milestones.

Good goals are:

- specific
- verifiable
- useful for later review

Example shape:

1. restore the official baseline
2. verify key metrics
3. propose one justified direction
4. produce evidence strong enough for writing or further analysis

### 4.10 Review the generated prompt

Before clicking `Create project`, read the generated kickoff prompt on the right.

Check for:

- wrong scope
- missing baseline information
- missing runtime constraints
- incorrect connector choice
- a tone that no longer matches the real task

This is the cheapest correction point in the whole workflow.

If you are unsure what the shortest real-project path looks like, it is:

1. `Start Research`
2. `Autonomous`
3. fill `Project title`
4. fill `Primary research request`
5. review the right-side prompt
6. click `Create project`

## 5. Click Create project

In real project mode, this creates a real local quest and opens its workspace.

In guided tutorial mode, it opens a staged demo quest that uses the same project-page layout for training.

After you click create, the most important mindset shift is:

- the task is no longer a text idea
- it is now a durable workspace with files, graph state, memory, and execution history

## 6. Learn the workspace in the right order

A good first order is:

1. top bar
2. explorer
3. one real file
4. canvas
5. details
6. memory
7. copilot / studio

### 6.1 Top bar

The top bar is the global control strip.

Use it to understand:

- which quest you are in
- whether you are on the expected branch
- how to jump back, replay tutorial flow, or navigate globally

### 6.2 Explorer

Explorer is the file-first view of the quest.

Use it when you want to answer:

- what durable files exist now
- whether the quest has produced anything reusable
- where notes, plans, reports, or artifacts actually live

Do not treat the graph as the only truth. The file tree is one of the most important evidence surfaces.

### 6.3 ArXiv and Files tabs

These two tabs serve different jobs:

- `ArXiv` is the literature shelf
- `Files` is the working tree

In normal work you should switch between them repeatedly.

Read a paper in one view.

Open plans, experiment files, and notes in the other.

### 6.4 Open a real file

Once you see a useful file in Explorer, click it.

This moves you from structure into actual project content.

Common examples:

- Markdown notes
- plans
- experiment summaries
- result reports
- paper drafts

In practice, many users treat Markdown files in the quest as a private local-first notebook for:

- notes
- plans
- handoffs
- findings
- team coordination

### 6.5 Canvas

Canvas makes the research map visible.

A healthy quest should not feel like one long chat log.

Canvas should help you see:

- baseline work
- candidate ideas
- failed branches
- successful paths
- later analysis and writing

The graph matters because it shows how the quest grew, not just where it ended.

### 6.6 Click a node in Canvas

Do not stop at looking.

Click a node to inspect what it actually means.

A useful node should lead you toward:

- branch summary
- linked files
- stage state
- durable evidence

This is how Canvas becomes inspectable instead of decorative.

### 6.7 Details

Use `Details` when you want the fastest high-confidence answer to:

`What is the current state of this quest right now?`

This is usually the first page to open when:

- you come back after a break
- the quest has been running for a while
- you want summary before intervention

### 6.8 Memory

Memory is how the quest keeps growing instead of restarting from zero.

Use it to understand:

- what reusable lessons were learned
- which weak paths should not be repeated
- what stable facts were extracted from prior work

Without memory, every round risks becoming disposable.

### 6.9 Copilot / Studio

Keep this surface open when you want to stay close to execution.

Use it to:

- watch the run
- intervene
- ask for a summary
- redirect the route
- continue the thread later

This is where the quest feels collaborative instead of static.

## 7. A practical first operating rhythm

Once the quest is running, the most useful rhythm is usually:

1. let the first round move
2. open the workspace instead of waiting in chat
3. inspect one or two key files
4. check Canvas for branching structure
5. read Details for current state
6. only then decide whether to intervene

This avoids two common mistakes:

- interrupting too early
- trusting a summary before checking durable evidence

## 8. Common mistakes

### 8.1 Treating Start Research like casual chat

It is not a casual chat box.

It is a project contract.

### 8.2 Leaving the goal vague

If the goal does not define verification, the first round will be weaker.

### 8.3 Hiding important references inside the main paragraph

Use the dedicated baseline and reference fields instead.

### 8.4 Ignoring the generated kickoff prompt

This is the cheapest place to catch a misunderstanding.

### 8.5 Treating Canvas as a pretty picture

Click nodes and inspect files. Otherwise you are only seeing shape, not evidence.

### 8.6 Waiting in the workspace without reading files

The file tree is one of the main truth surfaces of the system.

## 9. What to read next

- [02 Start Research Guide](./02_START_RESEARCH_GUIDE.md)
- [06 Runtime and Canvas](./06_RUNTIME_AND_CANVAS.md)
- [07 Memory and MCP](./07_MEMORY_AND_MCP.md)
- [13 Core Architecture Guide](./13_CORE_ARCHITECTURE_GUIDE.md)
