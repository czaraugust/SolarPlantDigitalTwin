"""
Headless: Analise de Impacto da Inclinacao do Painel
Simula diferentes angulos de inclinacao (tilt) de 0 a 20 graus (passo 1).
Calcula energia gerada (kWh) para cada inclinacao.

O angulo de azimute permanece 0 (Norte).
A irradiancia POA muda com o tilt, afetando toda a cadeia:
POA -> Temp Celula -> Single Diode -> M4 -> Eficiencia -> Energia
"""

import sys
import os
# Adiciona a raiz do projeto ao Python path de busca de módulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import pvlib

from core.solar_calculator import CalculadoraSolar
from core.irradiance_calculator import calcular_componentes_irradiancia
from core.inverter_model import InverterModel
from core.config import DATASET_16D_PATH, RESULTS_DIR

# --- CONFIGURACAO ---
CSV_PATH = DATASET_16D_PATH

LATITUDE = -9.55762188835476
LONGITUDE = -35.78094625196216
TZ_OFFSET = -3

DATASHEET = {
    'celltype': 'polySi',
    'v_mp': 31.7, 'i_mp': 8.52,
    'v_oc': 38.8, 'i_sc': 9.09,
    'alpha_sc': 0.005454,
    'beta_voc': -0.1164,
    'gamma_pmp': -0.40,
    'cells_in_series': 60,
}

S1_SERIES = 10
S2_SERIES = 9
TOTAL_MODULES = S1_SERIES + S2_SERIES

ALBEDO = 0.2
AZIMUTH = 0.0  # Norte

P_NOMINAL = 5000.0
V_PARTIDA = 120.0

M4 = {'a': 6.263008, 'b': -30.290082, 'c': -1.811529, 'd': 0.117656, 'e': 72.7470}

TILTS = list(range(0, 21))  # 0 a 20 graus





