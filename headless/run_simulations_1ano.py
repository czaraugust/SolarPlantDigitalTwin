"""
Script headless para simulação em lote de 1 ano vetorizado do Gêmeo Digital Solar.
Varre 26 tilts (0° a 25°), 4 azimutes (0°, 90°, 180°, 270°) e 21 cenários de oversizing (ILR 1.0 a 2.0).
Total de 2.184 simulações para 1 ano de dados.
"""

import os
import sys
import time
import pandas as pd
import numpy as np
import pvlib

# Adiciona a raiz do projeto ao path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import (
    DATASET_1ANO_PATH,
    RESULTS_DIR,
    LATITUDE,
    LONGITUDE,
    TZ_OFFSET,
    ALBEDO,
    S1_SERIES,
    S2_SERIES,
    TOTAL_MODULES,
    DATASHEET_JINKO,
    SDM_CALIBRADO_1ANO,
    M4_COEFS,
    SAPM_DELTAT
)
from core.irradiance_calculator import calcular_componentes_irradiancia_vetorizado
from core.inverter_model import InverterModel

# Constantes locais
P_PAINEL = 270.0  # Potência nominal de um módulo (W)


def carregar_e_preparar_dados() -> pd.DataFrame:
    """
    Carrega o dataset de 1 ano, renomeia as colunas para o padrão do twin,
    limpa valores inválidos/NaN e filtra o horário operacional (05:00 - 18:00).

    Returns:
        pd.DataFrame: DataFrame tratado e ordenado pelo index temporal.
    """
    print(f"Carregando dataset de 1 ano de: {DATASET_1ANO_PATH}...")
    if not os.path.exists(DATASET_1ANO_PATH):
        raise FileNotFoundError(f"Arquivo de dados não encontrado em {DATASET_1ANO_PATH}")

    df = pd.read_csv(DATASET_1ANO_PATH)
    
    # Mapeamento de colunas para padrão interno
    mapping = {
        'TIMESTAMP': 'datetime',
        'Radiacao_Avg': 'Irradiance',
        'Temp_Cel_Avg': 'PV Temperature',
        'Temp_Amb_Avg': 'Amb. Temperature',
        'Tensao_S1_Avg': 'Voltage S1',
        'Corrente_S1_Avg': 'Current S1',
        'Tensao_S2_Avg': 'Voltage S2',
        'Corrente_S2_Avg': 'Current S2',
        'Potencia_FV_Avg': 'Power'
    }
    
    df = df.rename(columns=mapping)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.set_index('datetime').sort_index()

    # Garantir conversão numérica
    cols_criticas = ['Irradiance', 'PV Temperature', 'Voltage S1', 'Voltage S2']
    for col in cols_criticas:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Filtrar apenas dados com valores não nulos nas colunas críticas
    df = df.dropna(subset=cols_criticas)

    # Filtrar horários operacionais diurnos (05:00 às 18:00) para economizar recursos computacionais
    df = df.between_time('05:00', '18:00')
    
    print(f"Dataset carregado com sucesso. Registros operacionais diurnos: {len(df)}")
    return df


