# Backend Selection

At the start of a figure task, ask the user to choose **Python or R** if they have
not already specified a backend. This is a blocking gate: stop after asking and wait
for the user's answer. Do not infer Python just because the task involves simulation,
NumPy-like data, or custom layout, and do not infer R just because the task is biological
or omics-adjacent.

Use the decision table only in either of these cases:

- the user explicitly asks you to recommend or choose the backend;
- the user provides an unambiguous language-specific workflow or file, such as an `.R`
  script, RDS object, Python notebook, or existing Python plotting code.

## Quick decision table

| Recommend R when | Recommend Python when |
|---|---|
| The user brings R scripts, RData/RDS, Seurat objects, DESeq2/limma outputs, survival models, or ggplot templates | The data pipeline is already Python, NumPy/Pandas arrays, PyTorch/TensorFlow outputs, image arrays, or simulation output |
| The target plot is `ggplot2`, `patchwork`, `ComplexHeatmap`, `ggtree`, `circlize`, `survminer`, `maftools`, or Seurat/UMAP-heavy | The target plot needs low-level custom layout, Matplotlib patches, image plates, subplot mosaics, or custom drawing primitives |
| The user provides an R template collection or an existing R plotting workflow | The user wants a self-contained script with matplotlib/seaborn/statsmodels and no R dependency |
| Heatmap annotations are biologically rich and multi-layered | Image panels and quantitative panels need tight pixel/axis control |

If either backend can do the job, honor the user's preference. Do not switch
backends for aesthetics alone.

## Backend exclusivity rule

Backend choice is not just a syntax preference; it defines the graphics engine for
the entire deliverable. Once Python or R has been selected, use that backend for
all of the following:

- plotting scripts;
- mock/simulated data examples that include plotting;
- preview PNG/TIFF files;
- SVG/PDF/TIFF exports;
- visual QA renders and final layout checks.

Do not generate a substitute preview or export with the non-selected backend. For
example, if the user selected R and `Rscript` is missing, do not use Python/matplotlib
to approximate the figure. If the user selected Python and `matplotlib` or another
required Python plotting package is missing, do not use R/ggplot2/ComplexHeatmap to
approximate the figure. Stop, report the selected-backend blocker, and provide the
selected-backend script plus install/run instructions or request permission to install
the selected-backend dependencies.

The non-selected language is allowed only for non-visual utility work, such as
listing files, checking CSV dimensions, decompressing an archive, or converting a
data file before the selected backend draws the figure. It must not import plotting
libraries, open graphics devices, save image/vector files, or decide visual layout.

## Default stacks

### R

- Core plotting: `ggplot2`
- Multi-panel assembly: `patchwork`
- Heatmaps: `ComplexHeatmap`, `circlize`
- Direct labels: `ggrepel`
- Survival/clinical: `survival`, `survminer`, `forestplot`, `ggplot2`
- Single-cell/omics: `Seurat`, `SingleCellExperiment`, `ComplexHeatmap`, `ggtree`
- Export: `svglite`, `grDevices::cairo_pdf`, `ragg`

### Python

- Core plotting: `matplotlib`
- Statistical plots: `seaborn`
- Layout: `subplot_mosaic`, `GridSpec`
- Tables/model output: `pandas`, `numpy`, `statsmodels`
- Images: `matplotlib.imshow`, `skimage`, `tifffile` when needed
- Export: `fig.savefig(... .svg/.pdf/.tiff)`, `svg.fonttype='none'`,
  `pdf.fonttype=42`

## Mixed workflow rule

Use the selected plotting backend for final assembly and all visual output. A mixed
workflow is reasonable only when the non-selected language performs non-visual data
preparation and the selected backend assembles the figure. In that case:

1. Export clean source data as CSV/TSV with stable column names.
2. Assemble the final figure in the selected backend.
3. Keep the source-data file next to the plotting script.
4. Do not stitch, preview, QA-render, or export final image/vector outputs from the
   non-selected backend unless the user explicitly changes the selected backend.

## Recommendation language

Use direct language:

```text
For this figure I recommend R because the main burden is ComplexHeatmap-style
omics annotation and patchwork assembly. I will still keep the export contract
SVG/PDF/TIFF with editable text.
```

```text
For this figure I recommend Python because the key panel is a custom image plate
with quantitative overlays and a subplot_mosaic layout. Matplotlib gives tighter
control over the raster and vector layers.
```
