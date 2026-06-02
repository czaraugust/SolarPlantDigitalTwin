"""
Analise Combinada: Orientacao x Inclinacao x Oversizing
4 azimutes (0, 90, 180, 270) x 5 inclinacoes (0, 5, 10, 15, 20) x 21 cenarios

Para cada inclinacao, gera 3 graficos com 4 curvas (uma por azimute):
  1. Energia Entregue vs kWp
  2. Ganho de Energia (%) vs Aumento (%)
  3. Perdas por Clipping vs kWp
"""

import sys
import os
# Adiciona a raiz do projeto ao Python path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import pvlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

from core.solar_calculator import CalculadoraSolar
from core.irradiance_calculator import calcular_componentes_irradiancia
from core.inverter_model import InverterModel
from core.config import DATASET_16D_PATH, RESULTS_DIR, PLOTS_DIR

# --- CONFIGURACAO ---
CSV_PATH = DATASET_16D_PATH
LATITUDE = -9.55762188835476
LONGITUDE = -35.78094625196216
TZ_OFFSET = -3
ALBEDO = 0.2
TOTAL_MODULES = 19
P_PAINEL = 270
P_NOMINAL = 5000.0
V_PARTIDA = 120.0

DATASHEET = {
    'celltype': 'polySi', 'v_mp': 31.7, 'i_mp': 8.52,
    'v_oc': 38.8, 'i_sc': 9.09, 'alpha_sc': 0.005454,
    'beta_voc': -0.1164, 'gamma_pmp': -0.40, 'cells_in_series': 60,
}
M4 = {'a': 6.263008, 'b': -30.290082, 'c': -1.811529, 'd': 0.117656, 'e': 72.7470}

AZIMUTHS = [0, 90, 180, 270]
AZ_LABELS = {0: 'Norte (0)', 90: 'Leste (90)', 180: 'Sul (180)', 270: 'Oeste (270)'}
AZ_COLORS = {0: '#2196F3', 90: '#FF9800', 180: '#4CAF50', 270: '#E91E63'}
AZ_MARKERS = {0: 'o', 90: 's', 180: '^', 270: 'D'}

TILTS = [0, 5, 10, 15, 20]
CENARIOS = [i / 100.0 for i in range(0, 105, 5)]


def simular_cenarios(p_dc_base, v_s1, v_s2):
    resultados = []
    for fator in CENARIOS:
        p_dc = p_dc_base * (1.0 + fator)
        n = len(p_dc)
        sm = InverterModel(v_partida=V_PARTIDA)
        p_ac_preclip = np.zeros(n)

        for i in range(n):
            estado, _ = sm.step(v_s1[i], v_s2[i], p_dc[i])
            if estado == InverterModel.LIGADO and p_dc[i] > 50:
                eff = sm.calculate_efficiency(p_dc[i])
                if eff > 0:
                    p_ac_preclip[i] = p_dc[i] * (eff / 100.0)

        p_ac = np.minimum(p_ac_preclip, P_NOMINAL)
        clip = np.maximum(p_ac_preclip - P_NOMINAL, 0)
        dt_h = 1.0 / 60.0
        e_total = (p_ac_preclip * dt_h).sum() / 1000.0
        e_entregue = (p_ac * dt_h).sum() / 1000.0
        c_kwh = (clip * dt_h).sum() / 1000.0
        c_pct = (c_kwh / e_total * 100) if e_total > 0 else 0.0

        resultados.append({
            'fator': fator, 'aumento_pct': fator * 100,
            'p_kwp': TOTAL_MODULES * P_PAINEL * (1 + fator) / 1000.0,
            'energy_entregue': e_entregue,
            'clip_kwh': c_kwh, 'clip_pct': c_pct,
        })
    df = pd.DataFrame(resultados)
    base_e = df.iloc[0]['energy_entregue']
    df['ganho_pct'] = (df['energy_entregue'] - base_e) / base_e * 100
    return df


