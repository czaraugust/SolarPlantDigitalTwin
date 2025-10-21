# solar_calculator.py (CORRIGIDO v2)

from datetime import datetime, timedelta, date
import math


class CalculadoraSolar:
    """
    Realiza todos os cálculos de posição solar (Declinação, Equação do Tempo, 
    Ângulo Horário, Elevação, Azimute e eventos de Nascer/Pôr do Sol) 
    para um determinado ponto no tempo e espaço.
    """

    def __init__(self, data_hora: datetime, latitude: float, longitude: float, utc: int):
        """
        Inicializa o objeto com os parâmetros de tempo e localização.
        """
        self.data_hora = data_hora
        self.latitude = latitude
        self.longitude = longitude
        self.utc = utc

        self.n = self._calc_dia_do_ano(
            data_hora.day, data_hora.month, data_hora.year)

        # Cálculos primários
        self._declinacao = self._calc_declinacao()
        self._equacao_tempo = self._equacao_do_tempo()
        self._meridiano_local = self._meridiano_local()
        self._fator_correcao_tempo = self._fator_correcao_tempo()

        # Cálculos de posição instantânea
        self._hora_solar_local = self._hora_solar_local()
        self._angulo_horario = self._angulo_horario()
        self._elevacao = self._elevacao()
        self._azimute = self._azimute()

        # Cálculos de eventos diários (Nascer/Pôr do Sol)
        self._angulo_horario_nascer_por = self._angulo_horario_nascer_por()
        self._meio_dia_solar = self._calc_meio_dia_solar()
        self._hora_nascer_sol = self._calc_hora_nascer_sol()
        self._hora_por_sol = self._calc_hora_por_sol()

        # O cálculo base do azimute do nascer/pôr do sol
        self._azimute_base_nascer_por = self._calc_azimute_nascer_por_base()
        self._azimute_nascer_sol = self._calc_azimute_nascer_sol()
        self._azimute_por_sol = self._calc_azimute_por_sol()

    # --- Métodos Auxiliares Internos ---

    def _calc_dia_do_ano(self, dia: int, mes: int, ano: int) -> int:
        return int(date(ano, mes, dia).strftime("%j"))

    def _calc_declinacao(self) -> float:
        ang = math.radians(0.98630136986301 * (self.n - 81))
        return 23.45 * math.sin(ang)

    def _equacao_do_tempo(self) -> float:
        ang = math.radians(0.98630136986301 * (self.n - 81))
        EOT = 9.87 * math.sin(2 * ang) - 7.53 * \
            math.cos(ang) - 1.5 * math.sin(ang)
        return EOT

    def _meridiano_local(self) -> float:
        return self.utc * 15.0

    def _fator_correcao_tempo(self) -> float:
        return 4 * (self.longitude - self._meridiano_local) + self._equacao_tempo

    def _hora_solar_local(self) -> datetime:
        return self.data_hora + timedelta(minutes=self._fator_correcao_tempo)

    def _angulo_horario(self) -> float:
        HSL = self._hora_solar_local
        hora_decimal = HSL.hour + HSL.minute / 60.0 + HSL.second / 3600.0
        return 15.0 * (hora_decimal - 12.0)

    def _elevacao(self) -> float:
        ang_declinacao = math.radians(self._declinacao)
        ang_angulo_horario = math.radians(self._angulo_horario)
        ang_latitude = math.radians(self.latitude)
        sin_elevacao = (
            math.cos(ang_latitude) * math.cos(ang_declinacao) * math.cos(ang_angulo_horario) +
            math.sin(ang_latitude) * math.sin(ang_declinacao)
        )
        if sin_elevacao > 1:
            sin_elevacao = 1
        elif sin_elevacao < -1:
            sin_elevacao = -1
        return math.degrees(math.asin(sin_elevacao))

    def _azimute(self) -> float:
        ang_declinacao = math.radians(self._declinacao)
        ang_elevacao = math.radians(self._elevacao)
        ang_latitude = math.radians(self.latitude)
        try:
            cos_azimute_temp = (
                math.sin(ang_declinacao) - math.sin(ang_elevacao) *
                math.sin(ang_latitude)
            ) / (math.cos(ang_elevacao) * math.cos(ang_latitude))
            if cos_azimute_temp > 1:
                cos_azimute_temp = 1
            elif cos_azimute_temp < -1:
                cos_azimute_temp = -1
            azimute_temp = math.degrees(math.acos(cos_azimute_temp))
        except ZeroDivisionError:
            azimute_temp = 0.0
        return azimute_temp if self._angulo_horario < 0 else 360.0 - azimute_temp

    # --- Métodos para Nascer/Pôr do Sol ---

    def _angulo_horario_nascer_por(self) -> float:
        ang_latitude = math.radians(self.latitude)
        ang_declinacao = math.radians(self._declinacao)
        ang_refraction = math.radians(-0.833)
        try:
            cos_hs = (-math.sin(ang_refraction) - math.sin(ang_latitude) * math.sin(ang_declinacao)) / \
                     (math.cos(ang_latitude) * math.cos(ang_declinacao))
            if cos_hs > 1:
                return 0.0
            elif cos_hs < -1:
                return 180.0
            return math.degrees(math.acos(cos_hs))
        except ZeroDivisionError:
            return 90.0

    def _calc_meio_dia_solar(self) -> datetime:
        meio_dia_civil = self.data_hora.replace(
            hour=12, minute=0, second=0, microsecond=0)
        return meio_dia_civil - timedelta(minutes=self._fator_correcao_tempo)

    def _calc_hora_nascer_sol(self) -> datetime:
        tempo_delta = timedelta(hours=self._angulo_horario_nascer_por / 15.0)
        return self._meio_dia_solar - tempo_delta

    def _calc_hora_por_sol(self) -> datetime:
        tempo_delta = timedelta(hours=self._angulo_horario_nascer_por / 15.0)
        return self._meio_dia_solar + tempo_delta

    # --- MÉTODOS DE AZIMUTE NASCER/PÔR DO SOL (CORRIGIDOS) ---

    def _calc_azimute_nascer_por_base(self) -> float:
        """
        Calcula o valor base do azimute para o nascer/pôr do sol usando a fórmula completa.
        """
        ang_latitude = math.radians(self.latitude)
        ang_declinacao = math.radians(self._declinacao)
        # Elevação padrão para nascer/pôr do sol
        ang_refraction = math.radians(-0.833)

        try:
            # Fórmula completa: cos(Az) = (sin(δ) - sin(α)sin(φ)) / (cos(α)cos(φ))
            # Como α é negativo, o sinal se inverte no numerador: sin(δ) + sin(0.833)sin(φ)
            cos_az = (math.sin(ang_declinacao) - math.sin(ang_refraction) * math.sin(ang_latitude)) / \
                     (math.cos(ang_refraction) * math.cos(ang_latitude))

            if cos_az > 1:
                cos_az = 1
            elif cos_az < -1:
                cos_az = -1

            return math.degrees(math.acos(cos_az))
        except ZeroDivisionError:
            # Retorna Leste (90°) em caso de divisão por zero (nos polos)
            return 90.0

    def _calc_azimute_nascer_sol(self) -> float:
        """
        Retorna o Azimute do Nascer do Sol. O valor base já corresponde ao azimute do nascer do sol.
        """
        return self._azimute_base_nascer_por

    def _calc_azimute_por_sol(self) -> float:
        """
        Retorna o Azimute do Pôr do Sol, que é simétrico ao do nascer do sol em relação ao eixo Norte-Sul.
        """
        return 360.0 - self._azimute_base_nascer_por

    # --- Propriedades de Acesso ---

    @property
    def numero_do_dia(self) -> int: return self.n
    @property
    def declinacao(self) -> float: return self._declinacao
    @property
    def equacao_do_tempo(self) -> float: return self._equacao_tempo
    @property
    def meridiano_local_padrao(self) -> float: return self._meridiano_local
    @property
    def fator_correcao_tempo(self) -> float: return self._fator_correcao_tempo
    @property
    def hora_solar_local(self) -> datetime: return self._hora_solar_local
    @property
    def angulo_horario(self) -> float: return self._angulo_horario
    @property
    def elevacao(self) -> float: return self._elevacao
    @property
    def azimute(self) -> float: return self._azimute

    @property
    def angulo_horario_nascer_por(
        self) -> float: return self._angulo_horario_nascer_por

    @property
    def hora_nascer_sol(self) -> datetime: return self._hora_nascer_sol
    @property
    def hora_por_sol(self) -> datetime: return self._hora_por_sol
    @property
    def azimute_nascer_sol(self) -> float: return self._azimute_nascer_sol
    @property
    def azimute_por_sol(self) -> float: return self._azimute_por_sol
    @property
    def meio_dia_solar(self) -> datetime: return self._meio_dia_solar
