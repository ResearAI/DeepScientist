"""
Reproduce image2 and image3 from the self-distillation paper.
image2: continuous training curves with confidence-band shading and a horizontal reference line
image3: discrete scaling curves with confidence-band shading
Source: Reinforcement learning via self-distillation
"""

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

# ── Style summary ─────────────────────────────────────────
# Typeface: serif, close to LaTeX Computer Modern, with usetex enabled.
# Weighting: title normal, SDPO legend entry bold, others normal.
# Spines: keep only left and bottom.
# Grid: none.
# Colors: green for SDPO, blue for GRPO, gray for the base model.
# Band: semi-transparent fill with alpha around 0.15.
plt.rcParams.update({
    'text.usetex': True,
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman', 'STIX Two Text', 'DejaVu Serif'],
    'axes.unicode_minus': False,
})

C_SDPO  = '#2CA02C'   # matplotlib tab green
C_GRPO  = '#1F77B4'   # matplotlib tab blue
C_BASE  = '#BCBCBC'   # light gray for the base model

# ══════════════════════════════════════════════════════════
# Figure 2: continuous training curves (LiveCodeBench v6)
# ══════════════════════════════════════════════════════════
np.random.seed(42)

steps = np.linspace(0, 20000, 400)   # more points for smoother EMA output

def raw_curve(start, end, steps, noise=0.008):
    t = steps / steps[-1]
    curve = start + (end - start) * (1 - np.exp(-4 * t))
    curve += np.random.normal(0, noise, len(steps)) * (1 - t * 0.7)
    return curve

def ema(arr, alpha=0.96):
    """Exponential moving average used to mimic smoothed training logs."""
    out = np.zeros_like(arr)
    out[0] = arr[0]
    for i in range(1, len(arr)):
        out[i] = alpha * out[i - 1] + (1 - alpha) * arr[i]
    return out

# Generate noisy raw curves first, then smooth them with EMA
sdpo_mean = ema(raw_curve(0.285, 0.490, steps, noise=0.006))
sdpo_std  = 0.012 * np.exp(-2 * steps / steps[-1]) + 0.007
grpo_mean = ema(raw_curve(0.285, 0.415, steps, noise=0.006))
grpo_std  = 0.010 * np.exp(-2 * steps / steps[-1]) + 0.006

fig2, ax2 = plt.subplots(figsize=(6.5, 4.4))

ax2.fill_between(steps, sdpo_mean - sdpo_std, sdpo_mean + sdpo_std,
                 color=C_SDPO, alpha=0.20)
ax2.fill_between(steps, grpo_mean - grpo_std, grpo_mean + grpo_std,
                 color=C_GRPO, alpha=0.20)
ax2.plot(steps, sdpo_mean, color=C_SDPO, lw=2.5, label=r'\textbf{SDPO}')
ax2.plot(steps, grpo_mean, color=C_GRPO, lw=2.5, label='GRPO')
# The source figure uses a sparse dotted baseline line rather than a standard dash
ax2.axhline(0.406, color='#AAAAAA', lw=1.8,
            linestyle=(0, (1, 2)), label='Claude Sonnet 4')

ax2.set_xlim(0, 20000)
ax2.set_ylim(0.28, 0.52)
ax2.set_xlabel('Number of Generations', fontsize=13)
ax2.set_ylabel('Accuracy', fontsize=13)
ax2.set_title('LiveCodeBench v6', fontsize=15, pad=7)

ax2.xaxis.set_major_formatter(ticker.FuncFormatter(
    lambda x, _: f'{int(x/1000)}k' if x > 0 else '0'))
ax2.xaxis.set_major_locator(ticker.MultipleLocator(5000))
ax2.yaxis.set_major_locator(ticker.MultipleLocator(0.05))

leg2 = ax2.legend(fontsize=11, loc='lower right',
                  framealpha=0, edgecolor='none',
                  handlelength=2.2, borderaxespad=0.5, labelspacing=0.3)
for text in leg2.get_texts():
    if 'SDPO' in text.get_text():
        text.set_fontweight('bold')

# Four-sided frame with inward ticks, matching the source figure
for sp in ax2.spines.values():
    sp.set_visible(True)
    sp.set_linewidth(1.5)
