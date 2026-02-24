import pandas as pd
import os

INPUT_FILE = "analise_eficiencia.csv"
OUTPUT_FILE = "analise_eficiencia_limpo.csv"

def clean_data():
    if not os.path.exists(INPUT_FILE):
        print(f"Arquivo {INPUT_FILE} não encontrado.")
        return

    print(f"Lendo {INPUT_FILE}...")
    try:
        df = pd.read_csv(INPUT_FILE)
        
        # Verificar colunas
        print("Colunas originais:", df.columns.tolist())
        
        # 1. Filtrar Eficiência > 0 (Remove zero e negativos)
        # Assumindo que a coluna se chama 'Eficiencia' com base no passo anterior
        if 'Eficiencia' in df.columns:
            print(f"Registros antes do filtro: {len(df)}")
            df_filtered = df[df['Eficiencia'] > 0].copy()
            print(f"Registros após filtro (> 0): {len(df_filtered)}")
        else:
            print("Coluna 'Eficiencia' não encontrada!")
            return

        # 2. Remover coluna de datetime
        # O datetime geralmente é a primeira coluna ou index mascarado de coluna.
        # Se salvou com index=True (padrão), a primeira coluna é 'datetime'.
        # Vamos manter apenas 'Potencia DC' e 'Eficiencia'.
        cols_to_keep = ['Potencia DC', 'Eficiencia']
        
        # Verificar se as colunas existem
        existing_cols = [c for c in cols_to_keep if c in df_filtered.columns]
        
        if len(existing_cols) < len(cols_to_keep):
            print(f"Aviso: Nem todas as colunas desejadas foram encontradas. Mantendo: {existing_cols}")
        
        df_final = df_filtered[existing_cols]

        # 3. Ordenar por Potencia DC (Crescente)
        if 'Potencia DC' in df_final.columns:
            print("Ordenando linhas por Potencia DC (Crescente)...")
            df_final = df_final.sort_values(by='Potencia DC', ascending=True)
        else:
            print("Aviso: Coluna 'Potencia DC' não encontrada para ordenação.")
        
        # Salvar sem o índice (que seria o datetime se não foi lido como coluna explícita)
        df_final.to_csv(OUTPUT_FILE, index=False)
        print(f"Arquivo limpo salvo em: {os.path.abspath(OUTPUT_FILE)}")
        print("Colunas finais:", df_final.columns.tolist())

    except Exception as e:
        print(f"Erro ao processar arquivo: {e}")

if __name__ == "__main__":
    clean_data()