def gerar_graficos(tilt, data_por_az, n_dias, output_dir):
    """Gera 3 graficos para um dado tilt."""
    # Labels do eixo X (usa dados do primeiro azimute)
    ref = data_por_az[AZIMUTHS[0]]
    labels_x = [f"{kwp:.2f}\n(+{pct:.0f}%)" for kwp, pct in zip(ref['p_kwp'], ref['aumento_pct'])]

    # --- GRAFICO 1: Energia Entregue ---
    fig1, ax1 = plt.subplots(figsize=(14, 6))
    for az in AZIMUTHS:
        d = data_por_az[az]
        ax1.plot(range(len(d)), d['energy_entregue'], f'{AZ_MARKERS[az]}-',
                 color=AZ_COLORS[az], linewidth=2, markersize=6, label=AZ_LABELS[az])
    ax1.set_xticks(range(len(ref)))
    ax1.set_xticklabels(labels_x, fontsize=6, rotation=45, ha='right')
    ax1.set_xlabel('Potencia Instalada kWp (Aumento %)', fontsize=11)
    ax1.set_ylabel('Energia Entregue (kWh)', fontsize=11)
    ax1.set_title(f'Energia Entregue vs Potencia Instalada (Tilt={tilt}, {n_dias} dias, Inv. 5kW)',
                  fontsize=13, fontweight='bold')
    ax1.grid(True, linestyle='--', alpha=0.4)
    ax1.legend(fontsize=10)
    fig1.tight_layout()
    f1 = os.path.join(output_dir, f'grafico_tilt{tilt}_energia.png')
    fig1.savefig(f1, dpi=150)
    plt.close(fig1)

    # --- GRAFICO 2: Ganho % ---
    fig2, ax2 = plt.subplots(figsize=(12, 6))
    ax2.plot([0, 100], [0, 100], '--', color='red', linewidth=1.5, alpha=0.6, label='Ganho Linear')
    for az in AZIMUTHS:
        d = data_por_az[az]
        ax2.plot(d['aumento_pct'], d['ganho_pct'], f'{AZ_MARKERS[az]}-',
                 color=AZ_COLORS[az], linewidth=2.5, markersize=7, label=AZ_LABELS[az])
    ax2.set_xticks(np.arange(0, 105, 5))
    ax2.set_yticks(np.arange(0, 105, 5))
    ax2.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax2.set_xlabel('Aumento na Potencia Instalada (%)', fontsize=12)
    ax2.set_ylabel('Ganho na Energia Entregue (%)', fontsize=12)
    ax2.set_title(f'Ganho de Energia vs Aumento (Tilt={tilt}, Inv. 5kW)', fontsize=13, fontweight='bold')
    ax2.grid(True, linestyle='--', alpha=0.4)
    ax2.legend(fontsize=10)
    ax2.set_xlim(-2, 102)
    ax2.set_ylim(-2, 102)
    fig2.tight_layout()
    f2 = os.path.join(output_dir, f'grafico_tilt{tilt}_ganho.png')
    fig2.savefig(f2, dpi=150)
    plt.close(fig2)

    # --- GRAFICO 3: Clipping ---
    fig3, ax3 = plt.subplots(figsize=(14, 6))
    ax3b = ax3.twinx()
    n_az = len(AZIMUTHS)
    bar_w = 0.8 / n_az
    x = np.arange(len(CENARIOS))
    for idx, az in enumerate(AZIMUTHS):
        d = data_por_az[az]
        off = (idx - n_az / 2 + 0.5) * bar_w
        ax3.bar(x + off, d['clip_kwh'], bar_w * 0.9,
                color=AZ_COLORS[az], alpha=0.6, label=f'{AZ_LABELS[az]}')
        ax3b.plot(x, d['clip_pct'], f'{AZ_MARKERS[az]}-',
                  color=AZ_COLORS[az], linewidth=1.8, markersize=5)
    ax3.set_xticks(x)
    ax3.set_xticklabels(labels_x, fontsize=6, rotation=45, ha='right')
    ax3.set_xlabel('Potencia Instalada kWp (Aumento %)', fontsize=11)
    ax3.set_ylabel('Clipping (kWh)', fontsize=11)
    ax3b.set_ylabel('Clipping (%)', fontsize=11)
    ax3.set_title(f'Perdas por Clipping (Tilt={tilt}, {n_dias} dias, Inv. 5kW)',
                  fontsize=13, fontweight='bold')
    ax3.grid(True, linestyle='--', alpha=0.3)
    ax3.legend(fontsize=8, loc='upper left')
    fig3.tight_layout()
    f3 = os.path.join(output_dir, f'grafico_tilt{tilt}_clipping.png')
    fig3.savefig(f3, dpi=150)
    plt.close(fig3)

    return f1, f2, f3


