---
name: nature-paper2ppt
description: Build a complete but efficient Nature-style Chinese PPTX presentation from a scientific paper, preprint, PDF, article text, abstract, figure legends, or reading notes. Use this skill whenever the user asks to make slides/PPT/PPTX for journal club, group meeting, paper sharing, thesis seminar, lab meeting, department report, or academic presentation from a research paper, not only medical papers. It identifies the paper type and argument, selects only the figures needed for the story, writes Chinese slide content and speaker notes, creates the actual .pptx deck, and performs lightweight verification with cross-platform Python tooling by default.
skill_role: companion
---

# Purpose

This companion skill is adapted from `Yuan1z0825/nature-skills/tree/main/nature-paper2ppt`.
See `UPSTREAM_LICENSE.txt` for the upstream MIT license.

## DeepScientist integration

- Follow the shared interaction contract injected by the system prompt.
- Use this only when the user explicitly wants slides, PPT, PPTX, a journal-club deck, a lab-meeting deck, or a paper-sharing presentation.
- Do not route ordinary paper writing, manuscript polishing, or evidence repair into this skill.
- The expected output is a real `.pptx` deck plus lightweight verification, not only an outline or talk script.

Transform a scientific paper or paper-derived notes into a complete Chinese, figure-integrated PPTX presentation package with a Nature-style reporting logic.

The skill must not stop at an outline or script. The expected end product is a real `.pptx` deck. Keep supporting files minimal unless the user asks for more traceability.

Use this skill for papers across scientific fields, including:
- life sciences and medicine
- chemistry and materials science
- environmental and earth sciences
- physics and engineering
- computational biology, AI, and methods papers
- interdisciplinary Nature-family style research
- reviews, perspectives, resources, datasets, and benchmark papers

# Core Principle
Use the paper's scientific argument as the presentation spine.

The default slide logic should help the audience answer, in order:
1. Why does this problem matter?
2. What gap or bottleneck does the paper address?
3. What did the authors do?
4. What is the key evidence?
5. Why should we trust the result?
6. What is new, reusable, or broadly meaningful?
7. Where are the boundaries and open questions?

This is more important than copying the paper section order.

# Lean Operating Mode
Default to the lowest-overhead workflow that still produces a usable PPTX.

Do:
- read only the source material needed to understand the paper's argument,
- extract only figures/tables that will actually appear in the deck,
- create the PPTX as the primary deliverable,
- run lightweight structural checks on the PPTX package,
- write a short QA report.

Avoid by default:
- exhaustive extraction of every figure, page, image, table, or supplement,
- full OCR unless normal text extraction fails or the PDF is scanned,
- saving full raw extracted paper text unless it is needed for debugging or reuse,
- installing new dependencies when an existing tool can complete the task,
- launching GUI apps or desktop automation just to render previews,
- generating long markdown scripts when the user only needs a deck,
- rendering every slide when no reliable headless renderer is available.

## Toolchain Policy
Use a cross-platform Python-first stack unless the user explicitly asks for something else:
- PyMuPDF for metadata, text extraction, page rendering, and page-level crops,
- Pillow for figure crops, contact sheets, and lightweight preview images,
- python-pptx for slide authoring and PPTX-safe editing,
- zipfile plus a reopen pass through python-pptx for package validation.

This stack must work on macOS, Linux, and Windows. Use `pathlib` paths, project-local output directories, and Office-safe fonts or theme fonts. Do not hardcode OS font paths or platform-specific file locations. If Python packages are missing, create a local virtual environment and install the minimum packages only when policy permits; do not install broad document suites just to finish a normal deck.

Treat LibreOffice/soffice as optional, only when it is already available and a real rendered preview is worth the cost. Avoid Keynote, PowerPoint desktop automation, AppleScript, Preview, Finder, `open`, and any OS-specific font or path dependency in helper scripts. If a preview can be made from extracted slide objects or assets, prefer that over re-rendering the whole deck.

Ask or document the tradeoff before doing expensive extras such as full supplementary-material processing, high-resolution recreation of many figures, full slide-by-slide rendered QA, or very long decks.

# Accepted Inputs
The skill may receive:
- a full paper PDF
- supplementary figures or tables
- Word or markdown converted paper text
- abstract + results + figure legends
- structured reading notes
- manually pasted article content
- an `input/source.md` file
- a user-provided PPTX template

