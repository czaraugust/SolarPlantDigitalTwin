import pvlib
import pandas as pd
import numpy as np


class PVSystemModel:
    """
    Modela um sistema fotovoltaico completo, desde um único módulo até um arranjo
    com strings em série e paralelo, usando a biblioteca pvlib.
    """

    # Coeficientes de correção M4 (ajustados por regressão no dataset real)
    # P_corr = a*P_pred + b*POA + c*Temp + d*POA*Temp + e
    M4_COEFS = {
        'a': 6.263008,
        'b': -30.290082,
        'c': -1.811529,
        'd': 0.117656,
        'e': 72.7470
    }

    def __init__(self, datasheet_params, modules_per_string, strings_in_parallel):
        """
        Inicializa o modelo do sistema.
        """
        self.datasheet = datasheet_params
        if isinstance(modules_per_string, int):
            self.modules_per_string = [modules_per_string]
        else:
            self.modules_per_string = modules_per_string # Expects list of ints
            
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

    def calculate_curves_and_mpp(self, poa_global, temp_air, wind_speed, forced_cell_temp=None):
        """
        Calcula as curvas I-V, P-V e o ponto de máxima potência (MPP) para o 
        sistema completo sob as condições operacionais fornecidas.
        
        Args:
            poa_global: Irradiância no plano do array (W/m²)
            temp_air: Temperatura ambiente (°C) - Usada se forced_cell_temp=None
            wind_speed: Velocidade do vento (m/s) - Usada se forced_cell_temp=None
            forced_cell_temp: (Opcional) Temperatura da Célula (°C). Se fornecida,
                              ignora o modelo Faiman e usa este valor diretamente.
        """
        try:
            # Evita RuntimeWarnings (overflow/invalid value) em situações de muito baixa irradiância (noite)
            if poa_global < 5.0:
                return {
                    'v_curve': np.zeros(200),
                    'i_curve': np.zeros(200),
                    'p_curve': np.zeros(200),
                    'mpp': (0.0, 0.0, 0.0),
                    'mpp_raw': 0.0
                }
            
            # --- PROTEÇÃO CONTRA OVERFLOW ---
            # O usuário relatou picos de irradiância > 1700 W/m² que causam 'overflow in exp' no modelo de diodo.
            # Limitamos a entrada para o modelo elétrico em 1400 W/m² (valor seguro e fisicamente extremo)
            # Isso não altera o gráfico de irradiância, apenas evita o crash do cálculo.
            effective_irradiance = min(poa_global, 1400.0)

            # Contexto para ignorar warnings de overflow que poluem o console
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore', category=RuntimeWarning)
                
                # 1. Calcular a temperatura da célula (ou usar valor forçado)
                # 1. Calcular a temperatura da célula
                # SE houver temperatura medida do módulo, usar modelo SAPM para estimar Célula
                # Modelo SAPM simplificado: Tcell = Tmodule + (POA / 1000) * DeltaT
                # O usuário definiu DeltaT = 1.0
                if forced_cell_temp is not None:
                    # assumindo que forced_cell_temp agora é a temperatura do MODULO (sensor)
                    # se o usuario passar a temp da celula direto, a logica muda, mas o pedido foi "usar modelo sapm"
                    # para garantir compatibilidade com chamadas antigas que passavam temp da celula, 
                    # vamos assumir que o argumento reflete o sensor colado no verso.
                    temp_module = float(forced_cell_temp)
                    temp_cell = temp_module + (effective_irradiance / 1000.0) * 1.0
                else:
                    # Fallback para Faiman se não tiver sensor
                    temp_cell = pvlib.temperature.faiman(
                        poa_global=effective_irradiance,
                        temp_air=temp_air,
                        wind_speed=wind_speed
                    )

                # 2. Escalar os parâmetros de STC para as condições de operação atuais
       
                photocurrent, saturation_current, resistance_series, resistance_shunt, nNsVth = pvlib.pvsystem.calcparams_desoto(
                    effective_irradiance=effective_irradiance,
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

                # Constrói vetores de curva a partir dos pontos-chave para a plotagem.
                v_oc_module_sim = iv_module_points['v_oc']

                # Ajuste no range para evitar prolongamento visual (cauda zero)
                # Antes era 1.1 (110%), agora 1.02 (102%) apenas para garantir o cruzamento
                v_curve_mod = np.linspace(0, v_oc_module_sim * 1.02, 200)

                # --- CORREÇÃO FINAL AQUI ---
                # Usa a função `solve_lambertw` do caminho correto
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
                # MODIFICADO: Suporte para Multi-Strings (Assimétricas em Paralelo)
                
                # Base de Tensão comum para soma de correntes (vai até a maior Voc possível)
                # Aproximadamente Voc_mod * max(modules_per_string)
                max_modules = max(self.modules_per_string)
                # Base de Tensão comum para soma de correntes (vai até a maior Voc possível)
                # Aproximadamente Voc_mod * max(modules_per_string)
                max_modules = max(self.modules_per_string)
                v_max_system = v_oc_module_sim * max_modules * 1.0 
                common_v_axis = np.linspace(0, v_max_system, 200)
                
                total_i_curve = np.zeros_like(common_v_axis)
                
                # MPP Total Accumulators
                total_p_mpp = 0.0
                # V_mpp e I_mpp do sistema combinado são complexos de definir apenas somando, 
                # mas para fins de "MPP do Inversor" (rastreamento global), podemos pegar o pico da curva combinada.
                
                for n_modules in self.modules_per_string:
                    # Curva da String (n_modules em série)
                    # Escala tensão
                    v_string_curve = v_curve_mod * n_modules
                    
                    # Interpola corrente para o eixo comum de tensão
                    # Pontos onde a tensão da string é menor que o eixo comum terão corrente extrapolada (ou zero se v > voc)
                    # pvlib singlediode devolve corrente. Se V > Voc, I deve ser 0.
                    
                    # Vamos usar a função singlediode novamente para o eixo comum escalado? 
                    # Não, pois singlediode é por módulo.
                    
                    # Mais fácil: Calcular I_module para (common_v_axis / n_modules)
                    v_per_module_requested = common_v_axis / n_modules
                    
                    i_string_currents = pvlib.singlediode._lambertw_i_from_v(
                        v_per_module_requested,
                        photocurrent,
                        saturation_current,
                        resistance_series,
                        resistance_shunt,
                        nNsVth
                    )
                    # Corrigir NaN ou negativos para 0
                    i_string_currents = np.nan_to_num(i_string_currents, nan=0.0)
                    i_string_currents[i_string_currents < 0] = 0
                    
                    # Multiplica por strings em paralelo (assumindo que strings_in_parallel se aplica a CADA sub-arranjo, 
                    # ou se divide. O usuario disse "10 em serie em paralelo com 9 em serie".
                    # Isso implica 1 string de 10 e 1 string de 9. Total = 2 strings.
                    # Então strings_in_parallel deve ser aplicado globalmente ou é 1 para cada? 
                    # Vamos assumir que self.strings_in_parallel é o multiplicador global.
                    # Mas no caso dele é 1 de 10 e 1 de 9. Então strings_in_parallel = 1.
                    
                    total_i_curve += (i_string_currents * self.strings_in_parallel)

                # Calcular Curva de Potência Combinada
                total_p_curve = common_v_axis * total_i_curve
                
                # Encontrar MPP Combinado
                idx_mpp = np.argmax(total_p_curve)
                p_mpp_system = total_p_curve[idx_mpp]
                v_mpp_system = common_v_axis[idx_mpp]
                i_mpp_system = total_i_curve[idx_mpp]

                # --- CORREÇÃO M4 (Regressão Multivariável) ---
                # M4 foi treinado com p_mp_modulo * 19 módulos.
                # Só aplica se a config atual bate com a do treinamento.
                total_modules = sum(self.modules_per_string)
                M4_TOTAL_MODULES = 19  # Config do treinamento

                if total_modules == M4_TOTAL_MODULES:
                    p_simple = p_mp_mod * total_modules
                    poa = effective_irradiance
                    temp_mod = forced_cell_temp if forced_cell_temp is not None else temp_cell
                    c = self.M4_COEFS
                    p_mpp_corrected = (c['a'] * p_simple + 
                                       c['b'] * poa + 
                                       c['c'] * temp_mod + 
                                       c['d'] * poa * temp_mod + 
                                       c['e'])
                    p_mpp_corrected = max(0.0, p_mpp_corrected)
                else:
                    # Config diferente do treinamento — usa MPP direto
                    p_mpp_corrected = p_mpp_system

                return {
                    'v_curve': common_v_axis,
                    'i_curve': total_i_curve,
                    'p_curve': total_p_curve,
                    'mpp': (v_mpp_system, i_mpp_system, p_mpp_corrected),
                    'mpp_raw': p_mpp_system
                }
        except Exception:
            # Em caso de erro numérico, retorna zero para evitar crash
            return {
                'v_curve': np.zeros(200),
                'i_curve': np.zeros(200),
                'p_curve': np.zeros(200),
                'mpp': (0.0, 0.0, 0.0),
                'mpp_raw': 0.0
            }
