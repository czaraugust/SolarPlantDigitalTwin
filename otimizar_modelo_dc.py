"""
Otimização do Modelo Elétrico DC
Analisa o erro entre P_DC previsto e P_DC real, e encontra fórmulas de
correção que minimizem o erro.

Abordagens testadas:
1. Fator de escala simples (k)
2. Regressão linear (a*P_pred + b)
3. Correção polinomial por irradiância
4. Correção multivariável (irradiância + temperatura)
5. Regressão polinomial completa
"""

import pandas as pd
import numpy as np
import pvlib
import os
import sys
from scipy.optimize import minimize
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from sklearn.metrics import mean_squared_error, mean_absolute_error

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
TOTAL_MODULES = S1_SERIES + S2_SERIES

TILT = 5.0
AZIMUTH = 0.0
ALBEDO = 0.2
MIN_POWER = 10.0


def calc_metrics(y_pred, y_real):
    """Calcula MSE, RMSE, MAE, MAPE, WAPE."""
    errors = y_pred - y_real
    mse = (errors ** 2).mean()
    rmse = np.sqrt(mse)
    mae = np.abs(errors).mean()
    mask = y_real > MIN_POWER
    mape = (np.abs(errors[mask]) / y_real[mask]).mean() * 100
    wape = np.abs(errors).sum() / y_real.sum() * 100
    return {'MSE': mse, 'RMSE': rmse, 'MAE': mae, 'MAPE': mape, 'WAPE': wape}


def print_metrics(name, metrics):
    print(f"  [{name}]")
    print(f"    RMSE: {metrics['RMSE']:.2f} W | MAE: {metrics['MAE']:.2f} W | "
          f"MAPE: {metrics['MAPE']:.2f}% | WAPE: {metrics['WAPE']:.2f}%")