Default output language is simplified Chinese unless the user requests otherwise. Preserve important technical terms, abbreviations, gene/protein names, model names, dataset names, equations, and statistical terms in English when needed.

# Default Fast Path
For a normal selectable-text paper PDF, run the shortest complete path:
1. Extract metadata, abstract, headings, figure legends, and table captions with PyMuPDF.
2. Identify the paper type, argument, and candidate figures before rendering high-resolution pages.
3. Render low-resolution contact sheets only when figure locations are unclear.
4. Render high-resolution images only for selected figure/table pages and crop only assets that will appear in the deck.
5. Build the PPTX directly with python-pptx, using native tables/charts when values are explicit and figure crops when the original visual carries the evidence.
6. Verify by reopening the PPTX and inspecting package structure; render slide previews only if a reliable cross-platform headless renderer is already available.

OCR, full supplementary extraction, all-page high-resolution rendering, all-slide rendered QA, and long script files are opt-in or justified exceptions, not defaults.

# Workflow

## Step 1. Read and extract source material
Extract, when available:
- title, authors, journal/preprint server, year, DOI
- field and subfield
- paper type
- central problem and knowledge gap
- main claim or thesis
- study design, workflow, model, dataset, or experimental system
- key methods and controls
- main results and quantitative findings
- key figures, tables, and figure legends
- validation, robustness, ablation, or sensitivity analyses
- limitations and unresolved questions
- broader scientific, clinical, technical, environmental, or translational meaning

Do not invent missing numbers, mechanisms, datasets, or figure details.
Use a two-pass reading strategy: first capture metadata, abstract, headings, figure legends, and table captions; then read only the result and methods pages needed to support the slides.

## Step 2. Classify the paper before designing slides
Identify the primary paper type. Choose the closest fit:
- discovery / mechanism paper
- translational or applied science paper
- clinical or population study
- methods / algorithm / tool paper
- resource / dataset / atlas paper
- omics, single-cell, spatial, or multi-modal study
- materials / chemistry / engineering performance study
- environmental, ecological, or earth-system study
- benchmark / evaluation paper
- review / perspective / commentary
- meta-analysis / systematic review

Then identify the best presentation logic:
- `claim-first`: useful when the paper has one strong central claim
- `question-to-evidence`: useful for mechanism and discovery papers
- `problem-to-solution`: useful for methods, tools, and engineering papers
- `workflow-to-validation`: useful for datasets, atlases, omics, and benchmarks
- `evidence-map`: useful for reviews and perspectives

## Step 3. Build the Chinese presentation plan
Default length: 12-16 slides for a 15-20 minute report.

The default structure is:
1. 标题页
2. 研究背景：为什么这个问题重要
3. 知识缺口 / 技术瓶颈
4. 论文核心问题与主张
5. 研究设计 / 技术路线 / 分析框架
6. 关键证据1
7. 关键证据2
8. 关键证据3
9. 验证、对照或稳健性证据
10. 机制模型 / 方法优势 / 综合框架
11. 创新点与可复用价值
12. 局限性与未解决问题
13. 总结与讨论

Adapt this structure to the paper type. Do not force every paper into the same template.

For a quick or unspecified request, prefer 10-14 slides. Expand beyond 16 slides only when the user asks for a detailed seminar deck or the paper genuinely needs the extra space to stay readable.

## Step 4. Select figures as evidence, not decoration
Inspect the source for:
- graphical abstracts or summary models
- study design and workflow diagrams
- central result figures
- microscopy or imaging panels
- heatmaps, dimensionality reduction, networks, maps, or spatial plots
- survival curves, forest plots, calibration curves, or statistical result plots
- materials characterization and performance plots
- model architecture, benchmark, ablation, or error analysis figures
- key tables
- validation or control figures

Prioritize figures that carry the paper's argument:
1. design/workflow,
2. main evidence,
3. validation or robustness,
4. mechanism/model/synthesis,
5. practical or conceptual implication.

Prefer a few readable key panels over many unreadable full figures.

