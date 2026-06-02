import numpy as np
from core.config import INVERTER_CONFIG

class InverterModel:
    """
    Modelagem do Inversor de Conexão à Rede (On-Grid).
    Encapsula a Máquina de Estados de Partida/Parada (FSM) e a Curva de Eficiência.
    """
    
    DESLIGADO = "DESLIGADO"
    LIGADO = "LIGADO"

    def __init__(self, v_partida=None):
        """
        Inicializa o modelo do inversor carregando as configurações e definindo
        o estado inicial como DESLIGADO.
        """
        # Parâmetros do inversor lidos da configuração centralizada
        self.p_nominal = INVERTER_CONFIG['p_nominal']
        self.v_partida = v_partida if v_partida is not None else INVERTER_CONFIG['v_partida']
        self.p_standby = INVERTER_CONFIG['p_standby']
        self.tempo_atraso = INVERTER_CONFIG['tempo_atraso']
        self.eff_coefs = INVERTER_CONFIG['eff_coefs']
        
        # Estado interno para execução passo a passo (FSM escalar)
        self.estado = self.DESLIGADO
        self.contador_minutos = 0

    def reset(self):
        """
        Reinicia o estado interno do inversor para DESLIGADO e zera o contador.
        
        Args:
            Nenhum.

        Returns:
            None.
        """
        self.estado = self.DESLIGADO
        self.contador_minutos = 0

    def calculate_efficiency(self, p_dc):
        """
        Calcula a eficiência de conversão (%) para uma dada potência de entrada DC.
        Eff = a - b/Pdc - c*Pdc
        
        Args:
            p_dc (float ou np.ndarray): Potência DC de entrada em Watts.

        Returns:
            float ou np.ndarray: Eficiência de conversão em percentual, limitada no intervalo [0.0, 100.0].
        """
        a, b, c = self.eff_coefs
        # Evita divisão por zero ou potências muito baixas
        if isinstance(p_dc, np.ndarray):
            eff = np.where(p_dc > self.p_standby, a - (b / np.maximum(p_dc, 1.0)) - (c * p_dc), 0.0)
            return np.clip(eff, 0.0, 100.0)
        else:
            if p_dc <= self.p_standby:
                return 0.0
            eff = a - (b / p_dc) - (c * p_dc)
            return clip(eff, 0.0, 100.0)

    def calculate_ac_power(self, p_dc, efficiency_pct):
        """
        Calcula a potência AC de saída aplicando a eficiência e o limite de clipping.
        
        Args:
            p_dc (float ou np.ndarray): Potência DC de entrada em Watts.
            efficiency_pct (float ou np.ndarray): Eficiência do inversor em percentual (0-100).

        Returns:
            float ou np.ndarray: Potência AC de saída em Watts, limitada à potência nominal.
        """
        if isinstance(p_dc, np.ndarray):
            p_ac = p_dc * (efficiency_pct / 100.0)
            return np.clip(p_ac, 0.0, self.p_nominal)
        else:
            p_ac = p_dc * (efficiency_pct / 100.0)
            return min(p_ac, self.p_nominal)

    def step(self, v_s1, v_s2, p_dc):
        """
        Executa um passo da FSM escalar (1 chamada = 1 minuto de dados) e retorna 
        o estado atual e a potência AC simulada.
        
        Args:
            v_s1 (float): Tensão da String 1 em Volts.
            v_s2 (float): Tensão da String 2 em Volts.
            p_dc (float): Potência DC de entrada total em Watts.

        Returns:
            tuple: (str, float) contendo o estado atual ('LIGADO' ou 'DESLIGADO') e a potência AC gerada em Watts.
        """
        cond_ligar = (v_s1 >= self.v_partida or v_s2 >= self.v_partida) and (p_dc > self.p_standby)
        cond_desligar = (v_s1 < self.v_partida and v_s2 < self.v_partida) or (p_dc <= self.p_standby)

        if self.estado == self.DESLIGADO:
            if cond_ligar:
                self.contador_minutos += 1
                if self.contador_minutos >= self.tempo_atraso:
                    self.estado = self.LIGADO
                    self.contador_minutos = 0
            else:
                self.contador_minutos = 0
        elif self.estado == self.LIGADO:
            if cond_desligar:
                self.estado = self.DESLIGADO
                self.contador_minutos = 0
            else:
                self.contador_minutos = 0

        # Cálculo da potência AC com base no estado da máquina
        if self.estado == self.LIGADO:
            eff = self.calculate_efficiency(p_dc)
            p_ac = self.calculate_ac_power(p_dc, eff)
        else:
            p_ac = 0.0

        return self.estado, p_ac

    def simulate_fsm_vectorized(self, v_s1_arr, v_s2_arr, p_dc_arr):
        """
        Simula a FSM para arrays NumPy de forma sequencial otimizada para o tempo
        (essencial para manter a coerência do histórico do temporizador de 19 minutos).
        Retorna o array de estados e o array correspondente de potência AC.
        
        Args:
            v_s1_arr (np.ndarray): Histórico de tensão da String 1 (V).
            v_s2_arr (np.ndarray): Histórico de tensão da String 2 (V).
            p_dc_arr (np.ndarray): Histórico de potência DC total de entrada (W).

        Returns:
            tuple: (np.ndarray, np.ndarray) contendo o array de estados e o correspondente array de potência AC.
        """
        n = len(p_dc_arr)
        
        v_partida = self.v_partida
        p_standby = self.p_standby
        tempo_atraso = self.tempo_atraso
        p_nominal = self.p_nominal
        a, b, c = self.eff_coefs
        
        # Pré-calcular condição de ligar de forma vetorizada
        cond_ligar_arr = ((v_s1_arr >= v_partida) | (v_s2_arr >= v_partida)) & (p_dc_arr > p_standby)
        
        ligado_arr = np.zeros(n, dtype=bool)
        estado_atual_ligado = False
        contador = 0
        
        # Loop sequencial apenas para a lógica de transição da FSM (muito rápido)
        for i in range(n):
            if not estado_atual_ligado:
                if cond_ligar_arr[i]:
                    contador += 1
                    if contador >= tempo_atraso:
                        estado_atual_ligado = True
                        contador = 0
                else:
                    contador = 0
            else:
                if not cond_ligar_arr[i]:  # cond_desligar
                    estado_atual_ligado = False
                    contador = 0
                else:
                    contador = 0
            ligado_arr[i] = estado_atual_ligado
            
        # Converter estados booleanos para as strings originais
        estados = np.where(ligado_arr, self.LIGADO, self.DESLIGADO)
        
        # Calcular potência AC de forma totalmente vetorizada
        eff = a - (b / np.maximum(p_dc_arr, 1.0)) - (c * p_dc_arr)
        eff = np.clip(eff, 0.0, 100.0)
        p_ac_arr = p_dc_arr * (eff / 100.0)
        p_ac_arr = np.clip(p_ac_arr, 0.0, p_nominal)
        p_ac_arr = np.where(ligado_arr, p_ac_arr, 0.0)
        
        return estados, p_ac_arr

def clip(val, min_v, max_v):
    """
    Função de clip simples para valores escalares.
    
    Args:
        val (float): Valor a ser limitado.
        min_v (float): Valor mínimo permitido.
        max_v (float): Valor máximo permitido.

    Returns:
        float: O valor limitado ao intervalo [min_v, max_v].
    """
    return min_v if val < min_v else (max_v if val > max_v else val)
