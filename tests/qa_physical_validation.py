import os
import pandas as pd
import numpy as np

RESULTS_DIR = r"c:\Users\55829\Downloads\PESSOAIS\MESTRADO\PESQUISA\PROJETO_GEMEO_DIGITAL_SOLAR\results"

def audit_file(filepath):
    filename = os.path.basename(filepath)
    print(f"\nAuditando {filename}...")
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"  [ERRO] Falha ao carregar o arquivo: {e}")
        return False
        
    print(f"  Tamanho: {df.shape[0]} linhas, {df.shape[1]} colunas")
    print(f"  Colunas: {list(df.columns)}")
    
    # 1. Verificar NaNs
    nans = df.isna().sum().sum()
    if nans > 0:
        print(f"  [ALERTA] Encontrados {nans} valores nulos (NaN) no arquivo!")
        for col in df.columns:
            col_nans = df[col].isna().sum()
            if col_nans > 0:
                print(f"    - Coluna '{col}': {col_nans} NaNs")
    else:
        print("  [OK] Nenhum valor nulo (NaN) detectado.")
        
    # 2. Verificar valores infinitos
    infs = np.isinf(df.select_dtypes(include=[np.number])).sum().sum()
    if infs > 0:
        print(f"  [ALERTA] Encontrados {infs} valores infinitos (inf) no arquivo!")
    else:
        print("  [OK] Nenhum valor infinito detectado.")

    # 3. Validações físicas específicas por tipo de arquivo
    errors_count = 0
    
    # Validações elétricas (Potência DC, AC, Eficiência)
    # Procurar colunas correspondentes de forma case-insensitive
    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in ['p_dc', 'potencia dc', 'potencia_dc', 'pdc']:
            col_mapping['p_dc'] = col
        elif col_lower in ['p_ac', 'potencia ac', 'potencia_ac', 'pac', 'p_ac_sim', 'p_ac_est']:
            col_mapping['p_ac'] = col
        elif col_lower in ['eff', 'eficiencia', 'eff_est', 'eff_real']:
            col_mapping['eff'] = col
        elif col_lower in ['poa', 'poa_global', 'global', 'irradiancia']:
            col_mapping['poa'] = col

    # Validar Potência DC não negativa
    if 'p_dc' in col_mapping:
        p_dc_col = col_mapping['p_dc']
        negatives = (df[p_dc_col] < -0.1).sum()
        if negatives > 0:
            print(f"  [ALERTA] Encontrados {negatives} valores negativos na potência DC '{p_dc_col}'!")
            errors_count += 1
        else:
            print(f"  [OK] Potência DC '{p_dc_col}' é sempre não-negativa (>= 0).")

    # Validar Potência AC não negativa e Conservação de Energia (AC <= DC)
    if 'p_ac' in col_mapping:
        p_ac_col = col_mapping['p_ac']
        negatives = (df[p_ac_col] < -0.1).sum()
        if negatives > 0:
            print(f"  [ALERTA] Encontrados {negatives} valores negativos na potência AC '{p_ac_col}'!")
            errors_count += 1
        else:
            print(f"  [OK] Potência AC '{p_ac_col}' é sempre não-negativa (>= 0).")
            
        # Comparar AC vs DC se ambas existirem
        if 'p_dc' in col_mapping:
            p_dc_col = col_mapping['p_dc']
            # P_ac deve ser menor ou igual a P_dc (com tolerância numérica de 0.5W para flutuações e interpolações)
            ac_gt_dc = (df[p_ac_col] > df[p_dc_col] + 0.5).sum()
            if ac_gt_dc > 0:
                # Vamos verificar se excede por muito ou se é desprezível
                max_excess = (df[p_ac_col] - df[p_dc_col]).max()
                print(f"  [ALERTA] Inconsistência física: {ac_gt_dc} instantes com Potência AC > Potência DC! Excesso máx: {max_excess:.2f} W")
                errors_count += 1
            else:
                print("  [OK] Conservação de energia respeitada: Potência AC <= Potência DC.")

    # Validar Eficiência do Inversor (0% a 100%)
    if 'eff' in col_mapping:
        eff_col = col_mapping['eff']
        out_of_bounds = ((df[eff_col] < 0.0) | (df[eff_col] > 100.001)).sum()
        if out_of_bounds > 0:
            print(f"  [ALERTA] Eficiência do inversor '{eff_col}' fora dos limites físicos [0, 100]% em {out_of_bounds} registros!")
            print(f"    - Min: {df[eff_col].min():.4f}%, Max: {df[eff_col].max():.4f}%")
            errors_count += 1
        else:
            print(f"  [OK] Eficiência do inversor '{eff_col}' está dentro dos limites físicos [0, 100]%.")

    # Validar POA Global/Irradiância
    if 'poa' in col_mapping:
        poa_col = col_mapping['poa']
        negatives = (df[poa_col] < -0.1).sum()
        if negatives > 0:
            print(f"  [ALERTA] Encontrados {negatives} valores negativos de irradiância '{poa_col}'!")
            errors_count += 1
        else:
            print(f"  [OK] Irradiância '{poa_col}' é sempre não-negativa (>= 0).")

    return errors_count == 0

def run_qa_audit():
    print("=" * 60)
    print("INICIANDO AUDITORIA FÍSICA E DE FORMATO DOS ARQUIVOS DE RESULTADOS")
    print("=" * 60)
    
    files_to_audit = [
        "resultado_inversor_simulado.csv",
        "validacao_modelo_eficiencia.csv",
        "resultado_previsao_dc.csv",
        "resultado_energia_clipping.csv",
        "resultado_otimizacao_dc.csv",
        "resultado_otimizacao_inversor.csv",
        "analise_eficiencia.csv",
        "analise_eficiencia_limpo.csv"
    ]
    
    success_count = 0
    for filename in files_to_audit:
        filepath = os.path.join(RESULTS_DIR, filename)
        if os.path.exists(filepath):
            if audit_file(filepath):
                print(f"[OK] {filename} passou na validacao fisica e de formato!")
                success_count += 1
            else:
                print(f"[FALHA] {filename} falhou em algum criterio de validacao!")
        else:
            print(f"\n[AVISO] Arquivo {filename} não encontrado na pasta results.")
            
    print("\n" + "=" * 60)
    print(f"RESUMO: {success_count} de {len(files_to_audit)} arquivos auditados com sucesso!")
    print("=" * 60)

if __name__ == "__main__":
    run_qa_audit()
