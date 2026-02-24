import pandas as pd
import numpy as np
import pvlib
import datetime
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Custom Calculators
from core.solar_calculator import CalculadoraSolar
from core.irradiance_calculator import calcular_componentes_irradiancia

# --- CONFIGURAÇÃO ---
CSV_PATH = r"C:\Users\55829\Downloads\PESSOAIS\MESTRADO\PESQUISA\PROJETO_GEMEO_DIGITAL_SOLAR\DATASET_MESTRE_COMPLETO.csv"
OUTPUT_DAILY = "metricas_diarias.csv"
OUTPUT_TOTAL = "metricas_totais.csv"

# Localização
LATITUDE = -9.55762188835476
LONGITUDE = -35.78094625196216
ALTITUDE = 10 
TZ_OFFSET = -3 # UTC-3 for Etc/GMT+3 logic (Alagoas/Brazil is UTC-3)

# Painel (JKM270PP)
DATASHEET = {
    'celltype': 'polySi',
    'v_mp': 31.7,
    'i_mp': 8.52,
    'v_oc': 38.8,
    'i_sc': 9.09,
    'alpha_sc': 0.005454, # A/C
    'beta_voc': -0.1164, # V/C
    'gamma_pmp': -0.40, # %/C
    'cells_in_series': 60,
    'temp_ref': 25,
}

# Array
TILT = 5.0
AZIMUTH = 0.0
ALBEDO = 0.2
MODULES_PER_STRING = 10
STRINGS_IN_PARALLEL = 1

