import pvlib
import pandas as pd
import numpy as np


class PVSystemModel:
    """
    Modela um sistema fotovoltaico completo, desde um único módulo até um arranjo
    com strings em série e paralelo, usando a biblioteca pvlib.
    """

    def __init__(self, datasheet_params, modules_per_string, strings_in_parallel):
        """
        Inicializa o modelo do sistema.
        """
        self.datasheet = datasheet_params
        self.modules_per_string = modules_per_string
        self.strings_in_parallel = strings_in_parallel

        # Armazena os parâmetros do modelo de diodo único calculados para STC
        self.stc_params = self._calculate_stc_parameters()

    def _calculate_stc_parameters(self):
        """
        Ajusta os parâmetros do modelo de diodo único para STC usando os dados do datasheet.
        """
        I_L_ref, I_0_ref, R_s, R_sh, a_ref, Adjust = pvlib.ivtools.sdm.fit_cec_sam(
            celltype=self.datasheet['cell_type'],
            v_mp=self.datasheet['v_mp'],
            i_mp=self.datasheet['i_mp'],
            v_oc=self.datasheet['v_oc'],
            i_sc=self.datasheet['i_sc'],
            alpha_sc=self.datasheet['alpha_sc'],
            beta_voc=self.datasheet['beta_voc'],
            gamma_pmp=self.datasheet['gamma_pmp'],
            cells_in_series=self.datasheet['cells_in_series']
        )

        return {
            'I_L_ref': I_L_ref,
            'I_0_ref': I_0_ref,
            'R_s': R_s,
            'R_sh_ref': R_sh,
            'a_ref': a_ref
        }

    def calculate_curves_and_mpp(self, poa_global, temp_air, wind_speed):
        """
        Calcula as curvas I-V, P-V e o ponto de máxima potência (MPP) para o 
        sistema completo sob as condições operacionais fornecidas.
        """
        # Evita RuntimeWarnings (overflow/invalid value) em situações de muito baixa irradiância (noite)
        if poa_global < 1.0:
            return {
                'v_curve': np.zeros(200),
                'i_curve': np.zeros(200),
                'p_curve': np.zeros(200),
                'mpp': (0.0, 0.0, 0.0)
            }
        # 1. Calcular a temperatura da célula
        temp_cell = pvlib.temperature.faiman(
            poa_global=poa_global,
            temp_air=temp_air,
            wind_speed=wind_speed
        )

        # 2. Escalar os parâmetros de STC para as condições de operação atuais
        photocurrent, saturation_current, resistance_series, resistance_shunt, nNsVth = pvlib.pvsystem.calcparams_desoto(
            effective_irradiance=poa_global,
            temp_cell=temp_cell,
            alpha_sc=self.datasheet['alpha_sc'],
            a_ref=self.stc_params['a_ref'],
            I_L_ref=self.stc_params['I_L_ref'],
            I_o_ref=self.stc_params['I_0_ref'],
            R_sh_ref=self.stc_params['R_sh_ref'],
            R_s=self.stc_params['R_s'],
            EgRef=1.121,
            dEgdT=-0.0002677
        )

        # 3. Calcular os 5 pontos principais da curva I-V do módulo para obter o MPP e Voc precisos
        iv_module_points = pvlib.pvsystem.singlediode(
            photocurrent=photocurrent,
            saturation_current=saturation_current,
            resistance_series=resistance_series,
            resistance_shunt=resistance_shunt,
            nNsVth=nNsVth,
            method='lambertw'
        )

        # Constrói vetores de curva a partir dos pontos-chave para a plotagem.
        v_oc_mod = iv_module_points['v_oc']

        v_curve_mod = np.linspace(0, v_oc_mod, 200)

        # --- CORREÇÃO FINAL AQUI ---
        # Usa a função `solve_lambertw` do caminho correto: pvlib.ivtools.sdiode
        i_curve_mod = pvlib.singlediode._lambertw_i_from_v(
            v_curve_mod,
            photocurrent,
            saturation_current,
            resistance_series,
            resistance_shunt,
            nNsVth
        )
        p_curve_mod = v_curve_mod * i_curve_mod

        # 4. Extrai o MPP dos pontos calculados
        v_mp_mod = iv_module_points['v_mp']
        i_mp_mod = iv_module_points['i_mp']
        p_mp_mod = iv_module_points['p_mp']

        # 5. Escalar as curvas e o MPP para o sistema completo (Array)
        v_array = v_curve_mod * self.modules_per_string
        i_array = i_curve_mod * self.strings_in_parallel
        p_array = v_array * i_array

        v_mp_array = v_mp_mod * self.modules_per_string
        i_mp_array = i_mp_mod * self.strings_in_parallel
        p_mp_array = p_mp_mod * self.modules_per_string * self.strings_in_parallel

        return {
            'v_curve': v_array,
            'i_curve': i_array,
            'p_curve': p_array,
            'mpp': (v_mp_array, i_mp_array, p_mp_array)
        }