ax2.tick_params(direction='in', length=5, width=1.2, labelsize=11)
ax2.grid(False)

fig2.tight_layout(pad=0.9)
fig2.savefig('/Users/bytedance/gitcode/paper_experiment_plot_skills/repro/line_selfdistill_v6_repro.png',
             dpi=300, facecolor='white')
plt.close(fig2)
print('saved: line_selfdistill_v6_repro.png')

# ══════════════════════════════════════════════════════════
# Figure 3: model scaling curves (Qwen3)
# ══════════════════════════════════════════════════════════
param_labels = ['0.6', '1.7', '4', '8']
param_x      = [0.6,   1.7,   4,   8]
x_pos        = [0, 1, 2, 3]   # evenly spaced manual positions for the x-axis labels

sdpo_pts = [0.215, 0.333, 0.450, 0.490]
grpo_pts = [0.212, 0.295, 0.400, 0.414]
base_pts = [0.095, 0.150, 0.233, 0.284]

sdpo_std3 = [0.005, 0.006, 0.008, 0.006]
grpo_std3 = [0.005, 0.006, 0.007, 0.006]

fig3, ax3 = plt.subplots(figsize=(10, 5))   # 2:1 aspect ratio, matching the source

ax3.fill_between(x_pos,
                 [v - s for v, s in zip(sdpo_pts, sdpo_std3)],
                 [v + s for v, s in zip(sdpo_pts, sdpo_std3)],
                 color=C_SDPO, alpha=0.18)
ax3.fill_between(x_pos,
                 [v - s for v, s in zip(grpo_pts, grpo_std3)],
                 [v + s for v, s in zip(grpo_pts, grpo_std3)],
                 color=C_GRPO, alpha=0.18)

MEC = 'black'   # the source figure uses black marker outlines
ax3.plot(x_pos, sdpo_pts, color=C_SDPO, lw=2.5,
         marker='o', ms=7, mfc=C_SDPO,
         markeredgecolor=MEC, markeredgewidth=1.0,
         label=r'\textbf{SDPO}')
ax3.plot(x_pos, grpo_pts, color=C_GRPO, lw=2.5,
         marker='o', ms=7, mfc=C_GRPO,
         markeredgecolor=MEC, markeredgewidth=1.0,
         label='GRPO')
ax3.plot(x_pos, base_pts, color=C_BASE, lw=2.5,   # keep the base line as thick as the others
         marker='o', ms=7, mfc=C_BASE,
         markeredgecolor=MEC, markeredgewidth=1.0,
         label='base model')

ax3.set_xticks(x_pos)
ax3.set_xticklabels(param_labels, fontsize=11)
ax3.set_xlim(-0.35, 3.35)
ax3.set_ylim(0.08, 0.51)   # align with the source 0.1-0.5 tick range
ax3.set_xlabel('Model parameters (B)', fontsize=13)
ax3.set_ylabel(r'\textit{Accuracy}', fontsize=13)
ax3.set_title('Model scaling (Qwen3)', fontsize=15, pad=7)
ax3.yaxis.set_major_locator(ticker.MultipleLocator(0.1))

# Move the legend to the lower-right, matching the source placement
leg3 = ax3.legend(fontsize=11, loc='lower right',
                  bbox_to_anchor=(0.98, 0.02),
                  framealpha=0, edgecolor='none',
                  handlelength=2.2, borderaxespad=0.5, labelspacing=0.3)
for text in leg3.get_texts():
    if 'SDPO' in text.get_text():
        text.set_fontweight('bold')

# Four-sided frame + inward ticks
for sp in ax3.spines.values():
    sp.set_visible(True)
    sp.set_linewidth(1.5)
ax3.tick_params(direction='in', length=5, width=1.2, labelsize=11)
ax3.grid(False)

fig3.tight_layout(pad=0.9)
fig3.savefig('/Users/bytedance/gitcode/paper_experiment_plot_skills/repro/line_selfdistill_scaling_repro.png',
             dpi=300, facecolor='white')
plt.close(fig3)
print('saved: line_selfdistill_scaling_repro.png')
