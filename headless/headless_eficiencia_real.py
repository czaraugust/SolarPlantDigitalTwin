"""
Headless Eficiência Real - Valida a fórmula de eficiência do inversor
usando a Potência DC REAL (medida) como entrada.

Fluxo:
1. Carrega CSV
2. P_DC_real = (V_s1 * I_s1) + (V_s2 * I_s2)
3. Aplica fórmula: Eff = 96.8016 - 9653.1352/P_dc_real - 0.000125*P_dc_real
4. P_AC_gerada = P_DC_real * (Eff / 100)
5. P_AC_real = coluna 'Power' do CSV
6. Compara P_AC_gerada vs P_AC_real
7. Calcula métricas: MSE, MAE, RMSE, MAPE, WAPE
"""

import sys
import os
# Adiciona a raiz do projeto ao Python path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

from core.inverter_model import InverterModel
from core.config import DATASET_16D_PATH, RESULTS_DIR

# --- CONFIGURAÇÃO ---
CSV_PATH = DATASET_16D_PATH
MIN_POWER_THRESHOLD = 10.0  # Padronizado com os demais scripts





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

    cols_numeric = ['Voltage S1', 'Current S1', 'Voltage S2', 'Current S2', 'Power']
    for col in cols_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    df = df.dropna(subset=cols_numeric)
    print(f"Registros após limpeza: {len(df)}")

    # P_DC Real (S1 + S2)
    df['P_dc_real'] = (df['Voltage S1'] * df['Current S1']) + \
                      (df['Voltage S2'] * df['Current S2'])

    # P_AC Real (do CSV)
    df['P_ac_real'] = df['Power']

    # Aplicar fórmula de eficiência sobre P_DC REAL
    inversor = InverterModel()
    df['Eff'] = inversor.calculate_efficiency(df['P_dc_real'].values)

    df['P_ac_gerada'] = df['P_dc_real'] * (df['Eff'] / 100.0)

    # --- MÉTRICAS ---
    print(f"\n--- Calculando métricas (P_AC Gerada vs P_AC Real) ---")
    print(f"    P_AC_gerada = P_DC_real * Eff(P_DC_real) / 100")

    valid = df[df['P_ac_real'] > MIN_POWER_THRESHOLD].copy()
    print(f"Registros válidos (P_ac_real > {MIN_POWER_THRESHOLD}W): {len(valid)}")

    errors = valid['P_ac_gerada'] - valid['P_ac_real']

    mse = (errors ** 2).mean()
    rmse = np.sqrt(mse)
    mae = errors.abs().mean()
    mape = (errors.abs() / valid['P_ac_real']).mean() * 100
    wape = (errors.abs().sum() / valid['P_ac_real'].sum()) * 100

    print("\n" + "=" * 55)
    print("  RESULTADOS: P_AC (Fórmula Eff) vs P_AC Real")
    print("  Entrada: Potência DC REAL (medida)")
    print("=" * 55)
    print(f"  Fórmula: Eff = 96.8016 - 9653.1352/Pdc - 0.000125*Pdc")
    print(f"  Threshold: > {MIN_POWER_THRESHOLD}W")
    print("-" * 55)
    print(f"  MSE:  {mse:.4f} W²")
    print(f"  RMSE: {rmse:.4f} W")
    print(f"  MAE:  {mae:.4f} W")
    print(f"  MAPE: {mape:.4f} %")
    print(f"  WAPE: {wape:.4f} %")
    print("=" * 55)

    # Salvar CSV
    output_df = valid[['P_dc_real', 'Eff', 'P_ac_gerada', 'P_ac_real']].copy()
    output_df['Erro'] = errors
    OUTPUT_FILE = os.path.join(RESULTS_DIR, "resultado_eficiencia_real.csv")
    output_df.to_csv(OUTPUT_FILE)
    print(f"\nCSV salvo em: {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    run_analysis()
