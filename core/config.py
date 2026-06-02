import os

# Caminhos base do projeto
CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CORE_DIR)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
PLOTS_DIR = os.path.join(PROJECT_ROOT, "plots")

# Datasets
DATASET_16D_PATH = os.path.join(DATA_DIR, "DATASET_MESTRE_COMPLETO.csv")
DATASET_1ANO_PATH = os.path.join(DATA_DIR, "DADOS DE 1 ANO.csv")

# Constantes Geográficas e Ambientais
LATITUDE = -9.55762188835476
LONGITUDE = -35.78094625196216
TZ_OFFSET = -3
ALBEDO = 0.2

# Parâmetros do Arranjo Fotovoltaico (Real)
S1_SERIES = 10
S2_SERIES = 9
TOTAL_MODULES = S1_SERIES + S2_SERIES

# Parâmetros Nominais do Módulo (Jinko JKM270PP)
DATASHEET_JINKO = {
    'cell_type': 'polySi',
    'v_mp': 31.7,
    'i_mp': 8.52,
    'v_oc': 38.8,
    'i_sc': 9.09,
    'alpha_sc': 0.005454,
    'beta_voc': -0.1164,
    'gamma_pmp': -0.40,
    'cells_in_series': 60
}

# Parâmetros de diodo único calibrados para o painel (1 ano)
SDM_CALIBRADO_1ANO = {
    'I_L_ref': 8.917905e+00,
    'I_o_ref': 1.144722e-10,
    'R_s': 4.016453e-01,
    'R_sh_ref': 2.536722e+02,
    'a_ref': 1.480987e+00
}

# Coeficientes do Modelo de Correção M4 (calibrados em 1 ano)
M4_COEFS = {
    'a': 4.972190,
    'b': -20.501738,
    'c': 4.763467,
    'd': 0.075893,
    'e': -93.8467
}

# Parâmetros de Ajuste Térmico SAPM
SAPM_DELTAT = 1.0

# Constantes e Coeficientes de Eficiência do Inversor (calibrados em 1 ano com otimização restrita do QA)
INVERTER_CONFIG = {
    'p_nominal': 5000.0,    # W
    'v_partida': 120.0,    # V
    'p_standby': 26.0,     # W (consumo de controle)
    'tempo_atraso': 19,    # minutos (timer para sincronizar e ligar)
    'eff_coefs': [95.8041, 9999.9996, 2.0515e-05] # Coefs a, b, c para a - b/Pdc - c*Pdc
}
