import os
import sys
import numpy as np
import pandas as pd
import pvlib
import warnings

# Adiciona o diretório raiz do projeto ao path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import (
    DATASET_1ANO_PATH,
    RESULTS_DIR,
    LATITUDE,
    LONGITUDE,
    TZ_OFFSET,
    ALBEDO,
    M4_COEFS,
    INVERTER_CONFIG,
    DATASHEET_JINKO
)
from core.irradiance_calculator import calcular_componentes_irradiancia_vetorizado
from core.calibrator import Calibrator
from core.inverter_model import InverterModel


def calc_metrics(p_pred, p_real, label=""):
    """Calcula RMSE, MAE, MAPE, WAPE entre os valores previstos e reais."""
    valid = p_real > 10.0  # Evita divisão por zero no cálculo do MAPE
    diff = p_pred - p_real
    rmse = np.sqrt((diff ** 2).mean())
    mae = np.abs(diff).mean()
    mape = (np.abs(diff[valid]) / p_real[valid]).mean() * 100.0
    wape = np.abs(diff).sum() / p_real.sum() * 100.0
    return {'label': label, 'rmse': rmse, 'mae': mae, 'mape': mape, 'wape': wape}


def run_calibration():
    print("=" * 80)
    print("  INICIANDO O PIPELINE DE CALIBRAÇÃO VETORIZADO DO GÊMEO DIGITAL SOLAR")
    print("=" * 80)

    # 1. Carregar e Pré-processar os Dados de 1 Ano
    print(f"\nCarregando dataset de 1 ano de: {DATASET_1ANO_PATH}...")
    if not os.path.exists(DATASET_1ANO_PATH):
        raise FileNotFoundError(f"Arquivo de dados não encontrado em {DATASET_1ANO_PATH}")

    df = pd.read_csv(DATASET_1ANO_PATH)
    
    # Mapeamento correto de colunas do CSV para variáveis internas
    mapping = {
        'TIMESTAMP': 'datetime',
        'Radiacao_Avg': 'Irradiance',
        'Temp_Cel_Avg': 'PV Temperature',
        'Temp_Amb_Avg': 'Amb. Temperature',
        'Tensao_S1_Avg': 'Voltage S1',
        'Corrente_S1_Avg': 'Current S1',
        'Tensao_S2_Avg': 'Voltage S2',
        'Corrente_S2_Avg': 'Current S2',
        'Potencia_FV_Avg': 'Power' # AC real do inversor
    }
    
    df = df.rename(columns=mapping)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.set_index('datetime')

    # Garantir tipo float e limpar valores ausentes (NaN)
    cols_numeric = ['Irradiance', 'PV Temperature', 'Amb. Temperature',
                    'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2', 'Power']
    for col in cols_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna(subset=cols_numeric)
    
    # Filtrar horários diurnos operacionais (05:00 - 18:00)
    df = df.between_time('05:00', '18:00')
    
    # Calcular Potência DC medida total (S1 + S2)
    df['P_dc_real'] = (df['Voltage S1'] * df['Current S1']) + (df['Voltage S2'] * df['Current S2'])
    
    # Filtrar registros com geração DC real
    df = df[df['P_dc_real'] > 0]
    print(f"Registros válidos pós-filtragem diurna: {len(df)}")

    # 2. Calcular Posição Solar Vetorizada (rápida) via pvlib
    print("\nCalculando posição solar de forma vetorizada...")
    # Localizar timezone do index (GMT-3 convention is Etc/GMT+3)
    tz_str = f"Etc/GMT{'+' if TZ_OFFSET < 0 else '-'}{abs(int(TZ_OFFSET))}"
    times = df.index.tz_localize(tz_str)
    
    solpos = pvlib.solarposition.get_solarposition(
        times,
        latitude=LATITUDE,
        longitude=LONGITUDE
    )
    solar_zenith = solpos['apparent_zenith'].values
    solar_azimuth = solpos['azimuth'].values

    # 3. Calcular POA Global Vetorizado usando a nova função implementada
    print("Calculando irradiância POA global vetorizada...")
    dia_do_ano = df.index.dayofyear.values
    poa_res = calcular_componentes_irradiancia_vetorizado(
        ghi=df['Irradiance'].values,
        albedo=ALBEDO,
        dia_do_ano=dia_do_ano,
        solar_zenith_deg=solar_zenith,
        solar_azimuth_deg=solar_azimuth,
        inclinacao_superficie=5.0, # Inclinação padrão de 5 graus
        azimute_superficie=0.0    # Azimute padrão ao Norte
    )
    poa_global = poa_res['global']

    # 4. Estimar Temperatura de Célula via Modelo SAPM
    # SAPM: Tcell = Tmodule + (POA / 1000) * deltaT (deltaT = 1.0)
    temp_cell = df['PV Temperature'].values + (poa_global / 1000.0) * 1.0

    # 5. Instanciar o Calibrador
    calibrator = Calibrator()

    # --- PILAR 1: Calibração de Parâmetros SDM ---
    # Para acelerar e evitar timeouts, amostramos 1 a cada 10 pontos diurnos (~27k pontos) para a otimização do SDM
    print("\nPreparando amostragem sistemática (1 a cada 10 pontos) para otimização do SDM...")
    df_opt = df.iloc[::10]
    poa_opt = poa_global[::10]
    temp_cell_opt = temp_cell[::10]
    p_dc_real_opt = df_opt['P_dc_real'].values

    print(f"Pontos selecionados para otimização SDM: {len(df_opt)}")
    
    # Executa a otimização dos parâmetros elétricos
    cal_sdm_params = calibrator.calibrate_sdm_parameters(
        poa_global=poa_opt,
        temp_cell=temp_cell_opt,
        p_dc_real=p_dc_real_opt
    )
    
    names_sdm = ['I_L_ref', 'I_o_ref', 'R_s', 'R_sh_ref', 'a_ref']
    print("\nParâmetros SDM Calibrados (1 ano):")
    for name, val in zip(names_sdm, cal_sdm_params):
        print(f"  {name:<10}: {val:.6e}")

    # --- PILAR 2: Ajuste de Correções M4 e Poly2 ---
    print("\nCalculando predições elétricas DC no ano todo para ajustar correções...")
    
    # 5.1 Parâmetros Originais de STC (CEC SAM)
    original_stc = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET_JINKO.get('cell_type', 'polySi'),
        v_mp=DATASHEET_JINKO['v_mp'],
        i_mp=DATASHEET_JINKO['i_mp'],
        v_oc=DATASHEET_JINKO['v_oc'],
        i_sc=DATASHEET_JINKO['i_sc'],
        alpha_sc=DATASHEET_JINKO['alpha_sc'],
        beta_voc=DATASHEET_JINKO['beta_voc'],
        gamma_pmp=DATASHEET_JINKO['gamma_pmp'],
        cells_in_series=DATASHEET_JINKO['cells_in_series']
    )
    original_sdm_params = np.array(original_stc[0:5])

    # Predições no ano todo (100% dos dados filtrados)
    p_pred_orig = calibrator.predict_dc(original_sdm_params, poa_global, temp_cell)
    p_pred_cal = calibrator.predict_dc(cal_sdm_params, poa_global, temp_cell)

    # Ajustando as regressões de correção sobre o calibrado de 1 ano
    print("Ajustando correções M4 e Poly2 sobre o SDM calibrado...")
    correcoes = calibrator.fit_m4_correction(
        p_pred=p_pred_cal,
        poa_global=poa_global,
        temp_module=df['PV Temperature'].values,
        p_dc_real=df['P_dc_real'].values
    )
    
    m4_cal_coefs = correcoes['m4']
    poly2_cal_coefs = correcoes['poly2']

    # Gerando as curvas corrigidas
    p_pred_orig_m4 = (M4_COEFS['a'] * p_pred_orig +
                      M4_COEFS['b'] * poa_global +
                      M4_COEFS['c'] * df['PV Temperature'].values +
                      M4_COEFS['d'] * poa_global * df['PV Temperature'].values +
                      M4_COEFS['e'])
    p_pred_orig_m4 = np.clip(p_pred_orig_m4, 0.0, None)

    p_pred_cal_m4 = (m4_cal_coefs['a'] * p_pred_cal +
                     m4_cal_coefs['b'] * poa_global +
                     m4_cal_coefs['c'] * df['PV Temperature'].values +
                     m4_cal_coefs['d'] * poa_global * df['PV Temperature'].values +
                     m4_cal_coefs['e'])
    p_pred_cal_m4 = np.clip(p_pred_cal_m4, 0.0, None)

    X_poly_in = np.column_stack([p_pred_cal, poa_global, df['PV Temperature'].values])
    X_poly = poly2_cal_coefs['transformer'].transform(X_poly_in)
    p_pred_cal_poly2 = poly2_cal_coefs['regressor'].predict(X_poly)
    p_pred_cal_poly2 = np.clip(p_pred_cal_poly2, 0.0, None)

    # --- PILAR 3: Calibração do Inversor ---
    print("\nExecutando calibração da eficiência do inversor...")
    a_inv, b_inv, c_inv = calibrator.calibrate_inverter(
        p_dc_real=df['P_dc_real'].values,
        p_ac_real=df['Power'].values
    )
    print(f"Coeficientes do inversor calibrados (1 ano): a={a_inv:.4f}, b={b_inv:.4f}, c={c_inv:.6e}")

    # Simular o inversor usando a FSM vetorizada
    print("Simulando inversor FSM no ano inteiro (Baseline vs Calibrado)...")
    v_s1 = df['Voltage S1'].values
    v_s2 = df['Voltage S2'].values
    p_dc_real_arr = df['P_dc_real'].values

    # Inversor Baseline
    inverter_orig = InverterModel()
    _, p_ac_orig_sim = inverter_orig.simulate_fsm_vectorized(v_s1, v_s2, p_dc_real_arr)

    # Inversor Calibrado
    inverter_cal = InverterModel()
    inverter_cal.eff_coefs = [a_inv, b_inv, c_inv]
    _, p_ac_cal_sim = inverter_cal.simulate_fsm_vectorized(v_s1, v_s2, p_dc_real_arr)

    # 6. Avaliar as Métricas Comparativas
    print("\nCalculando métricas de erro comparativas...")
    p_dc_real_full = df['P_dc_real'].values
    p_ac_real_full = df['Power'].values

    metrics_dc = [
        calc_metrics(p_pred_orig, p_dc_real_full, "Original SDM (puro)"),
        calc_metrics(p_pred_orig_m4, p_dc_real_full, "Original SDM + M4 (atual)"),
        calc_metrics(p_pred_cal, p_dc_real_full, "Calibrado SDM (puro)"),
        calc_metrics(p_pred_cal_m4, p_dc_real_full, "Calibrado SDM + M4 (calibrado)"),
        calc_metrics(p_pred_cal_poly2, p_dc_real_full, "Calibrado SDM + Poly2 (calibrado)")
    ]

    metrics_ac = [
        calc_metrics(p_ac_orig_sim, p_ac_real_full, "Inversor Baseline (16 dias)"),
        calc_metrics(p_ac_cal_sim, p_ac_real_full, "Inversor Calibrado (1 ano)")
    ]

    # Constantes antigas de 16 dias (para exibir a comparação no arquivo)
    cal_sdm_16d = {
        'I_L_ref': 9.003492e+00,
        'I_o_ref': 1.183504e-10,
        'R_s': 3.479506e-01,
        'R_sh_ref': 2.536717e+02,
        'a_ref': 1.513942e+00,
    }

    # 7. Salvar e Gerar o Relatório Final
    os.makedirs(RESULTS_DIR, exist_ok=True)
    report_path = os.path.join(RESULTS_DIR, "calibration_results_1ano.txt")
    
    print(f"\nEscrevendo relatório em {report_path}...")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("================================================================================\n")
        f.write("             RELATÓRIO DE CALIBRAÇÃO DE 1 ANO - GÊMEO DIGITAL SOLAR             \n")
        f.write("================================================================================\n")
        f.write(f"Dataset de Origem: {os.path.basename(DATASET_1ANO_PATH)}\n")
        f.write(f"Data de Execução: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Registros de minuto analisados (05:00-18:00, P_dc > 0): {len(df)}\n")
        f.write("================================================================================\n\n")

        f.write("1. COMPARATIVO DE PARÂMETROS DO DIODO ÚNICO (SDM)\n")
        f.write("-" * 80 + "\n")
        f.write(f"  {'Parâmetro':<12} | {'Original Datasheet':<20} | {'Calibrado (16 dias)':<20} | {'Calibrado (1 ano)':<20}\n")
        f.write(f"  {'-'*12}-+-{'-'*20}-+-{'-'*20}-+-{'-'*20}\n")
        for i, name in enumerate(names_sdm):
            v_orig = original_sdm_params[i]
            v_16d = cal_sdm_16d[name]
            v_1ano = cal_sdm_params[i]
            f.write(f"  {name:<12} | {v_orig:<20.6e} | {v_16d:<20.6e} | {v_1ano:<20.6e}\n")
        f.write("-" * 80 + "\n\n")

        f.write("2. NOVOS COEFICIENTES DE CORREÇÃO DC (SOBRE O SDM CALIBRADO DE 1 ANO)\n")
        f.write("-" * 80 + "\n")
        f.write("A. Correção Multivariada M4 (Linear com Interação)\n")
        f.write("   Equação: P_corr = a * P_pred + b * POA + c * T_module + d * (POA * T_module) + e\n")
        f.write(f"     a = {m4_cal_coefs['a']:.6f}\n")
        f.write(f"     b = {m4_cal_coefs['b']:.6f}\n")
        f.write(f"     c = {m4_cal_coefs['c']:.6f}\n")
        f.write(f"     d = {m4_cal_coefs['d']:.6f}\n")
        f.write(f"     e = {m4_cal_coefs['e']:.4f}\n\n")
        
        f.write("B. Correção Polinomial Quadrática (Poly2)\n")
        f.write("   Features na ordem do PolynomialFeatures(degree=2, include_bias=False) de [P_pred, POA, T_module]:\n")
        f.write(f"   Intercept: {poly2_cal_coefs['intercept']:.4f}\n")
        f.write("   Coeficientes:\n")
        for k, c_val in enumerate(poly2_cal_coefs['coefs']):
            f.write(f"     c_{k+1:<2} = {c_val:.6e}\n")
        f.write("-" * 80 + "\n\n")

        f.write("3. COMPARATIVO DE PARÂMETROS DE EFICIÊNCIA DO INVERSOR\n")
        f.write("-" * 80 + "\n")
        f.write("   Curva de eficiência: eta = a - b / P_dc - c * P_dc\n")
        f.write(f"  {'Coeficiente':<12} | {'Baseline (16 dias)':<25} | {'Calibrado (1 ano)':<25}\n")
        f.write(f"  {'-'*12}-+-{'-'*25}-+-{'-'*25}\n")
        f.write(f"  {'a':<12} | {INVERTER_CONFIG['eff_coefs'][0]:<25.4f} | {a_inv:<25.4f}\n")
        f.write(f"  {'b':<12} | {INVERTER_CONFIG['eff_coefs'][1]:<25.4f} | {b_inv:<25.4f}\n")
        f.write(f"  {'c':<12} | {INVERTER_CONFIG['eff_coefs'][2]:<25.6e} | {c_inv:<25.6e}\n")
        f.write("-" * 80 + "\n\n")

        f.write("4. MÉTRICAS DE ERRO COMPARATIVAS (ANO COMPLETO)\n")
        f.write("-" * 80 + "\n")
        f.write("A. Potência DC do Arranjo (Medida Total vs Prevista)\n")
        f.write(f"  {'Modelo':<36} | {'RMSE (W)':>10} | {'MAE (W)':>10} | {'MAPE (%)':>10} | {'WAPE (%)':>10}\n")
        f.write(f"  {'-'*36}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}\n")
        for m in metrics_dc:
            f.write(f"  {m['label']:<36} | {m['rmse']:>10.2f} | {m['mae']:>10.2f} | {m['mape']:>10.2f} | {m['wape']:>10.2f}\n")
        f.write("\n")

        f.write("B. Potência AC do Inversor (Medida Real vs Prevista via FSM)\n")
        f.write(f"  {'Modelo':<36} | {'RMSE (W)':>10} | {'MAE (W)':>10} | {'MAPE (%)':>10} | {'WAPE (%)':>10}\n")
        f.write(f"  {'-'*36}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}\n")
        for m in metrics_ac:
            f.write(f"  {m['label']:<36} | {m['rmse']:>10.2f} | {m['mae']:>10.2f} | {m['mape']:>10.2f} | {m['wape']:>10.2f}\n")
        f.write("================================================================================\n")

    # Mostrar o relatório no terminal também
    with open(report_path, 'r', encoding='utf-8') as f:
        print(f.read())

    print("\nPipeline finalizado com sucesso!")


if __name__ == "__main__":
    run_calibration()
