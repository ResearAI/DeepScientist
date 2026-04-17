---
name: paper-plot
description: Use when structured numeric data, arrays, or CSV-like measurements should be turned into a publication-quality figure by adapting a bundled paper-style plotting template instead of improvising a new chart from scratch.
skill_role: companion
---

# Paper Plot

Use this skill when the job is to turn measured data into a paper-quality figure quickly and consistently.
This companion skill is adapted from `Trae1ounG/paper-plot-skills/tree/main/plot-from-data`.

## Interaction discipline

- Follow the shared interaction contract injected by the system prompt.
- If chart semantics, units, grouping, or the intended comparison are ambiguous, ask the user a focused follow-up question instead of guessing.
- When the first durable render is ready, send a concise progress update that says which style was chosen, what data source was used, and where the output was written.

## Use when

- the user provides measured values, arrays, tables, or CSV-like data and wants a publication-quality figure
- the chart can be expressed as a bar, line, scatter, or radar plot using one of the bundled styles
- `write`, `analysis-campaign`, or `experiment` needs a first-pass paper-facing figure from structured results

## Do not use when

- the job is only final visual QA or last-mile refinement of an already rendered figure; use `figure-polish`
- the figure is a disposable debug plot with no durable value
- the figure requires a custom multi-panel composition that clearly does not fit any bundled template

All bundled templates emit a `dpi=300` PNG first. If a paper-facing final export needs vector output or further visual refinement, hand the result to `figure-polish` after the first-pass render.

## Available Styles

| Style | Type | Script | Best for |
|-------|------|--------|----------|
| `bar_paired_delta` | Bar | `scripts/bar_memevolve.py` | Baseline vs. method paired comparison with explicit gain arrows |
| `bar_grouped_hatch` | Bar | `scripts/bar_spice.py` | Multi-method comparison or ablation with highlighted primary method |
| `line_confidence_band` | Line | `scripts/line_selfdistill.py` | Training or scaling curves with uncertainty bands |
| `line_training_curve` | Line | `scripts/line_aime.py` | Ordered curves with reference lines or breakpoint markers |
| `line_loss_with_inset` | Line | `scripts/line_loss_inset.py` | Curves that need a local zoomed inset |
| `scatter_tsne_cluster` | Scatter | `scripts/scatter_tsne.py` | Clustered embedding plots with annotations |
| `scatter_broken_axis` | Scatter | `scripts/scatter_break.py` | Scatter plots with broken-axis layout for outliers or large gaps |
| `radar_dual_series` | Radar | `scripts/radar_dora.py` | Two-method multi-dimension comparison |

## Workflow

```
1. Confirm the chart question, units, grouping, and preferred output location.
2. Choose the closest bundled style; if two or more styles fit, ask the user or state the rationale.
3. Read `references/<style_name>.md` for the exact layout, color, and rcParams expectations.
4. Copy `scripts/<script>.py` into a quest-local figure workspace such as `paper/figures/scripts/<figure_id>.py`.
5. Replace only the clearly marked data and label section in the copied script; keep the bundled template immutable.
6. Run the copied script and inspect the rendered output.
7. If the figure is durable or paper-facing, hand the result to `figure-polish` before treating it as final.
```

## Data Substitution Tips

Each template script keeps the editable data block near the top, usually as `np.array(...)` declarations or a small dictionary.

- Keep array rank and basic types stable unless you intentionally refactor the plotting logic.
- If the number of categories changes, update width calculations, color lists, tick labels, and legend labels together.
- Replace labels and legends directly in the copied script instead of post-editing the exported figure.
- Keep the source data path and generated script path next to the figure output so the figure remains reproducible.

## Detailed Style Parameters

Read the corresponding file in `references/` for exact `rcParams`, colors, font sizes, spine settings, and tick directions before generating:

- Bar: `references/bar_paired_delta.md`, `references/bar_grouped_hatch.md`
- Line: `references/line_confidence_band.md`, `references/line_training_curve.md`, `references/line_loss_with_inset.md`
- Scatter: `references/scatter_tsne_cluster.md`, `references/scatter_broken_axis.md`
- Radar: `references/radar_dual_series.md`

## Relationship to other skills

- Use `paper-plot` for first-pass figure generation from structured data, especially for standard bar, line, scatter, and radar figure families.
- Use `figure-polish` for final render-inspect-revise work on durable milestone or paper-facing figures.
- In `write`, prefer this skill before inventing a new plotting stack for standard bar, line, scatter, or radar figures.
