"""
Headless Previsão DC - Análise completa do dataset
Replica a lógica da aba "Previsão" sem interface gráfica.

Fluxo:
1. Carrega CSV -> calcula posição solar e POA irradiância (custom calculators)
2. Calcula temperatura de célula via SAPM (sensor + ΔT)
3. Calcula P_DC previsto via single diode model (pvlib) para config [10s + 9s]
4. P_DC real = (V_s1 * I_s1) + (V_s2 * I_s2)
5. Compara P_DC previsto vs P_DC real
6. Calcula métricas: MSE, MAE, RMSE, MAPE, WAPE
"""

import pandas as pd
import numpy as np
import pvlib
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.solar_calculator import CalculadoraSolar
from core.irradiance_calculator import calcular_componentes_irradiancia

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
TOTAL_MODULES = S1_SERIES + S2_SERIES  # 19

TILT = 5.0
AZIMUTH = 0.0
ALBEDO = 0.2


def run_analysis():
    print(f"Carregando CSV: {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)

    print("Preparando dados...")
    df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str))
    df = df.set_index('datetime')
    df = df.between_time('05:00', '18:00')

    if len(df) == 0:
        print("Nenhum dado encontrado.")
        return

    df['Wind Speed'] = pd.to_numeric(df['Wind Speed'], errors='coerce') / 3.6

    cols_numeric = ['Amb. Temperature', 'Irradiance', 'PV Temperature',
                    'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2']
    for col in cols_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna(subset=cols_numeric + ['Wind Speed'])
    print(f"Registros válidos: {len(df)}")

    # P_DC Real (S1 + S2)
    df['P_dc_real'] = (df['Voltage S1'] * df['Current S1']) + \
                      (df['Voltage S2'] * df['Current S2'])

    # --- POSIÇÃO SOLAR E IRRADIÂNCIA ---
    print(f"Calculando posição solar e irradiância para {len(df)} registros...")
    poa_global_arr = np.zeros(len(df))
    timestamps = df.index.to_pydatetime()
    ghis = df['Irradiance'].values

    for i, dt in enumerate(timestamps):
        calc_solar = CalculadoraSolar(dt, LATITUDE, LONGITUDE, TZ_OFFSET)
        zenith = 90 - calc_solar.elevacao
        azimuth_sol = calc_solar.azimute
        day_of_year = calc_solar.numero_do_dia

        res_irr = calcular_componentes_irradiancia(
            ghi=ghis[i], albedo=ALBEDO, dia_do_ano=day_of_year,
            solar_zenith_deg=zenith, solar_azimuth_deg=azimuth_sol,
            inclinacao_superficie=TILT, azimute_superficie=AZIMUTH)

        poa_global_arr[i] = res_irr['global']
        if i % 1000 == 0:
            print(f"  Processado: {i}/{len(df)}", end='\r')

    print(f"  Processado: {len(df)}/{len(df)}")
    poa_global = pd.Series(poa_global_arr, index=df.index)

    # --- TEMPERATURA (SAPM) ---
    print("Calculando temperatura de célula (SAPM)...")
    temp_cell_sapm = pvlib.temperature.sapm_cell_from_module(
        module_temperature=df['PV Temperature'],
        poa_global=poa_global,
        deltaT=1.0)

    # --- SINGLE DIODE ---
    print("Estimando parâmetros elétricos (DeSoto + LambertW)...")
    stc_params = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'],
        cells_in_series=DATASHEET['cells_in_series'])

    I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = stc_params[0:5]

    effective_irradiance = poa_global.clip(upper=1400.0)

    desoto_params = pvlib.pvsystem.calcparams_desoto(
        effective_irradiance=effective_irradiance,
        temp_cell=temp_cell_sapm,
        alpha_sc=DATASHEET['alpha_sc'],
        a_ref=a_ref, I_L_ref=I_L_ref, I_o_ref=I_o_ref,
        R_sh_ref=R_sh_ref, R_s=R_s,
        EgRef=1.121, dEgdT=-0.0002677)

    IL, I0, Rs, Rsh, nNsVth = desoto_params

    print("Resolvendo single diode (LambertW)...")
    try:
        i_mp, v_mp, p_mp = pvlib.singlediode(
            photocurrent=IL, saturation_current=I0,
            resistance_series=Rs, resistance_shunt=Rsh,
            nNsVth=nNsVth, method='lambertw')
    except Exception:
        res = pvlib.singlediode.bishop88_mpp(
            photocurrent=IL, saturation_current=I0,
            resistance_series=Rs, resistance_shunt=Rsh,
            nNsVth=nNsVth, method='newton')
        p_mp = res[2]

    # P_DC Previsto (19 módulos = 10s + 9s)
    df['P_dc_pred_raw'] = p_mp * TOTAL_MODULES

    # --- CORREÇÃO M4 (Regressão Multivariável) ---
    # P_corr = a*P_pred + b*POA + c*Temp + d*POA*Temp + e
    M4 = {'a': 6.263008, 'b': -30.290082, 'c': -1.811529, 'd': 0.117656, 'e': 72.7470}
    df['P_dc_prev'] = (M4['a'] * df['P_dc_pred_raw'] +
                       M4['b'] * poa_global +
                       M4['c'] * df['PV Temperature'] +
                       M4['d'] * poa_global * df['PV Temperature'] +
                       M4['e'])
    df['P_dc_prev'] = df['P_dc_prev'].clip(lower=0.0)
    print(f"P_DC previsto calculado com correção M4 (config: {S1_SERIES}s + {S2_SERIES}s = {TOTAL_MODULES} módulos)")

    # --- MÉTRICAS ---
    print("\n--- Calculando métricas (P_DC Previsto vs P_DC Real) ---")

    valid = df[df['P_dc_real'] > 10.0].copy()
    print(f"Registros válidos (P_dc_real > 10W): {len(valid)}")

    errors = valid['P_dc_prev'] - valid['P_dc_real']

    mse = (errors ** 2).mean()
    rmse = np.sqrt(mse)
    mae = errors.abs().mean()
    mape = (errors.abs() / valid['P_dc_real']).mean() * 100
    wape = (errors.abs().sum() / valid['P_dc_real'].sum()) * 100

    print("\n" + "=" * 50)
    print("  RESULTADOS: P_DC Previsto vs P_DC Real")
    print("=" * 50)
    print(f"  Config: String 1 = {S1_SERIES}s, String 2 = {S2_SERIES}s")
    print(f"  Total Módulos: {TOTAL_MODULES}")
    print(f"  Modelo de Temperatura: SAPM (Sensor)")
    print("-" * 50)
    print(f"  MSE:  {mse:.4f} W²")
    print(f"  RMSE: {rmse:.4f} W")
    print(f"  MAE:  {mae:.4f} W")
    print(f"  MAPE: {mape:.4f} %")
    print(f"  WAPE: {wape:.4f} %")
    print("=" * 50)

    # Salvar CSV
    output_df = valid[['P_dc_prev', 'P_dc_real']].copy()
    output_df['Erro'] = errors
    OUTPUT_FILE = "resultado_previsao_dc.csv"
    output_df.to_csv(OUTPUT_FILE)
    print(f"\nCSV salvo em: {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    run_analysis()
