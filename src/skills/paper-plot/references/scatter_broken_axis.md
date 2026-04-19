# Style: scatter_broken_axis

## 适用场景
需要对比低 context（0-50k）与高 context（115k、200k）系统，X 轴因范围差异大需要折断表示。

## 视觉特征
- 字体：`sans-serif`，轴标签约 13pt 粗体
- Spine：左图 L 形（左+下），右图仅下
- 折断符号：仅在**底边 x 轴**画斜杠，不画顶部
- 图例：右下角，白底浅灰框，6 项（按顺序排列）
- 散点描边：主系列（Pareto 星、Few-shot 圆等）有黑色描边（`edgecolors='black', linewidths=0.8`）
- 非 Pareto 散点：无描边（`linewidths=0`），更淡（alpha=0.85）

## 颜色示例（Meta-Harness 论文）
```python
C_PARETO    = '#E53935'  # 亮红
C_NONPARETO = '#F4B8B8'  # 淡粉雾
C_DASH      = '#F0A0A0'  # 粉色虚线
C_FEW       = '#6B4FA0'  # 深紫
C_FEW_LINE  = '#B8A8D8'  # 浅紫曲线
C_MCE       = '#E69B00'  # 橙色
C_ACE       = '#2E86C1'  # 蓝色
C_ZS        = '#5B2D8E'  # 深紫（zero-shot）
```

## 关键参数
```python
# 双轴布局
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 5.5),
    gridspec_kw={'width_ratios': [5, 1.3], 'wspace': 0.05})

# 折断符号（只在底边）
d = 0.015
kwargs = dict(transform=ax1.transAxes, color='k', clip_on=False, lw=1.2)
ax1.plot((1-d, 1+d), (-d, +d), **kwargs)   # 底部斜杠（只这一条！）
kwargs2 = dict(transform=ax2.transAxes, color='k', clip_on=False, lw=1.2)
ax2.plot((-d, +d), (-d, +d), **kwargs2)    # 底部斜杠

# L 形 spine
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax2.spines[['top', 'right', 'left']].set_visible(False)

# 图例
from matplotlib.lines import Line2D
legend_elements = [
    Line2D([], [], marker='*', color='w', markerfacecolor=C_PARETO,
           markersize=11, label='Ours (Pareto)',
           linestyle='--', linewidth=1.2, markeredgecolor='black', markeredgewidth=0.8),
    ...
]
ax1.legend(handles=legend_elements, loc='lower right',
           frameon=True, facecolor='white', edgecolor='#CCCCCC')
```

## 复现文件
- `repro/scatter_break.py`
- `repro/scatter_break_repro.png`
