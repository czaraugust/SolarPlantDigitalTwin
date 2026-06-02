"""
Publication-quality charts:
(a) Clipping Losses (kWh bars + % line) vs Installed Power
(b) Energy Gain (%) vs Oversizing (%)
Uses existing CSV data. English labels, serif font, 300 DPI.
"""
import sys
import os
# Adiciona a raiz do projeto ao Python path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

from core.config import RESULTS_DIR, PLOTS_DIR

plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'legend.fontsize': 10,
    'xtick.labelsize': 9,
    'ytick.labelsize': 10,
    'figure.dpi': 300,
})

df = pd.read_csv(os.path.join(RESULTS_DIR, 'resultado_tilt_orientacao_oversizing.csv'))
# Use tilt=5, azimute=0 (current system config)
d = df[(df['tilt'] == 5) & (df['azimute'] == 0)].sort_values('aumento_pct').reset_index(drop=True)
n_dias = 16
P_NOMINAL = 5.0
d['ilr'] = d['p_kwp'] / P_NOMINAL

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

# ===================== PANEL (a): Clipping Losses =====================
x = np.arange(len(d))
labels_x = [f'{kwp:.2f}\n(+{pct:.0f}%)' for kwp, pct in zip(d['p_kwp'], d['aumento_pct'])]

# Bars (kWh)
bars = ax1.bar(x, d['clip_kwh'], width=0.7, color='#E57373', edgecolor='white',
               linewidth=0.5, alpha=0.85, label='Clipping (kWh)', zorder=3)

ax1.set_xlabel('Installed Power kWp (Oversizing %)')
ax1.set_ylabel('Clipping Losses (kWh)', color='#C62828')
ax1.tick_params(axis='y', labelcolor='#C62828')
ax1.set_xticks(x)
ax1.set_xticklabels(labels_x, fontsize=6.5, rotation=45, ha='right')
ax1.grid(True, axis='y', linestyle='--', alpha=0.3)

# Line (%) on twin axis
ax1b = ax1.twinx()
ax1b.plot(x, d['clip_pct'], 's-', color='#0D47A1', linewidth=2, markersize=5,
          label='Clipping (%)', zorder=5)
ax1b.set_ylabel('Clipping Losses (%)', color='#0D47A1')
ax1b.tick_params(axis='y', labelcolor='#0D47A1')

# ILR annotations
for i, row in d.iterrows():
    if i % 2 == 0:
        ax1.text(i, row['clip_kwh'] + 3, f'ILR\n{row["ilr"]:.2f}',
                 ha='center', fontsize=6, color='#555', fontweight='bold')

# Combined legend
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax1b.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=9)

ax1.set_title(f'(a) Clipping Losses vs Installed Power')

# ===================== PANEL (b): Energy Gain =====================
ax2.plot([0, 100], [0, 100], '--', color='#EF5350', linewidth=1.5, alpha=0.7,
         label='Linear Gain (no clipping)')

ax2.fill_between(d['aumento_pct'], d['ganho_pct'], alpha=0.15, color='#1B5E20')
ax2.plot(d['aumento_pct'], d['ganho_pct'], 'o-', color='#1B5E20',
         linewidth=2.5, markersize=6, label='Actual Energy Gain', zorder=5)



ax2.set_xticks(np.arange(0, 105, 10))
ax2.set_yticks(np.arange(0, 105, 10))
ax2.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
ax2.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
ax2.set_xlabel('Increase in Installed Power (%)')
ax2.set_ylabel('Energy Gain (%)')
ax2.set_title(f'(b) Energy Gain vs Oversizing')
ax2.set_xlim(-2, 102)
ax2.set_ylim(-2, 102)
ax2.grid(True, linestyle='--', alpha=0.3)
ax2.legend(fontsize=9, loc='upper left')

fig.suptitle('Oversizing Analysis: Clipping Losses and Energy Gain',
             fontsize=14, fontweight='bold', y=1.01)

plt.tight_layout()
plt.savefig(os.path.join(PLOTS_DIR, 'fig_oversizing_clipping_gain.png'), dpi=300, bbox_inches='tight')
plt.savefig(os.path.join(PLOTS_DIR, 'fig_oversizing_clipping_gain.pdf'), bbox_inches='tight')
print('Saved: fig_oversizing_clipping_gain.png / .pdf')
