"""
Reproduce: image8.png — DoRA vs LoRA Radar Chart
Style: sans-serif, dashed octagonal grid, white-bg value annotations,
       semi-transparent fill, legend: black text + colored line segment.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
    'text.usetex': False,
})

# ---- Data (clockwise, starting from the top) ----
CATEGORIES = [
    'CommonSense\n(LLaMA)',
    'MT-bench\n(LLaMA2)',
    'MT-bench\n(LLaMA)',
    'visual instruction\ntuning (LLaVA-1.5)',
    'video-text\n(VL-BART)',
    'image-text\n(VL-BART)',
    'CommonSense\n(LLaMA3)',
    'CommonSense\n(LLaMA2)',
]

DORA_raw = np.array([78.40, 6.00, 5.50, 67.60, 85.40, 77.40, 85.20, 79.70])
LORA_raw = np.array([76.30, 5.70, 5.10, 66.90, 83.50, 76.50, 80.80, 77.60])

N = len(CATEGORIES)

RANGES = [
    (74.0, 80.0),
    (5.4,  6.2),
    (4.8,  5.7),
    (65.0, 70.0),
    (81.0, 87.0),
    (74.0, 79.0),
    (78.0, 87.0),
    (75.0, 81.0),
]
RMIN, RMAX = 0.35, 1.0

def nrm(v, vmin, vmax):
    return RMIN + (RMAX - RMIN) * (v - vmin) / (vmax - vmin)

dora_r = np.array([nrm(v, r[0], r[1]) for v, r in zip(DORA_raw, RANGES)])
lora_r = np.array([nrm(v, r[0], r[1]) for v, r in zip(LORA_raw, RANGES)])

angles = np.linspace(0, 2 * np.pi, N, endpoint=False)

def close(arr):
    return np.concatenate([arr, [arr[0]]])

# Source image size is about 1032×850, so the aspect ratio is roughly 1.21
fig, ax = plt.subplots(figsize=(7.0, 5.8),
                       subplot_kw=dict(projection='polar'))

ax.set_theta_zero_location('N')
ax.set_theta_direction(-1)
ax.set_yticks([])
ax.set_xticks([])

# ---- Concentric octagonal dashed grids, not circular grids ----
for r in [0.4, 0.55, 0.7, 0.85, 1.0]:
    ax.plot(close(angles), close(np.full(N, r)),
            color='#CCCCCC', lw=0.8, linestyle='--', zorder=1)

# Radial guide lines
for ang in angles:
    ax.plot([ang, ang], [0, 1.0],
            color='#CCCCCC', lw=0.8, linestyle='--', zorder=1)

C_DORA = '#5A8A5A'   # deep green, close to the source figure
C_LORA = '#4169E1'   # royal blue, matching the LoRA line

# ---- Filled regions with a shared opacity ----
ax.fill(close(angles), close(dora_r), color=C_DORA, alpha=0.18, zorder=3)
ax.fill(close(angles), close(lora_r), color=C_LORA, alpha=0.18, zorder=3)

# ---- Lines (DoRA visibly thicker than LoRA) ----
ax.plot(close(angles), close(dora_r),
        color=C_DORA, lw=3.0, solid_capstyle='round', zorder=4)
ax.plot(close(angles), close(lora_r),
        color=C_LORA, lw=1.5, solid_capstyle='round', zorder=4)

# ---- Numeric labels with white boxes for readability ----
def fmt(v):
    # The source figure keeps two decimals
    return f'{v:.2f}'

for i, ang in enumerate(angles):
    # DoRA values outside the polygon
    r_d = dora_r[i] + 0.08
    ax.text(ang, r_d, fmt(DORA_raw[i]),
            ha='center', va='center',
            fontsize=7.8, color=C_DORA, zorder=6,
            bbox=dict(boxstyle='round,pad=0.12',
                      facecolor='white', edgecolor='none', alpha=0.85))
    # LoRA values inside the polygon
    r_l = lora_r[i] - 0.09
    ax.text(ang, r_l, fmt(LORA_raw[i]),
            ha='center', va='center',
            fontsize=7.8, color=C_LORA, zorder=6,
            bbox=dict(boxstyle='round,pad=0.12',
                      facecolor='white', edgecolor='none', alpha=0.85))

# ---- Axis labels ----
# In the source figure the labels sit close to the outer polygon ring
label_r = 1.13
for i, (ang, cat) in enumerate(zip(angles, CATEGORIES)):
    if abs(np.sin(ang)) < 0.15:
        ha = 'center'
    elif np.sin(ang) > 0:
        ha = 'left'
    else:
        ha = 'right'
    ax.text(ang, label_r, cat,
            ha=ha, va='center',
            fontsize=8.5, color='#333333',
            multialignment='center')

# ---- Legend: black series names plus colored line samples ----
# DoRA legend row (thicker green line + bold black text)
fig.text(0.09, 0.91,
         '────  ', color=C_DORA, fontsize=11,
         fontweight='bold', va='center', ha='left')
fig.text(0.155, 0.91,
         'DoRA', color='black', fontsize=10,
         fontweight='bold', va='center', ha='left')

# LoRA legend row (thinner blue line + regular black text)
fig.text(0.09, 0.875,
         '─────', color=C_LORA, fontsize=8.5,
         va='center', ha='left')
fig.text(0.155, 0.875,
         'LoRA', color='black', fontsize=10,
         va='center', ha='left')

ax.set_ylim(0, 1.32)   # reduce top and bottom whitespace so the polygon fills more of the canvas
ax.set_frame_on(False)

fig.subplots_adjust(left=0.10, right=0.90, top=0.86, bottom=0.06)
fig.savefig(
    '/Users/bytedance/gitcode/paper_experiment_plot_skills/repro/radar_dora_repro.png',
    dpi=300, facecolor='white',
)
plt.close(fig)
print('saved: radar_dora_repro.png')
