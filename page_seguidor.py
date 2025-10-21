import tkinter as tk
from tkinter import ttk
import math
import numpy as np
from datetime import datetime, timedelta

from solar_calculator import CalculadoraSolar
from ui_components import EntradaGlobalFrame

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class PaginaGrafico(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        style = ttk.Style(self)
        fonte_titulo = ('TkDefaultFont', 9, 'bold')
        style.configure('TLabelframe.Label', font=fonte_titulo)

        # --- MUDANÇA AQUI: Adiciona "Ângulo Zenital" ao dicionário de saídas ---
        self.saidas = {
            "Declinação Solar": tk.StringVar(),
            "Equação do Tempo": tk.StringVar(),
            "Meridiano Local Padrão": tk.StringVar(),
            "Fator de Correção": tk.StringVar(),
            "Hora Solar Local": tk.StringVar(),
            "Ângulo Horário": tk.StringVar(),
            "Elevação": tk.StringVar(),
            "Zênite": tk.StringVar(),  # <-- NOVA LINHA
            "Azimute": tk.StringVar(),
            "Ângulo Horário Nascer/Pôr": tk.StringVar(),
            "Hora Nascer do Sol": tk.StringVar(),
            "Hora Pôr do Sol": tk.StringVar(),
            "Azimute Nascer do Sol": tk.StringVar(),
            "Azimute Pôr do Sol": tk.StringVar(),
            "Meio-Dia Solar": tk.StringVar()
        }

        self._criar_widgets()
        self.controller.editar_data_var.trace_add(
            "write", self._toggle_edit_state)
        self.controller.editar_hora_var.trace_add(
            "write", self._toggle_edit_state)
        self._toggle_edit_state()

    def _criar_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        data_frame = ttk.Frame(main_frame)
        data_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        # Usa o novo componente reutilizável
        self.frame_entrada = EntradaGlobalFrame(data_frame, self.controller)
        self.frame_entrada.pack(fill=tk.X, pady=(0, 5), anchor='n')

        frame_saida = ttk.LabelFrame(
            data_frame, text="Parâmetros Solares Calculados", padding=5)
        frame_saida.pack(fill=tk.X, expand=True, pady=(5, 0))
        # O loop de criação de widgets já irá adicionar o novo campo automaticamente
        for i, key in enumerate(self.saidas.keys()):
            ttk.Label(frame_saida, text=f"{key}:").grid(
                row=i, column=0, sticky="w", pady=1)
            ttk.Entry(frame_saida, textvariable=self.saidas[key], state="readonly").grid(
                row=i, column=1, sticky="ew", padx=5, pady=1)

        frame_grafico = ttk.LabelFrame(
            main_frame, text="Elevação x Azimute", padding=10)
        frame_grafico.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.figura = Figure(figsize=(5.3, 5.3), dpi=100)
        self.ax_polar = self.figura.add_subplot(111, polar=True)
        self.canvas = FigureCanvasTkAgg(self.figura, master=frame_grafico)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _toggle_edit_state(self, *args):
        # Delega o controle de estado para o componente
        self.frame_entrada._toggle_edit_state()

    def atualizar_interface(self):
        solar = self.controller.solar_object
        if not solar:
            return

        self.saidas["Declinação Solar"].set(f"{solar.declinacao:.4f}°")
        self.saidas["Equação do Tempo"].set(
            f"{solar.equacao_do_tempo:.4f} min")
        self.saidas["Meridiano Local Padrão"].set(
            f"{solar.meridiano_local_padrao:.2f}°")
        self.saidas["Fator de Correção"].set(
            f"{solar.fator_correcao_tempo:.4f} min")
        self.saidas["Hora Solar Local"].set(
            solar.hora_solar_local.strftime('%H:%M:%S'))
        self.saidas["Ângulo Horário"].set(f"{solar.angulo_horario:.4f}°")
        self.saidas["Elevação"].set(f"{solar.elevacao:.4f}°")

        # --- MUDANÇA AQUI: Calcula e define o valor do Ângulo Zenital ---

        self.saidas["Zênite"].set(
            f"{90.0 - solar.elevacao:.4f}°")  # <-- NOVA LINHA

        self.saidas["Azimute"].set(f"{solar.azimute:.4f}°")
        self.saidas["Ângulo Horário Nascer/Pôr"].set(
            f"{solar.angulo_horario_nascer_por:.4f}°")
        self.saidas["Hora Nascer do Sol"].set(
            solar.hora_nascer_sol.strftime('%H:%M:%S'))
        self.saidas["Hora Pôr do Sol"].set(
            solar.hora_por_sol.strftime('%H:%M:%S'))
        self.saidas["Azimute Nascer do Sol"].set(
            f"{solar.azimute_nascer_sol:.4f}°")
        self.saidas["Azimute Pôr do Sol"].set(f"{solar.azimute_por_sol:.4f}°")
        self.saidas["Meio-Dia Solar"].set(
            solar.meio_dia_solar.strftime('%H:%M:%S'))
        self.atualizar_grafico(solar)

    def atualizar_grafico(self, solar_atual: CalculadoraSolar):
        self.ax_polar.clear()
        self.ax_polar.set_theta_zero_location('N')
        self.ax_polar.set_theta_direction(-1)
        self.ax_polar.set_rlim(90, 0)
        self.ax_polar.set_rgrids(np.arange(0, 91, 15))
        self.ax_polar.set_thetagrids(np.arange(0, 360, 15))
        self.ax_polar.tick_params(axis='both', which='major', labelsize=7)

        nascer_sol_dt, por_sol_dt = solar_atual.hora_nascer_sol, solar_atual.hora_por_sol
        intervalo = [nascer_sol_dt + timedelta(minutes=15*i) for i in range(int(
            (por_sol_dt - nascer_sol_dt).total_seconds() / 60 / 15) + 1)] if por_sol_dt > nascer_sol_dt else []

        caminho_azimute, caminho_elevacao = [], []
        for tempo in intervalo:
            temp_solar = CalculadoraSolar(
                tempo, solar_atual.latitude, solar_atual.longitude, solar_atual.utc)
            if temp_solar.elevacao >= 0:
                caminho_azimute.append(math.radians(temp_solar.azimute))
                caminho_elevacao.append(temp_solar.elevacao)

        self.ax_polar.plot(caminho_azimute, caminho_elevacao,
                           label="Trajetória do Sol", color="sandybrown")
        if solar_atual.elevacao >= 0:
            self.ax_polar.plot(math.radians(solar_atual.azimute), solar_atual.elevacao,
                               'o', markersize=8, color="darkorange", label="Posição Atual")

        self.ax_polar.plot([math.radians(solar_atual.azimute_nascer_sol)]*2,
                           [90, 0], color='red', linestyle='--', label='Azimute Nascente')
        self.ax_polar.plot([math.radians(solar_atual.azimute_por_sol)]*2,
                           [90, 0], color='magenta', linestyle='--', label='Azimute Poente')

        try:
            inclinacao = float(
                self.controller.dados_painel["painel_inclinacao"].get())
            azimute = float(
                self.controller.dados_painel["painel_azimute"].get())
            self.ax_polar.plot(math.radians(azimute), 90.0 - inclinacao, 'X',
                               markersize=10, color="black", label="Normal do Painel Fixo")
        except (ValueError, tk.TclError):
            pass

        self.ax_polar.legend(
            loc='upper left', bbox_to_anchor=(1.15, 1.05), fontsize=8)
        self.figura.tight_layout()
        self.canvas.draw()
