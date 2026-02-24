import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np

df = pd.read_csv('resultado_cenarios_oversizing.csv')

fig, ax = plt.subplots(figsize=(12, 6))

# Linha de referência (ganho linear ideal, sem clipping)
ax.plot([0, 100], [0, 100], '--', color='red', linewidth=1.5, alpha=0.7)

# Dados reais
ax.plot(df['aumento_pct'], df['ganho_pct'], 'o-', color='#4CAF50', linewidth=2.5, markersize=8)
ax.fill_between(df['aumento_pct'], df['ganho_pct'], alpha=0.12, color='#4CAF50')

# Ticks a cada 5%
ax.set_xticks(np.arange(0, 105, 5))
ax.set_yticks(np.arange(0, 105, 5))
ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))

ax.set_xlabel('Aumento na Potencia Instalada (%)', fontsize=12)
ax.set_ylabel('Ganho na Energia Entregue (%)', fontsize=12)
ax.set_title('Ganho de Energia vs Aumento de Potencia Instalada (Inversor 5kW)', fontsize=13, fontweight='bold')
ax.grid(True, linestyle='--', alpha=0.5)
ax.legend(fontsize=10)
ax.set_xlim(-2, 102)
ax.set_ylim(-2, 102)

plt.tight_layout()
plt.savefig('grafico_ganho_vs_aumento.png', dpi=150)
print('Grafico salvo: grafico_ganho_vs_aumento.png')
