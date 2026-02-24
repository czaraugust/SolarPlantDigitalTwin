"""
Headless Inversor Simulado - Análise completa do dataset
Replica a lógica da aba "Inversor - Simulado" sem interface gráfica.

Fluxo:
1. Carrega CSV -> calcula posição solar e POA irradiância (custom calculators)
2. Calcula temperatura de célula via SAPM (sensor + ΔT)
3. Calcula P_DC via single diode model (pvlib) para config [10s + 9s]
4. Aplica fórmula de eficiência: Eff = 96.8016 - 9653.1352/P_DC - 0.000125*P_DC
5. P_AC_simulado = P_DC * (Eff / 100)
6. Compara P_AC_simulado vs P_AC_real (coluna 'Power' do CSV)
7. Calcula métricas: MSE, MAE, RMSE, MAPE, WAPE
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

# Localização
LATITUDE = -9.55762188835476
LONGITUDE = -35.78094625196216
TZ_OFFSET = -3

# Painel (JKM270PP)
DATASHEET = {
    'celltype': 'polySi',
    'v_mp': 31.7, 'i_mp': 8.52,
    'v_oc': 38.8, 'i_sc': 9.09,
    'alpha_sc': 0.005454,
    'beta_voc': -0.1164,
    'gamma_pmp': -0.40,
    'cells_in_series': 60,
}

# Configuração da Planta (como na aba Inversor Simulado)
S1_SERIES = 10  # String 1: 10 painéis em série
S2_SERIES = 9   # String 2: 9 painéis em série
TOTAL_MODULES = S1_SERIES + S2_SERIES  # = 19

# Array
TILT = 5.0
AZIMUTH = 0.0
ALBEDO = 0.2

# Inversor
V_PARTIDA = 120.0  # V - tensão de partida


def efficiency_formula(p_dc):
    """Fórmula de eficiência do inversor (ajustada com R²=0.905)"""
    return 96.8016 - (9653.1352 / p_dc) - (0.000125 * p_dc)


def run_analysis():
    print(f"Carregando CSV: {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)

    # Preparar Dados
    print("Preparando dados...")
    df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str))
    df = df.set_index('datetime')
    df = df.between_time('05:00', '18:00')

    if len(df) == 0:
        print("Nenhum dado encontrado.")
        return

    # Conversão de Unidades
    df['Wind Speed'] = pd.to_numeric(df['Wind Speed'], errors='coerce') / 3.6

    cols_numeric = ['Amb. Temperature', 'Irradiance', 'PV Temperature',
                    'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2', 'Power']
    for col in cols_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna(subset=cols_numeric + ['Wind Speed'])
    print(f"Registros válidos: {len(df)}")

    # P_AC Real (do CSV)
    df['P_ac_real'] = df['Power']

    # --- CÁLCULO SOLAR E IRRADIÂNCIA ---
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

    # --- TEMPERATURA DE CÉLULA (SAPM) ---
    print("Calculando temperatura de célula (SAPM)...")
    # SAPM: Tcell = Tmodule_sensor + (POA / 1000) * deltaT
    temp_cell_sapm = pvlib.temperature.sapm_cell_from_module(
        module_temperature=df['PV Temperature'],
        poa_global=poa_global,
        deltaT=1.0)

    # --- CÁLCULO ELÉTRICO (Single Diode) ---
    print("Estimando parâmetros elétricos (DeSoto + LambertW)...")
    stc_params = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'], cells_in_series=DATASHEET['cells_in_series'])

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

    # P_DC Total (19 módulos = 10 + 9)
    df['P_dc_raw'] = p_mp * TOTAL_MODULES

    # --- CORREÇÃO M4 (Regressão Multivariável) ---
    M4 = {'a': 6.263008, 'b': -30.290082, 'c': -1.811529, 'd': 0.117656, 'e': 72.7470}
    df['P_dc'] = (M4['a'] * df['P_dc_raw'] +
                  M4['b'] * poa_global +
                  M4['c'] * df['PV Temperature'] +
                  M4['d'] * poa_global * df['PV Temperature'] +
                  M4['e'])
    df['P_dc'] = df['P_dc'].clip(lower=0.0)
    print(f"P_DC calculado com correção M4 (config: {S1_SERIES}s + {S2_SERIES}s = {TOTAL_MODULES} módulos)")

    # --- MÁQUINA DE ESTADOS ---
    print("Aplicando máquina de estados do inversor...")
    sm = InverterStateMachine(v_partida=V_PARTIDA)

    v_s1_arr = df['Voltage S1'].values
    v_s2_arr = df['Voltage S2'].values
    p_dc_arr = df['P_dc'].values

    estado_arr = []
    p_ac_sim_arr = np.zeros(len(df))

    for i in range(len(df)):
        estado = sm.step(v_s1_arr[i], v_s2_arr[i], p_dc_arr[i])
        estado_arr.append(estado)

        if estado == InverterStateMachine.LIGADO and p_dc_arr[i] > 50:
            eff = efficiency_formula(p_dc_arr[i])
            if eff > 0:
                p_ac_sim_arr[i] = p_dc_arr[i] * (eff / 100.0)

    df['Estado'] = estado_arr
    df['Eff'] = np.where(df['P_dc'] > 50, efficiency_formula(df['P_dc']), 0.0)
    df['Eff'] = df['Eff'].clip(lower=0.0)
    df['P_ac_sim'] = p_ac_sim_arr

    # Stats de estado
    n_ligado = (df['Estado'] == 'LIGADO').sum()
    n_desligado = (df['Estado'] == 'DESLIGADO').sum()
    print(f"  LIGADO: {n_ligado} min | DESLIGADO: {n_desligado} min")

    # --- CÁLCULO DE MÉTRICAS ---
    print("\n--- Calculando métricas (P_AC Simulado vs P_AC Real) ---")

    # Filtrar apenas registros com potência real significativa
    valid = df[df['P_ac_real'] > 10].copy()
    print(f"Registros válidos para métricas (P_ac_real > 10W): {len(valid)}")

    errors = valid['P_ac_sim'] - valid['P_ac_real']

    mse = (errors ** 2).mean()
    rmse = np.sqrt(mse)
    mae = errors.abs().mean()
    mape = (errors.abs() / valid['P_ac_real']).mean() * 100
    wape = (errors.abs().sum() / valid['P_ac_real'].sum()) * 100

    print("\n" + "=" * 50)
    print("  RESULTADOS: Inversor Simulado vs Real (AC)")
    print("=" * 50)
    print(f"  Configuração: String 1 = {S1_SERIES}s, String 2 = {S2_SERIES}s")
    print(f"  Total Módulos: {TOTAL_MODULES}")
    print(f"  Fórmula Eff: 96.8016 - 9653.1352/Pdc - 0.000125*Pdc")
    print(f"  V_PARTIDA: {V_PARTIDA} V | P_STANDBY: {InverterStateMachine.P_STANDBY} W | ATRASO: {InverterStateMachine.TEMPO_ATRASO} min")
    print(f"  Estado: LIGADO={n_ligado}min DESLIGADO={n_desligado}min")
    print("-" * 50)
    print(f"  MSE:  {mse:.4f} W²")
    print(f"  RMSE: {rmse:.4f} W")
    print(f"  MAE:  {mae:.4f} W")
    print(f"  MAPE: {mape:.4f} %")
    print(f"  WAPE: {wape:.4f} %")
    print("=" * 50)

    # Salvar CSV comparativo
    output_df = valid[['P_dc', 'Eff', 'P_ac_sim', 'P_ac_real', 'Estado']].copy()
    output_df['Erro'] = errors
    OUTPUT_FILE = "resultado_inversor_simulado.csv"
    output_df.to_csv(OUTPUT_FILE)
    print(f"\nCSV comparativo salvo em: {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    run_analysis()
