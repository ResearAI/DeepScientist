"""
Reproduce image5: a SPICE-style grouped bar chart.
Features: grouped bars, hatched primary method, top value labels with a bold
highlight for the best method, and a subtle gray grid.
Source: SPICE: Self-play in corpus environments improves reasoning
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Style summary ─────────────────────────────────────────
# Typeface: closer to LaTeX / Computer Modern than to Times,
# so the template enables usetex.
# Weighting: panel titles normal, SPICE legend entry bold,
# primary values bold and dark red, other values normal black.
# Layout: slim three-bar groups with clear whitespace between groups.
# Border: all spines remain visible and should stay visually above the bars.
# Output target: 300 dpi.
plt.rcParams.update({
    'text.usetex': True,
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman', 'STIX Two Text', 'DejaVu Serif'],
    'axes.unicode_minus': False,
    'hatch.color': 'white',     # white hatch strokes over a red fill
    'hatch.linewidth': 1.4,
})

# ── Colors & hatch settings ──────────────────────────────
# Left panel (ablation)
COLORS_ABL   = ['#FFB695', '#FF7F5E', '#D00000']   # light orange / mid orange / deep red
HATCHES_ABL  = ['', '', '//']
LABELS_ABL   = ['SPICE (Fixed Challenger)', 'SPICE (No Corpus)', 'SPICE']

# Right panel (comparison)
COLORS_CMP   = ['#D3D3D3', '#A9A9A9', '#D00000']   # light gray / mid gray / deep red
HATCHES_CMP  = ['', '', '//']
LABELS_CMP   = ['R-Zero', 'Absolute Zero', 'SPICE']

# ── Data ─────────────────────────────────────────────────
benchmarks = ['MATH500', "AIME'25", 'GPQA-Diamond', 'MMLU-Pro']

data_abl = {
    'SPICE (Fixed Challenger)': [68.2,  6.7, 26.3, 51.6],
    'SPICE (No Corpus)':        [72.6, 12.3, 31.8, 53.7],
    'SPICE':                    [78.0, 19.1, 39.4, 58.1],
}
data_cmp = {
    'R-Zero':        [72.6,  5.2, 27.8, 53.7],
    'Absolute Zero': [76.2, 13.4, 35.3, 52.6],
    'SPICE':         [78.0, 19.1, 39.4, 58.1],
}

BEST_METHOD = 'SPICE'   # render this method's value labels in bold


def draw_panel(
    ax,
    data_dict,
    colors,
    hatches,
    labels,
    title,
    x_positions,
    total_w,
    xlim,
    legend_anchor,
):
    n_groups  = len(benchmarks)
    n_methods = len(labels)
    x         = np.array(x_positions)
    bar_w     = total_w / n_methods

    for i, (label, color, hatch) in enumerate(zip(labels, colors, hatches)):
        vals   = data_dict[label]
        offset = (i - n_methods / 2 + 0.5) * bar_w
        bars   = ax.bar(x + offset, vals, width=bar_w,
                        color=color, hatch=hatch,
                        edgecolor='white',
                        linewidth=0.8, zorder=2, label=label)

        is_best = (label == BEST_METHOD)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2,
                    v + 0.5, f'{v}',
                    ha='center', va='bottom',
                    fontsize=8.7,
                    fontweight='bold' if is_best else 'normal',
                    color='black',   # keep values black; emphasis comes from font weight
                    zorder=3)

    # Axes
    ax.set_xticks(x)
    ax.set_xticklabels(benchmarks, fontsize=10.8)
    ax.set_xlabel('Benchmark', fontsize=11.2)
    ax.set_ylabel(r'Accuracy (\%)', fontsize=11.2)
    ax.set_ylim(0, 85)
    ax.set_xlim(*xlim)
    ax.set_title(title, fontsize=13.2, pad=5)

    # Grid (y-only, very light gray)
    ax.yaxis.grid(True, color='#EBEBEB', linewidth=0.7, linestyle='--', zorder=0)
    ax.set_axisbelow(True)

    # Open-axis look: keep only the left and bottom spines
    for side, spine in ax.spines.items():
        if side in ('top', 'right'):
            spine.set_visible(False)
        else:
            spine.set_linewidth(0.9)
            spine.set_color('#333333')
            spine.set_zorder(4)

    ax.tick_params(length=0, labelsize=10.2)

    # Legend
    handles = [mpatches.Patch(facecolor=c, hatch=h,
                               edgecolor='white', linewidth=0.8,
                               label=l)
               for l, c, h in zip(labels, colors, hatches)]
    leg = ax.legend(handles=handles, fontsize=8.9, loc='upper right',
                    bbox_to_anchor=legend_anchor,
                    framealpha=1.0, facecolor='white',
                    edgecolor='#C8C8C8', fancybox=False,
                    borderpad=0.28, labelspacing=0.26,
                    handlelength=1.7, handletextpad=0.45,
                    borderaxespad=0.28)
    # Only the primary method gets a bold legend label
    for text in leg.get_texts():
        if text.get_text() == BEST_METHOD:
            text.set_fontweight('bold')


# ── Canvas ───────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.8, 4.35))
fig.subplots_adjust(left=0.05, right=0.985, bottom=0.15, top=0.86, wspace=0.16)

draw_panel(
    ax1,
    data_abl,
    COLORS_ABL,
    HATCHES_ABL,
    LABELS_ABL,
    '(a) SPICE Ablations',
    x_positions=[0.00, 1.00, 2.00, 3.00],
    total_w=0.78,
    xlim=(-0.56, 3.56),
    legend_anchor=(0.992, 0.986),
)
draw_panel(
    ax2,
    data_cmp,
    COLORS_CMP,
    HATCHES_CMP,
    LABELS_CMP,
    '(b) SPICE vs Baselines',
    x_positions=[0.00, 1.00, 2.00, 3.00],
    total_w=0.78,
    xlim=(-0.56, 3.56),
    legend_anchor=(0.992, 0.986),
)

plt.savefig('/Users/bytedance/gitcode/paper_experiment_plot_skills/repro/bar_spice_repro.png',
            dpi=300, facecolor='white')
plt.close()
print('saved: bar_spice_repro.png')
