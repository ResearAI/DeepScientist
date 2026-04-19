# Style: bar_grouped_hatch（分组柱 + 斜线填充主方法）

**来源论文**：SPICE: Self-play in corpus environments improves reasoning  
**图表类型**：分组柱状图（每组 3 柱，主方法使用斜线填充强调）  
**复现代码**：`repro/bar_spice.py`  
**原图**：`image5.png`

---

## 视觉特征描述

- **颜色（消融图）**：浅橙 `#FFB695` / 中橙 `#FF7F5E` / 正红 `#D00000`，暖色渐进
- **颜色（对比图）**：浅灰 `#D3D3D3` / 中灰 `#A9A9A9` / 正红 `#D00000`；注意中灰不能太深（`#707070` 过深，与原图灰阶不符）
- **填充**：主方法使用 `//` 斜线，**白色斜线刻在深红底上**（`hatch.color='white'`）
- **所有柱** `edgecolor='white'` 统一，保持柱间白缝对称；hatch 颜色通过 `rcParams['hatch.color']` 独立设置为 `white`
- **Spine**：只保留左/下两条（开口式坐标轴），上/右隐藏；线色 `#333333`，线宽 0.9
- **Grid**：仅 y 轴，极浅灰 `#EBEBEB`，虚线 `--`，线宽 0.7
- **数值标注**：每柱顶部显示数值，主方法加粗 + 深红色，其他方法普通黑色
- **网格**：仅 y 轴浅灰水平线 `#DDDDDD`，zorder 置底
- **边框**：四边框均保留，颜色偏灰 `#7A7A7A`，线宽 0.8，边框层级高于柱体
- **图例**：右上角，带边框，色块 + 斜线样式与柱一致
- **整体风格**：学术简洁，主方法突出，适合消融对比和多方法比较

---

## 关键参数

```python
# 消融图颜色
COLORS_ABL  = ['#F5C5A3', '#E8845A', '#C0392B']
# 对比图颜色
COLORS_CMP  = ['#C8C8C8', '#707070', '#C0392B']

HATCHES     = ['', '', '//']          # 只有主方法有斜线，// 比 //// 稀疏，更接近原图
BEST_METHOD = 'SPICE'                 # 该方法的数值标注加粗+红色

bar_total_width = 0.78                # 一组内所有柱总宽（约占组宽 78%）
grid = 'y-only'                       # 仅 y 轴网格
spine_all_visible = True              # 四边框都显示
ymax = 85                             # 不让柱子顶得过高
x_positions = [0.00, 1.23, 2.46, 3.69]
xlim = (-0.52, 4.18)                 # 留出与原图接近的左右边距
legend_bbox = (0.992, 0.986)         # 图例框贴近右上角，但不压边
```

## 字体 & 加粗规范

| 元素 | 字体族 | 字号 | 加粗 |
|------|--------|------|------|
| 面板标题（"(a) SPICE Ablations"） | LaTeX serif（Computer Modern 风格） | 13.2 | **否**（正常细体）|
| 图例文字（非主方法） | LaTeX serif（Computer Modern 风格） | 9.2 | 否 |
| 图例文字（主方法 "SPICE"） | LaTeX serif（Computer Modern 风格） | 9.2 | **是** |
| 柱顶数值（非主方法） | LaTeX serif（Computer Modern 风格） | 8.7 | 否，黑色 |
| 柱顶数值（主方法） | LaTeX serif（Computer Modern 风格） | 8.7 | **是**，深红色 `#8B0000` |
| 轴标签 / 刻度 | LaTeX serif（Computer Modern 风格） | 10.8-11.2 | 否 |

```python
plt.rcParams.update({
    'text.usetex': True,
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman', 'STIX Two Text', 'DejaVu Serif'],
    'axes.unicode_minus': False,
})

# 图例中单独加粗主方法文字
leg = ax.legend(...)
for text in leg.get_texts():
    if text.get_text() == BEST_METHOD:
        text.set_fontweight('bold')
```

---

## 使用场景

适用于以下结构的数据：

```
- 若干 benchmark（x 轴）
- 每个 benchmark 有 N 个方法的对比值（N 通常 2-4）
- 有一个主方法需要视觉突出
- 两个子图：一个消融、一个与 baseline 对比
```

**用法示例（告诉 agent 数据格式）**：

```python
benchmarks = ['MATH500', "AIME'25", 'GPQA-Diamond', 'MMLU-Pro']
data = {
    'Method A': [68.2,  6.7, 26.3, 51.6],
    'Method B': [72.6, 12.3, 31.8, 53.7],
    'SPICE':    [78.0, 19.1, 39.4, 58.1],   # 主方法，自动加粗+斜线
}
best_method = 'SPICE'
title = '(a) SPICE Ablations'
ylabel = 'Accuracy (%)'
xlabel = 'Benchmark'
```

---

## 变体建议

- 单子图版本：直接用 `draw_panel` 函数，传入单组数据
- 超过 3 个方法时：适当减小 `bar_total_width` 避免柱子过细
- 主方法不在最后一列时：调整 `offset` 计算顺序即可
- 图例位置不要只用 `loc='upper right'` 粗放控制，优先用 `bbox_to_anchor` 做像素级微调
- 左右子图可以分别设置 `xlim / x_positions / legend_bbox`，不要强行共用一套参数
