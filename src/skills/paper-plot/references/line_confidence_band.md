# Style: `line_confidence_band` (line chart with confidence-band shading)

**Source paper**: Reinforcement learning via self-distillation  
**Chart family**: Line chart with semi-transparent confidence bands  
**Template script**: `repro/line_selfdistill.py`  
**Original figures**: `image2.png` (continuous training curve), `image3.png` (discrete scaling curve)

## Visual signature

- **Colors**: green `#3A8B3A` for the main method, blue `#3B6BB5` for the comparison, gray `#999999` for the base model
- **Band**: `fill_between` using the line color at `alpha=0.15`
- **Line widths**: 1.8 for the main and comparison methods, 1.4 for the base model
- **Markers**: filled circles on the discrete scaling variant
- **Reference line**: gray dashed horizontal line for the continuous training-curve variant
- **Typography**: LaTeX serif with the main legend entry in bold
- **Spines**: keep left and bottom only for an open-axis look
- **Grid**: none
- **Legend**: unframed and placed inside the plot area

## Key parameters

```python
plt.rcParams.update({
    'text.usetex': True,
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman', 'STIX Two Text', 'DejaVu Serif'],
})

C_SDPO = '#3A8B3A'
C_GRPO = '#3B6BB5'
C_BASE = '#999999'

ax.fill_between(x, mean - std, mean + std, color=C_SDPO, alpha=0.15)
ax.plot(x, mean, color=C_SDPO, lw=1.8, label=r'\\textbf{SDPO}')

for side, sp in ax.spines.items():
    sp.set_visible(side in ('left', 'bottom'))

leg = ax.legend(framealpha=0, edgecolor='none')
for text in leg.get_texts():
    if 'main method name' in text.get_text():
        text.set_fontweight('bold')
```

## Variants

### Type A: continuous training curve

- x-axis uses training steps such as `0, 5k, 10k, 15k, 20k`
- the confidence band usually narrows over time
- legend is typically placed in the lower-right
- a horizontal baseline reference line is usually present

### Type B: discrete scaling curve

- x-axis uses manually positioned labels for discrete model sizes
- every point carries a visible circular marker
- legend is typically in the upper-left
- no reference line

## Best use cases

Use this style when the user provides:

```python
# Type A
steps = np.linspace(0, 20000, 200)
sdpo_mean = [...]
sdpo_std = [...]

# Type B
param_labels = ['0.6B', '1.7B', '4B', '8B']
sdpo_pts = [0.215, 0.333, 0.450, 0.490]
sdpo_std = [0.005, 0.006, 0.008, 0.006]
```
