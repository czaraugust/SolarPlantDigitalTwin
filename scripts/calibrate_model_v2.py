"""
Calibracao dos 5 Parametros do Modelo de Diodo Unico (SDM)
Filtro: 05:00 - 18:00 (sem restricao de irradiancia)

Otimiza I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref para minimizar RMSE
entre P_DC prevista e P_DC real.

Ao final, compara todas as metricas (RMSE, MAE, MAPE, WAPE)
entre parametros originais (CEC SAM) e calibrados.
"""

import sys
import os
# Adiciona a raiz do projeto ao Python path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import pvlib
from scipy.optimize import minimize
from pvlib import pvsystem, singlediode

from core.solar_calculator import CalculadoraSolar
from core.irradiance_calculator import calcular_componentes_irradiancia
from core.config import DATASET_16D_PATH, RESULTS_DIR

# --- CONFIGURACAO ---
CSV_PATH = DATASET_16D_PATH

LATITUDE = -9.55762188835476
LONGITUDE = -35.78094625196216
TZ_OFFSET = -3

TILT = 5.0
AZIMUTH = 0.0
ALBEDO = 0.2

S1_SERIES = 10
S2_SERIES = 9
TOTAL_MODULES = S1_SERIES + S2_SERIES

DATASHEET = {
    'celltype': 'polySi',
    'v_mp': 31.7, 'i_mp': 8.52,
    'v_oc': 38.8, 'i_sc': 9.09,
    'alpha_sc': 0.005454,
    'beta_voc': -0.1164,
    'gamma_pmp': -0.40,
    'cells_in_series': 60,
}

# M4 Coefficients
M4 = {'a': 6.263008, 'b': -30.290082, 'c': -1.811529, 'd': 0.117656, 'e': 72.7470}


def calc_metrics(p_pred, p_real, label=""):
    """Calcula RMSE, MAE, MAPE, WAPE."""
    valid = p_real > 10  # Evita divisao por zero no MAPE
    diff = p_pred - p_real
    rmse = np.sqrt((diff ** 2).mean())
    mae = np.abs(diff).mean()
    mape = (np.abs(diff[valid]) / p_real[valid]).mean() * 100
    wape = np.abs(diff).sum() / p_real.sum() * 100
    return {'label': label, 'rmse': rmse, 'mae': mae, 'mape': mape, 'wape': wape}


def predict_dc(sdm_params, poa_global, temp_cell, apply_m4=False, poa_raw=None, temp_mod_raw=None):
    """Calcula P_DC usando parametros SDM fornecidos."""
    I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = sdm_params

    eff_irr = poa_global.clip(upper=1400.0)

    dp = pvsystem.calcparams_desoto(
        effective_irradiance=eff_irr,
        temp_cell=temp_cell,
        alpha_sc=DATASHEET['alpha_sc'],
        a_ref=a_ref,
        I_L_ref=I_L_ref,
        I_o_ref=I_o_ref,
        R_sh_ref=R_sh_ref,
        R_s=R_s,
        EgRef=1.121,
        dEgdT=-0.0002677
    )

    IL, I0, Rs, Rsh, nNsVth = dp

    mpp_res = singlediode.bishop88_mpp(
        photocurrent=IL,
        saturation_current=I0,
        resistance_series=Rs,
        resistance_shunt=Rsh,
        nNsVth=nNsVth,
        method='newton'
    )
    p_mp = mpp_res[2]  # p_mp por modulo
    p_dc = p_mp * TOTAL_MODULES

    if apply_m4 and poa_raw is not None and temp_mod_raw is not None:
        p_dc_m4 = (M4['a'] * p_dc +
                   M4['b'] * poa_raw +
                   M4['c'] * temp_mod_raw +
                   M4['d'] * poa_raw * temp_mod_raw +
                   M4['e'])
        p_dc_m4 = np.clip(p_dc_m4, 0, None)
        return p_dc, p_dc_m4

    return p_dc, None


def objective(params, poa_global, temp_cell, p_real):
    """Funcao objetivo: RMSE."""
    I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = params
    try:
        eff_irr = poa_global.clip(upper=1400.0)
        dp = pvsystem.calcparams_desoto(
            effective_irradiance=eff_irr, temp_cell=temp_cell,
            alpha_sc=DATASHEET['alpha_sc'],
            a_ref=a_ref, I_L_ref=I_L_ref, I_o_ref=I_o_ref,
            R_sh_ref=R_sh_ref, R_s=R_s,
            EgRef=1.121, dEgdT=-0.0002677)

        IL, I0, Rs, Rsh, nNsVth = dp
        mpp_res = singlediode.bishop88_mpp(
            photocurrent=IL, saturation_current=I0,
            resistance_series=Rs, resistance_shunt=Rsh,
            nNsVth=nNsVth, method='newton')

        p_model = mpp_res[2] * TOTAL_MODULES
        rmse = np.sqrt(((p_model - p_real) ** 2).mean())
        return rmse if not np.isnan(rmse) else 1e9
    except Exception:
        return 1e9


