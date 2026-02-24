"""
Headless: Analise Multi-Cenario de Oversizing
Simula aumento de potencia instalada de 0% a 100% (passo de 5%).
O inversor permanece o mesmo (P_NOMINAL fixo).

Para cada cenario calcula:
- Energia gerada (kWh)
- Energia entregue pos-clipping (kWh)
- Perdas por clipping (kWh e %)
"""

import pandas as pd
import numpy as np
import pvlib
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.solar_calculator import CalculadoraSolar
from core.irradiance_calculator import calcular_componentes_irradiancia
from core.inverter_state_machine import InverterStateMachine

# --- CONFIGURACAO ---
CSV_PATH = r"C:\Users\55829\Downloads\PESSOAIS\MESTRADO\PESQUISA\PROJETO_GEMEO_DIGITAL_SOLAR\DATASET_MESTRE_COMPLETO.csv"

LATITUDE = -9.55762188835476
LONGITUDE = -35.78094625196216
TZ_OFFSET = -3

DATASHEET = {
    'celltype': 'polySi',
    'v_mp': 31.7, 'i_mp': 8.52,
    'v_oc': 38.8, 'i_sc': 9.09,
    'alpha_sc': 0.005454,
    'beta_voc': -0.1164,
    'gamma_pmp': -0.40,
    'cells_in_series': 60,
}

S1_SERIES = 10
S2_SERIES = 9
TOTAL_MODULES = S1_SERIES + S2_SERIES
P_PAINEL = 270  # W

TILT = 5.0
AZIMUTH = 0.0
ALBEDO = 0.2

P_NOMINAL = 5000.0
V_PARTIDA = 120.0

M4 = {'a': 6.263008, 'b': -30.290082, 'c': -1.811529, 'd': 0.117656, 'e': 72.7470}

# Cenarios: 0% a 100% em passos de 5%
CENARIOS = [i / 100.0 for i in range(0, 105, 5)]  # 0.00, 0.05, ..., 1.00


def efficiency_formula(p_dc):
    return 96.8016 - (9653.1352 / p_dc) - (0.000125 * p_dc)


def simular_cenario(p_dc_base, v_s1, v_s2, fator, p_nominal):
    """Simula um cenario com fator de aumento sobre P_DC base."""
    p_dc = p_dc_base * (1.0 + fator)
    n = len(p_dc)

    sm = InverterStateMachine(v_partida=V_PARTIDA)
    p_ac_preclip = np.zeros(n)

    for i in range(n):
        estado = sm.step(v_s1[i], v_s2[i], p_dc[i])
        if estado == InverterStateMachine.LIGADO and p_dc[i] > 50:
            eff = efficiency_formula(p_dc[i])
            if eff > 0:
                p_ac_preclip[i] = p_dc[i] * (eff / 100.0)

    p_ac_clipped = np.minimum(p_ac_preclip, p_nominal)
    clip_loss = np.maximum(p_ac_preclip - p_nominal, 0)

    dt_h = 1.0 / 60.0
    energy_total = (p_ac_preclip * dt_h).sum() / 1000.0
    energy_entregue = (p_ac_clipped * dt_h).sum() / 1000.0
    clip_kwh = (clip_loss * dt_h).sum() / 1000.0
    clip_pct = (clip_kwh / energy_total * 100) if energy_total > 0 else 0.0

    return {
        'fator': fator,
        'p_instalada_kwp': TOTAL_MODULES * P_PAINEL * (1 + fator) / 1000.0,
        'energy_total': energy_total,
        'energy_entregue': energy_entregue,
        'clip_kwh': clip_kwh,
        'clip_pct': clip_pct,
    }


