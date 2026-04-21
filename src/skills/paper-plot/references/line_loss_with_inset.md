# Style: `line_loss_with_inset`

## Best use case

Training-loss curves where a local region must be magnified to show subtle differences through an inset panel.

## Visual signature

- Typeface: serif with `usetex=True` (Computer Modern-like)
- Main panel: L-shaped spines (left and bottom only) with axis-end arrowheads
- Inset: all four spines visible with a thicker border
- Connectors: black dashed connection lines
- Grid: light dotted grid on the main panel; no grid in the inset
- Legend: upper-right with a white background and a very light gray frame

## Color example

```python
C_ORANGE = '#FF7F0E'  # HybridNorm with spikes
C_BLUE   = '#1F77B4'  # HybridNorm-ResiDual with higher noise
C_GREEN  = '#2CA02C'  # SiameseNorm / smoother lower loss
```

## Key parameters

```python
# L-shaped main panel
ax_main.spines['top'].set_visible(False)
ax_main.spines['right'].set_visible(False)

# Axis-end arrowheads
ax_main.plot(1, 0, '>k', transform=ax_main.get_yaxis_transform(),
             clip_on=False, markersize=5)
ax_main.plot(0, 1, '^k', transform=ax_main.get_xaxis_transform(),
             clip_on=False, markersize=5)

# Zoom rectangle
zoom_rect = mpatches.FancyBboxPatch(
    (zoom_x1, zoom_y1), zoom_x2 - zoom_x1, zoom_y2 - zoom_y1,
    boxstyle='square,pad=0', linewidth=1.0, edgecolor='#333333',
    facecolor='none', linestyle='--', zorder=5)
ax_main.add_patch(zoom_rect)

# Connection line
con = ConnectionPatch(
    xyA=(zoom_x2, zoom_y2), coordsA=ax_main.transData,
    xyB=(ax_inset.get_xlim()[0], ax_inset.get_ylim()[1]),
    coordsB=ax_inset.transData,
    color='#333333', lw=0.8, linestyle='--')
fig.add_artist(con)

# Legend
ax_main.legend(loc='upper right', frameon=True,
               facecolor='white', edgecolor='#DDDDDD', framealpha=1.0)
```

## Notes

- The inset y-range should be chosen jointly from the zoom-box range and the local peak structure; avoid leaving large empty areas.
- The main-panel y-axis does not need to start at zero if the source figure clearly uses a tighter value range.

## Reference outputs

- `repro/line_loss_inset.py`
- `repro/line_loss_inset_repro.png`
