# Style: `scatter_tsne_cluster`

## Best use case

t-SNE cluster visualizations for high-dimensional embeddings, especially when the plot needs many labeled clusters and annotation boxes.

## Visual signature

- Typeface: serif with `usetex=True` (Computer Modern-like); fall back to `STIX Two Text` when TeX is unavailable
- Title: two bold lines around 13.5 pt
- Axis labels: bold, around 12 pt
- Ticks: regular, around 10 pt
- Legend: upper-right, white background, light gray frame, small markers
- Scatter cloud: `s=14`, `alpha=0.55`, no outlines, one color per cluster
- Annotation boxes: rounded boxes with a shared dark border (`#2C3E50`) and a translucent fill derived from the cluster color
- Grid: light dotted gray lines
- Spines: all four visible in dark gray
- Tick direction: inward

## Color example

```python
DS_COLORS = {
    'GSM8K': '#6A4C93',
    'MATH': '#D651A0',
    'GPQA': '#F06292',
    'KodCode': '#FF8A65',
    'BCB': '#FFB74D',
    'ALFWorld': '#FFF176',
    'TriviaQA': '#C888E8',
}
```

## Key parameters

```python
plt.rcParams.update({
    'text.usetex': True,
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman', 'STIX Two Text'],
})

ax.scatter(x, y, c=color, s=14, alpha=0.55, linewidths=0, rasterized=True)

rgba = list(mcolors.to_rgba(color))
rgba[3] = 0.28
ax.annotate(
    r'\\textbf{Name}', xy=...,
    bbox=dict(
        boxstyle='round,pad=0.30',
        facecolor=tuple(rgba),
        edgecolor='#2C3E50',
        linewidth=0.9,
    ),
)

ax.legend(frameon=True, facecolor='white', edgecolor='#CCCCCC',
          markerscale=1.0, handlelength=0.8)

for sp in ax.spines.values():
    sp.set_visible(True)
    sp.set_linewidth(0.9)
    sp.set_color('#333333')

ax.tick_params(direction='in', length=4, width=0.8)
ax.grid(True, color='#E0E0E0', linewidth=0.6, linestyle=':', zorder=0)
```

## Reference outputs

- `repro/scatter_tsne.py`
- `repro/scatter_tsne_repro.png`
