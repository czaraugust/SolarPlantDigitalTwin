import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.dates as mdates
import time # Import time for throttling

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pvlib
import numpy as np

# <-- Importa components reutilizáveis
from gui.components.ui_components import EntradaGlobalFrame


class PaginaMeteorologia(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Variáveis de Estado para Meteorologia
        self.meteo_vars = {
            'temp_painel': tk.StringVar(value="45.0"),
            'temp_amb': tk.StringVar(value="25.0"),
            'umidade': tk.StringVar(value="60.0"),
            'vento_vel': tk.StringVar(value="10.0"),
            'vento_dir': tk.StringVar(value="0"),
            'chuva': tk.StringVar(value="0.0")
        }
        
        # Controle de Edição (Individual por slider agora)
        # self.editar_meteo_var = tk.BooleanVar(value=False) # Removido em favor de checkboxes individuais
        self.meteo_checks = {}

        # Histórico de Dados
        self.trail_data = {
            'timestamps': [],
            'temp_amb': [], 'temp_painel': [],
            'umidade': [], 'vento_vel': [],
            'vento_dir': [], 'chuva': []
        }
        self.last_plot_time = 0 # Throttle control

        self._criar_widgets()
        
        # Listeners
        self.controller.editar_data_var.trace_add("write", self._toggle_edit_state)
        self.controller.editar_hora_var.trace_add("write", self._toggle_edit_state)
        
        self._toggle_edit_state()

    def _toggle_edit_state(self, *args):
        if hasattr(self, 'frame_entrada'):
            self.frame_entrada._toggle_edit_state()
            
    def _toggle_slider_state(self, key, slider_widget):
        is_enabled = self.meteo_checks[key].get()
        state = "normal" if is_enabled else "disabled"
        slider_widget.config(state=state)

    def _criar_widgets(self):
        # Layout Principal: Esquerda (Controles) | Direita (Gráficos)
        
        main_layout = ttk.Frame(self) # Container principal
        
        # --- COLUNA ESQUERDA (Inputs) ---
        left_col = ttk.Frame(self, width=250)
        left_col.pack(side="left", fill="y", padx=10, pady=10)
        
        self.frame_entrada = EntradaGlobalFrame(left_col, self.controller)
        self.frame_entrada.pack(fill="x", pady=(0, 10))
        
        # Frame de Controles Meteorológicos
        meteo_frame = ttk.LabelFrame(left_col, text="Condições Meteorológicas", padding=5)
        meteo_frame.pack(fill="x", pady=5)
        
        # cb_edit = ttk.Checkbutton(meteo_frame, text="Editar Meteorologia", 
        #                           variable=self.editar_meteo_var, style="Compact.TCheckbutton")
        # cb_edit.pack(anchor="w", pady=(0, 5))
        
        self.meteo_widgets = []
        
        def create_slider(parent, label, key, from_, to_, resolution=0.1, unit=""):
            f = ttk.Frame(parent)
            f.pack(fill="x", pady=2)
            
            # Header Row: Checkbox + Label
            header = ttk.Frame(f)
            header.pack(fill="x")
            
            self.meteo_checks[key] = tk.BooleanVar(value=False)
            cb = ttk.Checkbutton(header, text=label, variable=self.meteo_checks[key], style="Compact.TCheckbutton")
            cb.pack(side="left")
            
            row = ttk.Frame(f)
            row.pack(fill="x")
            
            # Se for direção do vento, resolution maior
            if key == 'vento_dir':
                resolution = 45

            s = ttk.Scale(row, from_=from_, to=to_, variable=self.meteo_vars[key], 
                          orient='horizontal', command=lambda v: self._on_slider_move(key, v))
            s.configure(state='disabled') # Começa desabilitado
            s.pack(side="left", fill="x", expand=True)
            self.meteo_widgets.append(s)
            
            # Link checkbutton to slider state
            cb.config(command=lambda k=key, w=s: self._toggle_slider_state(k, w))
            
            # Label Value em Negrito
            l = ttk.Label(row, textvariable=self.meteo_vars[key], width=5, font=('TkDefaultFont', 7, 'bold'))
            l.pack(side="right")
            ttk.Label(row, text=unit, font=('TkDefaultFont', 7)).pack(side="right")

        create_slider(meteo_frame, "Temperatura Painel", 'temp_painel', -10, 80, unit="°C")
        create_slider(meteo_frame, "Temperatura Ambiente", 'temp_amb', -10, 80, unit="°C")
        create_slider(meteo_frame, "Umidade Relativa", 'umidade', 0, 100, unit="%")
        create_slider(meteo_frame, "Velocidade do Vento", 'vento_vel', 0, 80, unit="km/h")
        create_slider(meteo_frame, "Chuva Acumulada", 'chuva', 0, 5, resolution=0.25, unit="mm")
        
        # Slider Direção Vento (0 a 315)
        create_slider(meteo_frame, "Direção do Vento", 'vento_dir', 0, 315, unit="°")
        
        btn_reset = ttk.Button(left_col, text="Reiniciar Gráficos", command=self._reset_graphs)
        btn_reset.pack(fill="x", pady=10)

        # --- ÁREA DOS GRÁFICOS ---
        graphs_area = ttk.Frame(self)
        graphs_area.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        # ... (restante do layout gráfico)
        graphs_area.columnconfigure(0, weight=2)
        graphs_area.columnconfigure(1, weight=1)
        graphs_area.rowconfigure(0, weight=1)
        
        # GRÁFICO 1: Temperaturas (Esquerda)
        frame_temp = ttk.LabelFrame(graphs_area, text="Temperatura Painel x Ambiente (°C)")
        frame_temp.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        
        self.fig_temp = Figure(dpi=100)
        self.ax_temp = self.fig_temp.add_subplot(111)
        self.canvas_temp = FigureCanvasTkAgg(self.fig_temp, master=frame_temp)
        self.canvas_temp.get_tk_widget().pack(fill="both", expand=True)
        
        # GRÁFICOS DIREITA (Grid 2x2)
        right_graphs = ttk.Frame(graphs_area)
        right_graphs.grid(row=0, column=1, sticky="nsew")
        right_graphs.columnconfigure(0, weight=1)
        right_graphs.columnconfigure(1, weight=1)
        right_graphs.rowconfigure(0, weight=1)
        right_graphs.rowconfigure(1, weight=1)
        
        # 2) Umidade
        frame_hum = ttk.LabelFrame(right_graphs, text="Umidade (%)")
        frame_hum.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.fig_hum = Figure(dpi=80) 
        self.ax_hum = self.fig_hum.add_subplot(111)
        self.canvas_hum = FigureCanvasTkAgg(self.fig_hum, master=frame_hum)
        self.canvas_hum.get_tk_widget().pack(fill="both", expand=True)

        # 3) Vento Velocidade
        frame_wind_spd = ttk.LabelFrame(right_graphs, text="Vel. Vento (km/h)")
        frame_wind_spd.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)
        self.fig_wind_spd = Figure(dpi=80)
        self.ax_wind_spd = self.fig_wind_spd.add_subplot(111)
        self.canvas_wind_spd = FigureCanvasTkAgg(self.fig_wind_spd, master=frame_wind_spd)
        self.canvas_wind_spd.get_tk_widget().pack(fill="both", expand=True)

        # 4) Chuva
        frame_rain = ttk.LabelFrame(right_graphs, text="Chuva Acumulada (mm)")
        frame_rain.grid(row=1, column=0, sticky="nsew", padx=2, pady=2)
        self.fig_rain = Figure(dpi=80)
        self.ax_rain = self.fig_rain.add_subplot(111)
        self.canvas_rain = FigureCanvasTkAgg(self.fig_rain, master=frame_rain)
        self.canvas_rain.get_tk_widget().pack(fill="both", expand=True)

        # 5) Vento Direção (Polar)
        frame_wind_dir = ttk.LabelFrame(right_graphs, text="Direção do Vento (º)")
        frame_wind_dir.grid(row=1, column=1, sticky="nsew", padx=2, pady=2)
        self.fig_wind_dir = Figure(dpi=80)
        self.ax_wind_dir = self.fig_wind_dir.add_subplot(111)
        self.canvas_wind_dir = FigureCanvasTkAgg(self.fig_wind_dir, master=frame_wind_dir)
        self.canvas_wind_dir.get_tk_widget().pack(fill="both", expand=True)

    def _on_slider_move(self, key, value):
        val_float = float(value)
        
        if key == 'vento_dir':
            # Snap logic: 0, 45, 90, 135, 180, 225, 270, 315
            steps = [0, 45, 90, 135, 180, 225, 270, 315]
            # Encontra o mais próximo
            closest = min(steps, key=lambda x: abs(x - val_float))
            self.meteo_vars[key].set(f"{closest}") 
        else:
            self.meteo_vars[key].set(f"{val_float:.1f}")

    def _reset_graphs(self):
        self.reset_history(confirm=True)

    def reset_history(self, confirm=True):
        if confirm:
            if not messagebox.askyesno("Reiniciar Gráficos", "Tem certeza que deseja limpar todo o histórico dos gráficos?"):
                return
        
        
        self.trail_data = {k: [] for k in self.trail_data}
        self._plot_graphs()

    def atualizar_meteorologia(self):
        try:
            # 1. Obter Timestamp
            solar = self.controller.solar_object
            if not solar:
                return
            timestamp = solar.data_hora
            
            # 2. Obter valores dos inputs
            
            t_amb = float(self.meteo_vars['temp_amb'].get())
            umid = float(self.meteo_vars['umidade'].get())
            v_vel = float(self.meteo_vars['vento_vel'].get()) # km/h
            v_dir = float(self.meteo_vars['vento_dir'].get())
            chuva = float(self.meteo_vars['chuva'].get())
            # Pega Temp Painel Manual
            temp_painel = float(self.meteo_vars['temp_painel'].get())
            
            # --- REMOVIDO CÁLCULO AUTOMÁTICO DE TEMP PAINEL ---
            # O usuário agora controla isso manualmente
            
            # 4. Atualizar Histórico
            self.trail_data['timestamps'].append(timestamp)
            self.trail_data['temp_amb'].append(t_amb)
            self.trail_data['temp_painel'].append(temp_painel)
            self.trail_data['umidade'].append(umid)
            self.trail_data['vento_vel'].append(v_vel)
            self.trail_data['vento_dir'].append(v_dir)
            self.trail_data['chuva'].append(chuva)
            
            # Limitar histórico para não explodir memória (ex: 1000 pontos)
            if len(self.trail_data['timestamps']) > 3600: # 1h se for 1s
                for k in self.trail_data:
                    self.trail_data[k].pop(0)

            # 5. Plotar
            self._plot_graphs()
            
        except Exception as e:
            # print(e)
            pass

    def _plot_graphs(self):
        # PERFORMANCE: Só desenha se a aba estiver visível
        if not self.winfo_viewable():
            return

        current_time = time.time()
        if current_time - self.last_plot_time < 0.2: # Limit to 5 FPS
            return
        self.last_plot_time = current_time

        timestamps = self.trail_data['timestamps']
        # Remove early return to allow clearing graphs
            
        # FORMATADOR DE DATA
        fmt = mdates.DateFormatter('%H:%M:%S')

        # 1. Temperaturas
        self.ax_temp.clear()
        if timestamps:
            self.ax_temp.plot(timestamps, self.trail_data['temp_painel'], label='Painel', color='red')
            self.ax_temp.plot(timestamps, self.trail_data['temp_amb'], label='Ambiente', color='blue')
            self.ax_temp.legend(loc='upper left')
            self.ax_temp.xaxis.set_major_formatter(fmt)
            self.fig_temp.autofmt_xdate()
        self.ax_temp.grid(True, linestyle='--', alpha=0.7)
        self.ax_temp.set_title("Temperatura (°C)")
        self.canvas_temp.draw()

        # 2. Umidade
        self.ax_hum.clear()
        if timestamps:
            self.ax_hum.plot(timestamps, self.trail_data['umidade'], color='blue')
            self.ax_hum.xaxis.set_major_formatter(fmt)
        self.ax_hum.set_ylim(0, 100)
        self.ax_hum.grid(True)
        # self.ax_hum.set_title("Umidade (%)") # Title no frame já diz
        self.ax_hum.tick_params(axis='x', rotation=30, labelsize=8)
        self.canvas_hum.draw()

        # 3. Vento Vel
        self.ax_wind_spd.clear()
        if timestamps:
            self.ax_wind_spd.plot(timestamps, self.trail_data['vento_vel'], color='green')
            self.ax_wind_spd.xaxis.set_major_formatter(fmt)
        self.ax_wind_spd.grid(True)
        self.ax_wind_spd.tick_params(axis='x', rotation=30, labelsize=8)
        self.canvas_wind_spd.draw()

        # 4. Chuva
        self.ax_rain.clear()
        # Chuva geralmente é acumulada ou barra. Vamos de linha preenchida
        if timestamps:
            self.ax_rain.fill_between(timestamps, self.trail_data['chuva'], color='blue', alpha=0.3)
            self.ax_rain.plot(timestamps, self.trail_data['chuva'], color='blue')
            self.ax_rain.xaxis.set_major_formatter(fmt)
        self.ax_rain.grid(True)
        self.ax_rain.tick_params(axis='x', rotation=30, labelsize=8)
        self.canvas_rain.draw()

        # 5. Vento Dir (Linear)
        self.ax_wind_dir.clear()
        if timestamps:
            self.ax_wind_dir.plot(timestamps, self.trail_data['vento_dir'], color='purple')
            self.ax_wind_dir.xaxis.set_major_formatter(fmt)
            
            # Atual
            if self.trail_data['vento_dir']:
                curr_dir_deg = self.trail_data['vento_dir'][-1]
                self.ax_wind_dir.set_title(f"Direção: {int(curr_dir_deg)}°", fontsize=10)

        self.ax_wind_dir.grid(True)
        self.ax_wind_dir.tick_params(axis='x', rotation=30, labelsize=8)
        
        # Configurar eixo Y para 0-360 graus com cardeais
        self.ax_wind_dir.set_ylim(0, 360)
        self.ax_wind_dir.set_yticks([0, 45, 90, 135, 180, 225, 270, 315])
        self.ax_wind_dir.set_yticklabels(['0', '45', '90', '135', '180', '225', '270', '315'], fontsize=8)
        
        self.canvas_wind_dir.draw()
