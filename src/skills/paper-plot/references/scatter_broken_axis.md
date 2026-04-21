# Style: `scatter_broken_axis`

## Best use case

Scatter plots comparing low-context (`0-50k`) and high-context (`115k`, `200k`) systems when the x-range is too discontinuous for a single unbroken axis.

## Visual signature

- Typeface: `sans-serif`, with bold axis labels around 13 pt
- Spines: left panel is L-shaped, right panel keeps only the bottom spine
- Axis break marks: only on the **bottom** x-axis edge, not on the top
- Legend: lower-right, white background, light gray frame, six ordered entries
- Marker outlines: main series use black outlines
- Non-Pareto cloud: no outlines and slightly higher transparency

## Color example

```python
C_PARETO    = '#E53935'
C_NONPARETO = '#F4B8B8'
C_DASH      = '#F0A0A0'
C_FEW       = '#6B4FA0'
C_FEW_LINE  = '#B8A8D8'
C_MCE       = '#E69B00'
C_ACE       = '#2E86C1'
C_ZS        = '#5B2D8E'
```

## Key parameters

```python
fig, (ax1, ax2) = plt.subplots(
    1, 2, figsize=(9.5, 5.5),
    gridspec_kw={'width_ratios': [5, 1.3], 'wspace': 0.05},
)

d = 0.015
kwargs = dict(transform=ax1.transAxes, color='k', clip_on=False, lw=1.2)
ax1.plot((1 - d, 1 + d), (-d, +d), **kwargs)
kwargs2 = dict(transform=ax2.transAxes, color='k', clip_on=False, lw=1.2)
ax2.plot((-d, +d), (-d, +d), **kwargs2)

ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax2.spines[['top', 'right', 'left']].set_visible(False)

ax1.legend(
    handles=legend_elements,
    loc='lower right',
    frameon=True,
    facecolor='white',
    edgecolor='#CCCCCC',
)
```

## Reference outputs

- `repro/scatter_break.py`
- `repro/scatter_break_repro.png`
