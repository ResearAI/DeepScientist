"""
Reproduce image1: a MemEvolve-style paired bar chart.
Features: paired bars (baseline vs. method), arrows, red percentage gain labels,
and a dashed horizontal reference line.
Source: MemEvolve: Meta-Evolution of Agent Memory Systems
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
import numpy as np

# ── Style summary ─────────────────────────────────────────
# Typeface: serif, close to a Computer Modern look.
# Weighting: title bold, delta labels bold, axis labels and ticks normal.
# Spacing: the two bars are almost touching, with a very small gap.
# Output target: 300 dpi.
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['STIXGeneral', 'DejaVu Serif', 'Times New Roman'],
    'mathtext.fontset': 'stix',
})

# ── Color system ─────────────────────────────────────────
COLOR_BASELINE = '#A8C8E8'   # light steel blue for baseline bars
COLOR_METHOD   = '#1B3D6E'   # deep navy for method bars
COLOR_DELTA    = '#CC2200'   # red for gain annotations

# ── Data ─────────────────────────────────────────────────
panels = [
    {
        'title': 'OWL-Workforce',   # plain-text title; no emoji-dependent glyphs
        'groups': ['Web', 'xBench', 'TaskCraft', 'GAIA'],
        'baseline': [58.1, 55.2, 58.7, 59.3],
        'method':   [62.3, 61.2, 65.5, 61.0],
        'delta':    ['+7.1%', '+10.9%', '+11.9%', '+2.7%'],
        'ylim':     (40, 71),   # left panel y-range matching the source figure
    },
    {
        'title': 'CK-Pro',
        'groups': ['Web', 'xBench', 'TaskCraft', 'GAIA'],
        'baseline': [61.2, 55.8, 63.8, 58.1],
        'method':   [63.8, 64.8, 67.8, 63.1],
        'delta':    ['+4.2%', '+16.1%', '+4.8%', '+8.4%'],
        'ylim':     (40, 76),   # right panel y-range matching the source figure
    },
]

# ── Canvas ───────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), sharey=False)
fig.subplots_adjust(wspace=0.35)

BAR_W    = 0.28
GAP      = 0.01      # the bars are nearly touching in the source figure
ARROW_KW = dict(arrowstyle='->', color='black', lw=1.2)

for ax, panel in zip(axes, panels):
    groups   = panel['groups']
    baseline = np.array(panel['baseline'])
    method   = np.array(panel['method'])
    delta    = panel['delta']
    n        = len(groups)
    x        = np.arange(n)

    # Bars
    bars_b = ax.bar(x - (BAR_W + GAP) / 2, baseline, width=BAR_W,
                    color=COLOR_BASELINE, zorder=3)
    bars_m = ax.bar(x + (BAR_W + GAP) / 2, method,   width=BAR_W,
                    color=COLOR_METHOD,   zorder=3)

    # Dashed reference line at the baseline height
    for i, (bl, me) in enumerate(zip(baseline, method)):
        # Horizontal dashed guide from the baseline bar top to the method bar top
        ax.plot([x[i] - BAR_W, x[i] + BAR_W + GAP / 2],
                [bl, bl], color='black', lw=0.9, ls='--', zorder=4)

        # Arrow from the baseline top to the method top
        ax.annotate('', xy=(x[i] + (BAR_W + GAP) / 2, me - 0.3),
                    xytext=(x[i] + (BAR_W + GAP) / 2, bl + 0.3),
                    arrowprops=ARROW_KW, zorder=5)

        # Red percentage gain label
        ax.text(x[i] + (BAR_W + GAP) / 2, me + 0.6,
                delta[i], color=COLOR_DELTA,
                ha='center', va='bottom', fontsize=9.5, fontweight='bold')

    # Axis styling: the source figure uses clearly bold labels
    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=10.5, fontweight='bold')
    ax.set_ylabel('Accuracy (Pass@1)', fontsize=10.5, fontweight='bold')
    ax.set_ylim(*panel['ylim'])
    ax.yaxis.set_major_locator(plt.MultipleLocator(5))

    # All four spines stay visible with a slightly heavier frame
    for spine in ax.spines.values():
        spine.set_linewidth(1.5)
        spine.set_color('black')
    ax.tick_params(length=0)
    ax.set_axisbelow(True)

    # Upper-left title in bold serif and dark blue
    ax.text(0.04, 0.97, panel['title'], transform=ax.transAxes,
            fontsize=12, fontweight='bold', va='top', ha='left',
            color='#003F6C', fontfamily='serif')

plt.savefig('/Users/bytedance/gitcode/paper_experiment_plot_skills/repro/bar_memevolve_repro.png',
            dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print('saved: bar_memevolve_repro.png')