def run():
    print("=" * 70)
    print("  ANALISE DE IMPACTO DA INCLINACAO DO PAINEL (0-20 graus)")
    print("=" * 70)

    # --- CARREGAR DADOS ---
    print(f"\nCarregando CSV...")
    df = pd.read_csv(CSV_PATH)
    df['datetime'] = pd.to_datetime(df['Date'].astype(str) + ' ' + df['Time'].astype(str))
    df = df.set_index('datetime')
    df = df.between_time('05:00', '18:00')

    df['Wind Speed'] = pd.to_numeric(df['Wind Speed'], errors='coerce') / 3.6
    cols = ['Amb. Temperature', 'Irradiance', 'PV Temperature',
            'Voltage S1', 'Current S1', 'Voltage S2', 'Current S2', 'Power']
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=cols + ['Wind Speed'])

    n = len(df)
    n_dias = len(df.index.normalize().unique())
    print(f"Registros: {n} | Dias: {n_dias}")

    # --- PRE-CALCULAR POSICAO SOLAR (independe do tilt) ---
    print("Pre-calculando posicao solar...")
    timestamps = df.index.to_pydatetime()
    ghis = df['Irradiance'].values
    v_s1 = df['Voltage S1'].values
    v_s2 = df['Voltage S2'].values
    temp_mod = df['PV Temperature'].values

    solar_data = []
    for i, dt in enumerate(timestamps):
        cs = CalculadoraSolar(dt, LATITUDE, LONGITUDE, TZ_OFFSET)
        solar_data.append({
            'zenith': 90 - cs.elevacao,
            'azimuth': cs.azimute,
            'dia': cs.numero_do_dia
        })
        if i % 2000 == 0:
            print(f"  {i}/{n}", end='\r')
    print(f"  {n}/{n}")

    # --- PARAMETROS STC (calcula uma vez) ---
    stc = pvlib.ivtools.sdm.fit_cec_sam(
        celltype=DATASHEET['celltype'],
        v_mp=DATASHEET['v_mp'], i_mp=DATASHEET['i_mp'],
        v_oc=DATASHEET['v_oc'], i_sc=DATASHEET['i_sc'],
        alpha_sc=DATASHEET['alpha_sc'], beta_voc=DATASHEET['beta_voc'],
        gamma_pmp=DATASHEET['gamma_pmp'], cells_in_series=DATASHEET['cells_in_series'])
    I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = stc[0:5]

    # --- RODAR CENARIOS POR TILT ---
    print(f"\nRodando {len(TILTS)} cenarios de inclinacao...\n")
    resultados = []

    for tilt in TILTS:
        # 1. Calcular POA para este tilt
        poa_arr = np.zeros(n)
        for i in range(n):
            sd = solar_data[i]
            res = calcular_componentes_irradiancia(
                ghi=ghis[i], albedo=ALBEDO, dia_do_ano=sd['dia'],
                solar_zenith_deg=sd['zenith'], solar_azimuth_deg=sd['azimuth'],
                inclinacao_superficie=tilt, azimute_superficie=AZIMUTH)
            poa_arr[i] = res['global']

        poa_global = pd.Series(poa_arr, index=df.index)

        # 2. Temperatura de celula
        temp_cell = pvlib.temperature.sapm_cell_from_module(
            module_temperature=df['PV Temperature'], poa_global=poa_global, deltaT=1.0)

        # 3. Modelo eletrico
        eff_irr = poa_global.clip(upper=1400.0)
        dp = pvlib.pvsystem.calcparams_desoto(
            effective_irradiance=eff_irr, temp_cell=temp_cell,
            alpha_sc=DATASHEET['alpha_sc'],
            a_ref=a_ref, I_L_ref=I_L_ref, I_o_ref=I_o_ref,
            R_sh_ref=R_sh_ref, R_s=R_s,
            EgRef=1.121, dEgdT=-0.0002677)

        IL, I0, Rs, Rsh, nNsVth = dp
        sd_res = pvlib.pvsystem.singlediode(
            photocurrent=IL, saturation_current=I0,
            resistance_series=Rs, resistance_shunt=Rsh,
            nNsVth=nNsVth, method='lambertw')

        p_dc_raw = sd_res['p_mp'] * TOTAL_MODULES
        p_dc_m4 = (M4['a'] * p_dc_raw +
                   M4['b'] * poa_arr +
                   M4['c'] * temp_mod +
                   M4['d'] * poa_arr * temp_mod +
                   M4['e'])
        p_dc_m4 = np.clip(p_dc_m4, 0, None)

        # 4. Maquina de estados + Eficiencia
        sm = InverterModel(v_partida=V_PARTIDA)
        p_ac = np.zeros(n)
        for i in range(n):
            estado, p_ac_sim = sm.step(v_s1[i], v_s2[i], p_dc_m4[i])
            p_ac[i] = p_ac_sim

        # 5. Energia
        dt_h = 1.0 / 60.0
        energy_kwh = (p_ac * dt_h).sum() / 1000.0
        poa_media = poa_arr[poa_arr > 10].mean()

        resultados.append({
            'tilt': tilt,
            'energy_kwh': energy_kwh,
            'energy_dia_kwh': energy_kwh / n_dias,
            'poa_media': poa_media,
        })

        print(f"  Tilt {tilt:>2} graus | POA media: {poa_media:>6.1f} W/m2 | "
              f"Energia: {energy_kwh:>7.1f} kWh | Media/dia: {energy_kwh/n_dias:.2f} kWh/dia")

    # --- RESUMO ---
    df_res = pd.DataFrame(resultados)
    best = df_res.loc[df_res['energy_kwh'].idxmax()]
    atual = df_res[df_res['tilt'] == 5].iloc[0]

    print("\n" + "=" * 70)
    print("  RESUMO")
    print("=" * 70)
    print(f"  Periodo: {n_dias} dias ({df.index[0].date()} a {df.index[-1].date()})")
    print(f"  Inclinacao atual: 5 graus -> {atual['energy_kwh']:.1f} kWh ({atual['energy_dia_kwh']:.2f} kWh/dia)")
    print(f"  Melhor inclinacao: {int(best['tilt'])} graus -> {best['energy_kwh']:.1f} kWh ({best['energy_dia_kwh']:.2f} kWh/dia)")
    ganho = (best['energy_kwh'] - atual['energy_kwh']) / atual['energy_kwh'] * 100
    print(f"  Ganho potencial: {ganho:+.2f}%")
    print("=" * 70)

    # Salvar CSV
    OUTPUT = os.path.join(RESULTS_DIR, "resultado_analise_inclinacao.csv")
    df_res.to_csv(OUTPUT, index=False)
    print(f"\nCSV salvo: {os.path.abspath(OUTPUT)}")


if __name__ == "__main__":
    run()
