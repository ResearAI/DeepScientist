# Style: line_loss_with_inset

## 适用场景
训练 loss 曲线，需要放大局部区域对比细节差异，通过 inset 子图实现局部放大。

## 视觉特征
- 字体：serif + `usetex=True`（Computer Modern）
- 主图：L 形 spine（仅左+下），**带轴端箭头**
- Inset：四边全显，较粗 spine（1.2pt）
- 连接线：黑色虚线（`color='#333333', linestyle='--', lw=0.8`）
- 网格：主图浅灰点线（`linestyle=':', color='#E0E0E0'`）；inset 无网格
- 图例：主图右上角，白底极浅灰框

## 颜色示例（SiameseNorm 论文，tab10 色系）
```python
C_ORANGE = '#FF7F0E'  # HybridNorm（会产生 spike）
C_BLUE   = '#1F77B4'  # HybridNorm-ResiDual（高噪声）
C_GREEN  = '#2CA02C'  # SiameseNorm Ours（平滑低 loss）
```

## 关键参数
```python
# 主图 L 形 spine + 轴端箭头
ax_main.spines['top'].set_visible(False)
ax_main.spines['right'].set_visible(False)
# 轴端箭头
ax_main.plot(1, 0, '>k', transform=ax_main.get_yaxis_transform(),
             clip_on=False, markersize=5)
ax_main.plot(0, 1, '^k', transform=ax_main.get_xaxis_transform(),
             clip_on=False, markersize=5)

# 局部放大框
zoom_rect = mpatches.FancyBboxPatch(
    (zoom_x1, zoom_y1), zoom_x2-zoom_x1, zoom_y2-zoom_y1,
    boxstyle='square,pad=0', linewidth=1.0, edgecolor='#333333',
    facecolor='none', linestyle='--', zorder=5)
ax_main.add_patch(zoom_rect)

# 连接线（从 zoom 框右角到 inset 左边）
from matplotlib.patches import ConnectionPatch
con = ConnectionPatch(
    xyA=(zoom_x2, zoom_y2), coordsA=ax_main.transData,
    xyB=(ax_inset.get_xlim()[0], ax_inset.get_ylim()[1]),
    coordsB=ax_inset.transData,
    color='#333333', lw=0.8, linestyle='--')
fig.add_artist(con)

# 图例
ax_main.legend(loc='upper right', frameon=True,
               facecolor='white', edgecolor='#DDDDDD', framealpha=1.0)
```

## 注意事项
- Inset 的 Y 轴范围应与 zoom box 的 Y 范围以及蓝线峰值综合决定，不要设太大导致大量空白
- 主图 Y 轴底部不从 0 开始（从实际数据 minimum 开始），与原图对齐

## 复现文件
- `repro/line_loss_inset.py`
- `repro/line_loss_inset_repro.png`
