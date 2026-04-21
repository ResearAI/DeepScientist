# Style: `bar_grouped_hatch` (grouped bars with hatched primary method)

**Source paper**: SPICE: Self-play in corpus environments improves reasoning  
**Chart family**: Grouped bar chart with three bars per group and a hatched primary method  
**Template script**: `repro/bar_spice.py`  
**Original figure**: `image5.png`

## Visual signature

- **Ablation palette**: light orange `#FFB695`, mid orange `#FF7F5E`, deep red `#D00000`
- **Comparison palette**: light gray `#D3D3D3`, mid gray `#A9A9A9`, deep red `#D00000`
- **Hatch**: the primary method uses `//` with white hatch strokes on a dark red fill
- **Bar borders**: every bar uses `edgecolor='white'` to keep symmetric white gaps between bars
- **Spines**: keep only left and bottom for the open-axis look; hide top and right
- **Grid**: y-only, very light gray, dashed, low visual weight
- **Value labels**: show the number above every bar; highlight the primary method with bold deep red text
- **Legend**: upper-right, framed, with the hatch pattern matching the plotted bars
- **Overall feel**: concise paper figure with one clearly emphasized method

## Key parameters

```python
# Ablation colors
COLORS_ABL = ['#F5C5A3', '#E8845A', '#C0392B']

# Comparison colors
COLORS_CMP = ['#C8C8C8', '#707070', '#C0392B']

HATCHES = ['', '', '//']            # Only the primary method uses hatching
BEST_METHOD = 'SPICE'               # Render this method's value labels in bold red

bar_total_width = 0.78              # Total width occupied by one grouped set
grid = 'y-only'
spine_all_visible = True
ymax = 85
x_positions = [0.00, 1.23, 2.46, 3.69]
xlim = (-0.52, 4.18)
legend_bbox = (0.992, 0.986)
```

## Typography

| Element | Typeface | Size | Weight |
| --- | --- | --- | --- |
| Panel title | LaTeX serif / Computer Modern-like | 13.2 | Normal |
| Legend text | LaTeX serif / Computer Modern-like | 9.2 | Normal |
| Primary legend text | LaTeX serif / Computer Modern-like | 9.2 | Bold |
| Value labels | LaTeX serif / Computer Modern-like | 8.7 | Normal |
| Primary value labels | LaTeX serif / Computer Modern-like | 8.7 | Bold |
| Axis labels / ticks | LaTeX serif / Computer Modern-like | 10.8-11.2 | Normal |

```python
plt.rcParams.update({
    'text.usetex': True,
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman', 'STIX Two Text', 'DejaVu Serif'],
    'axes.unicode_minus': False,
})

leg = ax.legend(...)
for text in leg.get_texts():
    if text.get_text() == BEST_METHOD:
        text.set_fontweight('bold')
```

## Best use cases

Use this style when you have:

- several benchmarks on the x-axis
- 2 to 4 methods per benchmark
- one clearly primary method that should stand out
- either an ablation panel or a baseline-vs-method comparison panel

## Example input shape

```python
benchmarks = ['MATH500', "AIME'25", 'GPQA-Diamond', 'MMLU-Pro']
data = {
    'Method A': [68.2, 6.7, 26.3, 51.6],
    'Method B': [72.6, 12.3, 31.8, 53.7],
    'SPICE':    [78.0, 19.1, 39.4, 58.1],
}
best_method = 'SPICE'
title = '(a) SPICE Ablations'
ylabel = 'Accuracy (%)'
xlabel = 'Benchmark'
```

## Variants

- For a single-panel version, call the panel drawing helper once with one data block.
- If you have more than three methods, reduce `bar_total_width` so the bars do not become too thin.
- If the primary method is not the last bar, adjust the offset order rather than reworking the style logic.
- Prefer `bbox_to_anchor` for legend micro-positioning instead of relying only on `loc='upper right'`.
- Tune `xlim`, `x_positions`, and `legend_bbox` per panel instead of forcing both panels to share one rigid layout.