def run():
    print("=" * 70)
    print("  CALIBRACAO DOS PARAMETROS SDM + COMPARACAO DE METRICAS")
    print("=" * 70)

    # --- CARREGAR DADOS ---
    print("\nCarregando CSV...")
    df = pd.read_csv(CSV_PATH)
    df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str))
    df = df.set_index('datetime')
    df = df.between_time('05:00', '18:00')

    df['Wind Speed'] = pd.to_numeric(df['Wind Speed'], errors='coerce') / 3.6
    cols = ['Amb. Temperature', 'Irradiance', 'PV Temperature',
            'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2']
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=cols + ['Wind Speed'])

    # P_DC Real
    df['P_dc_real'] = (df['Voltage S1'] * df['Current S1']) + \
                      (df['Voltage S2'] * df['Current S2'])
    # Filtrar P_real > 0
    df = df[df['P_dc_real'] > 0]
    print(f"Registros validos: {len(df)}")

    # --- CALCULAR POA ---
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
    temp_cell = pvlib.temperature.sapm_cell_from_module(
        module_temperature=df['PV Temperature'], poa_global=poa_global, deltaT=1.0)
    p_real = df['P_dc_real'].values

    # --- PARAMETROS ORIGINAIS (CEC SAM) ---
    print("\nExtraindo parametros originais (CEC SAM)...")
    stc = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'], cells_in_series=DATASHEET['cells_in_series'])

    original_params = np.array(stc[0:5])
    names = ['I_L_ref', 'I_o_ref', 'R_s', 'R_sh_ref', 'a_ref']

    print("\nParametros Originais (CEC SAM):")
    for i in range(5):
        print(f"  {names[i]:<10}: {original_params[i]:.6e}")

    # --- OTIMIZACAO ---
    print("\nOtimizando parametros SDM (L-BFGS-B)...")
    print(f"  Dados: {len(df)} registros (05:00-18:00, sem restricao de irradiancia)")

    bounds = [
        (original_params[0] * 0.7, original_params[0] * 1.3),  # I_L_ref
        (1e-13, 1e-7),                                          # I_o_ref
        (0.01, 2.0),                                             # R_s
        (5.0, 5000.0),                                           # R_sh_ref
        (0.5, 3.0),                                              # a_ref
    ]

    result = minimize(
        objective, original_params,
        args=(poa_global, temp_cell, p_real),
        method='L-BFGS-B',
        bounds=bounds,
        options={'disp': True, 'maxiter': 500, 'ftol': 1e-6}
    )

    cal_params = result.x
    print(f"\nOtimizacao concluida: Success={result.success}")

    print("\nParametros Calibrados:")
    for i in range(5):
        var = ((cal_params[i] - original_params[i]) / original_params[i]) * 100
        print(f"  {names[i]:<10}: {cal_params[i]:.6e}  (Var: {var:+.2f}%)")

    # --- CALCULAR PREVISOES ---
    print("\nCalculando previsoes para comparacao...")

    # 1. Original (SDM puro)
    p_orig_raw, _ = predict_dc(original_params, poa_global, temp_cell)

    # 2. Original + M4
    _, p_orig_m4 = predict_dc(original_params, poa_global, temp_cell,
                               apply_m4=True, poa_raw=poa_arr, temp_mod_raw=df['PV Temperature'].values)

    # 3. Calibrado (SDM puro)
    p_cal_raw, _ = predict_dc(cal_params, poa_global, temp_cell)

    # 4. Calibrado + M4
    _, p_cal_m4 = predict_dc(cal_params, poa_global, temp_cell,
                              apply_m4=True, poa_raw=poa_arr, temp_mod_raw=df['PV Temperature'].values)

    # --- METRICAS ---
    metrics = [
        calc_metrics(p_orig_raw, p_real, "Original (SDM puro)"),
        calc_metrics(p_orig_m4, p_real, "Original + M4"),
        calc_metrics(p_cal_raw, p_real, "Calibrado (SDM puro)"),
        calc_metrics(p_cal_m4, p_real, "Calibrado + M4"),
    ]

    print("\n" + "=" * 70)
    print("  COMPARACAO DE METRICAS — P_DC PREVISTA vs P_DC REAL")
    print("=" * 70)
    print(f"  Periodo: 05:00-18:00 | Registros: {len(df)}")
    print("-" * 70)
    print(f"  {'Modelo':<25} {'RMSE (W)':>10} {'MAE (W)':>10} {'MAPE (%)':>10} {'WAPE (%)':>10}")
    print("-" * 70)
    for m in metrics:
        print(f"  {m['label']:<25} {m['rmse']:>10.2f} {m['mae']:>10.2f} {m['mape']:>10.2f} {m['wape']:>10.2f}")
    print("=" * 70)

    # --- SALVAR RESULTADOS ---
    output = os.path.join(RESULTS_DIR, "calibration_results_v2.txt")
    with open(output, 'w') as f:
        f.write("# Parametros Calibrados (Single Diode Model) - v2\n")
        f.write(f"# Filtro: 05:00-18:00, {len(df)} registros, sem restricao de irradiancia\n")
        f.write(f"# RMSE: {metrics[0]['rmse']:.2f} W (original) -> {metrics[2]['rmse']:.2f} W (calibrado)\n")
        f.write("-" * 40 + "\n")
        for i in range(5):
            f.write(f"{names[i]} = {cal_params[i]:.6e}\n")
        f.write("\n# COMPARACAO COMPLETA\n")
        f.write(f"{'Modelo':<25} {'RMSE':>10} {'MAE':>10} {'MAPE':>10} {'WAPE':>10}\n")
        for m in metrics:
            f.write(f"{m['label']:<25} {m['rmse']:>10.2f} {m['mae']:>10.2f} {m['mape']:>10.2f} {m['wape']:>10.2f}\n")

    print(f"\nResultados salvos: {os.path.abspath(output)}")


if __name__ == "__main__":
    run()
