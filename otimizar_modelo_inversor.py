"""
Otimização do Modelo do Inversor (DC → AC)
Analisa o erro entre P_AC simulado e P_AC real, testando diferentes
modelos de eficiência para a conversão DC→AC.

Entrada: P_DC REAL (medido) — para isolar o erro do INVERSOR apenas.
Saída:   P_AC comparado contra P_AC REAL.

Modelos testados:
1. Baseline: Eff = 96.8016 - 9653.1352/Pdc - 0.000125*Pdc
2. Regressão linear (P_ac = a*P_dc + b)
3. Polinomial grau 2 (P_dc)
4. Multi-variável (P_dc + Temp)
5. Multi-variável (P_dc + Temp + P_dc*Temp)
6. Polinomial completo grau 2 (P_dc, Temp)
7. Eficiência com temperatura: Eff = f(P_dc, Temp)
"""

import pandas as pd
import numpy as np
import os
import sys
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# --- CONFIGURAÇÃO ---
CSV_PATH = r"C:\Users\55829\Downloads\PESSOAIS\MESTRADO\PESQUISA\PROJETO_GEMEO_DIGITAL_SOLAR\DATASET_MESTRE_COMPLETO.csv"
MIN_POWER = 10.0


def efficiency_baseline(p_dc):
    """Fórmula de eficiência atual (R²=0.905)"""
    return 96.8016 - (9653.1352 / p_dc) - (0.000125 * p_dc)


def calc_metrics(y_pred, y_real, min_power=10.0):
    """Calcula métricas de erro."""
    mask = y_real > min_power
    y_p = y_pred[mask]
    y_r = y_real[mask]
    errors = y_p - y_r
    mse = (errors ** 2).mean()
    rmse = np.sqrt(mse)
    mae = np.abs(errors).mean()
    mape = (np.abs(errors) / y_r).mean() * 100
    wape = np.abs(errors).sum() / y_r.sum() * 100
    return {'RMSE': rmse, 'MAE': mae, 'MAPE': mape, 'WAPE': wape, 'n': len(y_r)}


def print_metrics(name, m):
    print(f"  [{name}]")
    print(f"    RMSE: {m['RMSE']:.2f} W | MAE: {m['MAE']:.2f} W | "
          f"MAPE: {m['MAPE']:.2f}% | WAPE: {m['WAPE']:.2f}%")


