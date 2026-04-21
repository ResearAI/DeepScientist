# Style: `line_training_curve`

## Best use case

Training-process curves comparing multiple methods, especially when the figure needs vertical breakpoint markers and a horizontal reference line.

## Visual signature

- Typeface: `sans-serif`, no LaTeX
- Axis labels: roughly 12-13 pt and bold
- Spines: all four visible
- Tick direction: outward
- Grid: none
- Legend: lower-right with a white background and a gray frame

## Color example

```python
C_DYN   = '#5B0DAD'  # deep purple for the main method
C_NODYN = '#5BBCCA'  # soft teal for the comparison
C_REF   = '#3D78C2'  # separate blue for the horizontal reference line
```

## Key parameters

```python
# Horizontal reference line
ax.axhline(ref_y, color=C_REF, lw=1.5, linestyle='--')

# Vertical breakpoint lines
ax.axvline(step1, color=C_DYN, lw=1.5, linestyle='--', alpha=0.85)
ax.axvline(step2, color=C_NODYN, lw=1.5, linestyle='--', alpha=0.85)

# Full box + outward ticks
for sp in ax.spines.values():
    sp.set_visible(True)
    sp.set_linewidth(1.0)
ax.tick_params(direction='out', length=4, width=0.8)
```

## Reference outputs

- `repro/line_aime.py`
- `repro/line_aime_repro.png`
