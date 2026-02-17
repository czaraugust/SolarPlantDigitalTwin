import pandas as pd
import numpy as np
import pvlib
import datetime
import os
import sys
from scipy.optimize import minimize, Bounds
from pvlib import pvsystem, singlediode

# --- CONFIGURAÇÃO ---
CSV_PATH = r"C:\Users\55829\Downloads\PESSOAIS\MESTRADO\PESQUISA\PROJETO_GEMEO_DIGITAL_SOLAR\DATASET_MESTRE_COMPLETO.csv"
OUTPUT_FILE = "calibration_results.txt"

# Localização
LATITUDE = -9.55762188835476
LONGITUDE = -35.78094625196216
ALTITUDE = 10 
TZ = 'Etc/GMT+3' 

# Configuração do Array
TILT = 5.0
AZIMUTH = 0.0
ALBEDO = 0.2
MODULES_PER_STRING = 10
STRINGS_IN_PARALLEL = 1

# Datasheet Original (JKM270PP)
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

def load_and_filter_data():
    print("Loading data...")
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        print("CSV não encontrado!")
        return None

    # Prepara Datetime Index
    df['Date'] = df['Date'].astype(str)
    df['Time'] = df['Time'].astype(str)
    df['datetime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
    df = df.set_index('datetime')
    
    # Filtro Hora Solar (aprox 09:00 - 15:00 para minimizar efeitos angulares extremos)
    df = df.between_time('09:00', '15:00')
    
    # Conversões
    df['Wind Speed'] = pd.to_numeric(df['Wind Speed'], errors='coerce') / 3.6
    cols_to_numeric = ['Amb. Temperature', 'Irradiance', 'PV Temperature', 'Voltage S1', 'Current S1']
    for col in cols_to_numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna(subset=cols_to_numeric + ['Wind Speed'])
    
    # Potência Real (String/Array)
    df['P_real'] = df['Voltage S1'] * df['Current S1']

    # --- FILTRO ALTA IRRADIANCIA ---
    # Usamos apenas alta irradiancia para calibrar parâmetros "em operação",
    # pois erros de modelo térmico e angulares são menores aqui, e é onde a produção importa.
    # O datasheet define parâmetros em 1000 W/m2.
    # Vamos pegar > 800 W/m2.
    df_cal = df[df['Irradiance'] > 800].copy()
    
    # Também filtrar dados onde a produção é zero (inversores desligados, sombra total, erros)
    df_cal = df_cal[df_cal['P_real'] > 100]

    print(f"Data filtered: {len(df_cal)} points used for calibration (Irradiance > 800 W/m²).")
    return df_cal

# Variáveis globais para otimizar a função de custo (evitar recriar objetos pvlib)
# Mas como estamos usando pandas, passamos as Series
def objective_wrapper(params, poa_global, temp_cell, p_real):
    """
    Função wrapper para minimizar.
    params: [I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref]
    """
    I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = params
    
    # Clip POA (físico)
    effective_irradiance = poa_global.clip(upper=1400.0)
    
    try:
        # Calcparams DeSoto (Vetorizado)
        # Retorna: photocurrent, saturation_current, resistance_series, resistance_shunt, nNsVth
        desoto_params = pvsystem.calcparams_desoto(
            effective_irradiance=effective_irradiance,
            temp_cell=temp_cell,
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

        # Bishop88
        # Retorna tuple (imp, vmp, pmp) com method='newton'
        # Usar newton é mais rápido que lambertw
        mpp_res = singlediode.bishop88_mpp(
            photocurrent=IL,
            saturation_current=I0,
            resistance_series=Rs,
            resistance_shunt=Rsh,
            nNsVth=nNsVth,
            method='newton'
        )
        
        # Pega o terceiro elemento (p_mp)
        p_mp = mpp_res[2]
        
        # Escala para tensão do array
        p_model = p_mp * MODULES_PER_STRING * STRINGS_IN_PARALLEL
        
        # RMSE
        diff = p_model - p_real
        mse = (diff ** 2).mean()
        rmse = np.sqrt(mse)
        
        if np.isnan(rmse): return 1e9
        return rmse
        
    except Exception:
        return 1e9

def calibrate():
    # 1. Carregar Dados
    df = load_and_filter_data()
    if df is None or len(df) < 10:
        print("Erro: Poucos dados para calibração. Verifique os critérios de filtro.")
        return

    # 2. Pré-calcular Input Físico (POA, Temp Cell)
    print("Calculando irradiancia POA...")
    location = pvlib.location.Location(LATITUDE, LONGITUDE, tz=TZ, altitude=ALTITUDE)
    solar_pos = location.get_solarposition(df.index)
    
    # Erbs
    erbs = pvlib.irradiance.erbs(df['Irradiance'], solar_pos['zenith'], df.index)
    dni = erbs['dni']
    dhi = erbs['dhi']
    dni_extra = pvlib.irradiance.get_extra_radiation(df.index)

    poa_res = pvlib.irradiance.get_total_irradiance(
        surface_tilt=TILT,
        surface_azimuth=AZIMUTH,
        solar_zenith=solar_pos['zenith'],
        solar_azimuth=solar_pos['azimuth'],
        dni=dni,
        ghi=df['Irradiance'],
        dhi=dhi,
        dni_extra=dni_extra,
        model='isotropic',
        albedo=ALBEDO
    )
    poa_global = poa_res['poa_global']
    temp_cell = df['PV Temperature'] # Usar sensor para calibração elétrica
    p_real = df['P_real']

    # 3. Estimativa Inicial (Guess) - Usando valores do Datasheet
    stc_params = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'], cells_in_series=DATASHEET['cells_in_series']
    )
    # params structure from fit_cec_sam: I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref, Adjust
    # We calibrate the first 5.
    initial_guess = np.array(stc_params[0:5])
    
    print("\nParâmetros Iniciais (Calculados via pvlib.fit_cec_sam):")
    names = ['I_L_ref', 'I_o_ref', 'R_s', 'R_sh_ref', 'a_ref']
    for i in range(5):
        print(f"{names[i]:<10}: {initial_guess[i]:.6e}")

    # Teste Inicial Error
    initial_rmse = objective_wrapper(initial_guess, poa_global, temp_cell, p_real)
    print(f"RMSE Inicial (Baseline): {initial_rmse:.2f} W")

    # 4. Otimização
    print("\nOtimizando... (Isso pode levar alguns segundos)")
    
    # Define Bounds (Relaxados para permitir ajuste, mas limitados fisicamente)
    # I_L_ref: ~I_sc. Bounds: 80% a 120%
    # I_o_ref: Corrente de saturação. Pode variar ordens de magnitude. 1e-13 a 1e-7.
    # R_s: Resistencia serie. 0.001 a 1.0 ohm.
    # R_sh_ref: Resistencia shunt. 10 a 5000 ohm.
    # a_ref: Ideality * Ns * Vth. Geralmente 0.5 a 3.0.
    
    b_il = (initial_guess[0]*0.8, initial_guess[0]*1.2)
    b_io = (1e-13, 1e-7) 
    b_rs = (0.01, 2.0)
    b_rsh = (5.0, 5000.0)
    b_a = (0.5, 3.0)
    
    bounds = [b_il, b_io, b_rs, b_rsh, b_a]
    
    # Executa minimização
    result = minimize(
        objective_wrapper,
        initial_guess,
        args=(poa_global, temp_cell, p_real),
        method='L-BFGS-B', 
        bounds=bounds,
        options={'disp': True, 'maxiter': 500, 'ftol': 1e-6}
    )

    # 5. Resultados
    print("\n--- Calibration Complete ---")
    print(f"Success: {result.success}")
    print(f"RMSE Final: {result.fun:.2f} W")
    
    new_params = result.x
    print("\nNovos Parâmetros Calibrados:")
    for i in range(5):
        var = ((new_params[i] - initial_guess[i]) / initial_guess[i]) * 100
        print(f"{names[i]:<10}: {new_params[i]:.6e} (Var: {var:+.2f}%)")
    
    # Salvar em arquivo para o usuario copiar
    with open(OUTPUT_FILE, 'w') as f:
        f.write("# Parâmetros Calibrados (Single Diode Model)\n")
        f.write(f"RMSE_Improvement: {initial_rmse:.2f} W -> {result.fun:.2f} W\n")
        f.write("-" * 30 + "\n")
        f.write(f"I_L_ref = {new_params[0]:.6f}\n")
        f.write(f"I_o_ref = {new_params[1]:.6e}\n")
        f.write(f"R_s     = {new_params[2]:.6f}\n")
        f.write(f"R_sh_ref= {new_params[3]:.6f}\n")
        f.write(f"a_ref   = {new_params[4]:.6f}\n")
        
    print(f"\nResultados salvos em {os.path.abspath(OUTPUT_FILE)}")

if __name__ == "__main__":
    calibrate()