def run():
    print("=" * 70)
    print("  ANALISE MULTI-CENARIO: OVERSIZING DA PLANTA FOTOVOLTAICA")
    print("=" * 70)

    # --- CARREGAR E PREPARAR ---
    print(f"\nCarregando CSV...")
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

    n_dias = len(df.index.normalize().unique())
    print(f"Registros: {len(df)} | Dias: {n_dias}")

    # --- CALCULO SOLAR ---
    print("Calculando irradiancia POA...")
    poa_arr = np.zeros(len(df))
    timestamps = df.index.to_pydatetime()
    ghis = df['Irradiance'].values

    for i, dt in enumerate(timestamps):
        cs = CalculadoraSolar(dt, LATITUDE, LONGITUDE, TZ_OFFSET)
        zenith = 90 - cs.elevacao
        res = calcular_componentes_irradiancia(
            ghi=ghis[i], albedo=ALBEDO, dia_do_ano=cs.numero_do_dia,
            solar_zenith_deg=zenith, solar_azimuth_deg=cs.azimute,
            inclinacao_superficie=TILT, azimute_superficie=AZIMUTH)
        poa_arr[i] = res['global']
        if i % 2000 == 0:
            print(f"  {i}/{len(df)}", end='\r')
    print(f"  {len(df)}/{len(df)}")

    poa_global = pd.Series(poa_arr, index=df.index)

    # --- MODELO ELETRICO ---
    print("Calculando P_DC base (single diode + M4)...")
    temp_cell = pvlib.temperature.sapm_cell_from_module(
        module_temperature=df['PV Temperature'], poa_global=poa_global, deltaT=1.0)

    stc = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'], cells_in_series=DATASHEET['cells_in_series'])

    I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = stc[0:5]
    eff_irr = poa_global.clip(upper=1400.0)

    dp = pvlib.pvsystem.calcparams_desoto(
        effective_irradiance=eff_irr, temp_cell=temp_cell,
        alpha_sc=DATASHEET['alpha_sc'],
        a_ref=a_ref, I_L_ref=I_L_ref, I_o_ref=I_o_ref,
        R_sh_ref=R_sh_ref, R_s=R_s,
        EgRef=1.121, dEgdT=-0.0002677)

    IL, I0, Rs, Rsh, nNsVth = dp
    sd = pvlib.pvsystem.singlediode(
        photocurrent=IL, saturation_current=I0,
        resistance_series=Rs, resistance_shunt=Rsh,
        nNsVth=nNsVth, method='lambertw')

    p_dc_raw = sd['p_mp'] * TOTAL_MODULES
    p_dc_base = (M4['a'] * p_dc_raw +
                 M4['b'] * poa_global.values +
                 M4['c'] * df['PV Temperature'].values +
                 M4['d'] * poa_global.values * df['PV Temperature'].values +
                 M4['e'])
    p_dc_base = np.clip(p_dc_base, 0, None)

    v_s1 = df['Voltage S1'].values
    v_s2 = df['Voltage S2'].values

    # --- CENARIO REAL (referencia) ---
    dt_h = 1.0 / 60.0
    p_ac_real = df['Power'].values
    energy_real = (np.minimum(p_ac_real, P_NOMINAL) * dt_h).sum() / 1000.0

    # --- RODAR CENARIOS ---
    print(f"\nRodando {len(CENARIOS)} cenarios...\n")
    resultados = []

    for fator in CENARIOS:
        r = simular_cenario(p_dc_base, v_s1, v_s2, fator, P_NOMINAL)
        resultados.append(r)
        pct = fator * 100
        print(f"  +{pct:5.0f}% | {r['p_instalada_kwp']:.2f} kWp | "
              f"Gerado: {r['energy_total']:.1f} kWh | "
              f"Entregue: {r['energy_entregue']:.1f} kWh | "
              f"Clipping: {r['clip_kwh']:.2f} kWh ({r['clip_pct']:.2f}%)")

    # --- TABELA RESUMO ---
    print("\n" + "=" * 70)
    print("  RESUMO COMPARATIVO")
    print("=" * 70)
    print(f"  Periodo: {n_dias} dias | Inversor: {P_NOMINAL:.0f} W | Real: {energy_real:.1f} kWh")
    print("-" * 70)
    print(f"  {'Aumento':>8} {'kWp':>7} {'Gerado':>10} {'Entregue':>10} "
          f"{'Clip kWh':>10} {'Clip%':>7} {'Ganho':>8}")
    print("-" * 70)

    base_entregue = resultados[0]['energy_entregue']
    for r in resultados:
        ganho = ((r['energy_entregue'] - base_entregue) / base_entregue * 100) if base_entregue > 0 else 0
        print(f"  +{r['fator']*100:5.0f}%  {r['p_instalada_kwp']:>6.2f} "
              f"{r['energy_total']:>9.1f} {r['energy_entregue']:>9.1f} "
              f"{r['clip_kwh']:>9.2f} {r['clip_pct']:>6.2f}% {ganho:>7.2f}%")

    print("=" * 70)

    # --- SALVAR CSV ---
    df_result = pd.DataFrame(resultados)
    df_result['ganho_pct'] = ((df_result['energy_entregue'] - base_entregue) / base_entregue * 100)
    df_result['aumento_pct'] = df_result['fator'] * 100
    OUTPUT = "resultado_cenarios_oversizing.csv"
    df_result.to_csv(OUTPUT, index=False)
    print(f"\nCSV salvo: {os.path.abspath(OUTPUT)}")


if __name__ == "__main__":
    run()
