import tkinter as tk
from tkinter import ttk, messagebox
import traceback
import matplotlib.dates as mdates
import math

from core.pv_module_model import PVSystemModel
# <-- Importa os componentes
from gui.components.ui_components import EntradaGlobalFrame, IrradianceFrame

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class PaginaPrevisao(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.cached_pv_system = None
        self.cached_stc_results = None
        self.cached_static_inputs = {}
        
        # Armazena os dados do traço (histórico)
        self.trail_data = {'timestamps': [],
                           'sensor': [], 'faiman': [], 'ross': [], 'sapm': [], 'real': []}
        
        # Dados para calculo de erros acumulados
        self.error_stats = {
            'sensor': {
                'sum_sq_err': 0.0, 'sum_abs_err': 0.0,
                'sum_abs_perc': 0.0, 'sum_real': 0.0, 'count': 0, 'count_mape': 0
            },
            'faiman': {
                'sum_sq_err': 0.0, 'sum_abs_err': 0.0,
                'sum_abs_perc': 0.0, 'sum_real': 0.0, 'count': 0, 'count_mape': 0
            },
            'ross': {
                'sum_sq_err': 0.0, 'sum_abs_err': 0.0,
                'sum_abs_perc': 0.0, 'sum_real': 0.0, 'count': 0, 'count_mape': 0
            },
            'sapm': {
                'sum_sq_err': 0.0, 'sum_abs_err': 0.0,
                'sum_abs_perc': 0.0, 'sum_real': 0.0, 'count': 0, 'count_mape': 0
            },
            'real': {
                'sum_sq_err': 0.0, 'sum_abs_err': 0.0,
                'sum_abs_perc': 0.0, 'sum_real': 0.0, 'count': 0, 'count_mape': 0
            } 
        }

        self.editar_datasheet_var = tk.BooleanVar(value=False)
        self.editar_usina_var = tk.BooleanVar(value=False)

        self.datasheet_widgets = []
        self.ambient_widgets = []
        self.usina_widgets = []

        self.datasheet_vars = self.controller.dados_datasheet
        self.ambient_vars = self.controller.dados_ambientais
        self.array_vars = self.controller.dados_usina
        
        # Outputs da tabela de comparação
        self.mpp_outputs = {
            'sensor_p': tk.StringVar(), 
            'sensor_mse': tk.StringVar(), 'sensor_mae': tk.StringVar(), 
            'sensor_rmse': tk.StringVar(), 'sensor_mape': tk.StringVar(),
            'sensor_wape': tk.StringVar(),
            
            'faiman_p': tk.StringVar(), 
            'faiman_mse': tk.StringVar(), 'faiman_mae': tk.StringVar(), 
            'faiman_rmse': tk.StringVar(), 'faiman_mape': tk.StringVar(),
            'faiman_wape': tk.StringVar(),
            
            'ross_p': tk.StringVar(), 
            'ross_mse': tk.StringVar(), 'ross_mae': tk.StringVar(), 
            'ross_rmse': tk.StringVar(), 'ross_mape': tk.StringVar(),
            'ross_wape': tk.StringVar(),

            'sapm_p': tk.StringVar(), 
            'sapm_mse': tk.StringVar(), 'sapm_mae': tk.StringVar(), 
            'sapm_rmse': tk.StringVar(), 'sapm_mape': tk.StringVar(),
            'sapm_wape': tk.StringVar(),
            
            'real_p': tk.StringVar(), 
            'real_mse': tk.StringVar(), 'real_mae': tk.StringVar(), 
            'real_rmse': tk.StringVar(), 'real_mape': tk.StringVar(),
            'real_wape': tk.StringVar()
        }

        self._criar_widgets()
        self.controller.editar_data_var.trace_add(
            "write", self._toggle_edit_state)
        self.controller.editar_hora_var.trace_add(
            "write", self._toggle_edit_state)
        self.editar_datasheet_var.trace_add(
            "write", self._toggle_datasheet_edit_state)
        self.controller.editar_ambientais_var.trace_add(
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
        state = "normal" if self.controller.editar_ambientais_var.get() else "disabled"
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
        if self.controller.editar_ambientais_var.get():
            current_value = float(self.ambient_vars[variable_key].get())
            new_value = current_value + step
            new_value = max(from_val, min(to_val, new_value))
            self.ambient_vars[variable_key].set(f"{new_value:.1f}")
            self.controller.atualizar_calculos_e_telas()
            
    def _clear_and_restart_trail(self):
        self.reset_history(confirm=True)

    def reset_history(self, confirm=True):
        if confirm:
            if not messagebox.askyesno("Confirmar Reinicialização", "Você tem certeza que deseja reiniciar o gráfico de previsão e zerar todos os erros (MSE, MAE, etc)?"):
                return

        self.trail_data = {'timestamps': [],
                           'sensor': [], 'faiman': [], 'ross': [], 'sapm': [], 'real': []}
        
        # Reset de todas as estatísticas de erro
        for k in self.error_stats:
            self.error_stats[k] = {
                'sum_sq_err': 0.0, 'sum_abs_err': 0.0,
                'sum_abs_perc': 0.0, 'sum_real': 0.0, 'count': 0, 'count_mape': 0
            }
        
        self._atualizar_grafico_previsao()

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
            left_col, text="Condições Ambientais (Entrada Manual / Fixo)", padding=5)
        env_frame.pack(fill="x", pady=3)
        env_frame.columnconfigure(1, weight=1)

        cb_ambient = ttk.Checkbutton(env_frame, text="Editar Ambiente (Modelo Fixo)",
                                     variable=self.controller.editar_ambientais_var, style="Compact.TCheckbutton")
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
            left_col, text="Reiniciar Previsão", command=self._clear_and_restart_trail)
        btn_limpar.pack(pady=10, fill="x")

        right_col = ttk.Frame(main_frame)
        right_col.pack(side="left", fill="both", expand=True, padx=10)
        
        graph_frame = ttk.LabelFrame(
            right_col, text="Potência Gerada x Tempo (Comparativo)", padding=10)
        graph_frame.pack(fill="both", expand=True, pady=10)
        
        self.fig_power = Figure(dpi=100)
        self.ax_power = self.fig_power.add_subplot(111)
        self.canvas_power = FigureCanvasTkAgg(self.fig_power, master=graph_frame)
        self.canvas_power.get_tk_widget().pack(fill="both", expand=True)

        mpp_frame = ttk.LabelFrame(
            right_col, text="Comparação Modelo Manual vs Real vs Meteo", padding=10)
        mpp_frame.pack(fill="x", pady=10)

        # Atualizando Headers para novas colunas
        headers = [
            "Cenário", "Potência (W)", "MSE (W²)", "MAE (W)", "RMSE (W)", "MAPE (%)", "WAPE (%)"]
        
        for col, text in enumerate(headers):
            ttk.Label(mpp_frame, text=text, font=('TkDefaultFont', 6, 'bold')).grid(
                row=0, column=col, padx=4, sticky="w")

        # Ordem solicitada: Real, Sensor, Faiman, Ross, SAPM
        rows = [("REAL", "real"), ("MODELO @ SENSOR", "sensor"), ("MODELO @ FAIMAN", "faiman"), 
                ("MODELO @ ROSS", "ross"), ("MODELO @ SAPM", "sapm")]
        
        for row, (label, prefix) in enumerate(rows, start=1):
            lbl_style = "TkDefaultFont" if prefix != "real" else ("TkDefaultFont", 9, "bold")
            ttk.Label(mpp_frame, text=label, font=lbl_style).grid(
                row=row, column=0, sticky="w")
            
            # Potencia
            ttk.Entry(mpp_frame, textvariable=self.mpp_outputs[f"{prefix}_p"], state="readonly", width=10).grid(
                    row=row, column=1, padx=2)
            
            # MSE
            ttk.Entry(mpp_frame, textvariable=self.mpp_outputs[f"{prefix}_mse"], state="readonly", width=10).grid(
                    row=row, column=2, padx=2)
            
            # MAE
            ttk.Entry(mpp_frame, textvariable=self.mpp_outputs[f"{prefix}_mae"], state="readonly", width=10).grid(
                    row=row, column=3, padx=2)
            
            # RMSE
            ttk.Entry(mpp_frame, textvariable=self.mpp_outputs[f"{prefix}_rmse"], state="readonly", width=10).grid(
                    row=row, column=4, padx=2)

            # MAPE
            ttk.Entry(mpp_frame, textvariable=self.mpp_outputs[f"{prefix}_mape"], state="readonly", width=10).grid(
                    row=row, column=5, padx=2)
            
            # WAPE
            ttk.Entry(mpp_frame, textvariable=self.mpp_outputs[f"{prefix}_wape"], state="readonly", width=10).grid(
                    row=row, column=6, padx=2)

    def atualizar_previsao(self):
        try:
            datasheet = {}
            for key, var in self.datasheet_vars.items():
                if key == 'cell_type':
                    datasheet[key] = var.get()
                else:
                    datasheet[key] = float(var.get())
            datasheet['cells_in_series'] = int(datasheet['cells_in_series'])

            # Config do Array
            array_config = {k: int(v.get()) for k, v in self.array_vars.items()}
            current_static_inputs = {**datasheet, **array_config}
            
            # Cache do Sistema PV
            pv_system = self.cached_pv_system
            if current_static_inputs != self.cached_static_inputs:
                pv_system = PVSystemModel(
                    datasheet, array_config['modules_per_string'], array_config['strings_in_parallel'])
                self.cached_pv_system = pv_system
                self.cached_static_inputs = current_static_inputs

            if not pv_system:
                return

            # Dados Ambientais 1: Manual/Fixo (Sliders) -> Agora SENSOR
            temp_painel_sensor = 0.0
            
            # Dados Ambientais 2: Meteo Real (CSV/Aba Metereologia) -> Agora FAIMAN
            ambient_meteo = {
                'temp_air': 25.0, 'wind_speed': 1.0 # Default
            }

            if hasattr(self.controller, 'pagina_meteorologia'):
                pm = self.controller.pagina_meteorologia
                if hasattr(pm, 'meteo_vars'):
                     # Pega valores da aba meteorologia (que podem vir do CSV)
                     
                     # 1. FAIMAN Inputs (Ar + Vento)
                     t_amb_str = pm.meteo_vars['temp_amb'].get()
                     v_vel_str = pm.meteo_vars['vento_vel'].get() # km/h
                     
                     if t_amb_str: ambient_meteo['temp_air'] = float(t_amb_str)
                     if v_vel_str: ambient_meteo['wind_speed'] = float(v_vel_str) / 3.6 # km/h -> m/s
                     
                     # 2. SENSOR Inputs (Painel Real)
                     t_painel_str = pm.meteo_vars['temp_painel'].get()
                     if t_painel_str: temp_painel_sensor = float(t_painel_str)

            irr_fixo = float(
                self.controller.pagina_painel.saidas_irradiancia['POA_fixo_global'].get())

            # Cenários de Cálculo
            # 1. Sensor (Usa Temp Painel Real - Ignora Faiman)
            # 2. Faiman (Usa Temp Amb + Vento - Calcula Faiman)
            # 3. Ross (Usa Temp Amb + POA)
            # 4. SAPM (Usa Temp Sensor + POA)
            scenarios = {}
            
            # --- CÁLCULO SENSOR (FORCED TEMP) ---
            if irr_fixo > 0:
                res_sensor = pv_system.calculate_curves_and_mpp(
                    irr_fixo, 25.0, 1.0, forced_cell_temp=temp_painel_sensor) # Temp/Wind ignored
                scenarios['sensor'] = res_sensor['mpp'][2] # Power
            else:
                scenarios['sensor'] = 0.0

            # --- CÁLCULO FAIMAN (STANDARD) ---
            if irr_fixo > 0:
                res_faiman = pv_system.calculate_curves_and_mpp(
                    irr_fixo, ambient_meteo['temp_air'], ambient_meteo['wind_speed']) 
                scenarios['faiman'] = res_faiman['mpp'][2] # Power
            else:
                scenarios['faiman'] = 0.0

            # --- CÁLCULO ROSS (T_cell = T_amb + (POA/1000)*45) ---
            if irr_fixo > 0:
                # Ross Coeff DeltaT = 45 -> k = 0.045 C/(W/m2) se normalizado por 1000
                delta_t_ross = (irr_fixo / 1000.0) * 45.0
                temp_cell_ross = ambient_meteo['temp_air'] + delta_t_ross
                
                res_ross = pv_system.calculate_curves_and_mpp(
                    irr_fixo, 25.0, 1.0, forced_cell_temp=temp_cell_ross)
                scenarios['ross'] = res_ross['mpp'][2]
            else:
                scenarios['ross'] = 0.0

            # --- CÁLCULO SAPM Module (T_cell = T_module + (POA/1000)*1) ---
            if irr_fixo > 0:
                # DeltaT = 1
                delta_t_sapm = (irr_fixo / 1000.0) * 1.0
                temp_cell_sapm = temp_painel_sensor + delta_t_sapm
                
                res_sapm = pv_system.calculate_curves_and_mpp(
                    irr_fixo, 25.0, 1.0, forced_cell_temp=temp_cell_sapm)
                scenarios['sapm'] = res_sapm['mpp'][2]
            else:
                scenarios['sapm'] = 0.0


            # --- DADOS REAIS (REFERÊNCIA) ---
            v_real = float(self.controller.dados_painel['tensao_real'].get() or 0)
            i_real = float(self.controller.dados_painel['corrente_real'].get() or 0)
            p_real = (v_real * i_real) # W
            
            self.mpp_outputs['real_p'].set(f"{p_real:.2f}")
            self.mpp_outputs['real_mse'].set("REF")
            self.mpp_outputs['real_mae'].set("REF")
            self.mpp_outputs['real_mape'].set("REF")
            self.mpp_outputs['real_rmse'].set("REF")
            self.mpp_outputs['real_wape'].set("REF")

            # Update UI & Stats
            for prefix in ['sensor', 'faiman', 'ross', 'sapm']:
                p_w = scenarios[prefix]
                self.mpp_outputs[f"{prefix}_p"].set(f"{p_w:.2f}")

                # --- CÁLCULO DE ERROS ---
                diff = p_w - p_real
                abs_diff = abs(diff)
                sq_diff = diff ** 2
                
                # Atualiza somatórios
                self.error_stats[prefix]['sum_sq_err'] += sq_diff
                self.error_stats[prefix]['sum_abs_err'] += abs_diff
                self.error_stats[prefix]['sum_real'] += p_real
                self.error_stats[prefix]['count'] += 1
                
                count = self.error_stats[prefix]['count']
                
                # MSE
                mse = self.error_stats[prefix]['sum_sq_err'] / count if count > 0 else 0
                self.mpp_outputs[f"{prefix}_mse"].set(f"{mse:.2f}")
                
                # RMSE
                rmse = math.sqrt(mse)
                self.mpp_outputs[f"{prefix}_rmse"].set(f"{rmse:.2f}")
                
                # MAE
                mae = self.error_stats[prefix]['sum_abs_err'] / count if count > 0 else 0
                self.mpp_outputs[f"{prefix}_mae"].set(f"{mae:.2f}")
                
                # MAPE (Evitar divisão por zero)
                if p_real != 0:
                    abs_perc = (abs_diff / p_real)
                    self.error_stats[prefix]['sum_abs_perc'] += abs_perc
                    self.error_stats[prefix]['count_mape'] += 1
                
                count_mape = self.error_stats[prefix]['count_mape']
                mape = (self.error_stats[prefix]['sum_abs_perc'] / count_mape * 100) if count_mape > 0 else 0.0
                self.mpp_outputs[f"{prefix}_mape"].set(f"{mape:.2f}%")

                # WAPE
                sum_real = self.error_stats[prefix]['sum_real']
                sum_abs_err = self.error_stats[prefix]['sum_abs_err']
                wape = (sum_abs_err / sum_real * 100) if sum_real > 0 else 0.0
                self.mpp_outputs[f"{prefix}_wape"].set(f"{wape:.2f}%")
            
            
            # Adiciona ao histórico se houver timestamp disponível no controller
            # Adiciona ao histórico (Evita duplicatas de tempo e limita tamanho)
            solar = self.controller.solar_object
            if solar:
                current_time = solar.data_hora
                
                # Só adiciona se for o primeiro ponto ou se o tempo avançou
                if not self.trail_data['timestamps'] or current_time > self.trail_data['timestamps'][-1]:
                    self.trail_data['timestamps'].append(current_time)
                    self.trail_data['sensor'].append(scenarios['sensor'])
                    self.trail_data['faiman'].append(scenarios['faiman'])
                    self.trail_data['ross'].append(scenarios['ross'])
                    self.trail_data['sapm'].append(scenarios['sapm'])
                    self.trail_data['real'].append(p_real)
                    
                    # LOG DE TEMPERATURAS PARA DEBUG (Solicitado pelo usuário)
                    # Recalcula Faiman temp só para print (modelo já calculou internamente)
                    try:
                        import pvlib
                        t_faiman = pvlib.temperature.faiman(irr_fixo, ambient_meteo['temp_air'], ambient_meteo['wind_speed'])
                        print(f"[TEMP CHECK] Sensor: {temp_painel_sensor:.1f}°C | Faiman: {t_faiman:.1f}°C | Ross: {temp_cell_ross:.1f}°C | SAPM: {temp_cell_sapm:.1f}°C")
                    except:
                        pass

                    # Limita o tamanho do histórico (ex: 3600 pontos = 1 hora a 1s)
                    if len(self.trail_data['timestamps']) > 3600:
                        self.trail_data['timestamps'].pop(0)
                        self.trail_data['sensor'].pop(0)
                        self.trail_data['faiman'].pop(0)
                        self.trail_data['ross'].pop(0)
                        self.trail_data['sapm'].pop(0)
                        self.trail_data['real'].pop(0)
                
            self._atualizar_grafico_previsao()

        except Exception:
            traceback.print_exc()

    def _atualizar_grafico_previsao(self):
        # PERFORMANCE: Só desenha se a aba estiver visível
        if not self.winfo_viewable():
            return
            
        self.ax_power.clear()
        if self.trail_data['timestamps']:
            ts = self.trail_data['timestamps']
            
            # Modelo Sensor (Blue)
            self.ax_power.plot(ts, self.trail_data['sensor'], label="MODELO @ SENSOR", color='blue', zorder=2)
            
            # Modelo Faiman (Green)
            self.ax_power.plot(ts, self.trail_data['faiman'], label="MODELO @ FAIMAN", color='green', linestyle='--', zorder=3)

            # Modelo Ross (Orange)
            self.ax_power.plot(ts, self.trail_data['ross'], label="MODELO @ ROSS", color='darkorange', linestyle='-.', zorder=3)

            # Modelo SAPM (Purple)
            self.ax_power.plot(ts, self.trail_data['sapm'], label="MODELO @ SAPM", color='purple', linestyle=':', zorder=3)
            
            # Real (Black)
            self.ax_power.plot(ts, self.trail_data['real'], label="REAL", color='black', alpha=0.8, linewidth=2, zorder=1)

            # Dots no final
            last_ts = ts[-1]
            self.ax_power.plot(last_ts, self.trail_data['sensor'][-1], 'o', color='mediumblue', markersize=6)
            self.ax_power.plot(last_ts, self.trail_data['faiman'][-1], 'o', color='darkgreen', markersize=6)
            self.ax_power.plot(last_ts, self.trail_data['ross'][-1], 'o', color='darkorange', markersize=6)
            self.ax_power.plot(last_ts, self.trail_data['sapm'][-1], 'o', color='purple', markersize=6)
            self.ax_power.plot(last_ts, self.trail_data['real'][-1], 'o', color='black', markersize=6)

        self.ax_power.set_title("Comparação: Modelos Térmicos (Real vs Faiman vs Ross vs SAPM)")
        self.ax_power.set_xlabel("Hora")
        self.ax_power.set_ylabel("Potência (W)")
        if self.trail_data['timestamps']:
            self.ax_power.legend()
        self.ax_power.grid(True, which='both', linestyle='--', linewidth=0.5)

        if self.trail_data['timestamps']:
            self.ax_power.xaxis.set_major_formatter(
                mdates.DateFormatter('%H:%M:%S'))
            self.fig_power.autofmt_xdate()

        self.fig_power.tight_layout()
        self.canvas_power.draw()
