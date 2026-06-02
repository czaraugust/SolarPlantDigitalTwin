import sys
import os
# Adiciona a raiz do projeto ao Python path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np

from core.config import RESULTS_DIR


def main():
    print("=" * 60)
    print("  RELATÓRIO CONSOLIDADO DE COMPARAÇÃO DO GÊMEO DIGITAL")
    print("=" * 60)

    # 1. Carregar arquivos
    cli_path = os.path.join(RESULTS_DIR, "resultado_energia_clipping.csv")
    eff_path = os.path.join(RESULTS_DIR, "resultado_eficiencia_real.csv")
    inv_path = os.path.join(RESULTS_DIR, "resultado_inversor_simulado.csv")

    if not os.path.exists(cli_path):
        print(f"Erro: {cli_path} não encontrado. Execute o headless de clipping primeiro.")
        return
    if not os.path.exists(eff_path):
        print(f"Erro: {eff_path} não encontrado. Execute o headless de eficiência primeiro.")
        return
    if not os.path.exists(inv_path):
        print(f"Erro: {inv_path} não encontrado. Execute o headless do inversor primeiro.")
        return

    print("\nLendo arquivos...")
    df_cli = pd.read_csv(cli_path)
    df_eff = pd.read_csv(eff_path)
    df_inv = pd.read_csv(inv_path)

    # 2. Métricas de Clipping
    total_real_cli = df_cli['Clip_real'].sum() / 1000.0 # kWh
    total_sim_cli = df_cli['Clip_sim'].sum() / 1000.0
    real_delivered = df_cli['P_ac_real_clipped'].sum() * (1.0/60.0) / 1000.0
    sim_delivered = df_cli['P_ac_sim'].sum() * (1.0/60.0) / 1000.0

    # 3. Métricas de Eficiência e Inversor
    inv_rmse = np.sqrt((df_inv['Erro'] ** 2).mean())
    inv_mae = df_inv['Erro'].abs().mean()
    
    print("\n" + "-" * 50)
    print("  MÉTRICAS DO INVERSOR (Simulado vs Real)")
    print("-" * 50)
    print(f"  RMSE do Inversor: {inv_rmse:.2f} W")
    print(f"  MAE do Inversor:  {inv_mae:.2f} W")

    print("\n" + "-" * 50)
    print("  BALANÇO DE ENERGIA & CLIPPING (16 dias)")
    print("-" * 50)
    print(f"  Energia Entregue Real:      {real_delivered:.2f} kWh")
    print(f"  Energia Entregue Simulada:  {sim_delivered:.2f} kWh (Erro: {(sim_delivered-real_delivered)/real_delivered*100:+.2f}%)")
    print(f"  Perda por Clipping Real:    {total_real_cli:.2f} kWh")
    print(f"  Perda por Clipping Sim.:    {total_sim_cli:.2f} kWh (Erro: {(total_sim_cli-total_real_cli)/total_real_cli*100:+.2f}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
