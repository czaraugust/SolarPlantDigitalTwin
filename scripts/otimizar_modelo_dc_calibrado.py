"""
Otimizacao do Modelo DC com Parametros Calibrados
Treina novas correcoes de regressao usando P_DC do SDM calibrado.
Testa multiplos metodos e compara todas as metricas.

Modelos testados:
  M1: Linear (P_pred)
  M2: Linear (P_pred, POA)
  M3: Linear (P_pred, POA, Temp)
  M4: Linear com interacao (P_pred, POA, Temp, POA*Temp)
  M5: Polinomial grau 2

Comparacao final:
  - Original SDM (puro)
  - Original SDM + M4 original
  - Calibrado SDM (puro)
  - Calibrado SDM + melhor correcao
"""

import sys
import os
# Adiciona a raiz do projeto ao Python path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import pvlib
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
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
TOTAL_MODULES = 19

DATASHEET = {
    'celltype': 'polySi',
    'v_mp': 31.7, 'i_mp': 8.52,
    'v_oc': 38.8, 'i_sc': 9.09,
    'alpha_sc': 0.005454,
    'beta_voc': -0.1164,
    'gamma_pmp': -0.40,
    'cells_in_series': 60,
}

# Parametros originais M4
M4_ORIG = {'a': 6.263008, 'b': -30.290082, 'c': -1.811529, 'd': 0.117656, 'e': 72.7470}

# Parametros calibrados (da calibrate_model_v2.py)
CAL_PARAMS = {
    'I_L_ref': 9.003492e+00,
    'I_o_ref': 1.183504e-10,
    'R_s': 3.479506e-01,
    'R_sh_ref': 2.536717e+02,
    'a_ref': 1.513942e+00,
}


def calc_metrics(p_pred, p_real):
    valid = p_real > 10
    diff = p_pred - p_real
    rmse = np.sqrt((diff ** 2).mean())
    mae = np.abs(diff).mean()
    mape = (np.abs(diff[valid]) / p_real[valid]).mean() * 100
    wape = np.abs(diff).sum() / p_real.sum() * 100
    return rmse, mae, mape, wape


def predict_sdm(params_dict, poa_global, temp_cell):
    """Calcula P_DC usando parametros SDM."""
    eff_irr = np.clip(poa_global, 0, 1400.0)
    dp = pvsystem.calcparams_desoto(
        effective_irradiance=eff_irr, temp_cell=temp_cell,
        alpha_sc=DATASHEET['alpha_sc'],
        a_ref=params_dict['a_ref'],
        I_L_ref=params_dict['I_L_ref'],
        I_o_ref=params_dict['I_o_ref'],
        R_sh_ref=params_dict['R_sh_ref'],
        R_s=params_dict['R_s'],
        EgRef=1.121, dEgdT=-0.0002677)

    IL, I0, Rs, Rsh, nNsVth = dp
    mpp = singlediode.bishop88_mpp(
        photocurrent=IL, saturation_current=I0,
        resistance_series=Rs, resistance_shunt=Rsh,
        nNsVth=nNsVth, method='newton')
    return mpp[2] * TOTAL_MODULES  # p_mp * 19


