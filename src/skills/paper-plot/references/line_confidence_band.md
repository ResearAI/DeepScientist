# Style: line_confidence_band（折线 + 置信区间阴影）

**来源论文**：Reinforcement learning via self-distillation  
**图表类型**：折线图（连续训练曲线 / 离散 scaling 曲线）+ 半透明置信区间阴影  
**复现代码**：`repro/line_selfdistill.py`  
**原图**：`image2.png`（连续），`image3.png`（离散 scaling）

---

## 视觉特征描述

- **颜色**：绿 `#3A8B3A`（主方法 SDPO）| 蓝 `#3B6BB5`（对比方法 GRPO）| 灰 `#999999`（base model）
- **阴影**：主线颜色 + `alpha=0.15` 的 `fill_between`，宽度代表置信区间
- **线宽**：主方法 1.8，次要方法 1.8，base model 1.4
- **标记点**（scaling 图）：实心圆 `marker='o'`，大小 6pt
- **参考线**（训练曲线图）：水平灰色虚线 `ls='--'`，代表 baseline 性能
- **字体**：LaTeX serif（usetex=True），标题 normal weight，图例主方法 bold
- **Spine**：只保留左/下（开口式），线宽 0.9，颜色黑
- **Grid**：无
- **图例**：无边框（`framealpha=0, edgecolor='none'`），位于图内

---

## 关键参数

```python
plt.rcParams.update({
    'text.usetex': True,
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman', 'STIX Two Text', 'DejaVu Serif'],
})

C_SDPO = '#3A8B3A'
C_GRPO = '#3B6BB5'
C_BASE = '#999999'

# 阴影
ax.fill_between(x, mean - std, mean + std, color=C_SDPO, alpha=0.15)

# 折线
ax.plot(x, mean, color=C_SDPO, lw=1.8, label=r'\textbf{SDPO}')

# 只保留左/下 spine
for side, sp in ax.spines.items():
    sp.set_visible(side in ('left', 'bottom'))

# 图例无边框，主方法加粗
leg = ax.legend(framealpha=0, edgecolor='none')
for text in leg.get_texts():
    if '主方法名' in text.get_text():
        text.set_fontweight('bold')
```

---

## 两种子类型

### Type A：连续训练曲线（image2）
- x 轴为 step 数，格式化为 `0, 5k, 10k, 15k, 20k`
- 阴影宽度随训练进行逐渐收窄（前期宽、后期窄），用 `exp(-t)` 衰减模拟
- 图例位于**右下角**
- 水平参考虚线：外部 baseline 的性能水平

### Type B：离散 Scaling 曲线（image3）
- x 轴为离散参数量，使用等间距 x_pos + 手动刻度标签（避免对数轴变形）
- 每个数据点都有圆点标记
- 图例位于**左上角**
- 无参考线

---

## 使用场景

用户提供以下格式数据时适用：

```python
# Type A（训练曲线）
steps = np.linspace(0, 20000, 200)
sdpo_mean = [...]   # len=200
sdpo_std  = [...]   # len=200

# Type B（scaling 曲线）
param_labels = ['0.6B', '1.7B', '4B', '8B']
sdpo_pts = [0.215, 0.333, 0.450, 0.490]
sdpo_std = [0.005, 0.006, 0.008, 0.006]
```
