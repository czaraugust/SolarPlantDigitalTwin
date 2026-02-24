import pandas as pd
import numpy as np
import os

INPUT_FILE = "analise_eficiencia_limpo.csv"

def calculate_metrics():
    if not os.path.exists(INPUT_FILE):
        print(f"Arquivo {INPUT_FILE} não encontrado.")
        return

    print(f"Lendo {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    
    # 1. Obter Potência DC Real
    P_dc = df['Potencia DC']
    
    # 2. Reconstruir Potência AC Real
    # O arquivo tem 'Eficiencia' (Real) em %.
    # P_ac_real = P_dc * (Eficiencia / 100)
    # Nota: Eficiencia já não tem zeros (filtrado no passo anterior), mas vamos validar.
    Eff_real = df['Eficiencia']
    P_ac_real = P_dc * (Eff_real / 100.0)
    
    # 3. Calcular Eficiência Estimada (Fórmula)
    # Eficiência = 96.8016 - (9653.1352 / Potência DC) - 0.000125 * Potência DC
    # Cuidado com divisão por zero se P_dc for muito baixo (embora tenhamos filtrado eficiência > 0, P_dc pode ser baixo)
    # Vamos filtrar P_dc muito baixo para evitar explosão da fórmula, ou assumir que o dataset limpo é seguro.
    # O dataset limpo tem Eficiencia > 0, o que implica P_ac > 0 e P_dc > 0.
    
    Eff_est = 96.8016 - (9653.1352 / P_dc) - (0.000125 * P_dc)
    
    # A eficiência estimada não deve ser usada se P_dc for muito baixo (o termo 1/P_dc explode).
    # O modelo provavelmente é válido para P_dc observados.
    
    # 4. Calcular Potência AC Estimada
    P_ac_est = P_dc * (Eff_est / 100.0)
    
    # 5. Métricas
    # Comparar P_ac_est vs P_ac_real
    
    errors = P_ac_est - P_ac_real
    
    mae = errors.abs().mean()
    mse = (errors ** 2).mean()
    rmse = np.sqrt(mse)
    
    # MAPE: Mean Absolute Percentage Error
    # Cuidado com P_ac_real = 0 (filtrado, mas bom garantir)
    mape = (errors.abs() / P_ac_real).mean() * 100
    
    # WAPE: Weighted Absolute Percentage Error (Sum(|Errors|) / Sum(|Actual|))
    wape = (errors.abs().sum() / P_ac_real.sum()) * 100
    
    print("\n--- Resultados da Validação do Modelo de Eficiência ---")
    print(f"Fórmula: Eff = 96.8016 - (9653.1352 / P_dc) - (0.000125 * P_dc)")
    print("-" * 30)
    print(f"MSE:  {mse:.4f}")
    print(f"RMSE: {rmse:.4f} W")
    print(f"MAE:  {mae:.4f} W")
    print(f"MAPE: {mape:.4f} %")
    print(f"WAPE: {wape:.4f} %")
    print("-" * 30)
    
    # Opcional: Salvar CSV comparativo para o usuário verificar se quiser
    output_df = pd.DataFrame({
        'P_dc': P_dc,
        'P_ac_real': P_ac_real,
        'Eff_real': Eff_real,
        'Eff_est': Eff_est,
        'P_ac_est': P_ac_est,
        'Error': errors
    })
    output_df.to_csv("validacao_modelo_eficiencia.csv", index=False)
    print("CSV comparativo salvo em: validacao_modelo_eficiencia.csv")

if __name__ == "__main__":
    calculate_metrics()
