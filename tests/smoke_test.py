import sys
import os
from datetime import datetime
import numpy as np

# Adicionar a raiz do projeto ao path para garantir que core seja importado corretamente
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_smoke():
    print("Iniciando testes de fumaça (Smoke Test) dos módulos core...")
    
    # 1. Testando Imports das classes e funções principais
    print("\n[PASSO 1] Testando imports...")
    try:
        from core.solar_calculator import CalculadoraSolar
        from core.irradiance_calculator import calcular_componentes_irradiancia
        from core.pv_module_model import PVSystemModel
        from core.inverter_model import InverterModel
        from core.config import (
            DATASHEET_JINKO, 
            S1_SERIES, 
            S2_SERIES, 
            INVERTER_CONFIG,
            LATITUDE,
            LONGITUDE,
            TZ_OFFSET,
            ALBEDO
        )
        print("[OK] Todos os imports realizados com sucesso!")
    except Exception as e:
        print(f"[ERRO] Falha ao importar os módulos core: {e}")
        raise e

    # 2. Testando CalculadoraSolar
    print("\n[PASSO 2] Testando CalculadoraSolar...")
    try:
        dt = datetime(2023, 6, 21, 12, 0, 0)
        cs = CalculadoraSolar(dt, LATITUDE, LONGITUDE, TZ_OFFSET)
        
        print(f"  Dia do ano: {cs.numero_do_dia}")
        print(f"  Declinação: {cs.declinacao:.4f}°")
        print(f"  Elevação Solar: {cs.elevacao:.4f}°")
        print(f"  Azimute Solar: {cs.azimute:.4f}°")
        print(f"  Nascer do sol: {cs.hora_nascer_sol.strftime('%H:%M:%S')}")
        print(f"  Pôr do sol: {cs.hora_por_sol.strftime('%H:%M:%S')}")
        
        assert cs.elevacao is not None, "Elevação solar calculada é None"
        assert cs.azimute is not None, "Azimute solar calculado é None"
        print("[OK] CalculadoraSolar instanciada e executada com sucesso!")
    except Exception as e:
        print(f"[ERRO] Falha no teste da CalculadoraSolar: {e}")
        raise e

    # 3. Testando calcular_componentes_irradiancia
    print("\n[PASSO 3] Testando calcular_componentes_irradiancia...")
    try:
        irr_res = calcular_componentes_irradiancia(
            ghi=800.0,
            albedo=ALBEDO,
            dia_do_ano=cs.numero_do_dia,
            solar_zenith_deg=90.0 - cs.elevacao,
            solar_azimuth_deg=cs.azimute,
            inclinacao_superficie=10.0,
            azimute_superficie=0.0
        )
        
        print(f"  GHI de entrada: 800.0 W/m²")
        print(f"  POA Global calculado: {irr_res['global']:.2f} W/m²")
        print(f"  Componente direta: {irr_res['direta']:.2f} W/m²")
        print(f"  Componente difusa: {irr_res['difusa']:.2f} W/m²")
        print(f"  Componente refletida: {irr_res['refletida']:.2f} W/m²")
        
        assert irr_res['global'] >= 0, "POA Global não pode ser negativo"
        assert not np.isnan(irr_res['global']), "POA Global é NaN"
        print("[OK] calcular_componentes_irradiancia executada com sucesso!")
    except Exception as e:
        print(f"[ERRO] Falha no teste de calcular_componentes_irradiancia: {e}")
        raise e

    # 4. Testando PVSystemModel (Curvas/MPP)
    print("\n[PASSO 4] Testando PVSystemModel...")
    try:
        # Instanciar usando os dados de STC do config
        pv_model = PVSystemModel(
            datasheet_params=DATASHEET_JINKO,
            modules_per_string=[S1_SERIES, S2_SERIES],
            strings_in_parallel=1
        )
        
        # Testar com condições normais
        res_pv = pv_model.calculate_curves_and_mpp(
            poa_global=800.0,
            temp_air=25.0,
            wind_speed=1.0,
            forced_cell_temp=45.0
        )
        
        v_mpp, i_mpp, p_mpp = res_pv['mpp']
        print(f"  Tensão MPP do Sistema: {v_mpp:.2f} V")
        print(f"  Corrente MPP do Sistema: {i_mpp:.2f} A")
        print(f"  Potência MPP Corrigida (M4): {p_mpp:.2f} W")
        print(f"  Potência MPP Não Corrigida (Raw): {res_pv['mpp_raw']:.2f} W")
        
        assert p_mpp > 0, "Potência MPP calculada deve ser maior que zero"
        assert len(res_pv['v_curve']) == 200, "Vetor de curva de tensão deve ter 200 pontos"
        assert not np.isnan(p_mpp), "Potência MPP é NaN"
        
        # Testar com irradiância zero (noite) para garantir robustez
        res_pv_noite = pv_model.calculate_curves_and_mpp(
            poa_global=0.0,
            temp_air=20.0,
            wind_speed=0.0,
            forced_cell_temp=20.0
        )
        assert res_pv_noite['mpp'] == (0.0, 0.0, 0.0), "Durante a noite o MPP deve ser zero"
        print("[OK] PVSystemModel instanciado e executado com sucesso (inclusive caso noturno)!")
    except Exception as e:
        print(f"[ERRO] Falha no teste do PVSystemModel: {e}")
        raise e

    # 5. Testando InverterModel
    print("\n[PASSO 5] Testando InverterModel e FSM Vetorizada...")
    try:
        inverter = InverterModel()
        
        # Dados fictícios para simulação de FSM vetorizada
        v_s1_arr = np.array([0.0]*5 + [100.0]*5 + [150.0]*15 + [0.0]*5)
        v_s2_arr = np.array([0.0]*5 + [90.0]*5 + [140.0]*15 + [0.0]*5)
        p_dc_arr = np.array([0.0]*5 + [15.0]*5 + [1000.0]*15 + [0.0]*5)
        
        estados, p_ac_arr = inverter.simulate_fsm_vectorized(v_s1_arr, v_s2_arr, p_dc_arr)
        
        print(f"  Tamanho dos arrays: {len(p_ac_arr)}")
        print(f"  Estados resultantes: {set(estados)}")
        print(f"  Máxima Potência AC: {p_ac_arr.max():.2f} W")
        print(f"  Exemplo de estado no minuto 15: {estados[15]} - Potência AC: {p_ac_arr[15]:.2f} W")
        
        assert len(estados) == len(v_s1_arr), "Comprimento dos estados difere do de entrada"
        assert len(p_ac_arr) == len(v_s1_arr), "Comprimento da Potência AC difere do de entrada"
        assert p_ac_arr.max() <= INVERTER_CONFIG['p_nominal'], "Potência AC máxima excede a nominal do inversor"
        
        print(f"  Estado no minuto 9 (início da luz): {estados[9]}")
        print(f"  Estado no minuto 24 (fim da luz): {estados[24]}")
        
        print("[OK] InverterModel instanciado e FSM vetorizada executada com sucesso!")
    except Exception as e:
        print(f"[ERRO] Falha no teste do InverterModel: {e}")
        raise e

    print("\n=== SMOKE TEST COMPLETO: Todos os testes de fumaca passaram com sucesso! ===")

if __name__ == "__main__":
    test_smoke()
