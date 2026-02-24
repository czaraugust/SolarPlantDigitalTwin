import tkinter as tk
from tkinter import ttk, messagebox
import traceback
import matplotlib.dates as mdates

from core.pv_module_model import PVSystemModel
from core.inverter_state_machine import InverterStateMachine

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class PaginaInversorSimulado(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.cached_pv_system = None
        self.cached_static_inputs = {}

        # Histórico para gráfico
        self.trail_data = {
            'timestamps': [],
            'p_ac_sim': [],
            'p_ac_real': []
        }


        # Variáveis de configuração da planta (local à aba)
        self.plant_vars = {
            's1_series': tk.StringVar(value="10"),
            's1_parallel': tk.StringVar(value="1"),
            's2_series': tk.StringVar(value="9"),
            's2_parallel': tk.StringVar(value="1"),
            'p_nominal': tk.StringVar(value="5000"),
            'v_partida': tk.StringVar(value="120"),
        }

        # Máquina de estados do inversor
        self.state_machine = InverterStateMachine(v_partida=120.0)
        self.str_estado = tk.StringVar(value="DESLIGADO")

        # Variáveis de exibição numérica
        self.str_p_dc = tk.StringVar(value="0.0")
        self.str_eff = tk.StringVar(value="0.0%")
        self.str_p_ac_sim = tk.StringVar(value="0.0")
        self.str_p_ac_real = tk.StringVar(value="0.0")

        # Variáveis de energia acumulada
        self.str_energy_real = tk.StringVar(value="0.000")
        self.str_energy_sim = tk.StringVar(value="0.000")
        self.str_clip_real = tk.StringVar(value="0.000")
        self.str_clip_sim = tk.StringVar(value="0.000")

        # Acumuladores internos (Wh)
        self.energy_real_wh = 0.0
        self.energy_sim_wh = 0.0
        self.clip_real_wh = 0.0
        self.clip_sim_wh = 0.0
        self.last_timestamp = None


        self.editar_datasheet_var = tk.BooleanVar(value=False)
        self.datasheet_widgets = []
        self.datasheet_vars = self.controller.dados_datasheet

        self._criar_widgets()
        self.editar_datasheet_var.trace_add(
            "write", self._toggle_datasheet_edit_state)
        self._toggle_datasheet_edit_state()

    def _toggle_datasheet_edit_state(self, *args):
        is_editable = self.editar_datasheet_var.get()
        combo_state = "readonly" if is_editable else "disabled"
        text_state = "normal" if is_editable else "disabled"
        for widget in self.datasheet_widgets:
            if isinstance(widget, ttk.Combobox):
                widget.config(state=combo_state)
            else:
                widget.config(state=text_state)

    def _criar_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        style = ttk.Style()
        style.configure("Compact.TLabel", font=('TkDefaultFont', 6))
        style.configure("Compact.TCheckbutton", font=('TkDefaultFont', 6))

        # ===== SIDEBAR (LEFT) =====
        left_col = ttk.Frame(main_frame)
        left_col.pack(side="left", fill="y", anchor="n")

        # --- Datasheet STC ---
        ds_frame = ttk.LabelFrame(
            left_col, text="Parâmetros do Módulo (Datasheet STC)", padding=5)
        ds_frame.pack(fill="x", pady=3)

        cb_datasheet = ttk.Checkbutton(
            ds_frame, text="Editar Parâmetros",
            variable=self.editar_datasheet_var,
            command=self._toggle_datasheet_edit_state,
            style="Compact.TCheckbutton")
        cb_datasheet.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 3))

        ds_labels = {
            'v_oc': "Tensão Circ. Aberto (Voc) [V]:",
            'i_sc': "Corrente Curto-Circ. (Isc) [A]:",
            'v_mp': "Tensão Máx. Pot. (Vmp) [V]:",
            'i_mp': "Corrente Máx. Pot. (Imp) [A]:",
            'alpha_sc': "Coef. Temp. Isc [A/°C]:",
            'beta_voc': "Coef. Temp. Voc [V/°C]:",
            'gamma_pmp': "Coef. Temp. Pot. (γ) [%/°C]:",
            'cells_in_series': "Nº de Células em Série:",
            'cell_type': "Tipo de Célula:"
        }
        cell_types = ['monoSi', 'multiSi', 'polySi',
                      'cis', 'cigs', 'cdte', 'amorphous']

        for i, (key, text) in enumerate(ds_labels.items(), start=1):
            ttk.Label(ds_frame, text=text, style="Compact.TLabel").grid(
                row=i, column=0, sticky="w", pady=1)
            if key == 'cell_type':
                widget = ttk.Combobox(
                    ds_frame, textvariable=self.datasheet_vars[key],
                    values=cell_types, width=12, state="readonly",
                    font=('TkDefaultFont', 6))
                widget.bind("<<ComboboxSelected>>",
                            lambda e: self.controller.atualizar_calculos_e_telas())
            else:
                widget = ttk.Entry(
                    ds_frame, textvariable=self.datasheet_vars[key],
                    width=15, font=('TkDefaultFont', 6))
                widget.bind(
                    "<KeyRelease>",
                    lambda e: self.controller.atualizar_calculos_e_telas())
            widget.grid(row=i, column=1, sticky="e", padx=5, pady=1)
            self.datasheet_widgets.append(widget)

        # --- Configuração da Planta ---
        plant_frame = ttk.LabelFrame(
            left_col, text="Configuração da Planta", padding=5)
        plant_frame.pack(fill="x", pady=3)

        # String 1
        ttk.Label(plant_frame, text="── String 1 ──",
                  font=('TkDefaultFont', 7, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))

        ttk.Label(plant_frame, text="Painéis em Série:",
                  style="Compact.TLabel").grid(row=1, column=0, sticky="w", pady=1)
        s1_series_entry = ttk.Entry(
            plant_frame, textvariable=self.plant_vars['s1_series'],
            width=8, font=('TkDefaultFont', 6))
        s1_series_entry.grid(row=1, column=1, sticky="e", padx=5, pady=1)

        ttk.Label(plant_frame, text="Painéis em Paralelo:",
                  style="Compact.TLabel").grid(row=2, column=0, sticky="w", pady=1)
        s1_par_entry = ttk.Entry(
            plant_frame, textvariable=self.plant_vars['s1_parallel'],
            width=8, font=('TkDefaultFont', 6))
        s1_par_entry.grid(row=2, column=1, sticky="e", padx=5, pady=1)

        # String 2
        ttk.Label(plant_frame, text="── String 2 ──",
                  font=('TkDefaultFont', 7, 'bold')).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(5, 2))

        ttk.Label(plant_frame, text="Painéis em Série:",
                  style="Compact.TLabel").grid(row=4, column=0, sticky="w", pady=1)
        s2_series_entry = ttk.Entry(
            plant_frame, textvariable=self.plant_vars['s2_series'],
            width=8, font=('TkDefaultFont', 6))
        s2_series_entry.grid(row=4, column=1, sticky="e", padx=5, pady=1)

        ttk.Label(plant_frame, text="Painéis em Paralelo:",
                  style="Compact.TLabel").grid(row=5, column=0, sticky="w", pady=1)
        s2_par_entry = ttk.Entry(
            plant_frame, textvariable=self.plant_vars['s2_parallel'],
            width=8, font=('TkDefaultFont', 6))
        s2_par_entry.grid(row=5, column=1, sticky="e", padx=5, pady=1)

        # Potência Nominal do Inversor
        ttk.Label(plant_frame, text="── Inversor ──",
                  font=('TkDefaultFont', 7, 'bold')).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(5, 2))

        ttk.Label(plant_frame, text="Pot. Nominal [W]:",
                  style="Compact.TLabel").grid(row=7, column=0, sticky="w", pady=1)
        p_nom_entry = ttk.Entry(
            plant_frame, textvariable=self.plant_vars['p_nominal'],
            width=8, font=('TkDefaultFont', 6))
        p_nom_entry.grid(row=7, column=1, sticky="e", padx=5, pady=1)

        ttk.Label(plant_frame, text="V Partida [V]:",
                  style="Compact.TLabel").grid(row=8, column=0, sticky="w", pady=1)
        v_part_entry = ttk.Entry(
            plant_frame, textvariable=self.plant_vars['v_partida'],
            width=8, font=('TkDefaultFont', 6))
        v_part_entry.grid(row=8, column=1, sticky="e", padx=5, pady=1)

        # --- Monitor Numérico ---
        monitor_frame = ttk.LabelFrame(
            left_col, text="Monitor Instantâneo", padding=5)
        monitor_frame.pack(fill="x", pady=3)

        monitor_labels = [
            ("Potência DC [W]:", self.str_p_dc),
            ("Eficiência [%]:", self.str_eff),
            ("AC Simulado [W]:", self.str_p_ac_sim),
            ("AC Real [W]:", self.str_p_ac_real),
            ("Estado Inversor:", self.str_estado),
        ]
        for i, (text, var) in enumerate(monitor_labels):
            ttk.Label(monitor_frame, text=text,
                      font=('TkDefaultFont', 8, 'bold')).grid(
                row=i, column=0, sticky="w", pady=1)
            lbl = ttk.Label(monitor_frame, textvariable=var,
                      font=('TkDefaultFont', 8), width=10,
                      relief="sunken", anchor="center")
            lbl.grid(row=i, column=1, sticky="e", padx=5, pady=1)
            if var is self.str_estado:
                self._estado_label = lbl


        # Separador (ajustar row pois adicionamos 1 campo)
        ttk.Separator(monitor_frame, orient='horizontal').grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=4)

        # Campos de Energia Acumulada
        energy_labels = [
            ("Energia Real [kWh]:", self.str_energy_real),
            ("Energia Simulada [kWh]:", self.str_energy_sim),
            ("Perda Clipping Real [kWh]:", self.str_clip_real),
            ("Perda Clipping Sim. [kWh]:", self.str_clip_sim),
        ]
        for i, (text, var) in enumerate(energy_labels, start=6):
            ttk.Label(monitor_frame, text=text,
                      font=('TkDefaultFont', 7, 'bold')).grid(
                row=i, column=0, sticky="w", pady=1)
            ttk.Label(monitor_frame, textvariable=var,
                      font=('TkDefaultFont', 7), width=10,
                      relief="sunken", anchor="center").grid(
                row=i, column=1, sticky="e", padx=5, pady=1)

        # Botão Reiniciar
        btn_limpar = ttk.Button(
            left_col, text="Reiniciar Simulação",
            command=self._clear_and_restart_trail)
        btn_limpar.pack(pady=10, fill="x")

        # ===== CONTENT (RIGHT) =====
        right_col = ttk.Frame(main_frame)
        right_col.pack(side="left", fill="both", expand=True, padx=10)

        # Gráfico
        graph_frame = ttk.LabelFrame(
            right_col, text="Potência AC: Simulado vs Real", padding=10)
        graph_frame.pack(fill="both", expand=True, pady=10)

        self.fig_power = Figure(dpi=100)
        self.ax_power = self.fig_power.add_subplot(111)
        self.canvas_power = FigureCanvasTkAgg(
            self.fig_power, master=graph_frame)
        self.canvas_power.get_tk_widget().pack(fill="both", expand=True)


    def atualizar_inversor_simulado(self):
        try:
            # --- Datasheet ---
            datasheet = {}
            for key, var in self.datasheet_vars.items():
                if key == 'cell_type':
                    datasheet[key] = var.get()
                else:
                    datasheet[key] = float(var.get())
            datasheet['cells_in_series'] = int(datasheet['cells_in_series'])

            # --- Configuração da Planta ---
            s1_series = int(self.plant_vars['s1_series'].get() or 10)
            s1_parallel = int(self.plant_vars['s1_parallel'].get() or 1)
            s2_series = int(self.plant_vars['s2_series'].get() or 9)
            s2_parallel = int(self.plant_vars['s2_parallel'].get() or 1)

            # Cache check
            plant_config = {
                's1_series': s1_series, 's1_parallel': s1_parallel,
                's2_series': s2_series, 's2_parallel': s2_parallel
            }
            current_static_inputs = {**datasheet, **plant_config}

            pv_system = self.cached_pv_system
            if current_static_inputs != self.cached_static_inputs:
                # Cria sistema com as duas strings
                modules_per_string = [
                    s1_series * s1_parallel,
                    s2_series * s2_parallel
                ]
                pv_system = PVSystemModel(
                    datasheet, [s1_series, s2_series], 1)
                self.cached_pv_system = pv_system
                self.cached_static_inputs = current_static_inputs

            if not pv_system:
                return

            # --- Sensor Temperature (SAPM) ---
            temp_painel_sensor = 0.0
            if hasattr(self.controller, 'pagina_meteorologia'):
                pm = self.controller.pagina_meteorologia
                if hasattr(pm, 'meteo_vars'):
                    t_str = pm.meteo_vars['temp_painel'].get()
                    if t_str:
                        temp_painel_sensor = float(t_str)

            # --- Irradiância ---
            irr_fixo = float(
                self.controller.pagina_painel.saidas_irradiancia[
                    'POA_fixo_global'].get())

            # --- Cálculo DC (Mesmo modelo da Previsão) ---
            p_dc = 0.0
            if irr_fixo > 0:
                res = pv_system.calculate_curves_and_mpp(
                    irr_fixo, 25.0, 1.0,
                    forced_cell_temp=temp_painel_sensor)
                p_dc = res['mpp'][2]  # Power

            # --- Máquina de Estados ---
            v_s1 = float(self.controller.dados_painel['tensao_real'].get() or 0)
            v_s2 = float(self.controller.dados_painel['tensao_real_s2'].get() or 0)

            # Atualizar V_PARTIDA se o usuário alterou
            v_part = float(self.plant_vars['v_partida'].get() or 120)
            self.state_machine.v_partida = v_part

            estado = self.state_machine.step(v_s1, v_s2, p_dc)

            # --- Eficiência e Conversão DC -> AC ---
            p_ac_sim = 0.0
            eff = 0.0
            if estado == InverterStateMachine.LIGADO and p_dc > 50:
                eff = 96.8016 - (9653.1352 / p_dc) - (0.000125 * p_dc)
                if eff > 0:
                    p_ac_sim = p_dc * (eff / 100.0)
                else:
                    eff = 0.0

            # --- Potência Nominal (Clipping) ---
            p_nominal = float(self.plant_vars['p_nominal'].get() or 5000)

            # AC antes do clipping (para calcular perda)
            p_ac_sim_preclip = p_ac_sim
            p_ac_sim = min(p_ac_sim, p_nominal)  # Clipping

            # --- AC Real (CSV) ---
            p_ac_real = float(
                self.controller.dados_painel['potencia_ac'].get() or 0)
            p_ac_real_preclip = p_ac_real  # Real antes do clipping teórico
            p_ac_real_clipped = min(p_ac_real, p_nominal)

            # --- Atualizar Monitor Numérico ---
            self.str_p_dc.set(f"{p_dc:.1f}")
            self.str_eff.set(f"{eff:.1f}%")
            self.str_p_ac_sim.set(f"{p_ac_sim:.1f}")
            self.str_p_ac_real.set(f"{p_ac_real:.1f}")
            self.str_estado.set(estado)

            # Cor do label de estado
            if hasattr(self, '_estado_label'):
                self._estado_label.configure(
                    foreground='green' if estado == InverterStateMachine.LIGADO else 'red')


            # --- Histórico ---
            solar = self.controller.solar_object
            if solar:
                current_time = solar.data_hora
                if (not self.trail_data['timestamps'] or
                        current_time > self.trail_data['timestamps'][-1]):

                    # --- Acumular Energia (Wh) ---
                    if self.last_timestamp is not None:
                        dt_hours = (current_time - self.last_timestamp).total_seconds() / 3600.0
                        if 0 < dt_hours < 1:  # Sanity check
                            # Energia entregue (pós-clipping)
                            self.energy_real_wh += p_ac_real_clipped * dt_hours
                            self.energy_sim_wh += p_ac_sim * dt_hours
                            # Perda por clipping
                            clip_real = max(0, p_ac_real - p_nominal) * dt_hours
                            clip_sim = max(0, p_ac_sim_preclip - p_nominal) * dt_hours
                            self.clip_real_wh += clip_real
                            self.clip_sim_wh += clip_sim

                    self.last_timestamp = current_time

                    # Atualizar displays de energia (kWh)
                    self.str_energy_real.set(f"{self.energy_real_wh / 1000:.3f}")
                    self.str_energy_sim.set(f"{self.energy_sim_wh / 1000:.3f}")
                    self.str_clip_real.set(f"{self.clip_real_wh / 1000:.3f}")
                    self.str_clip_sim.set(f"{self.clip_sim_wh / 1000:.3f}")

                    self.trail_data['timestamps'].append(current_time)
                    self.trail_data['p_ac_sim'].append(p_ac_sim)
                    self.trail_data['p_ac_real'].append(p_ac_real)

                    # Limitar tamanho
                    if len(self.trail_data['timestamps']) > 3600:
                        self.trail_data['timestamps'].pop(0)
                        self.trail_data['p_ac_sim'].pop(0)
                        self.trail_data['p_ac_real'].pop(0)

            self._atualizar_grafico()

        except Exception:
            traceback.print_exc()

    def _atualizar_grafico(self):
        self.ax_power.clear()
        self.ax_power.set_xlabel("Hora")
        self.ax_power.set_ylabel("Potência AC (W)")
        self.ax_power.grid(True, linestyle='--', linewidth=0.5)

        ts = self.trail_data['timestamps']
        if ts:
            # Linha horizontal da potência nominal (desabilitado para debug)
            # try:
            #     p_nom = float(self.plant_vars['p_nominal'].get() or 5000)
            #     self.ax_power.axhline(
            #         y=p_nom, color='red', linewidth=1, linestyle=':',
            #         label=f"P Nominal ({p_nom:.0f}W)")
            # except ValueError:
            #     pass

            self.ax_power.plot(
                ts, self.trail_data['p_ac_sim'],
                label="AC Simulado", color='blue', linewidth=1.5)
            self.ax_power.plot(
                ts, self.trail_data['p_ac_real'],
                label="AC Real", color='green', linewidth=1.5,
                linestyle='--')

            self.ax_power.xaxis.set_major_locator(
                mdates.AutoDateLocator())
            self.ax_power.xaxis.set_major_formatter(
                mdates.DateFormatter('%H:%M'))
            self.fig_power.autofmt_xdate()
            self.ax_power.legend(loc='upper left')

        self.fig_power.tight_layout()
        self.canvas_power.draw()

    def _clear_and_restart_trail(self):
        self.reset_history(confirm=True)

    def reset_history(self, confirm=True):
        if confirm:
            if not messagebox.askyesno(
                    "Confirmar Reinicialização",
                    "Deseja reiniciar o gráfico e zerar métricas?"):
                return

        self.trail_data = {
            'timestamps': [], 'p_ac_sim': [], 'p_ac_real': []
        }
        self.last_timestamp = None
        # NÃO reseta a máquina de estados nem os acumuladores de energia
        self._atualizar_grafico()
