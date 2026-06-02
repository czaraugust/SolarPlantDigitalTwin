"""
Publication-quality condensed chart — v2
More distinct colors, ILR up to 1.8, inset zoom to amplify differences
"""
import sys
import os
# Adiciona a raiz do projeto ao Python path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from mpl_toolkits.axes_grid1.inset_locator import inset_axes, mark_inset

from core.config import RESULTS_DIR, PLOTS_DIR

plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'legend.fontsize': 9,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'figure.dpi': 300,
})

df = pd.read_csv(os.path.join(RESULTS_DIR, 'resultado_tilt_orientacao_oversizing.csv'))
P_NOMINAL = 5.0
df['ilr'] = df['p_kwp'] / P_NOMINAL

TILTS = [5, 10, 15]
TILT_LABELS = {5: '5°', 10: '10°', 15: '15°'}
TILT_STYLES = {5: '-', 10: '--', 15: ':'}
TILT_LW = {5: 2.0, 10: 2.2, 15: 2.5}

AZIMUTHS = [0, 90, 180, 270]
AZ_LABELS = {0: 'North', 90: 'East', 180: 'South', 270: 'West'}
AZ_COLORS = {0: '#0D47A1', 90: '#FF6F00', 180: '#1B5E20', 270: '#B71C1C'}
AZ_MARKERS = {0: 'o', 90: 's', 180: '^', 270: 'D'}

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

# Filter ILR <= 1.8
mask = df['ilr'] <= 1.85

# ===================== PANEL (a): Energy Delivered =====================
for tilt in TILTS:
    for az in AZIMUTHS:
        d = df[(df['tilt'] == tilt) & (df['azimute'] == az) & mask].sort_values('ilr')
        ax1.plot(d['ilr'], d['energy_entregue'],
                 linestyle=TILT_STYLES[tilt], color=AZ_COLORS[az],
                 linewidth=TILT_LW[tilt], markersize=4.5, marker=AZ_MARKERS[az],
                 markevery=2, alpha=0.9)

ax1.set_xlabel('Inverter Loading Ratio (ILR)')
ax1.set_ylabel('Energy Delivered (kWh)')
ax1.set_title('(a) Energy Delivered vs ILR')
ax1.grid(True, linestyle='--', alpha=0.3)
ax1.set_xlim(0.95, 1.82)
ax1.axhline(y=400, color='gray', linewidth=0.8, linestyle='-.', alpha=0.5)
ax1.text(0.97, 403, '400 kWh', fontsize=8, color='gray')

# INSET ZOOM on ax1 — high ILR region where curves diverge
ax1_ins = inset_axes(ax1, width="45%", height="45%", loc='lower right',
                     bbox_to_anchor=(0, 0.08, 1, 1), bbox_transform=ax1.transAxes)
for tilt in TILTS:
    for az in AZIMUTHS:
        d = df[(df['tilt'] == tilt) & (df['azimute'] == az) & mask].sort_values('ilr')
        ax1_ins.plot(d['ilr'], d['energy_entregue'],
                     linestyle=TILT_STYLES[tilt], color=AZ_COLORS[az],
                     linewidth=TILT_LW[tilt], markersize=3, marker=AZ_MARKERS[az],
                     markevery=1, alpha=0.9)
ax1_ins.set_xlim(1.55, 1.82)
ax1_ins.set_ylim(600, 660)
ax1_ins.grid(True, linestyle='--', alpha=0.2)
ax1_ins.tick_params(labelsize=7)
ax1_ins.set_title('Zoom: ILR 1.55–1.80', fontsize=8)
mark_inset(ax1, ax1_ins, loc1=2, loc2=4, fc="none", ec="0.5", linestyle='--', alpha=0.4)

# ===================== PANEL (b): Clipping Losses =====================
for tilt in TILTS:
    for az in AZIMUTHS:
        d = df[(df['tilt'] == tilt) & (df['azimute'] == az) & mask].sort_values('ilr')
        ax2.plot(d['ilr'], d['clip_pct'],
                 linestyle=TILT_STYLES[tilt], color=AZ_COLORS[az],
                 linewidth=TILT_LW[tilt], markersize=4.5, marker=AZ_MARKERS[az],
                 markevery=2, alpha=0.9)

ax2.set_xlabel('Inverter Loading Ratio (ILR)')
ax2.set_ylabel('Clipping Losses (%)')
ax2.set_title('(b) Clipping Losses vs ILR')
ax2.grid(True, linestyle='--', alpha=0.3)
ax2.set_xlim(0.95, 1.82)
ax2.axhline(y=5, color='gray', linewidth=0.8, linestyle='-.', alpha=0.5)
ax2.text(0.97, 5.5, '5% threshold', fontsize=8, color='gray')

# INSET ZOOM on ax2 — high ILR
ax2_ins = inset_axes(ax2, width="45%", height="45%", loc='upper left',
                     bbox_to_anchor=(0.05, 0, 1, 0.95), bbox_transform=ax2.transAxes)
for tilt in TILTS:
    for az in AZIMUTHS:
        d = df[(df['tilt'] == tilt) & (df['azimute'] == az) & mask].sort_values('ilr')
        ax2_ins.plot(d['ilr'], d['clip_pct'],
                     linestyle=TILT_STYLES[tilt], color=AZ_COLORS[az],
                     linewidth=TILT_LW[tilt], markersize=3, marker=AZ_MARKERS[az],
                     markevery=1, alpha=0.9)
ax2_ins.set_xlim(1.55, 1.82)
ax2_ins.set_ylim(13, 20)
ax2_ins.grid(True, linestyle='--', alpha=0.2)
ax2_ins.tick_params(labelsize=7)
ax2_ins.set_title('Zoom: ILR 1.55–1.80', fontsize=8)
mark_inset(ax2, ax2_ins, loc1=1, loc2=3, fc="none", ec="0.5", linestyle='--', alpha=0.4)

# ===================== LEGEND =====================
az_handles = [mlines.Line2D([], [], color=AZ_COLORS[az], marker=AZ_MARKERS[az],
              linestyle='-', linewidth=2, markersize=6, label=AZ_LABELS[az])
              for az in AZIMUTHS]
tilt_handles = [mlines.Line2D([], [], color='black', linestyle=TILT_STYLES[t],
                linewidth=2, label=f'Tilt = {TILT_LABELS[t]}')
                for t in TILTS]

fig.legend(handles=az_handles + [mlines.Line2D([], [], color='none', label='')] + tilt_handles,
           loc='lower center', ncol=8, frameon=True, fancybox=True,
           edgecolor='#ccc', fontsize=9, bbox_to_anchor=(0.5, -0.02))

fig.suptitle('Impact of Panel Orientation and Tilt on Inverter Clipping',
             fontsize=13, fontweight='bold', y=1.03)

plt.tight_layout(rect=[0, 0.06, 1, 1])
plt.savefig(os.path.join(PLOTS_DIR, 'fig_orientation_tilt_clipping.png'), dpi=300, bbox_inches='tight')
plt.savefig(os.path.join(PLOTS_DIR, 'fig_orientation_tilt_clipping.pdf'), bbox_inches='tight')
print('Saved: fig_orientation_tilt_clipping.png / .pdf')
