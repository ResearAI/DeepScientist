# Style: bar_paired_delta（配对对比柱 + 增益标注）

**来源论文**：MemEvolve: Meta-Evolution of Agent Memory Systems  
**图表类型**：分组柱状图（每组 2 柱：baseline vs method）  
**复现代码**：`repro/bar_memevolve.py`  
**原图**：`image1.png`

---

## 视觉特征描述

- **颜色**：浅钢蓝 `#A8C8E8`（baseline）+ 深海军蓝 `#1B3D6E`（method），强冷色对比
- **增益标注**：红色 `#CC2200` 粗体百分比，显示在 method 柱顶上方
- **箭头**：从 baseline 柱顶垂直指向 method 柱顶，使用实心箭头
- **参考线**：baseline 高度处一条黑色水平虚线，横跨两柱
- **网格**：无网格
- **边框**：四边实线，线宽 1.4，略粗
- **轴标签**：底部 x 轴标签，无刻度线
- **标题**：位于左上角 axes 内部，带 emoji icon + 粗体名称
- **整体风格**：干净、强调对比，适合展示方法相对 baseline 的绝对增益

---

## 关键参数

```python
COLOR_BASELINE = '#A8C8E8'
COLOR_METHOD   = '#1B3D6E'
COLOR_DELTA    = '#CC2200'

BAR_W   = 0.32
GAP     = 0.08          # 两柱间距
spine_linewidth = 1.4
grid    = False
title_position = 'upper left inside axes'
```

## 字体 & 加粗规范

| 元素 | 字体族 | 字号 | 加粗 |
|------|--------|------|------|
| 子图标题（"OWL-Workforce"） | serif（Palatino / Times） | 11.5 | **是** |
| 红色增益标注（"+7.1%"） | serif（继承全局） | 9.5 | **是** |
| Y 轴标签（"Accuracy (Pass@1)"） | serif（继承全局） | 10 | 否 |
| X 轴刻度标签 | serif（继承全局） | 10 | 否 |
| Y 轴刻度数字 | serif（继承全局） | 默认 | 否 |

```python
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Palatino', 'Times New Roman', 'DejaVu Serif'],
})
```

> 注意：原图标题中使用了 emoji icon（🦉🔷），matplotlib serif 字体不含 emoji 字形，会显示为小方框。可用文字替代，或用 `AnnotationBbox` 贴图标图片解决。

---

## 使用场景

用户有以下数据时适用：

```
- 若干 group（x 轴分类）
- 每个 group 有 baseline 和 method 两个值
- 需要突出显示每组的相对提升百分比
```

**用法示例（告诉 agent 数据格式）**：

```python
groups   = ['Web', 'xBench', 'TaskCraft', 'GAIA']
baseline = [58.1, 55.2, 58.7, 59.3]
method   = [62.3, 61.2, 65.5, 61.0]
delta    = ['+7.1%', '+10.9%', '+11.9%', '+2.7%']
title    = 'OWL-Workforce'
ylabel   = 'Accuracy (Pass@1)'
```

---

## 已知限制

- 原图标题中使用了 emoji（🦉🔷），但 matplotlib 默认字体不支持 emoji 渲染，实际输出会显示为空框。可用文字替代，或使用 `matplotlib.image` 贴图标 icon。
- 该风格适合值域差距在 2%-20% 之间的场景，差距过大时箭头比例会不协调。
