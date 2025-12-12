import sys
import os
import datetime
import traceback

# Ensure the root directory is in the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.solar_calculator import CalculadoraSolarPrecisa

try:
    print("Tentando instanciar CalculadoraSolarPrecisa...")
    data_hora = datetime.datetime(2025, 12, 11, 12, 0, 0)
    latitude = -23.55
    longitude = -46.63
    utc = -3
    
    calc = CalculadoraSolarPrecisa(data_hora, latitude, longitude, utc)
    print("Sucesso!")
    print(f"Azimute: {calc.azimute}")
    print(f"Elevação: {calc.elevacao}")
    
except Exception as e:
    print("ERRO ENCONTRADO:")
    traceback.print_exc()
