# main.py

import datetime
from solar_calculator import CalculadoraSolar
import time

# --- CONSTANTES DE LOCALIZAÇÃO E CONFIGURAÇÃO ---
UTC = -3  # Fuso horário
LATITUDE = -9.546349305716475
LONGITUDE = -35.78690867092527

# CONFIGURAÇÃO DE TEMPO
# Mude para True para usar a data e hora do sistema (agora)
USAR_DATA_HORA_SISTEMA = False

# Valores customizados (usados se USAR_DATA_HORA_SISTEMA for False)
DIA_CUSTOM = 6
MES_CUSTOM = 1
ANO_CUSTOM = 2025
HORA_CUSTOM = 16
MINUTO_CUSTOM = 0
SEGUNDO_CUSTOM = 0

# --- FUNÇÃO CENTRAL PARA OBTER A DATA/HORA ---


def obter_data_hora(usar_sistema: bool) -> datetime.datetime:
    """Retorna um objeto datetime baseado na configuração."""
    if usar_sistema:
        return datetime.datetime.now()
    else:
        return datetime.datetime(
            ANO_CUSTOM, MES_CUSTOM, DIA_CUSTOM,
            hour=HORA_CUSTOM, minute=MINUTO_CUSTOM, second=SEGUNDO_CUSTOM
        )


# --- EXECUÇÃO PRINCIPAL ---
print("--- Inicializando o Cálculo Solar ---")

# 1. Obtém o objeto datetime base
data_hora_base = obter_data_hora(USAR_DATA_HORA_SISTEMA)

# 2. Cria o objeto CalculadoraSolar, injetando todos os dados
solar = CalculadoraSolar(
    data_hora=data_hora_base,
    latitude=LATITUDE,
    longitude=LONGITUDE,
    utc=UTC
)

print(
    f"Configuração: {'Sistema' if USAR_DATA_HORA_SISTEMA else 'Customizada'}")
print(f"Local: Lat={LATITUDE}, Lon={LONGITUDE}, UTC={UTC}")
print(f"Data/Hora Base: {solar.data_hora.strftime('%d/%m/%Y %H:%M:%S')}")
print(f"Número do Dia do Ano (n): {solar.numero_do_dia}")

print('\n--- Resultados dos Cálculos de Posição Solar (Instante Atual) ---')

# Resultados de Posição
print(f"1. Declinação Solar (delta): {solar.declinacao:.4f} graus")
print(f"2. Equação do Tempo (EOT): {solar.equacao_do_tempo:.4f} minutos")
# <-- Meridiano Local Padrão!
print(f"3. Meridiano Local Padrão: {solar.meridiano_local_padrao:.2f} graus")
print(f"4. Fator de Correção Total: {solar.fator_correcao_tempo:.4f} minutos")
print(
    f"5. Hora Solar Local (HSL): {solar.hora_solar_local.strftime('%H:%M:%S')}")
print(f"6. Ângulo Horário (H) Atual: {solar.angulo_horario:.4f} graus")
print(f"7. Ângulo de Elevação (alpha) Atual: {solar.elevacao:.4f} graus")
print(f"8. Ângulo de Azimute (gama) Atual: {solar.azimute:.4f} graus")

print('\n--- Resultados de Nascer/Pôr do Sol (Para o Dia) ---')

# Resultados de Nascer/Pôr do Sol
print(
    f"9. Ângulo Horário Nascer/Pôr (Hs): {solar.angulo_horario_nascer_por:.4f} graus")
print(
    f"10. Hora do Nascer do Sol: {solar.hora_nascer_sol.strftime('%H:%M:%S')}")
print(f"11. Hora do Pôr do Sol: {solar.hora_por_sol.strftime('%H:%M:%S')}")
print(
    f"12. Azimute do Nascer do Sol: {solar.azimute_nascer_sol:.4f} graus (Leste)")
print(f"13. Azimute do Pôr do Sol: {solar.azimute_por_sol:.4f} graus (Oeste)")
print(
    f"14. Hora do Meio-Dia Solar: {solar.meio_dia_solar.strftime('%H:%M:%S')}")


time.sleep(1)
print('\n----------------------------------')
