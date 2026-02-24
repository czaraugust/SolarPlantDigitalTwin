import pandas as pd

def calcular_limiar_de_partida(caminho_csv):
    """
    Função para calcular a Irradiância exata em que o inversor PV sai 
    do modo Standby (potência negativa) para Geração Efetiva (potência > 0).
    """
    print("Carregando os dados e preparando a série temporal...")
    # 1. Carregar o dataset
    df = pd.read_csv(caminho_csv)
    
    # 2. Criar uma coluna de DateTime real para ordenação temporal precisa
    df['DateTime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
    df = df.sort_values(by='DateTime').reset_index(drop=True)
    
    # 3. Criar uma flag (True/False) indicando se o sistema está gerando energia real
    df['Generating'] = df['Power'] > 0
    
    # 4. A Regra do Ponto de Virada: 
    # O minuto ATUAL está gerando (True) E o minuto ANTERIOR NÃO estava gerando (False)
    # Usamos o shift(1) para olhar para a linha (minuto) anterior.
    df['Wake_Up_Event'] = df['Generating'] & (~df['Generating'].shift(1, fill_value=False))
    
    # 5. Filtrar para não considerar transições entre dias diferentes (meia-noite)
    df['Same_Day'] = df['Date'] == df['Date'].shift(1)
    df['Wake_Up_Event'] = df['Wake_Up_Event'] & df['Same_Day']
    
    # 6. Filtrar para considerar apenas os despertares matinais (excluir quedas de rede à tarde)
    # Filtramos para eventos que ocorreram antes ou até as 08:00 da manhã
    wake_up_morning = df[df['Wake_Up_Event'] & (df['DateTime'].dt.hour <= 8)].copy()
    
    # --- RESULTADOS ---
    print(f"\nTotal de dias analisados com 'Despertar Matinal' perfeito: {len(wake_up_morning)}")
    
    print("\n[ESTATÍSTICAS DO LIMIAR FÍSICO DE IRRADIÂNCIA W/m²]")
    print(wake_up_morning['Irradiance'].describe())
    
    print("\n[PRIMEIROS 5 EVENTOS DETECTADOS - EXATO MINUTO DA VIRADA]")
    # Mostramos apenas as colunas relevantes para a engenharia do inversor
    colunas_interesse = ['Date', 'Time', 'Irradiance', 'Voltage S1', 'Voltage S2', 'Power']
    print(wake_up_morning[colunas_interesse].head())
    
    return wake_up_morning

# Execução do script:
# Substitua o nome do arquivo se necessário
eventos_partida = calcular_limiar_de_partida('DATASET_MESTRE_COMPLETO.csv')