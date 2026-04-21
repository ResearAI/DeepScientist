"""
Reproduce: image9.png — Broken-axis scatter plot (Meta-Harness style)
X-axis has a break between ~50k and 115k.
Uses two side-by-side axes with shared y-axis.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
from scipy.interpolate import make_interp_spline

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
    'text.usetex': False,
})

# ---- Synthetic data ----
rng = np.random.default_rng(42)

# Ours (Pareto) — red stars + dashed pink line
pareto_x = np.array([0, 5000, 20000, 30000, 35000, 40000, 45000, 48000, 50000])
pareto_y = np.array([40.3, 40.3, 40.7, 44.3, 45.0, 47.3, 48.3, 48.8, 49.1])

# Ours (non-Pareto) — scattered light-pink circles
np_x = rng.uniform(25000, 50000, 32)
np_y = 35 + 14 * (np_x - 25000) / 25000 + rng.normal(0, 1.8, 32)
np_y = np.clip(np_y, 34, 50)

# Few-shot — purple circles + straight line (polyline, not a spline)
few_x = np.array([4000, 8000, 15000, 25000, 38000, 48000])
few_y = np.array([32.5, 34.2, 34.0, 35.7, 40.5, 41.0])

# Zero-shot — single purple X at origin
zs_x, zs_y = 0, 27.0

# MCE — orange triangle (right panel)
mce_x, mce_y = 115000, 39.6

# ACE — blue diamond (right panel)
ace_x, ace_y = 200000, 41.0


# ---- Colors ----
C_PARETO   = '#E53935'   # bright red
C_NONPARETO= '#F4B8B8'   # very light pink
C_FEW      = '#6B4FA0'   # deep purple
C_FEW_LINE = '#B8A8D8'   # light purple line
C_MCE      = '#E69B00'   # orange
C_ACE      = '#2E86C1'   # blue
C_ZS       = '#5B2D8E'   # deep purple for zero-shot
C_DASH     = '#F0A0A0'   # pink dashed line

# ---- Layout: wide left panel (0-50k), narrow right panel (115k, 200k) ----
fig, (ax1, ax2) = plt.subplots(
    1, 2,
    figsize=(9.5, 5.5),
    gridspec_kw={'width_ratios': [5, 1.3], 'wspace': 0.05},
)
fig.subplots_adjust(left=0.09, right=0.97, top=0.93, bottom=0.13)

YLIM = (25, 51)

for ax in [ax1, ax2]:
    ax.set_ylim(*YLIM)

# ---- Left axis (ax1: 0 to 50k) ----
ax1.set_xlim(-3000, 53000)

# Few-shot spline curve; the source figure shows a smooth S-shaped trajectory
spl = make_interp_spline(few_x, few_y, k=3)
spl_x = np.linspace(few_x[0], few_x[-1], 300)
spl_y = spl(spl_x)
ax1.plot(spl_x, spl_y, color=C_FEW_LINE, lw=1.8, zorder=2)
ax1.scatter(few_x, few_y,
            marker='o', s=70, color=C_FEW,
            zorder=4, linewidths=0.8, edgecolors='black')

# Zero-shot X
ax1.scatter([zs_x], [zs_y], marker='X', s=120, color=C_ZS, zorder=5,
            linewidths=0.8, edgecolors='black')

# Non-Pareto circles (light pink, no edge outline)
ax1.scatter(np_x, np_y, marker='o', s=28, color=C_NONPARETO, alpha=0.85,
            zorder=3, linewidths=0)

# Pareto dashed line + stars
ax1.plot(pareto_x, pareto_y, color=C_DASH, lw=1.8, linestyle='--', zorder=3)
ax1.scatter(pareto_x, pareto_y,
            marker='*', s=200, color=C_PARETO,
            zorder=5, linewidths=0.8, edgecolors='black')

ax1.set_xlabel('Additional context (chars)', fontsize=13, fontweight='bold', labelpad=4)
ax1.set_ylabel('Test accuracy', fontsize=13, fontweight='bold')
ax1.set_xticks([0, 10000, 20000, 30000, 40000, 50000])
ax1.set_xticklabels(['0', '10k', '20k', '30k', '40k', '50k'], fontsize=10)
ax1.tick_params(labelsize=10)

# Spines: left and bottom only
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax1.spines['left'].set_linewidth(1.0)
ax1.spines['bottom'].set_linewidth(1.0)

# ---- Right axis (ax2: 115k and 200k) ----
ax2.set_xlim(95000, 220000)

ax2.scatter([mce_x], [mce_y], marker='^', s=130, color=C_MCE, zorder=5,
            linewidths=0.8, edgecolors='black')
ax2.scatter([ace_x], [ace_y], marker='D', s=90, color=C_ACE, zorder=5,
            linewidths=0.8, edgecolors='black')

ax2.set_xticks([115000, 200000])
ax2.set_xticklabels(['115k', '200k'], fontsize=10)
ax2.tick_params(labelsize=10)
ax2.set_yticks([])

# Spines: bottom only
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
ax2.spines['left'].set_visible(False)
ax2.spines['bottom'].set_linewidth(1.0)

# ---- Break marks on the bottom x-axis only ----
d = 0.015
kwargs = dict(transform=ax1.transAxes, color='k', clip_on=False, lw=1.2)
ax1.plot((1 - d, 1 + d), (-d, +d), **kwargs)   # bottom slash

kwargs2 = dict(transform=ax2.transAxes, color='k', clip_on=False, lw=1.2)
ax2.plot((-d, +d), (-d, +d), **kwargs2)         # bottom slash

# ---- Legend (lower-right, light gray frame) ----
legend_elements = [
    mlines.Line2D([], [], marker='*', color='w', markerfacecolor=C_PARETO,
                  markersize=11, label='Ours (Pareto)',
                  linestyle='--', linewidth=1.2,
                  markeredgewidth=0.3, markeredgecolor='white'),
    mlines.Line2D([], [], marker='o', color='w', markerfacecolor=C_NONPARETO,
                  markersize=7, label='Ours (non-Pareto)', linestyle='None'),
    mlines.Line2D([], [], marker='^', color='w', markerfacecolor=C_MCE,
                  markersize=9, label='MCE', linestyle='None'),
    mlines.Line2D([], [], marker='D', color='w', markerfacecolor=C_ACE,
                  markersize=8, label='ACE', linestyle='None'),
    mlines.Line2D([], [], marker='X', color='w', markerfacecolor=C_ZS,
                  markersize=9, label='Zero-shot', linestyle='None'),
    mlines.Line2D([], [], marker='o', color='w', markerfacecolor=C_FEW,
                  markersize=8, label='Few-shot', linestyle='None'),
]

leg = ax1.legend(
    handles=legend_elements,
    loc='lower right',
    fontsize=9.0,
    frameon=True,
    facecolor='white',
    edgecolor='#CCCCCC',
    framealpha=1.0,
    borderpad=0.5,
    labelspacing=0.3,
    handletextpad=0.4,
)

fig.savefig(
    '/Users/bytedance/gitcode/paper_experiment_plot_skills/repro/scatter_break_repro.png',
    dpi=300, facecolor='white',
)
plt.close(fig)
print('saved: scatter_break_repro.png')