## Step 5. Extract and prepare figure assets
When the source contains usable figures:
- extract original images from the PDF or source package when possible, but only for selected figures,
- render high-resolution page images only for pages containing selected figures or tables,
- crop relevant panels when full figures are too dense,
- keep original data visuals unchanged,
- save images under `output/assets/figures/`,
- use clear filenames such as `fig1_workflow.png`, `fig2b_main_result.png`, or `fig4ef_validation.png`,
- record source page, figure number, panel, crop status, and intended slide in `output/asset_manifest.md`.

For a standard 10-14 slide journal-club deck, usually select 4-8 figure/table assets. Add more only when they directly support distinct evidence slides.

For tables and simple quantitative comparisons, prefer editable PPT-native tables/charts when values are explicit in the paper text or table. Use table screenshots only when recreating the table would risk transcription errors or when layout/formatting itself is the evidence.

If extraction fails, use the best available fallback:
- rendered page screenshot with careful crop,
- recreated editable table only when values are explicitly available,
- clearly labeled placeholder only when the visual is unavailable.

## Step 6. Write slide-by-slide content
For each slide, write:
- Chinese title
- slide purpose
- suggested layout
- 3-4 concise Chinese bullets
- selected figure or table asset, if any
- Chinese figure caption and interpretation
- one core takeaway sentence
- Chinese speaker note when oral explanation is useful

Each slide should make one point. Result slides should answer:
- What does this figure show?
- Why does it matter for the paper's claim?
- What should the audience believe after seeing it?

Speaker notes should be useful but concise. Do not write long narration for every slide when the slide content is self-explanatory.

### Evidence hierarchy on a slide
For any result slide, order the visual logic like this:
1. hero figure or main table crop,
2. narrow interpretation rail or short annotation band,
3. only the minimum labels needed to read the evidence,
4. any deeper explanation moves to speaker notes or the next slide.

Do not let the interpretation block become as large or louder than the evidence itself.

### Layout adaptation rule
Do not default to a fixed 50/50 left-right split.
Choose the layout from the figure's aspect ratio, density, and role in the argument:
- use a full-width or near-full-width visual when the figure is wide, complex, or the slide's main evidence,
- use a tall image with a narrow text rail when the figure is vertically oriented or the caption/interpretation is short,
- use a top/bottom stack when the figure needs more horizontal room or the slide benefits from a short argument above and a visual below,
- use an asymmetric split such as 70/30, 75/25, or 65/35 when one side clearly dominates,
- use a compact visual-plus-callout layout when the slide only needs a few annotations,
- use a table or figure crop instead of shrinking a dense graphic into a small frame.

Treat equal-weight 1:1 layouts as the exception, not the default. Use them only when the text and image truly carry comparable weight and neither needs dominance. In most result slides, one side should clearly dominate.

Prefer the smallest text block that still makes the claim legible. If the visual needs space, give it space; if the text is the main point, let the slide breathe and keep the figure smaller or move it to its own slide.

For dense figures or tables, crop to the most relevant panels and avoid squeezing them into equal columns. For sparse slides, do not pad the page with extra boxes just to fill space.

### Slide archetype defaults
Use these defaults unless the source strongly suggests otherwise:
- Cover slide: one dominant visual or typographic idea, no balanced split, no dashboard-like grid.
- Background/problem slide: short setup text plus one compact context visual or schematic.
- Workflow/method slide: full-width or top-to-bottom process diagram, not two equal text/figure columns.
- Result/evidence slide: one dominant figure or table crop with a narrow interpretation rail; avoid 1:1 layouts unless the evidence and explanation truly balance.
- Comparison/table slide: full-width table or split table across slides if it becomes cramped.
- Model/summary slide: a large central model with a brief takeaway strip or short annotation band.
- Conclusion/discussion slide: text-led but open composition, with 2-4 bullets and no unnecessary containers.

### Title writing rule
Use conclusion-style titles whenever possible. A good title states the slide's point, not just its topic. Prefer sentences like “PathAgent 主动识别信息不足并补充证据” over labels like “Case Study” or “Figure 3”.

### Visual density rule
Do not downscale a dense figure, table, or multi-panel graphic into a tiny slot just to preserve symmetry. If a visual cannot be read at presentation scale, crop it, split it, or give it its own slide. Prefer one legible visual over several cramped ones.

## Step 7. Build the actual PPTX deck
Create a real `.pptx` file as the primary deliverable.

