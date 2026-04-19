# Style: line_training_curve

## 适用场景
训练过程曲线，展示多种方法的收敛对比，带垂直断点线和水平基准线。

## 视觉特征
- 字体：`sans-serif`，无 LaTeX
- 轴标签：约 12-13pt 粗体
- Spine：四边全显
- 刻度：朝外（`direction='out'`）
- 网格：无
- 图例：右下角，白底灰框

## 颜色示例（AIME 训练曲线）
```python
C_DYN   = '#5B0DAD'  # 深紫（主方法）
C_NODYN = '#5BBCCA'  # 柔和青绿（对比）
C_REF   = '#3D78C2'  # 独立蓝（水平参考线，与主线颜色区分！）
```

## 关键参数
```python
# 水平参考线（独立颜色）
ax.axhline(ref_y, color=C_REF, lw=1.5, linestyle='--')

# 垂直断点线（与对应曲线同色）
ax.axvline(step1, color=C_DYN,   lw=1.5, linestyle='--', alpha=0.85)
ax.axvline(step2, color=C_NODYN, lw=1.5, linestyle='--', alpha=0.85)

# 四边框 + 朝外刻度
for sp in ax.spines.values():
    sp.set_visible(True); sp.set_linewidth(1.0)
ax.tick_params(direction='out', length=4, width=0.8)
```

## 复现文件
- `repro/line_aime.py`
- `repro/line_aime_repro.png`