def executar_simulacoes_lote(df: pd.DataFrame) -> pd.DataFrame:
    """
    Executa a simulação em lote de 1 ano vetorizada variando inclinações (tilts),
    azimutes e fatores de oversizing.

    Args:
        df (pd.DataFrame): DataFrame tratado com os dados ambientais e elétricos históricos.

    Returns:
        pd.DataFrame: DataFrame contendo o resumo acumulado de cada simulação.
    """
    t_inicio = time.time()
    
    # Parâmetros de varredura
    tilts = list(range(0, 26))  # 0° a 25° (26 tilts)
    azimutes = [0, 90, 180, 270]  # 4 azimutes
    fatores_oversizing = [i / 100.0 for i in range(0, 105, 5)]  # 21 cenários (0% a 100%)

    total_combinacoes = len(tilts) * len(azimutes)
    total_simulacoes = total_combinacoes * len(fatores_oversizing)
    
    print(f"Iniciando varredura: {len(tilts)} tilts x {len(azimutes)} azimutes x {len(fatores_oversizing)} oversizings = {total_simulacoes} simulações.")

    # 1. Pré-calcular posição solar uma única vez de forma vetorizada
    print("Pré-calculando posição solar vetorizada...")
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
    dayofyear = df.index.dayofyear.values

    # Instanciar modelo do inversor
    inverter = InverterModel()
    
    # Preparar listas para acumular resultados
    resultados = []
    
    # Passos de tempo (minuto a minuto -> 1/60 hora)
    dt_hours = 1.0 / 60.0
    
    # Guardar valores fixos do DataFrame para otimizar acessos
    v_s1_arr = df['Voltage S1'].values
    v_s2_arr = df['Voltage S2'].values
    t_mod_arr = df['PV Temperature'].values
    ghi_arr = df['Irradiance'].values
    
    contador_progresso = 0
    
    for tilt in tilts:
        for azimuth in azimutes:
            t0_comb = time.time()
            contador_progresso += 1
            
            # A. Calcular Irradiância POA Global Vetorizada
            poa_res = calcular_componentes_irradiancia_vetorizado(
                ghi=ghi_arr,
                albedo=ALBEDO,
                dia_do_ano=dayofyear,
                solar_zenith_deg=solar_zenith,
                solar_azimuth_deg=solar_azimuth,
                inclinacao_superficie=float(tilt),
                azimute_superficie=float(azimuth)
            )
            poa_global = poa_res['global']
            
            # B. Estimar Temperatura de Célula Vetorizada via Modelo SAPM
            temp_cell = pvlib.temperature.sapm_cell_from_module(
                module_temperature=t_mod_arr,
                poa_global=poa_global,
                deltaT=SAPM_DELTAT
            )
            
            # C. Calibrar Parâmetros Elétricos do Diodo Único de forma vetorizada
            eff_irr = np.clip(poa_global, 0.0, 1400.0)
            
            photocurrent, saturation_current, resistance_series, resistance_shunt, nNsVth = pvlib.pvsystem.calcparams_desoto(
                effective_irradiance=eff_irr,
                temp_cell=temp_cell,
                alpha_sc=DATASHEET_JINKO['alpha_sc'],
                a_ref=SDM_CALIBRADO_1ANO['a_ref'],
                I_L_ref=SDM_CALIBRADO_1ANO['I_L_ref'],
                I_o_ref=SDM_CALIBRADO_1ANO['I_o_ref'],
                R_sh_ref=SDM_CALIBRADO_1ANO['R_sh_ref'],
                R_s=SDM_CALIBRADO_1ANO['R_s'],
                EgRef=1.121,
                dEgdT=-0.0002677
            )
            
            # Simular MPP do diodo único vetorizado
            sd_res = pvlib.pvsystem.singlediode(
                photocurrent=photocurrent,
                saturation_current=saturation_current,
                resistance_series=resistance_series,
                resistance_shunt=resistance_shunt,
                nNsVth=nNsVth,
                method='lambertw'
            )
            p_mp_module = np.where(poa_global >= 5.0, sd_res['p_mp'], 0.0)
            
            # D. Aplicar Correção Multivariada M4 Vetorizada
            p_dc_raw = p_mp_module * TOTAL_MODULES
            p_dc_base = (
                M4_COEFS['a'] * p_dc_raw +
                M4_COEFS['b'] * poa_global +
                M4_COEFS['c'] * t_mod_arr +
                M4_COEFS['d'] * poa_global * t_mod_arr +
                M4_COEFS['e']
            )
            p_dc_base = np.where(poa_global >= 5.0, np.clip(p_dc_base, 0.0, None), 0.0)
            
            # E. Executar FSM vetorizada do inversor uma única vez por combinação (tilt, azimute) com a potência DC base
            estados, _ = inverter.simulate_fsm_vectorized(v_s1_arr, v_s2_arr, p_dc_base)

            # F. Varredura dos Cenários de Oversizing para este par (tilt, azimute)
            for fator in fatores_oversizing:
                p_dc = p_dc_base * (1.0 + fator)
                
                a_eff, b_eff, c_eff = inverter.eff_coefs
                eff = a_eff - (b_eff / np.maximum(p_dc, 1.0)) - (c_eff * p_dc)
                eff = np.clip(eff, 0.0, 100.0)
                
                p_ac_preclip = p_dc * (eff / 100.0)
                p_ac_preclip = np.where(estados == inverter.LIGADO, p_ac_preclip, 0.0)
                
                p_ac_entregue = np.minimum(p_ac_preclip, inverter.p_nominal)
                clip_w = np.maximum(p_ac_preclip - inverter.p_nominal, 0.0)
                
                # Acumular energia entregue e clipping (integrando no tempo minuto a minuto -> kWh)
                e_entregue_kwh = (p_ac_entregue * dt_hours).sum() / 1000.0
                e_total_pre_kwh = (p_ac_preclip * dt_hours).sum() / 1000.0
                c_kwh = (clip_w * dt_hours).sum() / 1000.0
                
                c_pct = (c_kwh / e_total_pre_kwh * 100.0) if e_total_pre_kwh > 0.0 else 0.0
                kwp_instalado = TOTAL_MODULES * P_PAINEL * (1.0 + fator) / 1000.0
                
                resultados.append({
                    'tilt': tilt,
                    'azimute': azimuth,
                    'fator_oversizing': fator,
                    'ilr': 1.0 + fator,
                    'kwp_instalado': kwp_instalado,
                    'energia_entregue_kwh': e_entregue_kwh,
                    'clipping_kwh': c_kwh,
                    'clipping_pct': c_pct,
                    'energia_total_pre_clipping_kwh': e_total_pre_kwh
                })
            
            t_comb = time.time() - t0_comb
            # Progresso parcial
            if contador_progresso % 10 == 0 or contador_progresso == total_combinacoes:
                print(f"Progresso: {contador_progresso}/{total_combinacoes} combinações ({contador_progresso/total_combinacoes*100:.1f}%) | "
                      f"Última comb. (Tilt={tilt}°, Az={azimuth}°) processada em {t_comb:.2f}s | "
                      f"Tempo total decorrido: {time.time() - t_inicio:.1f}s")
                
    df_resultados = pd.DataFrame(resultados)
    tempo_total = time.time() - t_inicio
    print(f"\nVarredura concluída com sucesso! Tempo total: {tempo_total:.2f} segundos ({tempo_total/60.0:.2f} minutos).")
    return df_resultados


def run():
    """
    Função principal que coordena a leitura dos dados, execução das simulações
    e salvamento dos resultados consolidados em CSV.
    """
    print("=" * 80)
    # Ignorar warnings do numpy e de LambertW que poluem a tela em baixas irradiâncias
    import warnings
    warnings.filterwarnings('ignore', category=RuntimeWarning)
    
    t_inicial = time.time()
    
    # 1. Carregar dados de 1 ano
    df = carregar_e_preparar_dados()
    
    # 2. Executar lote de simulações
    df_resultados = executar_simulacoes_lote(df)
    
    # 3. Salvar resultados consolidado em CSV
    os.makedirs(RESULTS_DIR, exist_ok=True)
    output_path = os.path.join(RESULTS_DIR, "resultado_tilt_orientacao_oversizing_1ano.csv")
    
    print(f"\nSalvando tabela consolidada em: {output_path}...")
    df_resultados.to_csv(output_path, index=False)
    
    tempo_total = time.time() - t_inicial
    print(f"Processo finalizado com sucesso em {tempo_total:.2f} segundos!")
    print(f"Tamanho do CSV gerado: {os.path.getsize(output_path) / (1024*1024):.2f} MB")
    print("=" * 80)


if __name__ == "__main__":
    run()
