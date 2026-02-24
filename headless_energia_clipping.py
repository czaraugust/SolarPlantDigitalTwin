"""
Headless: Energia Gerada e Perdas por Clipping — Real vs Simulado

Processa o CSV completo (05:00-18:00) e calcula:
- Energia gerada (kWh) — Real e Simulada
- Perdas por clipping (kWh) — Real e Simulada
- Métricas de comparação P_AC

Fluxo:
1. Calcula P_DC previsto (modelo PV + correção M4)
2. Aplica máquina de estados do inversor
3. Aplica fórmula de eficiência (DC → AC)
4. Aplica clipping na potência nominal
5. Acumula energia e perdas por clipping
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

# --- CONFIGURAÇÃO ---
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

TILT = 5.0
AZIMUTH = 0.0
ALBEDO = 0.2

# Inversor
P_NOMINAL = 5000.0   # W — potência nominal do inversor (clipping)
V_PARTIDA = 120.0     # V

# Correção M4
M4 = {'a': 6.263008, 'b': -30.290082, 'c': -1.811529, 'd': 0.117656, 'e': 72.7470}


def efficiency_formula(p_dc):
    """Eficiência do inversor."""
    return 96.8016 - (9653.1352 / p_dc) - (0.000125 * p_dc)


def run():
    print("=" * 65)
    print("  ANALISE DE ENERGIA E CLIPPING — REAL vs SIMULADO")
    print("=" * 65)

    # --- CARREGAR DADOS ---
    print(f"\nCarregando CSV: {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)

    df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str))
    df = df.set_index('datetime')
    df = df.between_time('05:00', '18:00')

    df['Wind Speed'] = pd.to_numeric(df['Wind Speed'], errors='coerce') / 3.6
    cols_numeric = ['Amb. Temperature', 'Irradiance', 'PV Temperature',
                    'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2', 'Power']
    for col in cols_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=cols_numeric + ['Wind Speed'])
    print(f"Registros validos: {len(df)}")

    # --- P_DC REAL ---
    df['P_dc_real'] = (df['Voltage S1'] * df['Current S1']) + \
                      (df['Voltage S2'] * df['Current S2'])

    # --- P_AC REAL ---
    df['P_ac_real'] = df['Power']

    # --- CALCULO SOLAR E IRRADIANCIA ---
    print(f"Calculando irradiancia POA para {len(df)} registros...")
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

    # --- TEMPERATURA DE CELULA (SAPM) ---
    temp_cell = pvlib.temperature.sapm_cell_from_module(
        module_temperature=df['PV Temperature'], poa_global=poa_global, deltaT=1.0)

    # --- CALCULO ELETRICO (Single Diode) ---
    print("Calculando P_DC previsto (single diode + M4)...")
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
    p_mp = sd['p_mp']

    # P_DC raw e corrigido (M4)
    df['P_dc_raw'] = p_mp * TOTAL_MODULES
    df['P_dc_sim'] = (M4['a'] * df['P_dc_raw'] +
                      M4['b'] * poa_global +
                      M4['c'] * df['PV Temperature'] +
                      M4['d'] * poa_global * df['PV Temperature'] +
                      M4['e']).clip(lower=0.0)

    # --- MAQUINA DE ESTADOS ---
    print("Aplicando maquina de estados...")
    sm = InverterStateMachine(v_partida=V_PARTIDA)

    v_s1 = df['Voltage S1'].values
    v_s2 = df['Voltage S2'].values
    p_dc_sim = df['P_dc_sim'].values

    estados = []
    p_ac_sim_arr = np.zeros(len(df))

    for i in range(len(df)):
        estado = sm.step(v_s1[i], v_s2[i], p_dc_sim[i])
        estados.append(estado)

        if estado == InverterStateMachine.LIGADO and p_dc_sim[i] > 50:
            eff = efficiency_formula(p_dc_sim[i])
            if eff > 0:
                p_ac_sim_arr[i] = p_dc_sim[i] * (eff / 100.0)

    df['Estado'] = estados
    df['P_ac_sim_preclip'] = p_ac_sim_arr

    # --- CLIPPING ---
    print(f"Aplicando clipping (P_nominal = {P_NOMINAL} W)...")
    df['P_ac_sim'] = np.minimum(df['P_ac_sim_preclip'], P_NOMINAL)
    df['P_ac_real_clipped'] = np.minimum(df['P_ac_real'], P_NOMINAL)

    df['Clip_sim'] = np.maximum(df['P_ac_sim_preclip'] - P_NOMINAL, 0)
    df['Clip_real'] = np.maximum(df['P_ac_real'] - P_NOMINAL, 0)

    # --- ACUMULAR ENERGIA ---
    # Cada registro = 1 minuto = 1/60 hora
    dt_hours = 1.0 / 60.0

    # Energia pos-clipping (entregue)
    energy_sim_kwh = (df['P_ac_sim'] * dt_hours).sum() / 1000.0
    energy_real_kwh = (df['P_ac_real_clipped'] * dt_hours).sum() / 1000.0

    # Energia sem clipping (total gerada)
    energy_sim_total_kwh = (df['P_ac_sim_preclip'] * dt_hours).sum() / 1000.0
    energy_real_total_kwh = (df['P_ac_real'] * dt_hours).sum() / 1000.0

    # Perdas por clipping
    clip_sim_kwh = (df['Clip_sim'] * dt_hours).sum() / 1000.0
    clip_real_kwh = (df['Clip_real'] * dt_hours).sum() / 1000.0

    # Métricas AC
    valid = df[df['P_ac_real'] > 10].copy()
    errors = valid['P_ac_sim'] - valid['P_ac_real_clipped']
    rmse = np.sqrt((errors ** 2).mean())
    mae = errors.abs().mean()
    mape = (errors.abs() / valid['P_ac_real_clipped']).mean() * 100
    wape = errors.abs().sum() / valid['P_ac_real_clipped'].sum() * 100

    n_ligado = (df['Estado'] == 'LIGADO').sum()
    n_desligado = (df['Estado'] == 'DESLIGADO').sum()
    n_dias = len(df.index.normalize().unique())

    # --- RESULTADOS ---
    print("\n" + "=" * 65)
    print("  RESULTADOS: ENERGIA E CLIPPING")
    print("=" * 65)
    print(f"  Periodo: {df.index[0].date()} a {df.index[-1].date()} ({n_dias} dias)")
    print(f"  Horario: 05:00 - 18:00")
    print(f"  Registros: {len(df)} ({n_ligado} LIGADO / {n_desligado} DESLIGADO)")
    print(f"  P_Nominal Inversor: {P_NOMINAL} W")

    print("\n" + "-" * 65)
    print(f"  {'':30} {'REAL':>12} {'SIMULADO':>12}")
    print("-" * 65)
    print(f"  {'Energia Total Gerada [kWh]':30} {energy_real_total_kwh:>12.3f} {energy_sim_total_kwh:>12.3f}")
    print(f"  {'Energia Entregue [kWh]':30} {energy_real_kwh:>12.3f} {energy_sim_kwh:>12.3f}")
    print(f"  {'Perda por Clipping [kWh]':30} {clip_real_kwh:>12.3f} {clip_sim_kwh:>12.3f}")
    print(f"  {'Perda Clipping [%]':30} {(clip_real_kwh/energy_real_total_kwh*100) if energy_real_total_kwh > 0 else 0:>11.2f}% {(clip_sim_kwh/energy_sim_total_kwh*100) if energy_sim_total_kwh > 0 else 0:>11.2f}%")

    print("\n" + "-" * 65)
    print("  METRICAS AC (Simulado vs Real)")
    print("-" * 65)
    print(f"  RMSE: {rmse:.2f} W")
    print(f"  MAE:  {mae:.2f} W")
    print(f"  MAPE: {mape:.2f}%")
    print(f"  WAPE: {wape:.2f}%")

    print("\n" + "-" * 65)
    print("  MEDIAS DIARIAS")
    print("-" * 65)
    print(f"  {'Energia Real/dia [kWh]':30} {energy_real_kwh/n_dias:>12.3f}")
    print(f"  {'Energia Simulada/dia [kWh]':30} {energy_sim_kwh/n_dias:>12.3f}")
    print(f"  {'Clipping Real/dia [kWh]':30} {clip_real_kwh/n_dias:>12.3f}")
    print(f"  {'Clipping Simulado/dia [kWh]':30} {clip_sim_kwh/n_dias:>12.3f}")
    print("=" * 65)

    # Salvar CSV
    output_df = df[['P_dc_real', 'P_dc_sim', 'P_ac_real', 'P_ac_real_clipped',
                     'P_ac_sim_preclip', 'P_ac_sim', 'Clip_real', 'Clip_sim',
                     'Estado']].copy()
    OUTPUT_FILE = "resultado_energia_clipping.csv"
    output_df.to_csv(OUTPUT_FILE)
    print(f"\nCSV salvo: {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    run()