def run():
    print("=" * 75)
    print("  ANALISE: ORIENTACAO x INCLINACAO x OVERSIZING")
    print(f"  {len(AZIMUTHS)} azimutes x {len(TILTS)} tilts x {len(CENARIOS)} cenarios"
          f" = {len(AZIMUTHS) * len(TILTS) * len(CENARIOS)} simulacoes")
    print("=" * 75)

    # --- CARREGAR DADOS ---
    print("\nCarregando CSV...")
    df = pd.read_csv(CSV_PATH)
    df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str))
    df = df.set_index('datetime')
    df = df.between_time('05:00', '18:00')

    df['Wind Speed'] = pd.to_numeric(df['Wind Speed'], errors='coerce') / 3.6
    cols = ['Amb. Temperature', 'Irradiance', 'PV Temperature',
            'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2', 'Power']
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=cols + ['Wind Speed'])

    n = len(df)
    n_dias = len(df.index.normalize().unique())
    print(f"Registros: {n} | Dias: {n_dias}")

    # --- POSICAO SOLAR ---
    print("Pre-calculando posicao solar...")
    timestamps = df.index.to_pydatetime()
    ghis = df['Irradiance'].values
    v_s1 = df['Voltage S1'].values
    v_s2 = df['Voltage S2'].values
    temp_mod = df['PV Temperature'].values

    solar_data = []
    for i, dt in enumerate(timestamps):
        cs = CalculadoraSolar(dt, LATITUDE, LONGITUDE, TZ_OFFSET)
        solar_data.append({'zenith': 90 - cs.elevacao, 'azimuth': cs.azimute, 'dia': cs.numero_do_dia})
        if i % 2000 == 0:
            print(f"  {i}/{n}", end='\r')
    print(f"  {n}/{n}")

    # --- STC ---
    stc = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'], cells_in_series=DATASHEET['cells_in_series'])
    I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = stc[0:5]

    # --- LOOP PRINCIPAL ---
    all_csv = []
    resumo_base = []

    for tilt in TILTS:
        print(f"\n{'='*60}")
        print(f"  INCLINACAO = {tilt} graus")
        print(f"{'='*60}")

        data_por_az = {}
        for az in AZIMUTHS:
            print(f"  Azimute {az} ({AZ_LABELS[az]}): ", end='')

            # POA
            poa_arr = np.zeros(n)
            for i in range(n):
                sd = solar_data[i]
                res = calcular_componentes_irradiancia(
                    ghi=ghis[i], albedo=ALBEDO, dia_do_ano=sd['dia'],
                    solar_zenith_deg=sd['zenith'], solar_azimuth_deg=sd['azimuth'],
                    inclinacao_superficie=tilt, azimute_superficie=az)
                poa_arr[i] = res['global']

            poa_s = pd.Series(poa_arr, index=df.index)
            temp_cell = pvlib.temperature.sapm_cell_from_module(
                module_temperature=df['PV Temperature'], poa_global=poa_s, deltaT=1.0)

            eff_irr = poa_s.clip(upper=1400.0)
            dp = pvlib.pvsystem.calcparams_desoto(
                effective_irradiance=eff_irr, temp_cell=temp_cell,
                alpha_sc=DATASHEET['alpha_sc'],
                a_ref=a_ref, I_L_ref=I_L_ref, I_o_ref=I_o_ref,
                R_sh_ref=R_sh_ref, R_s=R_s, EgRef=1.121, dEgdT=-0.0002677)
            IL, I0, Rs, Rsh, nNsVth = dp
            sd_res = pvlib.pvsystem.singlediode(
                photocurrent=IL, saturation_current=I0,
                resistance_series=Rs, resistance_shunt=Rsh,
                nNsVth=nNsVth, method='lambertw')

            p_dc_raw = sd_res['p_mp'] * TOTAL_MODULES
            p_dc_base = np.clip(
                M4['a'] * p_dc_raw + M4['b'] * poa_arr +
                M4['c'] * temp_mod + M4['d'] * poa_arr * temp_mod + M4['e'], 0, None)

            df_cen = simular_cenarios(p_dc_base, v_s1, v_s2)
            df_cen['tilt'] = tilt
            df_cen['azimute'] = az
            data_por_az[az] = df_cen
            all_csv.append(df_cen)

            base_e = df_cen.iloc[0]['energy_entregue']
            resumo_base.append({'tilt': tilt, 'azimute': az, 'label': AZ_LABELS[az],
                                'energy_kwh': base_e, 'kwh_dia': base_e / n_dias})
            print(f"Base={base_e:.1f} kWh | +100%={df_cen.iloc[-1]['energy_entregue']:.1f} kWh | "
                  f"Clip={df_cen.iloc[-1]['clip_pct']:.1f}%")

        # Gerar graficos para este tilt
        f1, f2, f3 = gerar_graficos(tilt, data_por_az, n_dias, PLOTS_DIR)
        print(f"  Graficos salvos: tilt{tilt}_*.png")

    # --- TABELA RESUMO ---
    print("\n" + "=" * 75)
    print("  RESUMO: ENERGIA BASE (sem oversizing) POR TILT x ORIENTACAO")
    print("=" * 75)
    print(f"  {'Tilt':>5} | {'Norte (0)':>12} | {'Leste (90)':>12} | {'Sul (180)':>12} | {'Oeste (270)':>12} | {'Melhor':>15}")
    print("  " + "-" * 75)
    for tilt in TILTS:
        vals = {r['azimute']: r['energy_kwh'] for r in resumo_base if r['tilt'] == tilt}
        best_az = max(vals, key=vals.get)
        print(f"  {tilt:>4} | {vals[0]:>10.1f} | {vals[90]:>10.1f} | "
              f"{vals[180]:>10.1f} | {vals[270]:>10.1f} | {AZ_LABELS[best_az]:>15}")

    # --- SALVAR CSV ---
    df_result = pd.concat(all_csv, ignore_index=True)
    OUTPUT = os.path.join(RESULTS_DIR, "resultado_tilt_orientacao_oversizing.csv")
    df_result.to_csv(OUTPUT, index=False)
    print(f"\nCSV: {OUTPUT}")


if __name__ == "__main__":
    run()
