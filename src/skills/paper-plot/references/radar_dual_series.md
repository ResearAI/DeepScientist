# Style: `radar_dual_series`

## Best use case

Radar / spider charts comparing two methods across several benchmark dimensions, with one method clearly highlighted.

## Visual signature

- Typeface: `sans-serif` (DejaVu Sans / Arial-like), no LaTeX
- Axis labels: about 9 pt, regular weight, multi-line centered text
- Value labels: about 8 pt, series-colored, rendered with white background boxes
- Legend: outside the plot in the upper-left, with black text and colored short line segments
- Grid: concentric **octagonal** dashed polygons, not circular approximations
- Frame: `ax.set_frame_on(False)` for a clean polar plot
- Fill: unified `alpha=0.18`
- Line-width contrast: clearly thicker primary method line

## Color example

```python
C_DORA = '#76A676'
C_LORA = '#7D82FF'
```

## Key parameters

```python
fig, ax = plt.subplots(figsize=(8, 7.8), subplot_kw=dict(projection='polar'))
ax.set_theta_zero_location('N')
ax.set_theta_direction(-1)
ax.set_yticks([])
ax.set_xticks([])

angles = np.linspace(0, 2 * np.pi, N, endpoint=False)
for r in [0.4, 0.55, 0.7, 0.85, 1.0]:
    ax.plot(close(angles), close(np.full(N, r)),
            color='#CCCCCC', lw=0.8, linestyle='--')

RMIN, RMAX = 0.35, 1.0
def nrm(v, vmin, vmax):
    return RMIN + (RMAX - RMIN) * (v - vmin) / (vmax - vmin)

ax.fill(close(angles), close(dora_r), color=C_DORA, alpha=0.18)
ax.plot(close(angles), close(dora_r), color=C_DORA, lw=2.8)
ax.fill(close(angles), close(lora_r), color=C_LORA, alpha=0.18)
ax.plot(close(angles), close(lora_r), color=C_LORA, lw=1.3)

ax.text(
    ang, r + 0.08, f'{v:.2f}',
    ha='center', fontsize=7.8, color=C_DORA,
    bbox=dict(boxstyle='round,pad=0.12', facecolor='white',
              edgecolor='none', alpha=0.85)
)
```

## Reference outputs

- `repro/radar_dora.py`
- `repro/radar_dora_repro.png`
