import math


def calcular_componentes_irradiancia(ghi: float, albedo: float, dia_do_ano: int,
                                     solar_zenith_deg: float, solar_azimuth_deg: float,
                                     inclinacao_superficie: float, azimute_superficie: float) -> dict:
    """
    Calcula os componentes da irradiância em uma superfície a partir do GHI.
    Usa o modelo de Erbs para decomposição e um modelo isotrópico para transposição.

    Retorna um dicionário com todos os componentes calculados.
    """
    # --- MUDANÇA AQUI ---
    # Se o sol está muito abaixo do horizonte (além do crepúsculo), todos os valores são zero.
    # O limite foi alterado de 90 para 105 graus.
    if solar_zenith_deg >= 105:
        return {'kt': 0, 'kd': 0, 'dhi': 0, 'dni': 0,
                'global': 0, 'direta': 0, 'difusa': 0, 'refletida': 0}

    # --- 1. Calcular Índices de Claridade (kt e kd) ---
    GSC = 1367  # Constante Solar em W/m²

    # Irradiância extraterrestre no topo da atmosfera
    I0_extraterrestre = GSC * \
        (1 + 0.033 * math.cos(math.radians(360 * dia_do_ano / 365)))

    # Irradiância extraterrestre em uma superfície horizontal
    cos_zenith = math.cos(math.radians(solar_zenith_deg))

    # Garante que cos_zenith não seja negativo para o cálculo de I0_horizontal
    cos_zenith_para_i0 = cos_zenith if cos_zenith > 0 else 0
    I0_horizontal = I0_extraterrestre * cos_zenith_para_i0

    # Índice de Claridade (kt)
    kt = ghi / I0_horizontal if I0_horizontal > 0 else 0

    # Modelo Erbs para calcular a Fração Difusa (kd)
    if kt <= 0.22:
        kd = 1.0 - 0.09 * kt
    elif 0.22 < kt <= 0.80:
        kd = 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    else:  # kt > 0.80
        kd = 0.165

    # --- 2. Decompor GHI em DHI (Difusa Horizontal) e DNI (Normal Direta) ---
    dhi = kd * ghi

    # Evita divisão por zero ou valores irrealistas quando o sol está no horizonte
    dni = (ghi - dhi) / cos_zenith if cos_zenith > 0.01 else 0

    # --- 3. Calcular Componentes no Plano de Array (POA) ---
    # Converte ângulos da superfície para radianos
    surface_tilt_rad = math.radians(inclinacao_superficie)
    surface_azimuth_rad = math.radians(azimute_superficie)

    # Ângulo de Incidência (AOI) - ângulo entre o sol e a normal do painel
    cos_aoi = (cos_zenith * math.cos(surface_tilt_rad) +
               math.sin(math.radians(solar_zenith_deg)) * math.sin(surface_tilt_rad) *
               math.cos(math.radians(solar_azimuth_deg) - surface_azimuth_rad))

    # Garante que o ângulo de incidência não seja > 90 graus (sol atrás do painel)
    if cos_aoi < 0:
        cos_aoi = 0

    # Componente Direta (Beam) no painel
    poa_direta = dni * cos_aoi

    # Componente Difusa do céu no painel (Modelo Isotrópico)
    poa_difusa_ceu = dhi * (1 + math.cos(surface_tilt_rad)) / 2

    # Componente Refletida do solo no painel
    poa_refletida_solo = ghi * albedo * (1 - math.cos(surface_tilt_rad)) / 2

    # Irradiância Global no painel
    poa_global = poa_direta + poa_difusa_ceu + poa_refletida_solo

    # Retorna todos os resultados em um dicionário completo
    return {
        'kt': kt,
        'kd': kd,
        'dhi': dhi,
        'dni': dni,
        'global': poa_global,
        'direta': poa_direta,
        'difusa': poa_difusa_ceu,
        'refletida': poa_refletida_solo
    }