Use `python-pptx` as the default authoring tool for scientific paper decks because it creates editable PPTX files and runs on macOS, Linux, and Windows. Use a user-provided PPTX template if supplied. Use the local Presentations plugin or other PPTX tooling only when it is already available and clearly reduces work without violating the cross-platform policy.

Use tools already available in the environment first. Install only the minimum Python dependencies when the PPTX cannot otherwise be created and the environment policy permits it.

The PPTX should:
- use 16:9 widescreen layout by default,
- include the selected original figures,
- use Chinese titles, bullets, captions, and speaker notes,
- include source labels for figure slides,
- keep slide text concise and readable,
- avoid text-only result slides when visuals are available,
- maintain consistent typography, spacing, titles, captions, and section transitions.

Use compact, evidence-first page composition. Avoid making every result slide a rigid two-column template or any balanced 1:1 scaffold. Let slide geometry follow the figure rather than forcing the figure to fit a template.

When a slide has one dominant figure, let that figure own the page. Keep the annotation rail narrow and short, and move secondary explanation into speaker notes or a follow-up slide rather than expanding the slide horizontally into a symmetrical split.

## Step 8. Render, inspect, and revise
After creating the PPTX, render previews only when a reliable headless renderer is readily available.

If rendered previews are available, inspect them for:
- missing images,
- distorted or low-resolution figures,
- unreadable panels,
- text overflow,
- overlapping captions, bullets, and figures,
- excessive bullet density,
- wrong slide order,
- missing source labels,
- missing or unhelpful speaker notes.

If no reliable renderer is available, perform lightweight verification instead:
- reopen the PPTX with the generation library when possible,
- check slide count,
- check embedded media count,
- check speaker notes presence when notes were planned,
- check obvious shape bounds if tooling supports it,
- create a contact sheet from selected extracted assets only if helpful, not a full-deck screenshot set.

Revise obvious defects. Document any remaining limitation in `output/qa_report.md`.

# Paper-Type Guidance

## Discovery / mechanism papers
Use a question-to-evidence arc:
1. phenomenon and importance,
2. unknown mechanism,
3. hypothesis or question,
4. experimental design,
5. evidence chain,
6. model,
7. limitations and next experiments.

## Methods, AI, tool, or algorithm papers
Use a problem-to-solution arc:
1. current bottleneck,
2. proposed method,
3. workflow or architecture,
4. evaluation design,
5. performance compared with baselines,
6. ablation, robustness, or failure cases,
7. reuse scenarios and limitations.

## Resource, dataset, atlas, omics, or benchmark papers
Use a workflow-to-validation arc:
1. why the resource is needed,
2. dataset/cohort/sample design,
3. generation and quality control workflow,
4. main landscape or map,
5. validation and reproducibility,
6. example biological or technical insights,
7. access, reuse, and boundaries.

## Clinical, population, or intervention studies
Use a design-to-inference arc:
1. clinical/public-health problem,
2. study question,
3. cohort/trial/design,
4. endpoints and variables,
5. primary result,
6. subgroup/sensitivity/secondary analyses,
7. bias, limitations, and practical implication.

## Materials, chemistry, physics, engineering papers
Use a property-to-mechanism or design-to-performance arc:
1. target property or technical challenge,
2. design principle,
3. synthesis/fabrication/setup,
4. characterization,
5. performance evidence,
6. mechanism or structure-property relationship,
7. scalability, stability, or application boundary.

## Reviews and perspectives
Use an evidence-map arc:
1. why the topic matters now,
2. conceptual framework,
3. theme 1,
4. theme 2,
5. theme 3,
6. controversy or unresolved problem,
7. author's synthesis,
8. future directions.

# Style Rules
Use a restrained Nature-style academic presentation design:
- clean white or very light background,
- dark readable text,
- one or two muted accent colors,
- compact but not crowded layouts,
- figure-first result slides,
- concise captions,
- no decorative stock images,
- no decorative gradients,
- no exaggerated marketing-style section pages.

Use Chinese suitable for oral academic reporting:
- avoid rigid translation,
- avoid long paragraphs,
- avoid jargon stacking,
- preserve technical terms where Chinese translation would reduce precision,
- prefer evidence-based interpretation over vague praise.

