import numpy as np
import warnings
import pvlib
from scipy.optimize import minimize
from pvlib import pvsystem, singlediode
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
from core.config import DATASHEET_JINKO, TOTAL_MODULES


class Calibrator:
    """
    Classe responsável pelo pipeline de calibração vetorizada de alto desempenho.
    Realiza a otimização dos parâmetros elétricos do módulo fotovoltaico (SDM),
    ajuste das correções multivariadas (M4 e Poly2) e calibração da eficiência do inversor.
    """

    def __init__(self, datasheet=None, total_modules=None):
        """
        Inicializa o calibrador com os parâmetros de datasheet do módulo e
        o número total de módulos no sistema.

        Args:
            datasheet (dict, opcional): Dicionário com dados do módulo fotovoltaico.
                                       Se None, usa DATASHEET_JINKO do core/config.py.
            total_modules (int, opcional): Número total de módulos no sistema.
                                          Se None, usa TOTAL_MODULES do core/config.py.
        """
        self.datasheet = datasheet if datasheet is not None else DATASHEET_JINKO
        self.total_modules = total_modules if total_modules is not None else TOTAL_MODULES

    def predict_dc(self, sdm_params, poa_global, temp_cell):
        """
        Calcula a potência DC prevista do arranjo usando os parâmetros do SDM fornecidos.

        Args:
            sdm_params (array-like): Parâmetros do SDM [I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref].
            poa_global (np.ndarray): Irradiância global no plano do array (W/m²).
            temp_cell (np.ndarray): Temperatura das células do painel (°C).

        Returns:
            np.ndarray: Potência DC prevista do arranjo em Watts.
        """
        I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref = sdm_params
        eff_irr = np.clip(poa_global, 0.0, 1400.0)
        
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            # Escala os parâmetros de STC para as condições de operação reais
            dp = pvsystem.calcparams_desoto(
                effective_irradiance=eff_irr,
                temp_cell=temp_cell,
                alpha_sc=self.datasheet['alpha_sc'],
                a_ref=a_ref,
                I_L_ref=I_L_ref,
                I_o_ref=I_o_ref,
                R_sh_ref=R_sh_ref,
                R_s=R_s,
                EgRef=1.121,
                dEgdT=-0.0002677
            )
            IL, I0, Rs, Rsh, nNsVth = dp
            # Calcula o ponto de máxima potência por módulo
            mpp_res = singlediode.bishop88_mpp(
                photocurrent=IL,
                saturation_current=I0,
                resistance_series=Rs,
                resistance_shunt=Rsh,
                nNsVth=nNsVth,
                method='newton'
            )
            p_model = mpp_res[2] * self.total_modules
            
        return np.nan_to_num(p_model, nan=0.0)

    def calibrate_sdm_parameters(self, poa_global, temp_cell, p_dc_real):
        """
        Calibra os 5 parâmetros do Single Diode Model (SDM) para STC
        (I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref) minimizando o RMSE em relação
        à potência DC real medida.

        Args:
            poa_global (np.ndarray): Irradiância global no plano do array (W/m²).
            temp_cell (np.ndarray): Temperatura das células do painel (°C).
            p_dc_real (np.ndarray): Potência DC real medida no arranjo (W).

        Returns:
            np.ndarray: Vetor com os 5 parâmetros calibrados [I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref].
        """
        # Calcular estimativa inicial usando fit_cec_sam com dados do datasheet
        print("Calculando parâmetros iniciais (CEC SAM)...")
        stc_original = pvlib.ivtools.sdm.fit_cec_sam(
            celltype=self.datasheet.get('cell_type', 'polySi'),
            v_mp=self.datasheet['v_mp'],
            i_mp=self.datasheet['i_mp'],
            v_oc=self.datasheet['v_oc'],
            i_sc=self.datasheet['i_sc'],
            alpha_sc=self.datasheet['alpha_sc'],
            beta_voc=self.datasheet['beta_voc'],
            gamma_pmp=self.datasheet['gamma_pmp'],
            cells_in_series=self.datasheet['cells_in_series']
        )
        # O fit_cec_sam retorna (I_L_ref, I_o_ref, R_s, R_sh_ref, a_ref, Adjust)
        # Extraímos apenas os primeiros 5 parâmetros
        original_params = np.array(stc_original[0:5])

        # Definir limites (bounds) descritos no SolarExpert
        bounds = [
            (original_params[0] * 0.7, original_params[0] * 1.3),  # I_L_ref
            (1e-13, 1e-7),                                          # I_o_ref
            (0.01, 2.0),                                             # R_s
            (5.0, 5000.0),                                           # R_sh_ref
            (0.5, 3.0),                                              # a_ref
        ]

        def objective(params):
            try:
                p_model = self.predict_dc(params, poa_global, temp_cell)
                rmse = np.sqrt(((p_model - p_dc_real) ** 2).mean())
                return rmse if not np.isnan(rmse) else 1e9
            except Exception:
                return 1e9

        print("Iniciando a otimização dos parâmetros SDM via L-BFGS-B...")
        result = minimize(
            objective,
            original_params,
            method='L-BFGS-B',
            bounds=bounds,
            options={'disp': True, 'maxiter': 500, 'ftol': 1e-6}
        )

        if not result.success:
            print(f"Aviso: Otimização terminou com falha ou aviso. Mensagem: {result.message}")

        return result.x

    def fit_m4_correction(self, p_pred, poa_global, temp_module, p_dc_real):
        """
        Ajusta os coeficientes das correções multivariadas M4 e Poly2 sobre o modelo elétrico.

        Equação M4:
            P_corr = a * P_pred + b * POA + c * T_module + d * (POA * T_module) + e

        Modelo Poly2 (Quadrático):
            P_corr = Regressão Linear com features polinomiais de grau 2 das variáveis [P_pred, POA, T_module].

        Args:
            p_pred (np.ndarray): Potência DC prevista pelo SDM (W).
            poa_global (np.ndarray): Irradiância POA global (W/m²).
            temp_module (np.ndarray): Temperatura medida do módulo (°C).
            p_dc_real (np.ndarray): Potência DC real medida (W).

        Returns:
            dict: Dicionário contendo:
                - 'm4': Dicionário com os coeficientes 'a', 'b', 'c', 'd', 'e'
                - 'poly2': Dicionário com o objeto regressor treinado e a transformação de features
        """
        # --- 1. Ajustar M4 ---
        # Regressores: P_pred, POA, T_module, POA * T_module
        X_m4 = np.column_stack([p_pred, poa_global, temp_module, poa_global * temp_module])
        reg_m4 = LinearRegression().fit(X_m4, p_dc_real)

        coefs_m4 = {
            'a': reg_m4.coef_[0],
            'b': reg_m4.coef_[1],
            'c': reg_m4.coef_[2],
            'd': reg_m4.coef_[3],
            'e': reg_m4.intercept_
        }

        # --- 2. Ajustar Poly2 (Polinomial grau 2) ---
        poly_transformer = PolynomialFeatures(degree=2, include_bias=False)
        X_poly_in = np.column_stack([p_pred, poa_global, temp_module])
        X_poly = poly_transformer.fit_transform(X_poly_in)
        reg_poly = LinearRegression().fit(X_poly, p_dc_real)

        coefs_poly = {
            'transformer': poly_transformer,
            'regressor': reg_poly,
            'coefs': reg_poly.coef_,
            'intercept': reg_poly.intercept_
        }

        return {
            'm4': coefs_m4,
            'poly2': coefs_poly
        }

    def calibrate_inverter(self, p_dc_real, p_ac_real):
        """
        Calibração otimizada da eficiência do inversor com consistência física:
            eff = a - b / P_dc - c * P_dc
        Filtra dados de operação estáveis (P_dc > 100 W, P_ac > 10 W) e
        remove outliers de eficiência física (70% <= eta <= 98%).
        Utiliza otimização restrita (a <= 100, b >= 0, c >= 0) para
        respeitar a termodinâmica de perdas ôhmicas.
        """
        # 1. Filtros físicos de estabilidade e remoção de ruído
        eta_bruta = np.where(p_dc_real > 1.0, (p_ac_real / p_dc_real) * 100.0, 0.0)
        mask = (p_dc_real > 100.0) & (p_ac_real > 10.0) & (eta_bruta >= 70.0) & (eta_bruta <= 98.0)
        
        if np.sum(mask) < 10:
            raise ValueError("Poucos pontos de dados válidos após filtragem física.")

        pdc_filt = p_dc_real[mask]
        eta_real = eta_bruta[mask]

        # 2. Definição da função de perda (erro quadrático médio)
        def loss_func(params):
            a, b, c = params
            eta_pred = a - (b / pdc_filt) - (c * pdc_filt)
            return np.mean((eta_pred - eta_real) ** 2)

        # 3. Otimização com restrições físicas (bounds)
        from scipy.optimize import minimize
        res = minimize(
            loss_func, 
            x0=[95.0, 10000.0, 1.25e-4], 
            bounds=[(0.0, 100.0), (0.0, None), (0.0, None)]
        )
        
        a, b, c = res.x
        return a, b, c