def run():
    print("=== OTIMIZACAO DO MODELO DO INVERSOR (DC->AC) ===\n")
    print(f"Carregando CSV: {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH)

    df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str))
    df = df.set_index('datetime')
    df = df.between_time('05:00', '18:00')

    cols_numeric = ['Amb. Temperature', 'Irradiance', 'PV Temperature',
                    'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2', 'Power']
    for col in cols_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna(subset=cols_numeric)
    print(f"Registros totais: {len(df)}")

    # P_DC Real (S1 + S2)
    df['P_dc'] = (df['Voltage S1'] * df['Current S1']) + \
                 (df['Voltage S2'] * df['Current S2'])

    # P_AC Real
    df['P_ac_real'] = df['Power']

    # Temperatura do módulo (sensor)
    df['Temp'] = df['PV Temperature']

    # Temperatura ambiente
    df['Tamb'] = df['Amb. Temperature']

    # Filtrar P_dc > 50 (onde a fórmula de eficiência é válida) e P_ac > 10
    valid = df[(df['P_dc'] > 50) & (df['P_ac_real'] > MIN_POWER)].copy()
    print(f"Registros válidos (P_dc>50 & P_ac>{MIN_POWER}): {len(valid)}\n")

    p_dc = valid['P_dc'].values
    p_ac_real = valid['P_ac_real'].values
    temp = valid['Temp'].values
    tamb = valid['Tamb'].values

    # =====================
    # BASELINE
    # =====================
    print("=" * 65)
    print("BASELINE: Eff = 96.8016 - 9653.1352/Pdc - 0.000125*Pdc")
    print("=" * 65)
    eff_base = np.clip(efficiency_baseline(p_dc), 0, 100)
    p_ac_base = p_dc * (eff_base / 100.0)
    base_m = calc_metrics(p_ac_base, p_ac_real)
    print_metrics("Baseline", base_m)

    # =====================
    # MODELO 1: Regressão Linear Direta (P_ac = a*P_dc + b)
    # =====================
    print("\n" + "-" * 65)
    print("MODELO 1: P_ac = a*P_dc + b")
    print("-" * 65)
    reg1 = LinearRegression().fit(p_dc.reshape(-1, 1), p_ac_real)
    y_m1 = reg1.predict(p_dc.reshape(-1, 1))
    m1 = calc_metrics(y_m1, p_ac_real)
    print(f"  a = {reg1.coef_[0]:.6f}, b = {reg1.intercept_:.4f}")
    print_metrics("Linear DC→AC", m1)

    # =====================
    # MODELO 2: Polinomial grau 2 em P_dc
    # =====================
    print("\n" + "-" * 65)
    print("MODELO 2: P_ac = a*P_dc + b*P_dc² + c")
    print("-" * 65)
    X2 = np.column_stack([p_dc, p_dc**2])
    reg2 = LinearRegression().fit(X2, p_ac_real)
    y_m2 = reg2.predict(X2)
    m2 = calc_metrics(y_m2, p_ac_real)
    print(f"  a = {reg2.coef_[0]:.6f}, b = {reg2.coef_[1]:.10f}, c = {reg2.intercept_:.4f}")
    print_metrics("Poly2 DC", m2)

    # =====================
    # MODELO 3: Multivariável (P_dc + Temp)
    # =====================
    print("\n" + "-" * 65)
    print("MODELO 3: P_ac = a*P_dc + b*Temp + c")
    print("-" * 65)
    X3 = np.column_stack([p_dc, temp])
    reg3 = LinearRegression().fit(X3, p_ac_real)
    y_m3 = reg3.predict(X3)
    m3 = calc_metrics(y_m3, p_ac_real)
    print(f"  a = {reg3.coef_[0]:.6f}, b = {reg3.coef_[1]:.6f}, c = {reg3.intercept_:.4f}")
    print_metrics("DC+Temp", m3)

    # =====================
    # MODELO 4: Multi com interação (P_dc + Temp + P_dc*Temp)
    # =====================
    print("\n" + "-" * 65)
    print("MODELO 4: P_ac = a*P_dc + b*Temp + c*P_dc*Temp + d")
    print("-" * 65)
    X4 = np.column_stack([p_dc, temp, p_dc * temp])
    reg4 = LinearRegression().fit(X4, p_ac_real)
    y_m4 = reg4.predict(X4)
    m4 = calc_metrics(y_m4, p_ac_real)
    print(f"  Coefs: {np.round(reg4.coef_, 6)}, intercept: {reg4.intercept_:.4f}")
    print_metrics("DC+Temp+Interação", m4)

    # =====================
    # MODELO 5: Polinomial Grau 2 Completo (P_dc, Temp)
    # =====================
    print("\n" + "-" * 65)
    print("MODELO 5: Polinomial Grau 2 (P_dc, Temp)")
    print("-" * 65)
    X5_raw = np.column_stack([p_dc, temp])
    poly5 = PolynomialFeatures(degree=2, include_bias=False)
    X5 = poly5.fit_transform(X5_raw)
    reg5 = LinearRegression().fit(X5, p_ac_real)
    y_m5 = reg5.predict(X5)
    m5 = calc_metrics(y_m5, p_ac_real)
    feat5 = poly5.get_feature_names_out(['Pdc', 'Temp'])
    print(f"  Features: {feat5.tolist()}")
    print(f"  Coefs: {np.round(reg5.coef_, 8)}")
    print(f"  Intercept: {reg5.intercept_:.4f}")
    print_metrics("Poly2 (Pdc,Temp)", m5)

    # =====================
    # MODELO 6: Polinomial Grau 3 em P_dc apenas
    # =====================
    print("\n" + "-" * 65)
    print("MODELO 6: P_ac = a*P_dc + b*P_dc² + c*P_dc³ + d")
    print("-" * 65)
    X6 = np.column_stack([p_dc, p_dc**2, p_dc**3])
    reg6 = LinearRegression().fit(X6, p_ac_real)
    y_m6 = reg6.predict(X6)
    m6 = calc_metrics(y_m6, p_ac_real)
    print(f"  Coefs: {reg6.coef_}")
    print(f"  Intercept: {reg6.intercept_:.4f}")
    print_metrics("Poly3 DC", m6)

    # =====================
    # MODELO 7: Re-otimizar a fórmula 1/x (mesmo formato, novos coefs)
    # =====================
    print("\n" + "-" * 65)
    print("MODELO 7: Eff = a - b/P_dc - c*P_dc (mesma forma, coefs otimizados)")
    print("-" * 65)
    # Eficiência real
    eff_real = np.where(p_dc > 50, (p_ac_real / p_dc) * 100, 0)
    X7 = np.column_stack([np.ones(len(p_dc)), -1.0 / p_dc, -p_dc])
    reg7 = LinearRegression(fit_intercept=False).fit(X7, eff_real)
    eff_m7 = reg7.predict(X7)
    eff_m7 = np.clip(eff_m7, 0, 100)
    y_m7 = p_dc * (eff_m7 / 100.0)
    m7 = calc_metrics(y_m7, p_ac_real)
    print(f"  Eff = {reg7.coef_[0]:.4f} - {reg7.coef_[1]:.4f}/P_dc - {reg7.coef_[2]:.8f}*P_dc")
    print_metrics("Eff Refit", m7)

    # =====================
    # MODELO 8: Eficiência com temperatura
    # =====================
    print("\n" + "-" * 65)
    print("MODELO 8: Eff = a - b/P_dc - c*P_dc + d*Temp + e*Temp/P_dc")
    print("-" * 65)
    X8 = np.column_stack([np.ones(len(p_dc)), -1.0/p_dc, -p_dc, temp, temp/p_dc])
    reg8 = LinearRegression(fit_intercept=False).fit(X8, eff_real)
    eff_m8 = np.clip(reg8.predict(X8), 0, 100)
    y_m8 = p_dc * (eff_m8 / 100.0)
    m8 = calc_metrics(y_m8, p_ac_real)
    print(f"  Coefs: {np.round(reg8.coef_, 6)}")
    print_metrics("Eff+Temp", m8)

    # =====================
    # RESUMO COMPARATIVO
    # =====================
    print("\n" + "=" * 65)
    print("RESUMO COMPARATIVO — MODELO DO INVERSOR")
    print("=" * 65)
    all_models = [
        ("Baseline (Eff atual)", base_m),
        ("M1: Linear DC→AC", m1),
        ("M2: Poly2 DC", m2),
        ("M3: DC+Temp", m3),
        ("M4: DC+Temp+Interação", m4),
        ("M5: Poly2 (Pdc,Temp)", m5),
        ("M6: Poly3 DC", m6),
        ("M7: Eff Refit", m7),
        ("M8: Eff+Temp", m8),
    ]
    print(f"  {'Modelo':<28} {'RMSE':>8} {'MAE':>8} {'MAPE':>8} {'WAPE':>8}")
    print("  " + "-" * 60)
    for name, m in all_models:
        print(f"  {name:<28} {m['RMSE']:>7.2f}W {m['MAE']:>7.2f}W "
              f"{m['MAPE']:>7.2f}% {m['WAPE']:>7.2f}%")

    best = min(all_models, key=lambda x: x[1]['RMSE'])
    print(f"\n*** MELHOR MODELO: {best[0]} (RMSE={best[1]['RMSE']:.2f}W) ***")

    # Salvar
    results_df = valid[['P_dc', 'Temp', 'P_ac_real']].copy()
    results_df['Baseline'] = p_ac_base
    results_df['M5_Poly2'] = y_m5
    results_df['M7_EffRefit'] = y_m7
    results_df['M8_EffTemp'] = y_m8
    results_df.to_csv("resultado_otimizacao_inversor.csv")
    print(f"\nCSV salvo: {os.path.abspath('resultado_otimizacao_inversor.csv')}")


if __name__ == "__main__":
    run()
