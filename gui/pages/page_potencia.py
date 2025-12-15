import tkinter as tk
from tkinter import ttk, messagebox
import traceback
import matplotlib.dates as mdates

from core.pv_module_model import PVSystemModel
# <-- Importa os componentes
from gui.components.ui_components import EntradaGlobalFrame, IrradianceFrame

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class PaginaPotencia(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.cached_pv_system = None
        self.cached_stc_results = None
        self.cached_static_inputs = {}
        
        # Armazena os dados do traço (histórico)
        self.trail_data = {'timestamps': [],
                           'horizontal': [], 'ideal': [], 'fixo': []}

        self.editar_datasheet_var = tk.BooleanVar(value=False)
        self.editar_ambientais_var = tk.BooleanVar(value=False)
        self.editar_usina_var = tk.BooleanVar(value=False)

        self.datasheet_widgets = []
        self.ambient_widgets = []
        self.usina_widgets = []

        self.datasheet_vars = {
            'v_oc': tk.StringVar(value="49.8"), 'i_sc': tk.StringVar(value="10.46"),
            'v_mp': tk.StringVar(value="41.7"), 'i_mp': tk.StringVar(value="9.98"),
            'alpha_sc': tk.StringVar(value="0.00523"), 'beta_voc': tk.StringVar(value="-0.15438"),
            'gamma_pmp': tk.StringVar(value="-0.38"), 'cells_in_series': tk.StringVar(value="72"),
            'cell_type': tk.StringVar(value='monoSi')
        }
        self.ambient_vars = {'temp_air': tk.StringVar(
            value="25.0"), 'wind_speed': tk.StringVar(value="1.0")}
        self.array_vars = {'modules_per_string': tk.StringVar(
            value="10"), 'strings_in_parallel': tk.StringVar(value="5")}
        
        self.mpp_outputs = {'ideal_v': tk.StringVar(), 'ideal_i': tk.StringVar(), 'ideal_p': tk.StringVar(), 'ideal_irr': tk.StringVar(),
                            'fixo_v': tk.StringVar(), 'fixo_i': tk.StringVar(), 'fixo_p': tk.StringVar(), 'fixo_irr': tk.StringVar(),
                            'horiz_v': tk.StringVar(), 'horiz_i': tk.StringVar(), 'horiz_p': tk.StringVar(), 'horiz_irr': tk.StringVar()}

        self._criar_widgets()
        self.controller.editar_data_var.trace_add(
            "write", self._toggle_edit_state)
        self.controller.editar_hora_var.trace_add(
            "write", self._toggle_edit_state)
        self.editar_datasheet_var.trace_add(
            "write", self._toggle_datasheet_edit_state)
        self.editar_ambientais_var.trace_add(
            "write", self._toggle_ambient_edit_state)
        self.editar_usina_var.trace_add("write", self._toggle_usina_edit_state)
        self._toggle_datasheet_edit_state()
        self._toggle_ambient_edit_state()
        self._toggle_usina_edit_state()
        self._toggle_edit_state()

    def _toggle_edit_state(self, *args):
        if hasattr(self, 'frame_entrada'):
            self.frame_entrada._toggle_edit_state()

    def _toggle_datasheet_edit_state(self, *args):
        is_editable = self.editar_datasheet_var.get()
        combo_state = "readonly" if is_editable else "disabled"
        text_state = "normal" if is_editable else "disabled"

        for widget in self.datasheet_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.config(state=combo_state)
            else:
                widget.config(state=text_state)

    def _toggle_ambient_edit_state(self, *args):
        state = "normal" if self.editar_ambientais_var.get() else "disabled"
        for widget in self.ambient_widgets:
            widget.config(state=state)

    def _toggle_usina_edit_state(self, *args):
        state = "normal" if self.editar_usina_var.get() else "disabled"
        for widget in self.usina_widgets:
            widget.config(state=state)

    def _on_ambient_slider_move(self, key, value_str):
        value = float(value_str)
        if key == 'temp_air':
            self.ambient_vars[key].set(f"{value:.1f}")
        else:
            self.ambient_vars[key].set(f"{value:.1f}")
        self.controller.atualizar_calculos_e_telas()

    def _handle_ambient_arrow_key(self, variable_key, step, from_val, to_val, event):
        if self.editar_ambientais_var.get():
            current_value = float(self.ambient_vars[variable_key].get())
            new_value = current_value + step
            new_value = max(from_val, min(to_val, new_value))
            self.ambient_vars[variable_key].set(f"{new_value:.1f}")
            self.controller.atualizar_calculos_e_telas()
            
    def _clear_and_restart_trail(self):
        resposta = messagebox.askyesno(
            "Confirmar Reinicialização", "Você tem certeza que deseja reiniciar o gráfico de potência?")
        if resposta:
            self.trail_data = {'timestamps': [],
                               'horizontal': [], 'ideal': [], 'fixo': []}
            self._atualizar_grafico_potencia()

    def _criar_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        left_col = ttk.Frame(main_frame)
        left_col.pack(side="left", fill="y", anchor="n")

        style = ttk.Style()
        style.configure("Compact.TLabel", font=('TkDefaultFont', 6))
        style.configure("Compact.TCheckbutton", font=('TkDefaultFont', 6))

        self.frame_entrada = EntradaGlobalFrame(left_col, self.controller)
        self.frame_entrada.pack(pady=(0, 3), fill="x")

        # --- USA O NOVO COMPONENTE DE IRRADIÂNCIA ---
        self.frame_irradiancia = IrradianceFrame(left_col, self.controller)
        self.frame_irradiancia.pack(pady=3, fill="x")

        ds_frame = ttk.LabelFrame(
            left_col, text="Parâmetros do Módulo (Datasheet STC)", padding=5)
        ds_frame.pack(fill="x", pady=3)

        cb_datasheet = ttk.Checkbutton(ds_frame, text="Editar Parâmetros",
                                       variable=self.editar_datasheet_var,
                                       command=self._toggle_datasheet_edit_state, style="Compact.TCheckbutton")
        cb_datasheet.grid(row=0, column=0, columnspan=2,
                          sticky="w", pady=(0, 3))

        ds_labels = {'v_oc': "Tensão Circuito Aberto (Voc) [V]:", 'i_sc': "Corrente Curto-Circuito (Isc) [A]:", 'v_mp': "Tensão Máx. Potência (Vmp) [V]:", 'i_mp': "Corrente Máx. Potência (Imp) [A]:",
                     'alpha_sc': "Coef. Temp. Isc [A/°C]:", 'beta_voc': "Coef. Temp. Voc [V/°C]:", 'gamma_pmp': "Coef. Temp. Potência (γ) [%/°C]:", 'cells_in_series': "Nº de Células em Série:", 'cell_type': "Tipo de Célula:"}

        cell_types = ['monoSi', 'multiSi', 'polySi',
                      'cis', 'cigs', 'cdte', 'amorphous']

        for i, (key, text) in enumerate(ds_labels.items(), start=1):
            ttk.Label(ds_frame, text=text, style="Compact.TLabel").grid(
                row=i, column=0, sticky="w", pady=1)

            if key == 'cell_type':
                widget = ttk.Combobox(
                    ds_frame, textvariable=self.datasheet_vars[key], values=cell_types, width=12, state="readonly", font=('TkDefaultFont', 6))
                widget.bind("<<ComboboxSelected>>",
                            lambda e: self.controller.atualizar_calculos_e_telas())
            else:
                widget = ttk.Entry(
                    ds_frame, textvariable=self.datasheet_vars[key], width=15, font=('TkDefaultFont', 6))
                widget.bind(
                    "<KeyRelease>", lambda e: self.controller.atualizar_calculos_e_telas())

            widget.grid(row=i, column=1, sticky="e", padx=5, pady=1)
            self.datasheet_widgets.append(widget)

        env_frame = ttk.LabelFrame(
            left_col, text="Condições Ambientais", padding=5)
        env_frame.pack(fill="x", pady=3)
        env_frame.columnconfigure(1, weight=1)

        cb_ambient = ttk.Checkbutton(env_frame, text="Editar Ambiente",
                                     variable=self.editar_ambientais_var, style="Compact.TCheckbutton")
        cb_ambient.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 3))

        ttk.Label(env_frame, text="Temp. Ambiente [°C]:", style="Compact.TLabel").grid(
            row=1, column=0, sticky="w", pady=1)
        temp_slider = ttk.Scale(env_frame, from_=-30, to=50, orient='horizontal',
                                variable=self.ambient_vars['temp_air'], command=lambda val: self._on_ambient_slider_move('temp_air', val), takefocus=True)
        temp_slider.grid(row=1, column=1, sticky="ew", padx=5)
        self.ambient_widgets.append(temp_slider)
        ttk.Label(env_frame, textvariable=self.ambient_vars['temp_air'], width=5, style="Compact.TLabel").grid(
            row=1, column=2, sticky="w")
        temp_slider.bind("<Button-1>", lambda e: temp_slider.focus_set())
        temp_slider.bind(
            "<KeyPress-Left>", lambda e: self._handle_ambient_arrow_key('temp_air', -1, -30, 50, e))
        temp_slider.bind(
            "<KeyPress-Right>", lambda e: self._handle_ambient_arrow_key('temp_air', 1, -30, 50, e))

        ttk.Label(env_frame, text="Veloc. do Vento [m/s]:", style="Compact.TLabel").grid(
            row=2, column=0, sticky="w", pady=1)
        wind_slider = ttk.Scale(env_frame, from_=0, to=50, orient='horizontal',
                                variable=self.ambient_vars['wind_speed'], command=lambda val: self._on_ambient_slider_move('wind_speed', val), takefocus=True)
        wind_slider.grid(row=2, column=1, sticky="ew", padx=5)
        self.ambient_widgets.append(wind_slider)
        ttk.Label(env_frame, textvariable=self.ambient_vars['wind_speed'], width=5, style="Compact.TLabel").grid(
            row=2, column=2, sticky="w")
        wind_slider.bind("<Button-1>", lambda e: wind_slider.focus_set())
        wind_slider.bind(
            "<KeyPress-Left>", lambda e: self._handle_ambient_arrow_key('wind_speed', -1, 0, 50, e))
        wind_slider.bind(
            "<KeyPress-Right>", lambda e: self._handle_ambient_arrow_key('wind_speed', 1, 0, 50, e))

        arr_frame = ttk.LabelFrame(
            left_col, text="Configuração da Usina", padding=5)
        arr_frame.pack(fill="x", pady=3)
        
        cb_usina = ttk.Checkbutton(
            arr_frame, text="Editar Configuração", variable=self.editar_usina_var, style="Compact.TCheckbutton")
        cb_usina.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 3))

        arr_labels = {
            'modules_per_string': "Módulos em Série:", 'strings_in_parallel': "Strings em Paralelo:"}
        for i, (key, text) in enumerate(arr_labels.items(), start=1):
            ttk.Label(arr_frame, text=text, style="Compact.TLabel").grid(
                row=i, column=0, sticky="w", pady=1)
            entry = ttk.Entry(
                arr_frame, textvariable=self.array_vars[key], width=15, font=('TkDefaultFont', 6))
            entry.grid(row=i, column=1, sticky="e", padx=5, pady=1)
            entry.bind("<KeyRelease>",
                       lambda e: self.controller.atualizar_calculos_e_telas())
            self.usina_widgets.append(entry)
            
        # Botão limpar gráfico
        btn_limpar = ttk.Button(
            left_col, text="Reiniciar Gráfico", command=self._clear_and_restart_trail)
        btn_limpar.pack(pady=10, fill="x")

        right_col = ttk.Frame(main_frame)
        right_col.pack(side="left", fill="both", expand=True, padx=10)
        
        graph_frame = ttk.LabelFrame(
            right_col, text="Potência Gerada x Tempo", padding=10)
        graph_frame.pack(fill="both", expand=True, pady=10)
        
        self.fig_power = Figure(dpi=100)
        self.ax_power = self.fig_power.add_subplot(111)
        self.canvas_power = FigureCanvasTkAgg(self.fig_power, master=graph_frame)
        self.canvas_power.get_tk_widget().pack(fill="both", expand=True)

    def atualizar_modelo_pv(self):
        try:
            datasheet = {}
            for key, var in self.datasheet_vars.items():
                if key == 'cell_type':
                    datasheet[key] = var.get()
                else:
                    datasheet[key] = float(var.get())
            datasheet['cells_in_series'] = int(datasheet['cells_in_series'])

            ambient = {k: float(v.get()) for k, v in self.ambient_vars.items()}
            array_config = {k: int(v.get())
                            for k, v in self.array_vars.items()}

            current_static_inputs = {**datasheet, **array_config}
            
            # Reutiliza lógica de cache, embora aqui seja menos crítico para o gráfico histórico
            # pois sempre recalculamos o ponto atual para adicionar ao histórico.
            # No entanto, a criação do objeto PVSystemModel é pesada, então mantemos o cache.

            pv_system = self.cached_pv_system
            
            if current_static_inputs != self.cached_static_inputs:
                pv_system = PVSystemModel(
                    datasheet, array_config['modules_per_string'], array_config['strings_in_parallel'])
                
                self.cached_pv_system = pv_system
                self.cached_static_inputs = current_static_inputs

            if not pv_system:
                return

            irr_ideal = float(
                self.controller.pagina_painel.saidas_irradiancia['POA_ideal_global'].get())
            irr_fixo = float(
                self.controller.pagina_painel.saidas_irradiancia['POA_fixo_global'].get())
            irr_horiz = float(
                self.controller.pagina_painel.saidas_irradiancia['GHI_global'].get())

            scenarios = {'ideal': irr_ideal,
                         'fixo': irr_fixo, 'horiz': irr_horiz}
            
            p_values = {}

            for prefix, irr_value in scenarios.items():
                if irr_value > 0:
                    results = pv_system.calculate_curves_and_mpp(
                        irr_value, ambient['temp_air'], ambient['wind_speed'])
                    _, _, p_mp = results['mpp']
                    p_values[prefix] = p_mp / 1000 # kW
                else:
                    p_values[prefix] = 0.0
            
            # Adiciona ao histórico se houver timestamp disponível no controller (pegamos do solar_object)
            solar = self.controller.solar_object
            if solar:
                self.trail_data['timestamps'].append(solar.data_hora)
                self.trail_data['ideal'].append(p_values['ideal'])
                self.trail_data['fixo'].append(p_values['fixo'])
                self.trail_data['horizontal'].append(p_values['horiz'])
                
            self._atualizar_grafico_potencia()

        except Exception:
            traceback.print_exc()

    def _atualizar_grafico_potencia(self):
        self.ax_power.clear()
        if self.trail_data['timestamps']:
            self.ax_power.plot(
                self.trail_data['timestamps'], self.trail_data['horizontal'], label="Painel Horizontal", color='blue', zorder=2)
            self.ax_power.plot(
                self.trail_data['timestamps'], self.trail_data['ideal'], label="Painel Ideal", color='red', zorder=2)
            self.ax_power.plot(
                self.trail_data['timestamps'], self.trail_data['fixo'], label="Painel Fixo", color='orange', zorder=2)

            last_ts = self.trail_data['timestamps'][-1]
            self.ax_power.plot(
                last_ts, self.trail_data['horizontal'][-1], 'o', color='mediumblue', markersize=8, zorder=4)
            self.ax_power.plot(
                last_ts, self.trail_data['ideal'][-1], 'o', color='darkred', markersize=8, zorder=4)
            self.ax_power.plot(
                last_ts, self.trail_data['fixo'][-1], 'o', color='darkorange', markersize=8, zorder=4)

        self.ax_power.set_title("Potência Gerada (kW)")
        self.ax_power.set_xlabel("Hora")
        self.ax_power.set_ylabel("Potência (kW)")
        if self.trail_data['timestamps']:
            self.ax_power.legend()
        self.ax_power.grid(
            True, which='both', linestyle='--', linewidth=0.5)

        if self.trail_data['timestamps']:
            self.ax_power.xaxis.set_major_formatter(
                mdates.DateFormatter('%H:%M:%S'))
            self.fig_power.autofmt_xdate()

        self.fig_power.tight_layout()
        self.canvas_power.draw()
