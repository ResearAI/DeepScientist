# Style: scatter_tsne_cluster

## 适用场景
高维 embedding 经 t-SNE 降维后的聚类可视化，多类别、带标注框的散点图。

## 视觉特征
- 字体：serif + `usetex=True`（Computer Modern），无 TeX 可用 `STIX Two Text`
- 标题：两行粗体，约 13.5pt
- 轴标签：粗体，约 12pt
- 刻度：常规，约 10pt
- 图例：右上角，白底浅灰框（`frameon=True, edgecolor='#CCCCCC'`），小标记
- 散点：`s=14, alpha=0.55`，无描边（`linewidths=0`），各聚类独立颜色
- 注释框：`boxstyle='round,pad=0.30'`，统一深灰边框（`#2C3E50`），背景为对应聚类色 + alpha=0.28
- 网格：浅灰点线（`linestyle=':', color='#E0E0E0', lw=0.6`）
- Spine：四边全显，深灰色（`#333333`），约 0.9pt
- 刻度方向：朝内（`direction='in'`）

## 颜色示例（MemEvolve 论文）
```python
DS_COLORS = {
    'GSM8K':    '#6A4C93',  # 深紫
    'MATH':     '#D651A0',  # 玫红
    'GPQA':     '#F06292',  # 玫瑰粉
    'KodCode':  '#FF8A65',  # 亮橙
    'BCB':      '#FFB74D',  # 琥珀
    'ALFWorld': '#FFF176',  # 亮黄（容易误用为蓝，注意！）
    'TriviaQA': '#C888E8',  # 亮薰衣草紫
}
```

## 关键参数
```python
plt.rcParams.update({
    'text.usetex': True,
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman', 'STIX Two Text'],
})

ax.scatter(x, y, c=color, s=14, alpha=0.55, linewidths=0, rasterized=True)

# 注释框（聚类标签）
import matplotlib.colors as mcolors
rgba = list(mcolors.to_rgba(color)); rgba[3] = 0.28
ax.annotate(r'\textbf{Name}', xy=...,
    bbox=dict(boxstyle='round,pad=0.30',
              facecolor=tuple(rgba),
              edgecolor='#2C3E50', linewidth=0.9))

# 图例
ax.legend(frameon=True, facecolor='white', edgecolor='#CCCCCC',
          markerscale=1.0, handlelength=0.8)

# 四边框
for sp in ax.spines.values():
    sp.set_visible(True); sp.set_linewidth(0.9); sp.set_color('#333333')
ax.tick_params(direction='in', length=4, width=0.8)
ax.grid(True, color='#E0E0E0', linewidth=0.6, linestyle=':', zorder=0)
```

## 复现文件
- `repro/scatter_tsne.py`
- `repro/scatter_tsne_repro.png`
