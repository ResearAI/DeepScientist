# Style: `bar_paired_delta` (paired bars with explicit delta labels)

**Source paper**: MemEvolve: Meta-Evolution of Agent Memory Systems  
**Chart family**: Two-bar grouped comparison (`baseline` vs `method`)  
**Template script**: `repro/bar_memevolve.py`  
**Original figure**: `image1.png`

## Visual signature

- **Colors**: light steel blue `#A8C8E8` for baseline and navy `#1B3D6E` for the method
- **Delta labels**: bold red percentage labels above the method bars
- **Arrows**: solid arrows pointing from the baseline bar top to the method bar top
- **Reference line**: a black dashed horizontal line at the baseline height spanning the pair
- **Grid**: none
- **Border**: all four spines visible with a moderately thick frame
- **Title**: placed inside the axes near the upper-left corner
- **Overall feel**: crisp paired-comparison figure that emphasizes absolute gains over baseline

## Key parameters

```python
COLOR_BASELINE = '#A8C8E8'
COLOR_METHOD   = '#1B3D6E'
COLOR_DELTA    = '#CC2200'

BAR_W = 0.32
GAP = 0.08
spine_linewidth = 1.4
grid = False
title_position = 'upper left inside axes'
```

## Typography

| Element | Typeface | Size | Weight |
| --- | --- | --- | --- |
| Panel title | serif (Palatino / Times-like) | 11.5 | Bold |
| Delta label | serif | 9.5 | Bold |
| Y-axis label | serif | 10 | Normal |
| X-axis ticks | serif | 10 | Normal |
| Y-axis ticks | serif | default | Normal |

```python
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Palatino', 'Times New Roman', 'DejaVu Serif'],
})
```

## Best use cases

Use this style when you have:

- several groups on the x-axis
- exactly two values per group: `baseline` and `method`
- a need to emphasize the relative gain for each group

## Example input shape

```python
groups = ['Web', 'xBench', 'TaskCraft', 'GAIA']
baseline = [58.1, 55.2, 58.7, 59.3]
method = [62.3, 61.2, 65.5, 61.0]
delta = ['+7.1%', '+10.9%', '+11.9%', '+2.7%']
title = 'OWL-Workforce'
ylabel = 'Accuracy (Pass@1)'
```

## Known limitations

- If the original figure used emoji or icon glyphs in the title, matplotlib serif fonts will not render them cleanly. Replace them with text or overlay them as images if needed.
- This style works best when the gain range is modest. Very large deltas can make the arrow geometry look imbalanced.