def run():
    # =====================
    # PREPARAÇÃO DOS DADOS
    # =====================
    print("=== OTIMIZAÇÃO DO MODELO DC ===\n")
    print(f"Carregando CSV: {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)

    df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str))
    df = df.set_index('datetime')
    df = df.between_time('05:00', '18:00')

    df['Wind Speed'] = pd.to_numeric(df['Wind Speed'], errors='coerce') / 3.6
    cols_numeric = ['Amb. Temperature', 'Irradiance', 'PV Temperature',
                    'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2']
    for col in cols_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=cols_numeric + ['Wind Speed'])

    # P_DC Real
    df['P_dc_real'] = (df['Voltage S1'] * df['Current S1']) + \
                      (df['Voltage S2'] * df['Current S2'])

    # =====================
    # CÁLCULOS SOLARES
    # =====================
    print(f"Calculando irradiância POA para {len(df)} registros...")
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

    df['POA'] = poa_arr
    poa = pd.Series(poa_arr, index=df.index)

    # Temperatura SAPM
    temp_cell = pvlib.temperature.sapm_cell_from_module(
        module_temperature=df['PV Temperature'], poa_global=poa, deltaT=1.0)

    # Single Diode (baseline)
    print("Calculando P_DC baseline (single diode)...")
    stc = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'], cells_in_series=DATASHEET['cells_in_series'])

    I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = stc[0:5]

    eff_irr = poa.clip(upper=1400.0)
    dp = pvlib.pvsystem.calcparams_desoto(
        effective_irradiance=eff_irr, temp_cell=temp_cell,
        alpha_sc=DATASHEET['alpha_sc'],
        a_ref=a_ref, I_L_ref=I_L_ref, I_o_ref=I_o_ref,
        R_sh_ref=R_sh_ref, R_s=R_s,
        EgRef=1.121, dEgdT=-0.0002677)

    IL, I0, Rs, Rsh, nNsVth = dp
    sd_result = pvlib.pvsystem.singlediode(
        photocurrent=IL, saturation_current=I0,
        resistance_series=Rs, resistance_shunt=Rsh,
        nNsVth=nNsVth, method='lambertw')
    p_mp = sd_result['p_mp']

    df['P_dc_pred'] = p_mp * TOTAL_MODULES

    # Filtrar para métricas
    valid = df[df['P_dc_real'] > MIN_POWER].copy()
    print(f"Registros válidos: {len(valid)}\n")

    y_real = valid['P_dc_real'].values
    y_pred = valid['P_dc_pred'].values
    irr = valid['POA'].values
    temp = valid['PV Temperature'].values
    ghi = valid['Irradiance'].values

    # =====================
    # BASELINE
    # =====================
    print("=" * 60)
    print("BASELINE (Modelo Atual - Single Diode + SAPM)")
    print("=" * 60)
    base_metrics = calc_metrics(y_pred, y_real)
    print_metrics("Baseline", base_metrics)

    # =====================
    # MODELO 1: Fator de Escala
    # =====================
    print("\n" + "-" * 60)
    print("MODELO 1: Fator de Escala Linear (P_corr = k * P_pred)")
    print("-" * 60)
    k_opt = y_real.sum() / y_pred.sum()
    y_m1 = y_pred * k_opt
    m1_metrics = calc_metrics(y_m1, y_real)
    print(f"  k = {k_opt:.6f}")
    print_metrics("Escala", m1_metrics)

    # =====================
    # MODELO 2: Regressão Linear
    # =====================
    print("\n" + "-" * 60)
    print("MODELO 2: Regressão Linear (P_corr = a*P_pred + b)")
    print("-" * 60)
    reg2 = LinearRegression().fit(y_pred.reshape(-1, 1), y_real)
    y_m2 = reg2.predict(y_pred.reshape(-1, 1))
    m2_metrics = calc_metrics(y_m2, y_real)
    print(f"  a = {reg2.coef_[0]:.6f}, b = {reg2.intercept_:.4f}")
    print_metrics("Linear", m2_metrics)

    # =====================
    # MODELO 3: Regressão com Irradiância
    # =====================
    print("\n" + "-" * 60)
    print("MODELO 3: P_corr = a*P_pred + b*POA + c*POA² + d")
    print("-" * 60)
    X3 = np.column_stack([y_pred, irr, irr**2])
    reg3 = LinearRegression().fit(X3, y_real)
    y_m3 = reg3.predict(X3)
    m3_metrics = calc_metrics(y_m3, y_real)
    print(f"  Coefs: {reg3.coef_}, intercept: {reg3.intercept_:.4f}")
    print_metrics("POA Quad.", m3_metrics)

    # =====================
    # MODELO 4: Multivariável (P_pred + POA + Temp)
    # =====================
    print("\n" + "-" * 60)
    print("MODELO 4: P_corr = a*P_pred + b*POA + c*Temp + d*POA*Temp + e")
    print("-" * 60)
    X4 = np.column_stack([y_pred, irr, temp, irr * temp])
    reg4 = LinearRegression().fit(X4, y_real)
    y_m4 = reg4.predict(X4)
    m4_metrics = calc_metrics(y_m4, y_real)
    print(f"  Coefs: {np.round(reg4.coef_, 6)}, intercept: {reg4.intercept_:.4f}")
    print_metrics("Multi", m4_metrics)

    # =====================
    # MODELO 5: Polinomial Grau 2 (P_pred, POA, Temp)
    # =====================
    print("\n" + "-" * 60)
    print("MODELO 5: Polinomial Grau 2 (P_pred, POA, Temp)")
    print("-" * 60)
    X5_raw = np.column_stack([y_pred, irr, temp])
    poly = PolynomialFeatures(degree=2, include_bias=False)
    X5 = poly.fit_transform(X5_raw)
    reg5 = LinearRegression().fit(X5, y_real)
    y_m5 = reg5.predict(X5)
    m5_metrics = calc_metrics(y_m5, y_real)
    feat_names = poly.get_feature_names_out(['P_pred', 'POA', 'Temp'])
    print(f"  Features: {feat_names.tolist()}")
    print(f"  Coefs: {np.round(reg5.coef_, 6)}")
    print(f"  Intercept: {reg5.intercept_:.4f}")
    print_metrics("Poly2", m5_metrics)

    # =====================
    # MODELO 6: Fórmula simples com GHI (regressão direta)
    # =====================
    print("\n" + "-" * 60)
    print("MODELO 6: Fórmula Direta P_dc = a*GHI + b*GHI² + c*Temp + d")
    print("-" * 60)
    X6 = np.column_stack([ghi, ghi**2, temp])
    reg6 = LinearRegression().fit(X6, y_real)
    y_m6 = reg6.predict(X6)
    m6_metrics = calc_metrics(y_m6, y_real)
    print(f"  P_dc = {reg6.coef_[0]:.6f}*GHI + {reg6.coef_[1]:.9f}*GHI² + "
          f"{reg6.coef_[2]:.4f}*Temp + {reg6.intercept_:.4f}")
    print_metrics("GHI Direto", m6_metrics)

    # =====================
    # RESUMO COMPARATIVO
    # =====================
    print("\n" + "=" * 60)
    print("RESUMO COMPARATIVO")
    print("=" * 60)
    all_models = [
        ("Baseline (SD+SAPM)", base_metrics),
        ("M1: Escala (k)", m1_metrics),
        ("M2: Linear (a,b)", m2_metrics),
        ("M3: POA Quad.", m3_metrics),
        ("M4: Multi (POA+T)", m4_metrics),
        ("M5: Poly2", m5_metrics),
        ("M6: GHI Direto", m6_metrics),
    ]
    print(f"  {'Modelo':<25} {'RMSE':>8} {'MAE':>8} {'MAPE':>8} {'WAPE':>8}")
    print("  " + "-" * 57)
    for name, m in all_models:
        print(f"  {name:<25} {m['RMSE']:>7.2f}W {m['MAE']:>7.2f}W "
              f"{m['MAPE']:>7.2f}% {m['WAPE']:>7.2f}%")

    # Salvar resultados
    results_df = valid[['POA', 'PV Temperature', 'Irradiance',
                        'P_dc_pred', 'P_dc_real']].copy()
    results_df['M1_Escala'] = y_m1
    results_df['M2_Linear'] = y_m2
    results_df['M5_Poly2'] = y_m5
    results_df['M6_GHI'] = y_m6
    results_df.to_csv("resultado_otimizacao_dc.csv")
    print(f"\nCSV salvo: {os.path.abspath('resultado_otimizacao_dc.csv')}")

    # Melhor modelo
    best = min(all_models, key=lambda x: x[1]['RMSE'])
    print(f"\n*** MELHOR MODELO: {best[0]} (RMSE={best[1]['RMSE']:.2f}W) ***")


if __name__ == "__main__":
    run()
