import datetime
import time
from utils import *

UTC = -3
LATITUDE = -9.546349305716475
LONGITUDE = -35.78690867092527
DATA_ATUAL = False
HORA_ATUAL = False

dataGlobal = datetime.now()
horaGlobal = datetime.now()

if (DATA_ATUAL):
    DIA = get_date_now()[0]
    MES = get_date_now()[1]
    ANO = get_date_now()[2]
    dataGlobal = datetime.now()


else:
    DIA = 6
    MES = 10
    ANO = 2025
    dataGlobal = datetime(ANO, MES, DIA)


if (HORA_ATUAL):
    HORA = get_hour_now()[0]
    MINUTO = get_hour_now()[1]
    SEGUNDO = get_hour_now()[2]
    horaGlobal = datetime.now()
else:
    HORA = 16
    MINUTO = 0
    SEGUNDO = 0
    horaGlobal = datetime(ANO, MES, DIA, hour=HORA,
                          minute=MINUTO, second=SEGUNDO)

print(dataGlobal, "|", horaGlobal)
DIADOANO = calc_dia_do_ano(DIA, MES, ANO)

print(equacao_do_tempo(DIADOANO))
print(meridiano_local(UTC))
print(fator_correcao_tempo(LONGITUDE, UTC, DIADOANO))
print(calc_declinacao(DIADOANO))
print(DIA, "/", MES, "/", ANO, HORA, ":", MINUTO, ":", SEGUNDO)
print(hora_solar_local(LONGITUDE, UTC, DIADOANO, horaGlobal))
print(angulo_horario(LONGITUDE, UTC, DIADOANO, horaGlobal))
print(elevacao(calc_declinacao(DIADOANO), angulo_horario(LONGITUDE, UTC, DIADOANO, horaGlobal), LATITUDE))
time.sleep(1)
print('----------------------------------')