def run_analysis():
    print(f"Carregando CSV: {CSV_PATH}...")
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        print("CSV não encontrado!")
        return
    except Exception as e:
        print(f"Erro ao ler CSV: {e}")
        return

    # Preparar Dados
    print("Preparando dados...")
    
    df['Date'] = df['Date'].astype(str)
    df['Time'] = df['Time'].astype(str)
    
    datetime_str = df['Date'] + ' ' + df['Time']
    # Use format if known for speed, else default
    df['datetime'] = pd.to_datetime(datetime_str)
    df = df.set_index('datetime')
    
    # Filtrar 05:00 - 18:00
    df = df.between_time('05:00', '18:00')
    
    if len(df) == 0:
        print("Nenhum dado encontrado após filtro de horário.")
        return

    # Conversão de Unidades e Limpeza
    df['Wind Speed'] = pd.to_numeric(df['Wind Speed'], errors='coerce') / 3.6
    
    cols_to_numeric = ['Amb. Temperature', 'Irradiance', 'PV Temperature', 
                       'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2', 'Power']
    for col in cols_to_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna(subset=cols_to_numeric + ['Wind Speed'])
    
    # Potência Real (DC Total = S1 + S2)
    # Assumindo que NaN em S2 seja 0 se não existir, mas o dropna acima já limpa.
    df['P_real'] = (df['Voltage S1'] * df['Current S1']) + (df['Voltage S2'] * df['Current S2'])
    
    # --- CÁLCULO SOLAR E IRRADIANCIA (CUSTOM LOOP) ---
    print(f"Iniciando cálculos solares e de irradiância (Custom Calculators) para {len(df)} registros...")
    
    # Pre-allocate numpy arrays for speed
    poa_global_arr = np.zeros(len(df))
    
    # Convert index to pydatetime array for loop
    timestamps = df.index.to_pydatetime()
    ghis = df['Irradiance'].values
    
    for i, dt in enumerate(timestamps):
        # 1. Posição Solar (CalculadoraSolar)
        # UTC offset handling: The datetime in CSV is likely local time (UTC-3).
        # SolarCalculator expects a datetime object.
        calc_solar = CalculadoraSolar(dt, LATITUDE, LONGITUDE, TZ_OFFSET)
        
        zenith = 90 - calc_solar.elevacao
        azimuth = calc_solar.azimute
        day_of_year = calc_solar.numero_do_dia
        
        # 2. Irradiância (calcular_componentes_irradiancia)
        res_irr = calcular_componentes_irradiancia(
            ghi=ghis[i],
            albedo=ALBEDO,
            dia_do_ano=day_of_year,
            solar_zenith_deg=zenith,
            solar_azimuth_deg=azimuth,
            inclinacao_superficie=TILT,
            azimute_superficie=AZIMUTH
        )
        
        poa_global_arr[i] = res_irr['global']
        
        if i % 1000 == 0:
            print(f"Processado: {i}/{len(df)}", end='\r')
            
    print(f"Processado: {len(df)}/{len(df)}")
    
    # Store in DataFrame (Vectorized operations resume from here)
    # Using specific series name to avoid confusion
    poa_global = pd.Series(poa_global_arr, index=df.index)
    
    # --- CÁLCULO DE TEMPERATURAS (4 Modelos - PVLIB) ---
    print("Calculando temperaturas de célula via pvlib...")
    
    # Modelo 1: Sensor
    temp_cell_sensor = df['PV Temperature']
    
    # Modelo 2: Faiman
    temp_cell_faiman = pvlib.temperature.faiman(
        poa_global, df['Amb. Temperature'], df['Wind Speed']
    )
    
    # Modelo 3: Ross
    try:
        temp_cell_ross = pvlib.temperature.ross(
            poa_global, df['Amb. Temperature'], k=0.045
        )
    except AttributeError:
        temp_cell_ross = df['Amb. Temperature'] + 0.045 * poa_global
    
    # Modelo 4: SAPM
    temp_cell_sapm = pvlib.temperature.sapm_cell_from_module(
        module_temperature=df['PV Temperature'],
        poa_global=poa_global,
        deltaT=1.0
    )
    
    # --- CÁLCULO ELÉTRICO (Single Diode / DeSoto - PVLIB) ---
    print("Estimando parâmetros elétricos e resolvendo single diode (LambertW)...")
    
    # Fit CEC Params
    stc_params = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'], cells_in_series=DATASHEET['cells_in_series']
    )
    
    I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = stc_params[0:5]
    
    def calculate_power_vectorized(temp_cell_series):
        effective_irradiance = poa_global.clip(upper=1400.0)
        
        desoto_params = pvlib.pvsystem.calcparams_desoto(
            effective_irradiance=effective_irradiance,
            temp_cell=temp_cell_series,
            alpha_sc=DATASHEET['alpha_sc'],
            a_ref=a_ref,
            I_L_ref=I_L_ref,
            I_o_ref=I_o_ref,
            R_sh_ref=R_sh_ref,
            R_s=R_s,
            EgRef=1.121,
            dEgdT=-0.0002677
        )
        
        IL, I0, Rs, Rsh, nNsVth = desoto_params
        
        try:
            i_mp, v_mp, p_mp = pvlib.singlediode(
                photocurrent=IL,
                saturation_current=I0,
                resistance_series=Rs,
                resistance_shunt=Rsh,
                nNsVth=nNsVth,
                method='lambertw'
            )
        except Exception:
            res = pvlib.singlediode.bishop88_mpp(
                photocurrent=IL, saturation_current=I0, resistance_series=Rs, 
                resistance_shunt=Rsh, nNsVth=nNsVth, method='newton'
            )
            p_mp = res[2]

        p_mp_total = p_mp * MODULES_PER_STRING * STRINGS_IN_PARALLEL
        return p_mp_total

    print("Calculando Potência MPP para os 4 modelos...")
    df['P_sensor'] = calculate_power_vectorized(temp_cell_sensor)
    df['P_faiman'] = calculate_power_vectorized(temp_cell_faiman)
    df['P_ross'] = calculate_power_vectorized(temp_cell_ross)
    df['P_sapm'] = calculate_power_vectorized(temp_cell_sapm)
    
    # --- ANÁLISE DE ERRO ---
    print("Calculando métricas...")
    
    results_daily = []
    models = ['Sensor', 'Faiman', 'Ross', 'SAPM']
    
    unique_dates = sorted(df.index.date)
    unique_dates = np.unique(unique_dates)
    
    cols = ['P_real'] + [f'P_{m.lower()}' for m in models]
    analysis_df = df[cols].copy()
    
    acc_stats = {m: {'sq': 0.0, 'abs': 0.0, 'per': 0.0, 'n': 0, 'n_mape': 0, 'real_sum': 0.0} for m in models}
    
    daily_stats = []
    
    for day in unique_dates:
        day_str = str(day)
        day_df = analysis_df[analysis_df.index.date == day]
        day_valid = day_df[day_df['P_real'] > 10.0]
        
        for m in models:
            col = f'P_{m.lower()}'
            if len(day_valid) > 0:
                p_pred = day_valid[col]
                p_real = day_valid['P_real']
                
                diff = p_pred - p_real
                sq_diff = (diff ** 2).sum()
                abs_diff = diff.abs().sum()
                mape_sum = (diff.abs() / p_real).sum()
                
                acc_stats[m]['sq'] += sq_diff
                acc_stats[m]['abs'] += abs_diff
                acc_stats[m]['per'] += mape_sum
                acc_stats[m]['n'] += len(day_valid)
                acc_stats[m]['n_mape'] += len(day_valid)
                acc_stats[m]['real_sum'] += p_real.sum()
        
        for m in models:
            n = acc_stats[m]['n']
            if n > 0:
                mse = acc_stats[m]['sq'] / n
                rmse = np.sqrt(mse)
                mae = acc_stats[m]['abs'] / n
                mape = (acc_stats[m]['per'] / n) * 100
                
                real_sum = acc_stats[m]['real_sum']
                wape = (acc_stats[m]['abs'] / real_sum * 100) if real_sum > 0 else 0.0

                daily_stats.append({
                    'Date': day_str,
                    'Model': m,
                    'MSE': mse,
                    'RMSE': rmse,
                    'MAE': mae,
                    'MAPE': mape,
                    'WAPE': wape,
                    'Samples': n
                })

    res_df = pd.DataFrame(daily_stats)
    res_df.to_csv(OUTPUT_DAILY, index=False)
    print(f"Resultados diários salvos em: {os.path.abspath(OUTPUT_DAILY)}")
    
    if not res_df.empty:
        last_day = res_df['Date'].iloc[-1]
        final_df = res_df[res_df['Date'] == last_day]
        final_df.to_csv(OUTPUT_TOTAL, index=False)
        print(f"Resultados finais salvos em: {os.path.abspath(OUTPUT_TOTAL)}")
        print("\n--- RESUMO FINAL ---")
        print(final_df[['Model', 'RMSE', 'MAE', 'MAPE', 'WAPE']].to_string(index=False))

    # --- ANÁLISE DE SOBRECARGA (> 5000W) ---
    print("\n--- ANÁLISE DE SOBRECARGA (> 5000W) ---")
    THRESHOLD = 5000.0
    
    # Filtrar momentos de sobrecarga
    overpower_df = df[df['P_real'] > THRESHOLD].copy()
    
    if len(overpower_df) > 0:
        # 1. Duração Total (Minutos)
        # Assumindo que cada linha é 1 minuto (amostragem típica). 
        # Se for diferente, precisaria calcular delta T real.
        # Vamos calcular delta T médio para confirmar
        time_diffs = df.index.to_series().diff().dt.total_seconds() / 60.0
        avg_step = time_diffs.median() # Passo médio em minutos
        
        minutes_over = len(overpower_df) * avg_step # Aproximação baseada no passo
        
        # 2. Energia Excedente (Wh)
        # Energia = Potência * Tempo
        # Excedente = (P_real - 5000) * (avg_step / 60 horas)
        power_excess = overpower_df['P_real'] - THRESHOLD
        energy_excess_wh = (power_excess * (avg_step / 60.0)).sum()
        
        # Energia Total Gerada acima de 5000 (não só o excedente, mas a energia total nesses momentos? 
        # O usuario pediu "quanta potencia acima de 5000 foi gerada". 
        # Isso geralmente significa a INTEGRAL DA PARTE EXCEDENTE (clipped).
        # "quanta energia" seria o termo correto, mas "potencia gerada" pode ser interpretado. 
        # Vou entregar a Energia Excedente (Wh).
        
        print(f"Limite de Potência: {THRESHOLD} W")
        print(f"Duração Total Acima do Limite: {minutes_over:.1f} minutos")
        print(f"Energia Excedente Gerada: {energy_excess_wh:.2f} Wh")
        print(f"Pico de Potência Registrado: {overpower_df['P_real'].max():.2f} W")
    else:
        print(f"Nenhum registro de potência acima de {THRESHOLD} W foi encontrado.")

    # --- EXPORTAÇÃO DE EFICIÊNCIA ---
    print("\nGerando CSV de Eficiência...")
    # Eficiência = (Potência AC / Potência DC) * 100
    # Evitar divisão por zero
    df['Efficiency'] = np.where(df['P_real'] > 10, (df['Power'] / df['P_real']) * 100, 0.0)
    
    # Selecionar colunas
    eff_df = df[['P_real', 'Efficiency']].copy()
    eff_df.columns = ['Potencia DC', 'Eficiencia'] # Renomear para português
    
    # Salvar
    EFF_OUTPUT = "analise_eficiencia.csv"
    eff_df.to_csv(EFF_OUTPUT) # Mantém o index (datetime) para referência
    print(f"Arquivo salvo: {os.path.abspath(EFF_OUTPUT)}")

if __name__ == "__main__":
    run_analysis()