Borrow Nature-style figure-page composition principles, but keep this skill self-contained and independent from any other skill. Treat each slide like a publication figure page: one dominant idea, one clear evidence hierarchy, and asymmetry when the story needs it.

### Nature-style page composition
- Prefer one hero visual per slide when the evidence is complex or the claim is central.
- Use asymmetric layouts by default when the visual and the text are not equally important.
- Keep gutters real and tight. Use whitespace to separate roles, not to make a balanced grid.
- Use small panel labels (`a`, `b`, `c`) when a slide contains multiple visual subpanels.
- Use direct labels or a shared legend strip when categories repeat across panels.
- Reuse one restrained palette across the slide or slide family; reserve green/red for gains, drops, or directional change.
- If a slide has a schematic and data, let one dominate and the other validate.
- Use dark backgrounds only when the dominant visual is an image plate or the source content benefits from it; keep normal chart slides light.
- Avoid decorative boxes, fake cards, and symmetrical two-column scaffolds unless the content truly calls for them.
- If a figure would become unreadable when scaled down, crop it, split it, or move it to its own slide.

# Citation and Attribution Rules
Include source information:
- title slide: paper title, authors if useful, journal/preprint server, year, DOI if available,
- figure slides: small labels such as `Source: Fig. 2b, Nature, 2024`,
- adapted or redrawn content: label as `整理自` or `改绘自`,
- do not remove original figure labels or alter scientific data.

# Output Files
Generate a minimal but complete output package by default.

## 1. `output/final_presentation_cn.pptx`
The main deliverable: a complete Chinese PPTX deck with figures, captions, takeaways, source labels, and speaker notes.

## 2. `output/qa_report.md`
A short quality report:
- PPTX creation status,
- slide count,
- figures inserted,
- missing or placeholder figures,
- verification method used,
- known limitations,
- manual follow-up if needed.

## 3. `output/assets/figures/`
Extracted or cropped figure assets used in the deck.

## 4. `output/asset_manifest.md`
Figure asset traceability file, generated only when external figure/table assets are extracted:
- asset filename,
- original figure / panel,
- source page or source file,
- extraction method,
- slide placement,
- quality notes.

If no external figure/table assets are extracted, omit `asset_manifest.md` or write a one-line note in `qa_report.md` instead.

Create these optional files only when useful for review, debugging, or user-requested traceability:

## Optional: `output/ppt_outline_cn.md`
Chinese outline:
- paper information,
- paper type,
- central argument,
- slide structure,
- slide purpose.

## Optional: `output/figure_plan.md`
Figure selection plan:
- figure / panel,
- what it shows,
- why it matters,
- recommended slide,
- Chinese caption,
- interpretation.

## Optional: `output/ppt_script_cn_with_figures.md`
Slide-by-slide script:

```markdown
## Slide X. [中文标题]
- Purpose:
- Layout:
- On-slide bullets:
  - ...
  - ...
  - ...
- Figure/Table:
- Chinese caption:
- Core takeaway:
- Speaker note:
```

## Optional: `output/rendered/`
Rendered slide previews only when a reliable headless renderer is available or the user requests visual QA.

Skip the optional outline/script/figure-plan files by default unless they materially reduce back-and-forth, help verify a complex paper, or are explicitly requested.

# Quality Rules
- Build the `.pptx` whenever tooling is available.
- Do not stop at a markdown outline or script.
- Do not fabricate results, methods, numbers, or figure details.
- Do not add expensive processing steps unless they improve the deck or were requested.
- Do not overload slides with text.
- Do not make result slides text-only when figures are available.
- Make every slide serve the paper's argument.
- Ensure figures are readable at presentation scale.
- Ensure text, captions, and figures do not overlap.
- Document uncertainty and missing source material clearly.

# Fallback Rules
If only partial content is available:
- still create a useful PPTX structure when possible,
- clearly mark uncertain slides or missing details,
- use placeholders only when a required figure is unavailable,
- do not invent exact values or claims,
- write `output/qa_report.md` explaining what could not be verified.

If PPTX tooling is unavailable:
- generate a concise markdown outline and figure plan,
- prepare figure assets if possible,
- explain why the PPTX could not be built in the current environment,
- keep the outputs structured enough for a downstream PPTX builder to run without re-reading the paper.