def run():
    print("=" * 75)
    print("  OTIMIZACAO M4 COM PARAMETROS CALIBRADOS + COMPARACAO COMPLETA")
    print("=" * 75)

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

    df['P_dc_real'] = (df['Voltage S1'] * df['Current S1']) + \
                      (df['Voltage S2'] * df['Current S2'])
    df = df[df['P_dc_real'] > 0]
    print(f"Registros: {len(df)}")

    # --- CALCULAR POA ---
    print("Calculando POA...")
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

    poa = poa_arr
    temp_mod = df['PV Temperature'].values
    p_real = df['P_dc_real'].values

    temp_cell = pvlib.temperature.sapm_cell_from_module(
        module_temperature=df['PV Temperature'],
        poa_global=pd.Series(poa, index=df.index), deltaT=1.0)

    # --- PARAMETROS ORIGINAIS ---
    print("\nExtaindo parametros originais...")
    stc = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'], cells_in_series=DATASHEET['cells_in_series'])

    orig_params = {
        'I_L_ref': stc[0], 'I_o_ref': stc[1], 'R_s': stc[2],
        'R_sh_ref': stc[3], 'a_ref': stc[4]
    }

    # --- CALCULAR P_DC COM AMBOS OS PARAMETROS ---
    print("Calculando P_DC com parametros originais...")
    p_dc_orig = predict_sdm(orig_params, poa, temp_cell)

    print("Calculando P_DC com parametros calibrados...")
    p_dc_cal = predict_sdm(CAL_PARAMS, poa, temp_cell)

    # --- TREINAR CORRECOES SOBRE O CALIBRADO ---
    print("\nTreinando modelos de correcao sobre SDM calibrado...")

    modelos_cal = {}

    # M1: Linear simples
    X1 = p_dc_cal.values.reshape(-1, 1) if hasattr(p_dc_cal, 'values') else p_dc_cal.reshape(-1, 1)
    reg1 = LinearRegression().fit(X1, p_real)
    modelos_cal['M1_cal'] = {'reg': reg1, 'pred': reg1.predict(X1).clip(0),
                              'desc': 'Linear(P_pred)', 'coefs': f"a={reg1.coef_[0]:.4f}, b={reg1.intercept_:.4f}"}

    # M2: Linear (P_pred, POA)
    p_dc_v = p_dc_cal.values if hasattr(p_dc_cal, 'values') else p_dc_cal
    X2 = np.column_stack([p_dc_v, poa])
    reg2 = LinearRegression().fit(X2, p_real)
    modelos_cal['M2_cal'] = {'reg': reg2, 'pred': reg2.predict(X2).clip(0),
                              'desc': 'Linear(P, POA)', 'coefs': f"a={reg2.coef_[0]:.4f}, b={reg2.coef_[1]:.4f}, c={reg2.intercept_:.4f}"}

    # M3: Linear (P_pred, POA, Temp)
    X3 = np.column_stack([p_dc_v, poa, temp_mod])
    reg3 = LinearRegression().fit(X3, p_real)
    modelos_cal['M3_cal'] = {'reg': reg3, 'pred': reg3.predict(X3).clip(0),
                              'desc': 'Linear(P, POA, T)', 'coefs': f"a={reg3.coef_[0]:.4f}, b={reg3.coef_[1]:.4f}, c={reg3.coef_[2]:.4f}, d={reg3.intercept_:.4f}"}

    # M4: Linear com interacao (P_pred, POA, Temp, POA*Temp)
    X4 = np.column_stack([p_dc_v, poa, temp_mod, poa * temp_mod])
    reg4 = LinearRegression().fit(X4, p_real)
    modelos_cal['M4_cal'] = {'reg': reg4, 'pred': reg4.predict(X4).clip(0),
                              'desc': 'Linear(P, POA, T, POA*T)',
                              'coefs': f"a={reg4.coef_[0]:.6f}, b={reg4.coef_[1]:.6f}, c={reg4.coef_[2]:.6f}, d={reg4.coef_[3]:.6f}, e={reg4.intercept_:.4f}"}

    # M5: Polinomial grau 2
    poly = PolynomialFeatures(degree=2, include_bias=False)
    X5 = poly.fit_transform(np.column_stack([p_dc_v, poa, temp_mod]))
    reg5 = LinearRegression().fit(X5, p_real)
    modelos_cal['M5_cal'] = {'reg': reg5, 'pred': reg5.predict(X5).clip(0),
                              'desc': 'Poly2(P, POA, T)', 'coefs': 'polinomial grau 2'}

    # --- TAMBEM TREINAR CORRECOES SOBRE O ORIGINAL (para comparacao justa) ---
    print("Treinando modelos de correcao sobre SDM original...")

    p_dc_o = p_dc_orig.values if hasattr(p_dc_orig, 'values') else p_dc_orig

    # M4 Original (ja temos os coefs)
    p_m4_orig = (M4_ORIG['a'] * p_dc_o +
                 M4_ORIG['b'] * poa +
                 M4_ORIG['c'] * temp_mod +
                 M4_ORIG['d'] * poa * temp_mod +
                 M4_ORIG['e'])
    p_m4_orig = np.clip(p_m4_orig, 0, None)

    # --- COMPARACAO COMPLETA ---
    print("\n" + "=" * 75)
    print("  RESULTADOS: COMPARACAO COMPLETA DE TODOS OS MODELOS")
    print("=" * 75)
    print(f"  Registros: {len(df)} | Periodo: 05:00-18:00")
    print("-" * 75)
    print(f"  {'#':<4} {'Modelo':<35} {'RMSE':>8} {'MAE':>8} {'MAPE':>8} {'WAPE':>8}")
    print("-" * 75)

    results = []

    # Baseline: Original SDM puro
    m = calc_metrics(p_dc_o, p_real)
    results.append(('1', 'Original SDM (puro)', *m))

    # Original + M4 original
    m = calc_metrics(p_m4_orig, p_real)
    results.append(('2', 'Original + M4 (atual)', *m))

    # Calibrado SDM puro
    m = calc_metrics(p_dc_v, p_real)
    results.append(('3', 'Calibrado SDM (puro)', *m))

    # Calibrado + cada modelo
    for i, (key, mod) in enumerate(modelos_cal.items()):
        m = calc_metrics(mod['pred'], p_real)
        results.append((f'{i+4}', f"Calibrado + {mod['desc']}", *m))

    for r in results:
        print(f"  {r[0]:<4} {r[1]:<35} {r[2]:>8.2f} {r[3]:>8.2f} {r[4]:>8.2f} {r[5]:>8.2f}")

    print("=" * 75)

    # Melhor modelo
    best_idx = np.argmin([r[5] for r in results])  # menor WAPE
    print(f"\n  MELHOR MODELO (por WAPE): {results[best_idx][1]} -> WAPE = {results[best_idx][5]:.2f}%")

    # --- COEFICIENTES ---
    print("\n" + "-" * 75)
    print("  COEFICIENTES DOS MODELOS CALIBRADOS")
    print("-" * 75)
    for key, mod in modelos_cal.items():
        print(f"  {key} ({mod['desc']}): {mod['coefs']}")

    # --- SALVAR ---
    output = os.path.join(RESULTS_DIR, "resultado_otimizacao_calibrado.txt")
    with open(output, 'w') as f:
        f.write("# Otimizacao M4 com Parametros Calibrados\n")
        f.write(f"# {len(df)} registros, 05:00-18:00\n\n")
        f.write(f"{'#':<4} {'Modelo':<35} {'RMSE':>8} {'MAE':>8} {'MAPE':>8} {'WAPE':>8}\n")
        f.write("-" * 75 + "\n")
        for r in results:
            f.write(f"{r[0]:<4} {r[1]:<35} {r[2]:>8.2f} {r[3]:>8.2f} {r[4]:>8.2f} {r[5]:>8.2f}\n")
        f.write(f"\nMelhor: {results[best_idx][1]} (WAPE = {results[best_idx][5]:.2f}%)\n")
        f.write("\nCoeficientes M4 Calibrado:\n")
        m4c = modelos_cal['M4_cal']
        f.write(f"  {m4c['coefs']}\n")

    print(f"\nResultados salvos: {os.path.abspath(output)}")


if __name__ == "__main__":
    run()
