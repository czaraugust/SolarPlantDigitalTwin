"""
Máquina de Estados do Inversor Solar.

Modela o comportamento de partida/parada do inversor:
- DESLIGADO: Espera tensão DC suficiente e tempo de estabilização.
- LIGADO: Gera potência AC. Desliga imediatamente se condições falharem.

Constantes internas:
- P_STANDBY = 26 W (consumo interno / tare loss)
- TEMPO_ATRASO = 19 minutos (tempo de sincronismo normativo)
"""


class InverterStateMachine:
    # Constantes internas do modelo
    P_STANDBY = 26.0       # W - consumo interno
    TEMPO_ATRASO = 19      # minutos - delay timer

    DESLIGADO = "DESLIGADO"
    LIGADO = "LIGADO"

    def __init__(self, v_partida=120.0):
        self.v_partida = v_partida
        self.estado = self.DESLIGADO
        self.contador_minutos = 0

    def step(self, v_s1, v_s2, p_dc):
        """
        Executa um passo da máquina de estados (1 chamada = 1 minuto).

        Args:
            v_s1: Tensão da String 1 (V)
            v_s2: Tensão da String 2 (V)
            p_dc: Potência DC total (W)

        Returns:
            str: Estado atual ('LIGADO' ou 'DESLIGADO')
        """
        # Condições físicas
        cond_ligar = (v_s1 >= self.v_partida or v_s2 >= self.v_partida) \
                     and (p_dc > self.P_STANDBY)
        cond_desligar = (v_s1 < self.v_partida and v_s2 < self.v_partida) \
                        or (p_dc <= self.P_STANDBY)

        if self.estado == self.DESLIGADO:
            if cond_ligar:
                self.contador_minutos += 1
                if self.contador_minutos >= self.TEMPO_ATRASO:
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

        return self.estado

    def reset(self):
        """Reinicia para o estado DESLIGADO."""
        self.estado = self.DESLIGADO
        self.contador_minutos = 0
