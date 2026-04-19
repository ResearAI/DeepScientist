# Style: radar_dual_series

## 适用场景
两个方法在多维 benchmark 的雷达/蜘蛛图对比，强调主方法优势。

## 视觉特征
- 字体：`sans-serif`（DejaVu Sans / Arial），无 LaTeX
- 轴标签：约 9pt，常规，多行文字居中
- 数值标注：约 8pt，各系列同色，带白底 bbox（alpha=0.85）
- 图例：左上角图外，黑色系列名（主方法加粗），彩色短线段
- 网格：同心正**八边形**虚线（用 `close(angles)` 的多边形，不用圆形近似！）
- Spine：`ax.set_frame_on(False)`（Polar axes 隐藏外框）
- 填充透明度：`alpha=0.18`（两系列统一）
- 线宽比：主方法约 2.8pt，对比方法约 1.3pt（原图差异显著）

## 颜色示例（DoRA 论文）
```python
C_DORA = '#76A676'  # 淡灰绿
C_LORA = '#7D82FF'  # 淡紫蓝
```

## 关键参数
```python
fig, ax = plt.subplots(figsize=(8, 7.8), subplot_kw=dict(projection='polar'))
ax.set_theta_zero_location('N')    # 正上方为 0
ax.set_theta_direction(-1)         # 顺时针
ax.set_yticks([]); ax.set_xticks([])

# 同心正八边形网格（非圆！）
angles = np.linspace(0, 2*np.pi, N, endpoint=False)
for r in [0.4, 0.55, 0.7, 0.85, 1.0]:
    ax.plot(close(angles), close(np.full(N, r)),
            color='#CCCCCC', lw=0.8, linestyle='--')

# 数据归一化：各轴独立映射到 [RMIN, RMAX]
RMIN, RMAX = 0.35, 1.0
def nrm(v, vmin, vmax): return RMIN + (RMAX-RMIN)*(v-vmin)/(vmax-vmin)

ax.fill(close(angles), close(dora_r), color=C_DORA, alpha=0.18)
ax.plot(close(angles), close(dora_r), color=C_DORA, lw=2.8)
ax.fill(close(angles), close(lora_r), color=C_LORA, alpha=0.18)
ax.plot(close(angles), close(lora_r), color=C_LORA, lw=1.3)

# 数值标注带白底
ax.text(ang, r+0.08, f'{v:.2f}', ha='center', fontsize=7.8, color=C_DORA,
        bbox=dict(boxstyle='round,pad=0.12', facecolor='white',
                  edgecolor='none', alpha=0.85))

# 图例（fig.text 实现）
fig.text(0.09, 0.90, '────  ', color=C_DORA, fontsize=12, fontweight='bold')
fig.text(0.155, 0.90, 'DoRA',  color='black',  fontsize=11, fontweight='bold')
```

## 复现文件
- `repro/radar_dora.py`
- `repro/radar_dora_repro.png`
