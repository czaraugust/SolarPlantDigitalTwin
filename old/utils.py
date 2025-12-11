from datetime import datetime, timedelta, date
import math





def get_hour_now():
    hora = []
    date = datetime.now()
    hora = [int(date.hour), int(date.minute), int(date.second)]
    return hora


def get_date_now():
    data = []
    date = datetime.now()
    data = [int(date.day), int(date.month), int(date.year)]
    return data


def calc_dia_do_ano(dia, mes, ano):
    data_exemplo = date(ano, mes, dia)
    diadoano = data_exemplo.strftime("%j")
    return int(diadoano)


def calc_dia_do_ano_hoje():
    hoje = date.today()
    data_exemplo = date(hoje.year, hoje.month, hoje.day)
    diadoano = hoje.strftime("%j")
    return int(diadoano)


def calc_declinacao(diadoano):
    ang = math.radians(0.98630136986301*(diadoano-81))
    declinacao = 23.45 * math.sin(ang)
    return declinacao


def equacao_do_tempo(diadoano):
    ang = math.radians(0.98630136986301*(diadoano-81))
    EOT = 9.87*math.sin(2*ang) - 7.53*math.cos(ang) - 1.5*math.sin(ang)
    return EOT


def meridiano_local(utc):
    return utc*15


def fator_correcao_tempo(longitude, utc, diadoano):
    correcao = 4*(longitude-meridiano_local(utc))+equacao_do_tempo(diadoano)
    return correcao


def hora_solar_local(longitude, utc, diadoano, hora):
    hora = hora + \
        timedelta(minutes=fator_correcao_tempo(longitude, utc, diadoano))
    return hora


def angulo_horario(longitude, utc, diadoano, hora):
    delta = timedelta(hours=12)
    tempo = hora_solar_local(longitude, utc, diadoano, hora)-delta
    hora = float(tempo.strftime("%I"))
    minuto_decimal = float(tempo.strftime("%M"))/60.00
    angulo = 15.00*(hora + minuto_decimal)
    # if (angulo < 180):
    #     angulo = angulo-180

    return angulo


def elevacao(declinacao, angulo_horario, latitude):
    ang_declinacao = math.radians(declinacao)
    ang_angulo_horario = math.radians(angulo_horario)
    ang_latitude = math.radians(latitude)
    x = math.cos(ang_latitude) * math.cos(ang_declinacao) * \
        math.cos(ang_angulo_horario) + math.sin(ang_latitude) * \
        math.sin(ang_declinacao)
    return math.degrees(math.asin(x))


def azimute(declinacao, angulo_horario, elevacao):
    ang_declinacao = math.radians(declinacao)
    ang_angulo_horario = math.radians(angulo_horario)
    ang_elevacao = math.radians(elevacao)

    x = (math.cos(ang_declinacao) * math.sin(ang_angulo_horario))/math.cos(elevacao)
    y = math.degrees(math.asin(x))
    print(y)
    return y



