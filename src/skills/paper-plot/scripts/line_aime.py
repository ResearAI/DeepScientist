"""
Reproduce: image6.png — AIME avg@32 training curve
Two lines with vertical breakpoint markers + horizontal reference line.
Style: sans-serif, 4-spine box, no grid, right-bottom legend.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
    'text.usetex': False,
})

rng = np.random.default_rng(42)

# ---- Synthetic data ----
# w/ Dynamic Sampling (purple): 0-2200 steps, rises fast, ends ~0.42
steps_dyn_a = np.arange(0, 2300, 50)
y_dyn_a = 0.43 * (1 - np.exp(-steps_dyn_a / 600))
y_dyn_a += rng.normal(0, 0.012, len(steps_dyn_a))
y_dyn_a = np.clip(y_dyn_a, 0, 0.45)
y_dyn_a[:2] = [0.03, 0.03]   # cold start

# w/o Dynamic Sampling (cyan): 0-9000, slower rise, peaks ~0.42 at step 6000, then drops
steps_nodyn = np.arange(0, 9100, 100)
y_nodyn = 0.38 * (1 - np.exp(-steps_nodyn / 1200))
y_nodyn += rng.normal(0, 0.012, len(steps_nodyn))
y_nodyn = np.clip(y_nodyn, 0, 0.44)
y_nodyn[:2] = [0.01, 0.02]
# After step 6000, add gradual decline
mask = steps_nodyn > 6000
y_nodyn[mask] -= 0.06 * (steps_nodyn[mask] - 6000) / 3000

C_DYN   = '#5B0DAD'   # deeper purple, closer to the source figure
C_NODYN = '#5BBCCA'   # soft teal
C_REF   = '#3D78C2'   # separate blue for the horizontal reference line
STEP_DYN  = 2200      # purple vertical marker
STEP_NODYN = 6050     # teal vertical marker
REF_Y = 0.43          # horizontal reference line

fig, ax = plt.subplots(figsize=(9.0, 4.8))

# ---- Main curves ----
ax.plot(steps_dyn_a, y_dyn_a, color=C_DYN, lw=1.4, zorder=3, label='w/ Dynamic Sampling')
ax.plot(steps_nodyn, y_nodyn, color=C_NODYN, lw=1.4, zorder=3, label='w/o Dynamic Sampling')

# ---- Horizontal reference line ----
ax.axhline(REF_Y, color=C_REF, lw=1.5, linestyle='--', zorder=2)

# ---- Vertical dashed markers ----
ax.axvline(STEP_DYN, color=C_DYN, lw=1.5, linestyle='--', alpha=0.85, zorder=2)
ax.axvline(STEP_NODYN, color=C_NODYN, lw=1.5, linestyle='--', alpha=0.85, zorder=2)

# ---- Axes styling ----
ax.set_xlim(-100, 9200)
ax.set_ylim(-0.01, 0.47)
ax.set_xticks([0, 2000, 4000, 6000, 8000])
ax.set_xticklabels(['0', '2000', '4000', '6000', '8000'], fontsize=10)
ax.set_yticks([0.0, 0.1, 0.2, 0.3, 0.4])
ax.tick_params(labelsize=10, direction='out', length=4, width=0.8)
ax.set_xlabel('Step', fontsize=12)
ax.set_ylabel('AIME avg@32', fontsize=12)

# Full box frame (all spines visible)
for sp in ax.spines.values():
    sp.set_visible(True)
    sp.set_linewidth(1.0)

ax.grid(False)

# ---- Legend ----
leg = ax.legend(
    loc='lower right',
    fontsize=9.5,
    frameon=True,
    facecolor='white',
    edgecolor='#AAAAAA',
    framealpha=1.0,
    borderpad=0.5,
    labelspacing=0.3,
    handlelength=2.0,
    handletextpad=0.5,
)

fig.tight_layout(pad=0.8)
fig.savefig(
    '/Users/bytedance/gitcode/paper_experiment_plot_skills/repro/line_aime_repro.png',
    dpi=300, facecolor='white',
)
plt.close(fig)
print('saved: line_aime_repro.png')
